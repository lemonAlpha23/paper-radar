from paper_radar.infrastructure.discovery import discover
from paper_radar.notifications.base import Notifier


def load_notifiers() -> dict[str, type[Notifier]]:
    # Discovery inspects this abstract class; it only instantiates concrete subclasses.
    return discover("paper_radar.notifications", Notifier)  # type: ignore[type-abstract]
