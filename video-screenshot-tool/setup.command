#!/bin/bash
# RedArc Video Tool — one-time setup (double-click to run)
# Builds the Python environment, ensures ffmpeg, and compiles the drag-drop app.
set -e
cd "$(dirname "$0")"

echo "──────────────────────────────────────────────"
echo "  RedArc Video Tool — setup"
echo "──────────────────────────────────────────────"

# 1. Python 3
if ! command -v python3 >/dev/null 2>&1; then
  echo "!! Python 3 is required. Install it from https://www.python.org/downloads/ and re-run."
  exit 1
fi

# 2. ffmpeg (system dependency)
if command -v ffmpeg >/dev/null 2>&1 || [ -x /opt/homebrew/bin/ffmpeg ] || [ -x /usr/local/bin/ffmpeg ]; then
  echo "✓ ffmpeg found"
else
  if command -v brew >/dev/null 2>&1; then
    echo "• Installing ffmpeg via Homebrew (this can take a few minutes)..."
    brew install ffmpeg
  else
    echo "!! ffmpeg is not installed, and Homebrew was not found."
    echo "   1) Install Homebrew:  https://brew.sh"
    echo "   2) Then run:          brew install ffmpeg"
    echo "   3) Re-run this setup."
    exit 1
  fi
fi

# 3. Python environment + faster-whisper
if [ ! -d venv ]; then
  echo "• Creating Python environment..."
  python3 -m venv venv
fi
echo "• Installing transcription engine (faster-whisper)..."
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet faster-whisper

# 4. Compile the drag-drop app (in a temp dir to avoid xattr issues, then move)
echo "• Building 'RedArc Video Tool.app'..."
tmp="$(mktemp -d)"
osacompile -o "$tmp/RedArc Video Tool.app" droplet.applescript
xattr -cr "$tmp/RedArc Video Tool.app" 2>/dev/null || true
rm -rf "RedArc Video Tool.app"
mv "$tmp/RedArc Video Tool.app" .
rm -rf "$tmp"

echo "──────────────────────────────────────────────"
echo "  ✓ Setup complete."
echo ""
echo "  To use it: drag a video file onto"
echo "  'RedArc Video Tool.app' in this folder."
echo ""
echo "  (First video downloads the transcription"
echo "   model once — a minute or two — then it's fast.)"
echo "──────────────────────────────────────────────"
