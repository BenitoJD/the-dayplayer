"""Generate the X marketing stills into marketing/kit/.

  python3 marketing/make_images.py

Produces, all sized for the timeline:
  trust-card.png       what it records vs what it never records
  patterns-card.png    Flow / Flail / Drift / Mire, the shared vocabulary
  day-shapes.png       four workdays, four rings
  blind-card.png       the A/B blind test invitation
  hero-card.png        the tagline over a painted ring
"""
from __future__ import annotations

import json
import math
import os
import random
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont  # noqa: E402

from dayplayer import patterns                                    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT = os.path.join(ROOT, "marketing", "kit")
BG_TOP, BG_BOT = (13, 13, 18), (5, 5, 9)
PANEL = (18, 18, 25)
INK, DIM = "#f5f5f7", "#8b93a7"
AMBER, GREEN = "#f0b429", "#30d158"
BRAND = "#4fd8eb"

FONTS = [
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/SFNSDisplay.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def font(size: int):
    for path in FONTS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def canvas(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)],
               fill=tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t)
                          for i in range(3)))
    return img


def brand_mark(img: Image.Image, x=64, y=56):
    d = ImageDraw.Draw(img)
    icon = os.path.join(ROOT, "assets", "icon.png")
    if os.path.exists(icon):
        ic = Image.open(icon).convert("RGBA").resize((56, 56), Image.LANCZOS)
        img.paste(ic, (x, y), ic)
    d.text((x + 74, y + 12), "CIRCADIA", font=font(30), fill=INK)


def centre(d, text, f, y, colour, w):
    tw = d.textlength(text, font=f)
    d.text((w / 2 - tw / 2, y), text, font=f, fill=colour)


# ------------------------------------------------------------ day shapes
def day_events(kind: str) -> list[dict]:
    """Four recognisable workdays."""
    rng = random.Random(hash(kind) % 9999)
    ev: list[dict] = []
    t = time.time() - 8 * 3600

    def add(**kw):
        nonlocal t
        kw["t"] = round(t, 3)
        ev.append(kw)

    def type_for(mins, cps):
        nonlocal t
        end = t + mins * 60
        while t < end:
            t += max(0.05, (1 / cps) * (1 + rng.uniform(-0.3, 0.3)))
            c = "space" if rng.random() < 0.15 else "key"
            add(type="kd", c=c)
            add(type="ku", c=c)

    def flail_for(mins):
        nonlocal t
        end = t + mins * 60
        while t < end:
            t += rng.uniform(0.3, 1.5)
            add(type="kd", c=rng.choice(["mod", "tab", "esc"]))
            add(type="ku", c="mod")
            if rng.random() < 0.5:
                add(type="win", app=rng.choice(["Safari", "Slack", "Mail"]))

    def drift_for(mins):
        nonlocal t
        end = t + mins * 60
        while t < end:
            t += rng.uniform(0.4, 1.3)
            add(type="mm", d=round(rng.uniform(20, 240), 1))
            if rng.random() < 0.2:
                add(type="ms", dy=1, n=2)

    def quiet_for(mins):
        nonlocal t
        t += mins * 60

    if kind == "deep":
        quiet_for(20)
        type_for(150, 4.5)
        drift_for(18)
        type_for(140, 4.2)
        quiet_for(60)
    elif kind == "meetings":
        for _ in range(5):
            type_for(14, 3.2)
            quiet_for(52)
        drift_for(20)
    elif kind == "firefighting":
        for _ in range(9):
            flail_for(13)
            type_for(11, 3.0)
            quiet_for(8)
    else:                                      # scattered
        for _ in range(14):
            type_for(9, 3.6)
            drift_for(11)
            quiet_for(6)
            flail_for(6)
    return ev


def ring_tile(kind: str, label: str, size=520) -> Image.Image:
    """One day drawn as a ring."""
    from dayplayer import features
    ev = day_events(kind)
    feats = features.features_from_events(ev, kind)
    minutes = feats["minutes"]
    active = [m for m in minutes if not m["idle"]]
    keys = sorted(m["key_rate"] for m in active) or [0]
    med = keys[len(keys) // 2]
    strip = [patterns.classify_minute(m, med) for m in minutes]
    n = max(len(strip), 1)

    square = Image.new("RGB", (size, size), (10, 10, 14))
    d = ImageDraw.Draw(square)
    pad = 34
    r = (size - 2 * pad) / 2
    cx = cy = size / 2
    ring_w = 22
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline="#191921",
              width=ring_w)
    glow = Image.new("RGBA", (size // 3, size // 3), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    i = 0
    while i < n:
        pat = strip[i]
        j = i
        while j < n and strip[j] == pat:
            j += 1
        a0, a1 = -90 + (i / n) * 360, -90 + (j / n) * 360
        if pat != patterns.MIRE:
            col = patterns.PATTERN_META[pat]["color"]
            d.arc([cx - r, cy - r, cx + r, cy + r], a0, a1, fill=col,
                  width=ring_w)
            gd.arc([cx / 3 - r / 3, cy / 3 - r / 3,
                    cx / 3 + r / 3, cy / 3 + r / 3], a0, a1, fill=col,
                   width=max(2, ring_w // 3))
        else:
            d.arc([cx - r, cy - r, cx + r, cy + r], a0, a1, fill="#23232c",
                  width=ring_w)
        i = j
    glow = glow.filter(ImageFilter.GaussianBlur(4))
    square = ImageChops.screen(
        square,
        glow.resize((size, size), Image.BILINEAR).convert("RGB"))
    tile = Image.new("RGB", (size, size + 74), (10, 10, 14))
    tile.paste(square, (0, 0))
    d = ImageDraw.Draw(tile)
    d.text((pad, size + 18), label, font=font(30), fill=DIM)
    counts = {p: strip.count(p) for p in patterns.PATTERN_META}
    dom = max(counts, key=counts.get)
    dot = patterns.PATTERN_META[dom]["color"]
    d.ellipse([size - pad - 22, size + 26, size - pad, size + 48], fill=dot)
    return tile


# ----------------------------------------------------------------- cards
def trust_card(path):
    W, H = 1080, 1350
    img = canvas(W, H)
    brand_mark(img)
    d = ImageDraw.Draw(img)
    centre(d, "What Circadia records", font(52), 190, INK, W)
    centre(d, "and what it never touches", font(34), 258, DIM, W)

    def block(y, title, colour, lines):
        box = Image.new("RGB", (W - 128, 40 + 46 * len(lines)), PANEL)
        img.paste(box, (64, y))
        dd = ImageDraw.Draw(img)
        dd.rectangle([64, y, 70, y + box.height], fill=colour)
        dd.text((100, y + 22), title, font=font(30), fill=colour)
        for k, line in enumerate(lines):
            dd.text((100, y + 76 + k * 46), line, font=font(28), fill=INK)

    block(330, "RECORDS", AMBER, [
        "how long you pause between keys",
        "how fast you type, in bursts",
        "mouse distance, clicks, scrolling",
        "which app is in front, by name",
    ])
    block(620, "NEVER RECORDS", GREEN, [
        "which keys you press (all the same token)",
        "words, passwords, window titles, URLs",
        "screen contents, clipboard, camera, mic",
        "nothing is uploaded, ever",
    ])
    centre(d, "every file stays in ~/.dayplayer on your own computer",
           font(26), 1030, DIM, W)
    centre(d, "no server  ·  no account  ·  open source", font(30), 1090,
           BRAND, W)
    centre(d, "github.com/BenitoJD/the-dayplayer", font(30), 1215, INK, W)
    img.save(path)
    return path


def patterns_card(path):
    W, H = 1080, 1350
    img = canvas(W, H)
    brand_mark(img)
    d = ImageDraw.Draw(img)
    centre(d, "Four things a workday does", font(52), 190, INK, W)
    centre(d, "once you can hear them, you notice them", font(32), 258, DIM, W)
    y = 350
    for key, meta in patterns.PATTERN_META.items():
        img.paste(Image.new("RGB", (W - 128, 190), PANEL), (64, y))
        d = ImageDraw.Draw(img)
        d.rectangle([64, y, 70, y + 190], fill=meta["color"])
        d.text((104, y + 28), meta["label"].upper(), font=font(44),
               fill=meta["color"])
        d.text((104, y + 96), meta["desc"], font=font(30), fill=INK)
        y += 214
    centre(d, "github.com/BenitoJD/the-dayplayer", font(30), 1250, INK, W)
    img.save(path)
    return path


def day_shapes(path):
    W, H = 1240, 1340
    img = canvas(W, H)
    brand_mark(img)
    d = ImageDraw.Draw(img)
    centre(d, "Four workdays", font(56), 170, INK, W)
    centre(d, "same person, same week, four different shapes",
           font(32), 244, DIM, W)
    tiles = [("deep", "deep work"), ("meetings", "meeting day"),
             ("firefighting", "firefighting"), ("scattered", "scattered")]
    for k, (kind, label) in enumerate(tiles):
        tile = ring_tile(kind, label, size=520)
        x = 60 + (k % 2) * 570
        y = 320 + (k // 2) * 470
        img.paste(tile, (x, y))
    d = ImageDraw.Draw(img)
    centre(d, "the dark stretches are the quiet hours", font(28), 1245, DIM, W)
    centre(d, "github.com/BenitoJD/the-dayplayer", font(30), 1295, INK, W)
    img.save(path)
    return path


def blind_card(path):
    W, H = 1080, 1350
    img = canvas(W, H)
    brand_mark(img)
    d = ImageDraw.Draw(img)
    centre(d, "Two versions of one day", font(54), 210, INK, W)
    centre(d, "one is the real day. one is the same day, shuffled.",
           font(32), 288, DIM, W)

    def wave(y, label, colour, seed):
        rng = random.Random(seed)
        box = Image.new("RGB", (W - 128, 260), PANEL)
        img.paste(box, (64, y))
        dd = ImageDraw.Draw(img)
        dd.text((104, y + 26), label, font=font(60), fill=colour)
        peaks = [abs(math.sin(i * 0.21 + rng.random())) ** 1.6
                 for i in range(150)]
        for i, v in enumerate(peaks):
            x = 220 + i * 5
            h = 12 + v * 170
            dd.line([(x, y + 130 - h / 2), (x, y + 130 + h / 2)],
                    fill=colour, width=3)

    wave(380, "A", patterns.PATTERN_META["flow"]["color"], 3)
    wave(690, "B", patterns.PATTERN_META["drift"]["color"], 11)
    centre(d, "which one is me?", font(52), 1030, INK, W)
    centre(d, "reply A or B. answer tomorrow.", font(30), 1105, DIM, W)
    centre(d, "github.com/BenitoJD/the-dayplayer", font(30), 1245, INK, W)
    img.save(path)
    return path


def hero_card(path):
    W, H = 1080, 1350
    img = canvas(W, H)
    tile = ring_tile("scattered", "", size=760)
    img.paste(tile, ((W - 760) // 2, 210))
    d = ImageDraw.Draw(img)
    centre(d, "Your workday is already", font(46), 1010, INK, W)
    centre(d, "a performance.", font(46), 1066, INK, W)
    centre(d, "This plays it back.", font(46), 1122, AMBER, W)
    centre(d, "timings only, never content", font(30), 1210, DIM, W)
    centre(d, "github.com/BenitoJD/the-dayplayer", font(30), 1265, INK, W)
    img.save(path)
    return path


def main():
    os.makedirs(KIT, exist_ok=True)
    made = [
        trust_card(os.path.join(KIT, "trust-card.png")),
        patterns_card(os.path.join(KIT, "patterns-card.png")),
        day_shapes(os.path.join(KIT, "day-shapes.png")),
        blind_card(os.path.join(KIT, "blind-card.png")),
        hero_card(os.path.join(KIT, "hero-card.png")),
    ]
    for p in made:
        with Image.open(p) as im:
            print(f"{os.path.basename(p):22s} {im.size[0]}x{im.size[1]}  "
                  f"{os.path.getsize(p)/1024:.0f} KB")


if __name__ == "__main__":
    main()
