import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from paper_radar.config.settings import Settings
from paper_radar.core.exceptions import RadarError
from paper_radar.core.models import Paper
from paper_radar.core.summaries import SummaryResult
from paper_radar.core.tasks import CrawlTask, Period, default_target
from paper_radar.infrastructure.http_client import HttpClient
from paper_radar.notifications.loader import load_notifiers
from paper_radar.services.crawl_service import CrawlService
from paper_radar.services.notification_service import NotificationService
from paper_radar.services.summary_service import SummaryService
from paper_radar.sources.loader import load_sources
from paper_radar.storage.json_storage import JsonStorage
from paper_radar.storage.summary_storage import SummaryJsonStorage, load_summary_input
from paper_radar.summarization.base import SummaryModel
from paper_radar.summarization.loader import create_summary_model, load_summary_models


def summarize_papers(
    task: CrawlTask,
    fetched_at: datetime,
    papers: list[Paper],
    model: SummaryModel,
    data_dir: Path,
    limit: int | None,
) -> SummaryResult:
    result = SummaryService(model).run(papers, limit)
    path = SummaryJsonStorage(data_dir).save(task, fetched_at, result)
    counts = {
        status: sum(paper.status == status for paper in result.papers)
        for status in ("success", "failed", "skipped")
    }
    print(f"{task.task_id}: summaries {counts}; saved {path}")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect and deliver paper rankings")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sources", help="List discovered sources")
    commands.add_parser("notifiers", help="List discovered notification channels")
    commands.add_parser("summary-models", help="List discovered summary providers")
    crawl = commands.add_parser("crawl", help="Fetch and save a ranking")
    crawl.add_argument("source")
    crawl.add_argument("period", choices=[*Period, "all"])
    crawl.add_argument("--target", help="YYYY-MM-DD, YYYY-Www, or YYYY-MM")
    crawl.add_argument("--notify", action="append", default=[], metavar="CHANNEL")
    crawl.add_argument("--top", type=int, help="Limit notification papers (default all)")
    crawl.add_argument("--data-dir", type=Path)
    crawl.add_argument("--summarize", action="store_true", help="Generate Chinese summaries")
    summarize = commands.add_parser("summarize", help="Summarize an existing crawl JSON snapshot")
    summarize.add_argument("input", type=Path)
    summarize.add_argument("--data-dir", type=Path)
    for command in (crawl, summarize):
        command.add_argument("--summary-provider", help="Discovered summary provider name")
        command.add_argument("--summary-model", help="Override SUMMARY_MODEL")
        command.add_argument(
            "--summary-limit", type=int, help="Summarize first N papers (default all)"
        )
    args = parser.parse_args(argv)
    http = None
    model = None
    try:
        if args.command == "summary-models":
            print("\n".join(sorted(load_summary_models())))
            return 0
        if args.command in {"sources", "notifiers"}:
            plugins = load_sources() if args.command == "sources" else load_notifiers()
            print("\n".join(sorted(plugins)))
            return 0
        settings = Settings.from_env()
        logging.basicConfig(level=settings.log_level, format="%(levelname)s %(message)s")
        # HTTP logs can expose webhook credentials and model request details.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        if args.summary_limit is not None and args.summary_limit < 1:
            raise RadarError("--summary-limit must be positive")
        if args.command == "summarize":
            task, fetched_at, papers = load_summary_input(args.input)
            model = create_summary_model(args.summary_provider, args.summary_model)
            return int(
                summarize_papers(
                    task,
                    fetched_at,
                    papers,
                    model,
                    args.data_dir or settings.data_dir,
                    args.summary_limit,
                ).has_failures
            )
        sources = load_sources()
        notifiers = load_notifiers()
        if args.source not in sources:
            raise RadarError(f"Unknown source: {args.source}")
        if args.top is not None and args.top < 1:
            raise RadarError("--top must be positive")
        if args.period == "all" and args.target:
            raise RadarError("--target requires one period, not all")
        for name in args.notify:
            if name not in notifiers:
                raise RadarError(f"Unknown notifier: {name}")
        today = datetime.now(ZoneInfo(settings.timezone)).date()
        periods = list(Period) if args.period == "all" else [Period(args.period)]
        tasks = [
            CrawlTask(args.source, period, args.target or default_target(period, today))
            for period in periods
        ]
        if args.summarize:
            model = create_summary_model(args.summary_provider, args.summary_model)
        elif args.summary_provider or args.summary_model or args.summary_limit is not None:
            raise RadarError("Summary options require --summarize on crawl")
        http = HttpClient(settings)
        notification = NotificationService(
            [notifiers[name](http) for name in dict.fromkeys(args.notify)]
        )
        service = CrawlService(
            sources[args.source](http), JsonStorage(args.data_dir or settings.data_dir)
        )
        failed = False
        for task in tasks:
            try:
                result = service.run(task)
                print(f"{task.task_id}: saved {len(result.papers)} papers")
                summaries = None
                if model is not None:
                    summaries = summarize_papers(
                        task,
                        result.fetched_at,
                        result.papers,
                        model,
                        args.data_dir or settings.data_dir,
                        args.summary_limit,
                    )
                    failed |= summaries.has_failures
                if args.notify:
                    notification.send(task, result, args.top, summaries=summaries)
            except (RadarError, ValueError, OSError) as exc:
                failed = True
                print(f"{task.task_id}: {exc}", file=sys.stderr)
        return 1 if failed else 0
    except (RadarError, ValueError, OSError, ZoneInfoNotFoundError) as exc:
        print(f"paper-radar: {exc}", file=sys.stderr)
        return 1
    finally:
        if http is not None:
            http.close()
        if model is not None:
            model.close()
