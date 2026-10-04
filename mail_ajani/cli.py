import argparse
import getpass
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler

from . import classifier, config, db, dinleyici, gmail, learning, sirlar, tur
from .telegram import TelegramClient

log = logging.getLogger("mail_ajani")


def _setup_logging(name: str) -> None:
    handler = RotatingFileHandler(config.log_dir() / f"{name}.log", maxBytes=1_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler, logging.StreamHandler()])


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


def cmd_tur(force: bool) -> int:
    cfg = config.load_config()
    tg = _telegram(cfg)
    if tg is None:
        return 2
    conn = db.connect(config.db_path())
    clients, warnings = build_clients(cfg["accounts"])
    stats = tur.run_tur(conn, clients, tg, classifier.classify, datetime.now(config.TZ), force=force,
                        warnings=warnings)
    log.info("tur: %s", stats)
    return 0


def cmd_dinle() -> int:
    cfg = config.load_config()
    tg = _telegram(cfg)
    if tg is None:
        return 2
    conn = db.connect(config.db_path())
    cache: dict = {}

    def get_clients() -> dict:
        missing = [a for a in cfg["accounts"] if a not in cache]
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


def cmd_bot_kur() -> int:
    token = getpass.getpass("BotFather'ın verdiği anahtarı yapıştır (ekranda görünmez): ").strip()
    probe = TelegramClient(token, None)
    input("Şimdi telefonda botuna /start yaz, sonra burada Enter'a bas...")
    updates = probe.updates(0, timeout=0)
    chats = [u["message"]["chat"]["id"] for u in updates if "message" in u]
    if not chats:
        print("Mesaj bulunamadı. Bota /start yazdığından emin ol ve tekrar dene.")
        return 1
    sirlar.set_secret("telegram_token", token)
    cfg = config.load_config()
    cfg["chat_id"] = chats[-1]
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
    gmail.build_client(email).fetch_new(datetime.now(config.TZ))  # connection check
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
    sub.add_parser("dinle")
    sub.add_parser("durum")
    sub.add_parser("bot-kur")
    p_hesap = sub.add_parser("hesap-ekle")
    p_hesap.add_argument("email")
    args = parser.parse_args(argv)

    _setup_logging(args.cmd)
    if args.cmd == "tur":
        return cmd_tur(args.force)
    if args.cmd == "dinle":
        return cmd_dinle()
    if args.cmd == "durum":
        return cmd_durum()
    if args.cmd == "bot-kur":
        return cmd_bot_kur()
    return cmd_hesap_ekle(args.email)
