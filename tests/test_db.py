from mail_ajani import db
from tests.helpers import make_mail, ts


def test_insert_is_idempotent(conn):
    m = {"account": "a@gmail.com", "gmail_id": "x1", "sender": "s@x.com", "sender_name": "S",
         "subject": "K", "snippet": "p", "category": "birincil", "received_at": ts(1)}
    first = db.insert_mail(conn, m)
    assert isinstance(first, int)
    assert db.insert_mail(conn, m) is None
    assert db.get_mail(conn, first)["sender"] == "s@x.com"


def test_pending_excludes_sent_and_decided(conn):
    a, b, c = make_mail(conn), make_mail(conn), make_mail(conn)
    db.mark_sent(conn, a, 10, ts(5))
    db.add_decision(conn, b, "cop", "rule", ts(5))
    assert [r["id"] for r in db.pending_mails(conn)] == [c]


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
