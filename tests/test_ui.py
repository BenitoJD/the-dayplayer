"""UI interaction test (QtTest): click through the real window.

Drives the actual widgets the user drives:
  ring renders the day · navigation works · Play My Day renders and opens
  the blind panel · voting reveals the truth · live toggle starts/stops.

Run:  .venv/bin/python tests/test_ui.py [--headed]
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt, QTimer                # noqa: E402
from PySide6.QtTest import QTest                     # noqa: E402
from PySide6.QtWidgets import QApplication           # noqa: E402

from dayplayer import config, features               # noqa: E402
from dayplayer.dashboard import Dashboard, QSS       # noqa: E402
from fixtures import isolate_dirs, write_synthetic_day  # noqa: E402

FIXTURE = "2099-01-01"
HEADED = "--headed" in sys.argv
TMP = tempfile.mkdtemp()
isolate_dirs(TMP)                      # never touch real ~/.dayplayer data
tags_file = os.path.join(TMP, "tags.json")
from dayplayer import tags as _tags    # noqa: E402
_tags.TAGS_FILE = tags_file


def pump(app, seconds: float):
    """Run the event loop for a while (lets workers + timers act)."""
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def wait_for(app, predicate, timeout=180.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.05)
    return False


def main():
    write_synthetic_day(FIXTURE, config.LOG_DIR)   # self-contained fixture
    assert features.extract(FIXTURE)["minutes"]
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    win = Dashboard(FIXTURE)
    win.show()
    pump(app, 1.0)

    # ---- 1. the ring carries the day, and a sentence was written
    assert win.ring.strip, "ring should hold the day's minutes"
    assert win.line1.text(), "there should be a sentence"
    print(f"[1] ring: {len(win.ring.strip)} minutes · "
          f"sentence: “{win.line1.text()}” {win.line2.text()}")

    # ---- 2. navigation: back a day, then forward again
    title_before = win.title.text()
    QTest.mouseClick(win.prev_btn, Qt.LeftButton)
    pump(app, 0.3)
    assert win._selected_offset == 1, "prev should move back one day"
    assert win.title.text() != title_before, "title should change"
    QTest.mouseClick(win.next_btn, Qt.LeftButton)
    pump(app, 0.3)
    assert win._selected_offset == 0
    print(f"[2] navigation OK (title: {win.title.text()!r})")

    # ---- 3. Play My Day -> renders -> blind panel appears
    sessions_before = set(os.listdir(config.RENDER_DIR))
    render_results = []
    win._render_done_sig.connect(lambda r: render_results.append(r))
    QTest.mouseClick(win.play_btn, Qt.LeftButton)
    assert win.play_btn.text() != "▸  Play My Day", "button should busy-state"
    ok = wait_for(app, lambda: win.blind.isVisible(), timeout=240)
    if not ok:
        print(f"    render result: {render_results}")
        print(f"    sentence line2: {win.line2.text()!r}")
    assert ok, "blind panel should appear after rendering"
    new_sessions = set(os.listdir(config.RENDER_DIR)) - sessions_before
    assert new_sessions, "a render session should have been written"
    sid = sorted(new_sessions)[-1]
    meta = json.load(open(os.path.join(config.RENDER_DIR, sid, "meta.json")))
    print(f"[3] render OK: session {sid} (real = {meta['real_label']})")
    win.ctl.stop_playback()          # silence the auto-play

    # ---- 4. vote the WRONG label, then the RIGHT one
    wrong = "b" if meta["real_label"] == "a" else "a"
    QTest.mouseClick(win.va if wrong == "a" else win.vb, Qt.LeftButton)
    pump(app, 0.4)
    assert "✘" in win.blind_result.text(), win.blind_result.text()
    print(f"[4] wrong vote answered honestly: "
          f"“{win.blind_result.text()}”")
    QTest.mouseClick(win.va if meta["real_label"] == "a" else win.vb,
                     Qt.LeftButton)
    pump(app, 0.4)
    assert "✔" in win.blind_result.text(), win.blind_result.text()
    print(f"[4] correct vote revealed: “{win.blind_result.text()}”")

    # ---- 5. tags → correlations path (UI write)
    win.tag_input.setText("shipped")
    win.tag_input.returnPressed.emit()
    pump(app, 0.3)
    from dayplayer import tags as tagmod
    assert "shipped" in tagmod.get_tags(FIXTURE), "tag should be stored"
    chips = [win.tag_chips.itemAt(i).widget().text()
             for i in range(win.tag_chips.count())
             if win.tag_chips.itemAt(i).widget()]
    assert any("shipped" in c for c in chips), chips
    print(f"[5] tag stored + chip rendered: {chips}")
    win._remove_tag("shipped")               # leave no test residue typed
    pump(app, 0.2)

    # ---- 6. live toggle starts and stops the engine
    QTest.mouseClick(win.live_btn, Qt.LeftButton)
    pump(app, 1.5)
    running = bool(win.live_engine and win.live_engine.running)
    assert running, "listen live should start the engine"
    state_shown = win.line1.text()
    QTest.mouseClick(win.live_btn, Qt.LeftButton)
    pump(app, 0.5)
    assert win.live_engine is None, "second click should stop the engine"
    print(f"[6] live toggle OK (showed “{state_shown}”, audio="
          f"{'on' if running else 'off'})")

    # ---- 7. record toggle spawns a REAL, SEPARATE recorder process
    # (never in-process: pynput's keyboard listener crashes inside a GUI app)
    from dayplayer.recorder import PID_FILE
    if win.ctl.recording:                    # live mode may have left one on
        QTest.mouseClick(win.rec_btn, Qt.LeftButton)
        pump(app, 1.2)
    assert not win.ctl.recording, "record toggle should have stopped it"
    QTest.mouseClick(win.rec_btn, Qt.LeftButton)
    pump(app, 1.5)
    assert win.ctl.recording, "record toggle should start recording"
    assert os.path.exists(PID_FILE), "recorder pid file should exist"
    pid = int(open(PID_FILE).read().strip())
    assert pid != os.getpid(), "recorder must NOT be this GUI process"
    os.kill(pid, 0)                          # raises if not alive
    print(f"[7] recorder spawned as a separate process (pid {pid}, "
          f"this process {os.getpid()})")
    hint = win.line2.text()
    if not win.ctl.trusted:
        assert "Accessibility" in hint or "macOS" in hint, hint
        print("[7] permission hint shown correctly (macOS blocking input)")
    QTest.mouseClick(win.rec_btn, Qt.LeftButton)     # stop it again
    pump(app, 1.2)
    assert not win.ctl.recording, "second click should stop recording"
    print("[7] recorder stopped cleanly")

    win.grab().save("/tmp/circadia-ui-test.png")
    print("\nALL UI TESTS PASSED ✔  (screenshot: /tmp/circadia-ui-test.png)")
    if HEADED:
        QTimer.singleShot(100, app.quit)
        app.exec()
    else:
        app.quit()


if __name__ == "__main__":
    main()
