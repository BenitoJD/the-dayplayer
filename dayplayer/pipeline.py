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
