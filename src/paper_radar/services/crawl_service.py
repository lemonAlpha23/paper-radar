import logging
import time

from paper_radar.core.models import CrawlResult
from paper_radar.core.tasks import CrawlTask
from paper_radar.services.dedup_service import deduplicate
from paper_radar.sources.base import PaperSource
from paper_radar.storage.base import PaperStorage

logger = logging.getLogger(__name__)


class CrawlService:
    def __init__(self, source: PaperSource, storage: PaperStorage):
        self.source = source
        self.storage = storage

    def run(self, task: CrawlTask) -> CrawlResult:
        start = time.monotonic()
        retries_before = self.source.http.retry_count
        try:
            result = deduplicate(task, self.source.fetch(task))
            self.storage.save(task, result)
        except Exception as exc:
            logger.error(
                "task_id=%s status=failed duration=%.2f error=%s",
                task.task_id,
                time.monotonic() - start,
                type(exc).__name__,
            )
            raise
        logger.info(
            "task_id=%s status=success paper_count=%s duration=%.2f retry_count=%s",
            task.task_id,
            len(result.papers),
            time.monotonic() - start,
            self.source.http.retry_count - retries_before,
        )
        return result
