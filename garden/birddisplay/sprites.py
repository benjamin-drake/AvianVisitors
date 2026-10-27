"""Pose sprites, filed by scientific name: art/<slug>/pose_1.png .. pose_5.png."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageFilter

from .species import slugify

POSE_NAMES = ("perched side-on", "perched front-on", "singing", "in flight", "feeding")


class SpriteLibrary:
    def __init__(self, art_dir: Path, stand_ins: bool = False):
        self.art_dir = Path(art_dir)
        # Preview-only: let species without art borrow someone else's, to test
        # how a crowded screen packs before the art exists.
        self.stand_ins = stand_ins

    @lru_cache(maxsize=None)
    def _own(self, sci: str) -> tuple[Image.Image, ...]:
        files = sorted((self.art_dir / slugify(sci)).glob("pose_*.png"))
        return tuple(Image.open(f).convert("RGBA") for f in files)

    @lru_cache(maxsize=None)
    def available(self) -> tuple[str, ...]:
        return tuple(sorted(p.name for p in self.art_dir.iterdir() if any(p.glob("pose_*.png"))))

    def poses(self, sci: str) -> tuple[Image.Image, ...]:
        own = self._own(sci)
        if own or not self.stand_ins or not self.available():
            return own
        # Deterministic borrow so a stand-in keeps the same art all day.
        slugs = self.available()
        borrowed = slugs[sum(map(ord, sci)) % len(slugs)]
        files = sorted((self.art_dir / borrowed).glob("pose_*.png"))
        return tuple(Image.open(f).convert("RGBA") for f in files)

    def has(self, sci: str) -> bool:
        return bool(self._own(sci))

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
