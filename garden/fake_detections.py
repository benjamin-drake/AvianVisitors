#!/usr/bin/env python3
"""A plausible few days of BirdNET detections for a farm garden near Melton Mowbray.

    python fake_detections.py --start 2026-10-26 --days 2 > detections.jsonl

One JSON object per line, the same fields BirdNET-Pi stores:
{"sci": "Turdus merula", "common": "Eurasian Blackbird", "time": "2026-10-27T07:12:03", "confidence": 0.83}
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import date, datetime, timedelta

from birddisplay.species import registry

# sci: (calls per hour at peak, (start hour, end hour), dawn boost). end > 24 wraps past midnight.
ACTIVITY = {
    "Cyanistes caeruleus":   (6, (7.0, 17.0), 1.5),   # art
    "Turdus merula":         (5, (5.5, 18.5), 2.5),   # art
    "Passer domesticus":     (6, (7.0, 17.0), 1.0),   # art
    "Phasianus colchicus":   (1.5, (6.0, 18.0), 2.5), # art; crows at dawn and dusk
    "Erithacus rubecula":    (5, (5.5, 22.0), 2.0),
    "Columba palumbus":      (3, (6.0, 18.0), 1.5),
    "Parus major":           (3, (7.0, 17.0), 1.5),
    "Troglodytes troglodytes": (2, (6.5, 17.0), 2.0),
    "Corvus frugilegus":     (3, (7.0, 17.0), 1.0),
    "Corvus monedula":       (2, (7.0, 17.0), 1.0),
    "Pica pica":             (1.5, (7.0, 17.0), 1.0),
    "Fringilla coelebs":     (1.5, (7.5, 16.0), 1.0),
    "Carduelis carduelis":   (1, (8.0, 16.0), 1.0),
    "Buteo buteo":           (0.6, (9.0, 16.0), 1.0),
    "Milvus milvus":         (0.3, (9.0, 15.0), 1.0),
    "Turdus iliacus":        (0.8, (6.0, 30.0), 1.0),  # migrating redwings call overhead at night
    "Strix aluco":           (3, (17.5, 30.0), 1.0),
    "Tyto alba":             (0.4, (18.0, 29.0), 1.0),
}


def generate(day: date, rng: random.Random) -> list[dict]:
    reg = registry()
    out = []
    t = datetime.combine(day, datetime.min.time())
    step = timedelta(minutes=5)
    while t.date() == day:
        h = t.hour + t.minute / 60
        for sci, (rate, (start, end), dawn) in ACTIVITY.items():
            hh = h if h >= start or end <= 24 else h + 24
            if not start <= hh < end:
                continue
            shape = dawn if 6 <= h <= 9 else 0.6 if 11 <= h <= 14 else 1.0
            if rng.random() < rate * shape * step.total_seconds() / 3600:
                when = t + timedelta(seconds=rng.randint(0, 299))
                out.append({"sci": sci, "common": reg.get(sci).birdnet_name,
                            "time": when.isoformat(timespec="seconds"),
                            "confidence": round(rng.uniform(0.7, 0.98), 2)})
        t += step
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=date.fromisoformat, default=date.today())
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    rows = []
    for i in range(args.days):
        rows += generate(args.start + timedelta(days=i), rng)
    for d in sorted(rows, key=lambda d: d["time"]):
        print(json.dumps(d))


if __name__ == "__main__":
    main()
