from dataclasses import replace

import httpx

from paper_radar.config.summary_settings import SummarySettings
from paper_radar.summarization.chat_completions import ChatCompletionSummaryModel


class DeepSeekSummaryModel(ChatCompletionSummaryModel):
    name = "deepseek"
    extra_payload = {"thinking": {"type": "disabled"}}

    def __init__(self, settings: SummarySettings, *, transport: httpx.BaseTransport | None = None):
        settings = replace(
            settings,
            provider=self.name,
            model=settings.model or "deepseek-flash",
            base_url="https://api.deepseek.com",
        )
        super().__init__(settings, transport=transport)

    @classmethod
    def create(cls, settings: SummarySettings) -> "DeepSeekSummaryModel":
        return cls(settings)
