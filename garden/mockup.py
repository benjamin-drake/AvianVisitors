#!/usr/bin/env python3
"""Mock up the finished portrait frame with every species you've drawn, once each.

    python mockup.py                         # out/mockup/...
    python mockup.py --title "Birds of the Hour" --seed 3

Writes, for each title font, the colour composition, the Spectra 6 e-ink
simulation and a true-size copy, plus fonts.png comparing the fonts side by
side and a night version with the first font.
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw

from birddisplay import eink
from birddisplay.collage import portrait, render_live
from birddisplay.species import registry
from birddisplay.sprites import POSE_NAMES, SpriteLibrary

ROOT = Path(__file__).resolve().parent
FONTS = [
    ("Fraunces-Display.ttf", 66),
    ("Fraunces-DisplayItalic.ttf", 70),
    ("InstrumentSerif-Regular.ttf", 76),
    ("Caveat.ttf", 84),
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--title", default="Birds of the Hour")
    ap.add_argument("--seed", type=int, default=1, help="try other numbers for other arrangements")
    ap.add_argument("--arch", type=float, default=24)
    ap.add_argument("--out", type=Path, default=ROOT / "out" / "mockup")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    library = SpriteLibrary(ROOT / "art")
    reg = registry()
    species = [reg.resolve(slug.replace("_", " ").capitalize()) for slug in library.available()]
    # Plausible call counts for a busy hour, so sizes vary the way they will for real.
    counts = [14, 9, 6, 4, 3, 2, 1, 1, 1, 1]
    entries = [(s.sci, s.birdnet_name, counts[i % len(counts)]) for i, s in enumerate(species)]
    day = date(2026, 10, 28 + args.seed % 3)  # the seed just picks a different day's arrangement

    sims = []
    for i, (font, size) in enumerate(FONTS):
        style = portrait(title=args.title, title_font=font, title_size=size, title_arch=args.arch)
        img, tiles, _ = render_live(entries, day, library, style, night=False)
        stem = args.out / Path(font).stem
        img.save(f"{stem}_color.png")
        sim = eink.simulated(eink.quantize(img))
        sim.save(f"{stem}_eink.png")
        big = eink.true_size(sim.rotate(90, expand=True)).rotate(-90, expand=True)
        big.save(f"{stem}_truesize.png", dpi=big.info.get("dpi", (144, 144)))
        sims.append((Path(font).stem, sim))
        if i == 0:
            print(f"{len(tiles)} birds:")
            for t in sorted(tiles, key=lambda t: -t.w * t.h):
                name = reg.resolve(t.sci).uk_name
                print(f"  {name:14} {POSE_NAMES[t.pose]:17} {'mirrored' if t.flip else '':9} {t.w:4.0f}x{t.h:<4.0f}px")
            night, _, _ = render_live(entries, day, library, style, night=True)
            eink.simulated(eink.quantize(night)).save(args.out / "night_eink.png")

    # Side-by-side comparison of the fonts.
    w, h = sims[0][1].size
    scale = 0.5
    tw, th = int(w * scale), int(h * scale)
    sheet = Image.new("RGB", (len(sims) * (tw + 20) + 20, th + 60), (70, 70, 70))
    d = ImageDraw.Draw(sheet)
    for i, (name, sim) in enumerate(sims):
        x = 20 + i * (tw + 20)
        d.text((x, 14), name, fill=(255, 255, 255))
        sheet.paste(sim.resize((tw, th), Image.LANCZOS), (x, 40))
    sheet.save(args.out / "fonts.png")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
