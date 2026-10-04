from mail_ajani import db
from tests.helpers import make_mail, ts


def test_insert_is_idempotent(conn):
    m = {"account": "a@gmail.com", "gmail_id": "x1", "sender": "s@x.com", "sender_name": "S",
         "subject": "K", "snippet": "p", "category": "birincil", "received_at": ts(1)}
    first = db.insert_mail(conn, m)
    assert isinstance(first, int)
    assert db.insert_mail(conn, m) is None
    assert db.get_mail(conn, first)["sender"] == "s@x.com"


def test_pending_includes_unreported_autos_but_excludes_sent_and_user_decided(conn):
    a, b, c, d = make_mail(conn), make_mail(conn), make_mail(conn), make_mail(conn)
    db.mark_sent(conn, a, 10, ts(5))
    db.add_decision(conn, b, "cop", "rule", ts(5))
    db.add_decision(conn, d, "cop", "user", ts(5))
    assert [r["id"] for r in db.pending_mails(conn)] == [b, c]


def test_undone_decision_makes_mail_pending_again(conn):
    a = make_mail(conn)
    d = db.add_decision(conn, a, "cop", "rule", ts(5))
    db.mark_undone(conn, d)
    assert [r["id"] for r in db.pending_mails(conn)] == [a]
    assert db.active_decision(conn, a) is None


def test_active_decision_is_latest(conn):
    a = make_mail(conn)
    db.add_decision(conn, a, "arsiv", "user", ts(5))
    d2 = db.add_decision(conn, a, "cop", "user", ts(6))
    assert db.active_decision(conn, a)["id"] == d2


def test_meta(conn):
    assert db.get_meta(conn, "k") is None
    db.set_meta(conn, "k", "v1")
    db.set_meta(conn, "k", "v2")
    assert db.get_meta(conn, "k") == "v2"


def test_prediction(conn):
    a = make_mail(conn)
    db.set_prediction(conn, a, "onemli", "fatura")
    row = db.get_mail(conn, a)
    assert (row["prediction"], row["summary"]) == ("onemli", "fatura")


def test_existing_database_migrates_notification_column_without_losing_data(tmp_path):
    import sqlite3
    path = tmp_path / 'old.db'
    legacy = sqlite3.connect(path)
    legacy.row_factory = sqlite3.Row
    legacy.executescript(db.SCHEMA.replace('  notified_at TEXT,\n', ''))
    mid = make_mail(legacy)
    did = db.add_decision(legacy, mid, 'onemli', 'rule', ts(5))
    legacy.close()
    conn = db.connect(path)
    assert db.get_mail(conn, mid)['subject'] == 'Konu'
    assert db.active_decision(conn, mid)['id'] == did
    assert db.get_decision(conn, did)['notified_at'] is None
    db.mark_notified(conn, did, ts(6))
    conn.close()
    conn = db.connect(path)
    assert db.get_decision(conn, did)['notified_at'] == ts(6)
    assert [r['id'] for r in db.pending_mails(conn)] == [mid]
    conn.close()
