"""Pose sprites, filed by scientific name: art/<slug>/pose_1.png .. pose_5.png."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageFilter

from .species import slugify

POSE_NAMES = ("perched side-on", "perched front-on", "singing", "in flight", "feeding")


class Poses:
    """A species' pose files, loaded only when one is actually used. Opening all
    five for every bird on screen would cost ~7 MB a species, which matters on
    a Pi Zero W with 512 MB."""

    def __init__(self, files: list[Path]):
        self.files = files
        self._cache: dict[int, Image.Image] = {}

    def __len__(self) -> int:
        return len(self.files)

    def __bool__(self) -> bool:
        return bool(self.files)

    def __getitem__(self, i: int) -> Image.Image:
        if i not in self._cache:
            self._cache[i] = Image.open(self.files[i]).convert("RGBA")
        return self._cache[i]


class SpriteLibrary:
    def __init__(self, art_dir: Path, stand_ins: bool = False):
        self.art_dir = Path(art_dir)
        # Preview-only: let species without art borrow someone else's, to test
        # how a crowded screen packs before the art exists.
        self.stand_ins = stand_ins

    @lru_cache(maxsize=None)
    def _files(self, slug: str) -> Poses:
        return Poses(sorted((self.art_dir / slug).glob("pose_*.png")))

    @lru_cache(maxsize=None)
    def available(self) -> tuple[str, ...]:
        if not self.art_dir.is_dir():
            return ()
        return tuple(sorted(p.name for p in self.art_dir.iterdir() if any(p.glob("pose_*.png"))))

    def poses(self, sci: str) -> Poses:
        own = self._files(slugify(sci))
        if own or not self.stand_ins or not self.available():
            return own
        # Deterministic borrow so a stand-in keeps the same art all day.
        slugs = self.available()
        return self._files(slugs[sum(map(ord, sci)) % len(slugs)])

    def has(self, sci: str) -> bool:
        return bool(self._files(slugify(sci)))

    def drawable(self, sci: str) -> bool:
        return bool(self.poses(sci))


def outlined(sprite: Image.Image, width: int, colour) -> Image.Image:
    """Sprite on a solid silhouette `width` px larger all round (sprite must have room)."""
    alpha = sprite.getchannel("A").point(lambda a: 255 if a > 80 else 0)
    grown = alpha.filter(ImageFilter.MaxFilter(2 * width + 1))
    out = Image.new("RGBA", sprite.size, tuple(colour) + (0,))
    out.putalpha(grown)
    out.alpha_composite(sprite)
    return out
