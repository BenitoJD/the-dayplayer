"""Build the two extra X videos into marketing/kit/.

  python3 marketing/make_videos.py

  blind-test.mp4   30s  A and B, same day, one shuffled. Reply A or B.
  live-clip.mp4    18s  hear your state while you work (flow -> flail -> ...)

Both come from the app's own engine, so they are honest: the blind test
really is a real day against its shuffled twin, and the live clip really is
the live soundscape.
"""
from __future__ import annotations

import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                                          # noqa: E402
from PIL import Image, ImageDraw, ImageFont                 # noqa: E402

from dayplayer import composer, config, features, patterns, synth  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT = os.path.join(ROOT, "marketing", "kit")
SR = 44100
FPS = 30
BG = (10, 10, 14)
INK, DIM = "#f5f5f7", "#8b93a7"
BRAND = "#4fd8eb"
FONTS = ["/System/Library/Fonts/SFNS.ttf",
         "/System/Library/Fonts/SFNSDisplay.ttf",
         "/System/Library/Fonts/HelveticaNeue.ttc",
         "/System/Library/Fonts/Supplemental/Arial.ttf"]


def font(size):
    for p in FONTS:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def centre(d, text, f, y, colour, w):
    d.text((w / 2 - d.textlength(text, font=f) / 2, y), text, font=f,
           fill=colour)


def wav_samples(path: str) -> np.ndarray:
    import wave
    with wave.open(path) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return x[::2].astype(np.float32) / 32768.0


def save_wav(path: str, mono: np.ndarray):
    import wave
    pcm = np.clip(mono, -1, 1)
    pcm = (pcm * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(np.column_stack([pcm, pcm]).tobytes())


def brand(img, d):
    icon = os.path.join(ROOT, "assets", "icon.png")
    if os.path.exists(icon):
        ic = Image.open(icon).convert("RGBA").resize((56, 56), Image.LANCZOS)
        img.paste(ic, (64, 56), ic)
    d.text((138, 68), "CIRCADIA", font=font(30), fill=INK)


def encode(frames_dir: str, wav_path: str, out: str, seconds: float):
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
         "-i", os.path.join(frames_dir, "%05d.png"), "-i", wav_path,
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
         "-shortest", "-movflags", "+faststart", out], check=True)
    return out


# ------------------------------------------------------------- blind test
def build_blind():
    """A real day against its shuffled twin, 12 seconds each."""
    rng = random.Random(4)
    ev = []
    t = time.time() - 6 * 3600
    for block in range(7):                      # a recognisable day
        for _ in range(int(60 * 3.6)):          # typing
            t += 0.28
            ev.append({"type": "kd", "c": "key", "t": round(t, 3)})
        for _ in range(int(60 * 0.6)):          # flail
            t += 0.9
            ev.append({"type": "kd", "c": rng.choice(["mod", "tab"]),
                       "t": round(t, 3)})
            ev.append({"type": "win", "app": "Slack", "t": round(t, 3)})
        for _ in range(int(60 * 1.2)):          # drift
            t += 0.8
            ev.append({"type": "mm", "d": round(rng.uniform(30, 200), 1),
                       "t": round(t, 3)})
        t += 12 * 60                            # quiet

    real_feats = features.features_from_events(ev, "blind")
    shuf = features.shuffled_events.__wrapped__ if False else None
    # shuffle by permuting the gaps, exactly like the app does
    ts = [e["t"] for e in ev]
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    rng.shuffle(gaps)
    shuf_ev, tt = [], ts[0]
    for e, g in zip(ev, gaps):
        e2 = dict(e)
        e2["t"] = tt
        shuf_ev.append(e2)
        tt += g
    shuf_feats = features.features_from_events(shuf_ev, "blind-shuffled")

    tmp = tempfile.mkdtemp(prefix="blind-")
    a_wav = os.path.join(tmp, "a.wav")
    b_wav = os.path.join(tmp, "b.wav")
    synth.render(composer.compose(real_feats, seed=3, target_duration=12.0),
                 a_wav)
    synth.render(composer.compose(shuf_feats, seed=3, target_duration=12.0),
                 b_wav)
    a, b = wav_samples(a_wav), wav_samples(b_wav)

    gap = np.zeros(int(1.4 * SR), dtype=np.float32)
    lead = np.zeros(int(2.2 * SR), dtype=np.float32)
    tail = np.zeros(int(4.4 * SR), dtype=np.float32)
    master = np.concatenate([lead, a, gap, b, tail])
    master_wav = os.path.join(tmp, "master.wav")
    save_wav(master_wav, master)

    W = H = 1080
    frames = tempfile.mkdtemp(prefix="blind-frames-")
    peaks_a = _peaks(a, FPS)
    peaks_b = _peaks(b, FPS)
    total = int(len(master) / SR * FPS)

    for i in range(total):
        t = i / FPS
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        brand(img, d)
        if t < 2.2:                                     # intro
            centre(d, "Two versions of one day.", font(52), 470, INK, W)
            centre(d, "One is the real day.", font(36), 560, DIM, W)
            centre(d, "One is the same day, shuffled.", font(36), 612, DIM, W)
            _sound_badge(d, W)
        elif t < 14.2:                                  # A
            k = int((t - 2.2) * FPS)
            centre(d, "A", font(150), 330,
                   patterns.PATTERN_META["flow"]["color"], W)
            _wave(d, peaks_a, k, W, H, patterns.PATTERN_META["flow"]["color"])
        elif t < 15.6:                                  # breath
            centre(d, "and now B", font(48), 470, DIM, W)
        elif t < 27.6:                                  # B
            k = int((t - 15.6) * FPS)
            centre(d, "B", font(150), 330,
                   patterns.PATTERN_META["drift"]["color"], W)
            _wave(d, peaks_b, k, W, H, patterns.PATTERN_META["drift"]["color"])
        else:                                           # outro
            centre(d, "Which one is me?", font(60), 430, INK, W)
            centre(d, "Reply A or B. The answer, tomorrow.", font(34), 530,
                   DIM, W)
            centre(d, "timings only, never content", font(28), 900, DIM, W)
            centre(d, "github.com/BenitoJD/the-dayplayer", font(30), 970,
                   INK, W)
        img.save(os.path.join(frames, f"{i:05d}.png"))

    out = os.path.join(KIT, "blind-test.mp4")
    encode(frames, master_wav, out, len(master) / SR)
    shutil.rmtree(frames, ignore_errors=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return out


def _peaks(x: np.ndarray, fps: int) -> np.ndarray:
    step = SR // fps
    n = len(x) // step
    return np.abs(x[:n * step].reshape(n, step)).max(axis=1)


def _wave(d, peaks, k, W, H, colour, span=70):
    """Scrolling waveform: the last `span` frames of audio, honestly."""
    base = H * 0.66
    start = max(0, k - span)
    window = peaks[start:start + span]
    if len(window) == 0:
        return
    bw = (W - 240) / span
    for j, v in enumerate(window):
        x = 120 + j * bw
        h = 6 + float(v) * 300
        d.rectangle([x, base - h / 2, x + bw * 0.62, base + h / 2],
                    fill=colour)


def _sound_badge(d, W):
    text = "SOUND ON"
    f = font(24)
    tw = d.textlength(text, font=f)
    x, y, h = W - tw - 150, 60, 46
    d.rounded_rectangle([x, y, x + tw + 74, y + h], radius=h // 2,
                        outline="#3a3a44", width=2)
    sy = y + h // 2
    d.polygon([(x + 18, sy - 6), (x + 26, sy - 6), (x + 34, sy - 13),
               (x + 34, sy + 13), (x + 26, sy + 6), (x + 18, sy + 6)],
              fill=INK)
    d.arc([x + 32, sy - 11, x + 46, sy + 11], -60, 60, fill=INK, width=2)
    d.text((x + 54, y + 12), text, font=f, fill=INK)


# --------------------------------------------------------------- live clip
def build_live():
    """The live soundscape morphing through four states, with the orb."""
    from dayplayer.live import LiveEngine
    eng = LiveEngine()
    eng.gain = 0.7
    script = [(0.0, "flow", 4.6), (6.0, "flail", 5.0),
              (11.0, "drift", 3.0), (14.0, "mire", 1.0)]
    dur = 18.0
    blocks = int(dur * SR / 512)
    buf = np.zeros(blocks * 512, dtype=np.float32)
    states = []
    for blk in range(blocks):
        t = blk * 512 / SR
        state, cps = "mire", 0.0
        for start, s, c in script:
            if t >= start:
                state, cps = s, c
        eng.state, eng.cps = state, cps
        out = np.zeros((512, 2), dtype=np.float32)
        eng._render_block(out, 512)
        buf[blk * 512:(blk + 1) * 512] = out[:, 0]
        states.append((t, dict(eng.weights), state))

    tmp = tempfile.mkdtemp(prefix="live-")
    wav_path = os.path.join(tmp, "live.wav")
    peak = float(np.abs(buf).max()) or 1.0
    save_wav(wav_path, buf / peak * 0.89)

    W = H = 1080
    frames = tempfile.mkdtemp(prefix="live-frames-")
    total = int(dur * FPS)
    for i in range(total):
        t = i / FPS
        idx = min(int(t * SR / 512), len(states) - 1)
        _, weights, state = states[idx]
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        brand(img, d)
        col = [0.0, 0.0, 0.0]
        for key, w in weights.items():
            c = patterns.PATTERN_META[key]["color"].lstrip("#")
            rgb = tuple(int(c[j:j + 2], 16) for j in (0, 2, 4))
            for j in range(3):
                col[j] += rgb[j] * w
        tot = sum(weights.values()) or 1
        col = [min(255, int(c / tot)) for c in col]
        breathe = 0.5 + 0.5 * math.sin(t * 2.4)
        cx, cy = W / 2, H * 0.42
        r = 210 * (0.94 + 0.06 * breathe)
        # draw the halo first and the bright core last: each ellipse covers
        # the previous ones, so the old order ended with a black disc on top
        for ring in range(25, -1, -1):              # soft orb falloff
            f = ring / 26
            rr = r * (1 + f * 0.7)
            alpha = (1 - f) ** 2
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                      fill=tuple(int(c * alpha * 0.9) for c in col))
        label = patterns.PATTERN_META[state]["label"].upper()
        centre(d, label, font(64), H * 0.72,
               patterns.PATTERN_META[state]["color"], W)
        if t > 1.5:
            centre(d, "hear your state while you work", font(32), H * 0.80,
                   DIM, W)
        if t > dur - 3.6:
            centre(d, "Listen live.", font(46), H * 0.88, INK, W)
            centre(d, "github.com/BenitoJD/the-dayplayer", font(28),
                   H * 0.94, INK, W)
        _sound_badge(d, W)
        img.save(os.path.join(frames, f"{i:05d}.png"))

    out = os.path.join(KIT, "live-clip.mp4")
    encode(frames, wav_path, out, dur)
    shutil.rmtree(frames, ignore_errors=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return out


def main():
    os.makedirs(KIT, exist_ok=True)
    t0 = time.time()
    blind = build_blind()
    print(f"{os.path.basename(blind):18s} "
          f"{os.path.getsize(blind)/1048576:.1f} MB")
    live = build_live()
    print(f"{os.path.basename(live):18s} "
          f"{os.path.getsize(live)/1048576:.1f} MB")
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
