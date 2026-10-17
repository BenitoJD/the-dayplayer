"""The composer: per-minute behavioral features -> a music "score".

The mapping (documented so it can be revised — the CONCEPT stays):

  typing energy        -> driving percussion (tick density & velocity)
  rhythm steadiness    -> quantized pulse when steady, skittering
                          jitter when erratic (key_cv)
  mod/tab/esc flailing -> skittering stutter blips, register jumps
  app switching        -> same flail family, more blips
  long idle stretch    -> one held, uneasy drone chord; the tension
                          (minor-2nd cluster) grows with stretch length
  mouse distance       -> a soft noise wash swelling under everything
  scrolling            -> faint high shimmer grains

Score = JSON dict; synth.py renders it to WAV. Same score could later
be played in a browser (Tone.js) without change.
"""
from __future__ import annotations

import random

from . import config

# A minor pentatonic (MIDI): A C D E G
PENTATONIC = [57, 60, 62, 64, 67]
ROOT = 45          # A2
FIFTH = 52         # E3
TENSION = 46       # Bb2 — the uneasy one


def _norm(value, scale):
    return max(0.0, min(1.0, value / scale)) if scale else 0.0


def compose(feature_data: dict, seed: int | None = None,
            target_duration: float | None = None) -> dict:
    """features.extract() output -> score dict.

    target_duration: seconds for the whole piece (default ~3 min);
    render_week uses ~40s per day so seven days become one album."""
    rng = random.Random(seed)
    minutes = feature_data["minutes"]
    meta = feature_data.get("meta", {})
    if not minutes:
        return {"duration": 10, "tracks": {}, "meta": meta, "empty": True}

    n = len(minutes)
    dur = target_duration or config.TARGET_DURATION
    spm = dur / n                                     # seconds per minute
    bpm = 96
    beat = 60.0 / bpm
    eighth = beat / 2

    active = [m for m in minutes if not m["idle"]]
    key_rates = sorted(m["key_rate"] for m in active) or [0]
    k_hi = max(key_rates[int(len(key_rates) * 0.6)], 25)   # p60: normal busy
    k_med = key_rates[len(key_rates) // 2]
    m_hi = max((m["mouse_dist"] for m in active), default=1) or 1

    tracks = {"tick": [], "kick": [], "flail": [], "drone": [],
              "wash": [], "shimmer": []}

    idle_run = 0
    idle_start = None
    tick_carry = 0.0          # fractional notes carry across minutes, so the
    flail_carry = 0.0         # density survives ANY day length (a 24h day
    last_kick = -9.0          # used to render completely silent)
    for i, m in enumerate(minutes):
        t0 = i * spm

        if m["idle"]:
            if idle_start is None:
                idle_start = t0
            idle_run += 1
            continue

        # ---- flush a completed idle stretch as one held drone chord
        if idle_start is not None:
            _emit_drone(tracks, idle_start, t0 - idle_start, idle_run, rng)
            idle_start, idle_run = None, 0

        # ---- percussion from typing energy
        intensity = _norm(m["key_rate"], k_hi)
        cv = m["key_cv"]
        # density: 0.3 floor for any real typing, up to ~7 ticks/s
        want = ((0.3 + 0.7 * intensity) * spm * 7
                if m["key_rate"] >= 5 else intensity * spm * 4)
        tick_carry += want
        n_ticks = int(tick_carry)
        tick_carry -= n_ticks
        if n_ticks > 0:
            steady = cv is not None and cv < 0.55
            grid = [t0 + j * eighth for j in range(int(spm / eighth) + 1)]
            for j in range(n_ticks):
                if steady:                             # flow: on the grid
                    t = grid[j % len(grid)]
                    jitter = 0.0
                else:                                  # hunt: skitter
                    t = t0 + rng.random() * spm
                    jitter = _norm(cv or 1.0, 1.6)
                tracks["tick"].append({
                    "t": round(t, 3), "vel": 0.35 + 0.55 * intensity,
                    "jitter": round(jitter, 3)})
            # accents, but never closer than ~1.6s (keeps kick a pulse,
            # not a machine gun, on very long days)
            busy = (m["burst"] > 2.2 or m["key_rate"] > k_med * 1.4
                    or m["key_rate"] >= k_hi)
            if busy and (t0 - last_kick) >= 1.6:
                last_kick = t0
                tracks["kick"].append({"t": round(t0, 3),
                                       "vel": 0.5 + 0.4 * intensity})

        # ---- the Flail: mod-keys + app switches
        flail_n = int(m["mod_rate"] + 2 * m["switches"])
        if flail_n >= config.HIGH_SWITCHES_PER_MIN or flail_n >= 3:
            flail_carry += min(flail_n, spm * 4)
            n_flail = int(flail_carry)
            flail_carry -= n_flail
            for _ in range(n_flail):
                octave = rng.choice([0, 12, 12, 24])   # register jumps
                note = rng.choice(PENTATONIC) + octave
                tracks["flail"].append({
                    "t": round(t0 + rng.random() * spm, 3),
                    "midi": note, "vel": 0.5 + 0.3 * rng.random()})

        # ---- mouse wash
        wash_amp = _norm(m["mouse_dist"], m_hi)
        if wash_amp > 0.05:
            tracks["wash"].append({"t": round(t0, 2), "dur": round(spm, 2),
                                   "amp": round(wash_amp * 0.6, 3)})

        # ---- scroll shimmer
        for _ in range(min(int(m["scroll_rate"] / 2), 6)):
            tracks["shimmer"].append({
                "t": round(t0 + rng.random() * spm, 3),
                "vel": 0.15 + 0.2 * rng.random()})

    # trailing idle stretch (the long quiet ride home)
    if idle_start is not None:
        _emit_drone(tracks, idle_start, dur - idle_start, idle_run, rng)

    # resolve: a clean open fifth at the very end
    tracks["drone"].append({"t": round(dur - 4.0, 2), "dur": 4.0,
                            "notes": [ROOT, FIFTH], "tension": 0.0,
                            "vel": 0.7})

    score = {"duration": dur, "bpm": bpm, "root": ROOT,
             "tracks": tracks, "meta": meta}
    return score


def _emit_drone(tracks, t0, length, idle_minutes, rng):
    if length <= 0.2:
        return
    tension = min(1.0, idle_minutes / 25.0)            # grows with stretch
    notes = [ROOT, FIFTH]
    if tension > 0.15:
        notes.append(TENSION)                          # the uneasy note
    tracks["drone"].append({
        "t": round(t0, 2), "dur": round(min(length, 120.0), 2),
        "notes": notes, "tension": round(tension, 3),
        "vel": 0.55 + 0.25 * tension})
