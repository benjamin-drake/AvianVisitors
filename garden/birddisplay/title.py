"""The frame's title, set along a gentle arch, like the lettering on an old plate.

    draw_title(img, "Birds of the Hour", font="Fraunces-Display.ttf", top=24, arch=22)

Each letter is drawn on its own, rotated to follow a circle whose centre sits
below the text. `arch` is the total angle the title spans in degrees: 0 is a
straight line, around 20-30 is a gentle bow, 60 or more is a strong rainbow.
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = Path(__file__).resolve().parent.parent / "fonts"


def load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = Path(name)
    return ImageFont.truetype(str(path if path.is_absolute() else FONTS / name), size)


def title_height(font_name: str, size: int, text: str, width: int, arch: float) -> int:
    """Vertical space the arched title needs, so the layout can keep birds out of it."""
    font = load_font(font_name, size)
    ascent, descent = font.getmetrics()
    span = font.getlength(text)
    if arch <= 0:
        return ascent + descent
    radius = span / math.radians(arch)
    sag = radius * (1 - math.cos(math.radians(arch) / 2))  # how far the ends drop
    return int(ascent + descent + sag + 0.12 * size)


def draw_title(img: Image.Image, text: str, font_name: str, size: int, top: int,
               arch: float = 22, colour=(0, 0, 0), letter_spacing: float = 0.02) -> int:
    """Draw `text` centred near the top of `img`, arched. Returns the y just below it."""
    font = load_font(font_name, size)
    ascent, descent = font.getmetrics()
    track = letter_spacing * size
    # Per-letter advance including kerning: length of the prefix with and without it.
    advances = [font.getlength(text[:i + 1]) - font.getlength(text[:i]) + track for i in range(len(text))]
    span = sum(advances) - track
    cx = img.width / 2

    if arch <= 0:
        ImageDraw.Draw(img).text((cx - span / 2, top), text, font=font, fill=colour)
        return top + ascent + descent

    radius = span / math.radians(arch)
    cy = top + ascent * 0.5 + radius          # circle centre, below the title
    angle = -math.radians(arch) / 2           # start at the left end
    cell = int(size * 2)
    for ch, adv in zip(text, advances):
        mid = angle + (adv - track) / 2 / radius
        if ch != " ":
            glyph = Image.new("RGBA", (cell, cell), (0, 0, 0, 0))
            d = ImageDraw.Draw(glyph)
            w = font.getlength(ch)
            # Draw so the glyph's baseline-centre sits at the cell centre.
            d.text((cell / 2 - w / 2, cell / 2 - ascent * 0.5), ch, font=font, fill=tuple(colour) + (255,))
            glyph = glyph.rotate(-math.degrees(mid), resample=Image.BICUBIC)
            x = cx + radius * math.sin(mid)
            y = cy - radius * math.cos(mid)
            img.paste(glyph, (round(x - cell / 2), round(y - cell / 2)), glyph)
        angle += adv / radius
    sag = radius * (1 - math.cos(math.radians(arch) / 2))
    return int(top + ascent + descent + sag)
