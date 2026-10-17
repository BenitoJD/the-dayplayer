#!/bin/bash
# The Dayplayer — start the recorder daemon.
# Double-click me. First run: macOS will ask for Input Monitoring access
# for your terminal app — allow it, then stop (Ctrl-C) and double-click
# me again. Records timings only, never content.
cd "$(dirname "$0")"
.venv/bin/python -m dayplayer.recorder
echo ""
echo "Recording stopped. Press any key to close."
read -n 1 -s
