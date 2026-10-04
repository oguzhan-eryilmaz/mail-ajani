from mail_ajani import db, learning
from tests.helpers import make_mail, ts


def decide(conn, sender, action, i, prediction=None):
    mid = make_mail(conn, sender=sender, prediction=prediction)
    return mid, learning.record_user_decision(conn, mid, action, ts(1000 + i))


def test_rule_after_ten_identical(conn):
    for i in range(9):
        decide(conn, "spam@x.com", "cop", i)
    assert learning.rule_for(conn, "spam@x.com") is None
    decide(conn, "spam@x.com", "cop", 9)
    assert learning.rule_for(conn, "spam@x.com") == "cop"


def test_contradiction_removes_rule(conn):
    for i in range(10):
        decide(conn, "s@x.com", "arsiv", i)
    decide(conn, "s@x.com", "kalsin", 10)
    assert learning.rule_for(conn, "s@x.com") is None


def test_kalsin_never_becomes_rule(conn):
    for i in range(10):
        decide(conn, "k@x.com", "kalsin", i)
    assert learning.rule_for(conn, "k@x.com") is None


def test_starred_sender_never_auto_trashed(conn):
    decide(conn, "boss@x.com", "onemli", 0)
    for i in range(1, 11):
        decide(conn, "boss@x.com", "cop", i)
    assert learning.rule_for(conn, "boss@x.com") is None
    assert learning.auto_action(conn, "boss@x.com", "cop", {"cop"}) is None
    assert learning.auto_action(conn, "boss@x.com", "onemli", {"onemli"}) == ("onemli", "style")


def train_style(conn, action, correct, total=30):
    for i in range(total):
        chosen = action if i < correct else "kalsin"
        decide(conn, f"u{i}@x.com", chosen, i, prediction=action)


def test_style_authority_needs_29_of_30(conn):
    train_style(conn, "arsiv", correct=29)
    assert learning.style_authorities(conn) == {"arsiv"}


def test_style_authority_denied_at_28(conn):
    train_style(conn, "arsiv", correct=28)
    assert learning.style_authorities(conn) == set()


def test_style_authority_needs_full_window(conn):
    train_style(conn, "cop", correct=29, total=29)
    assert learning.style_authorities(conn) == set()


def test_auto_action_prefers_rule(conn):
    for i in range(10):
        decide(conn, "n@x.com", "arsiv", i)
    assert learning.auto_action(conn, "n@x.com", "cop", {"cop"}) == ("arsiv", "rule")
    assert learning.auto_action(conn, "yeni@x.com", "cop", {"cop"}) == ("cop", "style")
    assert learning.auto_action(conn, "yeni@x.com", "cop", set()) is None
    assert learning.auto_action(conn, "yeni@x.com", None, {"cop"}) is None


def test_undo_style_resets_authority(conn):
    train_style(conn, "cop", correct=30)
    assert "cop" in learning.style_authorities(conn)
    mid = make_mail(conn, sender="z@x.com", prediction="cop")
    did = db.add_decision(conn, mid, "cop", "style", ts(2000))
    learning.undo(conn, did, ts(2001))
    assert "cop" not in learning.style_authorities(conn)
    assert db.active_decision(conn, mid) is None


def test_undo_rule_deletes_and_restarts_streak(conn):
    for i in range(10):
        decide(conn, "r@x.com", "cop", i)
    mid = make_mail(conn, sender="r@x.com")
    did = db.add_decision(conn, mid, "cop", "rule", ts(2000))
    learning.undo(conn, did, ts(2001))
    assert learning.rule_for(conn, "r@x.com") is None
    decide(conn, "r@x.com", "cop", 1500)  # one new decision must not revive the rule
    assert learning.rule_for(conn, "r@x.com") is None


def test_delete_rule_restarts_streak(conn):
    for i in range(10):
        decide(conn, "d@x.com", "cop", i)
    rule_id = learning.list_rules(conn)[0]["id"]
    learning.delete_rule(conn, rule_id, ts(2000))
    assert learning.list_rules(conn) == []
    decide(conn, "d@x.com", "cop", 1500)
    assert learning.rule_for(conn, "d@x.com") is None


def test_undo_user_decision_recomputes_rule(conn):
    last = None
    for i in range(10):
        _, last = decide(conn, "q@x.com", "cop", i)
    learning.undo(conn, last, ts(2000))
    assert learning.rule_for(conn, "q@x.com") is None


def test_recent_examples(conn):
    decide(conn, "e@x.com", "cop", 0)
    ex = learning.recent_examples(conn)
    assert ex == [{"sender": "e@x.com", "subject": "Konu", "action": "cop"}]


def test_empty_sender_does_not_form_rule_and_never_uses_style_authority(conn):
    for i in range(10):
        decide(conn, '', 'cop', i)
    assert learning.list_rules(conn) == []
    assert learning.rule_for(conn, '') is None
    assert learning.auto_action(conn, '', 'cop', {'cop'}) is None
    # A stale rule from an old database must not bypass the barrier.
    conn.execute("INSERT INTO rules(sender, action, created_at) VALUES('', 'arsiv', ?)", (ts(1),))
    conn.commit()
    assert learning.rule_for(conn, '') is None
    assert learning.auto_action(conn, '', 'onemli', {'onemli'}) is None
    learning.update_rule_for_sender(conn, '', ts(2000))
    assert learning.list_rules(conn) == []
