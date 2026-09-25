import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from paper_radar.core.models import CrawlResult
from paper_radar.core.tasks import CrawlTask, Period
from paper_radar.storage.json_storage import JsonStorage


@pytest.mark.parametrize(
    "period,target",
    [(Period.DAILY, "2026-09-24"), (Period.WEEKLY, "2026-W39"), (Period.MONTHLY, "2026-09")],
)
def test_snapshot_paths_use_beijing_fetch_time_even_for_empty_results(tmp_path, period, target):
    task = CrawlTask("huggingface", period, target)
    fetched_at = datetime(2026, 9, 24, 22, 0, 12, 123456, tzinfo=UTC)
    result = CrawlResult([], [], "<html>empty ranking</html>", fetched_at)

    JsonStorage(tmp_path).save(task, result)

    relative = f"huggingface/{period}/{target}/2026-09-25_06-00-12"
    raw = tmp_path / "raw" / f"{relative}.html"
    processed = tmp_path / "processed" / "papers" / f"{relative}.json"
    assert raw.read_text(encoding="utf-8") == result.raw_html
    document = json.loads(processed.read_text(encoding="utf-8"))
    assert document["schema_version"] == 2
    assert document["fetched_at"] == "2026-09-25T06:00:12.123456+08:00"
    assert document["task"]["target"] == target
    assert document["papers"] == document["observations"] == []


def test_three_daily_runs_and_same_second_fetches_preserve_history(tmp_path):
    task = CrawlTask("huggingface", Period.DAILY, "2026-09-24")
    timestamps = [
        datetime(2026, 9, 24, 22, tzinfo=UTC),
        datetime(2026, 9, 25, 4, tzinfo=UTC),
        datetime(2026, 9, 25, 10, tzinfo=UTC),
        datetime(2026, 9, 25, 10, 0, 0, 1, tzinfo=UTC),
    ]
    storage = JsonStorage(tmp_path)
    for index, timestamp in enumerate(timestamps):
        storage.save(task, CrawlResult([], [], f"snapshot {index}", timestamp))

    files = sorted(tmp_path.rglob("*.json"))
    assert {path.stem for path in files} == {
        "2026-09-25_06-00-00",
        "2026-09-25_12-00-00",
        "2026-09-25_18-00-00",
        "2026-09-25_18-00-00-2",
    }
    assert {path.stem for path in tmp_path.rglob("*.html")} == {path.stem for path in files}
    storage.save(task, CrawlResult([], [], "snapshot 3", timestamps[-1]))
    assert len(list(tmp_path.rglob("*.json"))) == 4
    directory = tmp_path / "raw" / "huggingface" / "daily" / task.target
    assert (directory / "2026-09-25_18-00-00.html").read_text() == "snapshot 2"
    assert (directory / "2026-09-25_18-00-00-2.html").read_text() == "snapshot 3"


def test_raw_only_snapshot_is_not_overwritten(tmp_path):
    task = CrawlTask("huggingface", Period.DAILY, "2026-09-24")
    directory = tmp_path / "raw" / "huggingface" / "daily" / task.target
    directory.mkdir(parents=True)
    orphan = directory / "2026-09-25_08-00-00.html"
    orphan.write_text("interrupted fetch", encoding="utf-8")
    result = CrawlResult([], [], "new fetch", datetime(2026, 9, 25, tzinfo=UTC))
    JsonStorage(tmp_path).save(task, result)
    assert orphan.read_text(encoding="utf-8") == "interrupted fetch"
    snapshot = next(tmp_path.rglob("*.json"))
    assert snapshot.stem == "2026-09-25_08-00-00-2"
    assert (directory / f"{snapshot.stem}.html").read_text(encoding="utf-8") == "new fetch"


def test_resaving_same_result_uses_same_snapshot_path(tmp_path):
    task = CrawlTask("huggingface", Period.DAILY, "2026-09-24")
    result = CrawlResult([], [], "original", datetime(2026, 9, 25, tzinfo=UTC))
    storage = JsonStorage(tmp_path)
    storage.save(task, result)
    storage.save(task, result)
    assert len(list(tmp_path.rglob("*.json"))) == 1
    assert len(list(tmp_path.rglob("*.html"))) == 1


def test_fetch_time_requires_timezone():
    with pytest.raises(ValueError, match="timezone"):
        CrawlResult([], [], "", datetime(2026, 9, 25))


def test_failed_new_snapshot_keeps_previous_history(tmp_path, monkeypatch):
    task = CrawlTask("huggingface", Period.DAILY, "2026-09-24")
    result = CrawlResult([], [], "original", datetime(2026, 9, 25, 4, tzinfo=UTC))
    storage = JsonStorage(tmp_path)
    storage.save(task, result)
    existing = {path: path.read_bytes() for path in tmp_path.rglob("*.*")}

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr("paper_radar.storage.json_files.os.replace", fail)
    with pytest.raises(OSError):
        storage.save(task, replace(result, fetched_at=datetime(2026, 9, 25, 10, tzinfo=UTC)))
    assert {path: path.read_bytes() for path in tmp_path.rglob("*.*")} == existing
