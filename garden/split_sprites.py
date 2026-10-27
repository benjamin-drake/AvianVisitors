#!/usr/bin/env python3
"""Split sprite sheets (five poses in a row) into trimmed, transparent PNGs filed by species.

    python split_sprites.py                      # every sheet in sheets/
    python split_sprites.py sheets/robin.png --species "Erithacus rubecula"

Output: art/<scientific_name>/pose_1.png .. pose_5.png, plus _check.png (the
poses on a loud checkerboard, for eyeballing the cut-out) and species.json.

Pose order on every sheet: 1 perched side-on, 2 perched front-on, 3 singing,
4 in flight, 5 feeding (head down).

Species: matched from the file name against species.csv (UK or BirdNET name),
or pinned in sheets/names.json ({"file name.png": "Scientific name"}) when the
name is ambiguous, e.g. "Sparrow Studies" could be House or Tree Sparrow.

Transparent sheets keep their alpha. Sheets on white (or any flat colour) have
the background flood-filled away from the edges. Either way the edge of each
bird is then shaved by --trim pixels (default 2) to remove colour fringing.

Poses are separated by finding the bird shapes (connected regions): the five
biggest are the poses and smaller pieces (a detached foot or feather tip) join
the nearest one. If fewer than five shapes are found it falls back to
splitting at empty columns, then to equal-width slices.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
from birddisplay.species import registry  # noqa: E402

ROOT = Path(__file__).resolve().parent
POSES = 5
POSE_NAMES = ("perched side-on", "perched front-on", "singing", "in flight", "feeding")


def has_real_alpha(img: Image.Image) -> bool:
    if "A" not in img.getbands() and "transparency" not in img.info:
        return False
    return img.convert("RGBA").getchannel("A").getextrema()[0] < 250


def remove_flat_background(img: Image.Image, tolerance: int) -> Image.Image:
    """Flood-fill the background from the border so white inside the bird survives."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    padded = Image.new("RGB", (w + 2, h + 2), rgb.getpixel((0, 0)))
    padded.paste(rgb, (1, 1))
    filled = padded.copy()
    ImageDraw.floodfill(filled, (0, 0), (255, 0, 255), thresh=tolerance)
    changed = ImageChops.difference(padded, filled).convert("L").point(lambda v: 255 if v else 0)
    bg = np.asarray(changed.crop((1, 1, w + 1, h + 1))) > 0
    bg |= enclosed_background(np.asarray(rgb), bg, rgb.getpixel((0, 0)), tolerance)
    out = rgb.convert("RGBA")
    out.putalpha(Image.fromarray(np.where(bg, 0, 255).astype(np.uint8)))
    return out


def enclosed_background(rgb: np.ndarray, outside: np.ndarray, bg_colour, tolerance: int) -> np.ndarray:
    """Background trapped between legs or under a wing, which the edge flood can't reach.

    Only flat patches of the background colour count: painted white (a cheek,
    a neck ring) has brush texture, paper doesn't."""
    diff = np.abs(rgb.astype(int) - np.array(bg_colour)).max(axis=2)
    near = (diff <= tolerance) & ~outside
    labels, n = ndimage.label(near)
    if not n:
        return np.zeros_like(outside)
    idx = range(1, n + 1)
    sizes = ndimage.sum(near, labels, idx)
    # Share of each patch that is essentially the paper colour. Its anti-aliased
    # rim drags a plain standard deviation up, so count pixels instead.
    paper = ndimage.sum(diff <= 6, labels, idx)
    flat = [i for i, (size, p) in enumerate(zip(sizes, paper), start=1) if size >= 40 and p / size >= 0.8]
    return np.isin(labels, flat)


def trim_edges(rgba: Image.Image, px: int) -> Image.Image:
    """Shave `px` pixels off the bird's outline and harden the faint edge pixels,
    which is where colour fringing lives."""
    a = np.asarray(rgba.getchannel("A"))
    solid = a > 128
    if px > 0:
        solid = ndimage.binary_erosion(solid, iterations=px, border_value=0)
    # Keep a 1px soft edge from the original alpha so scaled birds aren't jaggy.
    soft = ndimage.binary_dilation(solid, iterations=1) & ~solid
    new_a = np.where(solid, 255, np.where(soft, np.minimum(a, 128), 0)).astype(np.uint8)
    out = rgba.copy()
    out.putalpha(Image.fromarray(new_a))
    return out


def find_poses(alpha: np.ndarray, count: int) -> list[np.ndarray]:
    """Return one boolean mask per pose, left to right."""
    solid = alpha > 32
    labels, n = ndimage.label(solid, structure=np.ones((3, 3)))
    if n:
        sizes = ndimage.sum(solid, labels, index=range(1, n + 1))
        speck = max(50, solid.sum() * 0.0005)
        keep = [i + 1 for i, s in enumerate(sizes) if s >= speck]
        if len(keep) >= count:
            keep.sort(key=lambda i: -sizes[i - 1])
            seeds, extras = keep[:count], keep[count:]
            boxes = {i: ndimage.find_objects((labels == i).astype(int))[0] for i in keep}
            groups = {s: [s] for s in seeds}
            for e in extras:
                ey = (boxes[e][0].start + boxes[e][0].stop) / 2
                ex = (boxes[e][1].start + boxes[e][1].stop) / 2

                def dist(s):
                    sy, sx = boxes[s]
                    dx = max(sx.start - ex, 0, ex - sx.stop)
                    dy = max(sy.start - ey, 0, ey - sy.stop)
                    return dx * dx + dy * dy
                groups[min(seeds, key=dist)].append(e)
            masks = [np.isin(labels, g) for g in groups.values()]
            return sorted(masks, key=lambda m: np.nonzero(m.any(axis=0))[0].mean())
        print(f"  only {len(keep)} separate shapes (poses touching?); splitting by columns")
    # Fallback: empty columns, else equal slices.
    cols = solid.any(axis=0)
    runs, start = [], None
    for x, filled in enumerate(list(cols) + [False]):
        if filled and start is None:
            start = x
        elif not filled and start is not None:
            runs.append([start, x])
            start = None
    while len(runs) > count:
        gaps = [runs[i + 1][0] - runs[i][1] for i in range(len(runs) - 1)]
        i = gaps.index(min(gaps))
        runs[i:i + 2] = [[runs[i][0], runs[i + 1][1]]]
    if len(runs) != count:
        step = alpha.shape[1] / count
        runs = [[round(i * step), round((i + 1) * step)] for i in range(count)]
    masks = []
    for x0, x1 in runs:
        m = np.zeros_like(solid)
        m[:, x0:x1] = solid[:, x0:x1]
        masks.append(m)
    return masks


def resolve_species(path: Path, override: str | None, names: dict):
    reg = registry()
    pinned = override or names.get(path.name)
    if pinned:
        sp = reg.get(pinned)
        if not sp:
            sys.exit(f"{path.name}: '{pinned}' is not in species.csv; add a row for it first")
        return sp
    hits = reg.match_filename(path.stem)
    if len(hits) == 1:
        return hits[0]
    candidates = hits or reg.ambiguous_word(path.stem)
    if candidates:
        options = ", ".join(f"{s.uk_name} ({s.sci})" for s in candidates)
        sys.exit(f"{path.name}: could be {options}. Pin it in sheets/names.json, e.g.\n"
                 f'  {{"{path.name}": "{candidates[0].sci}"}}')
    sys.exit(f"{path.name}: no species name found in the file name. "
             f"Rename it, use --species, or pin it in sheets/names.json")


def split_sheet(path: Path, species, out_root: Path, trim: int, tolerance: int, max_size: int) -> Path:
    sheet = Image.open(path)
    sheet.load()
    rgba = sheet.convert("RGBA") if has_real_alpha(sheet) else remove_flat_background(sheet, tolerance)
    rgba = trim_edges(rgba, trim)

    out_dir = out_root / species.slug
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("pose_*.png"):
        old.unlink()

    alpha = np.asarray(rgba.getchannel("A"))
    rgba_arr = np.asarray(rgba)
    for i, mask in enumerate(find_poses(alpha, POSES), start=1):
        ys, xs = np.nonzero(mask)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        crop = rgba_arr[y0:y1, x0:x1].copy()
        crop[..., 3] = np.where(mask[y0:y1, x0:x1], crop[..., 3], 0)  # drop neighbours' bits
        pose = Image.fromarray(crop)
        if max(pose.size) > max_size:
            pose.thumbnail((max_size, max_size), Image.LANCZOS)
        canvas = Image.new("RGBA", (pose.width + 4, pose.height + 4), (0, 0, 0, 0))
        canvas.paste(pose, (2, 2))
        canvas.save(out_dir / f"pose_{i}.png", optimize=True)
        print(f"  pose {i} ({POSE_NAMES[i - 1]}): {canvas.width}x{canvas.height}")

    (out_dir / "species.json").write_text(json.dumps(
        {"sci": species.sci, "uk_name": species.uk_name, "sheet": path.name, "trim_px": trim}, indent=2))
    write_check(out_dir)
    return out_dir


def write_check(out_dir: Path) -> None:
    poses = [Image.open(p) for p in sorted(out_dir.glob("pose_*.png"))]
    w = sum(p.width for p in poses) + 10 * (len(poses) + 1)
    h = max(p.height for p in poses) + 20
    sheet = Image.new("RGBA", (w, h), (255, 0, 255, 255))
    draw = ImageDraw.Draw(sheet)
    for y in range(0, h, 16):
        for x in range((y // 16) % 2 * 16, w, 32):
            draw.rectangle((x, y, x + 15, y + 15), fill=(0, 190, 190, 255))
    x = 10
    for p in poses:
        sheet.alpha_composite(p, (x, 10))
        x += p.width + 10
    sheet.convert("RGB").save(out_dir / "_check.png")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sheets", nargs="*", type=Path, help="default: every PNG in sheets/")
    ap.add_argument("--out", type=Path, default=ROOT / "art")
    ap.add_argument("--species", help="scientific or common name (single sheet only)")
    ap.add_argument("--trim", type=int, default=2, choices=(0, 1, 2, 3),
                    help="pixels shaved off each bird's outline (default 2)")
    ap.add_argument("--tolerance", type=int, default=28, help="background tolerance for non-transparent sheets")
    ap.add_argument("--max-size", type=int, default=700, help="longest side of each saved pose")
    args = ap.parse_args()

    sheets = args.sheets or sorted((ROOT / "sheets").glob("*.png"))
    if args.species and len(sheets) != 1:
        ap.error("--species needs exactly one sheet")
    names_file = ROOT / "sheets" / "names.json"
    names = json.loads(names_file.read_text()) if names_file.exists() else {}

    for path in sheets:
        species = resolve_species(path, args.species, names)
        print(f"{path.name} -> {species.uk_name} ({species.sci})")
        out = split_sheet(path, species, args.out, args.trim, args.tolerance, args.max_size)
        print(f"  -> {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")


if __name__ == "__main__":
    main()
