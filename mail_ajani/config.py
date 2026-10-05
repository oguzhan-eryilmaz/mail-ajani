import json
import os
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Istanbul")
CLAUDE_BIN = os.environ.get("MAIL_AJANI_CLAUDE", str(Path.home() / ".local/bin/claude"))
KEYRING_SERVICE = "mail-ajani"
FALLBACK_KATEGORI = {"ad": "Diğer", "tanim": "yukarıdakilerin hiçbirine girmeyen mailler", "onemli": False}

DEFAULT_KATEGORILER = [
    {"ad": "Güvenlik", "tanim": "giriş ve cihaz uyarıları, şifre/passkey/2FA değişiklikleri, yetki ve OAuth izinleri, hesap güvenliği bildirimleri", "onemli": True},
    {"ad": "Fatura", "tanim": "fatura, e-fatura, makbuz, ödeme alındı/ödeme belgesi, abonelik ücreti, vergi ve muhasebe yazışmaları", "onemli": True},
    {"ad": "İşbirliği", "tanim": "sponsorluk, işbirliği, ortaklık, reklam ve marka teklifleri; gerçek bir kişi ya da şirketten gelen iş teklifi", "onemli": True},
    {"ad": "Yazışma", "tanim": "gerçek bir kişinin yazdığı, cevap bekleyebilecek iş ya da kişisel yazışma, destek talebi yanıtları", "onemli": False},
    {"ad": "Hesap", "tanim": "hesap ve üyelik bildirimleri, hoş geldin, sözleşme, e-posta doğrulama, tek kullanımlık kod ve giriş bağlantısı (güvenlik uyarısı olmayanlar)", "onemli": False},
    {"ad": "Geliştirici", "tanim": "GitHub, Vercel ve benzeri araçların depo, issue, PR, dağıtım bildirimleri", "onemli": False},
    {"ad": "Sosyal", "tanim": "LinkedIn, Instagram, YouTube ve benzeri platformların davet, öneri, etkinlik ve özet bildirimleri", "onemli": False},
    {"ad": "Bülten", "tanim": "bülten, ürün duyurusu, kampanya, pazarlama ve tanıtım mailleri", "onemli": False},
    dict(FALLBACK_KATEGORI),
]


def get_categories(cfg: dict | None = None) -> list[dict]:
    categories = (load_config() if cfg is None else cfg).get("kategoriler", [])
    if not isinstance(categories, list):
        raise ValueError("kategoriler bir liste olmalı")
    names = set()
    for c in categories:
        if not isinstance(c, dict):
            raise ValueError("her kategori bir nesne olmalı")
        if not isinstance(c.get("ad"), str) or not c["ad"].strip() or len(c["ad"]) > 60:
            raise ValueError("kategori adı boş olamaz; en fazla 60 karakterlik metin olmalı")
        if c["ad"] in names:
            raise ValueError("kategori adları yinelenemez")
        if not isinstance(c.get("tanim"), str):
            raise ValueError("kategori tanımı metin olmalı")
        if type(c.get("onemli")) is not bool:
            raise ValueError("kategori onemli alanı boolean olmalı")
        if "renk" in c and not isinstance(c["renk"], str):
            raise ValueError("kategori renk alanı metin olmalı")
        names.add(c["ad"])
    # Do not rewrite or mutate the operator's list when supplying the fallback.
    out = [dict(c, onemli=False) if c["ad"] == "Diğer" else dict(c) for c in categories]
    if out and "Diğer" not in names:
        out.append(dict(FALLBACK_KATEGORI))
    return out


def home() -> Path:
    p = Path(os.environ.get("MAIL_AJANI_HOME", Path.home() / "Library/Application Support/mail-ajani"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return home() / "ajan.db"


def client_secret_path(account: str | None = None) -> Path:
    if account:
        per_domain = home() / f"client_secret-{account.split('@')[-1]}.json"
        if per_domain.exists():
            return per_domain
    return home() / "client_secret.json"


def log_dir() -> Path:
    p = Path(os.environ.get("MAIL_AJANI_LOGS", Path.home() / "Library/Logs/mail-ajani"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_config() -> dict:
    f = home() / "config.json"
    if not f.exists():
        return {"accounts": [], "chat_id": None}
    return json.loads(f.read_text())


def save_config(cfg: dict) -> None:
    directory = home()
    content = json.dumps(cfg, indent=2, ensure_ascii=False)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix=".config-", suffix=".tmp", delete=False) as f:
            temporary = Path(f.name)
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, directory / "config.json")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
