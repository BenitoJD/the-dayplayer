"""Shared test fixtures — synthetic days written into a temp log dir.

Tests isolate themselves: they point config.LOG_DIR / RENDER_DIR at a
temp directory, so the user's real ~/.dayplayer data is never touched
(and production code never needs test-specific guards).
"""
from __future__ import annotations

import json
import os
import random
import time


def synthetic_day_events() -> list[dict]:
    """3h: flow typing -> flail -> idle -> mixed typing+mouse -> idle."""
    rng = random.Random(1)
    events: list[dict] = []
    t = time.time() - 3 * 3600

    def add(**kw):
        nonlocal t
        kw["t"] = round(t, 3)
        events.append(kw)

    def key(c="key"):
        nonlocal t
        t += rng.uniform(0.08, 0.35)
        add(type="kd", c=c)
        add(type="ku", c=c)

    for _ in range(1400):                       # deep work
        key()
        if rng.random() < 0.15:
            key("space")
    for _ in range(160):                        # flail
        t += rng.uniform(0.2, 1.5)
        add(type="kd", c=rng.choice(["mod", "tab"]))
        add(type="ku", c="mod")
        if rng.random() < 0.4:
            add(type="win", app=rng.choice(["Safari", "Slack", "VS Code"]))
    t += 70 * 60                                # long idle
    for _ in range(600):                        # mixed
        t += rng.uniform(0.3, 1.2)
        if rng.random() < 0.6:
            key()
        else:
            add(type="mm", d=round(rng.uniform(20, 120), 1))
        if rng.random() < 0.1:
            add(type="ms", dy=1, n=3)
    t += 20 * 60                                # tail
    return events


def write_synthetic_day(date: str, log_dir: str) -> str:
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, f"{date}.jsonl")
    with open(path, "w") as fh:
        for e in synthetic_day_events():
            fh.write(json.dumps(e) + "\n")
    return path


def isolate_dirs(tmp: str):
    """Point the app's data dirs at a temp location. Returns (logs, renders)."""
    from dayplayer import config
    logs = os.path.join(tmp, "logs")
    renders = os.path.join(tmp, "renders")
    os.makedirs(logs, exist_ok=True)
    os.makedirs(renders, exist_ok=True)
    config.LOG_DIR = logs
    config.RENDER_DIR = renders
    return logs, renders
