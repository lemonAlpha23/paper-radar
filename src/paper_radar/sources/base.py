from abc import ABC, abstractmethod
from typing import ClassVar

from paper_radar.core.models import CrawlResult
from paper_radar.core.tasks import CrawlTask
from paper_radar.infrastructure.http_client import HttpClient


class PaperSource(ABC):
    name: ClassVar[str]

    def __init__(self, http: HttpClient):
        self.http = http

    @abstractmethod
    def fetch(self, task: CrawlTask) -> CrawlResult: ...
