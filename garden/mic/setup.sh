#!/usr/bin/env bash
# Mic Pi (Raspberry Pi 3B) setup, run AFTER the stock AvianVisitors/BirdNET-Pi install:
#
#   ~/garden/garden/mic/setup.sh
#
# Safe to re-run. What it does:
#   1. BirdNET-Pi settings: location, mono mic, keep birds past midnight, cap saved clips
#   2. Turns off the extras a 1 GB Pi 3B can't spare (live stream, spectrogram, stats, charts)
#   3. Fewer SD card writes: logs in RAM, zram swap instead of a swap file, noatime
#   4. Installs the eBird include list if you've built one (garden/mic/ebird_species.py)
#   5. A Python env for the garden code, plus timers: archive + logs at 00:10, summary at 07:00
set -euo pipefail

GARDEN=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DATA=$HOME/garden-data
BIRDNET=$HOME/BirdNET-Pi
CONF=$BIRDNET/birdnet.conf

say() { printf '\n== %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[ "$EUID" -ne 0 ] || die "run as your normal user, not root (it uses sudo where needed)"
[ -f "$CONF" ] || die "$CONF not found: install AvianVisitors/BirdNET-Pi first (newinstaller.sh)"
mkdir -p "$DATA"

json() { python3 -c "import json,sys; print(json.load(open('$GARDEN/config.json'))['$1'])"; }

set_conf() {  # key value  (edits the real file; /etc/birdnet/birdnet.conf links to it)
  if grep -q "^$1=" "$CONF"; then
    sed -i "s|^$1=.*|$1=$2|" "$CONF"
  else
    printf '%s=%s\n' "$1" "$2" >> "$CONF"
  fi
}

say "1/5 BirdNET-Pi settings"
set_conf LATITUDE "$(json latitude)"
set_conf LONGITUDE "$(json longitude)"
set_conf CHANNELS 1              # lavalier mics are mono; halves the audio work
set_conf RESET_AT_MIDNIGHT 0     # the frame's 60-minute window runs across midnight
set_conf BIRDWEATHER_ENABLED 0
set_conf FULL_DISK purge         # never stop recording because the card is full
set_conf PURGE_THRESHOLD 90
set_conf MAX_FILES_SPECIES 30    # keep the 30 best clips per species, not every one
set_conf DATABASE_LANG en        # species.csv matches BirdNET's English names
grep -E '^(LATITUDE|LONGITUDE|CHANNELS|RESET_AT_MIDNIGHT|FULL_DISK|PURGE_THRESHOLD|MAX_FILES_SPECIES)=' "$CONF"

say "2/5 Turning off extras"
# Live audio stream, live spectrogram, Streamlit stats page, chart renderer,
# web log viewer and web terminal: each costs RAM/CPU (Streamlit alone is
# ~100 MB) and the frame needs none of them. Recording, analysis and the web
# UI stay on. Undo with: sudo systemctl enable --now <name>
for s in livestream icecast2 spectrogram_viewer birdnet_stats chart_viewer birdnet_log web_terminal; do
  if systemctl list-unit-files "$s.service" --no-legend 2>/dev/null | grep -q .; then
    sudo systemctl disable --now "$s.service" >/dev/null 2>&1 || true
    echo "  off: $s"
  fi
done

say "3/5 Fewer SD card writes"
# BirdNET-Pi already records its 15 s audio chunks to RAM (StreamData is tmpfs).
"$GARDEN/ops/low-writes.sh" 1024

say "4/5 Species list"
if [ -f "$DATA/include_species_list.txt" ]; then
  cp "$DATA/include_species_list.txt" "$BIRDNET/include_species_list.txt"
  echo "  $(wc -l < "$BIRDNET/include_species_list.txt") species from eBird (Leicestershire + Rutland)"
else
  echo "  none yet. Build it with:"
  echo "    $GARDEN/.venv/bin/python $GARDEN/mic/ebird_species.py --key YOUR_EBIRD_KEY && $0"
  echo "  (until then BirdNET-Pi's own location filter decides what's plausible)"
fi

say "5/5 Garden code and timers"
sudo apt-get install -y python3-venv python3-numpy python3-pil >/dev/null
[ -d "$GARDEN/.venv" ] || python3 -m venv --system-site-packages "$GARDEN/.venv"
"$GARDEN/.venv/bin/python" -c "import numpy, PIL" || die "numpy/Pillow missing from the venv"

unit() {  # name description command schedule
  sudo tee "/etc/systemd/system/$1.service" >/dev/null <<EOF
[Unit]
Description=$2
After=network-online.target

[Service]
Type=oneshot
User=$USER
Nice=10
ExecStart=$3
EOF
  sudo tee "/etc/systemd/system/$1.timer" >/dev/null <<EOF
[Unit]
Description=$2

[Timer]
OnCalendar=$4
Persistent=true

[Install]
WantedBy=timers.target
EOF
}
unit garden-nightly "Garden birds: archive collage, hourly log, drawing queue" \
  "$GARDEN/.venv/bin/python $GARDEN/mic/nightly.py" "*-*-* 00:10:00"
unit garden-summary "Garden birds: morning summary" \
  "$GARDEN/.venv/bin/python $GARDEN/mic/summary.py" "*-*-* 07:00:00"
sudo systemctl daemon-reload
sudo systemctl enable --now garden-nightly.timer garden-summary.timer >/dev/null
systemctl list-timers 'garden-*' --no-pager | head -4

sudo systemctl restart birdnet_recording birdnet_analysis 2>/dev/null || true
say "Done"
echo "Check it with: $GARDEN/ops/health.sh    (a reboot applies the swap and noatime changes)"
