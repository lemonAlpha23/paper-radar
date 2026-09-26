import json
from dataclasses import replace
from datetime import UTC, datetime

import httpx
import pytest

from paper_radar.cli import main
from paper_radar.config.settings import Settings
from paper_radar.config.summary_settings import SummarySettings
from paper_radar.core.exceptions import RadarError
from paper_radar.core.models import CrawlResult, Paper
from paper_radar.core.summaries import ChineseSummary
from paper_radar.core.tasks import CrawlTask, Period
from paper_radar.services.summary_service import SummaryService
from paper_radar.storage.json_storage import JsonStorage
from paper_radar.storage.summary_storage import SummaryJsonStorage, load_summary_input
from paper_radar.summarization.base import SummaryModel
from paper_radar.summarization.compatible.provider import CompatibleSummaryModel
from paper_radar.summarization.deepseek.provider import DeepSeekSummaryModel

PAPER = Paper("arxiv:2609.12345", "Test paper", ["Author"], "The original abstract.")
TASK = CrawlTask("huggingface", Period.DAILY, "2026-09-25")
FETCHED_AT = datetime(2026, 9, 25, 1, 59, 25, tzinfo=UTC)
CONTENT = {
    "title_zh": "测试论文",
    "summary_zh": "论文研究测试问题，并提出相应的方法。",
    "key_points": ["提出测试方法。"],
}


def completion(content=CONTENT, finish_reason="stop"):
    return {
        "choices": [
            {
                "finish_reason": finish_reason,
                "message": {"content": json.dumps(content, ensure_ascii=False)},
            }
        ]
    }


def test_deepseek_request_and_chinese_response():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=completion())

    model = DeepSeekSummaryModel(
        SummarySettings(api_key="test-secret"), transport=httpx.MockTransport(respond)
    )
    try:
        summary = model.summarize(PAPER)
    finally:
        model.close()
    assert summary == ChineseSummary(**CONTENT)
    assert str(requests[0].url) == "https://api.deepseek.com/chat/completions"
    assert requests[0].headers["Authorization"] == "Bearer test-secret"
    body = json.loads(requests[0].content)
    assert body["model"] == "deepseek-flash"
    assert body["thinking"] == {"type": "disabled"}
    assert body["response_format"] == {"type": "json_object"}
    instructions = body["messages"][0]
    assert instructions["role"] == "system"
    assert "有编程经验、但不一定熟悉论文研究领域的程序员" in instructions["content"]
    assert "准确、简洁、易懂的中文忠实翻译原标题" in instructions["content"]
    assert "保留 AI、大模型、视频生成模型" in instructions["content"]
    assert "三个字段必须在同一个对象内" in instructions["content"]
    assert json.loads(body["messages"][1]["content"]) == {
        "title": PAPER.title,
        "abstract": PAPER.abstract,
    }


def test_switch_provider_and_model(monkeypatch):
    monkeypatch.setenv("SUMMARY_PROVIDER", "compatible")
    monkeypatch.setenv("SUMMARY_MODEL", "user-selected-model")
    monkeypatch.setenv("SUMMARY_BASE_URL", "https://models.example/v1/")
    monkeypatch.setenv("API_KEY", "test-secret")
    settings = SummarySettings.from_env(model="override-model")
    assert settings.model == "override-model"
    assert "test-secret" not in repr(settings)
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=completion())

    model = CompatibleSummaryModel(settings, transport=httpx.MockTransport(respond))
    try:
        model.summarize(PAPER)
    finally:
        model.close()
    assert str(requests[0].url) == "https://models.example/v1/chat/completions"
    payload = json.loads(requests[0].content)
    assert payload["model"] == "override-model"
    assert "thinking" not in payload


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"choices": []},
        completion(finish_reason="length"),
        completion({}),
        completion({**CONTENT, "summary_zh": "English only"}),
        completion({**CONTENT, "key_points": "not a list"}),
        completion({**CONTENT, "key_points": []}),
        {"choices": [{"finish_reason": "stop", "message": {"content": ""}}]},
    ],
)
def test_invalid_model_output_never_becomes_success(body):
    model = DeepSeekSummaryModel(
        SummarySettings(api_key="test"),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)),
    )
    try:
        with pytest.raises(RadarError):
            model.summarize(PAPER)
    finally:
        model.close()


@pytest.mark.parametrize("status", [401, 429, 500, 302])
def test_http_error_is_not_retried_or_exposed(status):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            status,
            text="sensitive provider response",
            headers={"Location": "https://other.example"},
        )

    model = DeepSeekSummaryModel(
        SummarySettings(api_key="test-secret"), transport=httpx.MockTransport(respond)
    )
    try:
        with pytest.raises(RadarError, match=str(status)) as error:
            model.summarize(PAPER)
    finally:
        model.close()
    assert len(requests) == 1
    assert "sensitive" not in str(error.value)
    assert "test-secret" not in str(error.value)


class InMemoryModel(SummaryModel):
    @classmethod
    def create(cls, settings):
        return cls()

    provider = "test"
    model = "test-model"
    base_url = "https://test.example"

    def __init__(self):
        self.calls = []

    def summarize(self, paper):
        self.calls.append(paper.canonical_id)
        if paper.canonical_id == "failed":
            raise RadarError("Model request failed")
        return ChineseSummary(**CONTENT)


def test_service_is_independent_and_tracks_missing_abstract_and_failure():
    model = InMemoryModel()
    papers = [
        replace(PAPER, canonical_id="failed"),
        PAPER,
        replace(PAPER, canonical_id="missing", abstract=None),
    ]
    result = SummaryService(model).run(papers)
    assert [paper.status for paper in result.papers] == ["failed", "success", "skipped"]
    assert model.calls == ["failed", PAPER.canonical_id]
    assert result.has_failures
    assert result.papers[0].content is None
    assert result.papers[2].content is None
    assert len(SummaryService(model).run(papers, limit=1).papers) == 1
    assert SummaryService(model).run([]).papers == []


def test_snapshot_roundtrip_and_summary_history(tmp_path):
    original = CrawlResult([PAPER], [], "raw html", FETCHED_AT)
    JsonStorage(tmp_path).save(TASK, original)
    input_path = next((tmp_path / "processed" / "papers").rglob("*.json"))
    before = input_path.read_bytes()
    task, timestamp, papers = load_summary_input(input_path)
    assert (task, timestamp, papers) == (TASK, FETCHED_AT, [PAPER])
    result = SummaryService(InMemoryModel()).run(papers)
    storage = SummaryJsonStorage(tmp_path)
    first = storage.save(task, timestamp, result)
    second = storage.save(task, timestamp, result)
    assert first != second
    assert second.stem == first.stem + "-2"
    assert input_path.read_bytes() == before
    saved = json.loads(first.read_text(encoding="utf-8"))
    assert saved["source_fetched_at"] == "2026-09-25T09:59:25+08:00"
    assert saved["papers"][0]["content"]["title_zh"] == CONTENT["title_zh"]
    assert saved["model"] == "test-model"


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"schema_version": 4},
        {
            "schema_version": 2,
            "task": {"source": "../x", "period": "daily", "target": "2026-09-25"},
        },
    ],
)
def test_invalid_snapshot_is_rejected(tmp_path, data):
    path = tmp_path / "input.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RadarError):
        load_summary_input(path)


def test_standalone_cli_does_not_discover_sources_or_modify_input(tmp_path, monkeypatch):
    JsonStorage(tmp_path).save(TASK, CrawlResult([PAPER], [], "html", FETCHED_AT))
    input_path = next((tmp_path / "processed" / "papers").rglob("*.json"))
    before = input_path.read_bytes()
    monkeypatch.setattr("paper_radar.cli.Settings.from_env", lambda: Settings(data_dir=tmp_path))
    monkeypatch.setenv("API_KEY", "test")
    monkeypatch.setenv("SUMMARY_PROVIDER", "deepseek")
    monkeypatch.delenv("SUMMARY_MODEL", raising=False)

    def fail_discovery():
        raise AssertionError("Standalone summaries should not depend on source discovery")

    monkeypatch.setattr("paper_radar.cli.load_sources", fail_discovery)
    monkeypatch.setattr("paper_radar.cli.load_notifiers", fail_discovery)
    monkeypatch.setattr(
        "paper_radar.cli.create_summary_model",
        lambda provider, model: DeepSeekSummaryModel(
            SummarySettings.from_env(provider, model),
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=completion())),
        ),
    )
    assert main(["summarize", str(input_path)]) == 0
    assert input_path.read_bytes() == before
    assert len(list((tmp_path / "processed" / "summaries").rglob("*.json"))) == 1


def test_missing_key_fails_without_network(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("paper_radar.cli.Settings.from_env", lambda: Settings(data_dir=tmp_path))
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("SUMMARY_PROVIDER", "deepseek")
    assert main(["crawl", "huggingface", "daily", "--summarize"]) == 1
    assert "API_KEY" in capsys.readouterr().err


@pytest.mark.parametrize("model_status,exit_code", [(200, 0), (503, 1)])
def test_crawl_then_summary_keeps_crawl_snapshot(tmp_path, monkeypatch, model_status, exit_code):
    from pathlib import Path

    from paper_radar.infrastructure.http_client import HttpClient

    html = (Path(__file__).parent / "fixtures/huggingface/daily.html").read_text(encoding="utf-8")
    monkeypatch.setattr(
        "paper_radar.cli.Settings.from_env", lambda: Settings(data_dir=tmp_path, request_interval=0)
    )
    monkeypatch.setenv("API_KEY", "test")
    monkeypatch.setenv("SUMMARY_PROVIDER", "deepseek")
    monkeypatch.delenv("SUMMARY_MODEL", raising=False)
    monkeypatch.setattr(
        "paper_radar.cli.HttpClient",
        lambda settings: HttpClient(
            settings, transport=httpx.MockTransport(lambda request: httpx.Response(200, text=html))
        ),
    )
    monkeypatch.setattr(
        "paper_radar.cli.create_summary_model",
        lambda provider, model: DeepSeekSummaryModel(
            SummarySettings.from_env(provider, model),
            transport=httpx.MockTransport(
                lambda request: httpx.Response(model_status, json=completion())
            ),
        ),
    )

    assert (
        main(
            [
                "crawl",
                "huggingface",
                "daily",
                "--target",
                "2026-09-24",
                "--summarize",
                "--summary-limit",
                "1",
            ]
        )
        == exit_code
    )
    crawl = next((tmp_path / "processed/papers").rglob("*.json"))
    summary = next((tmp_path / "processed/summaries").rglob("*.json"))
    assert len(json.loads(crawl.read_text(encoding="utf-8"))["papers"]) == 29
    saved = json.loads(summary.read_text(encoding="utf-8"))
    assert len(saved["papers"]) == 1
    assert saved["papers"][0]["status"] == ("success" if model_status == 200 else "failed")
