"""Tests for launch-at-login, delete-my-data, and first-run onboarding.

Everything runs against temp paths: no real LaunchAgent, no real registry
key, no real ~/.dayplayer data is touched.

Run:  .venv/bin/python tests/test_features.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TMP = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dayplayer import autostart, config, maintenance   # noqa: E402

# isolate every path the app would touch
autostart.DRY_RUN = True
autostart.LAUNCH_AGENT_DIR = os.path.join(TMP, "LaunchAgents")
autostart.LAUNCH_AGENT = os.path.join(autostart.LAUNCH_AGENT_DIR,
                                      "com.benitojd.circadia.plist")
autostart.XDG_AUTOSTART = os.path.join(TMP, "autostart", "circadia.desktop")
config.LOG_DIR = os.path.join(TMP, "logs")
config.RENDER_DIR = os.path.join(TMP, "renders")
maintenance.TAGS_FILE = os.path.join(TMP, "tags.json")
maintenance.STATE_FILE = os.path.join(TMP, "state.json")
config.ensure_dirs()


def test_autostart():
    assert not autostart.is_enabled(), "should start disabled"
    assert autostart.enable(), "enable should succeed"
    assert autostart.is_enabled(), "should report enabled after enable"
    cmd = autostart.command()
    assert cmd[0] == "/bin/bash" and cmd[-1].endswith("--autostart"), cmd
    if sys.platform == "darwin":
        plist = open(autostart.LAUNCH_AGENT).read()
        assert "RunAtLoad" in plist and "<true/>" in plist
        assert "--autostart" in plist and "com.benitojd.circadia" in plist
    assert autostart.disable(), "disable should succeed"
    assert not autostart.is_enabled(), "should be off after disable"
    if sys.platform == "darwin":
        assert not os.path.exists(autostart.LAUNCH_AGENT), "plist removed"
    print("[1] launch at login: enable -> detect -> disable -> gone")


def test_delete_data():
    now = time.time()
    for i, day in enumerate(("2024-01-01", "2024-01-02")):
        with open(os.path.join(config.LOG_DIR, f"{day}.jsonl"), "w") as fh:
            for k in range(50):
                fh.write(json.dumps({"type": "kd", "c": "key",
                                     "t": now - 3600 + k}) + "\n")
    os.makedirs(os.path.join(config.RENDER_DIR, "session-1"), exist_ok=True)
    with open(os.path.join(config.RENDER_DIR, "session-1", "real.wav"),
              "wb") as fh:
        fh.write(b"0" * 4096)
    with open(maintenance.TAGS_FILE, "w") as fh:
        json.dump({"2024-01-01": ["shipped"]}, fh)

    s = maintenance.data_summary()
    assert s["days"] == 2 and s["events"] == 100, s
    assert s["renders"] == 1 and s["tagged_days"] == 1, s
    text = maintenance.summary_text(s)
    assert "2 day(s)" in text and "1 render(s)" in text, text
    print(f"[2] summary before delete: {text}")

    result = maintenance.delete_all_data()
    after = result["remaining"]
    assert after["days"] == 0 and after["events"] == 0, after
    assert after["renders"] == 0 and after["tagged_days"] == 0, after
    assert result["freed_bytes"] > 0, result
    assert maintenance.summary_text() == "Nothing stored yet."
    print(f"[2] delete all: freed {result['freed_bytes']} bytes, "
          f"logs/renders/tags all empty")


def test_onboarding_marker():
    assert maintenance.needs_onboarding(), "fresh install needs onboarding"
    maintenance.mark_onboarded()
    assert not maintenance.needs_onboarding(), "marker should suppress it"
    # the marker must survive a data wipe (settings are not data)
    maintenance.delete_all_data()
    assert not maintenance.needs_onboarding(), "wipe must not re-onboard"
    print("[3] onboarding marker: shown once, survives a data wipe")


def test_onboarding_window():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from dayplayer.onboarding import Onboarding, QSS
    app.setStyleSheet(QSS)
    win = Onboarding()
    win.show()
    app.processEvents()
    # the permission line must say something truthful about this machine
    perm = win.perm.text()
    assert perm, "permission line must never be empty"
    from dayplayer.recorder import permission_report
    rep = permission_report()
    if sys.platform == "darwin" and not (rep["accessibility"]
                                         and rep["input_monitoring"] is not False):
        assert "Accessibility" in perm or "Input Monitoring" in perm, perm
    else:
        assert "granted" in perm.lower() or "no permissions" in perm.lower(), perm
    # the start button must be wired, and starting must be reversible
    assert win.start_btn.text() == "Start recording"
    calls = {"spawned": 0, "enabled": 0}
    import dayplayer.recorder as rec
    import dayplayer.autostart as auto
    real_spawn, real_enable = rec.spawn_recorder, auto.enable
    rec.spawn_recorder = lambda: calls.__setitem__("spawned", calls["spawned"] + 1) or True
    auto.enable = lambda: calls.__setitem__("enabled", calls["enabled"] + 1) or True
    try:
        maintenance.set_state(onboarded=False)
        win.login_cb.setChecked(True)
        win._start()
        app.processEvents()
        assert calls["spawned"] == 1, "Start must launch the recorder"
        assert calls["enabled"] == 1, "checked login box must enable autostart"
        assert not maintenance.needs_onboarding(), "Start marks onboarding done"
    finally:
        rec.spawn_recorder, auto.enable = real_spawn, real_enable
    print(f"[4] onboarding window: '{perm[:52]}...' and Start wired correctly")


def main():
    test_autostart()
    test_delete_data()
    test_onboarding_marker()
    test_onboarding_window()
    print("\nALL FEATURE TESTS PASSED ✔")


if __name__ == "__main__":
    main()
