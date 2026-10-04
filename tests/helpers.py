import itertools
from datetime import datetime, timedelta

from mail_ajani import db
from mail_ajani.config import TZ

BASE = datetime(2026, 9, 19, 12, 0, tzinfo=TZ)
_counter = itertools.count(1)


def ts(i: int) -> str:
    return (BASE + timedelta(minutes=i)).isoformat()


def make_mail(conn, sender="haber@site.com", account="a@gmail.com", subject="Konu",
              prediction=None, category="birincil") -> int:
    n = next(_counter)
    mail_id = db.insert_mail(conn, {
        "account": account, "gmail_id": f"g{n}", "sender": sender, "sender_name": "Ad",
        "subject": subject, "snippet": "ön izleme", "category": category, "received_at": ts(n),
    })
    if prediction:
        db.set_prediction(conn, mail_id, prediction, "kısa özet")
    return mail_id


class FakeGmail:
    def __init__(self, account, mails=None, fail=None, bodies=None, body_fail=None):
        self.account = account
        self.mails = mails or []
        self.fail = fail
        self.bodies = bodies or {}
        self.body_fail = body_fail
        self.body_fetches = []
        self.applied, self.reverted, self.since = [], [], None

    def fetch_new(self, since):
        self.since = since
        if self.fail:
            raise self.fail
        return list(self.mails)

    def fetch_body(self, gmail_id):
        self.body_fetches.append(gmail_id)
        if self.body_fail:
            raise self.body_fail
        return self.bodies.get(gmail_id, "")

    def apply(self, gmail_id, action):
        self.applied.append((gmail_id, action))

    def revert(self, gmail_id, action):
        self.reverted.append((gmail_id, action))


class FakeTg:
    def __init__(self):
        self.sent, self.edited, self.answered = [], [], []
        self._next = 100

    def send(self, text, keyboard=None, silent=False):
        self._next += 1
        self.sent.append({"id": self._next, "text": text, "keyboard": keyboard, "silent": silent})
        return self._next

    def edit(self, message_id, text, keyboard=None):
        self.edited.append({"id": message_id, "text": text, "keyboard": keyboard})

    def answer(self, callback_id, text=""):
        self.answered.append(text)


def raw_mail(account, gid, sender="s@x.com", subject="Konu"):
    return {"account": account, "gmail_id": gid, "sender": sender, "sender_name": "S", "subject": subject,
            "snippet": "p", "category": "birincil", "received_at": ts(int(gid.strip("g") or 0))}
