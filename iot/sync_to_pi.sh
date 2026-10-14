#!/usr/bin/env bash
# Sync local IoT code to Raspberry Pi
cd "$(dirname "$0")"

TARGET="school.local"
if ! ping -c 1 -W 1 school.local >/dev/null 2>&1; then
    TARGET="10.180.5.188"
fi

echo "Syncing local iot/ files to school@$TARGET:~/stjoseph_iot/..."
rsync -avz -e "ssh -o StrictHostKeyChecking=no" \
  --exclude '.git' --exclude '__pycache__' --exclude 'node_modules' --exclude '.DS_Store' \
  ./ school@"$TARGET":~/stjoseph_iot/

echo "Sync complete!"
