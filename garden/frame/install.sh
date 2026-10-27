#!/usr/bin/env bash
# Frame Pi (Raspberry Pi Zero W / Zero 2 W + Waveshare 9.7" e-Paper HAT+ (E)) setup:
#
#   ~/garden/garden/frame/install.sh [--station http://birdnet.local]
#
# Works on 32-bit (Zero W) and 64-bit Raspberry Pi OS. Safe to re-run. Enables
# SPI, installs the Python bits from apt (no compiling on a Zero), keeps SD
# writes low, and adds a timer that runs frame.py every 15 minutes. A reboot
# is needed the first time, to bring SPI up.
set -euo pipefail

GARDEN=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DATA=$HOME/garden-data
STATION=http://birdnet.local

while [ $# -gt 0 ]; do
  case "$1" in
    --station) STATION=$2; shift 2 ;;
    *) echo "usage: $0 [--station URL]" >&2; exit 64 ;;
  esac
done

say() { printf '\n== %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
[ "$EUID" -ne 0 ] || die "run as your normal user, not root"

say "1/5 Packages"
echo "  $(tr -d '\0' < /proc/device-tree/model 2>/dev/null), $(getconf LONG_BIT)-bit OS"
sudo apt-get update -qq
sudo apt-get install -y python3-venv python3-numpy python3-pil python3-spidev \
  python3-gpiozero python3-lgpio >/dev/null
[ -d "$GARDEN/.venv" ] || python3 -m venv --system-site-packages "$GARDEN/.venv"
"$GARDEN/.venv/bin/python" -c "import numpy, PIL, spidev, gpiozero" || die "Python packages missing"

say "2/5 SPI"
reboot_needed=false
if [ ! -e /dev/spidev0.0 ]; then
  sudo raspi-config nonint do_spi 0
  reboot_needed=true
  echo "  SPI enabled (reboot needed)"
else
  echo "  SPI already on"
fi
sudo usermod -aG spi,gpio "$USER"

say "3/5 Fewer SD card writes"
"$GARDEN/ops/low-writes.sh" 256

say "4/5 Settings"
mkdir -p "$DATA"
if [ ! -f "$DATA/config.json" ]; then
  printf '{\n  "station_url": "%s",\n  "rotate": 0\n}\n' "$STATION" > "$DATA/config.json"
  echo "  wrote $DATA/config.json (station: $STATION)"
else
  echo "  keeping $DATA/config.json"
fi
if ! ls "$GARDEN"/art/*/pose_1.png >/dev/null 2>&1; then
  echo "  no bird art yet: from the Mac run garden/ops/push-art.sh"
fi

say "5/5 Timer"
sudo tee /etc/systemd/system/garden-frame.service >/dev/null <<EOF
[Unit]
Description=Garden birds e-ink frame
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$USER
ExecStart=$GARDEN/.venv/bin/python $GARDEN/frame/frame.py
TimeoutStartSec=5min
EOF
sudo tee /etc/systemd/system/garden-frame.timer >/dev/null <<EOF
[Unit]
Description=Garden birds e-ink frame, every 15 minutes

[Timer]
OnBootSec=2min
OnCalendar=*:00/15
AccuracySec=30s

[Install]
WantedBy=timers.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now garden-frame.timer >/dev/null
systemctl list-timers garden-frame.timer --no-pager | head -2

say "Done"
if $reboot_needed; then
  echo "Reboot now (sudo reboot); the frame draws about 2 minutes after it comes back."
else
  echo "Try it: $GARDEN/.venv/bin/python $GARDEN/frame/frame.py --force"
fi
echo "Logs: journalctl -u garden-frame    Health: $GARDEN/ops/health.sh"
