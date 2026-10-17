"""The Dayplayer / Circadia recorder.

Records ONLY input timing and coarse event classes:
  keyboard  -> down/up timestamps + class (letter/space/tab/mod/...)
  mouse     -> throttled move distances, clicks, scrolls
  window    -> foreground app *name* only (never window titles)

NEVER RECORDED: characters typed, file names, URLs, window titles,
clipboard, screen content, anything readable. See docs/TRUST.md.

How it runs: ALWAYS as its own plain process.

  python3 -m dayplayer.recorder        (CLI / spawned by the apps)

The GUI apps (menu bar, tray, dashboard, live window) never host the
keyboard listener in-process: pynput's macOS keyboard context crashes
inside a Cocoa/Qt application (its Carbon layout query collides with the
GUI run loop, found the hard way with faulthandler). They spawn this
module instead and watch the log, so one recorder feeds every window.
"""
from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import sys
import threading
import time

from pynput import keyboard, mouse

from . import config

PID_FILE = os.path.join(config.DATA_DIR, "recorder.pid")
ALIVE_FILE = os.path.join(config.DATA_DIR, "recorder.alive")
ALIVE_STALE_SECONDS = 20          # heartbeat lands every 5s


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def touch_alive():
    try:
        config.ensure_dirs()
        with open(ALIVE_FILE, "w") as fh:
            fh.write(str(time.time()))
    except Exception:
        pass


def recorder_running() -> bool:
    """True if a recorder process is alive RIGHT NOW.

    Two explicit signals, never inferred from log freshness (which kept
    a dead recorder looking alive for 90 seconds, a ghost ● in the UI):
      · the pid we spawned, still alive
      · the liveness heartbeat file, touched every few seconds
    """
    try:
        with open(PID_FILE) as fh:
            pid = int(fh.read().strip())
        if _pid_alive(pid):
            return True
    except Exception:
        pass
    try:
        return (time.time() - os.path.getmtime(ALIVE_FILE)
                < ALIVE_STALE_SECONDS)
    except Exception:
        return False


def spawn_recorder() -> bool:
    """Start the recorder as a detached background process."""
    if recorder_running():
        return True
    config.ensure_dirs()
    if getattr(sys, "frozen", False):              # PyInstaller exe
        cmd = [sys.executable, "--record"]
        cwd = None
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = [sys.executable, "-m", "dayplayer.recorder"]
        cwd = root
    kwargs = {}
    if os.name == "posix":
        kwargs["start_new_session"] = True         # survive app exit
    else:
        kwargs["creationflags"] = 0x00000008       # DETACHED_PROCESS
    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, **kwargs)
    except Exception:
        return False
    try:
        with open(PID_FILE, "w") as fh:
            fh.write(str(proc.pid))
    except Exception:
        pass
    return True


def stop_recorder() -> bool:
    """Stop the detached recorder process, if one is running."""
    pid = None
    try:
        with open(PID_FILE) as fh:
            pid = int(fh.read().strip())
    except Exception:
        pass
    if pid and _pid_alive(pid):
        try:
            if os.name == "posix":
                os.kill(pid, signal.SIGTERM)
            else:
                subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                               capture_output=True)
        except Exception:
            return False
    try:
        os.remove(PID_FILE)
    except Exception:
        pass
    return True


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
        return "key"                                # letters, digits, punct
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


def alive_beat(writer: JsonlWriter, stop: threading.Event):
    """Cheap liveness signal for the UI (no log noise)."""
    while not stop.is_set():
        touch_alive()
        stop.wait(5.0)


_AX_LIB = None
_TRUST_CACHE: bool | None = None


def macos_input_trusted(refresh: bool = False) -> bool:
    """True if THIS process may monitor input on macOS.

    Without accessibility trust the OS silently drops every key/mouse
    event, the recorder looks alive but hears nothing. We check so the
    app can say so out loud instead of pretending.

    The framework is loaded ONCE and the answer cached: macOS decides
    trust at process start (granting later needs a restart anyway), and
    re-loading the framework from a different thread than pynput's
    Carbon-using listener thread crashed the process (learned the hard
    way, faulthandler showed the two threads colliding).
    """
    global _AX_LIB, _TRUST_CACHE
    if sys.platform != "darwin":
        return True
    if _TRUST_CACHE is not None and not refresh:
        return _TRUST_CACHE
    try:
        if _AX_LIB is None:
            import ctypes
            _AX_LIB = ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/ApplicationServices.framework/"
                "ApplicationServices")
            _AX_LIB.AXIsProcessTrusted.restype = ctypes.c_bool
        _TRUST_CACHE = bool(_AX_LIB.AXIsProcessTrusted())
    except Exception:
        _TRUST_CACHE = False
    return _TRUST_CACHE


# --------------------------------------------------------------- Recorder
class Recorder:
    """Embeddable recorder: start()/stop(), event count, live flag."""

    def __init__(self):
        self.writer: JsonlWriter | None = None
        self._stop = threading.Event()
        self._kbd = None
        self._mse = None
        self._threads: list[threading.Thread] = []
        self.count = 0
        self.trusted = True

    @property
    def running(self) -> bool:
        return self.writer is not None

    def start(self):
        if self.running:
            return
        config.ensure_dirs()
        self.trusted = macos_input_trusted()
        self._stop = threading.Event()
        self.writer = JsonlWriter()
        self.writer.write({"type": "start"})       # explicit liveness marker
        touch_alive()
        self.count = 0
        mth = MouseMoveThrottle(config.MOUSE_MOVE_MIN_PX)
        w = self.writer

        def count(fn):
            def inner(*a, **kw):
                self.count += 1
                fn(*a, **kw)
            return inner

        # NOTE: on macOS pynput appends an `injected` flag to every
        # callback, so all handlers accept *args (learned the hard way:
        # without it every real event raised TypeError and nothing was
        # ever recorded).
        @count
        def on_press(key, *args):
            w.write({"type": "kd", "c": _key_class(key)})

        @count
        def on_release(key, *args):
            w.write({"type": "ku", "c": _key_class(key)})

        @count
        def on_move(x, y, *args):
            d = mth.distance(x, y)
            if d is not None:
                w.write({"type": "mm", "d": d})

        @count
        def on_click(x, y, button, pressed, *args):
            w.write({"type": "mc", "b": button.name, "down": pressed})

        @count
        def on_scroll(x, y, dx, dy, *args):
            w.write({"type": "ms", "dy": (1 if dy > 0 else -1),
                     "n": min(abs(int(dy)), 9)})

        self._kbd = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._kbd.start()
        self._mse = mouse.Listener(on_move=on_move, on_click=on_click,
                                   on_scroll=on_scroll)
        self._mse.start()
        for target in (window_watcher, heartbeat, alive_beat):
            t = threading.Thread(target=target,
                                 args=(self.writer, self._stop), daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self):
        if not self.running:
            return
        self._stop.set()
        for l in (self._kbd, self._mse):
            if l:
                l.stop()
        self._kbd = self._mse = None
        try:
            self.writer.write({"type": "stop"})    # explicit stop marker
        except Exception:
            pass
        self.writer.close()
        self.writer = None
        try:
            os.remove(ALIVE_FILE)                  # no ghost ● in the UI
        except Exception:
            pass


# ------------------------------------------------------------------- CLI
def main():
    rec = Recorder()
    shutdown = threading.Event()

    def on_term(*_args):
        shutdown.set()                             # clean stop on SIGTERM

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, on_term)
        except Exception:
            pass
    try:
        rec.start()
        print("● Circadia recording, only timings, never content.")
        print(f"  Log: {config.log_path()}")
        print("  Stop with Ctrl-C, or from the app menu.")
        if sys.platform == "darwin" and not macos_input_trusted():
            print("  !! macOS has NOT granted input access to this process.")
            print("     System Settings → Privacy & Security → Accessibility")
            print("     → add the app (Circadia), then restart it.")
        while not shutdown.is_set():
            time.sleep(0.3)
    except KeyboardInterrupt:
        pass
    finally:
        rec.stop()
        print("\n■ Recording stopped.")


if __name__ == "__main__":
    main()
