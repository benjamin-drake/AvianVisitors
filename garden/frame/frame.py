#!/usr/bin/env python3
"""Frame Pi: every 15 minutes, redraw the panel if the birds on screen have changed.

    python3 garden/frame/frame.py              # what the timer runs
    python3 garden/frame/frame.py --force      # redraw now regardless
    python3 garden/frame/frame.py --preview    # render to /dev/shm/garden-frame/frame.png, panel untouched

Each run asks the mic Pi which species were heard in the last 60 minutes
(upstream's /avian/api/birdnet-api.php?action=recent), renders the collage,
and compares its signature (date, day/night, species on screen) with the
last drawn one. Only a change, or the daily heal, refreshes the panel.

If the mic Pi can't be reached the panel keeps its last picture; after 3
hours without contact a small "no signal" mark is drawn so it's clear the
frame isn't live. Logs: journalctl -u garden-frame
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import ImageDraw  # noqa: E402

from birddisplay import eink, settings, sources  # noqa: E402
from birddisplay.collage import render_live, style_for  # noqa: E402
from birddisplay.sprites import SpriteLibrary  # noqa: E402
from birddisplay.sun import is_night  # noqa: E402

# RAM, not the SD card: the latest render (scp it to check what's on the wall) and the lock.
RUN = Path(os.environ.get("RUNTIME_DIRECTORY", "/dev/shm/garden-frame"))
STALE_AFTER = 3 * 3600


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    os.replace(tmp, path)  # atomic: a power cut can't leave half a file


def push(indexed, rotate: int, fake: bool = False) -> None:
    if rotate == 180:
        indexed = indexed.rotate(180)
    if fake:  # testing off the Pi: write the exact bytes the panel would get
        (RUN / "panel.bin").write_bytes(eink.panel_buffer(indexed))
        return
    from epd9in7e import EPD  # only importable on the Pi
    epd = EPD()
    try:
        epd.init()
        epd.display(eink.panel_buffer(indexed))
        epd.sleep()
    finally:
        epd.close()


def no_signal_mark(img) -> None:
    """A small hollow circle in the corner: 'not live'."""
    d = ImageDraw.Draw(img)
    w, h = img.size
    d.ellipse((w - 34, h - 34, w - 14, h - 14), outline=(160, 160, 160), width=3)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--config", type=Path)
    ap.add_argument("--fake-panel", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    cfg = settings.load(args.config)
    data = Path(cfg["data_dir"])
    state_path = data / "frame-state.json"
    RUN.mkdir(parents=True, exist_ok=True)

    # One run at a time: a manual --force colliding with the timer would
    # interleave two refreshes on the panel.
    lock = open(RUN / ".lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another run is in progress; skipping")
        return 0

    state = load_state(state_path)
    linger = timedelta(minutes=cfg["linger_minutes"])
    library = SpriteLibrary(Path(cfg["art_dir"]))
    now_ts = time.time()

    try:
        station_now, recent = sources.from_station_api(cfg["station_url"], linger)
        state["last_contact"] = now_ts
        stale = False
    except Exception as e:  # network, mic Pi rebooting, etc.
        print(f"mic Pi unreachable ({e})")
        since = now_ts - state.get("last_contact", now_ts)
        if since < STALE_AFTER or state.get("stale_drawn"):
            print("keeping the current picture")
            save_state(state_path, state)
            return 0
        print(f"no contact for {since / 3600:.1f} h: marking the frame as not live")
        station_now, recent, stale = datetime.now(), [], True

    night = is_night(station_now, cfg["latitude"], cfg["longitude"])
    entries = [(r.sci, r.common, r.count) for r in recent]
    image, tiles, sig = render_live(entries, station_now.date(), library, style_for(cfg), night)
    if stale:
        no_signal_mark(image)
        sig = "stale"
    missing = sorted(r.common for r in recent if not library.has(r.sci))

    heal_due = now_ts - state.get("last_refresh", 0) >= cfg["heal_hours"] * 3600
    changed = sig != state.get("signature")
    summary = ", ".join(t.common for t in tiles) or "(no birds)"
    if not (changed or heal_due or args.force or args.preview):
        print(f"no change: {summary}")
        return 0

    indexed = eink.quantize(image)
    eink.simulated(indexed).save(RUN / "frame.png")
    print(f"{'night' if night else 'day'}: {summary}" + (f"; no art yet: {', '.join(missing)}" if missing else ""))
    if args.preview:
        print(f"preview -> {RUN / 'frame.png'}")
        return 0

    t0 = time.monotonic()
    try:
        push(indexed, cfg["rotate"], args.fake_panel)
    except Exception as e:
        print(f"panel update failed: {e}", file=sys.stderr)
        return 1  # state untouched, so the next run tries again
    print(f"panel updated in {time.monotonic() - t0:.0f}s ({'changed' if changed else 'forced' if args.force else 'daily heal'})")
    state.update(signature=sig, last_refresh=now_ts, stale_drawn=stale)
    save_state(state_path, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
