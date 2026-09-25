from dataclasses import replace

from paper_radar.core.models import CrawlResult, Paper, PaperObservation
from paper_radar.core.tasks import CrawlTask


def deduplicate(task: CrawlTask, result: CrawlResult) -> CrawlResult:
    papers: dict[str, Paper] = {}
    for paper in result.papers:
        papers.setdefault(paper.canonical_id, paper)
    observations: dict[str, PaperObservation] = {}
    for observation in result.observations:
        if (observation.source, observation.period, observation.target) != (
            task.source,
            task.period,
            task.target,
        ) or observation.paper_id not in papers:
            raise ValueError(
                "Observation does not belong to its task or references a missing paper"
            )
        previous = observations.get(observation.paper_id)
        if previous is None or observation.rank < previous.rank:
            observations[observation.paper_id] = observation
    if set(papers) != set(observations):
        raise ValueError("Every paper must have an observation")
    return replace(result, papers=list(papers.values()), observations=list(observations.values()))
