# Garden birds

An e-ink bird frame built on AvianVisitors. A Raspberry Pi 3B runs BirdNET-Pi with a
microphone outside. A Pi Zero W (or Zero 2 W) drives a Waveshare 9.7" e-Paper HAT+ (E)
(Spectra 6, 1120x784) showing the birds heard in the last hour, drawn from your own
illustrations.

```
 mic outside ── Pi 3B "birdnet"                      Pi Zero W "birdframe"
                 stock AvianVisitors/BirdNET-Pi  <──── every 15 min: who was heard in the
                 + garden/ (this folder):        HTTP   last 60 min? Redraw only if that
                   00:10 archive, hourly log,           changed (or day/night flipped)
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
- `title`: "Birds of the Hour", set on a gentle arch (`title_arch`, in degrees; 0 = straight).
- `title_font`: any file in `fonts/`. Fraunces, Fraunces Italic, Instrument Serif and Caveat
  are included. `title_size` sets the size.
- `archive_title`: "Birds of {date}" for the midnight collage.

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

## Looking after it from Newcastle

```bash
ssh you@birdnet   ~/garden/garden/ops/health.sh    # mic, analysis backlog, today's count
ssh you@birdframe ~/garden/garden/ops/health.sh    # last redraw, last contact with the mic
scp you@birdframe:/dev/shm/garden-frame/frame.png .   # what's on the wall right now
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
- **On screen:** a bird appears when heard and stays 60 minutes after it was last heard
  (`linger_minutes`). Each new detection resets that timer.
- **Scene changes:** when a bird arrives or leaves, every bird gets a fresh pose (of five),
  mirroring, size and position. These are seeded by date and the set of birds, so a given
  scene always looks the same that day.
- **Packing:** ported from upstream's silhouette nester. Sizes come from calls^0.35 times the
  species size in `species.csv`, with no bird larger than 15% of the screen.
- **Night:** between sunset and sunrise at 52.77°N, 0.89°W, a black background with a 2 px
  pale outline.
- **Redraws:** checked every 15 minutes, and the panel only redraws when the species with art,
  or day/night mode, changes. There's also a daily redraw to keep the panel healthy.
- **If the mic Pi goes quiet:** the picture stays as it was. After 3 hours without contact the
  frame shows a small hollow circle in the corner, meaning "not live".
- **Colour:** dithering uses Pimoroni's measured Spectra 6 colours, then maps pixels straight
  to Waveshare's panel codes.
