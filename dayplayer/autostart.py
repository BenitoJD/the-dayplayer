"""Start Circadia when the user logs in.

macOS   -> LaunchAgent in ~/Library/LaunchAgents
Windows -> HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
Linux   -> XDG autostart .desktop file

The launched app gets --autostart, which starts the recorder straight away
so a rebooted machine never silently records nothing.
"""
from __future__ import annotations

import os
import subprocess
import sys
from xml.sax.saxutils import escape

APP_ID = "com.benitojd.circadia"
LAUNCH_AGENT_DIR = os.path.expanduser("~/Library/LaunchAgents")
LAUNCH_AGENT = os.path.join(LAUNCH_AGENT_DIR, f"{APP_ID}.plist")
WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
WIN_VALUE = "Circadia"
XDG_AUTOSTART = os.path.expanduser("~/.config/autostart/circadia.desktop")
DRY_RUN = False          # tests set this: write files, never call launchctl


def _run(cmd: list[str]):
    """Run a launchctl call, unless a test asked us not to."""
    if DRY_RUN:
        return
    try:
        subprocess.run(cmd, capture_output=True, timeout=10)
    except Exception:
        pass


def _root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def command() -> list[str]:
    """The command line that should run at login."""
    if getattr(sys, "frozen", False):              # packaged app
        return [sys.executable, "--autostart"]
    if os.name == "nt":
        py = os.path.join(_root(), ".venv", "Scripts", "pythonw.exe")
        return ["cmd", "/c", f'cd /d "{_root()}" && "{py}" -m dayplayer.app '
                             f'--autostart']
    py = os.path.join(_root(), ".venv", "bin", "python")
    return ["/bin/bash", "-lc",
            f'cd "{_root()}" && exec "{py}" -m dayplayer.app --autostart']


def is_enabled() -> bool:
    try:
        if sys.platform == "darwin":
            return os.path.exists(LAUNCH_AGENT)
        if os.name == "nt":
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY) as k:
                try:
                    winreg.QueryValueEx(k, WIN_VALUE)
                    return True
                except FileNotFoundError:
                    return False
        return os.path.exists(XDG_AUTOSTART)
    except Exception:
        return False


def enable() -> bool:
    try:
        cmd = command()
        if sys.platform == "darwin":
            os.makedirs(LAUNCH_AGENT_DIR, exist_ok=True)
            # every argument must be XML-escaped: a raw && in the shell
            # command made the whole plist invalid and launchd ignored it
            args = "".join(f"        <string>{escape(a)}</string>\n"
                           for a in cmd)
            with open(LAUNCH_AGENT, "w") as fh:
                fh.write(
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                    '<plist version="1.0">\n<dict>\n'
                    f'    <key>Label</key><string>{APP_ID}</string>\n'
                    f'    <key>ProgramArguments</key>\n    <array>\n{args}'
                    '    </array>\n'
                    '    <key>RunAtLoad</key><true/>\n'
                    '    <key>ProcessType</key><string>Interactive</string>\n'
                    '</dict>\n</plist>\n')
            uid = os.getuid()
            _run(["launchctl", "bootstrap", f"gui/{uid}", LAUNCH_AGENT])
            return True
        if os.name == "nt":
            import winreg
            quote = subprocess.list2cmdline(cmd)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                  WIN_RUN_KEY) as k:
                winreg.SetValueEx(k, WIN_VALUE, 0, winreg.REG_SZ, quote)
            return True
        os.makedirs(os.path.dirname(XDG_AUTOSTART), exist_ok=True)
        with open(XDG_AUTOSTART, "w") as fh:
            fh.write("[Desktop Entry]\nType=Application\n"
                     "Name=Circadia\n"
                     f"Exec={' '.join(cmd)}\nX-GNOME-Autostart-enabled=true\n")
        return True
    except Exception:
        return False


def disable() -> bool:
    try:
        if sys.platform == "darwin":
            uid = os.getuid()
            _run(["launchctl", "bootout", f"gui/{uid}", LAUNCH_AGENT])
            if os.path.exists(LAUNCH_AGENT):
                os.remove(LAUNCH_AGENT)
            return True
        if os.name == "nt":
            import winreg
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY, 0,
                                    winreg.KEY_SET_VALUE) as k:
                    winreg.DeleteValue(k, WIN_VALUE)
            except FileNotFoundError:
                pass
            return True
        if os.path.exists(XDG_AUTOSTART):
            os.remove(XDG_AUTOSTART)
        return True
    except Exception:
        return False
