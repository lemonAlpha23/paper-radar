import json
import re
from datetime import UTC, date, datetime, timedelta

from bs4 import BeautifulSoup

from paper_radar.core.exceptions import RadarError
from paper_radar.core.models import CrawlResult, Paper, PaperObservation
from paper_radar.core.tasks import CrawlTask, Period, default_target


def parse(html: str, task: CrawlTask, observed_at: datetime | None = None) -> CrawlResult:
    """Read the server-rendered DailyPapers payload; fail closed on schema changes."""
    node = BeautifulSoup(html, "html.parser").select_one('[data-target="DailyPapers"]')
    if node is None or not isinstance(node.get("data-props"), str):
        raise RadarError("Hugging Face DailyPapers payload is missing")
    papers: list[Paper] = []
    observations: list[PaperObservation] = []
    observed_at = observed_at or datetime.now(UTC)
    try:
        payload = json.loads(str(node["data-props"]))
        expected_period = {Period.DAILY: "day", Period.WEEKLY: "week", Period.MONTHLY: "month"}
        if payload["periodType"] != expected_period[task.period]:
            raise ValueError("Unexpected page period")
        page_date = date.fromisoformat(payload["dateString"])
        # HF's weekly payload uses the Sunday preceding the ISO week's Monday.
        if task.period == Period.WEEKLY:
            page_date += timedelta(days=1)
        actual_target = default_target(task.period, page_date)
        if actual_target != task.target:
            raise RadarError(f"Requested {task.target}, but Hugging Face returned {actual_target}")
        entries = payload["dailyPapers"]
        if not isinstance(entries, list):
            raise ValueError("dailyPapers is not a list")
        for rank, entry in enumerate(entries, 1):
            paper = entry["paper"]
            identifier = paper["id"]
            if not isinstance(identifier, str) or not re.fullmatch(
                r"(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?", identifier
            ):
                raise ValueError("Invalid arXiv identifier")
            canonical_id = "arxiv:" + re.sub(r"v\d+$", "", identifier)
            title = paper["title"]
            authors = paper["authors"]
            if not isinstance(title, str) or not title.strip() or not isinstance(authors, list):
                raise ValueError("Invalid paper title or authors")
            names = [author["name"] for author in authors]
            if any(not isinstance(name, str) or not name.strip() for name in names):
                raise ValueError("Invalid author name")
            upvotes = paper.get("upvotes")
            if upvotes is not None and (type(upvotes) is not int or upvotes < 0):
                raise ValueError("Invalid upvote count")
            abstract = paper.get("summary")
            if abstract is not None and not isinstance(abstract, str):
                raise ValueError("Invalid summary")
            published = paper.get("publishedAt")
            published_at = datetime.fromisoformat(published) if published else None
            if published_at is not None and published_at.tzinfo is None:
                raise ValueError("Published date has no timezone")
            papers.append(
                Paper(
                    canonical_id,
                    " ".join(title.split()),
                    names,
                    abstract,
                    published_at,
                    f"https://huggingface.co/papers/{identifier}",
                )
            )
            metadata = {
                key: paper[key]
                for key in ("githubRepo", "projectPage", "organization")
                if key in paper
            }
            metadata.update({"upvotes": upvotes, "num_comments": entry.get("numComments")})
            observations.append(
                PaperObservation(
                    canonical_id,
                    task.source,
                    task.period,
                    task.target,
                    rank,
                    float(upvotes) if upvotes is not None else None,
                    observed_at,
                    metadata,
                )
            )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise RadarError(f"Invalid Hugging Face payload ({type(exc).__name__})") from None
    return CrawlResult(papers, observations, html, fetched_at=observed_at)
