import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from paper_radar.core.exceptions import RadarError
from paper_radar.core.models import Paper
from paper_radar.core.summaries import SummaryResult
from paper_radar.core.tasks import CrawlTask, Period
from paper_radar.storage.json_files import atomic_write, encode_json


def load_summary_input(path: Path) -> tuple[CrawlTask, datetime, list[Paper]]:
    """Read existing v1/v2 crawl snapshots without fetching their source again."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["schema_version"] not in {1, 2}:
            raise ValueError("Unsupported snapshot version")
        task = CrawlTask(
            data["task"]["source"], Period(data["task"]["period"]), data["task"]["target"]
        )
        # v1 did not have a snapshot timestamp; observations carry the actual fetch time.
        timestamp = (
            data["fetched_at"]
            if data["schema_version"] == 2
            else data["observations"][0]["observed_at"]
        )
        fetched_at = datetime.fromisoformat(timestamp)
        if fetched_at.utcoffset() is None or not isinstance(data["papers"], list):
            raise ValueError("Invalid snapshot timestamp or paper list")
        papers = []
        seen: set[str] = set()
        for item in data["papers"]:
            identifier, title, authors = item["canonical_id"], item["title"], item["authors"]
            abstract = item.get("abstract")
            if (
                not isinstance(identifier, str)
                or not identifier.strip()
                or identifier in seen
                or not isinstance(title, str)
                or not title.strip()
                or not isinstance(authors, list)
                or any(not isinstance(a, str) for a in authors)
                or (abstract is not None and not isinstance(abstract, str))
            ):
                raise ValueError("Invalid paper data")
            seen.add(identifier)
            papers.append(Paper(identifier, title, authors, abstract))
        return task, fetched_at, papers
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        raise RadarError(
            "Invalid crawl snapshot; expected a v1/v2 papers JSON with fetch time"
        ) from None


class SummaryJsonStorage:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def save(self, task: CrawlTask, fetched_at: datetime, result: SummaryResult) -> Path:
        if fetched_at.utcoffset() is None or result.summarized_at.utcoffset() is None:
            raise ValueError("Summary timestamps must include a timezone")
        zone = ZoneInfo("Asia/Shanghai")
        summarized_at = result.summarized_at.astimezone(zone)
        folder = self.data_dir / "processed" / "summaries" / task.source / task.period / task.target
        filename = summarized_at.strftime("%Y-%m-%d_%H-%M-%S")
        sequence = 1
        while True:
            stem = filename if sequence == 1 else f"{filename}-{sequence}"
            path = folder / f"{stem}.json"
            if not path.exists():
                break
            sequence += 1
        document = {
            "schema_version": 1,
            "task": asdict(task),
            "source_fetched_at": fetched_at.astimezone(zone),
            "summarized_at": summarized_at,
            "language": "zh-CN",
            "provider": result.provider,
            "model": result.model,
            "base_url": result.base_url,
            "status": "partial_failure" if result.has_failures else "complete",
            "papers": [asdict(paper) for paper in result.papers],
        }
        atomic_write(path, encode_json(document))
        return path
