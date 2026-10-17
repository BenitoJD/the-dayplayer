"""The Dayplayer — Windows system tray app (pystray).

Same features as the macOS menu bar app, native Windows tray:
double-click the tray icon to start/stop recording; right-click for
the full menu (Render, Play A/B, vote, quit).

Windows needs no special permission for global input hooks —
it just works on first run.
"""
from __future__ import annotations

import ctypes
import os
import threading
import time

import pystray
from PIL import Image, ImageDraw

from . import config
from .controller import Controller

ABOUT = ("The Dayplayer\n\n"
         "Your workday, played back.\n\n"
         "Records timings only — never letters, never content.\n"
         "Raw logs stay in ~/.dayplayer.\n\n"
         "docs/TRUST.md holds the full promise.")


def _icon_image(recording: bool) -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, size - 2, size - 2], fill=(21, 25, 35, 255))
    r = size // 4
    color = (240, 180, 41, 255) if recording else (110, 120, 145, 255)
    d.ellipse([size // 2 - r, size // 2 - r, size // 2 + r, size // 2 + r],
              fill=color)
    return img


class WinTrayApp:
    def __init__(self):
        self.ctl = Controller(notify=self._notify)
        self._pending = None            # render result from worker thread
        self._rendering = False
        self._reveal = "— vote first —"
        self._session_ready = False
        self.icon = pystray.Icon(
            "Dayplayer", _icon_image(False), "Dayplayer", menu=self._menu())
        self._ticker = threading.Thread(target=self._tick_loop, daemon=True)

    # ------------------------------------------------------------- notify
    def _notify(self, title: str, message: str):
        try:
            self.icon.notify(message=message, title=f"Dayplayer — {title}")
        except Exception:
            pass

    # --------------------------------------------------------------- menu
    def _menu(self):
        return pystray.Menu(
            pystray.MenuItem(lambda item: self.ctl.status_text(),
                             None, enabled=False),
            pystray.MenuItem(lambda item: self.ctl.toggle_title(),
                             self.on_toggle, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: "Rendering… (~30s)"
                             if self._rendering else "▶  Render My Day",
                             self.on_render),
            pystray.MenuItem("Play A", self._play_a),
            pystray.MenuItem("Play B", self._play_b),
            pystray.MenuItem("Stop Playback", lambda: self.ctl.stop_playback()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("A is me", self._vote_a),
            pystray.MenuItem("B is me", self._vote_b),
            pystray.MenuItem(lambda item: self._reveal, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Logs Folder", self.on_logs),
            pystray.MenuItem("About Dayplayer", self.on_about),
            pystray.MenuItem("Quit", self.on_quit),
        )

    def _play_a(self):
        if self._session_ready:
            self.ctl.play("a")

    def _play_b(self):
        if self._session_ready:
            self.ctl.play("b")

    def _vote_a(self):
        self.on_vote("a")

    def _vote_b(self):
        self.on_vote("b")

    # ------------------------------------------------------------- ticker
    def _tick_loop(self):
        was_recording = None
        while True:
            time.sleep(2)
            try:
                if self._pending:
                    result, self._pending = self._pending, None
                    self._render_done(result)
                rec = self.ctl.recording
                if rec != was_recording:
                    was_recording = rec
                    self.icon.icon = _icon_image(rec)
                self.icon.update_menu()
            except Exception:
                pass

    # ------------------------------------------------------------ actions
    def on_toggle(self, icon=None, item=None):
        if self.ctl.recording:
            self.ctl.stop_recording()
        else:
            self.ctl.start_recording()   # Windows: no permission needed
        self.icon.icon = _icon_image(self.ctl.recording)
        self.icon.update_menu()

    def on_render(self, icon=None, item=None):
        if not self.ctl.recording and not self.ctl.has_any_data():
            self._notify("Nothing to render yet",
                         "Start recording and work for a while first.")
            return
        self._rendering = True
        self.icon.update_menu()
        self.ctl.render(lambda r: setattr(self, "_pending", r))

    def _render_done(self, result):
        self._rendering = False
        if result.get("error"):
            if result.get("error") != "no_data":
                self._notify("Render failed", result.get("message", ""))
            else:
                self._notify("Nothing to render", result.get("message", ""))
            return
        msg = self.ctl.accept_render(result)
        self._reveal = "— vote first —"
        self._session_ready = True
        self._notify("Your day is ready", msg)
        self.icon.update_menu()

    def on_vote(self, choice: str):
        self.ctl.stop_playback()
        if self._session_ready:
            self._reveal = self.ctl.vote(choice)
            self._notify("The blind test says…", self._reveal)
        self.icon.update_menu()

    def on_logs(self, icon=None, item=None):
        os.startfile(config.LOG_DIR)      # type: ignore[attr-defined]

    def on_about(self, icon=None, item=None):
        ctypes.windll.user32.MessageBoxW(0, ABOUT, "Dayplayer", 0x40)

    def on_quit(self, icon=None, item=None):
        self.ctl.stop_playback()
        self.ctl.stop_recording()
        self.icon.stop()

    # --------------------------------------------------------------- run
    def run(self):
        self._ticker.start()
        self.icon.run()
