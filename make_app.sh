#!/bin/bash
# Rebuild Circadia.app (macOS menu bar app) after code changes.
set -e
cd "$(dirname "$0")"
rm -rf Circadia.app
mkdir -p Circadia.app/Contents/MacOS Circadia.app/Contents/Resources
cat > Circadia.app/Contents/MacOS/Circadia <<'EOF'
#!/bin/bash
# Circadia launcher. Keep Circadia.app inside its folder,
# it uses the bundled Python environment next to it.
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"        # .../Circadia.app/Contents
ROOT="$(cd "$APP_DIR/../.." && pwd)"               # the dayplayer folder
PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
  osascript -e 'display alert "Circadia" message "Keep Circadia.app inside its folder, it needs the bundled Python environment next to it."'
  exit 1
fi
cd "$ROOT"
exec "$PY" -m dayplayer.app
EOF
chmod +x Circadia.app/Contents/MacOS/Circadia
cat > Circadia.app/Contents/Info.plist <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleName</key><string>Circadia</string>
	<key>CFBundleDisplayName</key><string>Circadia</string>
	<key>CFBundleIdentifier</key><string>com.benitojd.circadia</string>
	<key>CFBundleExecutable</key><string>Circadia</string>
	<key>CFBundlePackageType</key><string>APPL</string>
	<key>CFBundleShortVersionString</key><string>0.2.0</string>
	<key>CFBundleVersion</key><string>2</string>
	<key>CFBundleIconFile</key><string>icon.icns</string>
	<key>LSMinimumSystemVersion</key><string>13.0</string>
	<key>LSUIElement</key><true/>
	<key>NSHumanReadableCopyright</key><string>Timings only, never content.</string>
</dict>
</plist>
EOF
cp assets/icon.icns Circadia.app/Contents/Resources/icon.icns
codesign --force -s - Circadia.app
echo "✔ Circadia.app rebuilt, double-click it to run."
