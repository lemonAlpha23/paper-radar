import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from paper_radar.core.models import CrawlResult
from paper_radar.core.tasks import CrawlTask
from paper_radar.storage.base import PaperStorage
from paper_radar.storage.json_files import atomic_write, encode_json


class JsonStorage(PaperStorage):
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def save(self, task: CrawlTask, result: CrawlResult) -> None:
        fetched_at = result.fetched_at.astimezone(ZoneInfo("Asia/Shanghai"))
        filename = fetched_at.strftime("%Y-%m-%d_%H-%M-%S")
        relative = Path(task.source) / task.period / task.target
        sequence = 1
        while True:
            stem = filename if sequence == 1 else f"{filename}-{sequence}"
            raw = self.data_dir / "raw" / relative / f"{stem}.html"
            processed = self.data_dir / "processed" / "papers" / relative / f"{stem}.json"
            if processed.exists():
                saved = json.loads(processed.read_text(encoding="utf-8"))
                if datetime.fromisoformat(saved["fetched_at"]) == fetched_at:
                    break  # Saving the same fetch again must reuse its original path.
            elif not raw.exists():
                break
            # A raw-only file may belong to an interrupted save; leave it intact.
            sequence += 1
        document = {
            "schema_version": 2,
            "task": asdict(task),
            "fetched_at": fetched_at,
            "papers": [asdict(paper) for paper in result.papers],
            "observations": [asdict(item) for item in result.observations],
        }
        encoded = encode_json(document)
        # Processed JSON is the authoritative task snapshot, replaced only after raw is saved.
        atomic_write(raw, result.raw_html)
        atomic_write(processed, encoded)
