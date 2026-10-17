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
from fixtures import isolate_dirs, write_synthetic_day  # noqa: E402

TEST_DATE = "2099-01-01"


def synthetic_day(date=TEST_DATE):
    """Write the shared synthetic day into the (isolated) log dir."""
    return write_synthetic_day(date, config.LOG_DIR)


def wav_stats(path):
    with wave.open(path) as w:
        n = w.getnframes()
        dur = n / w.getframerate()
        import numpy as np
        raw = w.readframes(n)
        x = np.frombuffer(raw, dtype=np.int16)[::2].astype(float) / 32768
    return dur, float(abs(x).mean()), float(np.sqrt((x ** 2).mean()))


def main():
    import tempfile
    isolate_dirs(tempfile.mkdtemp())
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
