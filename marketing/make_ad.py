"""Build the Circadia ad video: ring painting + real synth audio.

  python3 marketing/make_ad.py                    # designed demo workday
  python3 marketing/make_ad.py --date 2026-10-17  # your own real day
  python3 marketing/make_ad.py --size 1920x1080   # wide cut

Output: marketing/circadia-ad.mp4 (1080x1080, 30fps, sound on)

The ring and the soundtrack come from the SAME data, so what you see
painting is exactly what you hear.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont  # noqa: E402

from dayplayer import composer, config, features, patterns, synth  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "marketing")
FG = "#f5f5f7"
DIM = "#8b93a7"
TRACK = "#191921"
BG_TOP = (13, 13, 18)
BG_BOT = (5, 5, 9)

FONT_CANDIDATES = [
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/SFNSDisplay.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
]


def load_font(size: int):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ------------------------------------------------------------- demo day
def demo_workday_events() -> list[dict]:
    """A designed 9:00 to 17:00 day with a clear arc:
    deep flow, a flail burst, drifting, a long lunch hole, flow again,
    a deadline flail, then a taper. Gives the ring a real workday shape.
    """
    rng = random.Random(7)
    events: list[dict] = []
    t = time.time() - 8 * 3600                      # 8 hours ago = 9:00

    def add(**kw):
        nonlocal t
        kw["t"] = round(t, 3)
        events.append(kw)

    def type_for(minutes: float, cps: float, jitter: float = 0.35,
                 app: str = "VS Code"):
        nonlocal t
        end = t + minutes * 60
        app_seen = None
        while t < end:
            gap = max(0.04, (1.0 / cps) * (1 + rng.uniform(-jitter, jitter)))
            t += gap
            c = "space" if rng.random() < 0.16 else (
                "backspace" if rng.random() < 0.06 else "key")
            add(type="kd", c=c)
            add(type="ku", c=c)
            if app_seen != app:
                add(type="win", app=app)
                app_seen = app

    def flail_for(minutes: float):
        nonlocal t
        end = t + minutes * 60
        while t < end:
            t += rng.uniform(0.25, 1.6)
            add(type="kd", c=rng.choice(["mod", "mod", "tab", "tab", "esc"]))
            add(type="ku", c="mod")
            if rng.random() < 0.45:
                add(type="win", app=rng.choice(
                    ["Safari", "Slack", "Mail", "VS Code"]))

    def drift_for(minutes: float):
        nonlocal t
        end = t + minutes * 60
        while t < end:
            t += rng.uniform(0.4, 1.4)
            if rng.random() < 0.7:
                add(type="mm", d=round(rng.uniform(25, 260), 1))
            else:
                add(type="ms", dy=1, n=rng.randint(1, 6))
            if rng.random() < 0.15:
                add(type="mc", b="left", down=True)

    def quiet_for(minutes: float):
        nonlocal t
        t += minutes * 60

    type_for(78, cps=4.6)          # morning deep work
    flail_for(14)                  # inbox panic
    drift_for(26)                  # wandering
    quiet_for(62)                  # lunch and meetings, the hole in the ring
    type_for(62, cps=3.8, app="Slack")   # afternoon work
    flail_for(18)                  # deadline scramble
    drift_for(22)                  # late afternoon wandering
    type_for(30, cps=2.6)          # taper
    quiet_for(18)                  # heading out
    return events


def prepare_day(date: str | None):
    """Returns (features, label). Real date, or the designed demo day."""
    if date:
        feats = features.extract(date)
        return feats, date
    tmp = tempfile.mkdtemp(prefix="circadia-ad-")
    real_log = config.LOG_DIR
    config.LOG_DIR = tmp
    try:
        events = demo_workday_events()
        with open(os.path.join(tmp, "demo.jsonl"), "w") as fh:
            for e in events:
                fh.write(json.dumps(e) + "\n")
        feats = features.features_from_events(events, "demo")
    finally:
        config.LOG_DIR = real_log
    return feats, "one workday"


# ----------------------------------------------------------------- video
class AdBuilder:
    def __init__(self, size: tuple[int, int], duration: float, fps: int,
                 feats: dict, label: str):
        self.W, self.H = size
        self.duration = duration
        self.fps = fps
        self.feats = feats
        self.label = label
        self.summary = None
        self.minutes: list[dict] = []
        self.strip: list[str] = []
        self.n = 1
        self.scale = self.W / 1080.0
        self._prepare_summary()
        self.fonts = {
            "brand": load_font(int(30 * self.scale)),
            "state": load_font(int(58 * self.scale)),
            "caption": load_font(int(46 * self.scale)),
            "sub": load_font(int(30 * self.scale)),
            "end_big": load_font(int(110 * self.scale)),
            "end_mid": load_font(int(40 * self.scale)),
            "end_small": load_font(int(26 * self.scale)),
            "badge": load_font(int(24 * self.scale)),
        }
        self.base = self._make_base()

    def _prepare_summary(self):
        # run day_summary-like classification over the in-memory features
        minutes = self.feats["minutes"]
        active = [m for m in minutes if not m["idle"]]
        keys = sorted(m["key_rate"] for m in active) or [0]
        med = keys[len(keys) // 2]
        for m in minutes:
            m["pattern"] = patterns.classify_minute(m, med)
        self.minutes = minutes
        self.strip = [m["pattern"] for m in minutes]
        self.n = max(len(self.strip), 1)

    def _make_base(self) -> Image.Image:
        """Static elements drawn once: background, track, wordmark."""
        img = Image.new("RGB", (self.W, self.H))
        d = ImageDraw.Draw(img)
        for y in range(self.H):
            t = y / self.H
            d.line([(0, y), (self.W, y)],
                   fill=tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t)
                              for i in range(3)))
        cx, cy, r = self._ring_geo()
        ring_w = int(26 * self.scale)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=TRACK,
                  width=ring_w)
        icon_path = os.path.join(ROOT, "assets", "icon.png")
        if os.path.exists(icon_path):
            icon = Image.open(icon_path).convert("RGBA")
            s = int(52 * self.scale)
            icon = icon.resize((s, s), Image.LANCZOS)
            img.paste(icon, (int(64 * self.scale), int(52 * self.scale)),
                      icon)
        d.text((int(132 * self.scale), int(66 * self.scale)), "CIRCADIA",
               font=self.fonts["brand"], fill=FG)
        return img

    def _runs(self, painted: float):
        """Consecutive same-pattern minute runs, as (pattern, a0, a1)."""
        i_min = 0
        while i_min < self.n and i_min < painted:
            pat = self.strip[i_min]
            j = i_min
            while (j < self.n and self.strip[j] == pat and j < painted):
                j += 1
            yield (pat,
                   -90 + (i_min / self.n) * 360,
                   -90 + (j / self.n) * 360)
            i_min = j

    def _ring_geo(self):
        cx, cy = self.W / 2, self.H * 0.47
        r = min(self.W, self.H) * 0.27
        return cx, cy, r

    # ------------------------------------------------------------ frames
    def frame(self, i: int) -> Image.Image:
        t = i / self.fps
        p = min(1.0, t / self.duration)
        img = self.base.copy()
        cx, cy, r = self._ring_geo()
        ring_w = int(26 * self.scale)
        painted = p * self.n
        QUIET_ARC = "#23232c"          # quiet hours still fill the ring, dimly,
                                       # so progress always reads

        # 1) halo pass: draw the arcs small, blur, upscale, and SCREEN them
        #    onto the frame. Screen only adds light, so the halo can never
        #    muddy the crisp arcs drawn afterwards (compositing a blurred
        #    RGBA layer on top darkened them by up to half).
        glow = Image.new("RGBA", (self.W // 4, self.H // 4), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        for pat, a0, a1 in self._runs(painted):
            if pat == patterns.MIRE:
                continue
            gd.arc([cx / 4 - r / 4, cy / 4 - r / 4,
                    cx / 4 + r / 4, cy / 4 + r / 4], a0, a1,
                   fill=patterns.PATTERN_META[pat]["color"],
                   width=max(2, ring_w // 3))
        glow = glow.filter(ImageFilter.GaussianBlur(4))
        img = ImageChops.screen(
            img, glow.resize((self.W, self.H), Image.BILINEAR).convert("RGB"))

        # 2) crisp pass: the real arcs, at full colour
        d = ImageDraw.Draw(img)
        for pat, a0, a1 in self._runs(painted):
            fill = (QUIET_ARC if pat == patterns.MIRE
                    else patterns.PATTERN_META[pat]["color"])
            d.arc([cx - r, cy - r, cx + r, cy + r], a0, a1, fill=fill,
                  width=ring_w)

        # 3) the now dot
        ang = math.radians(-90 + p * 360)
        nx = cx + r * math.cos(ang)
        ny = cy + r * math.sin(ang)
        dot = int(7 * self.scale)
        d.ellipse([nx - dot * 2, ny - dot * 2, nx + dot * 2, ny + dot * 2],
                  fill="#2a2a33")
        d.ellipse([nx - dot, ny - dot, nx + dot, ny + dot], fill=FG)

        # --- current state word in the middle
        if t > 1.2 and t < self.duration - 7:
            idx = min(int(p * self.n), self.n - 1)
            pat = self.strip[idx]
            meta = patterns.PATTERN_META[pat]
            colour = meta["color"]
            if pat == patterns.MIRE:      # legible, not invisible
                colour = DIM
            f = self.fonts["state"]
            tw = d.textlength(meta["label"].upper(), font=f)
            d.text((self.W / 2 - tw / 2, cy - 34 * self.scale),
                   meta["label"].upper(), font=f, fill=colour)
            sub = f"{self.n} minutes, compressed"
            f2 = self.fonts["sub"]
            sw = d.textlength(sub, font=f2)
            d.text((self.W / 2 - sw / 2, cy + 42 * self.scale), sub,
                   font=f2, fill=DIM)
        return img

    def caption(self, img: Image.Image, main: str, sub: str = "",
                y: float = 0.845):
        d = ImageDraw.Draw(img)
        f = self.fonts["caption"]
        tw = d.textlength(main, font=f)
        d.text((self.W / 2 - tw / 2, self.H * y), main, font=f, fill=FG)
        if sub:
            f2 = self.fonts["sub"]
            sw = d.textlength(sub, font=f2)
            d.text((self.W / 2 - sw / 2, self.H * y + 62 * self.scale),
                   sub, font=f2, fill=DIM)

    def sound_badge(self, img: Image.Image):
        d = ImageDraw.Draw(img)
        pad = int(18 * self.scale)
        f = self.fonts["badge"]
        text = "SOUND ON"
        tw = d.textlength(text, font=f)
        w = tw + pad * 2 + int(34 * self.scale)
        h = int(46 * self.scale)
        x = self.W - w - int(64 * self.scale)
        y = int(56 * self.scale)
        d.rounded_rectangle([x, y, x + w, y + h], radius=h // 2,
                            outline="#3a3a44", width=2)
        # little speaker glyph
        sx = x + pad
        sy = y + h // 2
        u = self.scale
        d.polygon([(sx, sy - 6 * u), (sx + 7 * u, sy - 6 * u),
                   (sx + 15 * u, sy - 13 * u), (sx + 15 * u, sy + 13 * u),
                   (sx + 7 * u, sy + 6 * u), (sx, sy + 6 * u)], fill=FG)
        d.arc([sx + 12 * u, sy - 11 * u, sx + 26 * u, sy + 11 * u],
              -60, 60, fill=FG, width=max(2, int(2 * u)))
        d.text((sx + 30 * u, y + h / 2 - 9 * self.scale), text, font=f,
               fill=FG)

    def end_card(self, img: Image.Image, alpha: float):
        """Fade to the closing card."""
        overlay = Image.new("RGB", (self.W, self.H), (5, 5, 9))
        img = Image.blend(img, overlay, alpha)
        d = ImageDraw.Draw(img)
        if alpha > 0.55:
            a = (alpha - 0.55) / 0.45
            f = self.fonts["end_big"]
            tw = d.textlength("Circadia", font=f)
            col = tuple(int(5 + (245 - 5) * a) for _ in range(3))
            d.text((self.W / 2 - tw / 2, self.H * 0.33), "Circadia",
                   font=f, fill=col)
            f2 = self.fonts["end_mid"]
            line = "Your day, played back."
            tw2 = d.textlength(line, font=f2)
            d.text((self.W / 2 - tw2 / 2, self.H * 0.47), line, font=f2,
                   fill=tuple(int(c * a) for c in (240, 180, 41)))
            f3 = self.fonts["end_small"]
            for k, line in enumerate([
                    "timings only, never content",
                    "free · macOS + Windows",
                    "github.com/BenitoJD/the-dayplayer"]):
                tw3 = d.textlength(line, font=f3)
                d.text((self.W / 2 - tw3 / 2,
                        self.H * (0.58 + k * 0.055)), line, font=f3,
                       fill=tuple(int(c * a) for c in (139, 147, 167)))
        return img

    def render_all(self, frames_dir: str):
        captions = [
            (0.0, 3.4, "I recorded my workday.", "timing only, never a letter"),
            (3.4, 9.5, "Every keystroke became a drum.", ""),
            (9.5, 15.5, "Alt-tabbing became a stutter.", ""),
            (15.5, 22.5, "The quiet hours became one held chord.", ""),
            (22.5, 29.0, "You can hear a focused morning.", ""),
            (29.0, 35.0, "And a scattered afternoon.", ""),
            (35.0, 39.0, "One workday, played back.", ""),
        ]
        os.makedirs(frames_dir, exist_ok=True)
        total = int(self.duration * self.fps)
        for i in range(total):
            t = i / self.fps
            img = self.frame(i)
            end_start = self.duration - 6.0
            if t < end_start:
                for a, b, main, sub in captions:
                    if a <= t < b:
                        self.caption(img, main, sub)
                        break
                if t < 5.0:
                    self.sound_badge(img)
            else:
                alpha = min(1.0, (t - end_start) / 2.2)
                img = self.end_card(img, alpha)
            img.save(os.path.join(frames_dir, f"{i:05d}.png"))
        return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="use a real recorded day")
    ap.add_argument("--duration", type=float, default=45.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--size", default="1080x1080")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    w, h = (int(x) for x in args.size.lower().split("x"))
    feats, label = prepare_day(args.date)
    if not feats.get("minutes"):
        print("no data for that day")
        return 1

    print(f"day: {label} · {len(feats['minutes'])} minutes "
          f"· {feats['meta'].get('total_key', 0):,} keys")

    score = composer.compose(feats, target_duration=args.duration)
    tr = score["tracks"]
    print(f"score: {len(tr['tick'])} ticks, {len(tr['kick'])} kicks, "
          f"{len(tr['flail'])} flail, {len(tr['drone'])} drones")

    os.makedirs(OUT_DIR, exist_ok=True)
    wav = os.path.join(OUT_DIR, "_ad_audio.wav")
    synth.render(score, wav)

    frames = tempfile.mkdtemp(prefix="circadia-frames-")
    builder = AdBuilder((w, h), args.duration, args.fps, feats, label)
    total = builder.render_all(frames)
    print(f"frames: {total} at {w}x{h}")

    out = args.out or os.path.join(OUT_DIR, "circadia-ad.mp4")
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-framerate", str(args.fps), "-i",
           os.path.join(frames, "%05d.png"),
           "-i", wav,
           "-c:v", "libx264", "-preset", "slow", "-crf", "19",
           "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.2",
           "-c:a", "aac", "-b:a", "192k", "-shortest",
           "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)
    shutil.rmtree(frames, ignore_errors=True)
    os.remove(wav)
    size_mb = os.path.getsize(out) / 1048576
    print(f"✔ {out}  ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
