import argparse
import fcntl
import getpass
import logging
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

from . import classifier, config, db, dinleyici, gmail, learning, sirlar, tur
from .telegram import TelegramClient, TelegramError

log = logging.getLogger("mail_ajani")


def _setup_logging(name: str) -> None:
    handler = RotatingFileHandler(config.log_dir() / f"{name}.log", maxBytes=1_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler, logging.StreamHandler()])
    # googleapiclient's retry warnings include the request URL; our own warnings are safe.
    logging.getLogger("googleapiclient.http").setLevel(logging.CRITICAL)


def build_clients(accounts: list[str], builder=gmail.build_client) -> tuple[dict, list[str]]:
    clients, warnings = {}, []
    for account in accounts:
        try:
            clients[account] = builder(account)
        except Exception as e:
            log.warning("gmail client failed for %s: %s", account, e.__class__.__name__)
            warnings.append(f"{account}: Gmail bağlantısı kurulamadı ({e.__class__.__name__}). "
                            f"Yeniden izin için: mail-ajani hesap-ekle {account}")
    return clients, warnings


def _telegram(cfg: dict) -> TelegramClient | None:
    token = sirlar.get_secret("telegram_token")
    if not token or not cfg.get("chat_id"):
        print("Telegram kurulu değil. Önce: mail-ajani bot-kur")
        return None
    return TelegramClient(token, cfg["chat_id"])


BACKLOG_LIMIT = 200


def cmd_tur(force: bool, geri: int | None = None, onayla: bool = False) -> int:
    with (config.home() / "tur.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Başka bir tur çalışıyor; bu tur atlandı.")
            return 0
        conn = db.connect(config.db_path())
        try:
            now = datetime.now(config.TZ)
            lookback = timedelta(days=geri) if geri else None
            force = force or bool(lookback)
            skipped = tur.skip_result(conn, now, force)
            if skipped is not None:
                log.info("tur: %s", skipped)
                return 1 if skipped.get("incomplete") else 0
            cfg = config.load_config()
            tg = _telegram(cfg)
            if tg is None:
                return 2
            clients, warnings = build_clients(cfg["accounts"])
            if lookback and not onayla:
                # Never flood the phone: count first, stop before sending anything.
                counts = {a: c.count_since(now - lookback, BACKLOG_LIMIT) for a, c in clients.items()}
                over = {a: n for a, n in counts.items() if n > BACKLOG_LIMIT}
                if over:
                    for account in over:
                        print(f"{account}: son {geri} günde {BACKLOG_LIMIT}'den fazla mail var.")
                    print("Hiçbir şey gönderilmedi. Daha kısa bir süre seç ya da --onayla ekle.")
                    return 0
            stats = tur.run_tur(conn, clients, tg, classifier.classify, now, force=force,
                                warnings=warnings, lookback=lookback)
            log.info("tur: %s", stats)
            return 1 if stats.get("incomplete") else 0
        except Exception as e:
            log.warning("Tur tamamlanamadı (%s); yeniden denenecek.", e.__class__.__name__)
            return 1
        finally:
            conn.close()


def cmd_dinle() -> int:
    cfg = config.load_config()
    tg = _telegram(cfg)
    if tg is None:
        return 2
    conn = db.connect(config.db_path())
    cache: dict = {}

    def get_clients() -> dict:
        accounts = config.load_config()["accounts"]
        for account in list(cache):
            if account not in accounts:
                cache.pop(account)
        missing = [a for a in accounts if a not in cache]
        if missing:
            built, _ = build_clients(missing)
            cache.update(built)
        return cache

    dinleyici.run_listener(conn, get_clients, tg, cfg["chat_id"])
    return 0


def cmd_durum() -> int:
    conn = db.connect(config.db_path())
    cfg = config.load_config()
    print(f"Hesaplar: {', '.join(cfg['accounts']) or 'yok'}")
    print(f"Telegram: {'bağlı' if cfg.get('chat_id') and sirlar.get_secret('telegram_token') else 'kurulu değil'}")
    print(f"Son tur: {db.get_meta(conn, 'last_run') or 'henüz yok'}")
    print(f"Bekleyen: {len(db.pending_mails(conn))}")
    print(f"Kesin kural: {len(learning.list_rules(conn))}")
    print(f"Tarz yetkisi: {', '.join(sorted(learning.style_authorities(conn))) or 'yok'}")
    return 0


def cmd_kategori_kur() -> int:
    cfg = config.load_config()
    if "kategoriler" not in cfg:
        cfg["kategoriler"] = [dict(c) for c in config.DEFAULT_KATEGORILER]
        config.save_config(cfg)
        print("Varsayılan kategoriler kuruldu.")
    else:
        print("Mevcut kategori listesi korundu.")
    for c in config.get_categories(cfg):
        print(f"{'⭐ ' if c['onemli'] else ''}{c['ad']}: {c['tanim']}")
    if not cfg["kategoriler"]:
        print("Kategori listesi boş; kategorilendirme kapalı.")
    return 0


def cmd_kategorile() -> int:
    # This lock is shared with scheduled and forced runs, for the entire backfill.
    with (config.home() / "tur.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Başka bir tur veya kategorilendirme çalışıyor; işlem atlandı.")
            return 0
        cfg = config.load_config()
        categories = config.get_categories(cfg)
        if not categories:
            print("Kategoriler tanımlı değil. Kurulum için: mail-ajani kategori-kur")
            return 0
        clients, warnings = build_clients(cfg["accounts"])
        conn = db.connect(config.db_path())
        counts = {c["ad"]: 0 for c in categories}
        by_name = {c["ad"]: c for c in categories}
        failed = 0
        try:
            mails = [m for m in db.uncategorized_mails(conn) if m["account"] in clients]
            examples = learning.recent_examples(conn)
            for start in range(0, len(mails), classifier.CHUNK):
                chunk = mails[start:start + classifier.CHUNK]
                try:
                    predictions, errors = classifier.classify(chunk, examples, kategoriler=categories)
                except Exception as e:
                    predictions, errors = {}, [f"sınıflandırıcı çalışmadı ({e.__class__.__name__})"]
                warnings.extend(errors)
                for mail in chunk:
                    name = getattr(predictions, "categories", {}).get(mail["id"], "")
                    if not isinstance(name, str) or name not in by_name or mail["id"] not in predictions:
                        failed += 1
                        continue
                    try:
                        clients[mail["account"]].label_category(mail["gmail_id"], name, by_name[name].get("renk"))
                    except Exception as e:
                        from googleapiclient.errors import HttpError
                        if isinstance(e, HttpError) and e.resp.status == 404:
                            continue
                        log.warning("Kategorilendirme etiketi uygulanamadı: mail #%s (%s)",
                                    mail["id"], e.__class__.__name__)
                        failed += 1
                        continue
                    db.set_category(conn, mail["id"], name)
                    counts[name] += 1
        finally:
            conn.close()
        for name, count in counts.items():
            print(f"{name}: {count}")
        for warning in dict.fromkeys(warnings):
            print(f"Uyarı: {warning}")
        if failed:
            print(f"Kategori veya etiket uygulanamayan mail: {failed}; sonraki çalıştırmada yeniden denenebilir.")
        return 1 if failed or warnings else 0


def cmd_bot_kur() -> int:
    token = getpass.getpass("BotFather'ın verdiği anahtarı yapıştır (ekranda görünmez): ").strip()
    probe = TelegramClient(token, None)
    input("Şimdi telefonda botuna /start yaz, sonra burada Enter'a bas...")
    try:
        updates = probe.updates(0, timeout=0)
    except TelegramError as e:
        code = e.status_code
        if code in (401, 404):
            print(f"Telegram bu anahtarı tanımadı (kod {code}). Anahtar eksik ya da fazla karakterle "
                  "yapıştırılmış olabilir. BotFather'daki anahtarı baştan sona kopyalayıp komutu yeniden çalıştır.")
        elif code == 409:
            print("Bu bot şu an başka bir yerden dinleniyor (kod 409). Dinleyici çalışıyorsa durdurup yeniden dene.")
        else:
            print(f"Telegram'a ulaşılamadı ({'kod ' + str(code) if code else 'bağlantı hatası'}). "
                  "İnternet bağlantısını kontrol edip yeniden dene.")
        return 1
    chats = [u["message"]["chat"] for u in updates
             if u.get("message", {}).get("text", "").strip() == "/start"]
    if not chats:
        print("Mesaj bulunamadı. Bota /start yazdığından emin ol ve tekrar dene.")
        return 1
    chat = chats[-1]
    name = chat.get("title") or " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")]))
    print(f"Bulunan sohbet: {name or '(ad yok)'} · @{chat.get('username') or '(kullanıcı adı yok)'} · kimlik: {chat['id']}")
    if input("Bu sohbeti sahip olarak kaydetmek için evet yaz: ").strip().lower() != "evet":
        print("Onay verilmedi; Telegram kurulumu kaydedilmedi.")
        return 1
    sirlar.set_secret("telegram_token", token)
    cfg = config.load_config()
    cfg["chat_id"] = chat["id"]
    config.save_config(cfg)
    TelegramClient(token, cfg["chat_id"]).send("✅ Mail Ajanı bağlandı. Bundan sonra mailler buraya gelecek.")
    print("Tamam: Telegram bağlandı, telefonuna deneme mesajı gitti.")
    return 0


def cmd_hesap_ekle(email: str) -> int:
    if not config.client_secret_path(email).exists():
        print(f"Önce Google izin dosyasını şuraya koy: {config.client_secret_path(email)}")
        return 2
    print(f"Tarayıcı açılacak: {email} hesabıyla giriş yapıp izin ver.")
    gmail.authorize(email)
    client = gmail.build_client(email)
    actual = client.svc.users().getProfile(userId="me").execute(num_retries=3)["emailAddress"].lower()
    if actual != email.lower():
        # The browser login decides the account; never keep a token under another name.
        if config.client_secret_path(actual) != config.client_secret_path(email):
            sirlar.delete_secret(f"gmail:{email}")
            print(f"İzin {actual} hesabıyla verildi ama bu adres başka bir izin dosyası gerektiriyor. "
                  f"Komutu doğru adresle yeniden çalıştır: hesap-ekle {actual}")
            return 1
        sirlar.set_secret(f"gmail:{actual}", sirlar.get_secret(f"gmail:{email}"))
        sirlar.delete_secret(f"gmail:{email}")
        print(f"Not: izin {actual} hesabıyla verildi; hesap bu adresle kaydediliyor.")
        email = actual
        client = gmail.build_client(email)
    client.fetch_new(datetime.now(config.TZ))  # connection check
    cfg = config.load_config()
    if email not in cfg["accounts"]:
        cfg["accounts"].append(email)
        config.save_config(cfg)
    print(f"Tamam: {email} bağlandı.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mail-ajani")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_tur = sub.add_parser("tur")
    p_tur.add_argument("--force", action="store_true")
    p_tur.add_argument("--geri", type=int, metavar="GUN", help="birikmiş mailler için son GUN günü tara")
    p_tur.add_argument("--onayla", action="store_true", help="--geri sınırını aş")
    sub.add_parser("dinle")
    sub.add_parser("durum")
    sub.add_parser("bot-kur")
    sub.add_parser("kategori-kur")
    sub.add_parser("kategorile")
    p_hesap = sub.add_parser("hesap-ekle")
    p_hesap.add_argument("email")
    args = parser.parse_args(argv)

    _setup_logging(args.cmd)
    if args.cmd == "tur":
        if args.geri is not None and args.geri < 1:
            parser.error("--geri en az 1 olmalı")
        return cmd_tur(args.force, args.geri, args.onayla)
    if args.cmd == "dinle":
        return cmd_dinle()
    if args.cmd == "durum":
        return cmd_durum()
    if args.cmd == "bot-kur":
        return cmd_bot_kur()
    if args.cmd == "kategori-kur":
        return cmd_kategori_kur()
    if args.cmd == "kategorile":
        return cmd_kategorile()
    return cmd_hesap_ekle(args.email)
