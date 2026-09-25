from paper_radar.core.models import CrawlResult
from paper_radar.core.tasks import CrawlTask
from paper_radar.sources.base import PaperSource
from paper_radar.sources.huggingface.parser import parse
from paper_radar.sources.huggingface.urls import build_url


class HuggingFaceSource(PaperSource):
    name = "huggingface"

    def fetch(self, task: CrawlTask) -> CrawlResult:
        if task.source != self.name:
            raise ValueError("Task does not belong to Hugging Face")
        return parse(self.http.get_text(build_url(task)), task)
