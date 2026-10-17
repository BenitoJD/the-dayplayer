"""Render pipeline: a day -> two WAVs (real + shuffled) for the blind test."""
from __future__ import annotations

import json
import os
import random
import time

from . import composer, config, features, synth


def render_day(date: str | None = None, out_root: str | None = None):
    """Compose and render both versions. Returns session dict."""
    date = date or time.strftime("%Y-%m-%d")
    out_root = out_root or config.RENDER_DIR
    session_id = time.strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.join(out_root, session_id)
    os.makedirs(out_dir, exist_ok=True)

    real_feats = features.extract(date)
    if not real_feats["minutes"]:
        return {"error": "no_data",
                "message": f"No input events logged for {date} yet."}

    shuffled = features.shuffled_events(date, rng=random.Random(42))
    shuf_feats = features.features_from_events(shuffled, date)

    real_score = composer.compose(real_feats, seed=7)
    shuf_score = composer.compose(shuf_feats, seed=7)

    synth.render(real_score, os.path.join(out_dir, "real.wav"), seed=7)
    synth.render(shuf_score, os.path.join(out_dir, "shuffled.wav"), seed=7)

    # blind labels: which player holds the real day
    real_label = random.choice(["a", "b"])
    meta = {
        "id": session_id,
        "date": date,
        "real_label": real_label,
        "created": time.time(),
        "stats": real_feats["meta"],
    }
    with open(os.path.join(out_dir, "meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2)
    return meta


def load_session(session_id: str) -> dict | None:
    p = os.path.join(config.RENDER_DIR, session_id, "meta.json")
    try:
        with open(p) as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None


# ------------------------------------------------------------------ week
WEEK_SECONDS_PER_DAY = 42.0
WEEK_CROSSFADE = 1.2


def render_week(end_date: str | None = None, n_days: int = 7):
    """The audible diary: last n_days of recorded days, each condensed to
    ~42s, crossfaded into one piece. Returns session dict."""
    import datetime
    import wave as wavmod

    import numpy as np

    from . import synth

    end = datetime.date.fromisoformat(
        end_date or time.strftime("%Y-%m-%d"))
    dates = []
    for i in range(n_days):
        d = (end - datetime.timedelta(days=i)).isoformat()
        if os.path.exists(config.log_path(d)):
            dates.append(d)
    dates.reverse()                                   # oldest first
    recorded = [d for d in dates
                if features.extract(d)["minutes"]]
    if not recorded:
        return {"error": "no_data",
                "message": "No recorded days found in the last week."}

    session_id = "week-" + time.strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.join(config.RENDER_DIR, session_id)
    os.makedirs(out_dir, exist_ok=True)

    chunks = []
    tmp_paths = []
    for d in recorded:
        feats = features.extract(d)
        score = composer.compose(feats, seed=7,
                                 target_duration=WEEK_SECONDS_PER_DAY)
        tmp = os.path.join(out_dir, f"day-{d}.wav")
        synth.render(score, tmp, seed=7)
        tmp_paths.append(tmp)
        with wavmod.open(tmp) as w:
            x = np.frombuffer(w.readframes(w.getnframes()),
                              dtype=np.int16).astype(float) / 32768.0
        chunks.append(x[::2])                          # mono

    fade = int(WEEK_CROSSFADE * config.SAMPLE_RATE)
    total = sum(len(c) for c in chunks) - fade * (len(chunks) - 1)
    out = np.zeros(total)
    pos = 0
    for i, c in enumerate(chunks):
        if i > 0:
            # crossfade with previous tail
            pos -= fade
            ramp_up = np.linspace(0, 1, fade)
            out[pos:pos + fade] *= (1 - ramp_up)
            c = c.copy()
            c[:fade] *= ramp_up
        out[pos:pos + len(c)] += c[:max(0, total - pos)]
        pos += len(c)
    peak = np.max(np.abs(out)) or 1.0
    out = out / peak * 0.89

    week_path = os.path.join(out_dir, "week.wav")
    pcm = (out * 32767).astype(np.int16)
    with wavmod.open(week_path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(config.SAMPLE_RATE)
        w.writeframes(np.column_stack([pcm, pcm]).tobytes())

    meta = {"id": session_id, "kind": "week", "dates": recorded,
            "created": time.time()}
    with open(os.path.join(out_dir, "meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2)
    return meta
