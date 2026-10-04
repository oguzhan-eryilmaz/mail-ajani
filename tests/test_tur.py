from datetime import datetime

from mail_ajani import db, learning, tur
from mail_ajani.config import TZ
from tests.helpers import FakeGmail, FakeTg, make_mail, raw_mail, ts

NOON = datetime(2026, 9, 19, 12, 5, tzinfo=TZ)
NIGHT = datetime(2026, 9, 19, 0, 5, tzinfo=TZ)


def no_ai(mails, examples):
    return {}, []


def test_no_mail_sends_nothing_but_records_run(conn):
    tg = FakeTg()
    stats = tur.run_tur(conn, {"a": FakeGmail("a")}, tg, no_ai, NOON)
    assert tg.sent == [] and stats["new"] == 0
    assert db.get_meta(conn, "last_run") == NOON.isoformat()


def test_skips_when_slot_already_done(conn):
    db.set_meta(conn, "last_run", datetime(2026, 9, 19, 12, 1, tzinfo=TZ).isoformat())
    assert tur.run_tur(conn, {}, FakeTg(), no_ai, NOON) == {"skipped": True}


def test_cards_sent_once(conn):
    g = FakeGmail("a", [raw_mail("a", "g1"), raw_mail("a", "g2")])
    tg = FakeTg()
    tur.run_tur(conn, {"a": g}, tg, no_ai, NOON)
    assert len(tg.sent) == 3  # summary + 2 cards
    assert "2 yeni" in tg.sent[0]["text"]
    assert tg.sent[1]["keyboard"]["inline_keyboard"][0][0]["callback_data"].startswith("a:cop:")
    tur.run_tur(conn, {"a": g}, tg, no_ai, NOON, force=True)
    assert len(tg.sent) == 3  # same mails are never re-sent


def test_uses_per_account_fetch_window(conn):
    db.set_meta(conn, "last_fetch:a", datetime(2026, 9, 19, 6, 2, tzinfo=TZ).isoformat())
    g = FakeGmail("a")
    tur.run_tur(conn, {"a": g}, FakeTg(), no_ai, NOON)
    assert g.since == datetime(2026, 9, 19, 5, 2, tzinfo=TZ)
    assert db.get_meta(conn, "last_fetch:a") == NOON.isoformat()


def test_night_is_silent(conn):
    tg = FakeTg()
    tur.run_tur(conn, {"a": FakeGmail("a", [raw_mail("a", "g1")])}, tg, no_ai, NIGHT)
    assert all(m["silent"] for m in tg.sent)


def test_rule_auto_trash(conn):
    for i in range(10):
        mid = make_mail(conn, sender="spam@x.com")
        db.mark_sent(conn, mid, None, ts(1))
        learning.record_user_decision(conn, mid, "cop", ts(100 + i))
    g = FakeGmail("a", [raw_mail("a", "g900", sender="spam@x.com")])
    tg = FakeTg()
    asked = []
    tur.run_tur(conn, {"a": g}, tg, lambda m, e: (asked.extend(m), ({}, []))[1], NOON)
    assert g.applied == [("g900", "cop")]
    assert asked == []  # rule-covered mail never goes to the model
    assert len(tg.sent) == 1 and "Çöpe atıldı (kural)" in tg.sent[0]["text"]
    assert tg.sent[0]["keyboard"]["inline_keyboard"][0][0]["callback_data"].startswith("u:")


def test_auto_important_still_sent_as_card(conn):
    for i in range(10):
        mid = make_mail(conn, sender="boss@x.com")
        db.mark_sent(conn, mid, None, ts(1))
        learning.record_user_decision(conn, mid, "onemli", ts(100 + i))
    g = FakeGmail("a", [raw_mail("a", "g901", sender="boss@x.com")])
    tg = FakeTg()
    tur.run_tur(conn, {"a": g}, tg, no_ai, NOON)
    assert g.applied == [("g901", "onemli")]
    assert len(tg.sent) == 2


def test_predictions_saved_and_important_first(conn):
    g = FakeGmail("a", [raw_mail("a", "g1", subject="reklam"), raw_mail("a", "g2", subject="fatura")])

    def ai(mails, examples):
        by_subject = {m["subject"]: m["id"] for m in mails}
        return {by_subject["reklam"]: ("cop", "reklam"), by_subject["fatura"]: ("onemli", "ödeme")}, []

    tg = FakeTg()
    tur.run_tur(conn, {"a": g}, tg, ai, NOON)
    assert "fatura" in tg.sent[1]["text"] and "Tahmin: önemli" in tg.sent[1]["text"]
    assert "1 önemli" in tg.sent[0]["text"]


def test_classifier_error_still_sends_cards_and_warns(conn):
    tg = FakeTg()
    tur.run_tur(conn, {"a": FakeGmail("a", [raw_mail("a", "g1")])}, tg, lambda m, e: ({}, ["limit doldu"]), NOON)
    assert len(tg.sent) == 3
    assert "limit doldu" in tg.sent[-1]["text"]


def test_account_failure_warns_and_others_continue(conn):
    ok = FakeGmail("b", [raw_mail("b", "g1")])
    bad = FakeGmail("a", fail=RuntimeError("invalid_grant"))
    tg = FakeTg()
    tur.run_tur(conn, {"a": bad, "b": ok}, tg, no_ai, NOON, warnings=["c: izin yok"])
    texts = "\n".join(m["text"] for m in tg.sent)
    assert "invalid_grant" in texts and "c: izin yok" in texts
    assert db.get_meta(conn, "last_fetch:a") is None
    assert len(tg.sent) == 3  # summary + 1 card + warning


def test_gmail_apply_failure_falls_back_to_card(conn):
    for i in range(10):
        mid = make_mail(conn, sender="spam@x.com")
        db.mark_sent(conn, mid, None, ts(1))
        learning.record_user_decision(conn, mid, "cop", ts(100 + i))
    g = FakeGmail("a", [raw_mail("a", "g902", sender="spam@x.com")])

    def boom(gid, action):
        raise RuntimeError("503")

    g.apply = boom
    tg = FakeTg()
    tur.run_tur(conn, {"a": g}, tg, no_ai, NOON)
    assert len(tg.sent) == 3  # summary + card + warning
    assert "a:cop:" in str(tg.sent[1]["keyboard"]) and "uygulanamadı" in tg.sent[2]["text"]
