import logging

from paper_radar.core.exceptions import RadarError
from paper_radar.core.models import Paper
from paper_radar.core.summaries import PaperSummary, SummaryResult
from paper_radar.summarization.base import SummaryModel

logger = logging.getLogger(__name__)


class SummaryService:
    """Summarize supplied papers independently of their source and persistence."""

    def __init__(self, model: SummaryModel):
        self.model = model

    def run(self, papers: list[Paper], limit: int | None = None) -> SummaryResult:
        if limit is not None and limit < 1:
            raise ValueError("Summary limit must be positive")
        summaries: list[PaperSummary] = []
        for paper in papers[:limit]:
            if not paper.abstract or not paper.abstract.strip():
                summaries.append(
                    PaperSummary(
                        paper.canonical_id, paper.title, "skipped", error="No abstract available"
                    )
                )
                continue
            try:
                content = self.model.summarize(paper)
            except RadarError as exc:
                logger.error("paper_id=%s summary_status=failed", paper.canonical_id)
                summaries.append(
                    PaperSummary(paper.canonical_id, paper.title, "failed", error=str(exc))
                )
            else:
                summaries.append(PaperSummary(paper.canonical_id, paper.title, "success", content))
                logger.info("paper_id=%s summary_status=success", paper.canonical_id)
        return SummaryResult(self.model.provider, self.model.model, self.model.base_url, summaries)
