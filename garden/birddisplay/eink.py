"""Waveshare 9.7" e-Paper HAT+ (E): E Ink Spectra 6, 1120x784, 201.60 x 141.12 mm.

We dither against what the panel *actually shows* (Pimoroni's measured
Spectra 6 colours, from their inky library), so error diffusion picks inks the
way the eye will see them. Then each pixel is mapped to the panel's own colour
code. Waveshare's driver getbuffer() is bypassed: it dithers against pure RGB
and has an unused code 4 that is also black.
"""
from __future__ import annotations

import numpy as np
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


def prepare(img: Image.Image, saturation: float = 1.0, contrast: float = 1.0) -> Image.Image:
    """Squeeze the image into the panel's range before dithering.

    The panel's white is a light grey and its black is the darkest thing it can
    do, so map screen white -> panel white and screen black -> panel black.
    Without this every light tone above the panel's white collapses to white,
    and pale plumage (a sparrow's belly) loses all detail.

    Saturation/contrast default to 1.0 ("natural", style B in dither_compare.py):
    with detailed painted art a boost (style A: 1.3 / 1.1) pushes browns pink.
    Set dither_saturation / dither_contrast in config.json to change it.
    """
    rgb = img.convert("RGB")
    if contrast != 1.0:
        rgb = ImageEnhance.Contrast(rgb).enhance(contrast)
    if saturation != 1.0:
        rgb = ImageEnhance.Color(rgb).enhance(saturation)
    lo, hi = MEASURED_RGB[0], MEASURED_RGB[1]
    channels = [band.point(lambda v, l=l, h=h: l + v * (h - l) / 255) for band, l, h in zip(rgb.split(), lo, hi)]
    return Image.merge("RGB", channels)


def quantize(img: Image.Image, method: str = "floyd", **prep) -> Image.Image:
    """Dither to the six inks. Returns a 'P' image indexed like INKS.

    floyd     Floyd-Steinberg: passes on all of each pixel's colour error. Finest
              shading, but busy speckle in mid-tones (Pillow, fast).
    atkinson  Passes on only 3/4 of the error: cleaner flat areas and crisper
              edges, slightly lighter and less detailed shading.
    ordered   A fixed 8x8 Bayer pattern instead of spreading error: an even,
              print-like texture with no wandering speckle.
    """
    prepared = prepare(img, **prep)
    if method == "floyd":
        return prepared.quantize(palette=_palette(MEASURED_RGB), dither=Image.Dither.FLOYDSTEINBERG)
    rgb = np.asarray(prepared, dtype=np.float32)
    if method == "atkinson":
        idx = _atkinson(rgb)
    elif method == "ordered":
        idx = _ordered(rgb)
    else:
        raise ValueError(f"unknown dither method {method!r}")
    out = Image.fromarray(idx.astype(np.uint8), "P")
    out.putpalette(_palette(MEASURED_RGB).getpalette())
    return out


_INKS = np.array(MEASURED_RGB, dtype=np.float32)


def _nearest(rgb: np.ndarray) -> np.ndarray:
    """Index of the nearest ink for every pixel (rgb: ...x3)."""
    d = ((rgb[..., None, :] - _INKS) ** 2).sum(axis=-1)
    return d.argmin(axis=-1)


def _ordered(rgb: np.ndarray, spread: float = 64.0) -> np.ndarray:
    b = np.array([[0, 2], [3, 1]], dtype=np.float32)
    for _ in range(2):  # 2x2 -> 8x8 Bayer matrix
        b = np.block([[4 * b, 4 * b + 2], [4 * b + 3, 4 * b + 1]])
    bayer = (b + 0.5) / b.size - 0.5
    h, w, _ = rgb.shape
    tile = np.tile(bayer, (h // 8 + 1, w // 8 + 1))[:h, :w]
    return _nearest(rgb + tile[..., None] * spread)


def _atkinson(rgb: np.ndarray) -> np.ndarray:
    """Row by row; each row's error goes to the next pixels and two rows below."""
    h, w, _ = rgb.shape
    img = np.pad(rgb, ((0, 2), (0, 2), (0, 0)))  # room for error to spill off the edge
    idx = np.zeros((h, w), dtype=np.uint8)
    inks = _INKS
    for y in range(h):
        row, nxt, nxt2 = img[y], img[y + 1], img[y + 2]
        for x in range(w):
            px = row[x]
            i = int(((inks - px) ** 2).sum(axis=1).argmin())
            idx[y, x] = i
            err = (px - inks[i]) / 8
            row[x + 1] += err
            row[x + 2] += err
            nxt[x - 1 if x else 0] += err
            nxt[x] += err
            nxt[x + 1] += err
            nxt2[x] += err
    return idx


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
    # numpy, not a Python loop over 439,040 pairs: that loop takes seconds on a Pi Zero W.
    px = np.frombuffer(codes, dtype=np.uint8)
    return ((px[0::2] << 4) | px[1::2]).tobytes()


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
