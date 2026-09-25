from paper_radar.infrastructure.discovery import discover
from paper_radar.sources.base import PaperSource


def load_sources() -> dict[str, type[PaperSource]]:
    # Discovery inspects this abstract class; it only instantiates concrete subclasses.
    return discover("paper_radar.sources", PaperSource)  # type: ignore[type-abstract]
