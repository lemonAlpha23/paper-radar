import base64
import hashlib
import hmac
import os
import time
from typing import Any

from paper_radar.core.exceptions import RadarError
from paper_radar.infrastructure.http_client import HttpClient
from paper_radar.notifications.base import Notifier, webhook_url


class FeishuNotifier(Notifier):
    name = "feishu"

    def __init__(self, http: HttpClient):
        super().__init__(http)
        self.url = webhook_url("FEISHU_WEBHOOK_URL")
        self.secret = os.getenv("FEISHU_SECRET", "")

    def send(self, message: str) -> None:
        payload: dict[str, Any] = {"msg_type": "text", "content": {"text": message}}
        if self.secret:
            timestamp = str(int(time.time()))
            signature = hmac.new(f"{timestamp}\n{self.secret}".encode(), b"", hashlib.sha256)
            payload.update(timestamp=timestamp, sign=base64.b64encode(signature.digest()).decode())
        response = self.http.post_json(self.url, payload)
        if type(response.get("code")) is not int or response["code"] != 0:
            raise RadarError("Feishu rejected notification")
