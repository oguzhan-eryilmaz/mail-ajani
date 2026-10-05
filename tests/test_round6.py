"""Tur-6 regresyonları: yalnız geçici ayar ve sahte dış servisler."""
import json
import subprocess
import unicodedata
from datetime import timedelta
from pathlib import Path

import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response

from mail_ajani import classifier, config, db, dinleyici, learning, tur
from mail_ajani.gmail import GmailClient
from tests.helpers import FakeGmail, FakeTg, raw_mail
from tests.test_gmail import body_part, service_with
from tests.test_kategoriler import ai_for, cards, categories, rule
from tests.test_tur import FailingTg, NOON


def test_fallback_is_added_without_mutating_operator_config():
    cfg = {"kategoriler": [{"ad": "Özel", "tanim": "özel", "onemli": True}]}
    before = json.dumps(cfg)
    assert config.get_categories(cfg) == cfg["kategoriler"] + [config.FALLBACK_KATEGORI]
    assert json.dumps(cfg) == before
    cfg["kategoriler"].append({"ad": "Diğer", "tanim": "genel", "onemli": True})
    result = config.get_categories(cfg)
    assert result[-1]["ad"] == "Diğer" and result[-1]["onemli"] is False
    assert cfg["kategoriler"][-1]["onemli"] is True
    assert config.get_categories({}) == config.get_categories({"kategoriler": []}) == []


def test_eight_unmatched_mails_all_get_diger_without_warning(conn, categories):
    assert categories[-1] == {"ad": "Diğer", "tanim": "yukarıdakilerin hiçbirine girmeyen mailler", "onemli": False}
    g = FakeGmail("a", [raw_mail("a", f"g{i}", subject="Kargo teslim edildi") for i in range(1, 9)])
    tg = FakeTg()

    def runner(cmd, input, **kwargs):
        schema = json.loads(cmd[cmd.index("--json-schema") + 1])["properties"]["items"]["items"]
        assert "kategori" in schema["required"]
        assert schema["properties"]["kategori"] == {"type": "string", "enum": [c["ad"] for c in categories]}
        assert "başka kategori uymuyorsa Diğer seç" in input and "boş dize" not in input
        ids = [json.loads(line)["id"] for line in input.splitlines() if line.startswith('{"id"')]
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"structured_output": {"items": [
            {"id": mid, "karar": "cop", "ozet": "Kargo bildirimi", "kategori": "Diğer"} for mid in ids]}}))

    def ai(mails, examples, **kwargs):
        return classifier.classify(mails, examples, runner=runner, **kwargs)

    stats = tur.run_tur(conn, {"a": g}, tg, ai, NOON)
    assert stats == {"new": 8, "auto": 0, "cards": 8, "warnings": 0}
    assert g.category_labels == [(f"g{i}", "Diğer", None) for i in range(1, 9)]
    assert g.applied == [] and len(cards(tg)) == 8 and len(tg.sent) == 9
    assert all("🏷 Diğer" in m["text"] for m in cards(tg))
    assert [m[0] for m in conn.execute("SELECT content_category FROM mails")] == ["Diğer"] * 8
    assert db.pending_mails(conn) == []


@pytest.mark.parametrize("authority", ["rule", "style"])
@pytest.mark.parametrize("action", ["cop", "arsiv", "onemli"])
def test_diger_allows_existing_sender_and_style_authorities(conn, categories, monkeypatch, authority, action):
    if authority == "rule":
        rule(conn, action=action)
    else:
        monkeypatch.setattr(learning, "style_authorities", lambda conn: {action})
    g = FakeGmail("a", [raw_mail("a", "g900", sender="notifications@github.com")])
    tg = FakeTg()
    stats = tur.run_tur(conn, {"a": g}, tg, ai_for("Diğer", action), NOON)
    assert g.category_labels == [("g900", "Diğer", None)] and g.applied == [("g900", action)]
    mail = conn.execute("SELECT * FROM mails WHERE gmail_id='g900'").fetchone()
    decision = db.active_decision(conn, mail["id"])
    assert (decision["source"], decision["action"]) == (authority, action)
    assert stats["warnings"] == 0 and mail["content_category"] == "Diğer"


@pytest.mark.parametrize("failure", ["missing", "empty", "unknown", "malformed", "down"])
def test_many_unusable_answers_keep_protection_and_only_one_warning(conn, categories, monkeypatch, failure):
    rule(conn)
    monkeypatch.setattr(learning, "style_authorities", lambda conn: {"cop", "arsiv"})
    g = FakeGmail("a", [raw_mail("a", f"g{i}", sender="notifications@github.com") for i in range(900, 908)])
    tg = FakeTg()

    def ai(mails, examples, **kwargs):
        if failure == "down":
            raise RuntimeError("https://invalid/SECRET")
        if failure == "malformed":
            return {}, ["bozuk çıktı"] * 3
        out = classifier.Predictions()
        for m in mails:
            out[m["id"]] = ("cop", "özet")
            if failure != "missing":
                out.categories[m["id"]] = "" if failure == "empty" else "Uydurma"
        return out, []

    stats = tur.run_tur(conn, {"a": g}, tg, ai, NOON)
    assert stats["warnings"] == 1 and len(cards(tg)) == 8
    assert g.applied == g.category_labels == []
    assert sum(m["text"].count("geçerli kategori alınamadı") for m in tg.sent) == 1
    assert "SECRET" not in str(tg.sent)


def test_no_categories_schema_is_byte_identical_to_before_round6():
    # Frozen pre-round schema, independent of the new schema builder.
    old = {"type": "object", "properties": {"items": {"type": "array", "items": {
        "type": "object", "properties": {"id": {"type": "integer"},
        "karar": {"type": "string", "enum": ["cop", "arsiv", "onemli", "kalsin", "emin_degil"]},
        "ozet": {"type": "string"}, "kategori": {"type": "string"}},
        "required": ["id", "karar", "ozet"]}}}, "required": ["items"]}
    cmd = classifier._command([])
    assert cmd[cmd.index("--json-schema") + 1] == json.dumps(old)
    classifier._command(config.DEFAULT_KATEGORILER)
    assert classifier.SCHEMA == old  # Configured calls cannot mutate the legacy schema.


def test_unusable_category_warning_is_single_across_resumed_delivery(conn, categories):
    rule(conn)
    g = FakeGmail("a", [raw_mail("a", f"g{i}", sender="notifications@github.com") for i in range(900, 908)])
    tg = FailingTg(fail_at=3)
    assert tur.run_tur(conn, {"a": g}, tg, ai_for(""), NOON)["incomplete"]
    tur.run_tur(conn, {"a": g}, tg, ai_for(""), NOON + timedelta(minutes=15))
    assert len(cards(tg)) == 8 and db.pending_mails(conn) == []
    assert g.applied == []
    assert sum(m["text"].count("geçerli kategori alınamadı") for m in tg.sent) == 1


VALID = {"ad": "Özel", "tanim": "özel", "onemli": False}
INVALID = [
    ("yanlış", "liste"), ([None], "nesne"), ([dict(VALID, ad=1)], "adı"),
    ([dict(VALID, ad=" ")], "boş"), ([VALID, VALID], "yinelenemez"),
    ([dict(VALID, tanim=[])], "tanımı"), ([dict(VALID, onemli="true")], "onemli"),
    ([dict(VALID, renk=1)], "renk"),
]


@pytest.mark.parametrize("invalid, problem", INVALID)
def test_invalid_config_delivers_using_unconfigured_contract_once_per_slot(
        conn, tmp_path, monkeypatch, invalid, problem):
    monkeypatch.setenv("MAIL_AJANI_HOME", str(tmp_path))
    config.save_config({"kategoriler": invalid})
    g, tg = FakeGmail("a", [raw_mail("a", "g1")]), FakeTg()

    def runner(cmd, input, **kwargs):
        assert cmd == classifier._command([])
        assert "## İçerik kategorileri" not in input
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"structured_output": {"items": [
            {"id": 1, "karar": "kalsin", "ozet": "özet"}]}}))

    def ai(mails, examples, **kwargs):
        assert kwargs == {"kategoriler": []}
        return classifier.classify(mails, examples, runner=runner, **kwargs)

    stats = tur.run_tur(conn, {"a": g}, tg, ai, NOON)
    assert stats == {"new": 1, "auto": 0, "cards": 1, "warnings": 1}
    assert len(cards(tg)) == 1 and db.pending_mails(conn) == []
    assert g.applied == g.category_labels == []
    assert sum(m["text"].count("Kategori ayarı geçersiz:") for m in tg.sent) == 1
    assert problem in tg.sent[-1]["text"]
    assert tur.run_tur(conn, {"a": g}, tg, ai, NOON + timedelta(minutes=5)) == {"skipped": True}
    # A fresh scheduled slot reports the still-invalid setting once again.
    stats = tur.run_tur(conn, {"a": g}, tg, ai, NOON + timedelta(hours=6))
    assert stats["warnings"] == 1
    assert sum(m["text"].count("Kategori ayarı geçersiz:") for m in tg.sent) == 2
    text, _ = dinleyici._rules_view(conn)
    assert "Kategori ayarı geçersiz:" in text and problem in text


def test_invalid_config_warning_survives_outage_without_duplication(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("MAIL_AJANI_HOME", str(tmp_path))
    config.save_config({"kategoriler": "invalid"})
    g, tg = FakeGmail("a", [raw_mail("a", "g1")]), FailingTg(fail_at=2)
    ai = lambda mails, examples, **kwargs: ({m["id"]: ("kalsin", "özet") for m in mails}, [])
    assert tur.run_tur(conn, {"a": g}, tg, ai, NOON)["incomplete"]
    # A changed problem during the same slot must not generate a second warning.
    config.save_config({"kategoriler": [dict(VALID, ad="")]})
    tur.run_tur(conn, {"a": g}, tg, ai, NOON + timedelta(minutes=15))
    assert len(cards(tg)) == 1 and db.pending_mails(conn) == []
    assert sum(m["text"].count("Kategori ayarı geçersiz:") for m in tg.sent) == 1


def test_invalid_config_skips_model_for_rule_mail_but_never_trashes_blind(conn, tmp_path, monkeypatch):
    # Denetim tur 7, E7-1: önceki sözleşme (kural uygulanır) kategori garantisini çiğniyordu.
    monkeypatch.setenv("MAIL_AJANI_HOME", str(tmp_path))
    config.save_config({"kategoriler": "invalid"})
    rule(conn)
    g, tg = FakeGmail("a", [raw_mail("a", "g900", sender="notifications@github.com")]), FakeTg()

    def forbidden(*args, **kwargs):
        pytest.fail("kategoriler kapalıyken gönderen kuralı modeli atlamalı")

    stats = tur.run_tur(conn, {"a": g}, tg, forbidden, NOON)
    assert g.applied == [] and g.category_labels == []
    assert stats["warnings"] == 1 and db.pending_mails(conn) == []
    assert len(cards(tg)) == 1


@pytest.mark.parametrize("fail", [False, True])
def test_save_config_replaces_complete_temp_atomically_and_preserves_old_on_failure(tmp_path, monkeypatch, fail):
    monkeypatch.setenv("MAIL_AJANI_HOME", str(tmp_path))
    old, new = {"accounts": ["eski"]}, {"accounts": ["yeni"], "kategoriler": config.DEFAULT_KATEGORILER}
    config.save_config(old)
    replace = config.os.replace
    calls = []

    def checked_replace(source, destination):
        source, destination = Path(source), Path(destination)
        calls.append((source, destination))
        assert source.parent == destination.parent == tmp_path and source != destination
        assert json.loads(source.read_text()) == new
        assert config.load_config() == old
        if fail:
            raise OSError("sahte hata")
        replace(source, destination)

    monkeypatch.setattr(config.os, "replace", checked_replace)
    if fail:
        with pytest.raises(OSError):
            config.save_config(new)
    else:
        config.save_config(new)
    assert len(calls) == 1 and config.load_config() == (old if fail else new)
    assert list(tmp_path.iterdir()) == [tmp_path / "config.json"]


@pytest.mark.parametrize("existing", ["kategori/güvenlik", unicodedata.normalize("NFD", "Kategori/Güvenlik")])
def test_label_matches_case_and_nfc_without_creation(existing):
    svc, msgs, labels = service_with([], labels=[{"name": existing, "id": "K"}])
    client = GmailClient("a", svc)
    for mid in ("g1", "g2"):
        client.label_category(mid, "Güvenlik")
    labels.create.assert_not_called()
    assert labels.list.call_count == 1
    assert [c.kwargs["body"] for c in msgs.modify.call_args_list] == [{"addLabelIds": ["K"]}] * 2


@pytest.mark.parametrize("color_rejected", [False, True])
def test_409_refreshes_once_then_reuses_existing_label(color_rejected):
    svc, msgs, labels = service_with([])
    labels.list.return_value.execute.side_effect = [
        {"labels": []}, {"labels": [{"name": unicodedata.normalize("NFD", "kategori/güvenlik"), "id": "K"}]}]
    errors = ([HttpError(Response({"status": 400}), b"SECRET")] if color_rejected else [])
    labels.create.return_value.execute.side_effect = errors + [HttpError(Response({"status": 409}), b"SECRET")]
    client = GmailClient("a", svc)
    for mid in ("g1", "g2"):
        client.label_category(mid, "Güvenlik", "#invalid" if color_rejected else None)
    assert labels.list.call_count == 2 and labels.create.call_count == (2 if color_rejected else 1)
    assert [c.kwargs["body"] for c in msgs.modify.call_args_list] == [{"addLabelIds": ["K"]}] * 2
    assert all(c.kwargs == {"num_retries": 3} for c in svc.mock_calls if c[0].endswith(".execute"))
    msgs.delete.assert_not_called()
    msgs.trash.assert_not_called()


def test_409_without_matching_label_stops_after_one_refresh():
    svc, msgs, labels = service_with([])
    labels.create.return_value.execute.side_effect = HttpError(Response({"status": 409}), b"SECRET")
    with pytest.raises(HttpError):
        GmailClient("a", svc).label_category("g1", "Diğer")
    assert labels.list.call_count == 2 and labels.create.call_count == 1
    msgs.modify.assert_not_called()


@pytest.mark.parametrize("mime, content, expected", [
    ("text/plain", "Tam metin ş", "Tam metin ş"),
    ("text/html", "<script>SECRET</script><p>Tam &amp; metin ş</p>", "Tam & metin ş"),
])
def test_attachment_body_is_fetched_read_only_with_charset_and_bounded_retries(mime, content, expected, caplog):
    part = body_part(mime, content, "iso-8859-9", encoding="iso-8859-9")
    data = part["body"].pop("data")
    part["body"].update(attachmentId="external", size=100)
    svc, msgs, labels = service_with([{"id": "m1", "payload": part}])
    attachments = msgs.attachments.return_value
    attachments.get.return_value.execute.return_value = {"data": data}
    assert GmailClient("a", svc).fetch_body("m1") == expected
    msgs.get.assert_called_once_with(userId="me", id="m1", format="full")
    attachments.get.assert_called_once_with(userId="me", messageId="m1", id="external")
    assert [c[0] for c in msgs.mock_calls] == ["get", "get().execute", "attachments", "attachments().get", "attachments().get().execute"]
    assert all(c.kwargs == {"num_retries": 3} for c in msgs.mock_calls if c[0].endswith(".execute"))
    assert labels.mock_calls == [] and content not in caplog.text


def test_real_attachments_are_skipped_and_failed_body_can_use_html_alternative():
    skipped = {"mimeType": "text/plain", "filename": "file.txt", "body": {"attachmentId": "file"}}
    disposition = {"mimeType": "multipart/mixed", "headers": [{"name": "Content-Disposition", "value": "attachment"}], "parts": [
        {"mimeType": "text/plain", "body": {"attachmentId": "file2"}}]}
    external = {"mimeType": "text/plain", "body": {"attachmentId": "body"}}
    svc, msgs, _ = service_with([{"id": "m1", "payload": {"parts": [skipped, disposition, external,
        body_part("text/html", "<p>Okunur alternatif</p>")]}}])
    msgs.attachments.return_value.get.return_value.execute.side_effect = RuntimeError("https://invalid/SECRET")
    assert GmailClient("a", svc).fetch_body("m1") == "Okunur alternatif"
    msgs.attachments.return_value.get.assert_called_once_with(userId="me", messageId="m1", id="body")


@pytest.mark.parametrize("mode", ["missing_data", "fetch_error", "size_only", "hidden_html", "image_only"])
def test_present_unreadable_autoimportant_body_emits_existing_warning_once(conn, categories, caplog, mode):
    part = {"mimeType": "text/plain", "body": {"attachmentId": "body", "size": 10}}
    if mode == "size_only":
        part["body"].pop("attachmentId")
    if mode == "hidden_html":
        part = body_part("text/html", "<script>BODY_PRIVATE_MARKER</script>")
    if mode == "image_only":
        part = {"mimeType": "image/png", "body": {"data": "AA"}}
    svc, msgs, _ = service_with([{"id": "g1", "payload": part}])
    msgs.attachments.return_value.get.return_value.execute.return_value = {}
    if mode == "fetch_error":
        msgs.attachments.return_value.get.return_value.execute.side_effect = RuntimeError("https://invalid/SECRET")
    g = FakeGmail("a", [raw_mail("a", "g1")])
    g.fetch_body = GmailClient("a", svc).fetch_body
    tg = FakeTg()
    stats = tur.run_tur(conn, {"a": g}, tg, ai_for("Fatura"), NOON)
    assert stats["warnings"] == 1 and len(cards(tg)) == 1 and len(tg.sent) == 3
    assert "tam metin okunamadı" in tg.sent[-1]["text"]
    assert all("📄 Tam metin" not in m["text"] for m in tg.sent)
    tur.run_tur(conn, {"a": g}, tg, ai_for("Fatura"), NOON + timedelta(hours=6))
    assert msgs.get.call_count == 1 and len(tg.sent) == 3
    assert "BODY_PRIVATE_MARKER" not in caplog.text + str(tg.sent) + "\n".join(conn.iterdump())
    assert "SECRET" not in caplog.text + str(tg.sent)
    msgs.modify.assert_not_called()
    msgs.delete.assert_not_called()


def test_attachment_full_body_follows_autoimportant_card_without_persistence(conn, categories, caplog):
    private = "BODY_PRIVATE_MARKER ş <&>"
    part = body_part("text/plain", private)
    data = part["body"].pop("data")
    part["body"]["attachmentId"] = "body"
    svc, msgs, _ = service_with([{"id": "g1", "payload": part}])
    msgs.attachments.return_value.get.return_value.execute.return_value = {"data": data}
    g, tg = FakeGmail("a", [raw_mail("a", "g1")]), FakeTg()
    g.fetch_body = GmailClient("a", svc).fetch_body
    stats = tur.run_tur(conn, {"a": g}, tg, ai_for("Fatura"), NOON)
    assert stats["warnings"] == 0 and len(tg.sent) == 3 and len(cards(tg)) == 1
    assert "🏷 Fatura" in tg.sent[1]["text"]
    assert "📄 Tam metin" in tg.sent[2]["text"] and "BODY_PRIVATE_MARKER ş &lt;&amp;&gt;" in tg.sent[2]["text"]
    assert private not in caplog.text + "\n".join(conn.iterdump())
    msgs.attachments.return_value.get.assert_called_once_with(userId="me", messageId="g1", id="body")
    msgs.modify.assert_not_called()
    msgs.trash.assert_not_called()
    msgs.delete.assert_not_called()


@pytest.mark.parametrize("action", ["cop", "arsiv"])
def test_invalid_category_config_never_trashes_or_archives_by_rule(conn, tmp_path, monkeypatch, action):
    # Denetim tur 7, E7-1: bozuk ayarda çöp kuralı fatura mailini sınıflandırmadan çöpe atıyordu.
    from datetime import datetime
    from mail_ajani import db, learning, tur
    from mail_ajani.config import TZ
    from tests.helpers import FakeGmail, FakeTg, make_mail, raw_mail, ts
    monkeypatch.setenv("MAIL_AJANI_HOME", str(tmp_path))
    config.save_config({"kategoriler": "bozuk"})
    for i in range(10):
        mid = make_mail(conn, sender="fatura@sirket.com")
        db.mark_sent(conn, mid, None, ts(1))
        learning.record_user_decision(conn, mid, action, ts(100 + i))
    assert learning.rule_for(conn, "fatura@sirket.com") == action
    g = FakeGmail("a", [raw_mail("a", "g900", sender="fatura@sirket.com", subject="Ekim faturanız")])
    tg = FakeTg()
    stats = tur.run_tur(conn, {"a": g}, tg, lambda m, e, **kw: ({}, []), datetime(2026, 9, 19, 12, 5, tzinfo=TZ))
    assert g.applied == [] and stats["auto"] == 0
    assert sum("a:cop:" in str(m["keyboard"]) for m in tg.sent) == 1
    assert any("Kategori ayarı geçersiz:" in m["text"] for m in tg.sent)
