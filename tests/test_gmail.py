import logging

import pytest
from googleapiclient.http import HttpRequest
from googleapiclient.errors import HttpError
from httplib2 import Response
from mail_ajani import cli

from datetime import datetime
from unittest.mock import MagicMock

from mail_ajani.config import TZ
from mail_ajani.gmail import GmailClient


def service_with(messages, labels=None):
    svc = MagicMock()
    msgs = svc.users.return_value.messages.return_value
    msgs.list.return_value.execute.return_value = {"messages": [{"id": m["id"]} for m in messages]}
    msgs.get.return_value.execute.side_effect = messages
    lab = svc.users.return_value.labels.return_value
    lab.list.return_value.execute.return_value = {"labels": labels or []}
    lab.create.return_value.execute.return_value = {"id": "Lnew"}
    return svc, msgs, lab


def raw(mid, frm="Ali Veli <Ali@X.com>", subject="Selam", labels=("INBOX",), snippet="Merhaba &amp; iyi g&#39;nler"):
    return {"id": mid, "snippet": snippet, "labelIds": list(labels), "internalDate": "1790000000000",
            "payload": {"headers": [{"name": "From", "value": frm}, {"name": "Subject", "value": subject}]}}


def test_fetch_new_parses_headers_and_query():
    svc, msgs, _ = service_with([raw("m1"), raw("m2", labels=("INBOX", "CATEGORY_PROMOTIONS"))])
    since = datetime(2026, 9, 19, 6, tzinfo=TZ)
    out = GmailClient("a@gmail.com", svc).fetch_new(since)
    q = msgs.list.call_args.kwargs["q"]
    assert q == f"in:inbox after:{int(since.timestamp())}"
    assert out[0]["sender"] == "ali@x.com" and out[0]["sender_name"] == "Ali Veli"
    assert out[0]["snippet"] == "Merhaba & iyi g'nler"
    assert out[0]["category"] == "birincil" and out[1]["category"] == "tanitim"
    assert out[0]["account"] == "a@gmail.com" and out[0]["gmail_id"] == "m1"
    assert out[0]["received_at"].endswith("+03:00")


def test_fetch_follows_pages():
    svc = MagicMock()
    msgs = svc.users.return_value.messages.return_value
    msgs.list.return_value.execute.side_effect = [
        {"messages": [{"id": "a"}], "nextPageToken": "t"}, {"messages": [{"id": "b"}]}]
    msgs.get.return_value.execute.side_effect = [raw("a"), raw("b")]
    out = GmailClient("a@gmail.com", svc).fetch_new(datetime(2026, 9, 19, tzinfo=TZ))
    assert [m["gmail_id"] for m in out] == ["a", "b"]


def test_apply_trash_uses_trash_not_delete():
    svc, msgs, _ = service_with([])
    GmailClient("a", svc).apply("m1", "cop")
    msgs.trash.assert_called_with(userId="me", id="m1")
    msgs.delete.assert_not_called()


def test_apply_archive_creates_label_once():
    svc, msgs, lab = service_with([])
    c = GmailClient("a", svc)
    c.apply("m1", "arsiv")
    c.apply("m2", "arsiv")
    assert lab.create.call_count == 1
    body = msgs.modify.call_args.kwargs["body"]
    assert body == {"removeLabelIds": ["INBOX"], "addLabelIds": ["Lnew"]}


def test_apply_star_uses_existing_label():
    svc, msgs, lab = service_with([], labels=[{"id": "L9", "name": "Ajan/Önemli"}])
    GmailClient("a", svc).apply("m1", "onemli")
    assert msgs.modify.call_args.kwargs["body"] == {"addLabelIds": ["STARRED", "L9"]}
    lab.create.assert_not_called()


def test_kalsin_does_nothing():
    svc, msgs, _ = service_with([])
    GmailClient("a", svc).apply("m1", "kalsin")
    msgs.modify.assert_not_called()
    msgs.trash.assert_not_called()


def test_revert():
    svc, msgs, lab = service_with([], labels=[{"id": "LA", "name": "Ajan/Arşiv"}, {"id": "LO", "name": "Ajan/Önemli"}])
    c = GmailClient("a", svc)
    c.revert("m1", "cop")
    msgs.untrash.assert_called_with(userId="me", id="m1")
    # Canlı deneme, 5 Ekim: untrash maili gelen kutusuna geri koymuyor.
    assert msgs.modify.call_args.kwargs["body"] == {"addLabelIds": ["INBOX"]}
    c.revert("m1", "arsiv")
    assert msgs.modify.call_args.kwargs["body"] == {"addLabelIds": ["INBOX"], "removeLabelIds": ["LA"]}
    c.revert("m1", "onemli")
    assert msgs.modify.call_args.kwargs["body"] == {"removeLabelIds": ["STARRED", "LO"]}


def test_every_gmail_request_has_bounded_library_retries():
    svc, msgs, lab = service_with([raw('m1')])
    client = GmailClient('a', svc)
    client.fetch_new(datetime(2026, 9, 19, tzinfo=TZ))
    for action in ('cop', 'arsiv', 'onemli'):
        client.apply('m1', action)
        client.revert('m1', action)
    # Includes message list/get, label list/create, trash/untrash and all modify calls.
    calls = [call for call in svc.mock_calls if str(call[0]).endswith('.execute')]
    assert len(calls) >= 10
    assert all(call.kwargs == {'num_retries': 3} for call in calls)
    msgs.delete.assert_not_called()
    for call in msgs.modify.call_args_list:
        assert 'UNREAD' not in str(call.kwargs)


@pytest.mark.parametrize('statuses, succeeds', [([429, 503, 200], True), ([503] * 4, False)])
def test_library_retries_transient_gmail_errors_without_url_logs(monkeypatch, caplog, statuses, succeeds):
    logger = logging.getLogger('googleapiclient.http')
    monkeypatch.setattr(logger, 'level', logger.level)
    cli._setup_logging('gmail-retry-test')
    statuses = iter(statuses)
    transport = MagicMock()
    transport.request.side_effect = lambda *a, **kw: (Response({'status': next(statuses)}), b'{}')
    request = HttpRequest(transport, lambda resp, data: {},
                          uri='https://example.invalid/private-url', method='POST')
    sleeps = []
    request._sleep = sleeps.append
    request._rand = lambda: 0.5
    svc, msgs, _ = service_with([])
    msgs.trash.return_value = request
    client = GmailClient('a', svc)
    if succeeds:
        client.apply('m1', 'cop')
        assert transport.request.call_count == 3 and sleeps == [1, 2]
    else:
        with pytest.raises(HttpError):
            client.apply('m1', 'cop')
        assert transport.request.call_count == 4 and sleeps == [1, 2, 4]
    assert 'private-url' not in caplog.text and 'https://' not in caplog.text
    msgs.delete.assert_not_called()
