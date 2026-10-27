#!/usr/bin/env bash
# One-screen health check for either Pi. Run it over SSH:
#   ssh birdnet ~/garden/garden/ops/health.sh
#   ssh birdframe ~/garden/garden/ops/health.sh
set -uo pipefail
GARDEN=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DATA=$HOME/garden-data

line() { printf '%-18s %s\n' "$1" "$2"; }
echo "== $(hostname) ($(tr -d '\0' < /proc/device-tree/model 2>/dev/null))"
line "up" "$(uptime -p)"
line "temperature" "$(vcgencmd measure_temp 2>/dev/null | cut -d= -f2)"
t=$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)
case "$t" in
  0x0|"") line "power" "ok" ;;
  *) line "power" "THROTTLED/UNDER-VOLTAGE ($t): check the power supply" ;;
esac
line "memory" "$(free -m | awk '/Mem:/{printf "%d of %d MB used", $3, $2}')"
line "swap" "$(swapon --show=NAME,USED --noheadings | tr '\n' ' ')"
line "disk" "$(df -h / | awk 'NR==2{print $3" of "$2" used ("$5")"}')"
line "tailscale" "$(tailscale ip -4 2>/dev/null || echo 'not running')"
line "wifi" "$(iwgetid -r 2>/dev/null) $(awk 'NR==3{print int($3)"/70"}' /proc/net/wireless 2>/dev/null)"

if [ -d "$HOME/BirdNET-Pi" ]; then
  echo "== mic"
  for s in birdnet_recording birdnet_analysis caddy; do line "$s" "$(systemctl is-active $s)"; done
  db=$HOME/BirdNET-Pi/scripts/birds.db
  line "last detection" "$(sqlite3 -readonly "$db" "SELECT Date||' '||Time||'  '||Com_Name FROM detections ORDER BY Date DESC, Time DESC LIMIT 1" 2>/dev/null)"
  line "today" "$(sqlite3 -readonly "$db" "SELECT COUNT(*)||' detections, '||COUNT(DISTINCT Sci_Name)||' species' FROM detections WHERE Date=date('now','localtime')" 2>/dev/null)"
  # Audio chunks waiting to be analysed. A growing pile means the 3B can't keep up.
  backlog=$(find "$HOME/BirdSongs/StreamData" -name '*.wav' 2>/dev/null | wc -l)
  line "analysis backlog" "$backlog chunk(s)$([ "$backlog" -gt 3 ] && echo '  <- falling behind')"
  line "mic" "$(arecord -l 2>/dev/null | grep -m1 card || echo 'NO USB MIC FOUND')"
  line "summary" "$(systemctl list-timers garden-summary.timer --no-legend 2>/dev/null | awk '{print "next "$1" "$2" "$3}')"
  [ -f "$DATA/missing_art.csv" ] && line "to draw next" "$(sed -n '2,4p' "$DATA/missing_art.csv" | cut -d, -f1,3 | tr '\n' ';')"
fi

if [ -f /etc/systemd/system/garden-frame.service ]; then
  echo "== frame"
  line "timer" "$(systemctl list-timers garden-frame.timer --no-legend | awk '{print "next "$1" "$2" "$3}')"
  line "station" "$(python3 -c "import json;print(json.load(open('$DATA/config.json'))['station_url'])" 2>/dev/null)"
  if [ -f "$DATA/frame-state.json" ]; then
    python3 - "$DATA/frame-state.json" <<'EOF'
import json, sys, time
s = json.load(open(sys.argv[1]))
ago = lambda k: f"{(time.time() - s[k]) / 60:.0f} min ago" if k in s else "never"
print(f"{'last redraw':<18} {ago('last_refresh')}")
print(f"{'last mic contact':<18} {ago('last_contact')}" + ("  (showing 'no signal')" if s.get("stale_drawn") else ""))
EOF
  fi
  line "art" "$(ls -d "$GARDEN"/art/*/ 2>/dev/null | wc -l) species"
  echo "-- last runs"
  journalctl -u garden-frame -n 6 --no-pager -o cat 2>/dev/null | grep -v '^$' | tail -6
  echo "(the latest render is /dev/shm/garden-frame/frame.png: scp it to see what's on the wall)"
fi
