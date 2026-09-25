import re

from paper_radar.core.exceptions import RadarError
from paper_radar.infrastructure.http_client import HttpClient
from paper_radar.notifications.base import Notifier, required_env


class TelegramNotifier(Notifier):
    name = "telegram"

    def __init__(self, http: HttpClient):
        super().__init__(http)
        token = required_env("TELEGRAM_BOT_TOKEN")
        if not re.fullmatch(r"\d+:[A-Za-z0-9_-]+", token):
            raise RadarError("Invalid TELEGRAM_BOT_TOKEN format")
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = required_env("TELEGRAM_CHAT_ID")

    def send(self, message: str) -> None:
        response = self.http.post_json(self.url, {"chat_id": self.chat_id, "text": message})
        if response.get("ok") is not True:
            raise RadarError("Telegram rejected notification")
