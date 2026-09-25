import json
from dataclasses import replace

import httpx
import pytest
from test_crawl import FIXTURES, TASK

from paper_radar.config.settings import Settings
from paper_radar.core.exceptions import RadarError
from paper_radar.infrastructure.http_client import HttpClient
from paper_radar.notifications.loader import load_notifiers
from paper_radar.services.notification_service import NotificationService, format_messages
from paper_radar.sources.huggingface.parser import parse


def test_transient_get_retries_and_honors_retry_after(monkeypatch):
    sleeps, requests = [], []
    monkeypatch.setattr("paper_radar.infrastructure.http_client.time.sleep", sleeps.append)

    def respond(request):
        requests.append(request)
        return (
            httpx.Response(429, headers={"Retry-After": "4"})
            if len(requests) == 1
            else httpx.Response(200, text="ok")
        )

    client = HttpClient(Settings(request_interval=0), transport=httpx.MockTransport(respond))
    try:
        assert client.get_text("https://example.com") == "ok"
        assert client.retry_count == 1
        assert 4 in sleeps
    finally:
        client.close()


def test_404_does_not_retry():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(404)

    client = HttpClient(Settings(request_interval=0), transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(RadarError, match="404"):
            client.get_text("https://example.com")
        assert len(requests) == 1
    finally:
        client.close()


@pytest.mark.parametrize(
    "name,response,key",
    [
        ("feishu", {"code": 0}, "msg_type"),
        ("wechat", {"errcode": 0}, "msgtype"),
        ("telegram", {"ok": True}, "chat_id"),
    ],
)
def test_notification_flow(name, response, key, monkeypatch):
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://example.com/secret")
    monkeypatch.setenv("WECHAT_WEBHOOK_URL", "https://example.com/secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:secret")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=response)

    client = HttpClient(Settings(), transport=httpx.MockTransport(respond))
    try:
        notifier = load_notifiers()[name](client)
        result = parse((FIXTURES / "daily.html").read_text(encoding="utf-8"), TASK)
        NotificationService([notifier]).send(TASK, result, top=1)
        assert key in requests[0]
        assert "SpeakerMem" in json.dumps(requests[0])
    finally:
        client.close()


def test_post_failure_is_not_retried_or_secret_leaked():
    calls = []

    def respond(request):
        calls.append(request)
        raise httpx.ReadTimeout("secret-token", request=request)

    client = HttpClient(Settings(), transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(RadarError) as error:
            client.post_json("https://example.com/secret-token", {})
        assert "secret-token" not in str(error.value)
        assert len(calls) == 1
    finally:
        client.close()


def test_provider_error_is_not_success(monkeypatch):
    monkeypatch.setenv("WECHAT_WEBHOOK_URL", "https://example.com/hook")
    client = HttpClient(
        Settings(),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"errcode": 93000})),
    )
    try:
        with pytest.raises(RadarError, match="rejected"):
            load_notifiers()["wechat"](client).send("hello")
    finally:
        client.close()


def test_message_size_and_top_selection():
    result = parse(
        (FIXTURES / "monthly.html").read_text(encoding="utf-8"),
        replace(TASK, period="monthly", target="2026-09"),
    )
    messages = format_messages(TASK, result, top=100)
    assert len(messages) > 1
    assert all(len(message.encode("utf-8")) <= 1800 for message in messages)
    assert len(format_messages(TASK, result, top=1)) == 1
    complete = "".join(format_messages(TASK, result))
    assert len(result.papers) > 10
    for paper in result.papers:
        assert paper.title in complete


@pytest.mark.parametrize(
    "message",
    [
        "中文汇总" * 300,
        "中" * 4096,
        "中" * 4097,
        "😀" * 2049,
        "中文标题：标题 <script>\n总结：A & B",
        "中文标题：标题 <script>\n总结：A & B" + "中" * 4097,
    ],
)
def test_telegram_batch_is_one_complete_delivery(message, monkeypatch):
    from datetime import UTC, datetime
    from html import escape

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 25, 22, 5, 6, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr("paper_radar.notifications.telegram.notifier.datetime", FixedDatetime)
    timestamp = "发送时间：2026-09-26 06:05:06（北京时间 UTC+08:00）"
    full_message = f"{timestamp}\n\n{message}"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:secret")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    client = HttpClient(Settings(), transport=httpx.MockTransport(respond))
    try:
        notifier = load_notifiers()["telegram"](client)
        notifier.send_batch([message[:600], message[600:]])
        assert len(requests) == 1
        request = requests[0]
        if len(full_message.encode("utf-16-le")) // 2 <= 4096:
            assert request.url.path.endswith("/sendMessage")
            payload = json.loads(request.content)
            rendered = payload["text"]
            assert payload["parse_mode"] == "HTML"
        else:
            assert request.url.path.endswith("/sendDocument")
            assert "multipart/form-data" in request.headers["content-type"]
            assert b'filename="paper-radar.html"' in request.content
            rendered = request.content.decode("utf-8")
            assert "white-space:pre-wrap" in rendered
            assert rendered.count(timestamp) == 2  # Caption and report share the send time.
        assert timestamp in rendered
        assert escape(message) in rendered.replace("<b>", "").replace("</b>", "")
        if "中文标题：" in message:
            assert "<b>中文标题：</b>" in rendered
            assert "<b>总结：</b>" in rendered
            assert "<script>" not in rendered
    finally:
        client.close()


def test_telegram_long_report_rejection_is_not_retried(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:secret")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": False})

    client = HttpClient(Settings(), transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(RadarError, match="rejected"):
            load_notifiers()["telegram"](client).send("中" * 5000)
        assert len(requests) == 1
    finally:
        client.close()


def test_chinese_summaries_are_included_and_missing_results_are_explicit():
    from paper_radar.core.summaries import ChineseSummary, PaperSummary, SummaryResult

    result = parse((FIXTURES / "daily.html").read_text(encoding="utf-8"), TASK)
    summaries = SummaryResult(
        "test",
        "test",
        "https://example.com",
        [
            PaperSummary(
                result.papers[0].canonical_id,
                result.papers[0].title,
                "success",
                ChineseSummary("中文标题", "论文中文总结", ["关键发现"]),
            ),
            PaperSummary(result.papers[1].canonical_id, result.papers[1].title, "failed"),
        ],
    )
    messages = format_messages(TASK, result, 3, summaries)
    text = "".join(messages)
    assert "论文中文总结" in text
    assert "关键发现" in text
    assert "生成失败" in text
    assert "未生成" in text
    assert result.papers[0].url in text
    assert "\n\n────────────────────────\n\n" in text
    assert all(len(message.encode("utf-8")) <= 1800 for message in messages)


def test_failed_channel_does_not_block_other_channels(monkeypatch):
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://feishu.example/hook")
    monkeypatch.setenv("WECHAT_WEBHOOK_URL", "https://wechat.example/hook")
    calls = []

    def respond(request):
        calls.append(request.url.host)
        return httpx.Response(
            200, json={"code": 1} if request.url.host == "feishu.example" else {"errcode": 0}
        )

    client = HttpClient(Settings(), transport=httpx.MockTransport(respond))
    try:
        plugins = load_notifiers()
        service = NotificationService([plugins[name](client) for name in ("feishu", "wechat")])
        result = parse((FIXTURES / "daily.html").read_text(encoding="utf-8"), TASK)
        with pytest.raises(RadarError, match="feishu"):
            service.send(TASK, result, top=1)
        assert calls == ["feishu.example", "wechat.example"]
    finally:
        client.close()
