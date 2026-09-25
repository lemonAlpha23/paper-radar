import logging
import time

from paper_radar.core.exceptions import RadarError
from paper_radar.core.models import CrawlResult
from paper_radar.core.tasks import CrawlTask
from paper_radar.notifications.base import Notifier

logger = logging.getLogger(__name__)


def format_messages(task: CrawlTask, result: CrawlResult, top: int) -> list[str]:
    if top < 1:
        raise ValueError("top must be positive")
    papers = {paper.canonical_id: paper for paper in result.papers}
    lines = [f"Paper Radar | {task.source} | {task.period} | {task.target}\n"]
    for observation in sorted(result.observations, key=lambda item: item.rank)[:top]:
        paper = papers[observation.paper_id]
        score = f" | votes: {observation.score:g}" if observation.score is not None else ""
        lines.append(
            f"{observation.rank}. {paper.title}{score}\n{paper.url or paper.canonical_id}\n"
        )
    if not result.papers:
        lines.append("No papers in this period.")
    # UTF-8 byte limit is stricter than all three providers' text character limits.
    messages: list[str] = []
    current = ""
    size = 0
    for character in "\n".join(lines):
        length = len(character.encode("utf-8"))
        if size + length > 1800:
            messages.append(current)
            current, size = "", 0
        current += character
        size += length
    if current:
        messages.append(current)
    return messages


class NotificationService:
    def __init__(self, notifiers: list[Notifier]):
        self.notifiers = notifiers

    def send(self, task: CrawlTask, result: CrawlResult, top: int = 10) -> None:
        messages = format_messages(task, result, top)
        failed = []
        for notifier in self.notifiers:
            try:
                for index, message in enumerate(messages):
                    if index:
                        time.sleep(3)  # Respect the group robot's 20 messages/minute limit.
                    notifier.send(message)
            except RadarError:
                failed.append(notifier.name)
                logger.error("task_id=%s notifier=%s status=failed", task.task_id, notifier.name)
            else:
                logger.info("task_id=%s notifier=%s status=sent", task.task_id, notifier.name)
        if failed:
            raise RadarError("Notification failed for: " + ", ".join(failed))
