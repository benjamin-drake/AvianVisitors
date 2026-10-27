#!/usr/bin/env python3
"""Build BirdNET-Pi's include list from eBird regions (default: Leicestershire + Rutland).

    python3 garden/mic/ebird_species.py --key YOUR_EBIRD_KEY
    python3 garden/mic/ebird_species.py --key KEY --labels ~/BirdNET-Pi/model/BirdNET_GLOBAL_6K_V2.4_Model_FP16_Labels.txt

Writes include_species_list.txt (one "Scientific name_Common name" per line,
the format BirdNET-Pi reads) to --out. With an include list in place
BirdNET-Pi only records species on it. setup.sh copies it into ~/BirdNET-Pi/.

eBird and BirdNET don't always agree on scientific names (eBird moves species
between genera faster), so a species matches on scientific name first, then
on English name, then on the aliases in species.csv.

Get a free key at https://ebird.org/api/keygen. Run it on the Mac or the Pi.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from birddisplay.species import registry  # noqa: E402

DEFAULT_LABELS = [
    Path.home() / "BirdNET-Pi/model/BirdNET_GLOBAL_6K_V2.4_Model_FP16_Labels.txt",
    HERE.parent.parent / "model/BirdNET_GLOBAL_6K_V2.4_Model_FP16_Labels.txt",
]


def ebird(path: str, key: str):
    req = urllib.request.Request(f"https://api.ebird.org/v2/{path}", headers={"X-eBirdApiToken": key})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def load_labels(path: Path) -> dict[str, str]:
    """{scientific: English name} for every species the model knows.

    The labels file lists scientific names (older models: 'Sci_Common');
    English names come from model/l18n/labels_en.json beside it."""
    english_file = path.parent / "l18n" / "labels_en.json"
    english = json.loads(english_file.read_text()) if english_file.exists() else {}
    labels = {}
    for line in path.read_text().splitlines():
        sci, _, com = line.strip().partition("_")
        if sci:
            labels[sci] = english.get(sci) or com or sci
    return labels


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--key", required=True, help="eBird API key")
    ap.add_argument("--regions", nargs="+", default=["GB-ENG-LEC", "GB-ENG-RUT"])
    ap.add_argument("--labels", type=Path)
    ap.add_argument("--out", type=Path, default=Path.home() / "garden-data/include_species_list.txt")
    args = ap.parse_args()

    labels_path = args.labels or next((p for p in DEFAULT_LABELS if p.exists()), None)
    if not labels_path:
        sys.exit("BirdNET labels file not found; pass --labels")
    labels = load_labels(labels_path)
    by_common = {c.lower(): s for s, c in labels.items()}

    codes: set[str] = set()
    for region in args.regions:
        found = ebird(f"product/spplist/{region}", args.key)
        print(f"{region}: {len(found)} taxa on eBird")
        codes |= set(found)
    taxonomy = ebird("ref/taxonomy/ebird?fmt=json&cat=species", args.key)

    reg = registry()
    chosen: dict[str, str] = {}
    unmatched = []
    for t in taxonomy:
        if t["speciesCode"] not in codes:
            continue
        sci, com = t["sciName"], t["comName"]
        known = reg.get(sci)
        candidates = [sci, *(known.aliases if known else ())]
        hit = next((c for c in candidates if c in labels), None) or by_common.get(com.lower())
        if hit:
            chosen[hit] = labels[hit]
        else:
            unmatched.append(f"{com} ({sci})")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(f"{s}_{c}\n" for s, c in sorted(chosen.items())))
    print(f"{len(chosen)} species BirdNET can identify -> {args.out}")
    if unmatched:
        print(f"{len(unmatched)} eBird species BirdNET has no label for (fine, mostly rarities/subspecies):")
        print("  " + ", ".join(sorted(unmatched)[:40]) + (" ..." if len(unmatched) > 40 else ""))


if __name__ == "__main__":
    main()
