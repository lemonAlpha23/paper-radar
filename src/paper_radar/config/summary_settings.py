import math
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class SummarySettings:
    provider: str = "deepseek"
    model: str = ""
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    timeout: float = 120
    max_tokens: int = 2048

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("Missing summary setting: API_KEY")
        if not math.isfinite(self.timeout) or self.timeout <= 0 or self.max_tokens < 1:
            raise ValueError("Summary timeout and max_tokens must be positive")
        if not self.base_url:
            return
        url = urlsplit(self.base_url)
        local = url.hostname in {"localhost", "127.0.0.1", "::1"}
        if (
            not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or (url.scheme != "https" and not (url.scheme == "http" and local))
        ):
            raise ValueError("SUMMARY_BASE_URL must be HTTPS (HTTP is allowed for localhost)")

    @classmethod
    def from_env(cls, provider: str | None = None, model: str | None = None) -> "SummarySettings":
        provider_name = provider or os.getenv("SUMMARY_PROVIDER") or "deepseek"
        return cls(
            provider=provider_name,
            model=model or os.getenv("SUMMARY_MODEL") or "",
            base_url=os.getenv("SUMMARY_BASE_URL", "").rstrip("/"),
            api_key=os.getenv("API_KEY", ""),
            timeout=float(os.getenv("SUMMARY_TIMEOUT", "120")),
            max_tokens=int(os.getenv("SUMMARY_MAX_TOKENS", "2048")),
        )
