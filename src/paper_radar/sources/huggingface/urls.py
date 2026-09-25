from paper_radar.core.tasks import CrawlTask, Period


def build_url(task: CrawlTask) -> str:
    routes = {Period.DAILY: "date", Period.WEEKLY: "week", Period.MONTHLY: "month"}
    return f"https://huggingface.co/papers/{routes[task.period]}/{task.target}"
