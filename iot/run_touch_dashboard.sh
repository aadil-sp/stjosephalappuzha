#!/usr/bin/env bash
# ==============================================================================
# Run IoT Smart Agriculture Touch Dashboard on Raspberry Pi 3.5" LCD Screen
# ==============================================================================

cd "$(dirname "$0")"

echo "=========================================================="
echo "  🌿 SMART IOT AGRI-DASHBOARD (3.5\" TOUCHSCREEN)"
echo "  Target: 480x320 ADS7846 Resistive LCD (/dev/fb1)"
echo "  Web UI: http://school.local:8000"
echo "=========================================================="

# Export Framebuffer for 3.5" LCD if running directly on console/service
if [ -e "/dev/fb1" ]; then
    export QT_QPA_PLATFORM=linuxfb:fb=/dev/fb1
fi

python3 main.py --fullscreen "$@"
