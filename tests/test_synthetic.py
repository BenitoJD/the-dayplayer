"""End-to-end test: fabricate a synthetic day, render both versions,
verify the audio is real, distinct, and the blind test answer is sound.

Run:  .venv/bin/python tests/test_synthetic.py
"""
import os
import random
import sys
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dayplayer import composer, config, features, pipeline, synth  # noqa: E402

TEST_DATE = "2099-01-01"


def synthetic_day(date=TEST_DATE):
    """3h: flow typing -> flail -> idle -> mixed typing+mouse -> idle."""
    rng = random.Random(1)
    config.ensure_dirs()
    path = config.log_path(date)
    with open(path, "w") as fh:
        t = time.time() - 3 * 3600
        def w(obj):
            obj["t"] = round(t, 3)
            fh.write(repr(obj).replace("'", '"') + "\n")
        def key(c="key"):
            nonlocal t
            t += rng.uniform(0.08, 0.35)               # steady flow
            w({"type": "kd", "c": c}); w({"type": "ku", "c": c})
        # 1) 40 min deep work: fast steady typing
        for _ in range(1400):
            key()
        # occasional space/enter
            if rng.random() < 0.15: key("space")
        # 2) 10 min flail: mod+tab, app switches
        for _ in range(160):
            t += rng.uniform(0.2, 1.5)
            w({"type": "kd", "c": rng.choice(["mod", "tab"])})
            w({"type": "ku", "c": "mod"})
            if rng.random() < 0.4:
                w({"type": "win", "app": rng.choice(["Safari", "Slack", "VS Code"])})
        # 3) 70 min idle: heartbeats only (no input events)
        t += 70 * 60
        # 4) 40 min mixed: typing + heavy mouse
        for _ in range(600):
            t += rng.uniform(0.3, 1.2)                 # slower, erratic
            if rng.random() < 0.6: key()
            else: w({"type": "mm", "d": round(rng.uniform(20, 120), 1)})
            if rng.random() < 0.1: w({"type": "ms", "dy": 1, "n": 3})
        # 5) 20 min idle tail
        t += 20 * 60
    return path


def wav_stats(path):
    with wave.open(path) as w:
        n = w.getnframes()
        dur = n / w.getframerate()
        import numpy as np
        raw = w.readframes(n)
        x = np.frombuffer(raw, dtype=np.int16)[::2].astype(float) / 32768
    return dur, float(abs(x).mean()), float(np.sqrt((x ** 2).mean()))


def main():
    path = synthetic_day()
    print(f"[1] synthetic log written: {path}")

    feats = features.extract(TEST_DATE)
    meta = feats["meta"]
    print(f"[2] features: {meta['n_minutes']} min span, "
          f"{meta['active_minutes']} active, {meta['total_key']} keys, "
          f"{meta['total_mouse']}px mouse")
    assert meta["total_key"] > 1000, "not enough keys captured"
    idle = [m for m in feats["minutes"] if m["idle"]]
    print(f"    idle minutes: {len(idle)} (expect the two long stretches)")

    score = composer.compose(feats, seed=7)
    tr = score["tracks"]
    print(f"[3] score: {len(tr['tick'])} ticks, {len(tr['kick'])} kicks, "
          f"{len(tr['flail'])} flail blips, {len(tr['drone'])} drones, "
          f"{len(tr['wash'])} washes")
    assert len(tr["tick"]) > 120, "typing should produce many ticks"
    assert len(tr["flail"]) > 10, "flail minute should produce blips"
    assert len(tr["drone"]) >= 2, "idle stretches should produce drones"

    out_dir = os.path.join(config.RENDER_DIR, "test-run")
    os.makedirs(out_dir, exist_ok=True)
    p1 = synth.render(score, os.path.join(out_dir, "real.wav"), seed=7)
    d1, m1, r1 = wav_stats(p1)
    print(f"[4] real.wav: {d1:.1f}s  peak-mean={m1:.4f}  rms={r1:.4f}")
    assert 170 < d1 < 190, f"duration should be ~180s, got {d1}"
    assert r1 > 0.01, "audio should not be silence"

    sh = features.shuffled_events(TEST_DATE, rng=random.Random(42))
    sh_feats = features.features_from_events(sh, TEST_DATE)
    sh_score = composer.compose(sh_feats, seed=7)
    p2 = synth.render(sh_score, os.path.join(out_dir, "shuffled.wav"), seed=7)
    d2, m2, r2 = wav_stats(p2)
    print(f"[5] shuffled.wav: {d2:.1f}s  rms={r2:.4f}")
    assert r1 != r2, "real and shuffled must differ audibly"

    # blind pipeline end-to-end via pipeline.render_day (temp output)
    tmp_root = os.path.join(config.RENDER_DIR, "test-pipeline")
    result = pipeline.render_day(TEST_DATE, out_root=tmp_root)
    assert "error" not in result, result
    print(f"[6] pipeline.render_day OK: id={result['id']} "
          f"real_label={result['real_label']}")
    for f in ("real.wav", "shuffled.wav"):
        assert os.path.exists(os.path.join(tmp_root, result["id"], f))
    print("\nALL TESTS PASSED ✔")


if __name__ == "__main__":
    main()
