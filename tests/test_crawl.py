import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from bs4 import BeautifulSoup

from paper_radar.config.settings import Settings
from paper_radar.core.exceptions import RadarError
from paper_radar.core.models import CrawlResult
from paper_radar.core.tasks import CrawlTask, Period, default_target
from paper_radar.infrastructure.http_client import HttpClient
from paper_radar.services.crawl_service import CrawlService
from paper_radar.services.dedup_service import deduplicate
from paper_radar.sources.huggingface.parser import parse
from paper_radar.sources.huggingface.source import HuggingFaceSource
from paper_radar.sources.huggingface.urls import build_url
from paper_radar.sources.loader import load_sources
from paper_radar.storage.json_storage import JsonStorage

FIXTURES = Path(__file__).parent / "fixtures" / "huggingface"
TASK = CrawlTask("huggingface", Period.DAILY, "2026-09-24")


@pytest.mark.parametrize(
    "period,target,count",
    [
        (Period.DAILY, "2026-09-24", 29),
        (Period.WEEKLY, "2026-W39", 105),
        (Period.MONTHLY, "2026-09", 105),
    ],
)
def test_real_payload(period, target, count):
    task = CrawlTask("huggingface", period, target)
    result = parse((FIXTURES / f"{period}.html").read_text(encoding="utf-8"), task)
    assert len(result.papers) == len(result.observations) == count
    assert result.papers[0].authors
    assert result.papers[0].abstract
    assert result.papers[0].canonical_id.startswith("arxiv:")
    assert result.observations[0].rank == 1
    assert result.observations[0].score >= 0
    assert result.papers[0].published_at.tzinfo is not None


def test_page_date_must_match_requested_date():
    html = (FIXTURES / "daily.html").read_text(encoding="utf-8")
    with pytest.raises(RadarError, match="returned 2026-09-24"):
        parse(html, replace(TASK, target="2026-09-25"))


@pytest.mark.parametrize(
    "html",
    [
        "<html>blocked</html>",
        '<div data-target="DailyPapers" data-props="{}"></div>',
        '<div data-target="DailyPapers" data-props="not json"></div>',
    ],
)
def test_schema_changes_fail_instead_of_saving_empty_data(html):
    with pytest.raises(RadarError):
        parse(html, TASK)


@pytest.mark.parametrize(
    "period,target",
    [
        (Period.DAILY, "2026-02-30"),
        (Period.DAILY, "../../x"),
        (Period.MONTHLY, "2026-13"),
        (Period.WEEKLY, "2025-W53"),
        (Period.DAILY, "2026-9-2"),
    ],
)
def test_invalid_target(period, target):
    with pytest.raises(ValueError):
        CrawlTask("huggingface", period, target)


def test_iso_year_boundary():
    assert default_target(Period.WEEKLY, date(2021, 1, 1)) == "2020-W53"
    assert build_url(CrawlTask("huggingface", Period.WEEKLY, "2020-W53")).endswith("/week/2020-W53")


def test_source_to_storage_preserves_each_fetch(tmp_path):
    html = (FIXTURES / "daily.html").read_text(encoding="utf-8")
    requests = []

    def respond(request):
        requests.append(str(request.url))
        return httpx.Response(200, text=html)

    http = HttpClient(Settings(request_interval=0), transport=httpx.MockTransport(respond))
    try:
        service = CrawlService(HuggingFaceSource(http), JsonStorage(tmp_path))
        first = service.run(TASK)
        service.run(TASK)
    finally:
        http.close()
    assert requests == [build_url(TASK)] * 2
    files = list(tmp_path.rglob("*.json"))
    assert len(files) == 2
    document = json.loads(files[0].read_text(encoding="utf-8"))
    assert len(document["papers"]) == len(first.papers)
    assert document["task"]["target"] == TASK.target
    assert len(list(tmp_path.rglob("*.html"))) == 2
    assert all(path.parent.name == TASK.target for path in files)


def test_dedup_retains_best_rank_and_rejects_broken_references():
    result = parse((FIXTURES / "daily.html").read_text(encoding="utf-8"), TASK)
    paper, observation = result.papers[0], result.observations[0]
    duplicate = CrawlResult([paper, paper], [replace(observation, rank=5), observation], "")
    cleaned = deduplicate(TASK, duplicate)
    assert cleaned.papers == [paper]
    assert cleaned.observations == [observation]
    assert cleaned.fetched_at == duplicate.fetched_at
    with pytest.raises(ValueError):
        deduplicate(TASK, CrawlResult([], [observation], ""))


def test_atomic_failure_preserves_previous_snapshot(tmp_path, monkeypatch):
    result = parse(
        (FIXTURES / "daily.html").read_text(encoding="utf-8"),
        TASK,
        datetime(2026, 9, 25, tzinfo=UTC),
    )
    storage = JsonStorage(tmp_path)
    storage.save(TASK, result)
    snapshot = next(tmp_path.rglob("*.json"))
    before = snapshot.read_bytes()

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr("paper_radar.storage.json_files.os.replace", fail)
    with pytest.raises(OSError):
        storage.save(TASK, result)
    assert snapshot.read_bytes() == before
    assert len(list(tmp_path.rglob("*.*"))) == 2


def test_discovery():
    assert load_sources() == {"huggingface": HuggingFaceSource}


def test_explicit_empty_payload_is_valid():
    node = BeautifulSoup((FIXTURES / "daily.html").read_text(encoding="utf-8"), "html.parser")
    component = node.select_one('[data-target="DailyPapers"]')
    payload = json.loads(component["data-props"])
    payload["dailyPapers"] = []
    component["data-props"] = json.dumps(payload)
    result = parse(str(node), TASK)
    assert result.papers == result.observations == []


def test_parse_failure_does_not_touch_existing_snapshot(tmp_path):
    storage = JsonStorage(tmp_path)
    storage.save(TASK, parse((FIXTURES / "daily.html").read_text(encoding="utf-8"), TASK))
    snapshot = next(tmp_path.rglob("*.json"))
    before = snapshot.read_bytes()
    http = HttpClient(
        Settings(request_interval=0),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="<html>maintenance</html>")
        ),
    )
    try:
        with pytest.raises(RadarError):
            CrawlService(HuggingFaceSource(http), storage).run(TASK)
    finally:
        http.close()
    assert snapshot.read_bytes() == before
