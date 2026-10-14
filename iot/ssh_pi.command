#!/usr/bin/env bash
# ==============================================================================
# One-Click SSH Login to Raspberry Pi 4 from iot/ folder
# ==============================================================================

clear
echo "Connecting to school@school.local..."
ssh -t school@school.local "cd ~/stjoseph_iot && bash --login"
