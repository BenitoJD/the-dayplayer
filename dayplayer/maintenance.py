"""Looking after the user's data: what is there, and how to erase it.

A product that watches your input has to make deleting it trivially easy
and completely honest about what gets removed. Nothing here touches
anything outside ~/.dayplayer.
"""
from __future__ import annotations

import glob
import json
import os
import shutil

from . import config

TAGS_FILE = os.path.join(config.DATA_DIR, "tags.json")
STATE_FILE = os.path.join(config.DATA_DIR, "state.json")


def state() -> dict:
    try:
        with open(STATE_FILE) as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def set_state(**kw):
    data = state()
    data.update(kw)
    config.ensure_dirs()
    with open(STATE_FILE, "w") as fh:
        json.dump(data, fh, indent=2)


def needs_onboarding() -> bool:
    return not state().get("onboarded")


def mark_onboarded():
    set_state(onboarded=True)


def _dir_size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def data_summary() -> dict:
    """Everything Circadia has stored, in human terms."""
    days, events, log_bytes = 0, 0, 0
    for path in glob.glob(os.path.join(config.LOG_DIR, "*.jsonl")):
        days += 1
        try:
            log_bytes += os.path.getsize(path)
            with open(path) as fh:
                for line in fh:
                    if line.strip():
                        events += 1
        except OSError:
            pass
    renders = [d for d in glob.glob(os.path.join(config.RENDER_DIR, "*"))
               if os.path.isdir(d)]
    render_bytes = _dir_size(config.RENDER_DIR)
    try:
        with open(TAGS_FILE) as fh:
            tagged = len(json.load(fh))
    except Exception:
        tagged = 0
    return {
        "days": days,
        "events": events,
        "log_bytes": log_bytes,
        "renders": len(renders),
        "render_bytes": render_bytes,
        "tagged_days": tagged,
    }


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


def summary_text(s: dict | None = None) -> str:
    s = s or data_summary()
    if not s["days"] and not s["renders"]:
        return "Nothing stored yet."
    return (f"{s['days']} day(s) of timings, {s['events']:,} events "
            f"({_human(s['log_bytes'])}), {s['renders']} render(s) "
            f"({_human(s['render_bytes'])}), {s['tagged_days']} tagged "
            f"day(s).")


def delete_all_data(stop_recording: bool = True) -> dict:
    """Erase every recording, render, and tag. Returns what was removed."""
    if stop_recording:
        try:
            from .recorder import stop_recorder
            stop_recorder()
        except Exception:
            pass
    before = data_summary()
    for pattern in (os.path.join(config.LOG_DIR, "*"),
                    os.path.join(config.RENDER_DIR, "*")):
        for path in glob.glob(pattern):
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    os.remove(path)
            except OSError:
                pass
    for path in (TAGS_FILE,
                 os.path.join(config.DATA_DIR, "recorder.pid"),
                 os.path.join(config.DATA_DIR, "recorder.alive")):
        try:
            os.remove(path)
        except OSError:
            pass
    config.ensure_dirs()
    after = data_summary()
    return {"removed": before, "remaining": after,
            "freed_bytes": max(0, before["log_bytes"]
                               + before["render_bytes"]
                               - after["log_bytes"]
                               - after["render_bytes"])}
