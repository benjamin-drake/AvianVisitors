"""Waveshare 9.7" e-Paper HAT+ (E): E Ink Spectra 6, 1120x784, 201.60 x 141.12 mm.

We dither against what the panel *actually shows* (Pimoroni's measured
Spectra 6 colours, from their inky library), so error diffusion picks inks the
way the eye will see them. Then each pixel is mapped to the panel's own colour
code. Waveshare's driver getbuffer() is bypassed: it dithers against pure RGB
and has an unused code 4 that is also black.
"""
from __future__ import annotations

from PIL import Image, ImageEnhance

WIDTH, HEIGHT = 1120, 784
ACTIVE_MM = (201.60, 141.12)

# Order matters: index i in a quantized image means INKS[i].
INKS = ("black", "white", "yellow", "red", "blue", "green")

# Measured panel colours (pimoroni/inky inky_e673.py SATURATED_PALETTE).
MEASURED_RGB = (
    (0, 0, 0),
    (161, 164, 165),
    (208, 190, 71),
    (156, 72, 75),
    (61, 59, 94),
    (58, 91, 70),
)

# Panel colour codes (waveshare epd9in7e.py: 0 black, 1 white, 2 yellow, 3 red, 5 blue, 6 green).
PANEL_CODE = (0, 1, 2, 3, 5, 6)


def _palette(colours) -> Image.Image:
    flat = [c for rgb in colours for c in rgb]
    flat += list(colours[0]) * (256 - len(colours))
    pal = Image.new("P", (1, 1))
    pal.putpalette(flat)
    return pal


def prepare(img: Image.Image, saturation: float = 1.3, contrast: float = 1.1) -> Image.Image:
    """Squeeze the image into the panel's range before dithering.

    The panel's white is a light grey and its black is the darkest thing it can
    do, so map screen white -> panel white and screen black -> panel black.
    Without this every light tone above the panel's white collapses to white,
    and pale plumage (a sparrow's belly) loses all detail. A saturation boost
    offsets how muted the inks are.
    """
    rgb = img.convert("RGB")
    if contrast != 1.0:
        rgb = ImageEnhance.Contrast(rgb).enhance(contrast)
    if saturation != 1.0:
        rgb = ImageEnhance.Color(rgb).enhance(saturation)
    lo, hi = MEASURED_RGB[0], MEASURED_RGB[1]
    channels = [band.point(lambda v, l=l, h=h: l + v * (h - l) / 255) for band, l, h in zip(rgb.split(), lo, hi)]
    return Image.merge("RGB", channels)


def quantize(img: Image.Image, **prep) -> Image.Image:
    """Floyd-Steinberg dither to the six inks. Returns a 'P' image indexed like INKS."""
    return prepare(img, **prep).quantize(palette=_palette(MEASURED_RGB), dither=Image.Dither.FLOYDSTEINBERG)


def simulated(indexed: Image.Image) -> Image.Image:
    """What the panel will look like (paper white is a light grey, inks are muted)."""
    out = indexed.copy()
    out.putpalette(_palette(MEASURED_RGB).getpalette())
    return out.convert("RGB")


def panel_buffer(indexed: Image.Image) -> bytes:
    """4 bits per pixel, two pixels per byte, as the panel's 0x10 command expects."""
    if indexed.size == (HEIGHT, WIDTH):
        indexed = indexed.rotate(90, expand=True)
    if indexed.size != (WIDTH, HEIGHT):
        raise ValueError(f"expected {WIDTH}x{HEIGHT}, got {indexed.size}")
    codes = indexed.point(list(PANEL_CODE) + [0] * (256 - len(PANEL_CODE))).tobytes()
    hi, lo = codes[0::2], codes[1::2]
    return bytes((h << 4) | l for h, l in zip(hi, lo))


def true_size(img: Image.Image, points_per_inch: float = 127, backing_scale: int = 2) -> Image.Image:
    """Upscale (nearest neighbour, so dither dots stay crisp) to real-world size.

    A 16" MacBook Pro shows 127 points per inch at 2 device pixels per point.
    The returned image is tagged 144 DPI, so Preview's 'Actual Size' gives the
    right size whichever way Preview defines 100% (1 image px = 1 screen px,
    or 'size on screen equals size printed' at macOS's 72 pt per inch).
    """
    px_per_inch = points_per_inch * backing_scale
    w = round(ACTIVE_MM[0] / 25.4 * px_per_inch)
    h = round(ACTIVE_MM[1] / 25.4 * px_per_inch)
    out = img.resize((w, h), Image.NEAREST)
    out.info["dpi"] = (72 * backing_scale, 72 * backing_scale)
    return out
