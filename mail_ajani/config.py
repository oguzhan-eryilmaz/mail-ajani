import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Istanbul")
CLAUDE_BIN = os.environ.get("MAIL_AJANI_CLAUDE", str(Path.home() / ".local/bin/claude"))
KEYRING_SERVICE = "mail-ajani"

DEFAULT_KATEGORILER = [
    {"ad": "Güvenlik", "tanim": "giriş ve cihaz uyarıları, şifre/passkey/2FA değişiklikleri, yetki ve OAuth izinleri, hesap güvenliği bildirimleri", "onemli": True},
    {"ad": "Fatura", "tanim": "fatura, e-fatura, makbuz, ödeme alındı/ödeme belgesi, abonelik ücreti, vergi ve muhasebe yazışmaları", "onemli": True},
    {"ad": "İşbirliği", "tanim": "sponsorluk, işbirliği, ortaklık, reklam ve marka teklifleri; gerçek bir kişi ya da şirketten gelen iş teklifi", "onemli": True},
    {"ad": "Yazışma", "tanim": "gerçek bir kişinin yazdığı, cevap bekleyebilecek iş ya da kişisel yazışma, destek talebi yanıtları", "onemli": False},
    {"ad": "Hesap", "tanim": "hesap ve üyelik bildirimleri, hoş geldin, sözleşme, e-posta doğrulama, tek kullanımlık kod ve giriş bağlantısı (güvenlik uyarısı olmayanlar)", "onemli": False},
    {"ad": "Geliştirici", "tanim": "GitHub, Vercel ve benzeri araçların depo, issue, PR, dağıtım bildirimleri", "onemli": False},
    {"ad": "Sosyal", "tanim": "LinkedIn, Instagram, YouTube ve benzeri platformların davet, öneri, etkinlik ve özet bildirimleri", "onemli": False},
    {"ad": "Bülten", "tanim": "bülten, ürün duyurusu, kampanya, pazarlama ve tanıtım mailleri", "onemli": False},
]


def get_categories(cfg: dict | None = None) -> list[dict]:
    categories = (load_config() if cfg is None else cfg).get("kategoriler", [])
    if not isinstance(categories, list):
        raise ValueError("kategoriler bir liste olmalı")
    names = set()
    for c in categories:
        if (not isinstance(c, dict) or not isinstance(c.get("ad"), str)
                or not c["ad"].strip() or len(c["ad"]) > 60 or c["ad"] in names
                or not isinstance(c.get("tanim"), str) or type(c.get("onemli")) is not bool
                or ("renk" in c and not isinstance(c["renk"], str))):
            raise ValueError("kategori adı, tanımı, önem veya renk alanı geçersiz")
        names.add(c["ad"])
    return categories


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
    (home() / "config.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
