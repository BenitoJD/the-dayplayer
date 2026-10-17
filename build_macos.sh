#!/bin/bash
# Build a standalone Circadia.app for macOS (no Python needed by the user).
# Result: dist/Circadia.app  ->  zip it for download with:
#   ditto -c -k --sequesterRsrc --keepParent dist/Circadia.app Circadia-macOS.zip
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/pyinstaller ]; then
  echo "installing pyinstaller into .venv ..."
  .venv/bin/pip install -q pyinstaller
fi
rm -rf build dist
.venv/bin/pyinstaller --noconfirm --name Circadia --windowed \
  --icon assets/icon.icns --add-data "assets:assets" \
  --hidden-import dayplayer.dashboard --hidden-import dayplayer.livewindow --hidden-import dayplayer.onboarding \
  run_dayplayer.py
codesign --force --deep -s - dist/Circadia.app
echo ""
echo "✔ built dist/Circadia.app  (ad-hoc signed, not notarized)"
echo "  users open it the first time with right-click -> Open"
