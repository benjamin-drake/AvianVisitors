#!/usr/bin/env bash
# From the Mac: split any new sprite sheets, then copy the art to both Pis.
# Your art stays out of the (public) GitHub fork; this is how it gets onto the Pis.
#
#   garden/ops/push-art.sh                     # to birdnet and birdframe (Tailscale names)
#   garden/ops/push-art.sh pi@birdnet.local    # or any SSH destinations
set -euo pipefail
GARDEN=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
HOSTS=("$@")
[ ${#HOSTS[@]} -gt 0 ] || HOSTS=(birdnet birdframe)

"$GARDEN/.venv/bin/python" "$GARDEN/split_sprites.py"
for h in "${HOSTS[@]}"; do
  echo "-> $h"
  rsync -a --delete --exclude '_check.png' "$GARDEN/art/" "$h:garden/garden/art/"
done
echo "Done. The frame picks new art up at its next 15-minute check (or run frame.py --force on it)."
