#!/usr/bin/env bash
# Cut SD card writes on a Pi: system logs in RAM, compressed RAM swap instead of a
# swap file, no access-time updates. Used by mic/setup.sh and frame/install.sh.
#
#   garden/ops/low-writes.sh [zram size in MB, default 1024]
#
# Safe to re-run. The swap and noatime changes take effect after a reboot.
set -euo pipefail
SIZE=${1:-1024}

sudo mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nStorage=volatile\nRuntimeMaxUse=40M\n' \
  | sudo tee /etc/systemd/journald.conf.d/garden.conf >/dev/null
sudo systemctl restart systemd-journald
echo "  system logs kept in RAM (they reset on reboot; read them with 'journalctl -b')"

if dpkg -s dphys-swapfile >/dev/null 2>&1; then
  sudo dphys-swapfile swapoff >/dev/null 2>&1 || true
  sudo systemctl disable --now dphys-swapfile >/dev/null 2>&1 || true
  echo "  swap file on the SD card: off"
fi
if swapon --show=NAME --noheadings | grep -q zram; then
  echo "  zram swap: already on"
elif systemctl is-enabled zram.service >/dev/null 2>&1; then
  # BirdNET-Pi's own zram.service (installed on small Pis); starts at boot.
  echo "  zram swap: BirdNET-Pi's zram.service will start it after reboot"
else
  sudo apt-get install -y zram-tools >/dev/null
  printf 'ALGO=zstd\nSIZE=%s\nPRIORITY=100\n' "$SIZE" | sudo tee /etc/default/zramswap >/dev/null
  sudo systemctl enable zramswap >/dev/null 2>&1 || true
  sudo systemctl restart zramswap || true
  echo "  zram swap (${SIZE} MB, compressed in RAM): on"
fi

if grep -qE '^\S+\s+/\s+\S+\s+\S*noatime' /etc/fstab; then
  echo "  noatime: already set"
else
  sudo cp /etc/fstab /etc/fstab.garden-backup
  sudo sed -i -E 's|^(\S+\s+/\s+\S+\s+)(\S+)|\1\2,noatime|' /etc/fstab
  echo "  noatime on / after reboot (backup: /etc/fstab.garden-backup)"
fi
