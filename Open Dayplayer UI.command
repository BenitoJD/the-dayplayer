#!/bin/bash
# The Dayplayer — open the dashboard (status, timeline, Render button).
cd "$(dirname "$0")"
.venv/bin/python -m dayplayer.server
echo ""
echo "UI stopped. Press any key to close."
read -n 1 -s
