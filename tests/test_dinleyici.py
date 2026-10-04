import pytest
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from httplib2 import Response
from mail_ajani.gmail import GmailAuthError

from datetime import datetime

from mail_ajani import db, dinleyici, learning
from mail_ajani.config import TZ
from tests.helpers import FakeGmail, FakeTg, make_mail, ts

NOW = datetime(2026, 9, 19, 13, 0, tzinfo=TZ)
OWNER = 42


def cb(data, message_id=500, chat=OWNER):
    return {"update_id": 1, "callback_query": {"id": "cb", "data": data,
                                               "message": {"message_id": message_id, "chat": {"id": chat}}}}


def msg(text, chat=OWNER):
    return {"update_id": 2, "message": {"text": text, "chat": {"id": chat}}}


def setup(conn):
    mid = make_mail(conn, account="a", sender="s@x.com")
    db.mark_sent(conn, mid, 500, ts(1))
    return mid, FakeGmail("a"), FakeTg()


def test_button_applies_and_records(conn):
    mid, g, tg = setup(conn)
    dinleyici.handle_update(conn, cb(f"a:cop:{mid}"), {"a": g}, tg, OWNER, NOW)
    gid = db.get_mail(conn, mid)["gmail_id"]
    assert g.applied == [(gid, "cop")]
    d = db.active_decision(conn, mid)
    assert (d["action"], d["source"]) == ("cop", "user")
    assert "Çöpe atıldı" in tg.edited[0]["text"]
    assert tg.edited[0]["keyboard"]["inline_keyboard"][0][0]["callback_data"] == f"u:{d['id']}"


def test_other_chat_ignored(conn):
    mid, g, tg = setup(conn)
    dinleyici.handle_update(conn, cb(f"a:cop:{mid}", chat=999), {"a": g}, tg, OWNER, NOW)
    dinleyici.handle_update(conn, msg("/kurallar", chat=999), {"a": g}, tg, OWNER, NOW)
    assert g.applied == [] and tg.sent == [] and tg.edited == []


def test_undo_from_card_restores_buttons(conn):
    mid, g, tg = setup(conn)
    dinleyici.handle_update(conn, cb(f"a:arsiv:{mid}"), {"a": g}, tg, OWNER, NOW)
    did = db.active_decision(conn, mid)["id"]
    dinleyici.handle_update(conn, cb(f"u:{did}"), {"a": g}, tg, OWNER, NOW)
    assert g.reverted == [(db.get_mail(conn, mid)["gmail_id"], "arsiv")]
    assert db.active_decision(conn, mid) is None
    assert tg.edited[-1]["keyboard"]["inline_keyboard"][0][0]["callback_data"] == f"a:cop:{mid}"


def test_undo_from_summary_sends_new_card(conn):
    mid = make_mail(conn, account="a")
    db.mark_sent(conn, mid, None, ts(1))
    did = db.add_decision(conn, mid, "cop", "rule", ts(2))
    g, tg = FakeGmail("a"), FakeTg()
    dinleyici.handle_update(conn, cb(f"u:{did}", message_id=777), {"a": g}, tg, OWNER, NOW)
    assert len(tg.sent) == 1 and f"a:cop:{mid}" in str(tg.sent[0]["keyboard"])
    assert db.get_mail(conn, mid)["tg_message_id"] == tg.sent[0]["id"]


def test_changing_auto_important_reverts_first(conn):
    mid, g, tg = setup(conn)
    db.add_decision(conn, mid, "onemli", "style", ts(2))
    dinleyici.handle_update(conn, cb(f"a:arsiv:{mid}"), {"a": g}, tg, OWNER, NOW)
    gid = db.get_mail(conn, mid)["gmail_id"]
    assert g.reverted == [(gid, "onemli")] and g.applied == [(gid, "arsiv")]
    assert db.active_decision(conn, mid)["action"] == "arsiv"


def test_same_action_twice_is_noop(conn):
    mid, g, tg = setup(conn)
    dinleyici.handle_update(conn, cb(f"a:cop:{mid}"), {"a": g}, tg, OWNER, NOW)
    dinleyici.handle_update(conn, cb(f"a:cop:{mid}"), {"a": g}, tg, OWNER, NOW)
    assert len(g.applied) == 1


def test_gmail_error_not_recorded(conn):
    mid, g, tg = setup(conn)

    def boom(gid, action):
        raise RuntimeError("503")

    g.apply = boom
    dinleyici.handle_update(conn, cb(f"a:cop:{mid}"), {"a": g}, tg, OWNER, NOW)
    assert db.active_decision(conn, mid) is None
    assert "tekrar dene" in tg.answered[-1]


def test_rules_command_and_delete(conn):
    for i in range(10):
        m = make_mail(conn, sender="spam@x.com")
        learning.record_user_decision(conn, m, "cop", ts(100 + i))
    g, tg = FakeGmail("a"), FakeTg()
    dinleyici.handle_update(conn, msg("/kurallar"), {"a": g}, tg, OWNER, NOW)
    assert "spam@x.com → çöp" in tg.sent[0]["text"]
    rule_id = learning.list_rules(conn)[0]["id"]
    dinleyici.handle_update(conn, cb(f"r:{rule_id}", message_id=tg.sent[0]["id"]), {"a": g}, tg, OWNER, NOW)
    assert learning.list_rules(conn) == []
    assert "henüz yok" in tg.edited[-1]["text"]


def test_status_command(conn):
    g, tg = FakeGmail("a"), FakeTg()
    dinleyici.handle_update(conn, msg("/durum"), {"a": g}, tg, OWNER, NOW)
    assert "Son tur" in tg.sent[0]["text"]


def test_run_listener_persists_offset(conn):
    class Tg(FakeTg):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def updates(self, offset, timeout=50):
            self.calls += 1
            return [{"update_id": 10, "message": {"text": "/durum", "chat": {"id": OWNER}}}] if self.calls == 1 else []

    tg = Tg()
    dinleyici.run_listener(conn, lambda: {}, tg, OWNER, stop=lambda: tg.calls >= 2)
    assert db.get_meta(conn, "tg_offset") == "11"


def test_undo_auto_important_from_summary_edits_existing_card_without_sending(conn):
    mid, g, tg = setup(conn)
    did = db.add_decision(conn, mid, 'onemli', 'rule', ts(2))
    dinleyici.handle_update(conn, cb(f'u:{did}', message_id=777), {'a': g}, tg, OWNER, NOW)
    assert tg.sent == []
    assert tg.edited[-1]['id'] == 500
    assert 'a:cop:' in str(tg.edited[-1]['keyboard'])
    assert db.get_mail(conn, mid)['tg_message_id'] == 500
    assert db.active_decision(conn, mid) is None
    assert g.reverted == [(db.get_mail(conn, mid)['gmail_id'], 'onemli')]


@pytest.mark.parametrize('error', [
    GmailAuthError('SECRET'), RefreshError('SECRET'), HttpError(Response({'status': 401}), b'SECRET'),
])
@pytest.mark.parametrize('undo', [False, True])
def test_auth_failure_invalidates_cached_client_for_action_and_undo(conn, error, undo, caplog):
    mid, g, tg = setup(conn)
    def denied(gid, action):
        raise error
    g.apply = g.revert = denied
    clients = {'a': g}
    if undo:
        did = db.add_decision(conn, mid, 'cop', 'rule', ts(2))
        update = cb(f'u:{did}')
    else:
        update = cb(f'a:cop:{mid}')
    dinleyici.handle_update(conn, update, clients, tg, OWNER, NOW)
    assert clients == {}
    assert 'tekrar dene' in tg.answered[-1]
    assert 'SECRET' not in caplog.text + str(tg.answered)


def test_transient_gmail_error_keeps_cached_client(conn):
    mid, g, tg = setup(conn)
    def unavailable(gid, action):
        raise HttpError(Response({'status': 503}), b'temporary')
    g.apply = unavailable
    clients = {'a': g}
    dinleyici.handle_update(conn, cb(f'a:cop:{mid}'), clients, tg, OWNER, NOW)
    assert clients == {'a': g} and db.active_decision(conn, mid) is None
