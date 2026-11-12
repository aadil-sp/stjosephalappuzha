#!/bin/bash
# Gives the farm controller a fixed internet address so the Android app works from anywhere.
# Run ON THE PI, once, with a free ngrok account (https://dashboard.ngrok.com):
#   bash setup_remote_access.sh <ngrok-authtoken> <static-domain>
#   e.g. bash setup_remote_access.sh 2abc...XYZ calm-owl-123.ngrok-free.app
# Installs ngrok, saves the token and starts the farm-tunnel service at every boot.
# The tunnel only forwards port 8000; the API asks anything from the internet for the
# app access key (see app_access.py).
set -euo pipefail
cd "$(dirname "$0")"
TOKEN="${1:?usage: setup_remote_access.sh <ngrok-authtoken> <static-domain>}"
DOMAIN="${2:?usage: setup_remote_access.sh <ngrok-authtoken> <static-domain>}"
DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN#http://}"; DOMAIN="${DOMAIN%%/*}"

if ! command -v ngrok >/dev/null; then
  echo "Installing ngrok..."
  curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
  echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y ngrok
fi
ngrok config add-authtoken "$TOKEN"

sudo tee /etc/systemd/system/farm-tunnel.service >/dev/null <<UNIT
[Unit]
Description=Smart Farm internet tunnel (ngrok)
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
ExecStart=$(command -v ngrok) http --url=https://$DOMAIN 8000 --log=stdout
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now farm-tunnel
sudo systemctl restart farm-tunnel
sleep 6

KEY=$(python3 -c "import app_access; print(app_access.app_key())")
echo
systemctl is-active --quiet farm-tunnel && echo "Tunnel: running" || { echo "Tunnel: NOT running"; journalctl -u farm-tunnel -n 15 --no-pager; }
echo "Check:   curl -s -o /dev/null -w '%{http_code}\n' https://$DOMAIN/api/telemetry   (401 = working, key needed)"
echo
echo "In the Android app, Settings:"
echo "  Farm address: $DOMAIN"
echo "  Access key:   $KEY"
