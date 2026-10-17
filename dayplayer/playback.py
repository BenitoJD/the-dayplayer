"""Cross-platform audio playback (WAV).

macOS  -> afplay subprocess (stop = terminate)
Windows-> winsound async (built into Python)
"""
from __future__ import annotations

import subprocess
import sys


class Player:
    def __init__(self):
        self._proc = None

    def play(self, path: str):
        """Start playing a WAV file; stops anything already playing."""
        self.stop()
        if sys.platform == "darwin":
            self._proc = subprocess.Popen(["afplay", path])
        elif sys.platform.startswith("win"):
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME |
                               winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        else:                                   # linux fallback
            for cmd in (["paplay", path], ["aplay", path]):
                try:
                    self._proc = subprocess.Popen(cmd)
                    break
                except FileNotFoundError:
                    continue

    def stop(self):
        if self._proc:
            self._proc.terminate()
            self._proc = None
        if sys.platform.startswith("win"):
            try:
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
