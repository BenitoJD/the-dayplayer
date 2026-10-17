"""Tests for Circadia v2: live engine classification, week render, tags.

Run:  .venv/bin/python tests/test_v2.py
"""
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dayplayer import config, pipeline, patterns, tags  # noqa: E402
from dayplayer.live import LiveEngine                    # noqa: E402


def write_log(path, events):
    with open(path, "w") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")


def flow_events(n=120):
    t = time.time() - n * 0.25
    out = []
    while t < time.time():
        out.append({"type": "kd", "c": "key", "t": round(t, 3)})
        t += 0.22 + random.uniform(-0.03, 0.05)
    return out


def flail_events():
    t = time.time() - 30
    out = []
    while t < time.time():
        out.append({"type": "kd",
                    "c": random.choice(["mod", "tab"]), "t": round(t, 3)})
        if random.random() < 0.5:
            out.append({"type": "win", "app": "X", "t": round(t, 3)})
        t += 0.4
    return out


def main():
    config.ensure_dirs()
    tmp = os.path.join(config.LOG_DIR, "2099-01-02.jsonl")

    # ---- live engine: flow
    write_log(tmp, flow_events())
    eng = LiveEngine(log_path=tmp)
    eng._maybe_start_recorder()          # should detect fresh, not embed
    assert eng._own_recorder is None, "should not double-record"
    eng._events.extend(json.loads(l)
                       for l in open(tmp).readlines())
    eng._analyze()
    print(f"[1] live flow -> {eng.state}  cps={eng.cps:.1f}")
    assert eng.state == patterns.FLOW, eng.state
    assert eng.cps > 2.0

    # ---- live engine: flail
    write_log(tmp, flail_events())
    eng2 = LiveEngine(log_path=tmp)
    eng2._events.extend(json.loads(l) for l in open(tmp).readlines())
    eng2._analyze()
    print(f"[2] live flail -> {eng2.state}")
    assert eng2.state == patterns.FLAIL, eng2.state

    # ---- live engine: idle (fresh engine reads nothing -> MIRE)
    eng3 = LiveEngine(log_path=tmp)
    eng3._analyze()
    print(f"[3] live idle -> {eng3.state}")
    assert eng3.state == patterns.MIRE

    # ---- audio callback smoke (no device needed — call directly)
    import numpy as np
    eng.weights = {k: 0.25 for k in eng.weights}
    outdata = np.zeros((512, 2), dtype=np.float32)
    eng.state = patterns.FLOW
    eng._audio_cb(None, outdata, 512, None, None)
    assert abs(outdata).max() > 0.001, "flow layer should make sound"
    eng.state = patterns.FLAIL
    eng._audio_cb(None, outdata, 512, None, None)
    assert abs(outdata).max() > 0.001, "flail layer should make sound"
    print("[4] audio callback produces signal for flow + flail")

    # ---- week render (uses synthetic day 2099-01-01 from test_synthetic)
    res = pipeline.render_week(end_date="2099-01-02", n_days=2)
    assert "error" not in res, res
    week = os.path.join(config.RENDER_DIR, res["id"], "week.wav")
    assert os.path.exists(week)
    import wave
    with wave.open(week) as w:
        dur = w.getnframes() / w.getframerate()
    print(f"[5] week render: {res['dates']} -> {dur:.1f}s")
    assert 30 < dur < 120

    # ---- tags + correlations in an isolated environment (temp log dir +
    # temp tags file, realistic dates — synthetic 2099-* is excluded by
    # design from real user correlations)
    import shutil
    import tempfile
    tmpdir = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmpdir, "logs"), exist_ok=True)
    real_log_dir, config.LOG_DIR = config.LOG_DIR, os.path.join(tmpdir, "logs")
    real_tags_file, tags.TAGS_FILE = tags.TAGS_FILE, os.path.join(
        tmpdir, "tags.json")
    try:
        src = os.path.join(real_log_dir, "2099-01-02.jsonl")
        for d in ("2024-03-01", "2024-03-02", "2024-03-03"):
            shutil.copyfile(src,
                            os.path.join(config.LOG_DIR, f"{d}.jsonl"))
        tags.set_tags("2024-03-01", ["shipped"])
        tags.set_tags("2024-03-02", ["shipped"])
        assert tags.get_tags("2024-03-01") == ["shipped"]
        corr = tags.correlations()
        print(f"[6] correlations: {[(c['tag'], c['n']) for c in corr]}")
        assert any(c["tag"] == "shipped" and c["n"] == 2 for c in corr), corr
    finally:
        config.LOG_DIR = real_log_dir
        tags.TAGS_FILE = real_tags_file

    print("\nALL V2 TESTS PASSED ✔")


if __name__ == "__main__":
    main()
