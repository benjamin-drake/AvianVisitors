#!/usr/bin/env python3
"""A stand-in frame on the Mac: a web page showing what the panel would show, live.

    .venv/bin/python webframe.py                          # http://localhost:8765
    .venv/bin/python webframe.py --station http://birdnet # over Tailscale, away from home
    python3 webframe.py --host 0.0.0.0 --panel-hours       # always-on test server (see ops/webframe/)

Every few minutes it asks the mic Pi who was heard today and in the last 60
minutes (the same API calls the frame Pi makes), renders with your art from
art/, and the page picks up the new picture. Open it in a browser and go full
screen. It follows the same views as the frame (birddisplay/scenes.py).

The page shows the e-ink simulation by default; press C for the full-colour
artwork and E to go back. It ignores the panel's on/off hours unless you pass
--panel-hours: then, like the real frame, from off_time to on_time it draws
"Birds of Today" once and holds it.
"""
from __future__ import annotations

import argparse
import io
import json
import threading
import time
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from birddisplay import eink, scenes, settings, sources
from birddisplay.collage import live_signature, render_live, style_for
from birddisplay.species import registry
from birddisplay.sprites import SpriteLibrary

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Birds of the Hour</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  html, body { margin: 0; height: 100%; background: #2b2b2b; }
  body { display: flex; align-items: center; justify-content: center; }
  img { height: 100vh; aspect-ratio: 784 / 1120; max-width: 100vw; object-fit: contain;
        background: #fff; box-shadow: 0 0 40px rgba(0,0,0,.5); }
  #info { position: fixed; left: 12px; bottom: 10px; font: 13px -apple-system, sans-serif;
          color: #bbb; max-width: calc(50vw - 420px); line-height: 1.5; }
  @media (max-width: 1300px) { #info { display: none; } }
</style></head>
<body><img id="frame" alt="Birds of the Hour"><div id="info"></div>
<script>
let mode = "eink", version = null;
async function tick() {
  try {
    const s = await (await fetch("/state.json", {cache: "no-store"})).json();
    if (s.version !== version || document.getElementById("frame").dataset.mode !== mode) {
      version = s.version;
      const img = document.getElementById("frame");
      img.src = `/${mode}.png?v=${s.version}`;
      img.dataset.mode = mode;
    }
    document.getElementById("info").innerHTML =
      `<b>${s.title || "On screen"}:</b> ${s.birds.join(", ") || "no birds"}<br>` +
      (s.missing.length ? `<b>No art yet:</b> ${s.missing.join(", ")}<br>` : "") +
      `Updated ${s.updated}` + (s.hold ? " (held overnight, as the panel would)" : "") + (s.error ? `<br><b>Mic Pi unreachable:</b> ${s.error}` : "") +
      `<br>${mode === "eink" ? "E-ink simulation (C for colour)" : "Colour artwork (E for e-ink)"}`;
  } catch (e) {}
}
document.addEventListener("keydown", e => {
  if (e.key === "c" || e.key === "C") mode = "color";
  if (e.key === "e" || e.key === "E") mode = "eink";
  tick();
});
tick(); setInterval(tick, 30000);
</script></body></html>
"""


class Frame:
    """The latest render, refreshed by a background thread."""

    def __init__(self, cfg: dict, station: str, panel_hours: bool = False):
        self.cfg, self.station, self.panel_hours = cfg, station, panel_hours
        self.library = SpriteLibrary(Path(cfg["art_dir"]))
        self.lock = threading.Lock()
        self.signature = None
        self.state = {"version": 0, "birds": [], "missing": [], "updated": "never", "error": ""}
        self.png = {}

    def refresh(self) -> None:
        try:
            now, recent = sources.from_station_api(self.station, timedelta(minutes=self.cfg["linger_minutes"]))
            # The station's own clock, so the container's time zone doesn't matter.
            hold = self.panel_hours and not scenes.in_hours(now, self.cfg["on_time"], self.cfg["off_time"])
            hold_sig = f"hold|{scenes.bird_day_start(now, self.cfg['on_time']).date()}"
            if hold and self.signature == hold_sig:
                with self.lock:
                    self.state.update(updated=f"{now:%H:%M}", error="")
                return
            scene = scenes.pick([] if hold else recent, now, self.cfg, self.library.drawable,
                                lambda a, b: sources.from_station_hours(self.station, a, b))
        except Exception as e:  # keep the last picture, as the real frame does
            with self.lock:
                self.state = {**self.state, "error": str(e), "updated": time.strftime("%H:%M")}
            print(f"mic Pi unreachable: {e}", flush=True)
            return
        sig = hold_sig if hold else \
            f"{scene.view}|{live_signature(scene.entries, scene.day, self.library, False, scene.recent)}"
        name = lambda sci, common: registry().resolve(sci, common).uk_name  # noqa: E731
        birds = [name(s, c) + (" (now)" if s in scene.recent else "")
                 for s, c, _ in scene.entries if self.library.drawable(s)]
        missing = sorted(name(s, c) for s, c, _ in scene.entries if not self.library.has(s))
        redraw = sig != self.signature or not self.png  # only this thread writes them
        if redraw:  # drawn outside the lock, so page requests aren't held up meanwhile
            image, _, _ = render_live(scene.entries, scene.day, self.library,
                                      style_for({**self.cfg, "title": scene.title}), False, scene.recent)
            indexed = eink.quantize(image, saturation=self.cfg["dither_saturation"],
                                    contrast=self.cfg["dither_contrast"])
            png = {"color": encode(image), "eink": encode(eink.simulated(indexed))}
        with self.lock:
            if redraw:
                self.png = png
                self.signature = sig
                self.state["version"] += 1
                held = " (held overnight)" if hold else ""
                print(f"{now:%H:%M} {scene.title}{held}: {', '.join(birds) or '(no birds)'}", flush=True)
            self.state.update(hold=hold, title=scene.title, birds=birds, missing=missing,
                              updated=f"{now:%H:%M}", error="")

    def loop(self, every: int) -> None:
        while True:
            time.sleep(every)
            self.refresh()


def encode(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def handler(frame: Frame):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            with frame.lock:
                if path == "/":
                    body, kind = PAGE.encode(), "text/html; charset=utf-8"
                elif path == "/state.json":
                    body, kind = json.dumps(frame.state).encode(), "application/json"
                elif path in ("/eink.png", "/color.png") and frame.png:
                    body, kind = frame.png[path[1:-4]], "image/png"
                else:
                    self.send_error(404)
                    return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--station", default="http://birdnet.local", help="the mic Pi (default %(default)s)")
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to serve the whole network (default %(default)s)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--panel-hours", action="store_true",
                    help="hold 'Birds of Today' overnight, as the panel does")
    ap.add_argument("--every", type=int, default=120, help="seconds between checks (default %(default)s)")
    args = ap.parse_args()

    frame = Frame(settings.load(), args.station, args.panel_hours)
    frame.refresh()
    threading.Thread(target=frame.loop, args=(args.every,), daemon=True).start()
    print(f"Web frame: http://{args.host}:{args.port}  (Ctrl-C to stop)", flush=True)
    ThreadingHTTPServer((args.host, args.port), handler(frame)).serve_forever()


if __name__ == "__main__":
    main()
