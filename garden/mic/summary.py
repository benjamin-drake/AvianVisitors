#!/usr/bin/env python3
"""Mic Pi, each morning: send yesterday's summary (with the archive collage attached).

    python3 garden/mic/summary.py              # yesterday, sends if notify.txt is set up
    python3 garden/mic/summary.py --dry-run    # print it instead

Delivery uses Apprise, which BirdNET-Pi already ships. Put one Apprise URL per
line in ~/garden-data/notify.txt, for example:

    mailtos://you%40gmail.com:APP_PASSWORD@gmail.com?to=you@example.com     email (Gmail app password)
    ntfy://garden-birds-XXXX                                                free push via the ntfy app
    tgram://BOT_TOKEN/CHAT_ID                                               Telegram
    twilio://SID:TOKEN@+44SENDER/+44YOURNUMBER                              SMS (paid, short version sent)

SMS gets the one-line version; everything else gets the full text and the picture.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from birddisplay import logbook, settings, sources  # noqa: E402
from birddisplay.sprites import SpriteLibrary  # noqa: E402

SMS_SCHEMES = ("twilio://", "sns://", "clicksend://", "messagebird://", "vonage://", "nexmo://", "d7sms://")


def send(apprise: str, urls: list[str], title: str, body: str, attach: list[Path]) -> bool:
    cmd = [apprise, "-vv", "-t", title, "-b", body]
    for a in attach:
        if a.exists():
            cmd += ["--attach", str(a)]
    r = subprocess.run(cmd + urls, capture_output=True, text=True, timeout=120)
    if r.returncode:
        print(r.stdout[-2000:], r.stderr[-2000:], file=sys.stderr)
    return r.returncode == 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", type=date.fromisoformat, default=date.today() - timedelta(days=1))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--config", type=Path)
    args = ap.parse_args()

    cfg = settings.load(args.config)
    data = Path(cfg["data_dir"])
    library = SpriteLibrary(Path(cfg["art_dir"]))
    detections = sources.from_birds_db(cfg["birds_db"], args.day, args.day)
    text = logbook.daily_summary(detections, args.day, library, cfg["latitude"], cfg["longitude"],
                                 seen_before=sources.species_before(cfg["birds_db"], args.day))
    short = logbook.short_summary(detections, args.day)
    (data / "summaries").mkdir(parents=True, exist_ok=True)
    (data / "summaries" / f"{args.day}.txt").write_text(text + "\n")

    notify = Path(cfg["notify_urls"])
    urls = [u.strip() for u in notify.read_text().splitlines()
            if u.strip() and not u.startswith("#")] if notify.exists() else []
    if args.dry_run or not urls:
        print(text, "\n\nSMS:", short)
        if not urls:
            print(f"\n(no delivery set up: add Apprise URLs to {notify})")
        return

    sms = [u for u in urls if u.startswith(SMS_SCHEMES)]
    rich = [u for u in urls if u not in sms]
    attach = [data / "archive" / f"{args.day}.png", data / "log" / f"{args.day:%Y-%m}.csv"]
    ok = True
    if rich:
        ok &= send(cfg["apprise"], rich, cfg["summary_title"], text, attach)
    if sms:
        ok &= send(cfg["apprise"], sms, "Birds", short, [])
    print("sent" if ok else f"delivery failed (see above); the summary is saved in {data / 'summaries'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
