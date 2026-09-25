import os
import time
from abc import ABC, abstractmethod
from typing import ClassVar
from urllib.parse import urlsplit

from paper_radar.core.exceptions import RadarError
from paper_radar.infrastructure.http_client import HttpClient


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RadarError(f"Missing notification setting: {name}")
    return value


def webhook_url(name: str) -> str:
    value = required_env(name)
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise RadarError(f"{name} must be an HTTPS webhook URL")
    return value


class Notifier(ABC):
    name: ClassVar[str]

    def __init__(self, http: HttpClient):
        self.http = http

    @abstractmethod
    def send(self, message: str) -> None: ...

    def send_batch(self, messages: list[str]) -> None:
        for index, message in enumerate(messages):
            if index:
                time.sleep(3)  # Group robots allow 20 messages per minute.
            self.send(message)
