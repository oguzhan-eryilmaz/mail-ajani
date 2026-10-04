from . import db

AUTO_ACTIONS = ("cop", "arsiv", "onemli")
RULE_STREAK = 10
STYLE_WINDOW = 30
STYLE_MIN_CORRECT = 29  # 30 * 0.95 rounded up


def sender_starred(conn, sender: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM decisions d JOIN mails m ON m.id=d.mail_id "
        "WHERE m.sender=? AND d.source='user' AND d.undone=0 AND d.action='onemli' LIMIT 1", (sender,)).fetchone()
    return row is not None


def _blocked(conn, sender: str, action: str) -> bool:
    return action in ("cop", "arsiv") and sender_starred(conn, sender)


def update_rule_for_sender(conn, sender: str, now_iso: str) -> None:
    if not sender.strip():
        conn.execute("DELETE FROM rules WHERE sender=?", (sender,))
        conn.commit()
        return
    since = db.get_meta(conn, f"rule_reset:{sender}") or ""
    acts = [r["action"] for r in conn.execute(
        "SELECT d.action FROM decisions d JOIN mails m ON m.id=d.mail_id "
        "WHERE m.sender=? AND d.source='user' AND d.undone=0 AND d.created_at>? "
        "ORDER BY d.id DESC LIMIT ?", (sender, since, RULE_STREAK))]
    if (len(acts) == RULE_STREAK and len(set(acts)) == 1 and acts[0] in AUTO_ACTIONS
            and not _blocked(conn, sender, acts[0])):
        conn.execute(
            "INSERT INTO rules(sender, action, created_at) VALUES(?,?,?) "
            "ON CONFLICT(sender) DO UPDATE SET action=excluded.action", (sender, acts[0], now_iso))
    else:
        conn.execute("DELETE FROM rules WHERE sender=?", (sender,))
    conn.commit()


def record_user_decision(conn, mail_id: int, action: str, now_iso: str) -> int:
    decision_id = db.add_decision(conn, mail_id, action, "user", now_iso)
    update_rule_for_sender(conn, db.get_mail(conn, mail_id)["sender"], now_iso)
    return decision_id


def rule_for(conn, sender: str) -> str | None:
    if not sender.strip():
        return None
    row = conn.execute("SELECT action FROM rules WHERE sender=?", (sender,)).fetchone()
    if row is None or _blocked(conn, sender, row["action"]):
        return None
    return row["action"]


def style_authorities(conn) -> set[str]:
    out = set()
    for action in AUTO_ACTIONS:
        since = db.get_meta(conn, f"reset:{action}") or ""
        rows = conn.execute(
            "SELECT d.action FROM mails m JOIN decisions d ON d.mail_id=m.id "
            "WHERE m.prediction=? AND d.source='user' AND d.undone=0 AND d.created_at>? "
            "ORDER BY d.id DESC LIMIT ?", (action, since, STYLE_WINDOW)).fetchall()
        if len(rows) == STYLE_WINDOW and sum(r["action"] == action for r in rows) >= STYLE_MIN_CORRECT:
            out.add(action)
    return out


def auto_action(conn, sender: str, prediction: str | None, authorities: set[str]) -> tuple[str, str] | None:
    if not sender.strip():
        return None
    action = rule_for(conn, sender)
    if action:
        return action, "rule"
    if prediction in authorities and not _blocked(conn, sender, prediction):
        return prediction, "style"
    return None


def reset_authority(conn, action: str, now_iso: str) -> None:
    db.set_meta(conn, f"reset:{action}", now_iso)


def _reset_rule(conn, sender: str, now_iso: str) -> None:
    db.set_meta(conn, f"rule_reset:{sender}", now_iso)
    conn.execute("DELETE FROM rules WHERE sender=?", (sender,))
    conn.commit()


def undo(conn, decision_id: int, now_iso: str):
    decision = db.get_decision(conn, decision_id)
    db.mark_undone(conn, decision_id)
    sender = db.get_mail(conn, decision["mail_id"])["sender"]
    if decision["source"] == "rule":
        _reset_rule(conn, sender, now_iso)
    elif decision["source"] == "style":
        reset_authority(conn, decision["action"], now_iso)
    else:
        update_rule_for_sender(conn, sender, now_iso)
    return decision


def list_rules(conn) -> list:
    return conn.execute("SELECT id, sender, action FROM rules ORDER BY sender").fetchall()


def delete_rule(conn, rule_id: int, now_iso: str) -> None:
    row = conn.execute("SELECT sender FROM rules WHERE id=?", (rule_id,)).fetchone()
    if row:
        _reset_rule(conn, row["sender"], now_iso)


def recent_examples(conn, limit: int = 40) -> list[dict]:
    rows = conn.execute(
        "SELECT m.sender, m.subject, d.action FROM decisions d JOIN mails m ON m.id=d.mail_id "
        "WHERE d.source='user' AND d.undone=0 ORDER BY d.id DESC LIMIT ?", (limit,)).fetchall()
    return [{"sender": r["sender"], "subject": r["subject"], "action": r["action"]} for r in rows]
