#!/usr/bin/env bash
# ==============================================================================
# Smart Animal Deterrence & Object Detection System Launcher (Workspace Root)
# Double-click this file in macOS Finder to launch the camera detection screen.
# ==============================================================================

# Change working directory to the animal-deterrence project folder
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR/animal-deterrence"

exec ./run_detector.command
