"""Circadia (a.k.a. The Dayplayer) — native apps for macOS and Windows.

macOS   → menu bar app (rumps): ● / ○ in the menu bar
Windows → system tray app (pystray): see dayplayer/wintray.py

Both share dayplayer.controller — the recorder, render pipeline,
blind A/B playback and votes.

Run:  python3 -m dayplayer.app   (or double-click the platform app)
"""
from __future__ import annotations

import subprocess
import sys

import rumps

from . import config
from .controller import Controller, open_dashboard_window, open_live_window

REFRESH_SECS = 2


class DayplayerApp(rumps.App):
    def __init__(self):
        super().__init__(name="Circadia", title="○", quit_button=None)
        self.ctl = Controller(notify=self._notify)
        self._pending = None            # render result, consumed on main loop
        self._rendering = False
        self._reveal = "— vote first —"
        self._build_menu()
        self._refresh()

    def _notify(self, title: str, message: str):
        rumps.notification("Circadia", title, message)

    # ------------------------------------------------------------- menu
    def _build_menu(self):
        self._status = rumps.MenuItem("○ Not recording")
        self._toggle = rumps.MenuItem("Start Recording",
                                      callback=self.on_toggle)
        self._render = rumps.MenuItem("▶  Render My Day",
                                      callback=self.on_render)
        self._play_a = rumps.MenuItem("Play A", callback=lambda mi:
                                      self.ctl.play("a"))
        self._play_b = rumps.MenuItem("Play B", callback=lambda mi:
                                      self.ctl.play("b"))
        self._stop_play = rumps.MenuItem("Stop Playback",
                                         callback=lambda mi:
                                         self.ctl.stop_playback())
        self._vote_a = rumps.MenuItem("A is me", callback=lambda mi:
                                      self.on_vote("a"))
        self._vote_b = rumps.MenuItem("B is me", callback=lambda mi:
                                      self.on_vote("b"))
        self._base_callbacks = [
            (self._play_a, self._play_a.callback),
            (self._play_b, self._play_b.callback),
            (self._vote_a, self._vote_a.callback),
            (self._vote_b, self._vote_b.callback),
        ]
        self._reveal_item = rumps.MenuItem(self._reveal)
        self.menu = [
            self._status, self._toggle, None,
            rumps.MenuItem("◈  Open Dashboard", callback=lambda mi:
                           open_dashboard_window()),
            rumps.MenuItem("◉  Go Live — hear your state", callback=lambda mi:
                           open_live_window()), None,
            self._render, None,
            self._play_a, self._play_b, self._stop_play, None,
            self._vote_a, self._vote_b, self._reveal_item, None,
            rumps.MenuItem("Open Logs Folder", callback=self.on_logs),
            rumps.MenuItem("About Dayplayer", callback=self.on_about),
            rumps.MenuItem("Quit", callback=self.on_quit),
        ]
        self._set_enabled(False)

    def _set_enabled(self, on: bool):
        for item, cb in self._base_callbacks:
            item.set_callback(cb if on else None)

    # ------------------------------------------------------------ refresh
    def _refresh(self):
        try:
            text = self.ctl.status_text()
            self.title = "●" if text.startswith("●") else "○"
            self._status.title = text
            self._toggle.title = self.ctl.toggle_title()
            self._reveal_item.title = self._reveal
        except Exception:
            pass

    @rumps.timer(REFRESH_SECS)
    def _tick(self, _sender):
        self._refresh()
        if self._pending:                       # consume on the main thread
            result, self._pending = self._pending, None
            self._render_done(result)

    # ----------------------------------------------------------- actions
    def on_toggle(self, _):
        if self.ctl.recording:
            self.ctl.stop_recording()
        else:
            if self.ctl.start_recording():
                self._notify("Recording started",
                             "If events stay at 0: allow Dayplayer under "
                             "Input Monitoring (System Settings → Privacy "
                             "& Security), then restart it.")
        self._refresh()

    def on_render(self, _):
        if not self.ctl.recording and not self.ctl.has_any_data():
            self._notify("Nothing to render yet",
                         "Start recording and work for a while first.")
            return
        self._rendering = True
        self._render.title = "Rendering… (~30s)"
        self._render.set_callback(None)
        self.ctl.render(lambda r: setattr(self, "_pending", r))

    def _render_done(self, result):
        self._rendering = False
        self._render.title = "▶  Render My Day"
        self._render.set_callback(self.on_render)
        if result.get("error"):
            if result.get("error") != "no_data":
                self._notify("Render failed", result.get("message", ""))
            else:
                self._notify("Nothing to render", result.get("message", ""))
            return
        msg = self.ctl.accept_render(result)
        self._reveal = "— vote first —"
        self._set_enabled(True)
        self._notify("Your day is ready", msg)

    def on_vote(self, choice: str):
        self.ctl.stop_playback()
        self._reveal = self.ctl.vote(choice)
        self._notify("The blind test says…", self._reveal)
        self._refresh()

    def on_logs(self, _):
        subprocess.Popen(["open", config.LOG_DIR])

    def on_about(self, _):
        rumps.Window(
            title="Circadia",
            message="Your day, played back.\n\n"
                    "Records timings only — never letters, never content.\n"
                    "Raw logs stay in ~/.dayplayer.\n\n"
                    "docs/TRUST.md holds the full promise.",
            dimensions=(320, 200)).run()

    def on_quit(self, _):
        self.ctl.stop_playback()
        self.ctl.stop_recording()
        rumps.quit_application()


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if "--record" in argv:                       # detached recorder process
        from .recorder import main as record_main
        record_main()
        return
    if "--dashboard" in argv:
        from .dashboard import main as dash_main
        dash_main()
        return
    if "--live" in argv:
        from .livewindow import main as live_main
        live_main()
        return
    config.ensure_dirs()
    if sys.platform == "darwin":
        DayplayerApp().run()
    else:
        from .wintray import WinTrayApp
        WinTrayApp().run()


if __name__ == "__main__":
    main()
