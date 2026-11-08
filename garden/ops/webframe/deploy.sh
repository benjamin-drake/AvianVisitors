#!/bin/sh
# Copy the garden code and your art to the mini PC and (re)start the web frame there.
#   garden/ops/webframe/deploy.sh          then open http://linuxserver.tail8c80fe.ts.net:8765
# Run it again after new art or code changes.
set -eu
HOST=${WEBFRAME_HOST:-benjamin@192.168.50.212}
KEY=${WEBFRAME_KEY:-$HOME/.ssh/minipc_migration_ed25519}
DEST=/opt/garden-webframe
GARDEN=$(cd "$(dirname "$0")/../.." && pwd)
SSH="ssh -i $KEY -o IdentitiesOnly=yes"

$SSH "$HOST" "sudo mkdir -p $DEST/garden && sudo chown -R \$(id -u):\$(id -g) $DEST"
rsync -a --delete -e "$SSH" "$GARDEN/ops/webframe/Dockerfile" "$GARDEN/ops/webframe/compose.yaml" "$HOST:$DEST/"
rsync -a --delete -e "$SSH" \
  --exclude .venv --exclude sheets --exclude out --exclude '__pycache__' \
  --exclude '*.jsonl' --exclude '_check.png' --exclude .git \
  "$GARDEN/" "$HOST:$DEST/garden/"
$SSH "$HOST" "cd $DEST && docker compose up -d --build && docker restart garden-webframe >/dev/null && sleep 4 && docker logs --tail 5 garden-webframe"
