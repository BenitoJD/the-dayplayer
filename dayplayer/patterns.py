"""Named usage patterns — the shared vocabulary (docs/PRINCIPLES.md).

Descriptive, not judgmental: these are *patterns*, never scores.

  FLOW   steady, sustained typing — the work is carrying you
  FLAIL  mod-keys + app switches — hunting, interrupting, context juggling
  DRIFT  mouse/scroll wandering, little typing
  MIRE   near-silence — meetings, reading, gone-for-coffee, thinking
"""
from __future__ import annotations

from . import features

FLOW, FLAIL, DRIFT, MIRE = "flow", "flail", "drift", "mire"

PATTERN_META = {
    FLOW:  {"label": "Flow",  "color": "#f0b429", "desc": "steady, sustained typing"},
    FLAIL: {"label": "Flail", "color": "#ef6c57", "desc": "alt-tab storms, context juggling"},
    DRIFT: {"label": "Drift", "color": "#5b8def", "desc": "mouse wandering, little typing"},
    MIRE:  {"label": "Mire",  "color": "#3a4256", "desc": "quiet stretch — meeting, reading, thinking"},
}


def classify_minute(m: dict, med_key: float) -> str:
    if m["idle"]:
        return MIRE
    flail_signal = m["mod_rate"] + 2 * m["switches"]
    if flail_signal >= 3:
        return FLAIL
    if m["key_rate"] >= max(8, med_key * 0.7) and (
            m["key_cv"] is None or m["key_cv"] < 0.8):
        return FLOW
    if m["mouse_dist"] + 40 * m["scroll_rate"] > max(300, m["key_rate"] * 6):
        return DRIFT
    return FLOW if m["key_rate"] > 5 else DRIFT


def day_summary(date: str | None = None) -> dict:
    """Full pattern summary for a day, for the dashboard."""
    data = features.extract(date)
    minutes = data["minutes"]
    meta = data["meta"]
    if not minutes:
        return {"empty": True, "date": date}

    active = [m for m in minutes if not m["idle"]]
    keys = sorted(m["key_rate"] for m in active) or [0]
    med_key = keys[len(keys) // 2]

    counts = {FLOW: 0, FLAIL: 0, DRIFT: 0, MIRE: 0}
    for m in minutes:
        m["pattern"] = classify_minute(m, med_key)
        counts[m["pattern"]] += 1

    # per-minute pattern strip for the timeline
    strip = [m["pattern"] for m in minutes]

    # app presence: appearance counts
    apps: dict[str, int] = {}
    for m in minutes:
        for a in m["apps"]:
            apps[a] = apps.get(a, 0) + 1
    top_apps = sorted(apps.items(), key=lambda kv: -kv[1])[:6]

    # longest flow streak
    best = cur = 0
    for p in strip:
        cur = cur + 1 if p == FLOW else 0
        best = max(best, cur)

    # busiest hour by input events
    start_ts = meta["start"]
    per_hour: dict[int, int] = {}
    for m in minutes:
        import time as _t
        hour = _t.localtime(start_ts + m["minute"] * 60).tm_hour
        per_hour[hour] = per_hour.get(hour, 0) + m["input_events"]
    busiest_hour = max(per_hour, key=per_hour.get) if per_hour else None

    return {
        "empty": False,
        "date": date or meta.get("date"),
        "minutes": minutes,
        "strip": strip,
        "counts": counts,
        "n_minutes": len(minutes),
        "active_minutes": len(active),
        "total_key": sum(m["key_rate"] for m in minutes),
        "total_clicks": sum(int(m["click_rate"]) for m in minutes),
        "mouse_km": sum(m["mouse_dist"] for m in minutes) / 1000.0,
        "switches": sum(m["switches"] for m in minutes),
        "top_apps": top_apps,
        "longest_flow": best,
        "busiest_hour": busiest_hour,
        "start_ts": start_ts,
    }
