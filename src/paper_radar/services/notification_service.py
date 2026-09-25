import logging

from paper_radar.core.exceptions import RadarError
from paper_radar.core.models import CrawlResult
from paper_radar.core.summaries import SummaryResult
from paper_radar.core.tasks import CrawlTask
from paper_radar.notifications.base import Notifier

logger = logging.getLogger(__name__)


def format_messages(
    task: CrawlTask,
    result: CrawlResult,
    top: int | None = None,
    summaries: SummaryResult | None = None,
) -> list[str]:
    if top is not None and top < 1:
        raise ValueError("top must be positive")
    papers = {paper.canonical_id: paper for paper in result.papers}
    translated = {item.paper_id: item for item in summaries.papers} if summaries else {}
    lines = [f"Paper Radar | {task.source} | {task.period} | {task.target}\n"]
    for observation in sorted(result.observations, key=lambda item: item.rank)[:top]:
        if len(lines) > 1:
            lines.append("\n\n────────────────────────\n\n")
        paper = papers[observation.paper_id]
        score = f" | votes: {observation.score:g}" if observation.score is not None else ""
        lines.append(
            f"{observation.rank}. {paper.title}{score}\n{paper.url or paper.canonical_id}\n"
        )
        if summaries is not None:
            item = translated.get(paper.canonical_id)
            if item is not None and item.status == "success" and item.content is not None:
                lines.append(f"中文标题：{item.content.title_zh}\n总结：{item.content.summary_zh}")
                lines.extend(f"• {point}" for point in item.content.key_points)
            else:
                status = {"failed": "生成失败", "skipped": "缺少原文摘要，已跳过"}
                lines.append(
                    "中文总结：" + (status.get(item.status, "未生成") if item else "未生成")
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

    def send(
        self,
        task: CrawlTask,
        result: CrawlResult,
        top: int | None = None,
        *,
        summaries: SummaryResult | None = None,
    ) -> None:
        messages = format_messages(task, result, top, summaries)
        failed = []
        for notifier in self.notifiers:
            try:
                notifier.send_batch(messages)
            except RadarError:
                failed.append(notifier.name)
                logger.error("task_id=%s notifier=%s status=failed", task.task_id, notifier.name)
            else:
                logger.info("task_id=%s notifier=%s status=sent", task.task_id, notifier.name)
        if failed:
            raise RadarError("Notification failed for: " + ", ".join(failed))
