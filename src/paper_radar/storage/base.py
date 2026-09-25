from abc import ABC, abstractmethod

from paper_radar.core.models import CrawlResult
from paper_radar.core.tasks import CrawlTask


class PaperStorage(ABC):
    @abstractmethod
    def save(self, task: CrawlTask, result: CrawlResult) -> None: ...
