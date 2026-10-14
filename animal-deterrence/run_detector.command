#!/usr/bin/env bash
# ==============================================================================
# Smart Animal Deterrence & Object Detection System Launcher
# Double-click this file in macOS Finder to start the detector screen.
# ==============================================================================

# Change working directory to this script's directory
cd "$(dirname "$0")"

clear
echo "=================================================================="
echo "         SMART ANIMAL DETERRENCE & OBJECT DETECTOR                "
echo "=================================================================="
echo ""

# Find Python 3 with ultralytics & cv2 installed
if [ -x "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3" ]; then
    PYTHON_CMD="/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
else
    echo " [Error] Python 3 not found in standard paths."
    echo " Please install Python 3 or add it to your PATH."
    read -p "Press [Enter] to exit..."
    exit 1
fi

echo "Probing connected camera hardware..."
$PYTHON_CMD -c "
import cv2
found = 0
for i in range(6):
    c = cv2.VideoCapture(i)
    if c.isOpened():
        ret, _ = c.read()
        if ret:
            w = int(c.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(c.get(cv2.CAP_PROP_FRAME_HEIGHT))
            default_tag = ' (Default)' if i == 0 else ''
            print(f'   [{i}] Camera #{i} -> {w}x{h}{default_tag}')
            found += 1
        c.release()
if found == 0:
    print('   [!] No physical cameras detected.')
"
echo "   [f] File Input (Drag & drop a video or image file here)"
echo "   [s] Simulation Feed (Test pattern without camera)"
echo ""
echo "------------------------------------------------------------------"
read -p " Select Camera Input [0-4/f/s] (Press Enter for Default #0): " CHOICE

if [ -z "$CHOICE" ]; then
    CHOICE="0"
fi

if [ "$CHOICE" = "f" ] || [ "$CHOICE" = "F" ]; then
    echo ""
    read -p " Drag & Drop your video or image file here and press Enter: " FILE_PATH
    # Remove quotes from drag-and-drop
    FILE_PATH=$(echo "$FILE_PATH" | tr -d "'" | tr -d '"' | xargs)
    echo " Starting detection on file: $FILE_PATH"
    echo ""
    $PYTHON_CMD main.py --source "$FILE_PATH"
elif [ "$CHOICE" = "s" ] || [ "$CHOICE" = "S" ]; then
    echo " Starting in Simulation Mode..."
    echo ""
    $PYTHON_CMD main.py --source "sim"
else
    echo " Starting Camera #$CHOICE..."
    echo " TIP: While viewing, press 'c' on your keyboard to switch cameras live!"
    echo ""
    $PYTHON_CMD main.py --source "$CHOICE"
fi

EXIT_CODE=$?
echo ""
echo "Detection screen closed."
if [ $EXIT_CODE -ne 0 ]; then
    echo "Exited with code $EXIT_CODE"
fi
read -p "Press [Enter] to close this window..."
