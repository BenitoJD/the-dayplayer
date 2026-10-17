"""Generate the Circadia app icon (procedural, no external assets).

Design: a *circadian ring* — 24 hours as bars around a circle. Heights
follow the day arc (tall at noon on top, quiet at night at the bottom);
color rides the same arc: warm amber daylight → deep indigo night →
first cyan of dawn. A play glyph sits at the heart; a thin orbital
guide ring and soft glows finish it.

Outputs: assets/icon.png (1024), icon.ico, icon.icns (macOS)
"""
from __future__ import annotations

import math
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageChops

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")

# theme
BG_TOP = (17, 24, 44)        # #111830
BG_BOT = (5, 8, 16)          # #050810
NOON = (255, 197, 66)        # warm amber sun
DUSK = (239, 108, 87)        # red dusk
NIGHT = (52, 72, 141)        # deep indigo
DAWN = (79, 216, 235)        # cyan dawn
PLAY = (232, 250, 255)

SS = 4
OUT = 1024
CANVAS = OUT * SS


def mix(*stops):
    """stops: list of (t, color) -> callable t->color"""
    def f(t):
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t <= t1:
                k = 0 if t1 - t0 == 0 else (t - t0) / (t1 - t0)
                return tuple(int(c0[i] + (c1[i] - c0[i]) * k)
                             for i in range(3))
        return stops[-1][1]
    return f


def make_master() -> Image.Image:
    img = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))

    # ---- squircle + gradient + vignette
    grad = Image.new("RGBA", (CANVAS, CANVAS))
    gd = ImageDraw.Draw(grad)
    for y in range(CANVAS):
        gd.line([(0, y), (CANVAS, y)],
                fill=tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * y / CANVAS)
                           for i in range(3)) + (255,))
    mask = Image.new("L", (CANVAS, CANVAS), 0)
    md = ImageDraw.Draw(mask)
    R = int(CANVAS * 0.225)
    md.rounded_rectangle([8, 8, CANVAS - 8, CANVAS - 8], R, fill=255)
    img.paste(grad, (0, 0), mask)

    # radial vignette (darken edges inside the squircle)
    vig = Image.new("L", (CANVAS, CANVAS), 0)
    vd = ImageDraw.Draw(vig)
    steps = 40
    for i in range(steps):
        t = i / steps
        r = int(CANVAS * (0.86 - 0.30 * t))
        shade = int(70 * (1 - t))
        vd.ellipse([CANVAS//2 - r, CANVAS//2 - r, CANVAS//2 + r,
                    CANVAS//2 + r], outline=shade, width=CANVAS // steps + 2)
    vig = vig.filter(ImageFilter.GaussianBlur(CANVAS * 0.03))
    dark = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 255))
    img = Image.composite(ImageChops.subtract(img, Image.merge(
        "RGBA", [vig, vig, vig, Image.new("L", (CANVAS, CANVAS), 0)])),
        img, Image.new("L", (CANVAS, CANVAS), 0))
    # (vignette via subtract on RGB)
    rgb = img.convert("RGB")
    vig3 = Image.merge("RGB", [vig, vig, vig])
    rgb = ImageChops.subtract(rgb, vig3)
    img = rgb.convert("RGBA")
    img.putalpha(mask)

    d = ImageDraw.Draw(img)
    d.rounded_rectangle([14, 14, CANVAS - 14, CANVAS - 14], R - 6,
                        outline=(79, 216, 235, 34), width=5)

    cx = cy = CANVAS / 2

    # ---- thin orbital guide ring
    rg = int(CANVAS * 0.295)
    d.ellipse([cx - rg, cy - rg, cx + rg, cy + rg],
              outline=(90, 108, 150, 90), width=5)

    # ---- circadian bars: loop position t: 0 = noon (top), 0.5 = midnight (bottom)
    N = 48
    r0 = int(CANVAS * 0.315)
    w = int(CANVAS * 0.019)
    dayness = mix((0.0, NOON), (0.25, DUSK), (0.5, NIGHT),
                  (0.75, NIGHT), (0.93, DAWN), (1.0, NOON))
    bars = []
    for i in range(N):
        t_i = i / N
        theta = -math.pi / 2 + t_i * 2 * math.pi
        elev = math.cos(2 * math.pi * t_i)             # 1 noon, -1 midnight
        base = 0.30 + 0.62 * max(0.0, elev) ** 0.9     # day arc heights
        jitter = 0.10 * math.sin(5 * theta + 1.3) + 0.07 * math.sin(9 * theta)
        h = max(0.10, base + jitter * (0.4 + 0.6 * max(0.0, elev)))
        h *= CANVAS * 0.155
        r1 = r0 + h
        c = dayness(t_i)
        p0 = (cx + r0 * math.cos(theta), cy + r0 * math.sin(theta))
        p1 = (cx + r1 * math.cos(theta), cy + r1 * math.sin(theta))
        bars.append((p0, p1, c))

    glow = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    g2 = ImageDraw.Draw(glow)
    for p0, p1, c in bars:
        g2.line([p0, p1], fill=c + (150,), width=int(w * 2.1), joint="curve")
    glow = glow.filter(ImageFilter.GaussianBlur(CANVAS * 0.013))
    img.alpha_composite(glow)
    d = ImageDraw.Draw(img)
    for p0, p1, c in bars:
        d.line([p0, p1], fill=c + (255,), width=w, joint="curve")

    # ---- noon apex: a small bright sun dot at the top bar
    r = int(CANVAS * 0.016)
    d.ellipse([cx - r, cy - r0 - CANVAS*0.155 - r,
               cx + r, cy - r0 - CANVAS*0.155 + r], fill=NOON + (255,))

    # ---- play glyph
    s = CANVAS * 0.082
    ox = CANVAS * 0.011
    tri = [(cx - s * 0.72 + ox, cy - s), (cx - s * 0.72 + ox, cy + s),
           (cx + s * 0.95 + ox, cy)]
    tglow = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    td = ImageDraw.Draw(tglow)
    td.polygon(tri, fill=DAWN + (140,))
    tglow = tglow.filter(ImageFilter.GaussianBlur(CANVAS * 0.009))
    img.alpha_composite(tglow)
    d = ImageDraw.Draw(img)
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
        for s in (16, 32, 128, 256, 512):
            master.resize((s, s), Image.LANCZOS).save(
                os.path.join(iconset, f"icon_{s}x{s}.png"))
            master.resize((s * 2, s * 2), Image.LANCZOS).save(
                os.path.join(iconset, f"icon_{s}x{s}@2x.png"))
        subprocess.run(["iconutil", "-c", "icns",
                        os.path.join(ASSETS, "icon.iconset"),
                        "-o", os.path.join(ASSETS, "icon.icns")], check=True)
        print("wrote icon.icns")


if __name__ == "__main__":
    main()
