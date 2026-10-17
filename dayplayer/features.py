"""Feature extraction: raw event log -> per-minute behavioral features.

A minute becomes one feature vector:
  key_rate    key presses / min            (energy)
  key_cv      coefficient of variation of  (rhythm steadiness:
              inter-press intervals         low = metronomic flow,
                                            high = erratic hunting)
  burst       max presses in any 3s        (burstiness)
  mod_rate    mod/tab/esc presses / min    (the Flail)
  switches    app switches / min
  mouse_dist  approx pixels travelled
  click_rate, scroll_rate
  idle        True if almost nothing happened
"""
from __future__ import annotations

import json
import math
import random

from . import config

INPUT_TYPES = {"kd", "mm", "mc", "ms"}
FLAIL_CLASSES = {"mod", "tab", "esc", "fn"}


def load_events(date: str | None = None) -> list[dict]:
    path = config.log_path(date)
    events = []
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue                          # partial line, skip
    except FileNotFoundError:
        return []
    events.sort(key=lambda e: e.get("t", 0))
    return events


def extract(date: str | None = None) -> dict:
    """Return {'minutes': [features...], 'meta': {...}} for a day."""
    events = [e for e in load_events(date) if e.get("type") in INPUT_TYPES
              or e.get("type") == "win"]
    return features_from_events(events, date)


def features_from_events(events: list[dict], date: str | None = None) -> dict:
    """Same pipeline, but over an in-memory event list (e.g. shuffled)."""
    if not events:
        return {"minutes": [], "meta": {"date": date, "empty": True}}

    t0, t1 = events[0]["t"], events[-1]["t"]
    start_min = int(t0 // 60)
    end_min = int(t1 // 60)
    n = end_min - start_min + 1
    minutes = [dict(minute=i, key_rate=0, key_cv=None, burst=0.0,
                    mod_rate=0.0, switches=0.0, mouse_dist=0.0,
                    click_rate=0.0, scroll_rate=0.0, input_events=0,
                    idle=True, apps=[])
               for i in range(n)]

    last_app = None
    last_key_t = None
    for e in events:
        m = minutes[int(e["t"] // 60) - start_min]
        et = e["type"]
        if et == "kd":
            m["key_rate"] += 1
            m["input_events"] += 1
            if e.get("c") in FLAIL_CLASSES:
                m["mod_rate"] += 1
            if last_key_t is not None and e["t"] > last_key_t:
                dt = e["t"] - last_key_t
                m.setdefault("ikis", []).append(dt)
            last_key_t = e["t"]
        elif et == "mm":
            m["mouse_dist"] += e.get("d", 0)
            m["input_events"] += 1
        elif et == "mc":
            if e.get("down"):
                m["click_rate"] += 1
                m["input_events"] += 1
        elif et == "ms":
            m["scroll_rate"] += 1
            m["input_events"] += 1
        elif et == "win":
            if e.get("app") != last_app:
                last_app = e.get("app")
                m["switches"] += 1
                if last_app and last_app not in m["apps"]:
                    m["apps"].append(last_app)

    # second pass: burstiness, cv, idle
    kd_by_min: dict[int, list[float]] = {}
    for e in events:
        if e["type"] == "kd":
            kd_by_min.setdefault(int(e["t"] // 60) - start_min,
                                 []).append(e["t"])
    for i, ts in kd_by_min.items():
        m = minutes[i]
        if ts:
            best = 0
            lo = 0
            for hi in range(len(ts)):
                while ts[hi] - ts[lo] > 3.0:
                    lo += 1
                best = max(best, hi - lo + 1)
            m["burst"] = best / 3.0                    # presses per second
        ikis = m.pop("ikis", None) or []
        if len(ikis) >= 3:
            mean = sum(ikis) / len(ikis)
            var = sum((x - mean) ** 2 for x in ikis) / len(ikis)
            m["key_cv"] = math.sqrt(var) / mean if mean > 0 else None

    for m in minutes:
        m["idle"] = m["input_events"] < config.IDLE_EVENTS_PER_MIN
        m.pop("ikis", None)

    meta = {
        "date": date,
        "start": t0,
        "end": t1,
        "n_minutes": n,
        "active_minutes": sum(1 for m in minutes if not m["idle"]),
        "total_key": sum(m["key_rate"] for m in minutes),
        "total_mouse": round(sum(m["mouse_dist"] for m in minutes)),
    }
    return {"minutes": minutes, "meta": meta}


# ------------------------------------------------------------ blind test
def shuffled_events(date: str | None = None, rng=None) -> list[dict]:
    """Same events, timings shuffled: permute the inter-event gaps.

    Preserves the exact multiset of events and the gap distribution,
    destroys the temporal structure (morning bursts land in the
    'afternoon', idle stretches smear everywhere).
    """
    rng = rng or random.Random()
    events = [e for e in load_events(date)
              if e.get("type") in INPUT_TYPES or e.get("type") == "win"]
    if len(events) < 4:
        return events
    ts = [e["t"] for e in events]
    t0 = ts[0]
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    rng.shuffle(gaps)                                  # identity is 1/n!, ignore
    out = []
    t = t0
    for e, g in zip(events, gaps):
        e2 = dict(e)
        e2["t"] = t
        out.append(e2)
        t += g
    return out
