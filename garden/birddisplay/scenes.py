"""Which picture the frame shows, so the screen is never empty during the day.

main_view "today" (the default):
1. Birds heard today              -> "Birds of Today", the last hour's drawn larger
2. else birds heard yesterday     -> "Birds of Yesterday" (before the first bird)

main_view "hour" (the original design):
1. Birds heard in the last hour   -> "Birds of the Hour"
2. else birds heard today         -> "Birds of Today"
3. else birds heard yesterday     -> "Birds of Yesterday"

Only species with art count. At most max_birds are drawn: the last hour's
first, then the most heard. "Today" is a bird day that starts at on_time
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
    recent: frozenset = frozenset()  # species heard in the last hour: drawn larger


def bird_day_start(now: datetime, on_time: str) -> datetime:
    h, m = map(int, on_time.split(":"))
    start = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return start if now >= start else start - timedelta(days=1)


def in_hours(now: datetime, on: str, off: str) -> bool:
    """True between on and off ("05:00", "23:00"); handles windows that cross midnight."""
    t = now.strftime("%H:%M")
    return on <= t < off if on < off else t >= on or t < off


def pick(recent: list[Recent], now: datetime, cfg: dict, drawable: Callable[[str], bool],
         fetch: Fetch) -> Scene:
    """recent: the last hour's species (pass [] to skip straight to the day views)."""
    start = bird_day_start(now, cfg["on_time"])

    now_scis = {r.sci for r in recent}

    def entries(rs):
        """Species with art, capped (the last hour's first, then the most heard),
        followed by those without art, which are never drawn but feed "no art yet"."""
        rs = sorted(rs, key=lambda r: (r.sci not in now_scis, -r.count))
        art = [r for r in rs if drawable(r.sci)][:cfg.get("max_birds", 20)]
        return [(r.sci, r.common, r.count) for r in art + [r for r in rs if not drawable(r.sci)]]

    def any_art(rs):
        return any(drawable(r.sci) for r in rs)

    if cfg.get("main_view", "today") == "today":
        today = fetch(start, now)
        if any_art(today):
            shown = entries(today)
            return Scene("today", cfg["title_today"], shown, start.date(),
                         frozenset(e[0] for e in shown) & frozenset(now_scis))
        yesterday = fetch(start - timedelta(days=1), start)
        if any_art(yesterday):
            return Scene("yesterday", cfg["title_yesterday"], entries(yesterday),
                         start.date() - timedelta(days=1))
        return Scene("today", cfg["title_today"], [], start.date())

    if any_art(recent):
        return Scene("hour", cfg["title"], entries(recent), start.date())
    today = fetch(start, now)
    if any_art(today):
        return Scene("today", cfg["title_today"], entries(today), start.date())
    yesterday = fetch(start - timedelta(days=1), start)
    if any_art(yesterday):
        return Scene("yesterday", cfg["title_yesterday"], entries(yesterday), start.date() - timedelta(days=1))
    return Scene("hour", cfg["title"], [], start.date())
