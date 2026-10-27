"""Detections -> who is on screen -> a packed collage.

On screen: a bird appears when heard and stays for `linger` (60 min) after its
most recent detection; hearing it again resets the clock.

The *scene* is the set of species on screen. Whenever it changes (a bird
arrives or expires) every bird gets a fresh pose, mirroring, size wobble and
position, all seeded from the date plus the scene, so the same scene on the
same day always looks the same and redraws are reproducible.

Packing is a port of AvianVisitors' mask nester (avian/frontend/apt.js,
maskPack and its tuning): tile areas are normalised against a viewport budget
with size ~ calls^0.65 (here ^0.35, times species size), then placed largest first by spiralling out from the
centre on an ellipse, accepting the first ring where the bird's silhouette
doesn't touch any placed silhouette (plus a padding moat). If anything won't
fit, everything shrinks 7% and repacks. Differences from upstream: five poses
chosen at random (upstream: perched, 15% flight), random mirroring, a size
wobble, a per-species size factor and a cap on the biggest bird, and the collision test uses an FFT
correlation of the whole occupancy grid so a Pi Zero 2 W can afford it.
"""
from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import eink
from .species import Registry, registry
from .sprites import SpriteLibrary, outlined


@dataclass(frozen=True)
class Detection:
    sci: str
    common: str
    time: datetime
    confidence: float = 1.0


@dataclass
class Visit:
    sci: str
    common: str
    start: datetime
    last_heard: datetime
    linger: timedelta
    count: int = 1

    @property
    def expires(self) -> datetime:
        return self.last_heard + self.linger


def build_visits(detections: Iterable[Detection], up_to: datetime | None,
                 linger: timedelta) -> list[Visit]:
    visits, current = [], {}
    for d in sorted(detections, key=lambda d: d.time):
        if up_to is not None and d.time > up_to:
            break
        v = current.get(d.sci)
        if v is not None and d.time <= v.expires:
            v.last_heard, v.count = d.time, v.count + 1
        else:
            current[d.sci] = v = Visit(d.sci, d.common, d.time, d.time, linger)
            visits.append(v)
    return visits


def on_screen(detections: Iterable[Detection], now: datetime, linger: timedelta) -> list[Visit]:
    return [v for v in build_visits(detections, now, linger) if v.start <= now < v.expires]


def rng_for(*parts) -> random.Random:
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


# ---------------------------------------------------------------------------
# Layout

@dataclass
class Style:
    width: int = eink.WIDTH
    height: int = eink.HEIGHT
    margin: int = 18            # keep birds clear of the frame's edge/mat
    grid: int = 4               # px per occupancy cell (upstream GRID_STRIDE)
    pad: int = 3                # gap around each bird, in cells (upstream COLLAGE_PAD)
    aspect_bias: float = 2.1    # wide ellipse for a landscape panel (upstream)
    count_exp: float = 0.35     # size ~ calls^0.35 (upstream 0.65 let a chatty tit outgrow a pheasant)
    size_exp: float = 2.0       # area ~ species size factor^2 (species.csv), so a pheasant reads bigger than a tit
    max_tile: float = 0.15      # no bird takes more than this share of the screen (few birds -> not huge)
    size_wobble: tuple[float, float] = (0.8, 1.25)  # area multiplier per appearance
    mirror: bool = True
    outline: int = 2            # night outline, px
    day_bg: tuple = (255, 255, 255)
    night_bg: tuple = (0, 0, 0)
    outline_colour: tuple = (255, 255, 255)


def tuning(n: int) -> dict:
    """Upstream's tuning(n): budget and floor step down as the plate gets busy."""
    return {
        "budget": 0.46 if n <= 4 else 0.40 if n <= 12 else 0.34 if n <= 24 else 0.28,
        "min_area": 0.0100 if n <= 8 else 0.0075 if n <= 20 else 0.0055,
    }


@dataclass
class Tile:
    sci: str
    common: str
    count: int
    pose: int
    flip: bool
    sprite: Image.Image
    score: float
    w: float = 0
    h: float = 0
    x: float = 0
    y: float = 0
    placed: bool = False
    _mask_key: tuple = field(default=(), repr=False)
    _mask: np.ndarray | None = field(default=None, repr=False)

    def mask(self, cell: int) -> np.ndarray:
        """Silhouette on the occupancy grid at the tile's current size."""
        key = (round(self.w), round(self.h), cell)
        if self._mask_key != key:
            gw, gh = max(1, math.ceil(self.w / cell)), max(1, math.ceil(self.h / cell))
            a = self.sprite.getchannel("A").resize((gw, gh), Image.BOX)
            m = np.asarray(a) > 24
            self._mask, self._mask_key = (m[:, ::-1] if self.flip else m), key
        return self._mask


def make_tiles(entries, library: SpriteLibrary, reg: Registry, rng: random.Random,
               style: Style) -> list[Tile]:
    """entries: (sci, common, count). Pose, mirroring and wobble come from rng."""
    tiles = []
    for sci, common, count in entries:
        poses = library.poses(sci)
        if not poses:
            continue
        pose = rng.randrange(len(poses))
        flip = style.mirror and rng.random() < 0.5
        size = reg.resolve(sci, common).size
        score = (max(1, count) ** style.count_exp * size ** style.size_exp
                 * rng.uniform(*style.size_wobble))
        tiles.append(Tile(sci, common, count, pose, flip, poses[pose], score))
    return tiles


def size_tiles(tiles: list[Tile], style: Style) -> None:
    """Upstream steps 2-3: areas normalised to the budget, floored, then w/h from aspect."""
    t = tuning(len(tiles))
    vp_area = (style.width - 2 * style.margin) * (style.height - 2 * style.margin)
    budget, min_area = vp_area * t["budget"], vp_area * t["min_area"]
    total = sum(x.score for x in tiles) or 1
    max_area = vp_area * style.max_tile
    areas = [min(max_area, max(min_area, budget * x.score / total)) for x in tiles]
    if sum(areas) > budget:
        fixed = sum(a for a in areas if a <= min_area + 1e-9)
        flex = sum(areas) - fixed
        shrink = min(1, max(0, budget - fixed) / flex) if flex else 1
        areas = [a if a <= min_area + 1e-9 else a * shrink for a in areas]
    for tile, area in zip(tiles, areas):
        ar = tile.sprite.width / tile.sprite.height
        tile.w = math.sqrt(area * ar)
        tile.h = tile.w / ar


def _dilate(m: np.ndarray, r: int) -> np.ndarray:
    out = m.copy()
    for _ in range(r):
        grown = out.copy()
        grown[1:, :] |= out[:-1, :]
        grown[:-1, :] |= out[1:, :]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        out = grown
    return out


def _collision_map(occ: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """hits[gy, gx] is True where the mask, top-left at (gx, gy), overlaps occ."""
    gh, gw = occ.shape
    mh, mw = mask.shape
    shape = (gh + mh, gw + mw)
    f = np.fft.rfft2(occ.astype(np.float32), shape)
    g = np.fft.rfft2(mask[::-1, ::-1].astype(np.float32), shape)
    full = np.fft.irfft2(f * g, shape)
    # The overlap count for offset (gx, gy) sits at full[gy + mh - 1, gx + mw - 1].
    return full[mh - 1:gh, mw - 1:gw] > 0.5


def mask_pack(tiles: list[Tile], style: Style, rng: random.Random,
              reserved: Iterable[tuple[int, int, int, int]] = ()) -> None:
    """Upstream maskPack: largest first, spiral out from the centre on an ellipse."""
    cell = style.grid
    gw, gh = math.ceil(style.width / cell), math.ceil(style.height / cell)
    occ = np.zeros((gh, gw), dtype=bool)
    for x0, y0, x1, y1 in reserved:
        occ[y0 // cell:math.ceil(y1 / cell), x0 // cell:math.ceil(x1 / cell)] = True

    lo_x, lo_y = style.margin, style.margin
    hi_x, hi_y = style.width - style.margin, style.height - style.margin
    cx, cy = style.width / 2, style.height / 2
    xb, yb = style.aspect_bias, 1.0
    placed: list[Tile] = []

    for t in sorted(tiles, key=lambda t: -t.w * t.h):
        t.placed = False
        m = t.mask(cell)
        mh, mw = m.shape
        if mw > gw or mh > gh:
            continue
        hits = _collision_map(occ, m)
        if placed:
            area = sum(p.w * p.h for p in placed)
            com_x = sum((p.x + p.w / 2) * p.w * p.h for p in placed) / area
            com_y = sum((p.y + p.h / 2) * p.w * p.h for p in placed) / area
        else:
            com_x, com_y = cx, cy
        step = max(cell, min(t.w, t.h) * 0.05)
        phase = rng.random() * 2 * math.pi
        best, best_cost, found_ring = None, math.inf, -1.0
        r = 0.0
        while r <= max(style.width, style.height):
            if found_ring >= 0 and r > found_ring + step * 2:
                break
            k = np.arange(max(36, int(r / 1.6)))
            theta = phase + k / len(k) * 2 * math.pi
            px = cx + r * xb * np.cos(theta) - t.w / 2
            py = cy + r * yb * np.sin(theta) - t.h / 2
            ok = (px >= lo_x) & (py >= lo_y) & (px + t.w <= hi_x) & (py + t.h <= hi_y)
            gx, gy = (px // cell).astype(int), (py // cell).astype(int)
            ok &= (gx >= 0) & (gy >= 0) & (gx <= gw - mw) & (gy <= gh - mh)
            if ok.any():
                idx = np.nonzero(ok)[0]
                free = idx[~hits[gy[idx], gx[idx]]]
                for i in free:
                    cost = math.hypot((px[i] + t.w / 2 - com_x) / xb, (py[i] + t.h / 2 - com_y) / yb)
                    cost += rng.random() * step * 0.5
                    if cost < best_cost:
                        best, best_cost = (px[i], py[i]), cost
            if best is not None and found_ring < 0:
                found_ring = r
            r += step
        if best is None:
            continue
        t.x, t.y, t.placed = float(best[0]), float(best[1]), True
        gx, gy = int(t.x // cell), int(t.y // cell)
        stamp = np.zeros_like(occ)
        stamp[gy:gy + mh, gx:gx + mw] = m
        occ |= _dilate(stamp, style.pad)
        placed.append(t)


def layout(entries, library: SpriteLibrary, style: Style, seed: str,
           reg: Registry | None = None, reserved=()) -> list[Tile]:
    """Size, pack, shrink-to-fit and centre. Returns the tiles that made it on screen."""
    reg = reg or registry()
    tiles = make_tiles(entries, library, reg, rng_for(seed), style)
    if not tiles:
        return []
    size_tiles(tiles, style)
    for _ in range(11):
        mask_pack(tiles, style, rng_for(seed, "pack"), reserved)
        if all(t.placed for t in tiles):
            break
        for t in tiles:  # upstream: 0.93 linear shrink, then repack
            t.w *= 0.93
            t.h *= 0.93
    placed = [t for t in tiles if t.placed]
    if not reserved and placed:
        # Re-centre the cluster, as upstream does. Skipped when part of the
        # canvas is reserved, so the caption corner stays clear.
        left, right = min(t.x for t in placed), max(t.x + t.w for t in placed)
        top, bottom = min(t.y for t in placed), max(t.y + t.h for t in placed)
        dx = style.width / 2 - (left + right) / 2
        dy = style.height / 2 - (top + bottom) / 2
        dx = max(style.margin - left, min(style.width - style.margin - right, dx))
        dy = max(style.margin - top, min(style.height - style.margin - bottom, dy))
        for t in placed:
            t.x += dx
            t.y += dy
    return placed


def render(tiles: list[Tile], style: Style, night: bool) -> Image.Image:
    bg = style.night_bg if night else style.day_bg
    canvas = Image.new("RGBA", (style.width, style.height), tuple(bg) + (255,))
    b = style.outline + 1
    for t in tiles:
        w, h = max(1, round(t.w)), max(1, round(t.h))
        sprite = t.sprite.resize((w, h), Image.LANCZOS)
        if t.flip:
            sprite = sprite.transpose(Image.FLIP_LEFT_RIGHT)
        if night:
            roomy = Image.new("RGBA", (w + 2 * b, h + 2 * b), (0, 0, 0, 0))
            roomy.paste(sprite, (b, b))
            canvas.alpha_composite(outlined(roomy, style.outline, style.outline_colour),
                                   (round(t.x) - b, round(t.y) - b))
        else:
            canvas.alpha_composite(sprite, (round(t.x), round(t.y)))
    return canvas.convert("RGB")


# ---------------------------------------------------------------------------
# Screen and archive

@dataclass
class Frame:
    image: Image.Image
    tiles: list[Tile]
    visits: list[Visit]          # every species currently "on screen", art or not
    missing: list[Visit]         # ...of which no art yet
    night: bool
    signature: str               # what the e-ink refresh rule compares


def scene_signature(day: date, scis: Iterable[str], night: bool) -> str:
    key = f"{day}|{'night' if night else 'day'}|{','.join(sorted(scis))}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def render_live(entries, today: date, library: SpriteLibrary, style: Style, night: bool):
    """entries: (sci, common, count) for every species on screen. Returns
    (image, tiles, signature). Seeded by date + scene, so an arrival or an
    expiry reshuffles poses and places, and nothing else does."""
    drawable = [e for e in entries if library.drawable(e[0])]
    scis = [e[0] for e in drawable]
    tiles = layout(drawable, library, style, f"{today}|{','.join(sorted(scis))}")
    return render(tiles, style, night), tiles, scene_signature(today, scis, night)


def render_screen(detections, now: datetime, library: SpriteLibrary, style: Style,
                  night: bool, linger: timedelta) -> Frame:
    visits = on_screen(detections, now, linger)
    image, tiles, sig = render_live([(v.sci, v.common, v.count) for v in visits],
                                    now.date(), library, style, night)
    missing = [v for v in visits if not library.has(v.sci)]
    return Frame(image, tiles, visits, missing, night, sig)


def render_archive(detections, day: date, library: SpriteLibrary, style: Style) -> Frame:
    """The whole day: every species with art, once, sized by its calls that day."""
    counts: dict[str, list] = {}
    for d in detections:
        if d.time.date() == day:
            counts.setdefault(d.sci, [d.common, 0])[1] += 1
    entries = [(sci, c, n) for sci, (c, n) in counts.items() if library.drawable(sci)]
    caption = f"{day:%A} {day.day} {day:%B %Y}  ·  {len(entries)} species"
    box = _caption_box(caption, style)
    tiles = layout(entries, library, style, f"{day}|archive", reserved=[box])
    img = render(tiles, style, night=False)
    ImageDraw.Draw(img).text((box[0], box[1]), caption, fill=(0, 0, 0), font=_font())
    return Frame(img, tiles, [], [], False, "")


def _font(size: int = 20):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _caption_box(text: str, style: Style) -> tuple[int, int, int, int]:
    _, _, x1, y1 = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=_font())
    x = style.width - x1 - style.margin
    y = style.height - y1 - style.margin
    return (x, y, x + x1, y + y1)
