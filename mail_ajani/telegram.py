import requests


class TelegramError(Exception):
    pass


class TelegramClient:
    def __init__(self, token: str, chat_id: int | None, session=None):
        self._base = f"https://api.telegram.org/bot{token}/"
        self.chat_id = chat_id
        self._s = session or requests.Session()

    def _call(self, method: str, **params):
        try:
            data = self._s.post(self._base + method, json=params, timeout=70).json()
        except (requests.RequestException, ValueError) as e:
            # never include the exception text: it may contain the URL with the token
            raise TelegramError(f"{method}: bağlantı hatası ({e.__class__.__name__})") from None
        if not data.get("ok"):
            raise TelegramError(f"{method}: {data.get('description')}")
        return data["result"]

    def send(self, text: str, keyboard: dict | None = None, silent: bool = False) -> int:
        params = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML",
                  "disable_notification": silent, "link_preview_options": {"is_disabled": True}}
        if keyboard:
            params["reply_markup"] = keyboard
        return self._call("sendMessage", **params)["message_id"]

    def edit(self, message_id: int, text: str, keyboard: dict | None = None) -> None:
        params = {"chat_id": self.chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML",
                  "link_preview_options": {"is_disabled": True},
                  "reply_markup": keyboard or {"inline_keyboard": []}}
        try:
            self._call("editMessageText", **params)
        except TelegramError as e:
            if "message is not modified" not in str(e):
                raise

    def answer(self, callback_id: str, text: str = "") -> None:
        self._call("answerCallbackQuery", callback_query_id=callback_id, text=text)

    def updates(self, offset: int, timeout: int = 50) -> list[dict]:
        return self._call("getUpdates", offset=offset, timeout=timeout,
                          allowed_updates=["message", "callback_query"])
