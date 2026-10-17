"""The Dayplayer — native macOS menu bar app.

  ● / ○ in the menu bar shows recording state.
  Click the menu: start/stop recording, render the day, play A/B
  blind, vote, reveal. No browser, no server.

Run:  python3 -m dayplayer.app     (or double-click Dayplayer.app)
"""
from __future__ import annotations

import os
import subprocess
import threading
import time

import rumps

from . import config, features, pipeline
from .recorder import Recorder

REFRESH_SECS = 20


class DayplayerApp(rumps.App):
    def __init__(self):
        super().__init__(name="Dayplayer", title="○", quit_button=None)
        self.recorder = Recorder()
        self.session = None          # blind render session id
        self.result = None           # last vote result text
        self.playing = None          # afplay subprocess
        self._build_menu()
        self._refresh()

    # ------------------------------------------------------------- menu
    def _build_menu(self):
        self._status = rumps.MenuItem("○ Not recording")
        self._toggle = rumps.MenuItem("Start Recording",
                                      callback=self.on_toggle)
        self._render = rumps.MenuItem("▶  Render My Day",
                                      callback=self.on_render)
        self._play_a = rumps.MenuItem("Play A", callback=lambda mi:
                                      self.on_play(mi, "a"))
        self._play_b = rumps.MenuItem("Play B", callback=lambda mi:
                                      self.on_play(mi, "b"))
        self._stop_play = rumps.MenuItem("Stop Playback",
                                         callback=self.on_stop_play)
        self._vote_a = rumps.MenuItem("A is me", callback=lambda mi:
                                      self.on_vote(mi, "a"))
        self._vote_b = rumps.MenuItem("B is me", callback=lambda mi:
                                      self.on_vote(mi, "b"))
        self._reveal = rumps.MenuItem("— vote first —")
        self.menu = [
            self._status, self._toggle, None,
            self._render, None,
            self._play_a, self._play_b, self._stop_play, None,
            self._vote_a, self._vote_b, self._reveal, None,
            rumps.MenuItem("Open Logs Folder", callback=self.on_logs),
            rumps.MenuItem("About Dayplayer", callback=self.on_about),
            rumps.MenuItem("Quit", callback=self.on_quit),
        ]
        self._set_render_enabled(False)

    def _set_render_enabled(self, on: bool):
        for item in (self._play_a, self._play_b, self._vote_a, self._vote_b):
            item.set_callback(item.callback if on else None)

    # ------------------------------------------------------------ status
    def _refresh(self, *a):
        try:
            events = [e for e in features.load_events()
                      if e.get("type") in features.INPUT_TYPES
                      or e.get("type") == "win"]
            live = self.recorder.running
            if not live and events:
                live = time.time() - events[-1]["t"] < 90
            n = len(events)
            self.title = "●" if live else "○"
            self._status.title = (f"● Recording — {n:,} events today"
                                  if live else f"○ Not recording ({n:,} today)")
            self._toggle.title = "Stop Recording" if self.recorder.running \
                else "Start Recording"
        except Exception:
            pass

    # ----------------------------------------------------------- actions
    def on_toggle(self, _):
        if self.recorder.running:
            self.recorder.stop()
            self._refresh()
            rumps.notification("Dayplayer", "Recording stopped",
                               "Your log is saved in ~/.dayplayer")
        else:
            try:
                self.recorder.start()
                self._refresh()
                if self.recorder.count == 0 and self.recorder.running:
                    rumps.notification(
                        "Dayplayer", "Recording started",
                        "If events stay at 0: allow Dayplayer under "
                        "Input Monitoring (System Settings → Privacy & "
                        "Security), then restart it.")
            except Exception as e:
                rumps.notification("Dayplayer", "Could not start", str(e))

    def on_render(self, _):
        if not self.recorder.running:
            today = features.load_events()
            if not today:
                rumps.notification(
                    "Dayplayer", "Nothing to render yet",
                    "Start recording and work for a while first.")
                return
        self._render.set_callback(None)
        self._render.title = "Rendering… (~30s)"
        threading.Thread(target=self._render_worker, daemon=True).start()

    def _render_worker(self):
        try:
            result = pipeline.render_day()
        except Exception as e:
            rumps.notification("Dayplayer", "Render failed", str(e))
            return
        finally:
            self._render.title = "▶  Render My Day"
            self._render.set_callback(self.on_render)
        if result.get("error"):
            rumps.notification("Dayplayer", "Nothing to render",
                               result.get("message", ""))
            return
        self.session = result["id"]
        self.result = None
        self._reveal.title = "— vote first —"
        self._set_render_enabled(True)
        mins = result.get("stats", {}).get("n_minutes", "?")
        rumps.notification(
            "Dayplayer", "Your day is ready",
            f"{mins} minutes compressed to ~3:00. "
            "Listen to A and B, then vote which is you.")

    def on_play(self, _, which: str):
        self.on_stop_play(None)
        sid = self.session
        if not sid:
            return
        # blind copies: a.wav/b.wav never reveal their source on disk
        meta = pipeline.load_session(sid)
        real_is_a = meta["real_label"] == "a"
        src = "real.wav" if (which == "a") == real_is_a else "shuffled.wav"
        blind_path = os.path.join(config.RENDER_DIR, sid,
                                  f"blind_{which}.wav")
        if not os.path.exists(blind_path):
            import shutil
            shutil.copyfile(os.path.join(config.RENDER_DIR, sid, src),
                            blind_path)
        self.playing = subprocess.Popen(["afplay", blind_path])

    def on_stop_play(self, _):
        if self.playing:
            self.playing.terminate()
            self.playing = None

    def on_vote(self, _, choice: str):
        if not self.session:
            return
        self.on_stop_play(None)
        try:
            meta = pipeline.load_session(self.session)
            correct = choice == meta["real_label"]
            real = meta["real_label"].upper()
            self.result = (
                f"{'✔ Correct' if correct else '✘ Wrong'} — "
                f"your real day was {real}")
        except Exception as e:
            self.result = f"(vote failed: {e})"
        self._reveal.title = self.result
        rumps.notification("Dayplayer", "The blind test says…", self.result)

    def on_logs(self, _):
        subprocess.Popen(["open", config.LOG_DIR])

    def on_about(self, _):
        rumps.Window(
            title="The Dayplayer",
            message="Your workday, played back.\n\n"
                    "Records timings only — never letters, never content.\n"
                    "Raw logs stay in ~/.dayplayer.\n\n"
                    "docs/TRUST.md holds the full promise.",
            dimensions=(320, 200)).run()

    def on_quit(self, _):
        self.on_stop_play(None)
        self.recorder.stop()
        rumps.quit_application()


def main():
    config.ensure_dirs()
    DayplayerApp().run()


if __name__ == "__main__":
    main()
