import logging
import time
from datetime import datetime

from . import config, db, gmail, learning, render
from .config import TZ

log = logging.getLogger(__name__)


def _rules_view(conn):
    rules, auth = learning.list_rules(conn), learning.style_authorities(conn)
    warning = ""
    try:
        categories = config.get_categories()
    except ValueError as e:
        categories = []
        warning = f"\nKategori ayarı geçersiz: {e}."
    return render.rules_text(rules, auth, categories) + warning, render.rules_keyboard(rules, auth)


def _on_action(conn, cq, action, mail_id, clients, tg, now_iso):
    mail = db.get_mail(conn, mail_id)
    client = clients.get(mail["account"]) if mail else None
    if client is None:
        tg.answer(cq["id"], "Bu hesap şu an bağlı değil")
        return
    active = db.active_decision(conn, mail_id)
    if active and active["action"] == action:
        tg.answer(cq["id"], render.ACTION_DONE[action])
        return
    try:
        if active:
            client.revert(mail["gmail_id"], active["action"])
            learning.undo(conn, active["id"], now_iso)
        client.apply(mail["gmail_id"], action)
    except Exception as e:
        if gmail.is_auth_error(e):
            clients.pop(mail["account"], None)
        log.warning("Gmail işlemi başarısız (%s)", e.__class__.__name__)
        tg.answer(cq["id"], "Gmail'e ulaşılamadı, tekrar dene")
        return
    decision_id = learning.record_user_decision(conn, mail_id, action, now_iso)
    tg.edit(cq["message"]["message_id"], render.done_text(mail, action), render.undo_keyboard(decision_id))
    tg.answer(cq["id"], render.ACTION_DONE[action])


def _on_undo(conn, cq, decision_id, clients, tg, now_iso):
    decision = db.get_decision(conn, decision_id)
    if decision is None or decision["undone"]:
        tg.answer(cq["id"], "Zaten geri alınmış")
        return
    mail = db.get_mail(conn, decision["mail_id"])
    client = clients.get(mail["account"])
    if client is None:
        tg.answer(cq["id"], "Bu hesap şu an bağlı değil")
        return
    try:
        client.revert(mail["gmail_id"], decision["action"])
    except Exception as e:
        if gmail.is_auth_error(e):
            clients.pop(mail["account"], None)
        log.warning("Gmail geri alma başarısız (%s)", e.__class__.__name__)
        tg.answer(cq["id"], "Gmail'e ulaşılamadı, tekrar dene")
        return
    learning.undo(conn, decision_id, now_iso)
    mail = db.get_mail(conn, mail["id"])
    if mail["tg_message_id"] is not None:
        tg.edit(mail["tg_message_id"], render.card_text(mail), render.card_keyboard(mail["id"]))
    else:
        message_id = tg.send(render.card_text(mail), render.card_keyboard(mail["id"]))
        db.mark_sent(conn, mail["id"], message_id, now_iso)
    tg.answer(cq["id"], "Geri alındı")


def handle_update(conn, update: dict, clients: dict, tg, owner_chat_id: int, now: datetime) -> None:
    now_iso = now.isoformat()
    if "callback_query" in update:
        cq = update["callback_query"]
        if cq.get("message", {}).get("chat", {}).get("id") != owner_chat_id:
            return
        kind, *rest = cq.get("data", "").split(":")
        if kind == "a":
            _on_action(conn, cq, rest[0], int(rest[1]), clients, tg, now_iso)
        elif kind == "u":
            _on_undo(conn, cq, int(rest[0]), clients, tg, now_iso)
        elif kind in ("r", "y"):
            if kind == "r":
                learning.delete_rule(conn, int(rest[0]), now_iso)
            else:
                learning.reset_authority(conn, rest[0], now_iso)
            text, keyboard = _rules_view(conn)
            tg.edit(cq["message"]["message_id"], text, keyboard)
            tg.answer(cq["id"], "Silindi")
    elif "message" in update:
        message = update["message"]
        if message.get("chat", {}).get("id") != owner_chat_id:
            return
        command = (message.get("text") or "").strip().split("@")[0]
        if command == "/kurallar":
            tg.send(*_rules_view(conn))
        elif command == "/durum":
            pending = len(db.pending_mails(conn))
            tg.send(render.status_text(db.get_meta(conn, "last_run"), pending,
                                       len(learning.list_rules(conn)), learning.style_authorities(conn)))


def run_listener(conn, get_clients, tg, owner_chat_id: int, stop=lambda: False) -> None:
    offset = int(db.get_meta(conn, "tg_offset") or 0)
    while not stop():
        try:
            updates = tg.updates(offset)
        except Exception:
            log.exception("getUpdates failed")
            time.sleep(10)
            continue
        for update in updates:
            offset = update["update_id"] + 1
            try:
                handle_update(conn, update, get_clients(), tg, owner_chat_id, datetime.now(TZ))
            except Exception:
                log.exception("update handling failed")
            db.set_meta(conn, "tg_offset", str(offset))
