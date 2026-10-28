"""Settings: garden/config.json holds the defaults (in git); ~/garden-data/config.json
on each Pi overrides any of them (not in git: station URL, notification setup)."""
from __future__ import annotations

import json
from pathlib import Path

GARDEN = Path(__file__).resolve().parent.parent
DATA = Path.home() / "garden-data"

DEFAULTS = {
    "latitude": 52.77,
    "longitude": -0.89,
    "linger_minutes": 60,
    "art_dir": str(GARDEN / "art"),
    "data_dir": str(DATA),
    # Mic Pi
    "birds_db": "~/BirdNET-Pi/scripts/birds.db",
    "apprise": "~/BirdNET-Pi/birdnet/bin/apprise",
    "notify_urls": "",          # default: <data_dir>/notify.txt
    "summary_title": "Birds heard yesterday",
    # Frame Pi
    "station_url": "http://birdnet.local",
    "rotate": 0,               # 180 if the frame hangs upside down
    "heal_hours": 24,          # redraw at least this often even if nothing changed
    "on_time": "05:00",        # panel shows birds from...
    "off_time": "23:00",       # ...until; outside these hours it's left blank
    "night_mode": False,
    "dither_saturation": 1.0,  # 1.0/1.0 = natural colour (style B); 1.3/1.1 = boosted (style A)
    "dither_contrast": 1.0,       # True: dark background with pale outlines between sunset and sunrise
}


def load(path: Path | None = None) -> dict:
    cfg = dict(DEFAULTS)
    for p in (GARDEN / "config.json", path or DATA / "config.json"):
        if p.exists():
            cfg.update(json.loads(p.read_text()))
    cfg["notify_urls"] = cfg["notify_urls"] or str(Path(cfg["data_dir"]) / "notify.txt")
    for key in ("art_dir", "data_dir", "birds_db", "apprise", "notify_urls"):
        p = Path(cfg[key]).expanduser()
        cfg[key] = str(p if p.is_absolute() else GARDEN / p)
    return cfg
