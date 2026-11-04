"""Where detections come from.

- BirdNET-Pi's own SQLite database (on the mic Pi): full history, for the logs,
  the archive and the summary. Opened read-only so we never block the analyser.
- The station's recent-detections API (from the frame Pi): species heard in
  the last N hours with their count and last time heard.
- A JSON-lines file (on the Mac): fake detections for previews.
"""
from __future__ import annotations

import json
import sqlite3
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from .collage import Detection


def from_jsonl(path: Path) -> list[Detection]:
    out = []
    for line in Path(path).read_text().splitlines():
        if line.strip():
            d = json.loads(line)
            out.append(Detection(d["sci"], d.get("common", d["sci"]),
                                 datetime.fromisoformat(d["time"]), d.get("confidence", 1.0)))
    return out


def from_birds_db(db: Path, start: date | None = None, end: date | None = None) -> list[Detection]:
    """Detections between two dates inclusive (all of them if no dates)."""
    con = sqlite3.connect(f"file:{Path(db).expanduser()}?mode=ro", uri=True, timeout=10)
    try:
        sql = "SELECT Sci_Name, Com_Name, Date, Time, Confidence FROM detections"
        args: list = []
        if start or end:
            sql += " WHERE Date BETWEEN ? AND ?"
            args = [(start or date.min).isoformat(), (end or date.max).isoformat()]
        rows = con.execute(sql + " ORDER BY Date, Time", args).fetchall()
    finally:
        con.close()
    return [Detection(sci, com, datetime.fromisoformat(f"{d} {t}"), float(conf or 0))
            for sci, com, d, t, conf in rows]


@dataclass
class Recent:
    sci: str
    common: str
    count: int
    last_heard: datetime


def from_station_api(base_url: str, linger: timedelta, timeout: float = 20) -> tuple[datetime, list[Recent]]:
    """Species heard within `linger` of the station's clock, via upstream's
    /avian/api/birdnet-api.php?action=recent. Returns (station time, species)."""
    hours = max(1, -(-int(linger.total_seconds()) // 3600))
    data = _station_json(base_url, f"action=recent&hours={hours}", timeout)
    # Use the station's clock, not ours, so a drifting frame clock can't expire birds early.
    # "anchor" is the station's local time, the clock last_seen is written in; "as_of"
    # is PHP's clock, which is UTC on a stock Pi (an hour out in summer).
    if data.get("anchor"):
        now = datetime.fromisoformat(data["anchor"])
    elif data.get("as_of"):
        now = datetime.fromisoformat(data["as_of"]).astimezone().replace(tzinfo=None)
    else:
        now = datetime.now()
    out = []
    for s in data.get("species", []):
        last = datetime.fromisoformat(s["last_seen"])
        if now - last < linger:
            out.append(Recent(s["sci"], s.get("com") or s["sci"], int(s.get("n") or 1), last))
    return now, out


def _station_json(base_url: str, query: str, timeout: float) -> dict:
    url = f"{base_url.rstrip('/')}/avian/api/birdnet-api.php?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "garden-frame/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read(2_000_000))


def from_station_hours(base_url: str, start: datetime, end: datetime, timeout: float = 20) -> list[Recent]:
    """Species heard in the whole hours from `start` up to `end`, via upstream's
    ?action=hourly (per-hour counts for one calendar day, its top 30 species).
    last_heard is the start of the last hour the species was heard in."""
    totals: dict[str, list] = {}
    day = start.date()
    while day <= end.date():
        data = _station_json(base_url, f"action=hourly&date={day}&limit=30", timeout)
        for s in data.get("species", []):
            for h in s.get("hours", []):
                t = datetime.combine(day, datetime.min.time()).replace(hour=int(h["hour"]))
                if start <= t < end:
                    e = totals.setdefault(s["sci"], [s.get("com") or s["sci"], 0, t])
                    e[1] += int(h["n"])
                    e[2] = max(e[2], t)
        day += timedelta(days=1)
    return [Recent(sci, com, n, last) for sci, (com, n, last) in totals.items()]


def species_totals(db: Path) -> list[tuple[str, str, int, datetime, datetime]]:
    """(sci, common, detections, first heard, last heard) for every species ever, via SQL."""
    con = sqlite3.connect(f"file:{Path(db).expanduser()}?mode=ro", uri=True, timeout=10)
    try:
        rows = con.execute(
            "SELECT Sci_Name, MAX(Com_Name), COUNT(*), MIN(Date||' '||Time), MAX(Date||' '||Time) "
            "FROM detections GROUP BY Sci_Name").fetchall()
    finally:
        con.close()
    return [(s, c, n, datetime.fromisoformat(a), datetime.fromisoformat(b)) for s, c, n, a, b in rows]


def species_before(db: Path, day: date) -> set[str]:
    con = sqlite3.connect(f"file:{Path(db).expanduser()}?mode=ro", uri=True, timeout=10)
    try:
        return {r[0] for r in con.execute("SELECT DISTINCT Sci_Name FROM detections WHERE Date < ?",
                                          (day.isoformat(),))}
    finally:
        con.close()
