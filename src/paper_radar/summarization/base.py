from abc import ABC, abstractmethod
from typing import ClassVar

from paper_radar.config.summary_settings import SummarySettings
from paper_radar.core.models import Paper
from paper_radar.core.summaries import ChineseSummary


class SummaryModel(ABC):
    """A model adapter knows its API, but neither crawls nor writes files."""

    name: ClassVar[str]
    provider: str
    model: str
    base_url: str

    @abstractmethod
    def summarize(self, paper: Paper) -> ChineseSummary: ...

    @classmethod
    @abstractmethod
    def create(cls, settings: SummarySettings) -> "SummaryModel": ...

    def close(self) -> None:
        """Override when the plugin owns connections or other resources."""
        return None
