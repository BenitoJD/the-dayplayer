"""PyInstaller entry point — launches the native Dayplayer app
(menu bar on macOS, system tray on Windows)."""
from dayplayer.app import main

if __name__ == "__main__":
    main()
