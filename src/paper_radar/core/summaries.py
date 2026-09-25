from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal


@dataclass(frozen=True)
class ChineseSummary:
    title_zh: str
    summary_zh: str
    key_points: list[str]


@dataclass(frozen=True)
class PaperSummary:
    paper_id: str
    original_title: str
    status: Literal["success", "failed", "skipped"]
    content: ChineseSummary | None = None
    error: str | None = None


@dataclass(frozen=True)
class SummaryResult:
    provider: str
    model: str
    base_url: str
    papers: list[PaperSummary]
    summarized_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def has_failures(self) -> bool:
        return any(paper.status == "failed" for paper in self.papers)
