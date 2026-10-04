from mail_ajani import render

MAIL = {"id": 7, "account": "a@gmail.com", "sender": "x@y.com", "sender_name": "X <b>",
        "subject": "Fatura & ödeme", "snippet": "ham", "summary": "Ekim faturası geldi", "prediction": "onemli"}


def test_card_text_escapes_and_shows_prediction():
    t = render.card_text(MAIL)
    assert "X &lt;b&gt;" in t
    assert "Fatura &amp; ödeme" in t
    assert "Ekim faturası geldi" in t
    assert "Tahmin: önemli" in t


def test_card_falls_back_to_snippet():
    t = render.card_text({**MAIL, "summary": None, "prediction": None})
    assert "ham" in t and "tahmin yok" in t


def test_card_keyboard():
    kb = render.card_keyboard(7)
    datas = [b["callback_data"] for b in kb["inline_keyboard"][0]]
    assert datas == ["a:cop:7", "a:arsiv:7", "a:onemli:7", "a:kalsin:7"]


def test_done_and_undo():
    assert "Çöpe atıldı" in render.done_text(MAIL, "cop")
    assert render.undo_keyboard(3)["inline_keyboard"][0][0]["callback_data"] == "u:3"


def test_summary_lists_autos_with_undo():
    autos = [{"decision_id": 10 + i, "mail": MAIL, "action": "cop", "source": "rule"} for i in range(22)]
    t = render.summary_text("12:00", 30, 2, 8, autos)
    assert t.startswith("<b>12:00 turu</b> · 30 yeni · 2 önemli · 8 senin kararını bekliyor")
    assert "1. 🗑 Çöpe atıldı (kural)" in t
    assert "22. 🗑 Çöpe atıldı (kural)" in t and "tane daha" not in t
    kb = render.summary_keyboard(autos)
    flat = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    assert flat == [f"u:{10 + i}" for i in range(22)]
    batches = render.summary_batches(autos)
    assert [len(batch) for batch in batches] == [20, 2]
    assert [a for batch in batches for a in batch] == autos


def test_summary_without_autos():
    assert "Kendi yaptıklarım" not in render.summary_text("06:00", 1, 0, 1, [])
    assert render.summary_keyboard([]) is None


def test_rules():
    rules = [{"id": 1, "sender": "s@x.com", "action": "cop"}]
    t = render.rules_text(rules, {"arsiv"})
    assert "s@x.com → çöp" in t and "• arşiv" in t
    datas = [r[0]["callback_data"] for r in render.rules_keyboard(rules, {"arsiv"})["inline_keyboard"]]
    assert datas == ["r:1", "y:arsiv"]
    assert "henüz yok" in render.rules_text([], set())
    assert render.rules_keyboard([], set()) is None


def test_warnings_escape():
    assert "&lt;x&gt;" in render.warnings_text(["<x>"])


def test_truncation_preserves_html_entities_tags_and_utf16_budget():
    from html.parser import HTMLParser
    class CardParser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.tags = []
        def handle_starttag(self, tag, attrs):
            assert tag in ('b', 'i') and attrs == []
            self.tags.append(tag)
        def handle_endtag(self, tag):
            assert self.tags.pop() == tag
    long = '😀<&>"' * 5000
    mail = {**MAIL, **{key: long for key in ('account', 'sender', 'sender_name', 'subject', 'summary')}}
    for text in (render.card_text(mail), render.done_text(mail, 'onemli'), render.fallback_card_text(mail)):
        assert len(text.encode('utf-16-le')) // 2 < 4096
        assert '…' in text and '&amp;' in text and '&lt;' in text
        parser = CardParser()
        parser.feed(text)
        assert parser.tags == []
