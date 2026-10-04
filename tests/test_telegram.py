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
    assert "chat not found" in str(e.value) and "SECRET123" not in str(e.value)


def test_network_error_hides_token():
    s = FakeSession(requests.ConnectionError("https://api.telegram.org/botSECRET123/sendMessage failed"))
    with pytest.raises(TelegramError) as e:
        TelegramClient("SECRET123", 1, session=s).send("x")
    assert "SECRET123" not in str(e.value)


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
