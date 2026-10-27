"""Plain-file records: what was heard each hour, what still needs drawing, and the
morning summary. All of it is recomputed from the detections, so nothing is
lost if a file is deleted, and the Pi writes each file once (small SD writes)."""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

from .collage import Detection
from .species import registry
from .sprites import SpriteLibrary
from .sun import sun_times

HOURLY_FIELDS = ["date", "hour", "species", "scientific_name", "detections", "best_confidence"]


def hourly_rows(detections: Iterable[Detection], day: date) -> list[dict]:
    reg = registry()
    buckets: dict[tuple[int, str], list[Detection]] = defaultdict(list)
    for d in detections:
        if d.time.date() == day:
            buckets[(d.time.hour, d.sci)].append(d)
    rows = []
    for (hour, sci), ds in sorted(buckets.items(), key=lambda kv: (kv[0][0], -len(kv[1]), kv[0][1])):
        rows.append({
            "date": day.isoformat(),
            "hour": f"{hour:02d}:00",
            "species": reg.resolve(sci, ds[0].common).uk_name,
            "scientific_name": sci,
            "detections": len(ds),
            "best_confidence": f"{max(d.confidence for d in ds):.2f}",
        })
    return rows


def write_hourly_log(detections, day: date, log_dir: Path) -> Path:
    """One CSV per month (log/2026-10.csv); opens straight into Excel or Numbers.
    Rewrites that day's rows, so re-running a day never duplicates it."""
    path = Path(log_dir) / f"{day:%Y-%m}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    keep = []
    if path.exists():
        with open(path, newline="") as f:
            keep = [r for r in csv.DictReader(f) if r["date"] != day.isoformat()]
    rows = sorted(keep + hourly_rows(detections, day), key=lambda r: (r["date"], r["hour"]))
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HOURLY_FIELDS)
        w.writeheader()
        w.writerows(rows)
    return path


def missing_art(detections: Iterable[Detection], library: SpriteLibrary) -> list[dict]:
    """Species heard that have no art, most-heard first: your drawing queue."""
    reg = registry()
    seen: dict[str, dict] = {}
    for d in detections:
        if library.has(d.sci):
            continue
        row = seen.setdefault(d.sci, {"species": reg.resolve(d.sci, d.common).uk_name,
                                      "scientific_name": d.sci, "detections": 0,
                                      "first_heard": d.time, "last_heard": d.time})
        row["detections"] += 1
        row["first_heard"] = min(row["first_heard"], d.time)
        row["last_heard"] = max(row["last_heard"], d.time)
    rows = sorted(seen.values(), key=lambda r: -r["detections"])
    for r in rows:
        r["first_heard"] = r["first_heard"].strftime("%Y-%m-%d %H:%M")
        r["last_heard"] = r["last_heard"].strftime("%Y-%m-%d %H:%M")
    return rows


def write_missing_art(detections, library: SpriteLibrary, path: Path, rows: list[dict] | None = None) -> Path:
    rows = missing_art(detections, library) if rows is None else rows
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["species", "scientific_name", "detections", "first_heard", "last_heard"])
        w.writeheader()
        w.writerows(rows)
    return path


def daily_summary(detections: list[Detection], day: date, library: SpriteLibrary,
                  lat: float = 52.77, lon: float = -0.89, seen_before: set[str] | None = None) -> str:
    """seen_before: species heard on earlier days (to flag NEW); worked out from
    `detections` if not given."""
    """Plain text, short enough for a text message's first screen, full enough for email."""
    reg = registry()
    today = [d for d in detections if d.time.date() == day]
    if not today:
        return f"{day:%A %-d %B}: no birds heard. Is the microphone OK?"
    counts = Counter(d.sci for d in today)
    first = {}
    for d in sorted(today, key=lambda d: d.time):
        first.setdefault(d.sci, d.time)
    earlier = seen_before if seen_before is not None else {d.sci for d in detections if d.time.date() < day}
    name = lambda sci: reg.resolve(sci).uk_name  # noqa: E731
    by_hour = Counter(d.time.hour for d in today)
    busiest = max(by_hour, key=by_hour.get)

    lines = [f"Birds heard on {day:%A %-d %B}: {len(counts)} species, {len(today)} detections.", ""]
    for sci, n in counts.most_common():
        flags = []
        if earlier and sci not in earlier:
            flags.append("NEW")
        if not library.has(sci):
            flags.append("no art yet")
        tail = f"  ({', '.join(flags)})" if flags else ""
        lines.append(f"  {name(sci)}: {n}, first at {first[sci]:%H:%M}{tail}")
    lines += ["", f"Busiest hour: {busiest:02d}:00-{busiest + 1:02d}:00 ({by_hour[busiest]} detections)."]
    # From an hour before sunrise, so owls calling in the dark don't count as the dawn chorus.
    rise, _ = sun_times(day, lat, lon)
    chorus_from = rise.astimezone().replace(tzinfo=None) - timedelta(hours=1) if rise else \
        datetime.combine(day, datetime.min.time()).replace(hour=4)
    dawn = [d for d in today if chorus_from <= d.time and d.time.hour < 12]
    if dawn:
        d0 = min(dawn, key=lambda d: d.time)
        lines.append(f"Dawn chorus began with: {name(d0.sci)} at {d0.time:%H:%M}.")
    return "\n".join(lines)


def short_summary(detections: list[Detection], day: date) -> str:
    """One line for SMS / push."""
    reg = registry()
    counts = Counter(d.sci for d in detections if d.time.date() == day)
    top = ", ".join(reg.resolve(s).uk_name for s, _ in counts.most_common(4))
    return f"{day:%a %-d %b}: {len(counts)} species. Most heard: {top}." if counts else f"{day:%a %-d %b}: no birds heard."
