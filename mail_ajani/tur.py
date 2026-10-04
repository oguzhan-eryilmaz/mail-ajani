import logging
from datetime import datetime

from . import db, learning, render, schedule

log = logging.getLogger(__name__)


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def run_tur(conn, clients: dict, tg, classify_fn, now: datetime, force: bool = False,
            warnings: list[str] | None = None) -> dict:
    warnings = list(warnings or [])
    if not force and not schedule.should_run(now, _parse(db.get_meta(conn, "last_run"))):
        return {"skipped": True}
    now_iso = now.isoformat()

    for account, client in clients.items():
        since = schedule.fetch_since(now, _parse(db.get_meta(conn, f"last_fetch:{account}")))
        try:
            for mail in client.fetch_new(since):
                db.insert_mail(conn, mail)
            db.set_meta(conn, f"last_fetch:{account}", now_iso)
        except Exception as e:
            log.exception("fetch failed for %s", account)
            warnings.append(f"{account}: {e.__class__.__name__}: {str(e)[:150]}")

    pending = db.pending_mails(conn)
    to_classify = [m for m in pending if learning.rule_for(conn, m["sender"]) is None]
    predictions = {}
    if to_classify:
        predictions, errors = classify_fn(to_classify, learning.recent_examples(conn))
        warnings += [f"Sınıflandırma yapılamadı, mailler tahminsiz geldi: {e}" for e in errors]

    authorities = learning.style_authorities(conn)
    autos, card_ids = [], []
    for mail in pending:
        if mail["id"] in predictions:
            db.set_prediction(conn, mail["id"], *predictions[mail["id"]])
        decision = learning.auto_action(conn, mail["sender"], predictions.get(mail["id"], (None,))[0], authorities)
        client = clients.get(mail["account"])
        if decision and client:
            action, source = decision
            try:
                client.apply(mail["gmail_id"], action)
            except Exception as e:
                log.exception("auto apply failed")
                warnings.append(f"{mail['account']}: otomatik işlem uygulanamadı ({e.__class__.__name__})")
                card_ids.append(mail["id"])
                continue
            decision_id = db.add_decision(conn, mail["id"], action, source, now_iso)
            autos.append({"decision_id": decision_id, "mail": db.get_mail(conn, mail["id"]),
                          "action": action, "source": source})
            if action == "onemli":
                card_ids.append(mail["id"])
            else:
                db.mark_sent(conn, mail["id"], None, now_iso)
        else:
            card_ids.append(mail["id"])

    silent = schedule.is_quiet(now)
    if pending:
        cards = [db.get_mail(conn, i) for i in card_ids]
        cards.sort(key=lambda m: m["prediction"] != "onemli")
        important = sum(1 for m in cards if m["prediction"] == "onemli")
        slot_label = schedule.latest_slot(now).strftime("%H:%M")
        tg.send(render.summary_text(slot_label, len(pending), important, len(cards), autos),
                render.summary_keyboard(autos), silent=silent)
        for mail in cards:
            message_id = tg.send(render.card_text(mail), render.card_keyboard(mail["id"]), silent=silent)
            db.mark_sent(conn, mail["id"], message_id, now_iso)
    if warnings:
        tg.send(render.warnings_text(warnings), silent=silent)

    db.set_meta(conn, "last_run", now_iso)
    return {"new": len(pending), "auto": len(autos), "cards": len(card_ids), "warnings": len(warnings)}
