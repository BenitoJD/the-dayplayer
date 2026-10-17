"""PyInstaller entry point, launches the native Dayplayer app
(menu bar on macOS, system tray on Windows). Pass --dashboard to open
the dashboard window directly."""
import sys

from dayplayer.app import main

if __name__ == "__main__":
    main(sys.argv[1:])
