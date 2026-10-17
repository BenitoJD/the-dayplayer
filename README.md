# Circadia

*formerly The Dayplayer — your workday is already a performance; Circadia plays it back.*

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

## The app (macOS)

Double-click **`Circadia.app`** — a native menu bar app. You'll see **○**
appear in your menu bar.

1. Click the ○ → **Start Recording**. macOS asks once for *Input
   Monitoring* — allow it (System Settings → Privacy & Security). If events
   stay at 0 after allowing, quit the app from the menu and start it again.
2. Work normally. The ○ turns **●** while recording; the menu shows today's
   event count.
3. Tonight: click ● → **▶ Render My Day** (~30s). You get two players:
   **Play A** and **Play B**. One is your real day; the other is the same
   events with timings shuffled. Listen blind, then vote **A is me** /
   **B is me** — the reveal tells you if the structure is real.

If you moved the repo or changed code: run `./make_app.sh` to rebuild the app.

## Circadia Live — hear your state while you work

Menu → **◉ Go Live** (or the GO LIVE button in the dashboard). A window with
a breathing orb opens, and a generative soundscape morphs with your state
in real time:

- **Flow** → a warm pad and a soft heartbeat that tracks your typing tempo
- **Flail** → static and two clashing notes creeping in
- **Drift** → an airy wind wash
- **Quiet** → a low tone, slowly breathing

**Calm mode** hides every number — just orb and sound. A non-judgmental
mirror: nothing to chase, nothing to feel bad about (see PRINCIPLES.md).

## The Week — the audible diary

Dashboard → **WEEK** tab. Seven day-cards show each day's pattern mix;
**▶ RENDER MY WEEK** turns them into one album (~42s per day, crossfaded) —
a week of your life you can *hear*. Tag your days ("shipped", "meeting
day", "good day") on the Today tab; once a tag has ≥2 days, the Week tab
shows what your tagged days look like versus the rest — descriptive, never
scores.

## The app (Windows)

Option A — **download the ready-made exe**: go to
[Actions](https://github.com/BenitoJD/the-dayplayer/actions) → latest
"Build Windows app" run → scroll to **Artifacts** → download
**Dayplayer-Windows** → unzip → double-click `Dayplayer.exe`.

Option B — build it yourself on any Windows PC with Python 3.11+:
double-click **`build_windows.bat`** → your app appears at
`dist\Dayplayer.exe`.

Either way: `Dayplayer.exe` lives in your **system tray** (near the clock).
Double-click the tray icon to start/stop recording — **no permission
prompt on Windows**, it just works. Right-click for the full menu
(Render, Play A/B, vote, Quit) — same features as the macOS app.

## The dashboard

From the menu bar / tray menu choose **◈ Open Dashboard** — a futuristic
window (same on both platforms) with everything about your day:

![dashboard](docs/dashboard-preview.png)

- **Today's timeline** — per-minute typing/mouse/idle, colored by pattern,
  hover any minute for detail
- **Patterns** — Flow / Flail / Drift / Mire minute counts (patterns,
  never productivity scores — see docs/PRINCIPLES.md)
- **Stat cards** — typing events, active minutes, longest flow streak,
  flail minutes, app switches, mouse distance
- **Top apps**, busiest hour
- **Render My Day** with waveform players for the blind A/B test and vote

## The blind test is the gate

Continue if the real-timing render is distinguishable and you *want to hear
it again*. Revise the mapping if it's mush. Stop claiming success if only
the technical render works but hearing it tells you nothing.
See docs/PRINCIPLES.md.

## How it works

```
recorder.py    pynput hooks → ~/.dayplayer/logs/YYYY-MM-DD.jsonl
               (coarse classes only: key/space/tab/mod… + timestamps;
               macOS + Windows + Linux in one codebase)
features.py    per-minute vectors: key rate, rhythm CV, burstiness,
               flail rate, mouse distance, idle
composer.py    features → score (JSON): ticks, kicks, blips, drones…
synth.py       score → WAV (pure numpy synth, no DAW, no internet)
controller.py  shared brain: recorder + render + blind session + votes
app.py         macOS menu bar app (rumps) — ● / ○ in the menu bar
wintray.py     Windows system tray app (pystray) — same features
playback.py    afplay (mac) / winsound (win) / paplay (linux)
server.py      optional local dashboard (kept for the future share player)
```

Packaging: `make_app.sh` (mac dev bundle), `build_windows.bat` (exe),
and GitHub Actions builds `Dayplayer.exe` on every push.

The **score is JSON** — the same score can later be played in a browser
(Tone.js) or wrapped in a native Windows shell without touching the recorder.

Test the whole chain without recording anything:

```bash
.venv/bin/python tests/test_synthetic.py
```

## Privacy

See **[docs/TRUST.md](docs/TRUST.md)** — the short version: raw logs never
leave `~/.dayplayer`, only rendered audio is ever meant to be shared, and the
recorder is open for anyone to read.

## Roadmap

- **Stage 1 (now):** macOS menu bar app + blind test. Gate: is the
  real-timing render distinguishable from the shuffled one?
- **Stage 2:** signed & notarized .dmg, Windows shell, shareable render
  links (web player for audio only).
- **Stage 3:** mapping packs, week/month renders ("the audible diary"),
  named patterns (Flow, Flail, Drift, Mire).
