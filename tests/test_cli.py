from datetime import datetime

import pytest

from paper_radar.cli import main


def test_list_plugins_without_notification_credentials(monkeypatch, capsys):
    for name in ("FEISHU_WEBHOOK_URL", "WECHAT_WEBHOOK_URL", "TELEGRAM_BOT_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    assert main(["sources"]) == 0
    assert capsys.readouterr().out.strip() == "huggingface"
    assert main(["notifiers"]) == 0
    assert capsys.readouterr().out.splitlines() == ["feishu", "telegram", "wechat"]


def test_invalid_tasks_fail_before_network(capsys):
    assert main(["crawl", "huggingface", "all", "--target", "2026-09-24"]) == 1
    assert "requires one period" in capsys.readouterr().err
    assert main(["crawl", "huggingface", "daily", "--target", "../escape"]) == 1
    assert "Invalid daily target" in capsys.readouterr().err


@pytest.mark.parametrize(
    "today,expected",
    [
        (datetime(2026, 9, 26), ["2026-09-25", "2026-W39", "2026-09"]),
        (datetime(2026, 1, 1), ["2025-12-31", "2026-W01", "2026-01"]),
        (datetime(2024, 3, 1), ["2024-02-29", "2024-W09", "2024-03"]),
    ],
)
def test_default_targets_and_explicit_daily_override(monkeypatch, tmp_path, today, expected):
    from paper_radar.config.settings import Settings
    from paper_radar.core.models import CrawlResult

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            assert str(tz) == "Asia/Shanghai"
            return today.replace(tzinfo=tz)

    tasks = []

    def run(self, task):
        tasks.append(task)
        return CrawlResult([], [], "")

    monkeypatch.setattr("paper_radar.cli.datetime", FixedDatetime)
    monkeypatch.setattr("paper_radar.cli.Settings.from_env", lambda: Settings())
    monkeypatch.setattr("paper_radar.cli.CrawlService.run", run)
    assert main(["crawl", "huggingface", "all", "--data-dir", str(tmp_path)]) == 0
    assert [task.target for task in tasks] == expected
    tasks.clear()
    assert (
        main(
            [
                "crawl",
                "huggingface",
                "daily",
                "--target",
                "2026-09-26",
                "--data-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert [task.target for task in tasks] == ["2026-09-26"]


def test_default_notification_has_no_limit(monkeypatch, tmp_path):
    from paper_radar.core.models import CrawlResult

    limits = []
    monkeypatch.setattr(
        "paper_radar.cli.CrawlService.run", lambda self, task: CrawlResult([], [], "")
    )
    monkeypatch.setattr("paper_radar.cli.load_notifiers", lambda: {"test": lambda http: object()})
    monkeypatch.setattr(
        "paper_radar.cli.NotificationService.send",
        lambda self, task, result, top, **kwargs: limits.append(top),
    )
    args = ["crawl", "huggingface", "all", "--notify", "test", "--data-dir", str(tmp_path)]
    assert main(args) == 0
    assert limits == [None, None, None]
    limits.clear()
    assert main([*args, "--top", "5"]) == 0
    assert limits == [5, 5, 5]


def test_all_attempts_remaining_tasks_after_failure(monkeypatch, tmp_path, capsys):
    from paper_radar.core.exceptions import RadarError
    from paper_radar.core.models import CrawlResult

    attempted = []

    def run(self, task):
        attempted.append(task.period)
        if task.period == "daily":
            raise RadarError("not published yet")
        return CrawlResult([], [], "")

    monkeypatch.setattr("paper_radar.cli.CrawlService.run", run)
    assert main(["crawl", "huggingface", "all", "--data-dir", str(tmp_path)]) == 1
    assert attempted == ["daily", "weekly", "monthly"]
    assert "not published yet" in capsys.readouterr().err
