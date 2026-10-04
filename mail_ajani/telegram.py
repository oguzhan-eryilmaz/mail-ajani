import math
from time import sleep

import requests

MAX_RETRIES = 3
MAX_RETRY_WAIT_S = 60


class TelegramError(Exception):
    def __init__(self, message, *, retry_after=None, not_modified=False, status_code=None):
        super().__init__(message)
        self.retry_after = retry_after
        self.not_modified = not_modified
        self.status_code = status_code

    @property
    def permanent(self):
        return (type(self.status_code) is int and 400 <= self.status_code < 500
                and self.status_code != 429)


class TelegramClient:
    def __init__(self, token: str, chat_id: int | None, session=None):
        self._base = f"https://api.telegram.org/bot{token}/"
        self.chat_id = chat_id
        self._s = session or requests.Session()

    def _call(self, method: str, **params):
        waited = 0
        for attempt in range(MAX_RETRIES + 1):
            delay = None
            status = None
            try:
                response = self._s.post(self._base + method, json=params, timeout=70)
                status = getattr(response, "status_code", 200)
                if status >= 500:
                    error = TelegramError(f"{method}: Telegram geçici sunucu hatası", status_code=status)
                    delay = 2 ** attempt
                else:
                    data = response.json()
                    if not isinstance(data, dict):
                        raise ValueError("invalid response")
                    if data.get("ok"):
                        return data["result"]
                    code = data.get("error_code", status)
                    description = str(data.get("description", ""))
                    # Never echo server descriptions: they may contain a URL or token.
                    if "message is not modified" in description:
                        error = TelegramError(f"{method}: mesaj zaten aynı", not_modified=True)
                    elif "chat not found" in description:
                        error = TelegramError(f"{method}: sohbet bulunamadı")
                    else:
                        error = TelegramError(f"{method}: Telegram isteği başarısız")
                    if code == 429:
                        parameters = data.get("parameters")
                        delay = parameters.get("retry_after", 1) if isinstance(parameters, dict) else 1
                        if (type(delay) not in (int, float) or not math.isfinite(delay) or delay < 0):
                            delay = 1
                        error = TelegramError(f"{method}: Telegram hız sınırı", retry_after=delay)
                    elif isinstance(code, int) and code >= 500:
                        delay = 2 ** attempt
                    error.status_code = code
            except (requests.ConnectionError, requests.Timeout) as e:
                error = TelegramError(f"{method}: bağlantı hatası ({e.__class__.__name__})")
                delay = 2 ** attempt
            except (requests.RequestException, ValueError, KeyError) as e:
                error = TelegramError(f"{method}: bağlantı hatası ({e.__class__.__name__})", status_code=status)
            if delay is None or attempt == MAX_RETRIES or waited + delay > MAX_RETRY_WAIT_S:
                raise error from None
            sleep(delay)
            waited += delay

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
            if not e.not_modified:
                raise

    def answer(self, callback_id: str, text: str = "") -> None:
        self._call("answerCallbackQuery", callback_query_id=callback_id, text=text)

    def updates(self, offset: int, timeout: int = 50) -> list[dict]:
        return self._call("getUpdates", offset=offset, timeout=timeout,
                          allowed_updates=["message", "callback_query"])
