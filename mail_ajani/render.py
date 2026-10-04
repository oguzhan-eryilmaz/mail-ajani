from html import escape

ACTION_BUTTONS = {"cop": "🗑 Çöp", "arsiv": "📦 Arşiv", "onemli": "⭐ Önemli", "kalsin": "✓ Kalsın"}
ACTION_DONE = {"cop": "🗑 Çöpe atıldı", "arsiv": "📦 Arşivlendi", "onemli": "⭐ Önemli işaretlendi",
               "kalsin": "✓ Kutuda bırakıldı"}
PREDICTION_TEXT = {"cop": "çöp", "arsiv": "arşiv", "onemli": "önemli", "kalsin": "kalsın",
                   "emin_degil": "emin değil"}
SOURCE_TEXT = {"rule": "kural", "style": "tarz"}
MAX_AUTOS_LISTED = 20
MAX_RULES_LISTED = 50


def card_text(mail) -> str:
    name = mail["sender_name"] or mail["sender"]
    body = mail["summary"] or mail["snippet"] or ""
    prediction = PREDICTION_TEXT.get(mail["prediction"], "tahmin yok")
    return (f"📬 <i>{escape(mail['account'])}</i>\n"
            f"👤 <b>{escape(name)}</b> &lt;{escape(mail['sender'])}&gt;\n"
            f"📝 {escape(mail['subject'] or '(konu yok)')}\n\n"
            f"{escape(body)}\n\n"
            f"🤖 Tahmin: {prediction}")


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
        for i, a in enumerate(autos[:MAX_AUTOS_LISTED], 1):
            m = a["mail"]
            lines.append(f"{i}. {ACTION_DONE[a['action']]} ({SOURCE_TEXT[a['source']]}) · "
                         f"{escape(m['sender'])} · {escape((m['subject'] or '')[:60])}")
        if len(autos) > MAX_AUTOS_LISTED:
            lines.append(f"… ve {len(autos) - MAX_AUTOS_LISTED} tane daha")
    return "\n".join(lines)


def summary_keyboard(autos: list) -> dict | None:
    if not autos:
        return None
    buttons = [{"text": f"↩ {i}", "callback_data": f"u:{a['decision_id']}"}
               for i, a in enumerate(autos[:MAX_AUTOS_LISTED], 1)]
    return {"inline_keyboard": [buttons[i:i + 5] for i in range(0, len(buttons), 5)]}


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


def status_text(last_run: str | None, pending_count: int, rule_count: int, authorities: set[str]) -> str:
    auth = ", ".join(PREDICTION_TEXT[a] for a in sorted(authorities)) or "yok"
    return (f"<b>Durum</b>\nSon tur: {escape(last_run or 'henüz yok')}\n"
            f"Bekleyen mail: {pending_count}\nKesin kural: {rule_count}\nTarz yetkisi: {auth}")
