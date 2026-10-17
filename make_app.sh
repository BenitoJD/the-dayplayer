#!/bin/bash
# Rebuild Dayplayer.app (macOS menu bar app) after code changes.
set -e
cd "$(dirname "$0")"
mkdir -p Dayplayer.app/Contents/MacOS Dayplayer.app/Contents/Resources
cat > Dayplayer.app/Contents/MacOS/Dayplayer <<'EOF'
#!/bin/bash
# The Dayplayer launcher. Keep Dayplayer.app inside its folder —
# it uses the bundled Python environment next to it.
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"        # .../Dayplayer.app/Contents
ROOT="$(cd "$APP_DIR/../.." && pwd)"               # the dayplayer folder
PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
  osascript -e 'display alert "Dayplayer" message "Keep Dayplayer.app inside its folder — it needs the bundled Python environment next to it."'
  exit 1
fi
cd "$ROOT"
exec "$PY" -m dayplayer.app
EOF
chmod +x Dayplayer.app/Contents/MacOS/Dayplayer
cat > Dayplayer.app/Contents/Info.plist <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleName</key><string>Dayplayer</string>
	<key>CFBundleDisplayName</key><string>Dayplayer</string>
	<key>CFBundleIdentifier</key><string>com.benitojd.dayplayer</string>
	<key>CFBundleExecutable</key><string>Dayplayer</string>
	<key>CFBundlePackageType</key><string>APPL</string>
	<key>CFBundleShortVersionString</key><string>0.1.0</string>
	<key>CFBundleVersion</key><string>1</string>
	<key>CFBundleIconFile</key><string>icon.icns</string>
	<key>LSMinimumSystemVersion</key><string>13.0</string>
	<key>LSUIElement</key><true/>
	<key>NSHumanReadableCopyright</key><string>Timings only, never content.</string>
</dict>
</plist>
EOF
cp assets/icon.icns Dayplayer.app/Contents/Resources/icon.icns
codesign --force -s - Dayplayer.app
echo "✔ Dayplayer.app rebuilt — double-click it to run."
