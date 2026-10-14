#!/usr/bin/env bash
# ==============================================================================
# One-Click SSH Login to Raspberry Pi 4 ("school")
# Double-click this file in Finder to open an interactive SSH shell on the Pi.
# ==============================================================================

clear
echo "=================================================================="
echo "          CONNECTING TO RASPBERRY PI (school.local)               "
echo "=================================================================="
echo " Target: school@school.local (IP: 10.180.5.188)"
echo " IoT Dir: ~/stjoseph_iot"
echo " Hardware: Raspberry Pi 4 Model B (Debian / aarch64)"
echo "=================================================================="
echo ""

ssh -t school@school.local "cd ~/stjoseph_iot && bash --login"

EXIT_CODE=$?
echo ""
echo "Session disconnected (code $EXIT_CODE)."
read -p "Press [Enter] to close..."
