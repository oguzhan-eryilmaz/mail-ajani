from html import escape

ACTION_BUTTONS = {"cop": "🗑 Çöp", "arsiv": "📦 Arşiv", "onemli": "⭐ Önemli", "kalsin": "✓ Kalsın"}
ACTION_DONE = {"cop": "🗑 Çöpe atıldı", "arsiv": "📦 Arşivlendi", "onemli": "⭐ Önemli işaretlendi",
               "kalsin": "✓ Kutuda bırakıldı"}
PREDICTION_TEXT = {"cop": "çöp", "arsiv": "arşiv", "onemli": "önemli", "kalsin": "kalsın",
                   "emin_degil": "emin değil"}
SOURCE_TEXT = {"rule": "kural", "style": "tarz"}
MAX_AUTOS_LISTED = 20
MAX_RULES_LISTED = 50


def _short_html(text: str, budget: int) -> str:
    # Limit the escaped UTF-16 payload too: entities/tags and astral characters
    # cannot take the card beyond Telegram's limit, even before HTML parsing.
    parts, used = [], 0
    for char in text:
        part = escape(char)
        size = len(part.encode("utf-16-le")) // 2
        if used + size > budget - 1:
            return "".join(parts) + "…"
        parts.append(part)
        used += size
    return "".join(parts)


def card_text(mail) -> str:
    name = mail["sender_name"] or mail["sender"]
    body = mail["summary"] or mail["snippet"] or ""
    prediction = PREDICTION_TEXT.get(mail["prediction"], "tahmin yok")
    return (f"📬 <i>{_short_html(mail['account'], 250)}</i>\n"
            f"👤 <b>{_short_html(name, 400)}</b> &lt;{_short_html(mail['sender'], 350)}&gt;\n"
            f"📝 {_short_html(mail['subject'] or '(konu yok)', 1800)}\n\n"
            f"{_short_html(body, 1000)}\n\n"
            f"🤖 Tahmin: {prediction}")


def fallback_card_text(mail) -> str:
    return (f"📬 Mail #{mail['id']} · {_short_html(mail['account'], 100)}\n"
            "Telegram ayrıntılı kartı reddetti. Mail Gmail'de kayıtlıdır.\n"
            f"📝 {_short_html(mail['subject'] or '(konu yok)', 200)}")


def card_keyboard(mail_id: int) -> dict:
    return {"inline_keyboard": [[{"text": label, "callback_data": f"a:{action}:{mail_id}"}
                                 for action, label in ACTION_BUTTONS.items()]]}


def done_text(mail, action: str) -> str:
    return card_text(mail) + f"\n\n<b>{ACTION_DONE[action]}</b>"


def undo_keyboard(decision_id: int) -> dict:
    return {"inline_keyboard": [[{"text": "↩ Geri al", "callback_data": f"u:{decision_id}"}]]}


def summary_text(slot_label: str, new_count: int, important_count: int, waiting_count: int, autos: list) -> str:
    lines = [f"<b>{escape(slot_label)} turu</b> · {new_count} yeni · {important_count} önemli · "
             f"{waiting_count} senin kararını bekliyor"]
    if autos:
        lines.append("\nKendi yaptıklarım:")
        for i, a in enumerate(autos, 1):
            m = a["mail"]
            lines.append(f"{i}. {ACTION_DONE[a['action']]} ({SOURCE_TEXT[a['source']]}) · "
                         f"{escape(m['sender'])} · {escape((m['subject'] or '')[:60])}")
    return "\n".join(lines)


def summary_keyboard(autos: list) -> dict | None:
    if not autos:
        return None
    buttons = [{"text": f"↩ {i}", "callback_data": f"u:{a['decision_id']}"}
               for i, a in enumerate(autos, 1)]
    return {"inline_keyboard": [buttons[i:i + 5] for i in range(0, len(buttons), 5)]}


def summary_batches(autos: list) -> list[list]:
    return [autos[i:i + MAX_AUTOS_LISTED] for i in range(0, len(autos), MAX_AUTOS_LISTED)] or [[]]


def rules_text(rules, authorities: set[str]) -> str:
    lines = ["<b>Öğrendiklerim</b>", "", "Kesin kurallar:"]
    shown = list(rules)[:MAX_RULES_LISTED]
    lines += [f"• {escape(r['sender'])} → {PREDICTION_TEXT[r['action']]}" for r in shown] or ["• (henüz yok)"]
    if len(rules) > MAX_RULES_LISTED:
        lines.append(f"… ve {len(rules) - MAX_RULES_LISTED} kural daha")
    lines += ["", "Tarz yetkileri (kendi karar verdiğim türler):"]
    lines += [f"• {PREDICTION_TEXT[a]}" for a in sorted(authorities)] or ["• (henüz yok, her şeyi sana soruyorum)"]
    return "\n".join(lines)


def rules_keyboard(rules, authorities: set[str]) -> dict | None:
    rows = [[{"text": f"✕ {r['sender'][:40]}", "callback_data": f"r:{r['id']}"}]
            for r in list(rules)[:MAX_RULES_LISTED]]
    rows += [[{"text": f"✕ Tarz: {PREDICTION_TEXT[a]}", "callback_data": f"y:{a}"}] for a in sorted(authorities)]
    return {"inline_keyboard": rows} if rows else None


def warnings_text(warnings: list[str]) -> str:
    return "⚠️ <b>Uyarı</b>\n" + "\n".join(f"• {escape(w)}" for w in warnings)


MAX_WARNING_UNITS = 3800
MAX_WARNING_LINE_UNITS = 700


def warning_messages(warnings: list[str]) -> list[tuple[str, list[str]]]:
    # Telegram rejects messages over 4096 UTF-16 units; split long warning
    # lists and return which warnings each message carries.
    head = "⚠️ <b>Uyarı</b>"
    out, lines, items, used = [], [], [], 0
    for w in warnings:
        line = "• " + _short_html(w, MAX_WARNING_LINE_UNITS)
        size = len(line.encode("utf-16-le")) // 2 + 1
        if lines and used + size > MAX_WARNING_UNITS:
            out.append((head + "\n" + "\n".join(lines), items))
            lines, items, used = [], [], 0
        lines.append(line)
        items.append(w)
        used += size
    if lines:
        out.append((head + "\n" + "\n".join(lines), items))
    return out


def warnings_fallback_text(count: int) -> str:
    return f"⚠️ {count} uyarı Telegram'a gönderilemedi; ayrıntı tur.log dosyasında."


def status_text(last_run: str | None, pending_count: int, rule_count: int, authorities: set[str]) -> str:
    auth = ", ".join(PREDICTION_TEXT[a] for a in sorted(authorities)) or "yok"
    return (f"<b>Durum</b>\nSon tur: {escape(last_run or 'henüz yok')}\n"
            f"Bekleyen mail: {pending_count}\nKesin kural: {rule_count}\nTarz yetkisi: {auth}")
