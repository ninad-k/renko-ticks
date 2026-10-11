"""Covers (1200x628) and icons (60x60) for the four parts of the series.

Run:  python make_covers.py
Writes figures/covers/cover_ep0N.png and icon_ep0N.png, N = 1..4.
Bricks on the covers are produced by python/renko_engine.py from a seeded random walk.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import to_rgba  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
from renko_engine import RenkoEngine  # noqa: E402

OUT = HERE / "covers"
OUT.mkdir(exist_ok=True)

SLATE = "#1E2A38"
UP, UP_E = "#1F8A5B", "#14684A"
DN, DN_E = "#C8423B", "#9E2F2A"
FORM = "#9AA3AE"
HILITE = "#D98E04"

TITLES = {
    1: "A Brick Engine That Cannot Repaint",
    2: "What a Renko Backtest Hides",
    3: "Do Renko Bricks Have Memory? A Random-Walk Test",
    4: "Making a Renko EA Pass Automatic Validation",
}
SERIES = "Tick-Driven Renko in MQL5"
BREAKS = {
    1: ["A Brick Engine That", "Cannot Repaint"],
    2: ["What a Renko", "Backtest Hides"],
    3: ["Do Renko Bricks Have Memory?", "A Random-Walk Test"],
    4: ["Making a Renko EA Pass", "Automatic Validation"],
}
for _n, _t in TITLES.items():
    assert " ".join(BREAKS[_n]) == _t

plt.rcParams["font.family"] = "DejaVu Sans"

CW, CH = 1200, 628
GAP, BH = 6, 30                 # horizontal gap, brick height (px)
N_BRICKS = 26
MARGIN = 72
BW = ((CW - 2 * MARGIN) + GAP) / N_BRICKS - GAP   # brick width so the row spans the margins
BASE_Y = 52                     # y (px from bottom) of the lowest brick row


def make_bricks(seed, burst_at=None, burst_n=5, max_span=5.01):
    """Return list of (open_level, close_level, dir, burst_index) from the engine."""
    rng = np.random.default_rng(seed)
    burst_at0 = burst_at
    for attempt in range(5000):
        burst_at = burst_at0
        rk = RenkoEngine()
        rk.init(1.0, 4096)
        price = 100.3
        rk.on_tick(0, price, price)
        t = 0
        out = []
        while len(out) < N_BRICKS + 40:
            t += 1
            price += rng.normal(0, 0.45)
            n = rk.on_tick(t, price, price)
            for s in range(n - 1, -1, -1):
                b = rk.get_brick(s)
                out.append((b.open, b.close, b.dir, b.burst_index))
            if burst_at is not None and len(out) >= burst_at:
                price += (burst_n + 0.3) * (1 if out[-1][2] > 0 else -1)
                t += 1
                n = rk.on_tick(t, price, price)
                for s in range(n - 1, -1, -1):
                    b = rk.get_brick(s)
                    out.append((b.open, b.close, b.dir, b.burst_index))
                burst_at = None
        window = out[:N_BRICKS] if burst_at is None and attempt >= 0 else out[:N_BRICKS]
        lv = [x for b in window for x in (b[0], b[1])]
        if max(lv) - min(lv) <= max_span:
            return window
    raise RuntimeError("no fitting brick path")


def longest_run(bricks):
    best = (0, 0, 0)
    start = 0
    for i in range(1, len(bricks) + 1):
        if i == len(bricks) or bricks[i][2] != bricks[start][2]:
            if i - start > best[0]:
                best = (i - start, start, i - 1)
            start = i
    return best


def draw_cover(n):
    fig = plt.figure(figsize=(CW / 100, CH / 100), dpi=100, facecolor=SLATE)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, CW)
    ax.set_ylim(0, CH)
    ax.axis("off")
    fig.patch.set_facecolor(SLATE)

    seeds = {1: 11, 2: 23, 3: 5, 4: 41}
    if n == 2:
        bricks = make_bricks(seeds[n], burst_at=14, burst_n=5, max_span=7.01)
    else:
        bricks = make_bricks(seeds[n])
    lv = [x for b in bricks for x in (b[0], b[1])]
    lo = min(lv)
    row_w = N_BRICKS * (BW + GAP) - GAP
    x0 = MARGIN
    for i, (o, c, d, bi) in enumerate(bricks):
        x = x0 + i * (BW + GAP)
        y = BASE_Y + (min(o, c) - lo) * BH
        up = d > 0
        fc, ec = (UP, UP_E) if up else (DN, DN_E)
        ls = "-"
        bi = bi if n == 2 else 0      # phantom styling only on part 2
        if bi > 0:
            fc, ls = to_rgba(fc, 0.35), (0, (3, 2))
        ax.add_patch(Rectangle((x, y), BW, BH * abs(c - o), facecolor=fc, edgecolor=ec if bi == 0 else UP if up else DN,
                               linewidth=1.6, linestyle=ls))
    if n == 3:
        ln, a, b = longest_run(bricks)
        xa = x0 + a * (BW + GAP)
        xb = x0 + b * (BW + GAP) + BW
        y = BASE_Y - 20
        ax.plot([xa, xb], [y, y], color=HILITE, lw=3, solid_capstyle="butt")
        ax.plot([xa, xa], [y - 7, y + 7], color=HILITE, lw=3, solid_capstyle="butt")
        ax.plot([xb, xb], [y - 7, y + 7], color=HILITE, lw=3, solid_capstyle="butt")
    if n == 4:
        ymid = BASE_Y + 2.5 * BH
        ax.plot([x0, x0 + row_w], [BASE_Y + 5.4 * BH] * 2, color=HILITE, lw=1.6,
                ls=(0, (6, 4)))

    # text
    ax.text(72, 560, f"{SERIES} · Part {n}", color=FORM, fontsize=15.5, ha="left", va="center")
    ax.add_patch(Rectangle((72, 516), 56, 4, facecolor=HILITE, edgecolor="none"))
    lines = BREAKS[n]
    fs = 50 if max(len(s) for s in lines) <= 26 else 44
    y = 478
    for ln in lines:
        ax.text(70, y, ln, color="white", fontsize=fs, fontweight="bold", ha="left", va="top")
        y -= 84
    fig.savefig(OUT / f"cover_ep0{n}.png", dpi=100, facecolor=SLATE, bbox_inches=None)
    plt.close(fig)


# ---- icons --------------------------------------------------------------------
S = 8  # supersampling


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def blend(fg, bg, a):
    return tuple(int(round(f * a + b * (1 - a))) for f, b in zip(fg, bg))


def dashed_rect(d, box, color, width, dash=3.0, gap=2.0):
    x0, y0, x1, y1 = box
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    for (ax_, ay), (bx, by) in zip(pts[:-1], pts[1:]):
        L = ((bx - ax_) ** 2 + (by - ay) ** 2) ** 0.5
        ux, uy = (bx - ax_) / L, (by - ay) / L
        pos = 0.0
        while pos < L:
            e = min(pos + dash * S, L)
            d.line([(ax_ + ux * pos, ay + uy * pos), (ax_ + ux * e, ay + uy * e)], fill=color,
                   width=int(width * S))
            pos += (dash + gap) * S


def draw_icon(n):
    bg = hex_rgb(SLATE)
    im = Image.new("RGB", (60 * S, 60 * S), bg)
    d = ImageDraw.Draw(im)
    bw, bh = 14, 14
    xs = [7, 23, 39]
    tops = [33, 19, 5]
    cols = [(UP, UP_E), (UP, UP_E), (DN, DN_E)]
    for i, (x, t, (fc, ec)) in enumerate(zip(xs, tops, cols)):
        box = (x * S, t * S, (x + bw) * S, (t + bh) * S)
        phantom = n == 2 and i == 1
        if phantom:
            d.rectangle(box, fill=blend(hex_rgb(fc), bg, 0.35))
            dashed_rect(d, (box[0] + S * 0.5, box[1] + S * 0.5, box[2] - S * 0.5, box[3] - S * 0.5),
                        hex_rgb(UP), 1.4)
        else:
            d.rectangle(box, fill=hex_rgb(fc), outline=hex_rgb(ec), width=int(1.2 * S))
    if n == 3:
        d.rectangle((7 * S, 51 * S, 53 * S, 53 * S), fill=hex_rgb(HILITE))
        d.rectangle((7 * S, 49 * S, 8.6 * S, 55 * S), fill=hex_rgb(HILITE))
        d.rectangle((51.4 * S, 49 * S, 53 * S, 55 * S), fill=hex_rgb(HILITE))
    if n == 4:
        dashed_rect(d, (3 * S, 3 * S, 57 * S, 57 * S), hex_rgb(HILITE), 1.2, dash=3, gap=2)
    im = im.resize((60, 60), Image.LANCZOS)
    im.save(OUT / f"icon_ep0{n}.png", optimize=True)


if __name__ == "__main__":
    for n in range(1, 5):
        draw_cover(n)
        draw_icon(n)
        print("wrote cover/icon", n)
