# The Dayplayer

Your workday is already a performance. This plays it back.

A small daemon records only the **timings** of your computer use — key-press
intervals, mouse distance, scroll velocity, window switches. **Never letters,
never content.** At the end of the day, press Render and the day condenses
into a ~3-minute piece:

- morning burst-typing → driving percussion
- the frustrated flail of alt-tabbing → skittering stutter blips
- the long silent afternoon stretch → one held, uneasy chord
- mouse movement → a soft wash swelling underneath

You hear the difference between a focused Saturday morning and a distracted
one — and it's yours.

## The blind test (the whole point, for now)

Every render produces **two** players: one is your real day, the other is the
*same events with timings shuffled*. Listen blind and vote. If you can
reliably tell which one is you, the structure is real and the concept
survives.

## Quick start (macOS / Windows)

```bash
python3 -m venv .venv
.venv/bin/pip install pynput numpy        # Windows: .venv\Scripts\pip
```

Then on **macOS**, double-click:

1. **`Start Recording.command`** — first run: allow *Input Monitoring* for
   your terminal app when macOS asks (System Settings → Privacy & Security),
   then stop (Ctrl-C) and start again. Work normally for a few hours.
2. **`Open Dayplayer UI.command`** — dashboard opens in your browser
   (http://127.0.0.1:7331). Watch the day's timeline build, then hit
   **Render my day** and take the blind test.

On **Windows**, run the same two steps from a terminal:

```bat
.venv\Scripts\python -m dayplayer.recorder
.venv\Scripts\python -m dayplayer.server
```

## How it works

```
recorder.py   pynput hooks → ~/.dayplayer/logs/YYYY-MM-DD.jsonl
              (coarse classes only: key/space/tab/mod… + timestamps)
features.py   per-minute vectors: key rate, rhythm CV, burstiness,
              flail rate, mouse distance, idle
composer.py   features → score (JSON): ticks, kicks, blips, drones…
synth.py      score → WAV (pure numpy synth, no DAW, no internet)
server.py     local dashboard + blind A/B test + timeline
```

The **score is JSON** — the same score can later be played in a browser
(Tone.js) or wrapped in a native shell without touching the recorder.

Test the whole chain without recording anything:

```bash
.venv/bin/python tests/test_synthetic.py
```

## Privacy

See **[docs/TRUST.md](docs/TRUST.md)** — the short version: raw logs never
leave `~/.dayplayer`, only rendered audio is ever meant to be shared, and the
recorder is open for anyone to read.

## Status

Stage 1 — proof of concept. The gate: *is the real-timing render
distinguishable from the shuffled one?* See docs/PRINCIPLES.md for the
stop/continue rules.
