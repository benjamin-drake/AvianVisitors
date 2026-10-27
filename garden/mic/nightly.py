#!/usr/bin/env python3
"""Mic Pi, just after midnight: yesterday's archive collage, hourly log and drawing queue.

    python3 garden/mic/nightly.py               # yesterday
    python3 garden/mic/nightly.py --day 2026-10-27

Writes into ~/garden-data/:
    archive/2026-10-27.png         the day's collage (full colour, for email and viewing)
    archive/2026-10-27_eink.png    the same, as it would look on the panel
    log/2026-10.csv                each hour's species and counts (one file per month)
    missing_art.csv                species heard that have no art yet, most-heard first

Everything is recomputed from BirdNET-Pi's database, so re-running a day is safe.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from birddisplay import eink, logbook, settings, sources  # noqa: E402
from birddisplay.collage import Style, render_archive  # noqa: E402
from birddisplay.species import registry  # noqa: E402
from birddisplay.sprites import SpriteLibrary  # noqa: E402


def missing_rows(db: str, library: SpriteLibrary) -> list[dict]:
    reg = registry()
    rows = [{"species": reg.resolve(sci, com).uk_name, "scientific_name": sci, "detections": n,
             "first_heard": f"{first:%Y-%m-%d %H:%M}", "last_heard": f"{last:%Y-%m-%d %H:%M}"}
            for sci, com, n, first, last in sources.species_totals(db) if not library.has(sci)]
    return sorted(rows, key=lambda r: -r["detections"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", type=date.fromisoformat, default=date.today() - timedelta(days=1))
    ap.add_argument("--config", type=Path)
    args = ap.parse_args()

    cfg = settings.load(args.config)
    data = Path(cfg["data_dir"])
    library = SpriteLibrary(Path(cfg["art_dir"]))
    detections = sources.from_birds_db(cfg["birds_db"], args.day, args.day)

    frame = render_archive(detections, args.day, library, Style())
    (data / "archive").mkdir(parents=True, exist_ok=True)
    frame.image.save(data / "archive" / f"{args.day}.png", optimize=True)
    eink.simulated(eink.quantize(frame.image)).save(data / "archive" / f"{args.day}_eink.png", optimize=True)

    log = logbook.write_hourly_log(detections, args.day, data / "log")
    todo = logbook.write_missing_art([], library, data / "missing_art.csv",
                                     rows=missing_rows(cfg["birds_db"], library))
    print(f"{args.day}: {len(detections)} detections, {len(frame.tiles)} birds in the archive")
    print(f"-> {data / 'archive' / f'{args.day}.png'}\n-> {log}\n-> {todo}")


if __name__ == "__main__":
    main()
