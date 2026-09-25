from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from paper_radar.core.tasks import Period


@dataclass(frozen=True)
class Paper:
    canonical_id: str
    title: str
    authors: list[str]
    abstract: str | None = None
    published_at: datetime | None = None
    url: str | None = None


@dataclass(frozen=True)
class PaperObservation:
    paper_id: str
    source: str
    period: Period
    target: str
    rank: int
    score: float | None
    observed_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CrawlResult:
    papers: list[Paper]
    observations: list[PaperObservation]
    raw_html: str
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.fetched_at.utcoffset() is None:
            raise ValueError("fetched_at must include a timezone")
