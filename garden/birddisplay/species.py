"""Species registry: scientific name is the key everywhere (BirdNET's common
names vary by language setting, and sprite sheet file names are free-form)."""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

REGISTRY = Path(__file__).resolve().parent.parent / "species.csv"


@dataclass(frozen=True)
class Species:
    sci: str
    uk_name: str
    birdnet_name: str
    size: float = 1.0
    aliases: tuple[str, ...] = ()

    @property
    def slug(self) -> str:
        return slugify(self.sci)


def slugify(name: str) -> str:
    """'Cyanistes caeruleus' -> 'cyanistes_caeruleus'"""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


class Registry:
    def __init__(self, path: Path = REGISTRY):
        self.species: list[Species] = []
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                aliases = tuple(a.strip() for a in (row.get("aliases") or "").split(";") if a.strip())
                self.species.append(Species(row["sci"].strip(), row["uk_name"].strip(),
                                            row["birdnet_name"].strip(), float(row["size"] or 1),
                                            aliases))
        self._by_key: dict[str, Species] = {}
        for s in self.species:
            for key in (s.sci, s.uk_name, s.birdnet_name, *s.aliases):
                self._by_key[key.lower()] = s

    def get(self, name: str) -> Species | None:
        """Look up by scientific, UK or BirdNET common name."""
        return self._by_key.get(name.strip().lower())

    def resolve(self, sci: str, common: str = "") -> Species:
        """Always returns something, so unknown BirdNET species still get logged."""
        return self.get(sci) or self.get(common) or Species(sci, common or sci, common or sci)

    def match_filename(self, filename: str) -> list[Species]:
        """Species whose UK/BirdNET name appears as whole words in a file name.
        Longest name wins, so 'Mistle Thrush' beats 'Thrush'."""
        text = " " + re.sub(r"[^a-z]+", " ", filename.lower()) + " "
        hits: dict[str, tuple[int, Species]] = {}
        for s in self.species:
            for name in (s.uk_name, s.birdnet_name, s.sci):
                words = " " + re.sub(r"[^a-z]+", " ", name.lower()).strip() + " "
                if words in text:
                    best = hits.get(s.sci, (0, s))[0]
                    hits[s.sci] = (max(best, len(words)), s)
        if not hits:
            return []
        top = max(n for n, _ in hits.values())
        return [s for n, s in hits.values() if n == top]

    def ambiguous_word(self, filename: str) -> list[Species]:
        """For 'Sparrow Studies': species whose name *ends* with a word in the file name."""
        words = set(re.sub(r"[^a-z]+", " ", filename.lower()).split())
        return [s for s in self.species if s.uk_name.lower().split()[-1] in words]


@lru_cache(maxsize=1)
def registry() -> Registry:
    return Registry()
