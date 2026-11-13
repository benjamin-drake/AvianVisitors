# Garden birds

An e-ink bird frame built on AvianVisitors. A Raspberry Pi 3B runs BirdNET-Pi with a
microphone outside. A Pi Zero W (or Zero 2 W) drives a Waveshare 9.7" e-Paper HAT+ (E)
(Spectra 6, 1120x784) showing the birds heard today, the last hour's drawn larger,
from your own illustrations.

```
 mic outside ── Pi 3B "birdnet"                      Pi Zero W "birdframe"
                 stock AvianVisitors/BirdNET-Pi  <──── every 15 min: who was heard today,
                 + garden/ (this folder):        HTTP   and in the last 60 min? Redraw only
                   00:10 archive, hourly log,           if that changed
                         drawing queue
                   07:00 morning summary (email/text)
        both on Tailscale ─── ssh from anywhere
```

**Why this folder is separate from the rest of the repo.** BirdNET-Pi on the 3B is the
stock upstream install (Twarner491/AvianVisitors, branch `avian-visitors`). Its updater
refuses any other origin, so "Pull latest" keeps working. This `garden/` folder is a
second, separate checkout of this fork on each Pi at `~/garden`. It changes no upstream
files. The frame reads upstream's own API (`avian/api/birdnet-api.php?action=recent`).

**Your art stays off GitHub.** The fork is public, so `sheets/` and `art/` are gitignored.
`ops/push-art.sh` copies the art to the Pis instead.

## On the Mac

```bash
cd garden && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python split_sprites.py                       # sheets/*.png -> art/<species>/pose_1..5.png
.venv/bin/python fake_detections.py --start 2026-10-27 > detections.jsonl
.venv/bin/python preview.py detections.jsonl --at 2026-10-27T08:30
.venv/bin/python preview.py detections.jsonl --day 2026-10-27       # contact sheet of the whole day
.venv/bin/python preview.py detections.jsonl --archive 2026-10-27
ops/push-art.sh                                         # once the Pis exist: split + copy art to both
```

**Sprite sheets.** Five poses in a row, in this order: perched side-on, front-on, singing,
in flight, feeding. They can be transparent or on white.
- **Species** is read from the file name. If the name is ambiguous, pin it in
  `sheets/names.json`.
- **Edge trim.** `--trim 2` (the default) shaves the fringe off each bird's outline.
- **Check the result** in `art/<species>/_check.png`.

**Look of the frame** (`config.json`):
- `orientation`: `portrait` (784x1120, as hung) or `landscape`.
- `main_view`: `today` (the day's birds, the last hour's drawn larger) or `hour` (the
  last hour's birds only, as first designed). `max_birds`: at most this many on screen (20).
- `front_on`: how often a bird faces straight out (pose 2). 0.3 makes it rare, 1 as
  common as the other poses, 0 never.
- `labels`: each bird's UK name in small black letters under it, field-guide style
  (`label_font` Caveat, `label_size` 24; Fraunces-DisplayItalic.ttf is the tidier
  alternative). Black, not grey: the panel has no grey ink. Names are packed with their
  birds, so they never sit on another bird; birds come out a little smaller.
- `title_today` "Birds of Today", `title_yesterday`, and `title` "Birds of the Hour" (hour view),
  set on a gentle arch (`title_arch`, in degrees; 0 = straight).
- `title_font`: any file in `fonts/`. Fraunces, Fraunces Italic, Instrument Serif and Caveat
  are included. `title_size` sets the size.
- `archive_title`: "Birds of {date}" for the midnight collage.

**A stand-in frame on the Mac** until the panel arrives: `.venv/bin/python webframe.py`, then open
<http://localhost:8765> and go full screen. It shows the live birds from the mic Pi with your art
(press C for colour, E for the e-ink simulation). Away from home use `--station http://birdnet`.
For an always-on copy, `ops/webframe/deploy.sh` runs it in Docker on the home server
(<http://linuxserver.tail8c80fe.ts.net:8765>), following the panel's hours. Re-run it after new art.
With `WALL` set in `ops/webframe/compose.yaml` it opens on **On the wall** (W): the real frame's
own last picture, fetched over Tailscale from the frame Pi's `frame/serve.py` (port 8090), with
when it was drawn and when the frame last checked in.

`mockup.py` draws every species you've drawn, once each, under each title font, and saves
`out/mockup/fonts.png` to compare them. Change the arrangement with `--seed 2`.
Poses are dealt like cards so birds on screen share as few poses as possible.

**Preview output.** `*_eink.png` is the panel simulation using measured Spectra 6 colours.
`*_truesize.png` opens at real size in Preview (View > Actual Size).

## Building the Pis

Do all of this at home, on your own wifi. Then add your in-laws' wifi (step 4) before
taking the Pis over.

### 1. Flash both SD cards
Use Raspberry Pi Imager with Raspberry Pi OS **Lite**:
- **3B (mic): 64-bit.** BirdNET-Pi won't install on anything else.
- **Zero W (frame): 32-bit.** The original Zero W can't run 64-bit, and the frame code
  doesn't need it. (If you swap in a Zero 2 W or 3A+ later, either works.)

In Imager's settings:
- Hostname: `birdnet` for the 3B, `birdframe` for the Zero W.
- Your username and password, with SSH turned on.
- Your home wifi, and Wireless LAN country GB.

### 2. Mic Pi (3B)

```bash
ssh you@birdnet.local
curl -s https://raw.githubusercontent.com/Twarner491/AvianVisitors/avian-visitors/newinstaller.sh | bash
# ...reboots. Then:
git clone --filter=blob:none --sparse -b garden https://github.com/benjamin-drake/AvianVisitors.git ~/garden
git -C ~/garden sparse-checkout set garden
~/garden/garden/mic/setup.sh
~/garden/garden/ops/tailscale.sh birdnet
sudo reboot
```

`setup.sh` makes these changes for a 1 GB Pi 3B:
- **Settings:** mono mic, the 52.77°N 0.89°W location, and birds kept on screen across
  midnight. It also keeps only the best 30 clips per species.
- **Services turned off:** the live audio stream (Icecast), live spectrogram, Streamlit stats
  page, chart renderer, web log viewer and web terminal. Turn one back on with
  `sudo systemctl enable --now <name>`.
- **SD card writes:** logs are kept in RAM, swap moves to compressed RAM (zram) instead of a
  file on the card, and the card is mounted with `noatime`. BirdNET-Pi already records its
  audio chunks to RAM.

**Species list (Leicestershire + Rutland):** get a free key at <https://ebird.org/api/keygen>, then

```bash
~/garden/garden/.venv/bin/python ~/garden/garden/mic/ebird_species.py --key YOUR_KEY
~/garden/garden/mic/setup.sh        # installs the list into BirdNET-Pi
```

**Morning summary:** put one or more Apprise URLs in `~/garden-data/notify.txt`. Examples
are in `mic/summary.py`: email, ntfy, Telegram or SMS. Test it with
`~/garden/garden/.venv/bin/python ~/garden/garden/mic/summary.py`.

### 3. Frame Pi (Zero W + panel)

The Zero W needs a 40-pin header to plug into the panel's HAT. If yours is a plain "W"
rather than a "WH", solder on a 2x20 header (about £1) or fit a solderless hammer-in one
(about £5, comes with a jig). On a Zero W expect a render to take a few seconds plus about
30 s of panel refresh, run from a 15-minute timer. Check the first few runs with
`journalctl -u garden-frame`.

```bash
ssh you@birdframe.local
sudo apt install -y git
git clone --filter=blob:none --sparse -b garden https://github.com/benjamin-drake/AvianVisitors.git ~/garden
git -C ~/garden sparse-checkout set garden
~/garden/garden/frame/install.sh                 # enables SPI, timer every 15 min
~/garden/garden/ops/tailscale.sh birdframe
sudo reboot
```

Then from the Mac, run `garden/ops/push-art.sh`. The frame draws at its next quarter-hour.
If it's mounted upside down, set `"rotate": 180` in `~/garden-data/config.json`.

### 4. Before taking them to the other house
- Add their wifi to both Pis, so they join it on arrival. They'll still use yours at home:
  ```bash
  sudo nmcli connection add type wifi con-name inlaws ssid "THEIR-SSID" \
       wifi-sec.key-mgmt wpa-psk wifi-sec.psk "THEIR-PASSWORD" connection.autoconnect yes
  ```
  Both Pis are 2.4 GHz only. Their router needs a 2.4 GHz network; most combined networks
  include one.
- In the Tailscale admin console, **Disable key expiry** on both machines.
- Run `ops/health.sh` on both and check power shows "ok". The 3B needs a proper 2.5 A supply.

### 5. The frame's printed back

`enclosure/back.py` models the back that holds the panel in the wooden frame and carries the
boards (`pip install manifold3d numpy matplotlib`, then `python enclosure/back.py --preview`;
STLs and pictures land in `out/enclosure/`). Every measurement is a setting at the top.

- **Wooden frame:** cut the rebate opening **160.9 x 212.8 mm** (the panel, 1 mm all round,
  plus 4 mm on the ribbon side for its bend). The back's flange overlaps the frame by 14 mm
  and screws on with 8 small countersunk wood screws (No.4 / 3 mm x 12 mm), so it lifts off.
- **Stack in the rebate, front to back:** glass (optional), your mount, the panel, then the
  back's 2.5 mm plug pressing it all forward. Make the rebate deep enough for the first three
  plus the plug, or change `PLUG_T`; a thin foam sheet takes up any slack.
- **Ribbon:** the panel's ribbon leaves its left edge (seen from the front). It bends
  back behind the panel, never towards the front, into the adapter board. The adapter is
  screwed into the window with its connectors facing the panel (4 x M2 x 6 mm screws, no longer, from
  outside, nuts on the panel side). Its slotted holes allow 3 mm of adjustment.
- **Boards:** the HAT and the Pi Zero go on 6 mm posts (M2.5 self-tapping x 6 mm, or heat-set
  inserts with `PILOT = 3.5`). This Zero's header is on its underside, so mount it logo side
  up, SD card at the bottom. The power cable presses into the channel down to the bottom edge.
- **Stand:** the 103 mm leg slides into the angled socket. The frame then leans back 15°.
- **Printing:** the back prints panel-face down with no supports. On the H2C it fits in one piece.
  Use wood PLA with 3 walls and 15% infill; the leg is better at 100% infill or in plain PLA.

## Looking after it from Newcastle

```bash
ssh you@birdnet   ~/garden/garden/ops/health.sh    # mic, analysis backlog, today's count
ssh you@birdframe ~/garden/garden/ops/health.sh    # last redraw, last contact with the mic
curl -O http://birdframe:8090/wall.png               # what's on the wall right now (or the web frame's W view)
ssh you@birdframe '~/garden/garden/.venv/bin/python ~/garden/garden/frame/frame.py --force'
journalctl -u garden-frame -n 50                   # frame log (on the frame Pi)
```

**Updating:**
- Garden code: `git -C ~/garden pull` on each Pi.
- BirdNET-Pi itself: Tools > Pull latest in its web UI, as usual. Re-run `mic/setup.sh`
  afterwards in case an update turned services back on.

**Files on the mic Pi** (in `~/garden-data/`):
- `log/YYYY-MM.csv`: each hour's species and counts, kept indefinitely. They open in Excel.
- `archive/YYYY-MM-DD.png`: each day's collage.
- `missing_art.csv`: species heard that have no art yet. This is your drawing queue.
- `summaries/`: the morning summaries.

## How the frame decides what to show
- **On screen:** "Birds of Today", every bird with art heard so far today, sized by its
  calls. Birds heard in the last 60 minutes (`linger_minutes`) are drawn about three
  times the area, so the frame still shows who is about right now. Before the first
  bird of the morning it shows "Birds of Yesterday", so the screen is never empty.
  The day runs from `on_time` (05:00), not midnight, so a 2 a.m. owl counts towards
  the evening before and appears in the next morning's "Birds of Yesterday".
- **Busy days:** at most `max_birds` (20) are drawn: the last hour's first, then the
  most heard.
- **Hour view** (`"main_view": "hour"`): only the last hour's birds, falling back to
  "Birds of Today" and then "Birds of Yesterday". It was sparse in testing, especially
  in winter, hence the change.
- **Scene changes:** when a bird arrives, or one starts or stops being "this hour", every bird gets a fresh pose (of five),
  mirroring, size and position. These are seeded by date and the set of birds, so a given
  scene always looks the same that day.
- **Packing:** ported from upstream's silhouette nester. Sizes come from calls^0.35 times the
  species size in `species.csv`, with no bird larger than 15% of the screen.
- **Hours:** the frame follows the birds from 05:00 to 23:00 (`on_time`, `off_time`).
  At 23:00 it draws "Birds of Today" and holds it overnight without redrawing; e-ink
  keeps a picture with no power. The mic keeps listening all night, so owls still
  reach the logs, the archive, the summary and the next morning's "Birds of Yesterday".
- **Always light:** the same pale background at any hour. A dark night style (black
  background, pale outlines, between sunset and sunrise) is still there if you want it:
  set `"night_mode": true`.
- **Redraws:** checked every 15 minutes, and the panel only redraws when the species with art,
  the ones heard this hour, or day/night mode change. There's also a daily redraw to keep the panel healthy.
- **If the mic Pi goes quiet:** the picture stays as it was. After 3 hours without contact the
  frame shows a small hollow circle in the corner, meaning "not live".
- **Colour:** dithering uses Pimoroni's measured Spectra 6 colours, then maps pixels straight
  to Waveshare's panel codes.
