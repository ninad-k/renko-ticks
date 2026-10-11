"""Figures for Part 4: Making a Renko EA Pass Automatic Validation.

Run:  python make_ep04.py   (writes figures/ep04/*.png, 750 px wide, STYLE.md colours)
"""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon, FancyArrowPatch
from PIL import Image

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ep04")
os.makedirs(OUT, exist_ok=True)

# STYLE.md palette
UP, UP_E = "#1F8A5B", "#14684A"
DN, DN_E = "#C8423B", "#9E2F2A"
PATH = "#2B4C7E"
FORM = "#9AA3AE"
REF = "#6B7280"
HI = "#D98E04"
NEUT = "#EEF1F4"
GRID = "#E6E8EB"
INK = "#1F2933"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.titlesize": 11,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "figure.dpi": 150,
    "savefig.dpi": 150,
})
W_IN = 5.0
DPI = 150


def tint(hexcol, alpha):
    """Blend a palette colour with white (same look as alpha on white)."""
    h = hexcol.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r = round(255 - (255 - r) * alpha)
    g = round(255 - (255 - g) * alpha)
    b = round(255 - (255 - b) * alpha)
    return "#%02X%02X%02X" % (r, g, b)


_probe_fig = plt.figure(figsize=(W_IN, 1), dpi=DPI)
_probe_r = _probe_fig.canvas.get_renderer()


def text_w_in(s, fs, weight="normal"):
    t = _probe_fig.text(0, 0, s, fontsize=fs, fontweight=weight)
    w = t.get_window_extent(_probe_r).width / DPI
    t.remove()
    return w


def wrap(s, width_in, fs, weight="normal"):
    lines, cur = [], ""
    for word in s.split():
        trial = word if not cur else cur + " " + word
        if text_w_in(trial, fs, weight) <= width_in or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def new_canvas(h_in):
    fig = plt.figure(figsize=(W_IN, h_in), dpi=DPI, facecolor="white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W_IN)
    ax.set_ylim(0, h_in)
    ax.axis("off")
    return fig, ax


def title(ax, h_in, text, y_top=0.12):
    lines = wrap(text, W_IN - 0.4, 11, "bold")
    y = h_in - y_top
    for ln in lines:
        ax.text(0.2, y, ln, fontsize=11, fontweight="bold", color=INK, ha="left", va="top")
        y -= 0.2
    return y


def box(ax, x, y, w, h, fc=NEUT, ec=REF, lw=0.8, ls="-", r=0.05, z=2):
    p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                       fc=fc, ec=ec, lw=lw, ls=ls, zorder=z)
    ax.add_patch(p)
    return p


def arrow(ax, x0, y0, x1, y1, col=REF, ls="-", lw=1.0, z=1):
    a = FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=8,
                        color=col, lw=lw, ls=ls, zorder=z, shrinkA=0, shrinkB=0)
    ax.add_patch(a)


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=DPI, bbox_inches=None, facecolor="white")
    plt.close(fig)
    im = Image.open(path)
    # re-save as an optimised palette PNG to keep files small
    im = im.convert("RGB").quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    im.save(path, optimize=True)
    im = Image.open(path)
    print(name, im.size, os.path.getsize(path) // 1024, "KB")


# ---------------------------------------------------------------- Figure 1
def figure1():
    rows = [
        ("There are no trading operations",
         "A fixed price-unit brick and a 500-brick warm-up fit one symbol. Elsewhere no brick closes, or no trade follows.",
         "Brick = 0.25 x ATR(14) of the last D1 bar. Warm-up of 3 bricks. ATR wait capped at 60 minutes."),
        ("Invalid volume [10014]",
         "Lot off the volume step or outside min and max, typical for risk-based lots.",
         "MS_NormalizeVolume rounds down to the step and clamps to min and max. MS_CheckMarketOrder checks it again."),
        ("Not enough money [10019]",
         "Order sent without looking at free margin, while the validator uses small deposits.",
         "OrderCalcMargin against free margin before every order. On failure: skip and print why."),
        ("Invalid stops [10016]",
         "A 2-brick stop on a small brick can land inside the stops level or the spread.",
         "SL and TP pushed out to max(stops, freeze level) + 1 tick, rounded to the tick grid."),
        ("Market closed / trade disabled",
         "Opening on a symbol that is close-only or disabled, or with algo trading off.",
         "MS_TradingAllowed reads terminal, account and SYMBOL_TRADE_MODE for each direction."),
    ]
    fs = 8
    x0, gap = 0.15, 0.2
    cw = [0.95, 1.62, 1.72]
    xs = [x0, x0 + cw[0] + gap, x0 + cw[0] + gap + cw[1] + gap]
    pad = 0.07
    lh = 0.135
    wrapped = []
    for r in rows:
        cols = [wrap(r[0], cw[0] - 2 * pad, fs, "bold"),
                wrap(r[1], cw[1] - 2 * pad, fs),
                wrap(r[2], cw[2] - 2 * pad, fs)]
        wrapped.append(cols)
    heights = [max(len(c) for c in cols) * lh + 2 * pad + 0.02 for cols in wrapped]
    row_gap = 0.12
    head_h = 0.26
    title_txt = "Each validator failure traces to a specific Renko choice and has a fix in the EA"
    n_title = len(wrap(title_txt, W_IN - 0.4, 11, "bold"))
    top = 0.12 + 0.2 * n_title + 0.1
    foot = 0.3
    H = top + head_h + 0.08 + sum(heights) + row_gap * (len(rows) - 1) + foot
    fig, ax = new_canvas(H)
    title(ax, H, title_txt)
    y = H - top
    heads = ["Validator report", "Cause in a Renko EA", "Fix in the EA"]
    for i, hd in enumerate(heads):
        ax.text(xs[i] + 0.02, y - head_h / 2, hd, fontsize=8, fontweight="bold", color=REF, ha="left", va="center")
    y -= head_h + 0.08
    for cols, h in zip(wrapped, heights):
        yb = y - h
        fills = [tint(DN, 0.18), NEUT, tint(UP, 0.16)]
        edges = [DN_E, REF, UP_E]
        for i in range(3):
            box(ax, xs[i], yb, cw[i], h, fc=fills[i], ec=edges[i])
            n = len(cols[i])
            ytxt = yb + h / 2 + (n - 1) * lh / 2
            for k, ln in enumerate(cols[i]):
                ax.text(xs[i] + pad, ytxt - k * lh, ln, fontsize=fs, color=INK, ha="left", va="center",
                        fontweight="bold" if i == 0 else "normal")
        for i in range(2):
            arrow(ax, xs[i] + cw[i] + 0.02, yb + h / 2, xs[i + 1] - 0.02, yb + h / 2)
        y = yb - row_gap
    ax.text(0.15, 0.12, "Failure names from the Market validation checks; fixes from RenkoTickContinuationEA 1.00.",
            fontsize=6.5, color=FORM, ha="left", va="center")
    save(fig, "f1_validator_risks.png")


# ---------------------------------------------------------------- Figure 2
def figure2():
    fs = 8
    lh = 0.135
    pad = 0.07
    cx = 1.75          # centre column x
    bw = 2.3           # box width
    nw = 1.6           # note width (right side)
    nx = cx + bw / 2 + 0.22
    steps = [
        ("box", "New tick", "SymbolInfoTick: bid and ask above zero"),
        ("box", "ServiceBrickSize", "Waits for the daily ATR, or refits the brick on a new D1 bar"),
        ("box", "CRenkoEngine.OnTick(tick)", "Returns n, the number of bricks this tick closed"),
        ("dia", "n > 0 ?", None),
        ("dia", "Run first reached InpSameBricks on this tick?", None),
        ("box", "Position and spread checks", "Foreign netting position, same side open, close on reversal, spread cap"),
        ("box", "Stops adjusted", "SL and TP beyond the stops and freeze level, on the tick grid"),
        ("box", "Lot normalised", "Round down to the volume step, clamp to min and max"),
        ("box", "MS_CheckMarketOrder", "Trade mode, free margin (OrderCalcMargin), volume limit, stops again"),
        ("box", "OrderSend and result", "Retcode checked, one line logged"),
    ]
    notes = {
        3: "No: wait for the next tick",
        4: "No: nothing to do",
        5: "Foreign position, frozen close or wide spread: skip",
        6: "SL at or below zero: skip",
        7: "Lot cannot be computed: skip",
        8: "Any check fails: skip and print why",
    }
    hs = []
    for kind, head, sub in steps:
        if kind == "box":
            sub_l = wrap(sub, bw - 2 * pad, fs)
            hs.append(0.2 + len(sub_l) * lh + 0.06)
        else:
            hs.append(0.78 if head.startswith("Run") else 0.46)
    gaps = [0.2, 0.2, 0.2, 0.42, 0.2, 0.2, 0.2, 0.2, 0.2]
    title_txt = "One tick makes one decision, and an order passes four gates before it is sent"
    n_title = len(wrap(title_txt, W_IN - 0.4, 11, "bold"))
    top = 0.12 + 0.2 * n_title + 0.1
    H = top + sum(hs) + sum(gaps) + 0.15
    fig, ax = new_canvas(H)
    title(ax, H, title_txt)
    y = H - top
    centres = []
    for idx, ((kind, head, sub), h) in enumerate(zip(steps, hs)):
        yb = y - h
        yc = yb + h / 2
        centres.append((yb, y, yc))
        if kind == "box":
            is_trade = head in ("Lot normalised", "MS_CheckMarketOrder", "Stops adjusted",
                                "OrderSend and result", "Position and spread checks")
            fc = tint(UP, 0.14) if is_trade else NEUT
            ec = UP_E if is_trade else REF
            box(ax, cx - bw / 2, yb, bw, h, fc=fc, ec=ec)
            ax.text(cx, y - 0.04, head, fontsize=fs, fontweight="bold", color=INK, ha="center", va="top")
            sub_l = wrap(sub, bw - 2 * pad, fs)
            for k, ln in enumerate(sub_l):
                ax.text(cx, y - 0.2 - k * lh, ln, fontsize=7.5, color=INK, ha="center", va="top")
        else:
            half_w = bw / 2 + 0.05
            poly = Polygon([(cx - half_w, yc), (cx, y), (cx + half_w, yc), (cx, yb)], closed=True,
                           fc=tint(HI, 0.16), ec=HI, lw=0.9, zorder=2)
            ax.add_patch(poly)
            lines = wrap(head, 1.3, fs, "bold")
            for k, ln in enumerate(lines):
                ax.text(cx, yc + (len(lines) - 1) * lh / 2 - k * lh, ln, fontsize=fs, fontweight="bold",
                        color=INK, ha="center", va="center")
        y = yb - (gaps[idx] if idx < len(gaps) else 0)
    for i in range(len(steps) - 1):
        yb = centres[i][0]
        yt_next = centres[i + 1][1]
        arrow(ax, cx, yb, cx, yt_next)
        if steps[i][0] == "dia":
            ax.text(cx - 0.06, (yb + yt_next) / 2, "yes", fontsize=7.5, color=REF, ha="right", va="center")
    for i, txt in notes.items():
        yb, yt, yc = centres[i]
        kind = steps[i][0]
        x_start = cx + (bw / 2 + 0.05 if kind == "dia" else bw / 2)
        arrow(ax, x_start, yc, nx - 0.02, yc, col=FORM, ls="--", lw=0.9)
        lines = wrap(txt, nw, 7.5)
        for k, ln in enumerate(lines):
            ax.text(nx, yc + (len(lines) - 1) * 0.06 - k * 0.12, ln, fontsize=7.5, color=REF, ha="left", va="center")
    # gap callout between the two diamonds, on the right
    y_mid = (centres[3][0] + centres[4][1]) / 2
    call = wrap("n > 1 is a gap: the extra bricks are phantom, so the EA decides once, at this tick's bid and ask",
                nw, 7.5, "bold")
    for k, ln in enumerate(call):
        ax.text(nx, y_mid + (len(call) - 1) * 0.06 - k * 0.12, ln, fontsize=7.5, color=HI, ha="left", va="center",
                fontweight="bold")
    arrow(ax, cx + 0.02, y_mid, nx - 0.02, y_mid, col=HI, ls="--", lw=0.9)
    save(fig, "f2_tick_to_order.png")


# ---------------------------------------------------------------- Figure 3
def figure3():
    syms = ["XAUUSD", "EURUSD", "US500"]
    rng = np.array([129.39, 0.00660, 87.03])          # average daily range, price units
    frac = 0.25
    atr_brick = frac * rng
    fixed = 15.0
    per_day_atr = rng / atr_brick                      # 4 by construction
    per_day_fix = rng / fixed
    range_lbl = ["range $129.4", "range 0.00660", "range 87.03 pts"]
    brick_lbl = ["brick $32.3", "brick 0.00165", "brick 21.8 pts"]

    h = 4.7
    fig = plt.figure(figsize=(W_IN, h), dpi=DPI, facecolor="white")
    title_txt = "A fixed 15-unit brick spans 0.0004 to 8.6 bricks of a day's range; 0.25 x ATR spans 4 on every symbol"
    lines = wrap(title_txt, W_IN - 0.4, 11, "bold")
    for k, ln in enumerate(lines):
        fig.text(0.2 / W_IN, 1 - (0.12 + 0.2 * k) / h, ln, fontsize=11, fontweight="bold", color=INK, ha="left", va="top")
    top_in = 0.12 + 0.2 * len(lines) + 0.45
    bottom_in = 1.55
    ax = fig.add_axes([0.85 / W_IN, bottom_in / h, (W_IN - 0.85 - 0.2) / W_IN, (h - bottom_in - top_in) / h])
    x = np.arange(3)
    bw = 0.36
    ax.set_yscale("log")
    ax.set_ylim(1e-4, 1e2)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=GRID, lw=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(REF)
    ax.bar(x - bw / 2 - 0.01, per_day_atr, bw, color=UP, edgecolor=UP_E, lw=0.8,
           label="Brick = 0.25 x daily ATR (EA default)")
    ax.bar(x + bw / 2 + 0.01, per_day_fix, bw, color=DN, edgecolor=DN_E, lw=0.8,
           label="Fixed brick of 15 price units")
    ax.axhline(1.0, color=REF, lw=0.9, ls="--")
    ax.text(2.55, 1.15, "range of one\nbrick per\naverage day", fontsize=7.5, color=REF, ha="left", va="bottom", linespacing=1.1)
    vals = ["8.6", "0.00044", "5.8"]
    for i in range(3):
        ax.text(x[i] - bw / 2 - 0.01, per_day_atr[i] * 1.25, f"{per_day_atr[i]:.1f}", ha="center", va="bottom",
                fontsize=8, color=UP_E, fontweight="bold")
        ax.text(x[i] + bw / 2 + 0.01 - (bw / 2 if i == 1 else 0), per_day_fix[i] * 1.25, vals[i],
                ha="left" if i == 1 else "center", va="bottom", fontsize=8, color=DN_E, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(syms, fontsize=9, fontweight="bold")
    ax.set_xlim(-0.6, 3.3)
    ax.set_ylabel("Average daily range in bricks\n(range / brick, log scale)", fontsize=8.5)
    ax.tick_params(axis="x", length=0, pad=4)
    ax.tick_params(axis="y", labelsize=8)
    ax.set_yticks([1e-4, 1e-3, 1e-2, 1e-1, 1, 10, 100])
    ax.set_yticklabels(["0.0001", "0.001", "0.01", "0.1", "1", "10", "100"])
    ax.minorticks_off()
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), fontsize=7.5, frameon=False, ncol=1, handlelength=1.2,
              borderaxespad=0.1)
    for i in range(3):
        xf = ax.transData.transform((x[i], 1e-4))[0] / (W_IN * DPI)
        fig.text(xf, (bottom_in - 0.4) / h, range_lbl[i], fontsize=7.5, color=REF, ha="center", va="top")
        fig.text(xf, (bottom_in - 0.55) / h, brick_lbl[i], fontsize=7.5, color=UP_E, ha="center", va="top")
    cap = wrap("On EURUSD a fixed 15 is 2,273 days of range, so no brick ever prints. On XAUUSD it is 12% of a day, on US500 17%.",
               W_IN - 0.4, 7.5)
    for k, ln in enumerate(cap):
        fig.text(0.2 / W_IN, (0.68 - 0.14 * k) / h, ln, fontsize=7.5, color=INK, ha="left", va="center")
    src = wrap("Average daily range from tick data: XAUUSD 2026 average, EURUSD and US500 April 2026. Ratio = range / brick.",
               W_IN - 0.4, 6.5)
    for k, ln in enumerate(src):
        fig.text(0.2 / W_IN, (0.26 - 0.11 * k) / h, ln, fontsize=6.5, color=FORM, ha="left", va="center")
    path = os.path.join(OUT, "f3_brick_scaling.png")
    fig.savefig(path, dpi=DPI, bbox_inches=None, facecolor="white")
    plt.close(fig)
    im = Image.open(path).convert("RGB").quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    im.save(path, optimize=True)
    im = Image.open(path)
    print("f3_brick_scaling.png", im.size, os.path.getsize(path) // 1024, "KB")


if __name__ == "__main__":
    figure1()
    figure2()
    figure3()
