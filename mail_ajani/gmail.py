import json
from datetime import datetime
from email.utils import parseaddr
from html import unescape

from . import config, sirlar

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
LABEL_ARSIV = "Ajan/Arşiv"
LABEL_ONEMLI = "Ajan/Önemli"
CATEGORIES = {"CATEGORY_PROMOTIONS": "tanitim", "CATEGORY_SOCIAL": "sosyal",
              "CATEGORY_UPDATES": "guncelleme", "CATEGORY_FORUMS": "forum"}


class GmailAuthError(Exception):
    pass


def is_auth_error(error: Exception) -> bool:
    from google.auth.exceptions import RefreshError
    from googleapiclient.errors import HttpError

    return (isinstance(error, (GmailAuthError, RefreshError)) or
            isinstance(error, HttpError) and error.resp.status == 401)


class GmailClient:
    def __init__(self, account: str, service):
        self.account = account
        self.svc = service
        self._labels: dict[str, str] = {}

    def _messages(self):
        return self.svc.users().messages()

    def _label_id(self, name: str) -> str:
        if name not in self._labels:
            existing = self.svc.users().labels().list(userId="me").execute(num_retries=3).get("labels", [])
            for label in existing:
                self._labels[label["name"]] = label["id"]
        if name not in self._labels:
            created = self.svc.users().labels().create(userId="me", body={
                "name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}).execute(num_retries=3)
            self._labels[name] = created["id"]
        return self._labels[name]

    def fetch_new(self, since: datetime) -> list[dict]:
        query = f"in:inbox after:{int(since.timestamp())}"
        ids, token = [], None
        while True:
            resp = self._messages().list(userId="me", q=query, pageToken=token, maxResults=100).execute(num_retries=3)
            ids += [m["id"] for m in resp.get("messages", [])]
            token = resp.get("nextPageToken")
            if not token:
                break
        out = []
        for mid in ids:
            msg = self._messages().get(userId="me", id=mid, format="metadata",
                                       metadataHeaders=["From", "Subject"]).execute(num_retries=3)
            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            name, addr = parseaddr(headers.get("from", ""))
            labels = msg.get("labelIds", [])
            category = next((v for k, v in CATEGORIES.items() if k in labels), "birincil")
            received = datetime.fromtimestamp(int(msg["internalDate"]) / 1000, config.TZ)
            out.append({"account": self.account, "gmail_id": mid, "sender": addr.lower(), "sender_name": name,
                        "subject": headers.get("subject", ""), "snippet": unescape(msg.get("snippet", "")),
                        "category": category, "received_at": received.isoformat()})
        return out

    def count_since(self, since: datetime, limit: int) -> int:
        # Cheap pre-check for backlog scans: ids only, stops just past the limit.
        query = f"in:inbox after:{int(since.timestamp())}"
        count, token = 0, None
        while count <= limit:
            resp = self._messages().list(userId="me", q=query, pageToken=token, maxResults=100).execute(num_retries=3)
            count += len(resp.get("messages", []))
            token = resp.get("nextPageToken")
            if not token:
                break
        return count

    def apply(self, gmail_id: str, action: str) -> None:
        m = self._messages()
        if action == "cop":
            m.trash(userId="me", id=gmail_id).execute(num_retries=3)
        elif action == "arsiv":
            m.modify(userId="me", id=gmail_id, body={
                "removeLabelIds": ["INBOX"], "addLabelIds": [self._label_id(LABEL_ARSIV)]}).execute(num_retries=3)
        elif action == "onemli":
            m.modify(userId="me", id=gmail_id, body={
                "addLabelIds": ["STARRED", self._label_id(LABEL_ONEMLI)]}).execute(num_retries=3)

    def revert(self, gmail_id: str, action: str) -> None:
        m = self._messages()
        if action == "cop":
            m.untrash(userId="me", id=gmail_id).execute(num_retries=3)
            # Live check, 5 Oct 2026: untrash alone leaves the mail archived
            # (no INBOX label). Every mail the agent handles came from the inbox.
            m.modify(userId="me", id=gmail_id, body={"addLabelIds": ["INBOX"]}).execute(num_retries=3)
        elif action == "arsiv":
            m.modify(userId="me", id=gmail_id, body={
                "addLabelIds": ["INBOX"], "removeLabelIds": [self._label_id(LABEL_ARSIV)]}).execute(num_retries=3)
        elif action == "onemli":
            m.modify(userId="me", id=gmail_id, body={
                "removeLabelIds": ["STARRED", self._label_id(LABEL_ONEMLI)]}).execute(num_retries=3)


def load_credentials(account: str):
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    raw = sirlar.get_secret(f"gmail:{account}")
    if not raw:
        raise GmailAuthError(f"{account} için izin yok")
    creds = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
    if not creds.valid:
        try:
            creds.refresh(Request())
        except RefreshError as e:
            raise GmailAuthError(f"{account} izni geçersiz, yeniden izin gerekli") from e
        sirlar.set_secret(f"gmail:{account}", creds.to_json())
    return creds


def build_client(account: str) -> GmailClient:
    from googleapiclient.discovery import build

    service = build("gmail", "v1", credentials=load_credentials(account), cache_discovery=False)
    return GmailClient(account, service)


def authorize(account: str) -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(config.client_secret_path(account)), SCOPES)
    creds = flow.run_local_server(port=0, login_hint=account, prompt="consent", access_type="offline")
    sirlar.set_secret(f"gmail:{account}", creds.to_json())
