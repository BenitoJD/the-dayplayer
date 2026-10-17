"""Circadia Live — real-time sonification of your working state.

Tails the day's log (works whether the recorder is the menu bar app,
the tray app, or an embedded one), classifies the last 60 seconds into
a pattern every second, and plays a generative soundscape that morphs
with your state:

  FLOW   warm pad + a soft heartbeat pulse that tracks your typing tempo
  FLAIL  static, skittering gates, two close notes beating against each other
  DRIFT  a slow airy wash
  MIRE   a quiet low tone, breathing

No scores, no numbers pushed at you — the sound IS the mirror.
(Audio needs `sounddevice`; analysis works without it.)
"""
from __future__ import annotations

import json
import math
import threading
import time
from collections import deque

from . import config, patterns

SR = 44100
BLOCK = 512
WINDOW = 60.0            # analysis window (seconds)
SMOOTH = 1.6             # state crossfade time (seconds)


class LiveEngine:
    def __init__(self, log_path: str | None = None):
        self.log_path = log_path or config.today_log_path()
        self._fixed_path = log_path                    # honored while same day
        self._fixed_date = time.strftime("%Y-%m-%d")
        self.trusted = True                            # set in start()
        self.state = patterns.MIRE
        self.weights = {k: 1.0 if k == patterns.MIRE else 0.0
                        for k in patterns.PATTERN_META}
        self.cps = 0.0                 # keys per second (last 10s)
        self.running = False
        self.gain = 0.7
        self.audio_on = False
        self._events: deque[dict] = deque()
        self._pending = ""                     # half-written log line
        self.started_recorder = False          # did WE spawn the recorder?
        self._stop = threading.Event()
        self._med_key_ema = 40.0
        self._stream = None
        # audio state
        import numpy as np
        self.np = np
        self._ph = {}                  # oscillator phases
        self._pulse_at = 0.0           # next pulse trigger (seconds)

    # --------------------------------------------------------- lifecycle
    def start(self, with_audio: bool = True):
        if self.running:
            return
        from .recorder import macos_input_trusted
        self.trusted = macos_input_trusted()
        self.running = True
        self._stop.clear()
        self._maybe_start_recorder()
        threading.Thread(target=self._tail_loop, daemon=True).start()
        threading.Thread(target=self._tick_loop, daemon=True).start()
        if with_audio:
            self._start_audio()

    def stop(self):
        self._stop.set()
        if self._stream:
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self.audio_on = False
        # the recorder keeps running on purpose: recording is the app's
        # job, live mode is just a listener (stop it from the menu/tray)
        self.running = False

    # ----------------------------------------------------------- inputs
    def _maybe_start_recorder(self):
        """If nobody is recording, spawn the recorder PROCESS.

        Never in-process: pynput's macOS keyboard listener crashes inside
        a Cocoa/Qt app, and Qt windows are exactly where live mode runs.
        """
        from .recorder import recorder_running, spawn_recorder
        try:
            if recorder_running():
                return
            self.started_recorder = spawn_recorder()
        except Exception:
            self.started_recorder = False

    def _tail_loop(self):
        """Follow the day's log file like `tail -f`."""
        fh = None
        cur_date = time.strftime("%Y-%m-%d")
        while not self._stop.is_set():
            try:
                today = time.strftime("%Y-%m-%d")
                if fh is None or today != cur_date:
                    if fh:
                        fh.close()
                    cur_date = today
                    # honor a caller-provided path while it's still that day
                    if self._fixed_path and today == self._fixed_date:
                        self.log_path = self._fixed_path
                    else:
                        self.log_path = config.log_path(today)
                    fh = open(self.log_path)
                    fh.seek(0, 2)                  # jump to end
                line = fh.readline()
                if not line:
                    time.sleep(0.3)
                    continue
                if not line.endswith("\n"):
                    # a half-written line (the recorder flushes mid-write):
                    # hold it and finish it on the next pass instead of
                    # dropping the event and mis-parsing its tail
                    self._pending += line
                    time.sleep(0.2)
                    continue
                full = self._pending + line
                self._pending = ""
                try:
                    self._events.append(json.loads(full))
                except json.JSONDecodeError:
                    continue
                now = time.time()
                while self._events and now - self._events[0]["t"] > 120:
                    self._events.popleft()
            except FileNotFoundError:
                time.sleep(0.5)
            except Exception:
                time.sleep(0.5)

    # --------------------------------------------------------- analysis
    def _tick_loop(self):
        while not self._stop.is_set():
            try:
                self._analyze()
            except Exception:
                pass
            self._stop.wait(1.0)

    def _pseudo_minute(self) -> dict | None:
        now = time.time()
        ev = [e for e in self._events if now - e["t"] <= WINDOW
              and e.get("type") in ("kd", "mm", "mc", "ms", "win")]
        if not ev:
            return None
        kd_ts, ikis = [], []
        last = None
        flail_classes = {"mod", "tab", "esc", "fn"}
        m = dict(key_rate=0, mod_rate=0.0, switches=0.0, mouse_dist=0.0,
                 scroll_rate=0.0, click_rate=0.0, input_events=0, idle=False)
        last_app = None
        for e in ev:
            et = e["type"]
            m["input_events"] += 1
            if et == "kd":
                m["key_rate"] += 1
                if e.get("c") in flail_classes:
                    m["mod_rate"] += 1
                if last is not None:
                    ikis.append(e["t"] - last)
                last = e["t"]
                kd_ts.append(e["t"])
            elif et == "mm":
                m["mouse_dist"] += e.get("d", 0)
            elif et == "mc":
                if e.get("down"):
                    m["click_rate"] += 1
            elif et == "ms":
                m["scroll_rate"] += 1
            elif et == "win":
                if e.get("app") != last_app:
                    last_app = e.get("app")
                    m["switches"] += 1
        if len(ikis) >= 3:
            mean = sum(ikis) / len(ikis)
            var = sum((x - mean) ** 2 for x in ikis) / len(ikis)
            m["key_cv"] = math.sqrt(var) / mean if mean > 0 else None
        else:
            m["key_cv"] = None
        self.cps = sum(1 for t in kd_ts if now - t <= 10) / 10.0
        return m

    def _analyze(self):
        m = self._pseudo_minute()
        if m is None or m["input_events"] < config.IDLE_EVENTS_PER_MIN:
            self.state = patterns.MIRE
            return
        if m["key_rate"] >= 5:
            k = 0.9 * self._med_key_ema + 0.1 * m["key_rate"]
            self._med_key_ema = max(k, 8.0)
        self.state = patterns.classify_minute(m, self._med_key_ema)

    # ------------------------------------------------------------ audio
    def _start_audio(self):
        try:
            import sounddevice as sd
            self._stream = sd.OutputStream(
                samplerate=SR, blocksize=BLOCK, channels=2,
                dtype="float32", callback=self._audio_cb)
            self._stream.start()
            self.audio_on = True
        except Exception:
            self._stream = None
            self.audio_on = False

    def _phv(self, key, freq, n):
        """Vectorized phase accumulator; returns phases [0,1) + saw."""
        np = self.np
        p0 = self._ph.get(key, 0.0)
        ph = (p0 + freq / SR * np.arange(n)) % 1.0
        self._ph[key] = float(ph[-1])
        return ph

    def _audio_cb(self, outdata, frames, time_info, status):
        """sounddevice output-stream callback: (outdata, frames, time, status).

        Wrapped in try/except: a bug in the synth must never spam or kill
        the audio thread — we just go quiet for that block instead.
        """
        try:
            self._render_block(outdata, frames)
        except Exception:
            try:
                outdata.fill(0)
            except Exception:
                pass

    def _render_block(self, outdata, frames):
        np = self.np
        n = frames
        t_now = time.time()
        # smooth weights toward one-hot(state) continuously
        target = {k: (1.0 if k == self.state else 0.0)
                  for k in self.weights}
        step = n / SR / SMOOTH
        mix = np.zeros(n)
        for k, w in self.weights.items():
            self.weights[k] = w + (target[k] - w) * min(step, 1.0)

        # ---- FLOW: warm pad + heartbeat pulse tracking typing tempo
        if self.weights[patterns.FLOW] > 0.01:
            w = self.weights[patterns.FLOW]
            p1 = self._phv("flow1", 110.0, n)
            p2 = self._phv("flow2", 110.0 * 1.004, n)
            p3 = self._phv("flow3", 164.81, n)
            pad = (np.sin(2 * np.pi * p1) + 0.6 * np.sin(2 * np.pi * p2)
                   + 0.35 * np.sin(2 * np.pi * p3)) / 1.95
            # heartbeat: bpm tracks typing tempo
            bpm = min(110.0, max(44.0, 40.0 + self.cps * 30.0))
            interval = 60.0 / bpm
            tt = np.arange(n) / SR
            phase = (t_now % interval)
            env = np.exp(-((phase + tt) % interval) * 9.0)
            thump = np.sin(2 * np.pi * 52.0 * ((phase + tt) % interval)) * env
            mix += w * (0.22 * pad + 0.20 * thump)

        # ---- FLAIL: static, skitter gates, beating seconds
        if self.weights[patterns.FLAIL] > 0.01:
            w = self.weights[patterns.FLAIL]
            rng = np.random.default_rng()
            noise = rng.standard_normal(n)
            noise = np.diff(noise, prepend=0.0)     # high-passed
            pa = self._phv("fl1", 220.0, n)
            pb = self._phv("fl2", 233.1, n)         # close -> beating
            beat = 0.4 * (np.sin(2 * np.pi * pa) + np.sin(2 * np.pi * pb))
            gate = (np.sin(2 * np.pi * self._phv("gate", 3.3, n)) > 0.15)
            mix += w * (0.12 * noise * gate + 0.16 * beat * (1 - gate * 0.5))

        # ---- DRIFT: airy wash
        if self.weights[patterns.DRIFT] > 0.01:
            w = self.weights[patterns.DRIFT]
            rng = np.random.default_rng()
            noise = rng.standard_normal(n)
            wash = np.convolve(noise, np.ones(12) / 12, mode="same")
            lfo = 0.5 + 0.5 * np.sin(2 * np.pi * self._phv("lfo", 0.09, n))
            mix += w * 0.16 * wash * (0.4 + 0.6 * lfo)

        # ---- MIRE: quiet breathing low tone
        if self.weights[patterns.MIRE] > 0.01:
            w = self.weights[patterns.MIRE]
            pm = self._phv("mire", 55.0, n)
            breathe = 0.5 + 0.5 * np.sin(2 * np.pi * self._phv("br", 0.05, n))
            mix += w * 0.10 * np.sin(2 * np.pi * pm) * breathe

        out = np.tanh(mix * self.gain * 1.4)
        stereo = np.column_stack([out, out]).astype(np.float32)
        outdata[:n] = stereo
