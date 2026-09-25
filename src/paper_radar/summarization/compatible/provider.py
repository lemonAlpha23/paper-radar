from dataclasses import replace

import httpx

from paper_radar.config.summary_settings import SummarySettings
from paper_radar.summarization.chat_completions import ChatCompletionSummaryModel


class CompatibleSummaryModel(ChatCompletionSummaryModel):
    name = "compatible"

    def __init__(self, settings: SummarySettings, *, transport: httpx.BaseTransport | None = None):
        if not settings.model.strip() or not settings.base_url:
            raise ValueError("Compatible provider requires SUMMARY_MODEL and SUMMARY_BASE_URL")
        super().__init__(replace(settings, provider=self.name), transport=transport)

    @classmethod
    def create(cls, settings: SummarySettings) -> "CompatibleSummaryModel":
        return cls(settings)
