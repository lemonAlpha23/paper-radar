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
