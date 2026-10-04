import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS mails(
  id INTEGER PRIMARY KEY,
  account TEXT NOT NULL,
  gmail_id TEXT NOT NULL,
  sender TEXT NOT NULL,
  sender_name TEXT,
  subject TEXT,
  snippet TEXT,
  category TEXT,
  received_at TEXT,
  prediction TEXT,
  summary TEXT,
  sent_at TEXT,
  tg_message_id INTEGER,
  UNIQUE(account, gmail_id)
);
CREATE TABLE IF NOT EXISTS decisions(
  id INTEGER PRIMARY KEY,
  mail_id INTEGER NOT NULL REFERENCES mails(id),
  action TEXT NOT NULL,
  source TEXT NOT NULL,
  created_at TEXT NOT NULL,
  notified_at TEXT,
  undone INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS rules(
  id INTEGER PRIMARY KEY,
  sender TEXT NOT NULL UNIQUE,
  action TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX IF NOT EXISTS idx_mails_sender ON mails(sender);
CREATE INDEX IF NOT EXISTS idx_decisions_mail ON decisions(mail_id);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    # The listener can also open a legacy DB while a scheduled run migrates it.
    conn.execute("BEGIN IMMEDIATE")
    if "notified_at" not in {r["name"] for r in conn.execute("PRAGMA table_info(decisions)")}:
        conn.execute("ALTER TABLE decisions ADD COLUMN notified_at TEXT")
    conn.commit()
    return conn


def insert_mail(conn, m: dict) -> int | None:
    cur = conn.execute(
        "INSERT OR IGNORE INTO mails(account, gmail_id, sender, sender_name, subject, snippet, category, received_at) "
        "VALUES(:account, :gmail_id, :sender, :sender_name, :subject, :snippet, :category, :received_at)", m)
    conn.commit()
    return cur.lastrowid if cur.rowcount else None


def get_mail(conn, mail_id: int):
    return conn.execute("SELECT * FROM mails WHERE id=?", (mail_id,)).fetchone()


def pending_mails(conn) -> list:
    return conn.execute(
        "SELECT * FROM mails m WHERE sent_at IS NULL AND NOT EXISTS "
        "(SELECT 1 FROM decisions d WHERE d.mail_id=m.id AND d.undone=0 AND d.source='user') "
        "ORDER BY received_at, id").fetchall()


def mark_notified(conn, decision_id: int, now_iso: str) -> None:
    conn.execute("UPDATE decisions SET notified_at=? WHERE id=?", (now_iso, decision_id))
    conn.commit()


def set_prediction(conn, mail_id: int, prediction: str | None, summary: str | None) -> None:
    conn.execute("UPDATE mails SET prediction=?, summary=? WHERE id=?", (prediction, summary, mail_id))
    conn.commit()


def mark_sent(conn, mail_id: int, tg_message_id: int | None, now_iso: str) -> None:
    conn.execute("UPDATE mails SET sent_at=?, tg_message_id=? WHERE id=?", (now_iso, tg_message_id, mail_id))
    conn.commit()


def add_decision(conn, mail_id: int, action: str, source: str, now_iso: str) -> int:
    cur = conn.execute("INSERT INTO decisions(mail_id, action, source, created_at) VALUES(?,?,?,?)",
                       (mail_id, action, source, now_iso))
    conn.commit()
    return cur.lastrowid


def get_decision(conn, decision_id: int):
    return conn.execute("SELECT * FROM decisions WHERE id=?", (decision_id,)).fetchone()


def active_decision(conn, mail_id: int):
    return conn.execute("SELECT * FROM decisions WHERE mail_id=? AND undone=0 ORDER BY id DESC LIMIT 1",
                        (mail_id,)).fetchone()


def mark_undone(conn, decision_id: int) -> None:
    conn.execute("UPDATE decisions SET undone=1 WHERE id=?", (decision_id,))
    conn.commit()


def get_meta(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, value))
    conn.commit()
