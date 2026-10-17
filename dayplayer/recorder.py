"""The Dayplayer recorder daemon.

Records ONLY input timing and coarse event classes:
  keyboard  -> down/up timestamps + class (letter/space/tab/mod/...)
  mouse     -> throttled move distances, clicks, scrolls
  window    -> foreground app *name* only (never window titles)

NEVER RECORDED: characters typed, file names, URLs, window titles,
clipboard, screen content, anything readable. See docs/TRUST.md.

Run:  python3 -m dayplayer.recorder
Stop: Ctrl-C  (or close the terminal)
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import threading
import time

from pynput import keyboard, mouse

from . import config


class JsonlWriter:
    """Append-only JSONL writer with midnight rollover."""

    def __init__(self):
        config.ensure_dirs()
        self._date = time.strftime("%Y-%m-%d")
        self._fh = open(config.log_path(self._date), "a", buffering=1)

    def write(self, obj: dict):
        today = time.strftime("%Y-%m-%d")
        if today != self._date:                      # midnight rollover
            self._fh.close()
            self._date = today
            self._fh = open(config.log_path(today), "a", buffering=1)
        obj["t"] = round(time.time(), 3)
        self._fh.write(json.dumps(obj, separators=(",", ":")) + "\n")

    def close(self):
        try:
            self._fh.close()
        except Exception:
            pass


# ---------------------------------------------------------------- keyboard
# Coarse classes only. A letter is a "key"; we never record which one.
_SPECIAL_CLASSES = {
    "space": "space", "enter": "enter", "return": "enter",
    "backspace": "backspace", "delete": "delete", "tab": "tab",
    "esc": "esc", "escape": "esc", "caps_lock": "caps",
    "up": "arrow", "down": "arrow", "left": "arrow", "right": "arrow",
    "shift": "mod", "shift_r": "mod", "shift_l": "mod",
    "ctrl": "mod", "ctrl_l": "mod", "ctrl_r": "mod", "control": "mod",
    "control_l": "mod", "control_r": "mod",
    "alt": "mod", "alt_l": "mod", "alt_r": "mod", "alt_gr": "mod",
    "option": "mod", "option_l": "mod", "option_r": "mod",
    "cmd": "mod", "cmd_l": "mod", "cmd_r": "mod",
    "cmd_or_ctrl": "mod", "win": "mod", "windows": "mod",
    "home": "nav", "end": "nav", "page_up": "nav", "page_down": "nav",
}


def _key_class(key) -> str:
    """Map a pynput key to a coarse, content-free class."""
    if isinstance(key, keyboard.KeyCode):
        ch = key.char
        if ch is None:
            return "key"                            # dead key / ime
        if ch == " ":
            return "space"
        if ch.isalpha() or ch.isdigit() or ch in "\t\n\r":
            # letters, digits -> same class. tab/newline specials below.
            return "key"
        return "key"                                # punctuation -> same class
    name = getattr(key, "name", "") or ""
    if name.startswith("f") and name[1:].isdigit():
        return "fn"
    return _SPECIAL_CLASSES.get(name, "other")


# ------------------------------------------------------------------- mouse
class MouseMoveThrottle:
    def __init__(self, min_px: int):
        self.min_px = min_px
        self.last = None                            # (x, y) last *logged*
        self.since = None                           # (x, y) last *seen*

    def distance(self, x: float, y: float) -> float | None:
        """Return accumulated distance if it crossed the threshold."""
        self.since = (x, y)
        if self.last is None:
            self.last = (x, y)
            return None
        d = math.hypot(x - self.last[0], y - self.last[1])
        if d < self.min_px:
            return None
        self.last = (x, y)
        return round(d, 1)


# ------------------------------------------------------------ window watch
def _frontmost_app_darwin() -> str | None:
    try:
        from AppKit import NSWorkspace               # permission-free
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return app.localizedName()
    except Exception:
        return None


def _frontmost_app_windows() -> str | None:
    try:
        import ctypes
        import ctypes.wintypes as wt
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return None
        buf = ctypes.create_unicode_buffer(512)
        size = wt.DWORD(512)
        try:
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value)
        finally:
            kernel32.CloseHandle(h)
    except Exception:
        pass
    return None


def window_watcher(writer: JsonlWriter, stop: threading.Event):
    """Log foreground app NAME changes (names only, never titles)."""
    getter = _frontmost_app_darwin if sys.platform == "darwin" else (
        _frontmost_app_windows if sys.platform.startswith("win") else None)
    if getter is None:
        return
    current = None
    while not stop.is_set():
        try:
            name = getter()
            if name and name != current:
                current = name
                writer.write({"type": "win", "app": name})
        except Exception:
            pass
        stop.wait(config.WINDOW_POLL_SECONDS)


def heartbeat(writer: JsonlWriter, stop: threading.Event):
    """Minute heartbeat so we can tell 'running quietly' from 'dead'."""
    while not stop.is_set():
        writer.write({"type": "hb"})
        stop.wait(60.0)


# ------------------------------------------------------------------- main
def main():
    config.ensure_dirs()
    writer = JsonlWriter()
    stop = threading.Event()

    mth = MouseMoveThrottle(config.MOUSE_MOVE_MIN_PX)

    def on_press(key):
        writer.write({"type": "kd", "c": _key_class(key)})

    def on_release(key):
        writer.write({"type": "ku", "c": _key_class(key)})

    def on_move(x, y):
        d = mth.distance(x, y)
        if d is not None:
            writer.write({"type": "mm", "d": d})

    def on_click(x, y, button, pressed):
        writer.write({"type": "mc", "b": button.name, "down": pressed})

    def on_scroll(x, y, dx, dy):
        writer.write({"type": "ms", "dy": (1 if dy > 0 else -1),
                      "n": min(abs(int(dy)), 9)})

    threads = [threading.Thread(target=window_watcher, args=(writer, stop), daemon=True),
               threading.Thread(target=heartbeat, args=(writer, stop), daemon=True)]

    kbd = None
    mse = None
    try:
        kbd = keyboard.Listener(on_press=on_press, on_release=on_release)
        kbd.start()
        mse = mouse.Listener(on_move=on_move, on_click=on_click,
                             on_scroll=on_scroll)
        mse.start()
        for t in threads:
            t.start()

        print("● Dayplayer recording — only timings, never content.")
        print(f"  Log: {config.log_path()}")
        print("  Stop with Ctrl-C.")
        if sys.platform == "darwin":
            print("  (If no events appear: grant Input Monitoring to your")
            print("   terminal app in System Settings → Privacy & Security.)")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n■ Recording stopped.")
    finally:
        stop.set()
        for l in (kbd, mse):
            if l:
                l.stop()
        writer.close()


if __name__ == "__main__":
    main()
