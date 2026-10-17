"""Cross-platform audio playback (WAV).

macOS   -> afplay subprocess (stop = terminate)
Windows -> winsound async (stop = SND_PURGE)
Other   -> paplay / aplay

`playing` answers "is sound coming out right now?", so the UI can show a
stop control only while something is actually playing. win­sound cannot
report when a sound ends, so we remember the WAV's duration and let the
clock answer instead.
"""
from __future__ import annotations

import subprocess
import sys
import time
import wave


def wav_duration(path: str) -> float:
    try:
        with wave.open(path) as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        return 0.0


class Player:
    def __init__(self):
        self._proc = None
        self._ends_at: float | None = None

    @property
    def playing(self) -> bool:
        if self._proc is not None and self._proc.poll() is None:
            return True
        if self._ends_at is not None and time.time() < self._ends_at:
            return True
        return False

    def play(self, path: str):
        """Start playing a WAV file; stops anything already playing."""
        self.stop()
        dur = wav_duration(path)
        self._ends_at = (time.time() + dur) if dur > 0 else None
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
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None
        if sys.platform.startswith("win"):
            try:
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
        self._ends_at = None
