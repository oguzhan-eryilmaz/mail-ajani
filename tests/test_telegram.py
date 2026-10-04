from mail_ajani import telegram

import pytest
import requests

from mail_ajani.telegram import TelegramClient, TelegramError


class FakeResp:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append((url, json))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return FakeResp(r)


def test_send_payload():
    s = FakeSession({"ok": True, "result": {"message_id": 5}})
    tg = TelegramClient("TOKEN", 42, session=s)
    assert tg.send("hi", {"inline_keyboard": []}, silent=True) == 5
    url, body = s.calls[0]
    assert url.endswith("/sendMessage")
    assert body["chat_id"] == 42 and body["parse_mode"] == "HTML" and body["disable_notification"] is True
    assert body["reply_markup"] == {"inline_keyboard": []}


def test_api_error_raises_without_token():
    s = FakeSession({"ok": False, "description": "Bad Request: chat not found"})
    with pytest.raises(TelegramError) as e:
        TelegramClient("SECRET123", 1, session=s).send("x")
    assert "sohbet bulunamadı" in str(e.value) and "SECRET123" not in str(e.value)


def test_network_error_hides_token():
    s = FakeSession(*[requests.ConnectionError("https://api.telegram.org/botSECRET123/sendMessage failed")
                      for _ in range(4)])
    with pytest.raises(TelegramError) as e:
        TelegramClient("SECRET123", 1, session=s).send("x")
    assert "SECRET123" not in str(e.value)
    assert len(s.calls) == 4


def test_edit_ignores_not_modified():
    s = FakeSession({"ok": False, "description": "Bad Request: message is not modified"})
    TelegramClient("T", 1, session=s).edit(3, "same")


def test_updates_and_answer():
    s = FakeSession({"ok": True, "result": [{"update_id": 9}]}, {"ok": True, "result": True})
    tg = TelegramClient("T", 1, session=s)
    assert tg.updates(7) == [{"update_id": 9}]
    assert s.calls[0][1]["offset"] == 7
    tg.answer("cb1", "tamam")
    assert s.calls[1][1] == {"callback_query_id": "cb1", "text": "tamam"}


@pytest.mark.parametrize('failure, expected_wait', [
    ({'ok': False, 'error_code': 429, 'parameters': {'retry_after': 7}}, 7),
    ({'ok': False, 'error_code': 503}, 1),
    (requests.ConnectionError('https://example.invalid/SECRET'), 1),
    (requests.Timeout('https://example.invalid/SECRET'), 1),
])
def test_transient_errors_retry_then_succeed(monkeypatch, failure, expected_wait):
    waits = []
    monkeypatch.setattr(telegram, 'sleep', waits.append)
    session = FakeSession(failure, {'ok': True, 'result': {'message_id': 6}})
    assert TelegramClient('SECRET', 1, session=session).send('x') == 6
    assert waits == [expected_wait] and len(session.calls) == 2


@pytest.mark.parametrize('failure, waits', [
    ({'ok': False, 'error_code': 429, 'parameters': {'retry_after': 7}}, [7, 7, 7]),
    (requests.Timeout('https://example.invalid/SECRET'), [1, 2, 4]),
])
def test_retries_are_bounded_and_exhaustion_is_safe(monkeypatch, failure, waits):
    slept = []
    monkeypatch.setattr(telegram, 'sleep', slept.append)
    session = FakeSession(*[failure] * 4)
    with pytest.raises(TelegramError) as exc:
        TelegramClient('SECRET', 1, session=session).send('x')
    assert len(session.calls) == 4 and slept == waits
    assert 'SECRET' not in str(exc.value) and 'https://' not in str(exc.value)


def test_long_retry_after_is_deferred_without_retrying_early(monkeypatch):
    waits = []
    monkeypatch.setattr(telegram, 'sleep', waits.append)
    session = FakeSession({'ok': False, 'error_code': 429, 'parameters': {'retry_after': 1800}})
    with pytest.raises(TelegramError) as exc:
        TelegramClient('SECRET', 1, session=session).send('x')
    assert exc.value.retry_after == 1800 and len(session.calls) == 1 and waits == []


def test_api_description_cannot_leak_token_or_url():
    session = FakeSession({'ok': False, 'error_code': 400,
                           'description': 'https://api.telegram.org/botSECRET/sendMessage'})
    with pytest.raises(TelegramError) as exc:
        TelegramClient('SECRET', 1, session=session).send('x')
    assert 'SECRET' not in str(exc.value) and 'https://' not in str(exc.value)
    assert len(session.calls) == 1


@pytest.mark.parametrize('code', [400, 401, 403, 404, 422, 429, 503])
def test_error_exposes_safe_permanent_status_without_server_text(code):
    response = {'ok': False, 'error_code': code, 'description': 'https://example.invalid/SECRET'}
    session = FakeSession(*[response] * 4)
    with pytest.raises(TelegramError) as exc:
        TelegramClient('SECRET', 1, session=session).send('x')
    assert exc.value.status_code == code
    assert exc.value.permanent == (code == 400)
    assert exc.value.needs_backoff == (code in (401, 403, 404, 422))
    assert len(session.calls) == (1 if 400 <= code < 500 and code != 429 else 4)
    assert 'SECRET' not in str(exc.value) and 'https://' not in str(exc.value)


def test_chat_not_found_is_not_a_card_rejection():
    session = FakeSession({'ok': False, 'error_code': 400, 'description': 'Bad Request: chat not found'})
    with pytest.raises(TelegramError) as exc:
        TelegramClient('SECRET', 1, session=session).send('x')
    assert not exc.value.permanent and exc.value.needs_backoff


def test_non_json_http_rejection_is_not_a_card_rejection_and_safe():
    class NonJsonResponse:
        status_code = 400
        def json(self):
            raise ValueError('https://example.invalid/SECRET')
    class Session:
        def post(self, *a, **kw):
            return NonJsonResponse()
    with pytest.raises(TelegramError) as exc:
        TelegramClient('SECRET', 1, session=Session()).send('x')
    assert not exc.value.permanent and exc.value.status_code == 400
    assert exc.value.needs_backoff
    assert 'SECRET' not in str(exc.value) and 'https://' not in str(exc.value)
