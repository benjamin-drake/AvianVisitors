"""Which picture the frame shows, so the screen is never empty during the day:

1. Birds heard in the last hour   -> "Birds of the Hour"
2. else birds heard today         -> "Birds of Today"
3. else birds heard yesterday     -> "Birds of Yesterday"

Only species with art count. "Today" is a bird day that starts at on_time
(05:00), not midnight, so an owl at 2 a.m. joins the evening before: the
05:00 "Birds of Yesterday" is then the whole of the last day and night.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable

from .sources import Recent

Fetch = Callable[[datetime, datetime], list[Recent]]  # species heard from start up to end


@dataclass
class Scene:
    view: str     # "hour", "today" or "yesterday"
    title: str
    entries: list  # (sci, common, count)
    day: date      # the bird day shown; seeds the arrangement


def bird_day_start(now: datetime, on_time: str) -> datetime:
    h, m = map(int, on_time.split(":"))
    start = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return start if now >= start else start - timedelta(days=1)


def pick(recent: list[Recent], now: datetime, cfg: dict, drawable: Callable[[str], bool],
         fetch: Fetch) -> Scene:
    """recent: the last hour's species (pass [] to skip straight to the day views)."""
    start = bird_day_start(now, cfg["on_time"])

    def entries(rs):
        return [(r.sci, r.common, r.count) for r in rs]

    def any_art(rs):
        return any(drawable(r.sci) for r in rs)

    if any_art(recent):
        return Scene("hour", cfg["title"], entries(recent), start.date())
    today = fetch(start, now)
    if any_art(today):
        return Scene("today", cfg["title_today"], entries(today), start.date())
    yesterday = fetch(start - timedelta(days=1), start)
    if any_art(yesterday):
        return Scene("yesterday", cfg["title_yesterday"], entries(yesterday), start.date() - timedelta(days=1))
    return Scene("hour", cfg["title"], [], start.date())
