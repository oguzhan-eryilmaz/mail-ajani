import json
import logging
from datetime import datetime, timedelta
from time import monotonic, sleep

from . import db, learning, render, schedule
from .telegram import TelegramError

log = logging.getLogger(__name__)
SEND_INTERVAL_S = 1.0


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def skip_result(conn, now: datetime, force: bool = False) -> dict | None:
    if (not force and db.get_meta(conn, "tur_incomplete") != "1"
            and not schedule.should_run(now, _parse(db.get_meta(conn, "last_run")))
            and not db.pending_mails(conn)
            and not json.loads(db.get_meta(conn, "pending_warnings") or "[]")):
        return {"skipped": True}
    retry_at = _parse(db.get_meta(conn, "telegram_retry_at"))
    if retry_at and now < retry_at:
        return {"incomplete": True}
    return None


def run_tur(conn, clients: dict, tg, classify_fn, now: datetime, force: bool = False,
            warnings: list[str] | None = None) -> dict:
    skipped = skip_result(conn, now, force)
    if skipped is not None:
        return skipped
    if db.get_meta(conn, "tur_incomplete") != "1":
        db.set_meta(conn, "tur_summary_sent", "0")
        db.set_meta(conn, "tur_warned", "[]")
    db.set_meta(conn, "tur_incomplete", "1")
    started = monotonic()
    complete = True  # Only unfinished Telegram delivery keeps this slot open.
    warnings = json.loads(db.get_meta(conn, "pending_warnings") or "[]") + list(warnings or [])
    warned = json.loads(db.get_meta(conn, "tur_warned") or "[]")
    rejections = json.loads(db.get_meta(conn, "card_rejections") or "{}")
    now_iso = now.isoformat()

    for account, client in clients.items():
        since = schedule.fetch_since(now, _parse(db.get_meta(conn, f"last_fetch:{account}")))
        try:
            for mail in client.fetch_new(since):
                db.insert_mail(conn, mail)
            db.set_meta(conn, f"last_fetch:{account}", now_iso)
        except Exception as e:
            log.warning("Gmail çekimi başarısız: %s (%s)", account, e.__class__.__name__)
            warnings.append(f"{account}: mailler alınamadı ({e.__class__.__name__})")

    pending = db.pending_mails(conn)
    active = {m["id"]: db.active_decision(conn, m["id"]) for m in pending}
    to_classify = [m for m in pending if active[m["id"]] is None
                   and str(m["id"]) not in rejections
                   and learning.rule_for(conn, m["sender"]) is None]
    predictions = {}
    if to_classify:
        try:
            predictions, errors = classify_fn(to_classify, learning.recent_examples(conn))
        except Exception as e:
            predictions, errors = {}, [f"sınıflandırıcı çalışmadı ({e.__class__.__name__})"]
        warnings += [f"Sınıflandırma yapılamadı, bazı mailler tahminsiz geldi: {e}" for e in errors]
        # A previous failed send may have left a prediction; fallback must clear it.
        for mail in to_classify:
            db.set_prediction(conn, mail["id"], *predictions.get(mail["id"], (None, None)))

    authorities = learning.style_authorities(conn)
    autos, card_ids = [], []
    for mail in pending:
        if str(mail["id"]) in rejections:
            card_ids.append(mail["id"])
            continue
        decision = active[mail["id"]]
        if decision is None:
            automatic = learning.auto_action(conn, mail["sender"],
                                             predictions.get(mail["id"], (None,))[0], authorities)
            client = clients.get(mail["account"])
            if automatic and client:
                action, source = automatic
                try:
                    client.apply(mail["gmail_id"], action)
                except Exception as e:
                    log.warning("Otomatik işlem başarısız (%s)", e.__class__.__name__)
                    warnings.append(f"{mail['account']}: otomatik işlem uygulanamadı ({e.__class__.__name__})")
                else:
                    decision_id = db.add_decision(conn, mail["id"], action, source, now_iso)
                    decision = db.get_decision(conn, decision_id)
                    active[mail["id"]] = decision
        if decision:
            if decision["notified_at"] is None:
                autos.append({"decision_id": decision["id"], "mail": db.get_mail(conn, mail["id"]),
                              "action": decision["action"], "source": decision["source"]})
            if decision["action"] == "onemli":
                card_ids.append(mail["id"])
        else:
            card_ids.append(mail["id"])

    warnings = [w for w in dict.fromkeys(warnings) if w not in warned]
    db.set_meta(conn, "pending_warnings", json.dumps(warnings, ensure_ascii=False))
    silent = schedule.is_quiet(now)
    sent_any = False
    # Permanent fallback rejections are durable and identified in the warning.
    # Their mails become delivered only after that warning reaches the owner.
    rejected_ids = []

    def rejection_warning(mid):
        return (f"Mail #{mid}: kısa kart da reddedildi. "
                "Mail yerelde kayıtlı; Gmail'den kontrol edin.")

    def send(text, keyboard=None):
        nonlocal sent_any
        if sent_any:
            sleep(SEND_INTERVAL_S)
        message_id = tg.send(text, keyboard, silent=silent)
        sent_any = True
        return message_id

    def defer(error):
        nonlocal complete
        log.warning("Telegram gönderimi tamamlanamadı (%s)", error.__class__.__name__)
        warnings.append("Telegram gönderimi tamamlanamadı; kalan bildirimler yeniden denenecek.")
        if error.retry_after:
            retry_delay = monotonic() - started + error.retry_after
            deadline = now + timedelta(seconds=retry_delay)
            previous = _parse(db.get_meta(conn, "telegram_retry_at"))
            db.set_meta(conn, "telegram_retry_at", max(deadline, previous or deadline).isoformat())
        complete = False

    try:
        if pending:
            cards = [db.get_mail(conn, i) for i in card_ids]
            cards.sort(key=lambda m: m["prediction"] != "onemli"
                       and not (active[m["id"]] and active[m["id"]]["action"] == "onemli"))
            important = sum(m["prediction"] == "onemli" or
                            (active[m["id"]] is not None and active[m["id"]]["action"] == "onemli")
                            for m in cards)
            slot_label = schedule.latest_slot(now).strftime("%H:%M")
            batches = (render.summary_batches(autos) if autos
                       or db.get_meta(conn, "tur_summary_sent") != "1" else [])
            for batch in batches:
                send(render.summary_text(slot_label, len(pending), important, len(cards), batch),
                     render.summary_keyboard(batch))
                db.set_meta(conn, "tur_summary_sent", "1")
                for auto in batch:
                    db.mark_notified(conn, auto["decision_id"], now_iso)
                    if auto["action"] != "onemli":
                        db.mark_sent(conn, auto["mail"]["id"], None, now_iso)
            for mail in cards:
                if str(mail["id"]) in rejections:
                    rejected_ids.append(mail["id"])
                    warnings.append(rejection_warning(mail["id"]))
                    continue
                keyboard = render.card_keyboard(mail["id"])
                try:
                    message_id = send(render.card_text(mail), keyboard)
                except TelegramError as e:
                    if not e.permanent:
                        raise
                    warnings.append(f"Mail #{mail['id']}: Telegram ayrıntılı kartı reddetti; kısa kart denendi.")
                    try:
                        message_id = send(render.fallback_card_text(mail), keyboard)
                    except TelegramError as fallback_error:
                        if not fallback_error.permanent:
                            defer(fallback_error)
                            continue
                        rejections[str(mail["id"])] = fallback_error.status_code
                        db.set_meta(conn, "card_rejections", json.dumps(rejections))
                        rejected_ids.append(mail["id"])
                        warnings.append(rejection_warning(mail["id"]))
                        continue
                db.mark_sent(conn, mail["id"], message_id, now_iso)
        warnings = [w for w in dict.fromkeys(warnings) if w not in warned]
        if warnings:
            db.set_meta(conn, "pending_warnings", json.dumps(warnings, ensure_ascii=False))
            send(render.warnings_text(warnings))
            warned += warnings
            db.set_meta(conn, "tur_warned", json.dumps(warned, ensure_ascii=False))
        for mid in rejected_ids:
            if rejection_warning(mid) in warned:
                db.mark_sent(conn, mid, None, now_iso)
    except TelegramError as e:
        defer(e)
        db.set_meta(conn, "pending_warnings", json.dumps(list(dict.fromkeys(warnings)), ensure_ascii=False))
    else:
        db.set_meta(conn, "pending_warnings", "[]")
        if complete:
            db.set_meta(conn, "telegram_retry_at", "")

    if complete:
        db.set_meta(conn, "last_run", now_iso)
        db.set_meta(conn, "tur_incomplete", "0")
    stats = {"new": len(pending), "auto": len(autos), "cards": len(card_ids), "warnings": len(warnings)}
    if not complete:
        stats["incomplete"] = True
    return stats
