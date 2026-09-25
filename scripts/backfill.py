"""Replay daily tasks through the same CLI; deliberately does not send notifications."""

import argparse
from datetime import date, timedelta

from paper_radar.cli import main


def backfill() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("start", type=date.fromisoformat)
    parser.add_argument("end", type=date.fromisoformat)
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    if args.end < args.start:
        parser.error("end must not precede start")
    failed = False
    current = args.start
    while current <= args.end:
        failed |= bool(
            main(
                [
                    "crawl",
                    "huggingface",
                    "daily",
                    "--target",
                    current.isoformat(),
                    "--data-dir",
                    args.data_dir,
                ]
            )
        )
        current += timedelta(days=1)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(backfill())
