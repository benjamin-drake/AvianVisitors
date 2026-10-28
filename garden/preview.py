#!/usr/bin/env python3
"""Preview the Waveshare 9.7" frame on the Mac from a detections file.

    python preview.py detections.jsonl --at 2026-10-27T08:30     # the screen at one moment
    python preview.py detections.jsonl --day 2026-10-27          # every 15 min + contact sheet
    python preview.py detections.jsonl --archive 2026-10-27      # the midnight collage
    python preview.py detections.jsonl --logs 2026-10-27         # hourly CSV, drawing queue, summary

Each screen render writes, into out/:
    *_color.png      the composition before dithering
    *_eink.png       dithered to Spectra 6 and shown in the panel's measured colours (1120x784)
    *_truesize.png   the e-ink image at real size: open in Preview, View > Actual Size

--stand-ins lets species without art borrow existing art, to see how a busy
screen packs before you've drawn them. Those renders are named stress_*.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw

from birddisplay import eink, logbook
from birddisplay.collage import Detection, render_archive, render_screen, style_for
from birddisplay.sprites import SpriteLibrary
from birddisplay.sun import is_night

ROOT = Path(__file__).resolve().parent


def load_detections(path: Path) -> list[Detection]:
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            d = json.loads(line)
            out.append(Detection(d["sci"], d.get("common", d["sci"]),
                                 datetime.fromisoformat(d["time"]), d.get("confidence", 1.0)))
    return out


def save_all(img: Image.Image, stem: Path, true_size: bool = True) -> Image.Image:
    stem.parent.mkdir(parents=True, exist_ok=True)
    img.save(f"{stem}_color.png")
    sim = eink.simulated(eink.quantize(img))
    sim.save(f"{stem}_eink.png")
    if true_size:
        big = eink.true_size(sim)
        big.save(f"{stem}_truesize.png", dpi=big.info["dpi"])
    return sim


def contact_sheet(frames, cols: int = 8, scale: float = 0.2) -> Image.Image:
    tw, th = int(eink.WIDTH * scale), int(eink.HEIGHT * scale)
    lab = 14
    rows = -(-len(frames) // cols)
    sheet = Image.new("RGB", (cols * (tw + 6) + 6, rows * (th + lab + 6) + 6), (90, 90, 90))
    draw = ImageDraw.Draw(sheet)
    for i, (label, im) in enumerate(frames):
        x, y = 6 + (i % cols) * (tw + 6), 6 + (i // cols) * (th + lab + 6)
        draw.text((x, y), label, fill=(255, 255, 255))
        sheet.paste(im.resize((tw, th), Image.LANCZOS), (x, y + lab))
    return sheet


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("detections", type=Path)
    when = ap.add_mutually_exclusive_group(required=True)
    when.add_argument("--at", type=datetime.fromisoformat)
    when.add_argument("--day", type=date.fromisoformat)
    when.add_argument("--archive", type=date.fromisoformat)
    when.add_argument("--logs", type=date.fromisoformat)
    ap.add_argument("--every", type=int, default=15, help="minutes between frames with --day")
    ap.add_argument("--mode", choices=("auto", "day", "night"), default="auto")
    ap.add_argument("--stand-ins", action="store_true")
    ap.add_argument("--out", type=Path, default=ROOT / "out")
    args = ap.parse_args()

    cfg = json.loads((ROOT / "config.json").read_text())
    library = SpriteLibrary(ROOT / cfg["art_dir"], stand_ins=args.stand_ins)
    linger = timedelta(minutes=cfg["linger_minutes"])
    style = style_for(cfg)
    archive_style = style_for({**cfg, "title": cfg.get("archive_title", "Birds of {date}").replace(
        "{date}", f"{args.archive.day} {args.archive:%B}") if args.archive else ""})
    detections = load_detections(args.detections)
    prefix = "stress_" if args.stand_ins else ""
    night_at = (lambda t: args.mode == "night") if args.mode != "auto" else \
        (lambda t: is_night(t, cfg["latitude"], cfg["longitude"]))

    if args.logs:
        log = logbook.write_hourly_log(detections, args.logs, args.out / "log")
        todo = logbook.write_missing_art(detections, library, args.out / "missing_art.csv")
        summary = logbook.daily_summary(detections, args.logs, library, cfg["latitude"], cfg["longitude"])
        (args.out / f"summary_{args.logs}.txt").write_text(summary + "\n")
        print(summary, "\n")
        print("SMS version:", logbook.short_summary(detections, args.logs))
        print(f"-> {log}\n-> {todo}\n-> {args.out / f'summary_{args.logs}.txt'}")
        return

    if args.archive:
        frame = render_archive(detections, args.archive, library, archive_style)
        stem = args.out / "archive" / f"{prefix}{args.archive}"
        save_all(frame.image, stem)
        print(f"{len(frame.tiles)} species -> {stem}_*.png")
        return

    if args.at:
        t0 = time.perf_counter()
        frame = render_screen(detections, args.at, library, style, night_at(args.at), linger)
        ms = (time.perf_counter() - t0) * 1000
        stem = args.out / f"{prefix}screen_{args.at:%Y%m%d_%H%M}"
        save_all(frame.image, stem)
        shown = ", ".join(f"{t.common} (pose {t.pose + 1}{', mirrored' if t.flip else ''})" for t in frame.tiles)
        print(f"{'night' if frame.night else 'day'}, rendered in {ms:.0f} ms: {shown or '(empty)'}")
        if frame.missing:
            print("heard but no art yet:", ", ".join(v.common for v in frame.missing))
        print(f"-> {stem}_*.png")
        return

    frames, last_sig, redraws = [], None, 0
    t = datetime.combine(args.day, datetime.min.time())
    while t.date() == args.day:
        frame = render_screen(detections, t, library, style, night_at(t), linger)
        changed = frame.signature != last_sig
        redraws += changed
        last_sig = frame.signature
        sim = save_all(frame.image, args.out / f"{prefix}frames" / f"{t:%H%M}", true_size=False)
        frames.append((f"{t:%H:%M} {'N' if frame.night else 'D'} {len(frame.tiles)}{' *' if changed else ''}", sim))
        t += timedelta(minutes=args.every)
    path = args.out / f"{prefix}contact_{args.day}.png"
    contact_sheet(frames).save(path)
    print(f"{len(frames)} checks, {redraws} panel redraws (marked * on the sheet) -> {path}")


if __name__ == "__main__":
    main()
