"""Run explicitly: uv run pytest tests/test_telegram_live.py --send-telegram -v"""

import logging
from pathlib import Path

import pytest

from paper_radar.config.settings import Settings
from paper_radar.core.tasks import CrawlTask, Period
from paper_radar.infrastructure.http_client import HttpClient
from paper_radar.notifications.telegram.notifier import TelegramNotifier
from paper_radar.services.notification_service import format_messages
from paper_radar.sources.huggingface.parser import parse


def test_send_combined_report_to_telegram(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not request.config.getoption("--send-telegram"):
        pytest.skip("Use --send-telegram to send one real Telegram message")

    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)
    settings = Settings.from_env()
    # HTTP logs contain the bot token in the request URL.
    for name in ("httpx", "httpcore"):
        monkeypatch.setattr(logging.getLogger(name), "level", logging.WARNING)

    task = CrawlTask("huggingface", Period.MONTHLY, "2026-09")
    html = (root / "tests/fixtures/huggingface/monthly.html").read_text(encoding="utf-8")
    result = parse(html, task)
    messages = format_messages(task, result, top=len(result.papers))
    messages[0] = "【Paper Radar 合并推送测试】以下为历史测试样本，不是今日榜单。\n\n" + messages[0]
    assert len(messages) > 1
    assert len("".join(messages).encode("utf-16-le")) // 2 > 4096

    http = HttpClient(settings)
    requests: list[str] = []
    http.client.event_hooks["request"].append(lambda request: requests.append(request.url.path))
    try:
        # send raises on HTTP errors or Telegram ok != true; no mock and no POST retry.
        TelegramNotifier(http).send_batch(messages)
        # Never include the token-bearing URL in assertion output.
        assert len(requests) == 1
        assert requests[0].endswith("/sendDocument") is True
    finally:
        http.close()
