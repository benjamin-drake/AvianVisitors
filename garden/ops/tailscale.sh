#!/usr/bin/env bash
# Remote access: put this Pi on your Tailscale network so you can SSH in from anywhere.
#
#   garden/ops/tailscale.sh birdnet       # on the mic Pi
#   garden/ops/tailscale.sh birdframe     # on the frame Pi
#
# Then from your Mac (with Tailscale installed and signed in): ssh <user>@birdnet
#
# No router changes at the other house: both Pis dial out to Tailscale, which
# also copes with the broadband's address changing. Tailscale SSH means no SSH
# keys to manage; your Tailscale login is the credential.
set -euo pipefail
NAME=${1:?usage: $0 <hostname, e.g. birdnet or birdframe>}

if ! command -v tailscale >/dev/null; then
  echo "Installing Tailscale (adds Tailscale's apt repository)..."
  curl -fsSL https://tailscale.com/install.sh | sh
fi
sudo systemctl enable --now tailscaled

# --ssh: Tailscale handles SSH auth (normal sshd keeps working on the LAN too).
# Prints a login link the first time: open it and sign in to YOUR account.
sudo tailscale up --ssh --hostname="$NAME"
sudo tailscale set --auto-update

echo
tailscale status --self --peers=false
cat <<EOF

Two things to do in the Tailscale admin console (https://login.tailscale.com/admin/machines):
  1. On '$NAME': ... menu > Disable key expiry. Otherwise it drops off the network
     after 180 days and someone at that house has to log it back in.
  2. Check MagicDNS is on (DNS tab), so 'ssh $USER@$NAME' works by name.
EOF
