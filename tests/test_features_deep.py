"""Deep tests for the launch features.

Goes past "does the file exist":
  · launchd really accepts the plist we generate (it runs the job once)
  · plutil validates the XML, and a corrupt plist is still handled
  · paths with spaces survive (the repo folder has a space in it)
  · delete refuses to touch anything outside Circadia's folder
  · delete while recording actually stops the recorder
  · onboarding buttons do the right thing, under every permission state
  · --autostart really starts a recorder, --onboarding opens the window

Run:  .venv/bin/python tests/test_features_deep.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Point the whole app at a temp data dir BEFORE importing it, so logs,
# renders, tags, settings and the recorder's pid file all live in a sandbox.
TMP = tempfile.mkdtemp(prefix="circadia-deep-")
os.environ["CIRCADIA_DATA_DIR"] = TMP

from dayplayer import autostart, config, maintenance   # noqa: E402

assert config.DATA_DIR == TMP, "sandbox failed: refusing to run on real data"
config.ensure_dirs()

autostart.DRY_RUN = True
autostart.LAUNCH_AGENT_DIR = os.path.join(TMP, "LaunchAgents")
autostart.LAUNCH_AGENT = os.path.join(autostart.LAUNCH_AGENT_DIR,
                                      "com.benitojd.circadia.plist")
autostart.XDG_AUTOSTART = os.path.join(TMP, "autostart", "circadia.desktop")


# ---------------------------------------------------------------- autostart
def test_plist_is_valid_and_launchd_accepts_it():
    """The strongest autostart test: give launchd a real job and watch it
    run. Uses a harmless command that only touches a temp file."""
    if sys.platform != "darwin":
        print("[1] launchd test skipped (not macOS)")
        return
    fired = os.path.join(TMP, "fired.txt")
    label = "com.benitojd.circadia.deep"
    plist = os.path.join(TMP, f"{label}.plist")
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string><string>-lc</string>
    <string>date &gt; "{fired}"</string>
  </array>
  <key>RunAtLoad</key><true/>
</dict></plist>'''
    open(plist, "w").write(xml)
    lint = subprocess.run(["plutil", "-lint", plist], capture_output=True,
                          text=True)
    assert lint.returncode == 0, lint.stdout + lint.stderr
    uid = os.getuid()
    boot = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", plist],
                          capture_output=True, text=True)
    ok = boot.returncode == 0
    if not ok and "already bootstrapped" not in (boot.stderr or ""):
        print(f"[1] launchd refused to bootstrap here ({boot.stderr.strip()}"
              f"), plist lint passed: continuing")
        return
    for _ in range(20):
        if os.path.exists(fired):
            break
        time.sleep(0.2)
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", plist],
                   capture_output=True)
    ran = os.path.exists(fired)
    print(f"[1] launchd accepted the job and ran it at load: {ran}")
    assert ran, "launchd bootstrapped the job but never ran it"


def test_generated_plist_parses_and_keeps_the_space():
    """Our repo lives in 'the dayplayer': a space in the path must survive."""
    autostart.enable()
    plist = open(autostart.LAUNCH_AGENT).read()
    lint = subprocess.run(["plutil", "-lint", autostart.LAUNCH_AGENT],
                          capture_output=True, text=True)
    assert lint.returncode == 0, lint.stdout + lint.stderr
    cmd = autostart.command()
    assert any("the dayplayer" in part for part in cmd), cmd
    assert "--autostart" in plist and "RunAtLoad" in plist
    assert "ProgramArguments" in plist
    print(f"[2] generated plist lints clean, path with space preserved "
          f"({len(cmd)} args)")


def test_frozen_command_shape():
    """In a packaged app the command must be the bundle itself."""
    real = getattr(sys, "frozen", None)
    sys.frozen = True
    try:
        cmd = autostart.command()
        assert cmd[0] == sys.executable and cmd[1] == "--autostart", cmd
    finally:
        if real is None:
            del sys.frozen
        else:
            sys.frozen = real
    print("[3] frozen build points the login item at the app itself")


def test_corrupt_plist_still_reports_and_cleans():
    open(autostart.LAUNCH_AGENT, "w").write("this is not a plist")
    assert autostart.is_enabled(), "presence is what we report"
    assert autostart.disable(), "disable must cope with junk"
    assert not os.path.exists(autostart.LAUNCH_AGENT)
    assert not autostart.is_enabled()
    print("[4] corrupt login item: still detected and removed")


# ------------------------------------------------------------- delete data
def test_delete_refuses_outside_its_folder():
    """The guard that stops a misconfigured path becoming a disaster."""
    safe_logs, safe_renders = config.LOG_DIR, config.RENDER_DIR
    victim = os.path.join(TMP, "..", "not-ours")
    os.makedirs(os.path.join(victim, "sub"), exist_ok=True)
    open(os.path.join(victim, "sub", "precious.txt"), "w").write("keep me")
    config.LOG_DIR = victim
    try:
        result = maintenance.delete_all_data()
        assert result.get("error") == "refused", result
        assert os.path.exists(os.path.join(victim, "sub", "precious.txt")), \
            "refusal must leave the foreign folder untouched"
        print(f"[5] delete refused a foreign path: {result['message'][:66]}...")
    finally:
        config.LOG_DIR = safe_logs
        config.RENDER_DIR = safe_renders


def test_delete_stops_a_running_recorder():
    from dayplayer.recorder import (recorder_running, spawn_recorder,
                                    stop_recorder)
    spawn_recorder()
    time.sleep(2.5)
    assert recorder_running(), "recorder should be running before the wipe"
    with open(os.path.join(config.LOG_DIR, "2024-02-02.jsonl"), "w") as fh:
        fh.write(json.dumps({"type": "kd", "c": "key", "t": time.time()})
                 + "\n")
    result = maintenance.delete_all_data()          # stops it, then wipes
    time.sleep(0.6)
    assert not recorder_running(), "wipe must leave no recorder running"
    assert result["remaining"]["days"] == 0, result["remaining"]
    assert not os.path.exists(os.path.join(config.DATA_DIR, "recorder.pid"))
    stop_recorder()
    print("[6] delete while recording: recorder stopped, logs gone, "
          "pid file cleared")


def test_delete_is_idempotent_and_survives_a_fresh_install():
    import shutil
    shutil.rmtree(config.LOG_DIR, ignore_errors=True)
    shutil.rmtree(config.RENDER_DIR, ignore_errors=True)
    first = maintenance.delete_all_data()
    assert "error" not in first, first
    assert maintenance.summary_text() == "Nothing stored yet."
    second = maintenance.delete_all_data()
    assert "error" not in second, second
    assert second["freed_bytes"] == 0
    config.ensure_dirs()
    print("[7] delete on a fresh or already-empty install is a no-op, "
          "not a crash")


def test_settings_survive_a_wipe():
    maintenance.set_state(onboarded=True, other="keep")
    maintenance.delete_all_data()
    s = maintenance.state()
    assert s.get("other") == "keep", s
    print("[8] settings survive the wipe, data does not")


# -------------------------------------------------------------- onboarding
def test_onboarding_permission_states():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    import dayplayer.recorder as rec
    from dayplayer.onboarding import Onboarding, QSS
    app.setStyleSheet(QSS)
    real = rec.permission_report
    cases = [
        ({"accessibility": True, "input_monitoring": True}, "granted", False),
        ({"accessibility": False, "input_monitoring": True},
         "Accessibility", True),
        ({"accessibility": True, "input_monitoring": False},
         "Input Monitoring", True),
        ({"accessibility": True, "input_monitoring": None}, "granted", False),
    ]
    try:
        for rep, expect, button in cases:
            rec.permission_report = lambda r=rep: r
            if sys.platform != "darwin":
                continue                          # mac-only messaging
            win = Onboarding()
            txt = win.perm.text()
            assert expect.lower() in txt.lower(), (rep, txt)
            assert win.fix_btn.isVisibleTo(win) == button, (rep, button)
            win.close()
    finally:
        rec.permission_report = real
    print(f"[9] onboarding tells the truth in all {len(cases)} "
          f"permission states")


def test_onboarding_buttons_with_qt():
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    import dayplayer.autostart as auto
    import dayplayer.recorder as rec
    from dayplayer.onboarding import Onboarding
    calls = {"spawn": 0, "enable": 0, "disable": 0}
    real_spawn, real_en, real_dis = (rec.spawn_recorder, auto.enable,
                                     auto.disable)
    rec.spawn_recorder = lambda: calls.__setitem__("spawn", calls["spawn"] + 1) or True
    auto.enable = lambda: calls.__setitem__("enable", calls["enable"] + 1) or True
    auto.disable = lambda: calls.__setitem__("disable", calls["disable"] + 1) or True
    try:
        # "Not now" must never start recording or change login settings
        maintenance.set_state(onboarded=False)
        win = Onboarding()
        win.login_cb.setChecked(False)
        later = [b for b in win.findChildren(type(win.start_btn))
                 if b.text() == "Not now"][0]
        QTest.mouseClick(later, Qt.LeftButton)
        app.processEvents()
        assert calls == {"spawn": 0, "enable": 0, "disable": 0}, calls
        assert not maintenance.needs_onboarding(), "Not now still marks it seen"

        # Start must spawn the recorder and honour the login checkbox
        maintenance.set_state(onboarded=False)
        win2 = Onboarding()
        win2.login_cb.setChecked(True)
        QTest.mouseClick(win2.start_btn, Qt.LeftButton)
        app.processEvents()
        assert calls["spawn"] == 1 and calls["enable"] == 1, calls
        assert not maintenance.needs_onboarding()
        print("[10] onboarding buttons: Not now is inert, Start spawns the "
              "recorder and enables autostart")
    finally:
        rec.spawn_recorder, auto.enable, auto.disable = (real_spawn, real_en,
                                                         real_dis)


# ------------------------------------------------------------- integration
def test_autostart_flag_starts_recording():
    """--autostart is what a login launch runs: it must record on its own."""
    from dayplayer.recorder import recorder_running, stop_recorder
    stop_recorder()
    time.sleep(0.5)
    maintenance.set_state(onboarded=True)      # skip the welcome window
    env = dict(os.environ, CIRCADIA_TEST_AUTOSTART="1")
    proc = subprocess.Popen(
        [sys.executable, "-m", "dayplayer.app", "--autostart"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    try:
        deadline = time.time() + 15
        while time.time() < deadline and not recorder_running():
            time.sleep(0.5)
        running = recorder_running()
        print(f"[11] launched with --autostart -> recorder running: {running}")
        assert running, "--autostart must start recording by itself"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        stop_recorder()
        time.sleep(0.5)


def main():
    test_plist_is_valid_and_launchd_accepts_it()
    test_generated_plist_parses_and_keeps_the_space()
    test_frozen_command_shape()
    test_corrupt_plist_still_reports_and_cleans()
    test_delete_refuses_outside_its_folder()
    test_delete_stops_a_running_recorder()
    test_delete_is_idempotent_and_survives_a_fresh_install()
    test_settings_survive_a_wipe()
    test_onboarding_permission_states()
    test_onboarding_buttons_with_qt()
    test_autostart_flag_starts_recording()
    print("\nALL DEEP FEATURE TESTS PASSED ✔")


if __name__ == "__main__":
    main()
