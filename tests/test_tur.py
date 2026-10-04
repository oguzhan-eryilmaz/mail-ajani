import pytest
from mail_ajani.telegram import TelegramError

from datetime import datetime, timedelta

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
    assert "RuntimeError" in texts and "c: izin yok" in texts
    assert "invalid_grant" not in texts
    assert db.get_meta(conn, "last_fetch:a") is None
    assert db.get_meta(conn, "last_run") == NOON.isoformat()
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


class FailingTg(FakeTg):
    def __init__(self, fail_at):
        super().__init__()
        self.fail_at = fail_at
        self.calls = 0

    def send(self, text, keyboard=None, silent=False):
        self.calls += 1
        if self.calls == self.fail_at:
            raise TelegramError('bağlantı hatası')
        return super().send(text, keyboard, silent)


def train_rule(conn, action):
    for i in range(10):
        mid = make_mail(conn, sender='auto@x.com')
        db.mark_sent(conn, mid, None, ts(1))
        learning.record_user_decision(conn, mid, action, ts(100 + i))


@pytest.mark.parametrize('action, fail_at', [('cop', 1), ('arsiv', 1), ('onemli', 1), ('onemli', 2)])
def test_auto_delivery_recovers_without_reapplying_or_duplicate_card(conn, action, fail_at):
    train_rule(conn, action)
    g = FakeGmail('a', [raw_mail('a', 'g900', sender='auto@x.com')])
    tg = FailingTg(fail_at)
    stats = tur.run_tur(conn, {'a': g}, tg, no_ai, NOON)
    assert stats['incomplete'] is True and db.get_meta(conn, 'last_run') is None
    pending = db.pending_mails(conn)
    assert len(pending) == 1 and pending[0]['sent_at'] is None
    mid = pending[0]['id']
    decision = db.active_decision(conn, mid)
    assert (decision['notified_at'] is not None) == (fail_at == 2)
    # Resume in the same slot; no Gmail client or model is needed for this notification.
    def forbidden_ai(mails, examples):
        raise AssertionError('already applied mail must not be classified')
    stats = tur.run_tur(conn, {}, tg, forbidden_ai, NOON + timedelta(minutes=15))
    assert 'incomplete' not in stats
    assert g.applied == [('g900', action)]
    assert db.pending_mails(conn) == []
    undo_buttons = [b['callback_data'] for m in tg.sent if m['keyboard']
                    for row in m['keyboard']['inline_keyboard'] for b in row
                    if b['callback_data'].startswith('u:')]
    assert undo_buttons == [f"u:{decision['id']}"]
    assert sum('turu</b>' in m['text'] for m in tg.sent) == 1
    cards = [m for m in tg.sent if m['keyboard'] and 'a:cop:' in str(m['keyboard'])]
    assert len(cards) == (1 if action == 'onemli' else 0)
    count = len(tg.sent)
    tur.run_tur(conn, {'a': g}, tg, no_ai, NOON + timedelta(minutes=16), force=True)
    assert len(tg.sent) == count and g.applied == [('g900', action)]


def test_partial_cards_resume_same_slot_and_completed_slot_skips(conn):
    g = FakeGmail('a', [raw_mail('a', f'g{i}') for i in range(1, 4)])
    tg = FailingTg(3)  # summary and first card delivered
    assert tur.run_tur(conn, {'a': g}, tg, no_ai, NOON)['incomplete']
    assert len(db.pending_mails(conn)) == 2
    assert db.get_meta(conn, 'last_run') is None
    later = NOON + timedelta(minutes=15)
    assert 'incomplete' not in tur.run_tur(conn, {'a': g}, tg, no_ai, later)
    ids = [m['keyboard']['inline_keyboard'][0][0]['callback_data'] for m in tg.sent
           if m['keyboard'] and 'a:cop:' in str(m['keyboard'])]
    assert len(ids) == 3 and len(set(ids)) == 3
    assert sum('turu</b>' in m['text'] for m in tg.sent) == 1
    assert db.get_meta(conn, 'last_run') == later.isoformat()
    assert tur.run_tur(conn, {'a': g}, tg, no_ai, later + timedelta(minutes=15)) == {'skipped': True}


def test_warning_delivery_is_retried_even_when_cards_already_sent(conn):
    tg = FailingTg(3)  # summary + card succeed, warning fails
    g = FakeGmail('a', [raw_mail('a', 'g1')])
    stats = tur.run_tur(conn, {'a': g}, tg, lambda m, e: ({}, ['limit doldu']), NOON)
    assert stats['incomplete'] and db.pending_mails(conn) == []
    tur.run_tur(conn, {'a': g}, tg, no_ai, NOON + timedelta(minutes=15))
    assert 'limit doldu' in tg.sent[-1]['text']
    assert db.get_meta(conn, 'pending_warnings') == '[]'
    assert len([m for m in tg.sent if 'a:cop:' in str(m['keyboard'])]) == 1


def test_classifier_exception_clears_old_prediction_and_sends_warning(conn, caplog):
    mid = make_mail(conn, account='a', prediction='cop')
    def broken_ai(mails, examples):
        raise AttributeError('https://example.invalid/SECRET')
    tg = FakeTg()
    tur.run_tur(conn, {}, tg, broken_ai, NOON)
    assert 'tahmin yok' in tg.sent[1]['text']
    assert 'Sınıflandırma yapılamadı' in tg.sent[2]['text']
    assert db.get_mail(conn, mid)['prediction'] is None
    assert 'SECRET' not in str(tg.sent) + caplog.text


def test_more_than_twenty_autos_each_have_undo_and_partial_summary_recovers(conn):
    train_rule(conn, 'cop')
    g = FakeGmail('a', [raw_mail('a', f'g{i}', sender='auto@x.com') for i in range(900, 925)])
    tg = FailingTg(2)
    assert tur.run_tur(conn, {'a': g}, tg, no_ai, NOON)['incomplete']
    assert len(db.pending_mails(conn)) == 5
    assert len(tg.sent[0]['keyboard']['inline_keyboard']) == 4
    stats = tur.run_tur(conn, {'a': g}, tg, no_ai, NOON + timedelta(minutes=15))
    assert stats['auto'] == 5 and len(g.applied) == 25
    undo = [b['callback_data'] for m in tg.sent if m['keyboard']
            for row in m['keyboard']['inline_keyboard'] for b in row]
    assert len(undo) == 25 and len(set(undo)) == 25
    assert all(s.startswith('u:') for s in undo)
    assert db.pending_mails(conn) == []


def test_sends_are_paced(conn, monkeypatch):
    waits = []
    monkeypatch.setattr(tur, 'sleep', waits.append)
    g = FakeGmail('a', [raw_mail('a', 'g1'), raw_mail('a', 'g2')])
    tg = FakeTg()
    tur.run_tur(conn, {'a': g}, tg, no_ai, NOON)
    assert waits == [tur.SEND_INTERVAL_S, tur.SEND_INTERVAL_S]
    assert tur.SEND_INTERVAL_S >= 0.5


def test_failed_fetch_completes_slot_and_recovers_next_slot_without_repeats(conn):
    previous = NOON - timedelta(hours=6)
    db.set_meta(conn, 'last_fetch:a', previous.isoformat())
    g = FakeGmail('a', fail=RuntimeError('https://example.invalid/SECRET'))
    ok = FakeGmail('b', [raw_mail('b', 'g1')])
    tg = FakeTg()
    assert 'incomplete' not in tur.run_tur(conn, {'a': g, 'b': ok}, tg, no_ai, NOON)
    assert db.get_meta(conn, 'last_run') == NOON.isoformat()
    assert db.get_meta(conn, 'last_fetch:a') == previous.isoformat()
    assert 'SECRET' not in str(tg.sent)
    count = len(tg.sent)
    ok.mails.append(raw_mail('b', 'g3'))
    for minutes in (15, 30, 45):
        assert tur.run_tur(conn, {'a': g, 'b': ok}, tg, no_ai,
                           NOON + timedelta(minutes=minutes)) == {'skipped': True}
    assert len(tg.sent) == count
    g.fail = None
    g.mails = [raw_mail('a', 'g2')]
    later = NOON + timedelta(hours=6)
    assert 'incomplete' not in tur.run_tur(conn, {'a': g, 'b': ok}, tg, no_ai, later)
    assert db.get_meta(conn, 'last_run') == later.isoformat()
    assert g.since == previous - timedelta(hours=1)
    cards = [m['keyboard']['inline_keyboard'][0][0]['callback_data'] for m in tg.sent
             if 'a:cop:' in str(m['keyboard'])]
    assert len(cards) == len(set(cards)) == 3
    assert sum('Uyarı' in m['text'] for m in tg.sent) == 1


def test_missing_client_completes_slot_and_recovers_next_slot(conn):
    tg = FakeTg()
    ok = FakeGmail('b', [raw_mail('b', 'g1')])
    stats = tur.run_tur(conn, {'b': ok}, tg, no_ai, NOON, warnings=['a: izin yok'])
    assert 'incomplete' not in stats and db.get_meta(conn, 'last_run') == NOON.isoformat()
    assert db.get_meta(conn, 'last_fetch:a') is None
    count = len(tg.sent)
    for minutes in (15, 30, 45):
        assert tur.run_tur(conn, {'b': ok}, tg, no_ai, NOON + timedelta(minutes=minutes),
                           warnings=['a: izin yok']) == {'skipped': True}
    assert len(tg.sent) == count and sum('Uyarı' in m['text'] for m in tg.sent) == 1
    recovered = FakeGmail('a', [raw_mail('a', 'g2')])
    later = NOON + timedelta(hours=6)
    tur.run_tur(conn, {'a': recovered, 'b': ok}, tg, no_ai, later)
    assert recovered.since == later - timedelta(hours=24)
    assert db.get_meta(conn, 'last_fetch:a') == later.isoformat()
    cards = [m['keyboard']['inline_keyboard'][0][0]['callback_data'] for m in tg.sent
             if 'a:cop:' in str(m['keyboard'])]
    assert len(cards) == len(set(cards)) == 2 and db.pending_mails(conn) == []


def test_long_telegram_retry_after_survives_until_scheduled_retry(conn):
    class RateLimited(FakeTg):
        def send(self, *args, **kwargs):
            raise TelegramError('hız sınırı', retry_after=1800)
    mid = make_mail(conn, account='a')
    assert tur.run_tur(conn, {}, RateLimited(), no_ai, NOON)['incomplete']
    tg = FakeTg()
    assert tur.run_tur(conn, {}, tg, no_ai, NOON + timedelta(minutes=15)) == {'incomplete': True}
    assert tg.sent == [] and db.get_mail(conn, mid)['sent_at'] is None
    assert 'incomplete' not in tur.run_tur(conn, {}, tg, no_ai, NOON + timedelta(minutes=31))
    assert len([m for m in tg.sent if 'a:cop:' in str(m['keyboard'])]) == 1


def test_twenty_five_autos_have_twenty_five_undo_buttons_on_normal_path(conn):
    train_rule(conn, 'arsiv')
    g = FakeGmail('a', [raw_mail('a', f'g{i}', sender='auto@x.com') for i in range(900, 925)])
    tg = FakeTg()
    tur.run_tur(conn, {'a': g}, tg, no_ai, NOON)
    assert len(tg.sent) == 2
    buttons = [b['callback_data'] for m in tg.sent for row in m['keyboard']['inline_keyboard'] for b in row]
    assert len(buttons) == len(set(buttons)) == 25
    assert db.pending_mails(conn) == []


def test_retry_after_deadline_includes_time_spent_classifying(conn, monkeypatch):
    clock = iter([0.0, 300.0])
    monkeypatch.setattr(tur, 'monotonic', lambda: next(clock))
    mid = make_mail(conn, account='a')
    class RateLimited(FakeTg):
        def send(self, *args, **kwargs):
            raise TelegramError('hız sınırı', retry_after=900)
    tur.run_tur(conn, {}, RateLimited(), no_ai, NOON)
    assert db.get_meta(conn, 'telegram_retry_at') == (NOON + timedelta(seconds=1200)).isoformat()
    tg = FakeTg()
    assert tur.run_tur(conn, {}, tg, no_ai, NOON + timedelta(minutes=15)) == {'incomplete': True}
    assert tg.sent == [] and db.get_mail(conn, mid)['sent_at'] is None


@pytest.mark.parametrize('action', ['cop', 'arsiv', 'onemli'])
def test_style_auto_failed_summary_is_recovered_without_a_second_gmail_action(conn, monkeypatch, action):
    monkeypatch.setattr(learning, 'style_authorities', lambda conn: {action})
    g = FakeGmail('a', [raw_mail('a', 'g901')])
    def ai(mails, examples):
        return {m['id']: (action, 'özet') for m in mails}, []
    tg = FailingTg(1)
    assert tur.run_tur(conn, {'a': g}, tg, ai, NOON)['incomplete']
    mid = db.pending_mails(conn)[0]['id']
    assert db.active_decision(conn, mid)['source'] == 'style'
    assert 'incomplete' not in tur.run_tur(conn, {'a': g}, tg, ai, NOON + timedelta(minutes=15))
    assert g.applied == [('g901', action)] and db.pending_mails(conn) == []
    assert sum('a:cop:' in str(m['keyboard']) for m in tg.sent) == (action == 'onemli')


@pytest.mark.parametrize('stdout', ['[]', '"metin"', '{"structured_output":{"items":null}}',
                                    '{"structured_output":{"items":["x"]}}'])
def test_malformed_claude_output_reaches_predictionless_cards_with_warning(conn, stdout):
    import subprocess
    from mail_ajani import classifier
    def runner(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout)
    def ai(mails, examples):
        return classifier.classify(mails, examples, runner=runner)
    tg = FakeTg()
    tur.run_tur(conn, {'a': FakeGmail('a', [raw_mail('a', 'g1')])}, tg, ai, NOON)
    assert len(tg.sent) == 3
    assert 'tahmin yok' in tg.sent[1]['text']
    assert 'Sınıflandırma yapılamadı' in tg.sent[2]['text']
    assert db.get_meta(conn, 'last_run') == NOON.isoformat()


def test_empty_sender_with_style_authority_always_gets_card(conn, monkeypatch):
    monkeypatch.setattr(learning, 'style_authorities', lambda conn: {'cop'})
    g = FakeGmail('a', [raw_mail('a', 'g901', sender='')])
    def ai(mails, examples):
        return {m['id']: ('cop', 'özet') for m in mails}, []
    tg = FakeTg()
    tur.run_tur(conn, {'a': g}, tg, ai, NOON)
    assert g.applied == [] and len(tg.sent) == 2
    assert 'a:cop:' in str(tg.sent[1]['keyboard'])


def test_failed_forced_run_reopens_previously_completed_slot(conn):
    previous = NOON - timedelta(minutes=1)
    db.set_meta(conn, 'last_run', previous.isoformat())
    g = FakeGmail('a', [raw_mail('a', 'g1')])
    tg = FailingTg(1)
    assert tur.run_tur(conn, {'a': g}, tg, no_ai, NOON, force=True)['incomplete']
    assert db.get_meta(conn, 'last_run') == previous.isoformat()
    assert db.get_meta(conn, 'tur_incomplete') == '1'
    later = NOON + timedelta(minutes=15)
    assert 'incomplete' not in tur.run_tur(conn, {'a': g}, tg, no_ai, later)
    assert db.get_meta(conn, 'last_run') == later.isoformat()
    assert db.get_meta(conn, 'tur_incomplete') == '0'
    assert tur.run_tur(conn, {'a': g}, tg, no_ai, later + timedelta(minutes=15)) == {'skipped': True}


@pytest.mark.parametrize('fallback_rejected', [False, True])
def test_permanent_card_rejection_continues_to_other_cards_and_warning(conn, fallback_rejected):
    class RejectCard(FakeTg):
        def send(self, text, keyboard=None, silent=False):
            if 'a:cop:2' in str(keyboard) and ('📬 <i>' in text or fallback_rejected):
                raise TelegramError('kalıcı ret', status_code=400)
            return super().send(text, keyboard, silent)

    g = FakeGmail('a', [raw_mail('a', 'g1', subject='ilk'),
                        raw_mail('a', 'g2', subject='reddedilen'),
                        raw_mail('a', 'g3', subject='sonraki')])
    tg = RejectCard()
    stats = tur.run_tur(conn, {'a': g}, tg, no_ai, NOON, warnings=['b: izin yok'])
    assert 'incomplete' not in stats and db.pending_mails(conn) == []
    assert any('sonraki' in m['text'] for m in tg.sent)
    assert 'b: izin yok' in tg.sent[-1]['text'] and 'Mail #2' in tg.sent[-1]['text']
    rejected = db.get_mail(conn, 2)
    assert rejected['sent_at'] == NOON.isoformat()
    if fallback_rejected:
        import json
        assert json.loads(db.get_meta(conn, 'card_rejections')) == {'2': 400}
        assert rejected['tg_message_id'] is None
        assert 'kısa kart da reddedildi' in tg.sent[-1]['text']
    else:
        card = next(m for m in tg.sent if 'a:cop:2' in str(m['keyboard']))
        assert 'Telegram ayrıntılı kartı reddetti' in card['text']
        assert rejected['tg_message_id'] == card['id']
    count = len(tg.sent)
    tur.run_tur(conn, {'a': g}, tg, no_ai, NOON + timedelta(minutes=15))
    tur.run_tur(conn, {'a': g}, tg, no_ai, NOON + timedelta(hours=6))
    assert len(tg.sent) == count and g.applied == []


def test_permanent_rejection_waits_for_warning_delivery_and_is_not_retried(conn):
    class RejectAndFailWarning(FakeTg):
        def __init__(self):
            super().__init__()
            self.card_attempts = 0
            self.fail_warning = True

        def send(self, text, keyboard=None, silent=False):
            if 'a:cop:2' in str(keyboard):
                self.card_attempts += 1
                raise TelegramError('kalıcı ret', status_code=400)
            if 'Uyarı' in text and self.fail_warning:
                raise TelegramError('geçici hata', status_code=503)
            return super().send(text, keyboard, silent)

    tg = RejectAndFailWarning()
    g = FakeGmail('a', [raw_mail('a', f'g{i}') for i in range(1, 4)])
    assert tur.run_tur(conn, {'a': g}, tg, no_ai, NOON)['incomplete']
    assert [m['id'] for m in db.pending_mails(conn)] == [2]
    assert tg.card_attempts == 2
    assert sum('a:cop:3' in str(m['keyboard']) for m in tg.sent) == 1
    tg.fail_warning = False
    assert 'incomplete' not in tur.run_tur(conn, {'a': g}, tg, no_ai, NOON + timedelta(minutes=15))
    assert tg.card_attempts == 2 and db.pending_mails(conn) == []
    assert sum('turu</b>' in m['text'] for m in tg.sent) == 1
    assert sum('Uyarı' in m['text'] for m in tg.sent) == 1
    assert 'Mail #2' in tg.sent[-1]['text'] and g.applied == []


def test_long_card_payload_is_bounded_before_delivery(conn):
    class LengthCheckingTg(FakeTg):
        def send(self, text, keyboard=None, silent=False):
            if len(text.encode('utf-16-le')) // 2 > 4096:
                raise TelegramError('çok uzun', status_code=400)
            return super().send(text, keyboard, silent)
    mail = raw_mail('a', 'g1', sender='😀&<>' * 5000, subject='😀&<>' * 5000)
    mail.update(sender_name='😀&<>' * 5000, snippet='😀&<>' * 5000)
    tg = LengthCheckingTg()
    assert 'incomplete' not in tur.run_tur(conn, {'a': FakeGmail('a', [mail])}, tg, no_ai, NOON)
    assert len(tg.sent) == 2 and db.pending_mails(conn) == []
    assert 'tahmin yok' in tg.sent[1]['text'] and '…' in tg.sent[1]['text']


def test_resume_sends_summary_if_first_attempt_was_not_delivered(conn):
    tg = FailingTg(1)
    g = FakeGmail('a', [raw_mail('a', 'g1')])
    assert tur.run_tur(conn, {'a': g}, tg, no_ai, NOON)['incomplete']
    assert tg.sent == [] and db.get_meta(conn, 'tur_summary_sent') == '0'
    tur.run_tur(conn, {'a': g}, tg, no_ai, NOON + timedelta(minutes=15))
    assert sum('turu</b>' in m['text'] for m in tg.sent) == 1
    g.mails.append(raw_mail('a', 'g2'))
    tur.run_tur(conn, {'a': g}, tg, no_ai, NOON + timedelta(hours=6))
    assert sum('turu</b>' in m['text'] for m in tg.sent) == 2


def test_partial_classifier_result_keeps_valid_predictions_in_cards(conn):
    import json
    import subprocess
    from mail_ajani import classifier
    def runner(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({'structured_output': {'items': [
            {'id': 1, 'karar': 'onemli', 'ozet': 'geçerli özet'},
            {'id': 2, 'karar': {}, 'ozet': 'https://example.invalid/SECRET'},
        ]}}))
    def ai(mails, examples):
        return classifier.classify(mails, examples, runner=runner)
    tg = FakeTg()
    g = FakeGmail('a', [raw_mail('a', f'g{i}') for i in range(1, 4)])
    tur.run_tur(conn, {'a': g}, tg, ai, NOON)
    assert db.get_mail(conn, 1)['prediction'] == 'onemli'
    assert all(db.get_mail(conn, i)['prediction'] is None for i in (2, 3))
    assert sum('tahmin yok' in m['text'] for m in tg.sent) == 2
    assert 'geçerli özet' in tg.sent[1]['text'] and 'Sınıflandırma yapılamadı' in tg.sent[-1]['text']
    assert 'SECRET' not in str(tg.sent) and 'https://' not in str(tg.sent)
    assert db.pending_mails(conn) == [] and g.applied == []


def test_permanent_card_with_temporary_fallback_failure_continues_and_recovers(conn):
    class RejectThenRetry(FakeTg):
        def __init__(self):
            super().__init__()
            self.ready = False
        def send(self, text, keyboard=None, silent=False):
            if 'a:cop:2' in str(keyboard):
                if '📬 <i>' in text:
                    raise TelegramError('kalıcı ret', status_code=400)
                if not self.ready:
                    raise TelegramError('hız sınırı', status_code=429, retry_after=600)
            return super().send(text, keyboard, silent)
    g = FakeGmail('a', [raw_mail('a', f'g{i}') for i in range(1, 4)])
    tg = RejectThenRetry()
    assert tur.run_tur(conn, {'a': g}, tg, no_ai, NOON, warnings=['b: izin yok'])['incomplete']
    assert [m['id'] for m in db.pending_mails(conn)] == [2]
    assert sum('a:cop:3' in str(m['keyboard']) for m in tg.sent) == 1
    assert sum('b: izin yok' in m['text'] for m in tg.sent) == 1
    count = len(tg.sent)
    assert tur.run_tur(conn, {'a': g}, tg, no_ai, NOON + timedelta(minutes=5)) == {'incomplete': True}
    assert len(tg.sent) == count
    tg.ready = True
    assert 'incomplete' not in tur.run_tur(conn, {'a': g}, tg, no_ai, NOON + timedelta(minutes=15),
                                          warnings=['b: izin yok'])
    cards = [m['keyboard']['inline_keyboard'][0][0]['callback_data'] for m in tg.sent
             if 'a:cop:' in str(m['keyboard'])]
    assert len(cards) == len(set(cards)) == 3 and db.pending_mails(conn) == []
    assert sum('turu</b>' in m['text'] for m in tg.sent) == 1
    assert sum('b: izin yok' in m['text'] for m in tg.sent) == 1
    assert g.applied == []


def test_persistent_account_failure_warns_once_in_each_completed_slot(conn):
    tg = FakeTg()
    bad = FakeGmail('a', fail=RuntimeError('https://example.invalid/SECRET'))
    for hours in (0, 6):
        now = NOON + timedelta(hours=hours)
        assert 'incomplete' not in tur.run_tur(conn, {'a': bad}, tg, no_ai, now)
        assert tur.run_tur(conn, {'a': bad}, tg, no_ai, now + timedelta(minutes=15)) == {'skipped': True}
    assert len(tg.sent) == 2 and all('Uyarı' in m['text'] for m in tg.sent)
    assert db.get_meta(conn, 'last_fetch:a') is None
    assert 'SECRET' not in str(tg.sent) and 'https://' not in str(tg.sent)


def test_recorded_rejection_reconstructs_identified_warning_before_marking_sent(conn):
    mid = make_mail(conn, account='a')
    db.set_meta(conn, 'tur_incomplete', '1')
    db.set_meta(conn, 'tur_summary_sent', '1')
    db.set_meta(conn, 'card_rejections', f'{{"{mid}": 400}}')
    # The durable rejection itself must recover its warning, even if no warning
    # text was saved yet. The mail cannot be marked delivered silently.
    tg = FakeTg()
    stats = tur.run_tur(conn, {}, tg, no_ai, NOON)
    assert 'incomplete' not in stats and db.pending_mails(conn) == []
    assert len(tg.sent) == 1 and f'Mail #{mid}' in tg.sent[0]['text']
    assert 'kısa kart da reddedildi' in tg.sent[0]['text']
    assert db.get_mail(conn, mid)['sent_at'] == NOON.isoformat()


def test_auth_failure_is_not_recorded_as_card_rejection_and_recovers_with_buttons(conn):
    # Denetim tur 3, Ö-A: 403 kart reddi değildir; kartlar düğmeleriyle sonradan gelmeli.
    class Forbidden(FakeTg):
        down = True

        def send(self, text, keyboard=None, silent=False):
            if self.down:
                raise TelegramError('yetki yok', status_code=403)
            return super().send(text, keyboard, silent)

    tg = Forbidden()
    g = FakeGmail('a', [raw_mail('a', f'g{i}') for i in range(1, 4)])
    assert tur.run_tur(conn, {'a': g}, tg, no_ai, NOON)['incomplete']
    assert not db.get_meta(conn, 'card_rejections')
    assert len(db.pending_mails(conn)) == 3
    # Yetki hatasında bir saat beklenir: 15 dakika sonraki çağrı hiçbir şey yapmaz.
    g.since = 'dokunulmadı'
    assert tur.run_tur(conn, {'a': g}, tg, no_ai, NOON + timedelta(minutes=15)) == {'incomplete': True}
    assert g.since == 'dokunulmadı'
    tg.down = False
    stats = tur.run_tur(conn, {'a': g}, tg, no_ai, NOON + timedelta(minutes=61))
    assert 'incomplete' not in stats and db.pending_mails(conn) == []
    cards = [m for m in tg.sent if 'a:cop:' in str(m['keyboard'])]
    assert len(cards) == 3 and g.applied == []
    assert not any('kısa kart da reddedildi' in m['text'] for m in tg.sent)


def test_rejection_warning_names_account_sender_and_subject(conn):
    # Denetim tur 3, Ö-B.
    class RejectCard(FakeTg):
        def send(self, text, keyboard=None, silent=False):
            if 'a:cop:1' in str(keyboard):
                raise TelegramError('kalıcı ret', status_code=400)
            return super().send(text, keyboard, silent)

    tg = RejectCard()
    g = FakeGmail('a', [raw_mail('a', 'g1', sender='banka@ornek.com', subject='Ekstre <Ekim>')])
    assert 'incomplete' not in tur.run_tur(conn, {'a': g}, tg, no_ai, NOON)
    text = tg.sent[-1]['text']
    assert 'Mail #1' in text and 'banka@ornek.com' in text and 'Ekstre &lt;Ekim&gt;' in text
    assert db.pending_mails(conn) == []


def test_many_warnings_are_split_under_telegram_limit(conn):
    class LengthCheckingTg(FakeTg):
        def send(self, text, keyboard=None, silent=False):
            if len(text.encode('utf-16-le')) // 2 > 4096:
                raise TelegramError('çok uzun', status_code=400)
            return super().send(text, keyboard, silent)

    tg = LengthCheckingTg()
    many = [f'hesap{i}: ' + 'x' * 300 for i in range(40)]
    stats = tur.run_tur(conn, {}, tg, no_ai, NOON, warnings=many)
    assert 'incomplete' not in stats
    assert len(tg.sent) > 1 and all('Uyarı' in m['text'] for m in tg.sent)
    assert all(f'hesap{i}:' in ''.join(m['text'] for m in tg.sent) for i in range(40))
    count = len(tg.sent)
    tur.run_tur(conn, {}, tg, no_ai, NOON + timedelta(minutes=15))
    assert len(tg.sent) == count


def test_rejected_warning_falls_back_once_and_closes_slot(conn, caplog):
    class RejectWarning(FakeTg):
        def send(self, text, keyboard=None, silent=False):
            if '<b>Uyarı</b>' in text:
                raise TelegramError('kalıcı ret', status_code=400)
            return super().send(text, keyboard, silent)

    tg = RejectWarning()
    stats = tur.run_tur(conn, {}, tg, no_ai, NOON, warnings=['b: izin yok'])
    assert 'incomplete' not in stats
    assert len(tg.sent) == 1 and 'tur.log' in tg.sent[0]['text']
    assert 'b: izin yok' in caplog.text
    tur.run_tur(conn, {}, tg, no_ai, NOON + timedelta(minutes=15))
    assert len(tg.sent) == 1


def _rule(conn, sender, action='arsiv'):
    for i in range(10):
        mid = make_mail(conn, sender=sender)
        db.mark_sent(conn, mid, None, ts(1))
        learning.record_user_decision(conn, mid, action, ts(100 + i))


def test_summary_with_very_long_senders_stays_under_limit(conn):
    # Denetim tur 4, Ö4-3: 254 karakterlik adreslerle özet 4096 sınırını aşıyordu.
    class LengthCheckingTg(FakeTg):
        def send(self, text, keyboard=None, silent=False):
            if len(text.encode('utf-16-le')) // 2 > 4096:
                raise TelegramError('çok uzun', status_code=400)
            return super().send(text, keyboard, silent)

    senders = [('u%02d' % i) + 'x' * 240 + '@ornek.com' for i in range(20)]
    for s in senders:
        _rule(conn, s)
    g = FakeGmail('a', [raw_mail('a', f'g9{i:02d}', sender=s, subject='k' * 300) for i, s in enumerate(senders)])
    tg = LengthCheckingTg()
    stats = tur.run_tur(conn, {'a': g}, tg, no_ai, NOON)
    assert 'incomplete' not in stats and stats['auto'] == 20
    assert 'Kendi yaptıklarım' in tg.sent[0]['text'] and 'u00' in tg.sent[0]['text']
    assert len(g.applied) == 20


def test_rejected_summary_falls_back_and_cards_still_arrive(conn):
    class RejectSummary(FakeTg):
        def send(self, text, keyboard=None, silent=False):
            if 'Kendi yaptıklarım:\n' in text:
                raise TelegramError('kalıcı ret', status_code=400)
            return super().send(text, keyboard, silent)

    _rule(conn, 'kural@x.com')
    g = FakeGmail('a', [raw_mail('a', 'g901', sender='kural@x.com'), raw_mail('a', 'g902', sender='yeni@x.com')])
    tg = RejectSummary()
    stats = tur.run_tur(conn, {'a': g}, tg, no_ai, NOON)
    assert 'incomplete' not in stats and db.pending_mails(conn) == []
    assert 'ayrıntı gösterilemedi' in tg.sent[0]['text'] and 'u:' in str(tg.sent[0]['keyboard'])
    assert sum('a:cop:' in str(m['keyboard']) for m in tg.sent) == 1
    assert len(g.applied) == 1
    count = len(tg.sent)
    tur.run_tur(conn, {'a': g}, tg, no_ai, NOON + timedelta(minutes=15))
    assert len(tg.sent) == count and len(g.applied) == 1


def test_force_overrides_auth_backoff(conn):
    # Denetim tur 4, Ö4-1: bot düzeltildikten sonra elle çalıştırma bir saat beklemez.
    class Forbidden(FakeTg):
        down = True

        def send(self, text, keyboard=None, silent=False):
            if self.down:
                raise TelegramError('yetki yok', status_code=403)
            return super().send(text, keyboard, silent)

    tg = Forbidden()
    g = FakeGmail('a', [raw_mail('a', 'g1')])
    assert tur.run_tur(conn, {'a': g}, tg, no_ai, NOON)['incomplete']
    tg.down = False
    assert tur.run_tur(conn, {'a': g}, tg, no_ai, NOON + timedelta(minutes=5)) == {'incomplete': True}
    stats = tur.run_tur(conn, {'a': g}, tg, no_ai, NOON + timedelta(minutes=6), force=True)
    assert 'incomplete' not in stats and db.pending_mails(conn) == []
    assert sum('a:cop:' in str(m['keyboard']) for m in tg.sent) == 1
