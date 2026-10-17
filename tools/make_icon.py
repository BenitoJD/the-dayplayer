"""Generate The Dayplayer app icon (procedural, no external assets).

Design: dark squircle (macOS style), a circular waveform ring whose
bars pulse at different heights — a day's rhythm seen from above,
amber (morning energy) flowing into cyan (evening calm) — with a play
glyph at the heart.

Outputs:
  assets/icon.png        1024px master
  assets/icon.ico        Windows multi-size
  assets/icon.icns       macOS (via iconutil on macOS)
"""
from __future__ import annotations

import math
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")

# theme (same as dashboard.py)
BG_TOP = (19, 26, 46)        # #131a2e
BG_BOT = (7, 10, 18)         # #070a12
AMBER = (240, 180, 41)       # #f0b429
CYAN = (79, 216, 235)        # #4fd8eb
PLAY = (226, 250, 255)       # near-white cyan tint

SS = 4                        # supersampling factor
OUT = 1024
CANVAS = OUT * SS             # 4096


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def make_master() -> Image.Image:
    img = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))

    # ---- squircle background with vertical gradient
    grad = Image.new("RGBA", (CANVAS, CANVAS))
    gd = ImageDraw.Draw(grad)
    for y in range(CANVAS):
        t = y / CANVAS
        gd.line([(0, y), (CANVAS, y)],
                fill=lerp(BG_TOP, BG_BOT, t) + (255,))
    mask = Image.new("L", (CANVAS, CANVAS), 0)
    md = ImageDraw.Draw(mask)
    R = int(CANVAS * 0.225)                       # squircle radius
    md.rounded_rectangle([8, 8, CANVAS - 8, CANVAS - 8], R, fill=255)
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    # subtle inner border glow
    d.rounded_rectangle([16, 16, CANVAS - 16, CANVAS - 16], R - 8,
                        outline=(79, 216, 235, 40), width=6)

    cx = cy = CANVAS / 2

    # ---- ring bars (glow layer first, then crisp)
    N = 56
    r0 = int(CANVAS * 0.295)
    w = int(CANVAS * 0.0165)
    bars = []                                      # (p0, p1, color)
    for i in range(N):
        theta = -math.pi / 2 + i * 2 * math.pi / N   # start at 12 o'clock
        # organic rhythm: layered sines + occasional burst accents
        h = (0.42 + 0.30 * math.sin(7 * theta + 1.1)
             + 0.18 * math.sin(3 * theta - 0.4)
             + 0.10 * math.sin(11 * theta + 2.0))
        if i % 9 == 4:                              # burst accent
            h = 1.05
        h = max(0.16, h) * CANVAS * 0.145
        r1 = r0 + h
        p0 = (cx + r0 * math.cos(theta), cy + r0 * math.sin(theta))
        p1 = (cx + r1 * math.cos(theta), cy + r1 * math.sin(theta))
        t = (math.sin(theta) + 1) / 2               # amber -> cyan around
        bars.append((p0, p1, lerp(AMBER, CYAN, t)))

    glow = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    gd2 = ImageDraw.Draw(glow)
    for p0, p1, c in bars:
        gd2.line([p0, p1], fill=c + (160,), width=int(w * 1.9),
                 joint="curve")
    glow = glow.filter(ImageFilter.GaussianBlur(CANVAS * 0.012))
    img.alpha_composite(glow)

    for p0, p1, c in bars:
        d.line([p0, p1], fill=c + (255,), width=w, joint="curve")

    # ---- play glyph at the heart
    s = CANVAS * 0.085                              # half-height
    ox = CANVAS * 0.012                             # optical centering
    tri = [(cx - s * 0.72 + ox, cy - s), (cx - s * 0.72 + ox, cy + s),
           (cx + s * 0.95 + ox, cy)]
    tglow = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    td = ImageDraw.Draw(tglow)
    td.polygon(tri, fill=CYAN + (150,))
    tglow = tglow.filter(ImageFilter.GaussianBlur(CANVAS * 0.010))
    img.alpha_composite(tglow)
    d.polygon(tri, fill=PLAY + (255,))

    return img.resize((OUT, OUT), Image.LANCZOS)


def main():
    os.makedirs(ASSETS, exist_ok=True)
    master = make_master()
    master.save(os.path.join(ASSETS, "icon.png"))
    master.save(os.path.join(ASSETS, "icon.ico"),
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                       (128, 128), (256, 256), (512, 512)])
    print("wrote icon.png + icon.ico")

    if sys.platform == "darwin":
        iconset = os.path.join(ASSETS, "icon.iconset")
        os.makedirs(iconset, exist_ok=True)
        sizes = [16, 32, 128, 256, 512]
        for s in sizes:
            master.resize((s, s), Image.LANCZOS).save(
                os.path.join(iconset, f"icon_{s}x{s}.png"))
            master.resize((s * 2, s * 2), Image.LANCZOS).save(
                os.path.join(iconset, f"icon_{s}x{s}@2x.png"))
        subprocess.run(["iconutil", "-c", "icns",
                        os.path.join(ASSETS, "icon.iconset"),
                        "-o", os.path.join(ASSETS, "icon.icns")],
                       check=True)
        print("wrote icon.icns")


if __name__ == "__main__":
    main()
