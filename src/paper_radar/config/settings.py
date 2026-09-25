import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("data")
    http_timeout: float = 30
    max_retries: int = 3
    request_interval: float = 1
    user_agent: str = "paper-radar/0.1"
    timezone: str = "Asia/Shanghai"
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        if self.http_timeout <= 0 or self.max_retries < 0 or self.request_interval < 0:
            raise ValueError("HTTP_TIMEOUT must be positive; retries and interval nonnegative")
        ZoneInfo(self.timezone)
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("Invalid LOG_LEVEL")

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(Path.cwd() / ".env")
        return cls(
            data_dir=Path(os.getenv("DATA_DIR", "data")),
            http_timeout=float(os.getenv("HTTP_TIMEOUT", "30")),
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
            request_interval=float(os.getenv("REQUEST_INTERVAL", "1")),
            user_agent=os.getenv("USER_AGENT", "paper-radar/0.1"),
            timezone=os.getenv("TIMEZONE", "Asia/Shanghai"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
