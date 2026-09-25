import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class Period(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


def default_target(period: Period, today: date) -> str:
    match period:
        case Period.DAILY:
            return today.isoformat()
        case Period.WEEKLY:
            year, week, _ = today.isocalendar()
            return f"{year}-W{week:02d}"
        case Period.MONTHLY:
            return today.strftime("%Y-%m")


@dataclass(frozen=True)
class CrawlTask:
    source: str
    period: Period
    target: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.source):
            raise ValueError("Invalid source name")
        object.__setattr__(self, "period", Period(self.period))
        formats = {
            Period.DAILY: r"\d{4}-\d{2}-\d{2}",
            Period.WEEKLY: r"\d{4}-W\d{2}",
            Period.MONTHLY: r"\d{4}-\d{2}",
        }
        if not re.fullmatch(formats[self.period], self.target):
            raise ValueError(f"Invalid {self.period} target: {self.target}")
        match self.period:
            case Period.DAILY:
                date.fromisoformat(self.target)
            case Period.WEEKLY:
                date.fromisocalendar(int(self.target[:4]), int(self.target[-2:]), 1)
            case Period.MONTHLY:
                date.fromisoformat(self.target + "-01")

    @property
    def task_id(self) -> str:
        return f"{self.source}/{self.period}/{self.target}"
