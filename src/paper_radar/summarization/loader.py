import os

from paper_radar.config.summary_settings import SummarySettings
from paper_radar.core.exceptions import RadarError
from paper_radar.infrastructure.discovery import discover
from paper_radar.summarization.base import SummaryModel


def load_summary_models() -> dict[str, type[SummaryModel]]:
    # Discovery inspects an abstract interface and returns only concrete implementations.
    return discover("paper_radar.summarization", SummaryModel)  # type: ignore[type-abstract]


def create_summary_model(provider: str | None = None, model: str | None = None) -> SummaryModel:
    name = provider or os.getenv("SUMMARY_PROVIDER") or "deepseek"
    plugins = load_summary_models()
    if name not in plugins:
        raise RadarError(
            f"Unknown summary provider: {name}; available: {', '.join(sorted(plugins))}"
        )
    return plugins[name].create(SummarySettings.from_env(name, model))
