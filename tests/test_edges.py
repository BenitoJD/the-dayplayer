"""Edge-case suite: the weird days, the corrupt files, the extremes.

Every case here is something that would otherwise reach a user:
  · a 24-hour day (recorder left running), used to render SILENT
  · a 1-minute day · a markers-only log · a corrupt/partial JSONL line
  · a 100k-event day · tags with emoji/dupes/missing files
  · two renders in the same second · a vote with no session
  · browsing to a day that never existed

Run:  .venv/bin/python tests/test_edges.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                                     # noqa: E402

from dayplayer import composer, config, features, pipeline, tags  # noqa: E402
from dayplayer.dashboard import day_sentence                     # noqa: E402
from dayplayer.live import LiveEngine                            # noqa: E402
from dayplayer.patterns import (FLOW, MIRE, classify_minute,     # noqa: E402
                                day_summary)


def write_day(date: str, events: list[dict], log_dir: str):
    with open(os.path.join(log_dir, f"{date}.jsonl"), "w") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")


def synth_day(date: str, log_dir: str, hours: float, per_second: float = 1.0):
    """A continuous day of typing at `per_second` keys/sec."""
    now = time.time()
    start = now - hours * 3600
    events, t = [], start
    step = 1.0 / per_second
    while t < now:
        events.append({"type": "kd", "c": "key", "t": round(t, 3)})
        t += step
    write_day(date, events, log_dir)
    return len(events)


def loudness(path: str) -> tuple[float, float]:
    with wave.open(path) as w:
        n = w.getnframes()
        x = np.frombuffer(w.readframes(n), dtype=np.int16)[::2]
        x = x.astype(float) / 32768
        return n / w.getframerate(), float(np.sqrt((x ** 2).mean()))


def main():
    # isolated log dir + tags file for every case below
    tmp = tempfile.mkdtemp()
    log_dir = os.path.join(tmp, "logs")
    os.makedirs(log_dir, exist_ok=True)
    real_log_dir, config.LOG_DIR = config.LOG_DIR, log_dir
    real_tags, tags.TAGS_FILE = tags.TAGS_FILE, os.path.join(tmp, "tags.json")
    tmp_renders = os.path.join(tmp, "renders")
    try:
        # ---------------------------------------------- 1. the 24h day
        n = synth_day("2099-08-08", log_dir, hours=24)
        feats = features.extract("2099-08-08")
        score = composer.compose(feats)
        tr = score["tracks"]
        per_min = len(tr["tick"]) / score["duration"] * 60
        print(f"[1] 24h day: {n:,} events, {feats['meta']['n_minutes']} min "
              f"-> {len(tr['tick'])} ticks, {len(tr['kick'])} kicks, "
              f"{len(tr['flail'])} flail ({per_min:.0f} ticks/min of audio)")
        assert len(tr["tick"]) > 300, "a long day must not render silent"
        assert len(tr["kick"]) > 5, "long day still needs accents"
        assert tr["tick"][0]["t"] >= 0

        # ---------------------------------------------- 2. the 1-minute day
        t = time.time() - 30
        write_day("2099-08-09", [{"type": "kd", "c": "key", "t": t + i * 0.3}
                                 for i in range(20)], log_dir)
        f2 = features.extract("2099-08-09")
        s2 = composer.compose(f2)
        print(f"[2] 1-minute day: {f2['meta']['n_minutes']} min -> "
              f"{len(s2['tracks']['tick'])} ticks, "
              f"{s2['tracks']['drone'] and 'drone' or 'no drone'}")
        assert s2["duration"] == config.TARGET_DURATION
        assert len(s2["tracks"]["tick"]) > 0

        # ---------------------------------------- 3. markers-only log
        write_day("2099-08-10",
                  [{"type": "hb", "t": time.time()},
                   {"type": "start", "t": time.time()},
                   {"type": "stop", "t": time.time()}], log_dir)
        f3 = features.extract("2099-08-10")
        s3 = day_summary("2099-08-10")
        l1, l2 = day_sentence(s3, live=False, today=False)
        print(f"[3] markers-only day -> empty={s3.get('empty')}, "
              f"sentence: “{l1}” / “{l2}”")
        assert f3["minutes"] == [] and s3.get("empty")
        assert isinstance(l2, str), "sentence must always have 2 lines"

        # ------------------------------- 4. corrupt + partial JSONL line
        with open(os.path.join(log_dir, "2099-08-11.jsonl"), "w") as fh:
            now = time.time()
            fh.write(json.dumps({"type": "kd", "c": "key",
                                 "t": now - 30}) + "\n")
            fh.write("{ this is not json\n")           # corrupt line
            fh.write(json.dumps({"type": "kd", "c": "key",
                                 "t": now - 20}) + "\n")
            fh.write('{"type":"kd","c":"key","t":')    # half-written line
        f4 = features.extract("2099-08-11")
        print(f"[4] corrupt day: parsed {len(f4['minutes'])} minutes, "
              f"{f4['meta'].get('total_key')} keys (junk skipped, no crash)")
        assert f4["meta"]["total_key"] == 2

        # ------------------------------------- 5. heavy day (performance)
        heavy = 40_000
        write_day("2099-08-12",
                  [{"type": "kd", "c": "key", "t": time.time() - 3600
                    + i * 0.09} for i in range(heavy)], log_dir)
        t0 = time.time()
        fh_ = features.extract("2099-08-12")
        parse_s = time.time() - t0
        t0 = time.time()
        features.extract("2099-08-12")                 # cached pass
        cached_s = time.time() - t0
        print(f"[5] {heavy:,}-event day: parse {parse_s:.2f}s, "
              f"cached {cached_s*1000:.1f}ms")
        assert parse_s < 20 and cached_s < 0.05, "cache should be instant"

        # ------------------------- 6. two renders in the same second
        r1 = pipeline.render_day("2099-08-09", out_root=tmp_renders)
        r2 = pipeline.render_day("2099-08-09", out_root=tmp_renders)
        print(f"[6] same-second renders -> {r1['id']} and {r2['id']}")
        assert r1["id"] != r2["id"], "session ids must not collide"
        assert os.path.exists(os.path.join(tmp_renders, r2["id"], "real.wav"))

        # --------------------------------------- 7. vote with no session
        from dayplayer.controller import Controller
        ctl = Controller()
        assert ctl.vote("a").startswith("(nothing rendered"), ctl.vote("a")
        ctl.session = "does-not-exist"
        assert ctl.vote("a").startswith("(session missing")
        print(f"[7] votes without/with a bogus session handled gracefully")

        # ---------------------------------- 8. tags: emoji, dupes, removal
        tags.set_tags("2099-08-09", ["shipped", "shipped", " 🚀 big day "])
        got = tags.get_tags("2099-08-09")
        print(f"[8] tags stored: {got}")
        assert got == ["shipped", "🚀 big day"], got    # deduped + sorted
        tags.set_tags("2099-08-09", [])
        assert tags.get_tags("2099-08-09") == []
        with open(tags.TAGS_FILE, "w") as fh:
            fh.write("{broken")                            # corrupt tags file
        assert tags.get_tags("2099-08-09") == []
        print("[8] corrupt tags file tolerated")

        # --------------------------- 9. correlations need >=2 tagged days
        synth_day("2099-08-13", log_dir, hours=2)
        tags.set_tags("2099-08-13", ["shipped"])
        assert tags.correlations() == [], "one tagged day is not enough"
        tags.set_tags("2099-08-12", ["shipped"])
        corr = tags.correlations()
        print(f"[9] correlations with 2 tagged days: "
              f"{[(c['tag'], c['n']) for c in corr]}")
        assert corr and corr[0]["n"] == 2

        # -------------------- 10. live tail survives a half-written line
        live_log = os.path.join(tmp, "live.jsonl")
        with open(live_log, "w") as fh:
            fh.write(json.dumps({"type": "hb", "t": time.time()}) + "\n")
        eng = LiveEngine(log_path=live_log)
        eng.start(with_audio=False)
        time.sleep(1.0)
        with open(live_log, "a") as fh:
            fh.write('{"type":"kd","c":"key","t":')       # partial
            fh.flush()
            time.sleep(0.5)
            fh.write(f'{time.time():.3f}' + "}\n")        # completed later
            fh.write(json.dumps({"type": "kd", "c": "key",
                                 "t": round(time.time(), 3)}) + "\n")
            fh.flush()
        time.sleep(1.5)
        got = [e for e in eng._events if e.get("type") == "kd"]
        eng.stop()
        print(f"[10] tail recovered {len(got)} key events across a split line")
        assert len(got) == 2, f"partial line should be reassembled ({got})"

        # --------------------- 11. classify with a zero baseline (no crash)
        m = dict(key_rate=0, key_cv=None, mod_rate=0, switches=0,
                 mouse_dist=0, scroll_rate=0, input_events=0, idle=True)
        assert classify_minute(m, 0) == MIRE
        m2 = dict(m, idle=False, key_rate=12, input_events=20)
        print(f"[11] classify with zero baseline -> {classify_minute(m2, 0)}")
        assert classify_minute(m2, 0) in (FLOW, "drift")

        # ------------------------------ 12. day that never existed
        s12 = day_summary("1999-01-01")
        l1, l2 = day_sentence(s12, live=False, today=False)
        print(f"[12] day with no log: “{l1}” / “{l2}”")
        assert s12.get("empty") and l2 == ""

    finally:
        config.LOG_DIR = real_log_dir
        tags.TAGS_FILE = real_tags

    print("\nALL EDGE CASES PASSED ✔")


if __name__ == "__main__":
    main()
