"""Synth: score -> WAV. Pure numpy, no DAW, no internet.

Small subtractive/additive voices:
  tick    band-passed noise grain        (typing percussion)
  kick    sine drop 110->40 Hz           (burst accents)
  flail   detuned saw blip, hi register  (alt-tab stutter)
  drone   detuned saw stack + lowpass,   (idle stretch; tension adds a
          slow tremolo                    minor-2nd cluster)
  wash    lowpassed noise swell          (mouse movement)
  shimmer high sine grain                (scrolling)

Everything is deterministic given the score.
"""
from __future__ import annotations

import math
import wave

import numpy as np

from . import config

SR = config.SAMPLE_RATE


def _midi_hz(m: int) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _env_attack_decay(n: int, attack: float, decay_tau: float) -> np.ndarray:
    t = np.arange(n) / SR
    env = np.exp(-t / decay_tau)
    a = min(n, max(1, int(attack * SR)))
    env[:a] *= np.linspace(0, 1, a)
    return env


def _lowpass(x: np.ndarray, cutoff_hz: float) -> np.ndarray:
    """FFT one-pole-ish lowpass."""
    f = np.fft.rfftfreq(len(x), 1 / SR)
    mask = 1 / (1 + (f / max(cutoff_hz, 1)) ** 2)
    return np.fft.irfft(np.fft.rfft(x) * mask, n=len(x))


def _bandpass_noise(n: int, lo: float, hi: float, rng: np.random.Generator):
    x = rng.standard_normal(n)
    f = np.fft.rfftfreq(n, 1 / SR)
    mask = 1 / (1 + (lo / np.maximum(f, 1)) ** 4) / (1 + (f / hi) ** 4)
    return np.fft.irfft(np.fft.rfft(x) * mask, n=len(x))


class Synth:
    def __init__(self, duration: float, seed: int = 7):
        self.buf = np.zeros(int(duration * SR) + int(SR * 2))
        self.rng = np.random.default_rng(seed)
        # precompute one filtered-noise pool for ticks
        pool_n = int(0.3 * SR)
        self.tick_pool = _bandpass_noise(pool_n, 3000, 9000, self.rng)

    def _add(self, start_s: float, x: np.ndarray):
        i = int(start_s * SR)
        if i < 0:
            x, i = x[-i:], 0
        j = min(len(self.buf), i + len(x))
        if j > i:
            self.buf[i:j] += x[: j - i]

    # ----------------------------------------------------------------voices
    def tick(self, t: float, vel: float, jitter: float):
        n = int((0.02 + 0.03 * (1 - jitter)) * SR)
        i0 = self.rng.integers(0, len(self.tick_pool) - n)
        grain = self.tick_pool[i0:i0 + n].copy()
        grain *= _env_attack_decay(n, 0.001, 0.012) * vel * 0.35
        self._add(t, grain)

    def kick(self, t: float, vel: float):
        n = int(0.30 * SR)
        tt = np.arange(n) / SR
        freq = 40 + 70 * np.exp(-tt / 0.04)
        phase = 2 * np.pi * np.cumsum(freq) / SR
        x = np.sin(phase) * _env_attack_decay(n, 0.002, 0.09) * vel * 0.8
        self._add(t, x)

    def blip(self, t: float, midi: int, vel: float):
        n = int(0.09 * SR)
        tt = np.arange(n) / SR
        f = _midi_hz(midi)
        x = (np.sign(np.sin(2 * np.pi * f * tt)) * 0.6
             + np.sign(np.sin(2 * np.pi * f * 1.007 * tt)) * 0.4)
        x *= _env_attack_decay(n, 0.001, 0.025) * vel * 0.22
        self._add(t, _lowpass(x, 3500))

    def drone(self, t: float, dur: float, notes, tension: float, vel: float):
        n = int(dur * SR)
        tt = np.arange(n) / SR
        x = np.zeros(n)
        for m in notes:
            f = _midi_hz(m)
            x += (np.sin(2 * np.pi * f * tt)
                  + 0.5 * np.sin(2 * np.pi * f * 1.004 * tt)
                  + 0.25 * np.sin(2 * np.pi * f * 0.996 * tt))
        x /= (3 * len(notes))
        # unease: slow tremolo whose depth grows with tension
        lfo = 0.5 + 0.5 * np.sin(2 * np.pi * (0.3 + tension) * tt)
        x *= 1 - tension * 0.5 * lfo
        attack = min(1.5, max(0.3, dur * 0.2))
        env = np.minimum(1, tt / max(attack, 1e-6))
        rel = int(min(n * 0.3, 1.2 * SR))
        env[-rel:] *= np.linspace(1, 0, rel)
        x *= env * vel * 0.5
        self._add(t, _lowpass(x, 700 + 900 * (1 - tension)))

    def wash(self, t: float, dur: float, amp: float):
        n = int(dur * SR)
        x = self.rng.standard_normal(n)
        x = _lowpass(x, 650)
        tt = np.arange(n) / SR
        env = np.minimum(1, tt / max(0.8, 1e-6))
        rel = int(min(n * 0.4, 1.0 * SR))
        env[-rel:] *= np.linspace(1, 0, rel)
        self._add(t, x * env * amp * 0.18)

    def shimmer(self, t: float, vel: float):
        n = int(0.05 * SR)
        tt = np.arange(n) / SR
        f = self.rng.uniform(2200, 4200)
        x = np.sin(2 * np.pi * f * tt) * _env_attack_decay(n, 0.002, 0.012)
        self._add(t, x * vel * 0.12)


def render(score: dict, out_path: str, seed: int = 7) -> str:
    """Render a score dict to a 16-bit stereo WAV."""
    tr = score.get("tracks", {})
    s = Synth(score["duration"], seed)

    for e in tr.get("tick", []):
        s.tick(e["t"], e["vel"], e.get("jitter", 0))
    for e in tr.get("kick", []):
        s.kick(e["t"], e["vel"])
    for e in tr.get("flail", []):
        s.blip(e["t"], e["midi"], e["vel"])
    for e in tr.get("drone", []):
        s.drone(e["t"], e["dur"], e.get("notes", [45, 52]),
                e.get("tension", 0), e.get("vel", 0.6))
    for e in tr.get("wash", []):
        s.wash(e["t"], e["dur"], e["amp"])
    for e in tr.get("shimmer", []):
        s.shimmer(e["t"], e["vel"])

    n = int(score["duration"] * SR)
    out = s.buf[:n]
    # global fades
    fi = int(1.5 * SR)
    out[:fi] *= np.linspace(0, 1, fi)
    fo = int(3.0 * SR)
    out[-fo:] *= np.linspace(1, 0, fo)
    # soft clip + normalize
    out = np.tanh(out * 1.2)
    peak = np.max(np.abs(out)) or 1.0
    out = out / peak * 0.89

    pcm = (out * 32767).astype(np.int16)
    stereo = np.column_stack([pcm, pcm]).tobytes()
    with wave.open(out_path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo)
    return out_path
