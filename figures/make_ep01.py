"""Figures for part 1: A Brick Engine That Cannot Repaint.

Run:  python make_ep01.py
Writes figures/ep01/f1..f6 (750 px wide PNG). Bricks are always computed with
python/renko_engine.py, never re-implemented here.
"""
from __future__ import annotations

import os
import pickle
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import to_rgba  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
from renko_engine import RenkoEngine  # noqa: E402

OUT = HERE / "ep01"
OUT.mkdir(exist_ok=True)

# working files (tail of the tick CSV, brick cache); override with RENKO_SCRATCH
SCRATCH = Path(os.environ.get("RENKO_SCRATCH", HERE.parent / ".cache"))
SCRATCH.mkdir(parents=True, exist_ok=True)
TAIL_CSV = SCRATCH / "xau_tail.csv"      # `tail -n 40000000` of XAUUSD_ticks.csv
BRICK_CACHE = SCRATCH / "bricks.pkl"

# ---- style (STYLE.md) ------------------------------------------------------
UP, UP_E = "#1F8A5B", "#14684A"
DN, DN_E = "#C8423B", "#9E2F2A"
FORM = "#9AA3AE"
PATH = "#2B4C7E"
REF = "#6B7280"
HILITE = "#D98E04"
NEUTRAL = "#EEF1F4"
GRID = "#E6E8EB"
TEXT = "#1F2933"
DPI = 150
W = 5.0

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "axes.edgecolor": REF,
    "axes.labelcolor": TEXT,
    "text.color": TEXT,
    "xtick.color": TEXT,
    "ytick.color": TEXT,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": DPI,
    "savefig.dpi": DPI,
})


def new_fig(h):
    return plt.figure(figsize=(W, h), facecolor="white")


def put_title(fig, text, h):
    fig.text(0.02, 1 - 0.13 / h, text, ha="left", va="top", fontsize=11,
             fontweight="bold")


def put_source(fig, text, h):
    fig.text(0.02, 0.09 / h, text, ha="left", va="bottom", fontsize=6.5, color=FORM)


def style_axes(ax, ygrid=True):
    ax.set_facecolor("white")
    if ygrid:
        ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(length=3, width=0.6)


def brick(ax, x, o, c, phantom=False, w=0.8, pending=False, z=3, lw=1.0):
    if pending:
        fc, ec, ls = NEUTRAL, FORM, (0, (3, 2))
    else:
        up = c > o
        fc, ec = (UP, UP_E) if up else (DN, DN_E)
        ls = "-"
        if phantom:
            fc, ls = to_rgba(fc, 0.35), (0, (3, 2))
    r = Rectangle((x - w / 2, min(o, c)), w, abs(c - o), facecolor=fc, edgecolor=ec,
                  linestyle=ls, linewidth=lw, zorder=z)
    ax.add_patch(r)
    return r


def save(fig, name):
    p = OUT / name
    fig.savefig(p, dpi=DPI, bbox_inches=None, facecolor="white")
    plt.close(fig)
    print("wrote", p)


def feed_path(rk, ticks, t0=0, spread=0.0, spreads=None):
    """Feed (price) ticks, return list of (tick_price, n_bricks)."""
    res = []
    for i, p in enumerate(ticks):
        sp = spreads[i] if spreads else spread
        n = rk.on_tick(t0 + (i + 1) * 1000, p, p + sp)
        res.append((p, n))
    return res


def new_engine(brick_size=1.0, history=1024):
    rk = RenkoEngine()
    assert rk.init(brick_size, history)
    return rk


def arrow(ax, p0, p1, color=HILITE, style="<->", lw=1.1, **kw):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle=style, color=color, lw=lw,
                                 mutation_scale=7, shrinkA=0, shrinkB=0, zorder=6, **kw))


# ---------------------------------------------------------------------------
# f1 - brick rules
# ---------------------------------------------------------------------------
def fig1():
    h = 3.3
    fig = new_fig(h)
    put_title(fig, "Reversing needs twice the travel of continuing", h)
    ax = fig.add_axes([0.105, 0.05, 0.875, 0.80])
    style_axes(ax)
    ax.set_xlim(-0.7, 10.0)
    ax.set_ylim(99.6, 105.0)
    ax.set_yticks(range(100, 106))
    ax.set_xticks([])
    ax.spines["bottom"].set_visible(False)
    ax.set_ylabel("Price ($)")

    ax.axhspan(101, 104, color=NEUTRAL, zorder=0.5)
    for y in (101, 104):
        ax.axhline(y, color=REF, ls="--", lw=1.0, zorder=2)

    # closed bricks 101->102->103 (up)
    brick(ax, 0.0, 101, 102)
    brick(ax, 1.0, 102, 103)
    ax.text(0.5, 103.2, "last closed\nbricks", ha="center", va="bottom", fontsize=8,
            color=REF, linespacing=1.1)

    # pending bricks: continuation and reversal
    xp = 2.5
    brick(ax, xp, 103, 104, pending=True)
    brick(ax, xp, 102, 101, pending=True)
    ax.text(xp, 104.1, "pending", ha="center", va="bottom", fontsize=8, color=REF)

    # reversal brick opens at the previous brick's open (102)
    ax.plot([1.4, 2.1], [102, 102], color=HILITE, lw=1.4, ls=(0, (1, 1.5)), zorder=5)
    ax.plot([1.75], [102], marker="o", color=HILITE, ms=4, zorder=6)
    ax.annotate("Reversal brick opens at 102, the open\nof the last brick (not at 103)",
                xy=(1.75, 102), xytext=(-0.5, 100.2), ha="left", va="center", fontsize=8,
                color=TEXT,
                arrowprops=dict(arrowstyle="-", color=HILITE, lw=1.0, shrinkA=2, shrinkB=3,
                                connectionstyle="angle,angleA=0,angleB=90,rad=0"), zorder=6)

    # dimension arrows
    x1 = 3.7
    arrow(ax, (x1, 103), (x1, 104))
    ax.text(x1 + 0.2, 103.5, "1 brick to continue", ha="left", va="center", fontsize=8,
            fontweight="bold", color=HILITE)
    x2 = 6.6
    arrow(ax, (x2, 103), (x2, 101))
    ax.text(x2 + 0.2, 102.0, "2 bricks\nto reverse", ha="left", va="center", fontsize=8,
            fontweight="bold", color=HILITE, linespacing=1.15)

    ax.text(3.7, 101.3, "dead zone (101, 104):\nno brick prints", ha="left", va="bottom",
            fontsize=8, color=REF, linespacing=1.15)

    ax.text(9.9, 104.08, "continuation trigger 104", ha="right", va="bottom", fontsize=8,
            color=REF)
    ax.text(9.9, 100.92, "reversal trigger 101", ha="right", va="top", fontsize=8, color=REF)
    save(fig, "f1_brick_rules.png")


# ---------------------------------------------------------------------------
# f2 - grid convergence
# ---------------------------------------------------------------------------
def fig2():
    h = 3.9
    fig = new_fig(h)
    put_title(fig, "Different start prices converge to one brick grid", h)
    shared = [102.0, 103.0, 104.4, 102.0, 101.0, 105.6, 99.2]
    res = {}
    for name, first in (("A", 100.3), ("B", 99.7)):
        rk = new_engine()
        rk.on_tick(500, first, first)
        counts = []
        for i, p in enumerate(shared):
            counts.append(rk.on_tick(1000 + i * 1000, p, p))
        res[name] = (rk, counts)
    bricksA = [res["A"][0].get_brick(s) for s in range(res["A"][0].stored() - 1, -1, -1)]
    bricksB = [res["B"][0].get_brick(s) for s in range(res["B"][0].stored() - 1, -1, -1)]
    nA, nB = len(bricksA), len(bricksB)
    # identical after the first (extra) brick of B
    for a, b in zip(bricksA, bricksB[1:]):
        assert (a.open, a.close) == (b.open, b.close)
    n_end = nB - 1                       # index of the last brick (B starts at 0)
    xA = [n_end - (nA - 1) + i for i in range(nA)]
    xB = list(range(nB))
    x_extra = 0

    top = [0.115, 0.585, 0.865, 0.30]
    bot = [0.115, 0.29, 0.865, 0.27]
    strip = [0.115, 0.12, 0.865, 0.12]
    axA = fig.add_axes(top)
    axB = fig.add_axes(bot, sharex=axA)
    axS = fig.add_axes(strip, sharex=axA)
    for ax in (axA, axB):
        style_axes(ax)
        ax.set_ylim(98.4, 107.0)
        ax.set_yticks(range(99, 106, 2))
        ax.tick_params(labelbottom=False)
        ax.set_ylabel("Price ($)")
        ax.spines["bottom"].set_color(GRID)
    axA.set_xlim(-0.8, nB - 0.2)

    for ax, bricks, xs in ((axA, bricksA, xA), (axB, bricksB, xB)):
        ax.axvspan(0.5, nB - 0.5, color=NEUTRAL, zorder=0.3)
        for x, b in zip(xs, bricks):
            brick(ax, x, b.open, b.close, w=0.78)
    # highlight the extra brick of B
    rb = Rectangle((x_extra - 0.5, 99.9), 1.0, 1.2, fill=False, ec=HILITE, lw=1.3,
                   ls=(0, (3, 2)), zorder=7)
    axB.add_patch(rb)
    axB.text(x_extra + 0.62, 99.25, "B prints 1 extra brick (100→101) on the first shared tick",
             ha="left", va="center", fontsize=8, color=HILITE, fontweight="bold")
    axA.text(0.012, 0.93, "Engine A: first tick 100.3", transform=axA.transAxes, ha="left",
             va="top", fontsize=8.5, fontweight="bold")
    axB.text(0.012, 0.93, "Engine B: first tick 99.7", transform=axB.transAxes, ha="left",
             va="top", fontsize=8.5, fontweight="bold")
    axA.text(0.997, 0.93, "identical from the tick at 102.0 on", transform=axA.transAxes,
             ha="right", va="top", fontsize=8, color=REF)

    # tick strip
    axS.set_ylim(0, 1)
    axS.set_yticks([])
    for sp in ("left",):
        axS.spines[sp].set_visible(False)
    axS.set_xlabel("Brick index (aligned at the last brick)")
    axS.set_xticks(range(0, nB))
    axS.tick_params(labelsize=7.5)
    pos = 0
    # groups for B (it has every brick)
    cB = res["B"][1]
    cA = res["A"][1]
    pos = 0
    for i, p in enumerate(shared):
        nb = cB[i]
        x0, x1 = pos - 0.4, pos + nb - 1 + 0.4
        axS.plot([x0, x1], [0.62, 0.62], color=REF, lw=1.2, solid_capstyle="butt")
        axS.plot([x0, x0], [0.62, 0.78], color=REF, lw=1.2)
        axS.plot([x1, x1], [0.62, 0.78], color=REF, lw=1.2)
        lab = f"{p:.1f}"
        axS.text((x0 + x1) / 2, 0.46, lab, ha="center", va="top", fontsize=7, color=PATH)
        pos += nb
    axS.text(-0.75, 0.9, "tick price that printed the group", ha="left", va="center",
             fontsize=7.5, color=REF)
    axS.set_xlim(-0.8, nB - 0.2)
    save(fig, "f2_grid_convergence.png")
    return nA, nB


# ---------------------------------------------------------------------------
# f3 - gap tick, phantom bricks
# ---------------------------------------------------------------------------
def fig3():
    h = 3.4
    fig = new_fig(h)
    put_title(fig, "One gap tick printed four bricks nobody could trade", h)
    rk = new_engine()
    seq = [100.3, 102.0, 103.0, 101.0]
    feed_path(rk, seq)
    n = rk.on_tick(10_000, 106.2, 106.2 + 0.3)
    assert n == 4
    prev = [rk.get_brick(s) for s in range(rk.stored() - 1, 3, -1)]
    burst = [rk.get_brick(s) for s in range(3, -1, -1)]
    assert [b.burst_index for b in burst] == [0, 1, 2, 3]
    assert [(b.open, b.close) for b in burst] == [(102, 103), (103, 104), (104, 105), (105, 106)]

    ax = fig.add_axes([0.105, 0.05, 0.875, 0.80])
    style_axes(ax)
    ax.set_xlim(0.2, 9.9)
    ax.set_ylim(99.4, 108.0)
    ax.set_yticks(range(100, 108))
    ax.set_ylabel("Price ($)")
    ax.set_xticks([])
    ax.spines["bottom"].set_visible(False)

    xs_prev = [1, 2, 3]
    for x, b in zip(xs_prev, prev):
        brick(ax, x, b.open, b.close)
    x0 = 4.4
    for i, b in enumerate(burst):
        brick(ax, x0 + i, b.open, b.close, phantom=b.burst_index > 0)

    # real fill marker
    ax.plot([x0 - 0.45, 9.8], [106.2, 106.2], color=PATH, lw=1.4, zorder=5)
    ax.plot([x0 - 0.45], [106.2], marker="o", color=PATH, ms=4, zorder=6)
    ax.text(9.8, 106.4, "gap tick: bid 106.2 (spread 0.3), real fill ≈ 106.2", ha="right",
            va="bottom", fontsize=8, color=PATH, fontweight="bold")

    # gap between first brick close and fill
    xa = x0 + 0.65
    ax.plot([x0 + 0.4, x0 + 0.4 + 0.25], [103, 103], color=HILITE, lw=1, zorder=5)
    arrow(ax, (xa, 103), (xa, 106.2), color=HILITE, style="<->")
    ax.text(xa - 0.13, 104.75, "fill is 3.2 above\nthe first brick's\nclose (103)", ha="right",
            va="center", fontsize=8, color=HILITE, fontweight="bold", linespacing=1.15)

    # burst bracket on top
    yb = 107.3
    ax.plot([x0 - 0.4, x0 + 3.4], [yb, yb], color=REF, lw=1.2, solid_capstyle="butt")
    for xx in (x0 - 0.4, x0 + 3.4):
        ax.plot([xx, xx], [yb - 0.18, yb], color=REF, lw=1.2)
    ax.text(x0 + 1.5, yb + 0.15, "all four closed by one tick", ha="center", va="bottom",
            fontsize=8.5, fontweight="bold")

    # burst_index row
    yr = 99.75
    ax.text(0.35, yr, "burst_index", ha="left", va="center", fontsize=8, color=REF)
    for i in range(4):
        ax.text(x0 + i, yr, str(i), ha="center", va="center", fontsize=9,
                fontweight="bold", color=TEXT)
    # earlier bricks label
    ax.text(2, 104.0, "earlier bricks", ha="center", va="bottom", fontsize=8, color=REF)

    # legend
    lx = 0.35
    ax.add_patch(Rectangle((0.2, 105.6), 2.2, 2.3, facecolor="white", edgecolor="none", zorder=2))
    ax.add_patch(Rectangle((lx, 106.85), 0.32, 0.5, facecolor=UP, edgecolor=UP_E, lw=1, zorder=3))
    ax.text(lx + 0.5, 107.1, "tradable", ha="left", va="center", fontsize=8)
    ax.add_patch(Rectangle((lx, 106.0), 0.32, 0.5, facecolor=to_rgba(UP, 0.35),
                           edgecolor=UP_E, lw=1, ls=(0, (3, 2)), zorder=3))
    ax.text(lx + 0.5, 106.25, "phantom", ha="left", va="center", fontsize=8)
    save(fig, "f3_gap_phantom.png")


# ---------------------------------------------------------------------------
# f4 - closed vs forming
# ---------------------------------------------------------------------------
def fig4():
    h = 3.7
    fig = new_fig(h)
    put_title(fig, "Dead-zone ticks move the forming price, not bricks", h)
    rk = new_engine()
    rk.on_tick(1000, 100.3, 100.3)
    rk.on_tick(2000, 102.0, 102.0)
    b0 = rk.get_brick(0)
    assert (b0.open, b0.close) == (101.0, 102.0)
    stored = rk.stored()
    path = [102.9, 100.2, 102.5, 100.01, 102.99]
    forming = []
    for i, p in enumerate(path):
        assert rk.on_tick(3000 + i * 1000, p, p) == 0
        forming.append(rk.last_price)
    assert rk.stored() == stored and rk.get_brick(0) == b0
    assert rk.up_level() == 103.0 and rk.down_level() == 100.0

    axT = fig.add_axes([0.105, 0.32, 0.68, 0.52])
    axB = fig.add_axes([0.105, 0.115, 0.68, 0.16], sharex=axT)
    style_axes(axT)
    style_axes(axB)
    axT.set_xlim(-0.7, 5.7)
    axT.set_ylim(99.45, 103.55)
    axT.set_yticks([100, 101, 102, 103])
    axT.set_ylabel("Price ($)")
    axT.tick_params(labelbottom=False)

    axT.axhspan(100, 103, color=NEUTRAL, zorder=0.5)
    for y, lab in ((103, "continuation trigger 103"), (100, "reversal trigger 100")):
        axT.axhline(y, color=REF, ls="--", lw=1.0, zorder=2)
    side = dict(transform=axT.get_yaxis_transform(), ha="left", va="center", fontsize=8,
                linespacing=1.15, clip_on=False)
    axT.text(1.02, 103, "continuation\ntrigger 103", color=REF, **side)
    axT.text(1.02, 100, "reversal\ntrigger 100", color=REF, **side)
    axT.text(1.02, 101.0, "dead zone\n(100, 103)", color=REF, **side)

    brick(axT, 0, b0.open, b0.close, w=0.7)
    axT.text(0, 100.75, "last closed\nbrick 101→102", ha="center", va="top", fontsize=7.5,
             color=TEXT, linespacing=1.1)

    xs = list(range(1, 6))
    # tick path
    axT.plot([0] + xs, [102.0] + path, color=PATH, lw=1.3, marker="o", ms=4, zorder=5,
             label="tick path")
    # forming price (display only)
    axT.step([0] + xs + [5.55], [102.0] + forming + [forming[-1]], where="post", color=FORM,
             lw=1.2, ls=(0, (3, 2)), zorder=4)
    for x, p in zip(xs, path):
        dy = 0.13 if p > 102 else -0.13
        axT.text(x, p + dy, f"{p:g}", ha="center", va="bottom" if dy > 0 else "top",
                 fontsize=7.5, color=PATH, zorder=7,
                 bbox=dict(fc="white", ec="none", pad=0.6, alpha=0.85))
    axT.text(1.02, 102.0, "dashed grey:\nforming price\n(display only)", color=REF, **side)

    # bottom strip: stored bricks after each tick
    axB.set_ylim(100.35, 102.65)
    axB.set_yticks([101, 102])
    for x in [0] + xs:
        brick(axB, x, b0.open, b0.close, w=0.7)
    axB.set_xticks([0] + xs)
    axB.set_xticklabels(["close"] + [f"tick {i}" for i in xs])
    axB.tick_params(labelsize=7.5)
    axB.set_ylabel("Stored")
    axB.text(1.02, 0.5, "stored bricks\nunchanged:\nno repaint", transform=axB.transAxes,
             ha="left", va="center", fontsize=8, color=HILITE, fontweight="bold",
             linespacing=1.15, clip_on=False)
    axB.set_xlim(-0.7, 5.7)
    save(fig, "f4_closed_vs_forming.png")


# ---------------------------------------------------------------------------
# f5 - real XAUUSD weekly open
# ---------------------------------------------------------------------------
def scan_xau():
    if BRICK_CACHE.exists():
        return pickle.load(open(BRICK_CACHE, "rb"))
    rk = RenkoEngine()
    rk.init(2.0, 4096, 0)
    rows, nt = [], 0
    for ch in pd.read_csv(TAIL_CSV, header=None, names=["dt", "bid", "ask", "vol"],
                          chunksize=2_000_000):
        ch = ch[ch.bid > 0]
        ts = pd.to_datetime(ch.dt, format="%Y%m%d %H:%M:%S.%f").astype(
            "datetime64[ms]").astype("int64").to_numpy()
        bid, ask = ch.bid.to_numpy(), ch.ask.to_numpy()
        for i in range(len(ts)):
            n = rk.on_tick(int(ts[i]), float(bid[i]), float(ask[i]))
            for s in range(n - 1, -1, -1):
                b = rk.get_brick(s)
                rows.append((nt + i, b.id, b.time_close_msc, b.open, b.close, b.dir,
                             b.burst_index, b.trigger_price, b.spread, b.ticks))
        nt += len(ts)
    d = dict(bricks=rows, nt=nt, first=None, last=int(ts[-1]))
    pickle.dump(d, open(BRICK_CACHE, "wb"))
    return d


def fig5():
    d = scan_xau()
    df = pd.DataFrame(d["bricks"], columns="ti id t o c dir burst trig spr ticks".split())
    df["ts"] = pd.to_datetime(df.t, unit="ms")
    size = df.groupby("ti").burst.max() + 1
    # skip bursts whose trigger quote is a data error: spread > $50 on the trigger tick
    cand = size.sort_values(ascending=False)
    chosen = None
    for ti, n in cand.items():
        g = df[df.ti == ti]
        if g.spr.iloc[0] < 50 and g.ts.iloc[0].dayofweek == 6:   # Sunday weekly open
            chosen = (ti, int(n))
            break
    ti, n = chosen
    g = df[df.ti == ti]
    i0 = g.index[0]
    w = df.iloc[i0 - 45: i0 + n + 45].reset_index(drop=True)
    first_i = 45
    last_i = 45 + n - 1
    t_gap = g.ts.iloc[0]
    # last tick before the gap
    before = df.iloc[i0 - 1]
    prev_close_ts = before.ts
    # find the exact last Friday tick time and bid from the csv around row ti
    with open(TAIL_CSV, "rb") as f:
        pass
    ln = _csv_line(ti - 1), _csv_line(ti)
    last_fri_ts, last_fri_bid = ln[0][0], ln[0][1]
    gap_ts, gap_bid, gap_ask = ln[1]
    gap_h = (pd.Timestamp(gap_ts) - pd.Timestamp(last_fri_ts))
    hrs = gap_h.total_seconds() / 3600

    h = 3.7
    fig = new_fig(h)
    put_title(fig, f"One tick at the weekly open printed {n} bricks", h)
    ax = fig.add_axes([0.135, 0.255, 0.845, 0.585])
    axS = fig.add_axes([0.135, 0.19, 0.845, 0.045], sharex=ax)
    style_axes(ax)
    ax.set_ylabel("Price ($ per oz)")
    xs = np.arange(len(w))
    for x, r in zip(xs, w.itertuples()):
        brick(ax, x, r.o, r.c, phantom=r.burst > 0, w=0.82, lw=0.7)
    ax.set_xlim(-1.5, len(w) + 0.5)
    ylo, yhi = w[["o", "c"]].min().min(), w[["o", "c"]].max().max()
    pad = (yhi - ylo) * 0.06
    ax.set_ylim(ylo - pad, yhi + pad)
    ax.tick_params(labelbottom=False)
    ax.spines["bottom"].set_color(GRID)

    # burst span
    ax.axvspan(first_i - 0.5, last_i + 0.5, color=NEUTRAL, zorder=0.4)
    ax.text(first_i + n / 2 - 0.5, yhi + pad * 0.6, f"{n} bricks from\none tick",
            ha="center", va="top", fontsize=7.5, color=REF, linespacing=1.15)

    # annotations
    top_y = w.o.iloc[first_i]
    ax.annotate(f"Fri {pd.Timestamp(last_fri_ts):%Y-%m-%d %H:%M:%S.%f}"[:-3] + f" UTC\nlast tick of the week: bid {last_fri_bid:.2f}",
                xy=(first_i - 0.6, top_y), xytext=(0.8, ylo + (yhi - ylo) * 0.32), ha="left",
                va="center", fontsize=7.5,
                arrowprops=dict(arrowstyle="-|>", color=REF, lw=0.9, mutation_scale=7,
                                shrinkA=2, shrinkB=1, connectionstyle="arc3,rad=0.2"))
    ax.annotate(f"Sun {pd.Timestamp(gap_ts):%Y-%m-%d}\n{pd.Timestamp(gap_ts):%H:%M:%S.%f}"[:-3] + f" UTC\n({hrs:.1f} h after the last tick)\nbid {gap_bid:.2f}, spread {gap_ask - gap_bid:.2f}\n"
                f"closes {n} bricks\n(${n * 2}: {g.o.iloc[0]:.0f} → {g.c.iloc[-1]:.0f})",
                xy=(last_i + 0.6, g.c.iloc[-1] + 1.5), xytext=(last_i + 3.0, yhi - (yhi - ylo) * 0.12),
                ha="left", va="top", fontsize=7.5, color=TEXT, linespacing=1.2,
                arrowprops=dict(arrowstyle="-|>", color=HILITE, lw=1.1, mutation_scale=7,
                                shrinkA=2, shrinkB=1, connectionstyle="arc3,rad=0.2"))

    # legend
    lx, ly = 0.8, ylo + (yhi - ylo) * 0.115
    ax.add_patch(Rectangle((lx, ly), 1.6, (yhi - ylo) * 0.045, facecolor=DN, edgecolor=DN_E, lw=0.8))
    ax.text(lx + 2.6, ly + (yhi - ylo) * 0.022, "tradable", va="center", fontsize=7.5)
    ly2 = ly - (yhi - ylo) * 0.08
    ax.add_patch(Rectangle((lx, ly2), 1.6, (yhi - ylo) * 0.045, facecolor=to_rgba(DN, 0.35),
                           edgecolor=DN_E, lw=0.8, ls=(0, (3, 2))))
    ax.text(lx + 2.6, ly2 + (yhi - ylo) * 0.022, "phantom (burst_index > 0)", va="center", fontsize=7.5)

    # time strip: date segments by UTC date of brick close
    axS.set_ylim(0, 1)
    axS.set_yticks([])
    axS.set_xticks([])
    for s in axS.spines.values():
        s.set_visible(False)
    axS.set_xlim(*ax.get_xlim())
    days = w.ts.dt.normalize()
    segs = []
    start = 0
    for i in range(1, len(w) + 1):
        if i == len(w) or days[i] != days[start]:
            segs.append((start, i - 1, days[start]))
            start = i
    for k, (a, b, day) in enumerate(segs):
        axS.add_patch(Rectangle((a - 0.5, 0), b - a + 1, 1, facecolor=NEUTRAL if k % 2 == 0 else "#DDE2E8",
                                edgecolor="white", lw=1))
        t0, t1 = w.ts[a], w.ts[b]
        axS.text((a + b) / 2, 0.5, f"{day:%a %m-%d}  {t0:%H:%M}–{t1:%H:%M} UTC",
                 ha="center", va="center", fontsize=7, color=TEXT)
    fig.text(0.135, 0.165, "x = brick index; the strip shows the UTC close times of the bricks above",
             ha="left", va="top", fontsize=7, color=REF)
    first_day = df.ts.iloc[0]
    put_source(fig, f"XAUUSD ticks {first_day:%Y-%m-%d} to 2026-09-02, $2 bricks, Python port of RenkoEngine.mqh", h)
    save(fig, "f5_xauusd_session.png")
    return dict(n=n, gap_ts=gap_ts, gap_bid=gap_bid, last_ts=last_fri_ts, last_bid=last_fri_bid,
                hrs=hrs, o=g.o.iloc[0], c=g.c.iloc[-1], nbricks=len(w), spread=gap_ask - gap_bid,
                ti=ti)


def _csv_line(row):
    """Return (timestamp str, bid, ask) of csv row index `row` (0-based, no header)."""
    with open(TAIL_CSV, "r", encoding="ascii") as f:
        for i, line in enumerate(f):
            if i == row:
                a = line.strip().split(",")
                return a[0], float(a[1]), float(a[2])


# ---------------------------------------------------------------------------
# f6 - architecture
# ---------------------------------------------------------------------------
def box(ax, x, y, w, h, text, fc=NEUTRAL, ec=REF, tc=TEXT, ls="-", lw=1.1, fs=8, bold=False):
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.1", fc=fc, ec=ec,
                       lw=lw, ls=ls, zorder=3)
    ax.add_patch(p)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=tc,
            linespacing=1.25, fontweight="bold" if bold else "normal", zorder=4)


def conn(ax, p0, p1, color=REF, ls="-", rad=0.0, lw=1.3):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=9, color=color,
                                 lw=lw, ls=ls, shrinkA=0, shrinkB=0,
                                 connectionstyle=f"arc3,rad={rad}", zorder=2))


def fig6():
    h = 3.5
    fig = new_fig(h)
    put_title(fig, "Only closed bricks reach the signal logic", h)
    ax = fig.add_axes([0.0, 0.0, 1.0, 1 - 0.55 / h])
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6.2)
    ax.axis("off")

    # column headers
    for x, t in ((1.6, "Tick sources"), (5.2, "Engine"), (8.35, "Outputs")):
        ax.text(x, 5.95, t.upper(), fontsize=7, color=REF, fontweight="bold", ha="center",
                va="center")
    # sources
    sx, sw, sh = 0.25, 2.7, 1.05
    ys = [4.35, 2.95, 1.55]
    box(ax, sx, ys[0], sw, sh, "Live feed\nOnTick() in the EA")
    box(ax, sx, ys[1], sw, sh, "History replay\nCopyTicksRange() via\nFeedHistory")
    box(ax, sx, ys[2], sw, sh, "File replay\nCTickCsvReader\n(tick CSV)")
    # engine
    ex, ew = 3.9, 2.6
    box(ax, ex, 2.55, ew, 2.35, "CRenkoEngine\nOnTick(time_msc,\nbid, ask)", fc=PATH, ec=PATH,
        tc="white", fs=8.5, bold=True)
    ymid = 2.55 + 2.35 / 2
    for y in ys:
        conn(ax, (sx + sw, y + sh / 2), (ex, ymid + (y + sh / 2 - ymid) * 0.35), rad=0.0)
    # SetBrickSize
    box(ax, ex, 0.55, ew, 0.95, "SetBrickSize()\nre-anchors the grid", fc="white", ec=HILITE,
        ls=(0, (4, 2)), fs=8)
    conn(ax, (ex + ew / 2, 1.5), (ex + ew / 2, 2.55), color=HILITE)
    # outputs
    ox, ow = 7.0, 2.7
    box(ax, ox, 3.9, ow, 1.55, "Closed bricks\nring buffer\nGetBrick(shift)\nused for signals",
        fc="#E3F2EA", ec=UP_E, lw=1.5, fs=8)
    box(ax, ox, 1.45, ow, 1.55, "Forming state\nFormingPrice / ticks\ndisplay only,\nnever stored",
        fc="white", ec=FORM, ls=(0, (4, 2)), lw=1.4, fs=8)
    conn(ax, (ex + ew, ymid + 0.5), (ox, 4.65), color=UP_E, lw=1.6)
    conn(ax, (ex + ew, ymid - 0.5), (ox, 2.25), color=FORM)
    ax.text(ox + ow / 2, 0.85, "a tick inside the dead zone\nmoves only this box", fontsize=7.5,
            color=REF, ha="center", va="center", linespacing=1.2)
    save(fig, "f6_architecture.png")


if __name__ == "__main__":
    fig1()
    print("f2 bricks", fig2())
    fig3()
    fig4()
    print("f5", fig5())
    fig6()
