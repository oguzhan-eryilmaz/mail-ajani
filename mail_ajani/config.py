import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Istanbul")
CLAUDE_BIN = os.environ.get("MAIL_AJANI_CLAUDE", str(Path.home() / ".local/bin/claude"))
KEYRING_SERVICE = "mail-ajani"


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
