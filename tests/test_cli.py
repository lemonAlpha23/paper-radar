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
