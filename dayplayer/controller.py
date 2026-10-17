"""UI-agnostic controller shared by the macOS and Windows apps.

Owns: the recorder, the render pipeline, the blind-session state,
playback, and votes. The UI layers (app.py / wintray.py) only draw
menus and push buttons.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time

from . import config, features, pipeline
from .playback import Player
from .recorder import Recorder


def open_dashboard_window():
    """Open the dashboard window as a separate process (works frozen
    or from source, mac or windows)."""
    if getattr(sys, "frozen", False):
        subprocess.Popen([sys.executable, "--dashboard"])
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        kwargs = {"cwd": root}
        if sys.platform != "win32":
            kwargs["start_new_session"] = True      # detach from terminal
        subprocess.Popen([sys.executable, "-m", "dayplayer.dashboard"], **kwargs)


class Controller:
    def __init__(self, notify=None):
        # notify(title, message) — UI-appropriate notifications
        self.notify = notify or (lambda title, message: None)
        self.recorder = Recorder()
        self.player = Player()
        self.session: str | None = None
        self.last_result: str | None = None

    # ---------------------------------------------------------- recording
    @property
    def recording(self) -> bool:
        return self.recorder.running

    def start_recording(self) -> bool:
        if self.recording:
            return True
        try:
            self.recorder.start()
            return True
        except Exception as e:
            self.notify("Could not start", str(e))
            return False

    def stop_recording(self):
        if self.recording:
            self.recorder.stop()
            self.notify("Recording stopped",
                        "Your log is saved in ~/.dayplayer")

    def status_text(self) -> str:
        try:
            events = [e for e in features.load_events()
                      if e.get("type") in features.INPUT_TYPES
                      or e.get("type") == "win"]
            live = self.recording or (
                bool(events) and time.time() - events[-1]["t"] < 90)
            n = len(events)
            return (f"● Recording — {n:,} events today" if live
                    else f"○ Not recording ({n:,} today)")
        except Exception:
            return "○ Dayplayer" if not self.recording else "● Recording"

    def toggle_title(self) -> str:
        return "Stop Recording" if self.recording else "Start Recording"

    # ------------------------------------------------------------- render
    def has_any_data(self) -> bool:
        return bool(features.load_events())

    def render(self, done):
        """Render today in a worker thread; done(result) when finished."""
        def worker():
            try:
                result = pipeline.render_day()
            except Exception as e:                     # keep the app alive
                result = {"error": "crash", "message": str(e)}
            try:
                done(result)
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def accept_render(self, result: dict) -> str:
        """Handle a finished render; returns a notification message
        (or empty string if nothing to say)."""
        if result.get("error"):
            return ""
        self.session = result["id"]
        self.last_result = None
        stats = result.get("stats", {})
        return (f"{stats.get('n_minutes', '?')} minutes compressed "
                f"to ~3:00. Listen to A and B, then vote which is you.")

    # -------------------------------------------------------- blind play
    def _blind_path(self, which: str) -> str | None:
        if not self.session:
            return None
        meta = pipeline.load_session(self.session)
        if not meta:
            return None
        blind = os.path.join(config.RENDER_DIR, self.session,
                             f"blind_{which}.wav")
        if not os.path.exists(blind):
            real_is_a = meta["real_label"] == "a"
            src = "real.wav" if (which == "a") == real_is_a else "shuffled.wav"
            shutil.copyfile(os.path.join(config.RENDER_DIR, self.session, src),
                            blind)
        return blind

    def play(self, which: str):
        p = self._blind_path(which)
        if p:
            self.player.play(p)

    def stop_playback(self):
        self.player.stop()

    # -------------------------------------------------------------- vote
    def vote(self, choice: str) -> str:
        if not self.session:
            return "(nothing rendered yet)"
        meta = pipeline.load_session(self.session)
        if not meta:
            return "(session missing)"
        correct = choice == meta["real_label"]
        real = meta["real_label"].upper()
        self.last_result = (
            f"{'✔ Correct' if correct else '✘ Wrong'} — "
            f"your real day was {real}")
        return self.last_result
