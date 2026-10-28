#!/usr/bin/env python3
"""Compare dithering styles on the mock-up: full frames, then a close-up of the texture.

    python mockup.py && python dither_compare.py    # -> out/mockup/dither_compare.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from birddisplay import eink

ROOT = Path(__file__).resolve().parent
VARIANTS = [
    ("A  Floyd-Steinberg, boosted (current)", dict(method="floyd", saturation=1.3, contrast=1.1)),
    ("B  Floyd-Steinberg, natural colour", dict(method="floyd", saturation=1.0, contrast=1.0)),
    ("C  Atkinson", dict(method="atkinson", saturation=1.15, contrast=1.05)),
    ("D  Ordered (Bayer)", dict(method="ordered", saturation=1.15, contrast=1.05)),
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", type=Path, default=ROOT / "out/mockup/Fraunces-Display_color.png")
    ap.add_argument("--zoom", type=int, nargs=4, default=(250, 430, 560, 740),
                    help="close-up box x0 y0 x1 y1 (pixels in the 784x1120 frame)")
    args = ap.parse_args()

    src = Image.open(args.image).convert("RGB")
    panels = [("Original artwork (screen)", src)]
    for name, opts in VARIANTS:
        sim = eink.simulated(eink.quantize(src, **opts))
        sim.save(args.image.parent / f"dither_{name[0]}.png")
        panels.append((name, sim))

    scale = 0.5
    tw, th = int(src.width * scale), int(src.height * scale)
    zw = tw
    crop = tuple(args.zoom)
    zh = int(zw * (crop[3] - crop[1]) / (crop[2] - crop[0]))
    gap, label = 18, 30
    sheet = Image.new("RGB", (len(panels) * (tw + gap) + gap, label + th + gap + label + zh + gap), (60, 60, 60))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=15)
    except TypeError:
        font = ImageFont.load_default()
    for i, (name, im) in enumerate(panels):
        x = gap + i * (tw + gap)
        d.text((x, 8), name, fill=(255, 255, 255), font=font)
        sheet.paste(im.resize((tw, th), Image.LANCZOS), (x, label))
        # Close-up at enlarged 1:1 pixels (nearest neighbour), so the dither texture is visible.
        y = label + th + gap
        d.text((x, y + 6), "close-up", fill=(200, 200, 200), font=font)
        sheet.paste(im.crop(crop).resize((zw, zh), Image.NEAREST), (x, y + label))
    out = args.image.parent / "dither_compare.png"
    sheet.save(out)
    print(f"-> {out}")


if __name__ == "__main__":
    main()
