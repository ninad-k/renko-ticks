"""Figures for part 2: What a Renko Backtest Hides.

Run:  python make_ep02.py
Writes figures/ep02/f1..f6 (750 px wide PNG). Data comes from results/ep02
(cost_by_size.csv, cost_by_year.csv, market_by_year.csv, overshoot_*.parquet),
which were produced by the Python port of RenkoSweep. Nothing is re-run here.
Every number in a title or label is read from those files, so the script can be
re-run unchanged when the results are refreshed.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter  # noqa: E402

HERE = Path(__file__).resolve().parent
RES = HERE.parent / "results" / "ep02"
OUT = HERE / "ep02"
OUT.mkdir(exist_ok=True)

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
    "text.parse_math": False,
    "figure.dpi": DPI,
    "savefig.dpi": DPI,
})


def new_fig(h):
    return plt.figure(figsize=(W, h), facecolor="white")


def put_title(fig, lines, h):
    fig.text(0.02, 1 - 0.12 / h, "\n".join(lines), ha="left", va="top", fontsize=11,
             fontweight="bold", linespacing=1.3)


def put_source(fig, text, h, y=0.09):
    fig.text(0.02, y / h, text, ha="left", va="bottom", fontsize=6.5, color=FORM)


def rect(h, left, bottom, width, height):
    """Axes rectangle from inches (origin bottom-left) to figure fractions."""
    return [left / W, bottom / h, width / W, height / h]


def style_axes(ax, ygrid=True):
    ax.set_facecolor("white")
    if ygrid:
        ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(length=3, width=0.6)


def save(fig, name):
    p = OUT / name
    fig.savefig(p, dpi=DPI, bbox_inches=None, facecolor="white")
    plt.close(fig)
    print("wrote", p)


# ---- data ------------------------------------------------------------------
cost = pd.read_csv(RES / "cost_by_size.csv")
fixed = cost[cost.kind == "fixed"].reset_index(drop=True)
cby = pd.read_csv(RES / "cost_by_year.csv")
mby = pd.read_csv(RES / "market_by_year.csv")
oq = pd.read_csv(RES / "overshoot_quantiles.csv").set_index("label")
fe = pd.read_csv(RES / "filter_effect.csv")
SIZES = fixed.param.values
N_TICKS = int(mby[mby.year.astype(str) == "ALL"].ticks.iloc[0])
SRC = "XAUUSD ticks 2017-10 to 2026-09-02, Python port of RenkoSweep"


def row(p):
    return fixed[np.isclose(fixed.param, p)].iloc[0]


def size_fmt(v):
    return f"{v:g}"


def sgn(v, nd=2):
    return f"{'+' if v >= 0 else '-'}${abs(v):.{nd}f}"


def log_x_sizes(ax):
    ax.set_xscale("log")
    ax.set_xlim(0.42, 62)
    ax.xaxis.set_major_locator(FixedLocator([0.5, 1, 2, 5, 10, 20, 50]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: size_fmt(v)))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel("Brick size ($ per oz, log scale)")


# ---------------------------------------------------------------------------
# f1 - theo vs net per trade
# ---------------------------------------------------------------------------
def fig1():
    h = 3.75
    r1 = row(1.0)
    pos = fixed[fixed.A_net_per_trade > 0].param.min()
    npos = int(fixed[np.isclose(fixed.param, pos)].A_trades.iloc[0])
    fig = new_fig(h)
    put_title(fig, [f"A $1 flip-follow shows {sgn(r1.A_theo_per_trade)} per trade but",
                    f"fills at {sgn(r1.A_net_per_trade)}; net turns positive at ${pos:g}"], h)
    ax = fig.add_axes(rect(h, 0.62, 0.70, 4.25, 2.35))
    style_axes(ax)
    ax.set_yscale("symlog", linthresh=1.0, linscale=0.75)
    x = SIZES
    theo = fixed.A_theo_per_trade.values
    net = fixed.A_net_per_trade.values
    ax.fill_between(x, net, theo, color=HILITE, alpha=0.22, lw=0, zorder=2)
    ax.axhline(0, color=REF, lw=0.9, ls=(0, (4, 3)), zorder=3)
    ax.plot(x, theo, color=HILITE, lw=1.8, marker="o", ms=3.6, zorder=5,
            label="theo: filled at the brick boundary, no costs")
    ax.plot(x, net, color=PATH, lw=1.8, marker="o", ms=3.6, zorder=5,
            label="net: next-tick fill, real bid/ask, $7/lot")
    ax.set_ylim(-2.2, 40)
    ax.set_yticks([-1, 0, 1, 3, 10, 30])
    ax.set_yticklabels(["-1", "0", "1", "3", "10", "30"])
    ax.yaxis.set_minor_locator(FixedLocator([]))
    log_x_sizes(ax)
    ax.set_ylabel("Per trade ($ per oz, symlog scale)")
    ax.legend(loc="upper left", frameon=False, fontsize=7.5, handlelength=1.6, borderaxespad=0.2)
    gap1 = r1.A_theo_per_trade - r1.A_net_per_trade
    ax.plot([1.0, 1.0], [r1.A_net_per_trade, r1.A_theo_per_trade], color=TEXT, lw=1.0, zorder=6)
    ax.annotate(f"$1: {r1.A_theo_per_trade:+.2f} vs {r1.A_net_per_trade:+.2f}\n"
                f"gap {gap1:.2f} = {100 * gap1 / 1.0:.0f}% of a brick",
                xy=(1.0, 0.05), xytext=(0.46, 3.6), fontsize=7.5, color=TEXT, ha="left",
                arrowprops=dict(arrowstyle="-", color=REF, lw=0.7, shrinkA=2, shrinkB=1, relpos=(0.2, 0.0)),
                zorder=8)
    ax.axvline(pos, color=REF, lw=0.8, ls=(0, (2, 2)), zorder=1)
    ax.text(pos * 1.12, -1.0, f"net > 0\nfrom ${pos:g}\n({npos:,} trades)", fontsize=7.5, ha="left", va="center",
            color=TEXT, zorder=8)
    put_source(fig, SRC + ". Strategy A, fixed bricks.", h)
    save(fig, "f1_theo_vs_net.png")


# ---------------------------------------------------------------------------
# f2 - approximate cost decomposition
# ---------------------------------------------------------------------------
def decomposition():
    d = fixed.copy()
    d["gap"] = d.A_theo_per_trade - d.A_net_per_trade
    d["sp"] = d.avg_spread
    d["com"] = 0.07
    d["ov"] = 2 * d.avg_overshoot
    d["res"] = d.gap - d.sp - d.com - d.ov
    for c in ["gap", "sp", "com", "ov", "res"]:
        d[c + "_p"] = 100 * d[c] / d.avg_brick
    return d


def draw_stack(ax, d):
    xs = np.arange(len(d))
    bw = 0.72
    comps = [("sp_p", PATH, "spread"), ("com_p", FORM, "commission"), ("ov_p", HILITE, "2 x overshoot")]
    bottom = np.zeros(len(d))
    for key, col, lab in comps:
        v = d[key].values
        ax.bar(xs, v, bw, bottom=bottom, color=col, lw=0, zorder=3, label=lab)
        bottom += v
    res = d.res_p.values
    pos = np.where(res > 0, res, 0)
    neg = np.where(res < 0, res, 0)
    ax.bar(xs, pos, bw, bottom=bottom, facecolor=NEUTRAL, edgecolor=REF, hatch="////", lw=0.6, zorder=3,
           label="residual")
    ax.bar(xs, neg, bw, bottom=0, facecolor=NEUTRAL, edgecolor=REF, hatch="////", lw=0.6, zorder=3)
    ax.axhline(0, color=REF, lw=0.8, zorder=4)
    gap = d.gap_p.values
    ax.scatter(xs, gap, marker="_", s=70, color=TEXT, lw=1.6, zorder=6, label="gap (theo - net)")
    ax.set_xticks(xs)
    ax.set_xticklabels([size_fmt(v) for v in d.param.values])
    ax.set_xlim(-0.6, len(d) - 0.4)
    ax.tick_params(axis="x", labelsize=7.5)
    return xs, gap


def fig2():
    d = decomposition()
    h = 3.6
    s1, s2, s20 = (float(d[np.isclose(d.param, p)].sp_p.iloc[0]) for p in (1, 2, 20))
    fig = new_fig(h)
    put_title(fig, [f"Spread is most of the gap: {s1:.0f}% of a $1 brick,",
                    f"{s2:.0f}% of a $2 brick, {s20:.0f}% of a $20 brick"], h)
    left = d[d.param <= 6]
    right = d[d.param >= 8]
    axL = fig.add_axes(rect(h, 0.62, 0.95, 1.95, 1.70))
    axR = fig.add_axes(rect(h, 2.86, 0.95, 2.04, 1.70))
    for ax in (axL, axR):
        style_axes(ax)
    xs, gap = draw_stack(axL, left)
    ymaxL = float(left.gap_p.max())
    for x, g in zip(xs, gap):
        axL.text(x, g + ymaxL * 0.015, f"{g:.0f}%", ha="center", va="bottom", fontsize=7)
    axL.set_ylim(0, ymaxL * 1.15)
    axL.set_ylabel("Cost per trade (% of brick)")
    axL.set_xlabel("Brick size ($): 0.5 to 6")
    xs, gap = draw_stack(axR, right)
    ymaxR = float(right.gap_p.max())
    yminR = float(min(0, right.res_p.min()))
    tops = (right.sp_p + right.com_p + right.ov_p + right.res_p.clip(lower=0)).values
    for x, g, tp in zip(xs, gap, tops):
        axR.text(x, max(g, tp) + ymaxR * 0.02, f"{g:.0f}%", ha="center", va="bottom", fontsize=7)
    axR.set_ylim(yminR - 1.0, ymaxR * 1.18)
    axR.set_xlabel("Brick size ($): 8 to 50")
    h_, l_ = axL.get_legend_handles_labels()
    fig.legend(h_, l_, loc="upper left", bbox_to_anchor=(0.075, 1 - 0.68 / h), frameon=False, fontsize=7,
               ncol=5, handlelength=1.1, columnspacing=1.0, handletextpad=0.4)
    put_source(fig, SRC + ". Approximate.", h)
    save(fig, "f2_cost_decomposition.png")


# ---------------------------------------------------------------------------
# f3 - phantom and sub-second shares
# ---------------------------------------------------------------------------
def fig3():
    h = 3.45
    r05, r20 = row(0.5), row(20)
    fig = new_fig(h)
    put_title(fig, [f"At $0.50, {r05.phantom_pct:.1f}% of bricks are phantom and {r05.subsec_pct:.1f}%",
                    "of closing ticks come within a second of the last"], h)
    ax = fig.add_axes(rect(h, 0.62, 0.70, 4.25, 2.15))
    style_axes(ax)
    x = SIZES
    ph = fixed.phantom_pct.values
    ss = fixed.subsec_pct.values
    ax.plot(x, ss, color=PATH, lw=1.8, marker="o", ms=3.6, zorder=5)
    ax.plot(x, ph, color=HILITE, lw=1.8, marker="o", ms=3.6, zorder=5)
    log_x_sizes(ax)
    ax.set_ylim(0, max(ss.max(), ph.max()) * 1.12)
    ax.set_ylabel("Share (%)")
    top = ss.max()
    ax.text(0.5, ss[0] + top * 0.04, f"{ss[0]:.1f}%", color=PATH, fontsize=8, ha="left", va="bottom")
    ax.text(0.5, ph[0] + top * 0.04, f"{ph[0]:.1f}%", color=HILITE, fontsize=8, ha="left", va="bottom")
    ax.text(1.35, top * 0.80, "closing ticks within 1 s of\nthe previous closing tick", color=PATH,
            fontsize=7.5, va="center")
    ax.text(5.5, top * 0.30, "phantom bricks, share of all bricks", color=HILITE, fontsize=7.5, va="center")
    ax.annotate(f"$20: {r20.phantom_pct:.1f}% phantom,\n{r20.subsec_pct:.2f}% sub-second",
                xy=(20, r20.phantom_pct), xytext=(10.5, top * 0.50), fontsize=7.5, color=TEXT,
                arrowprops=dict(arrowstyle="-", color=REF, lw=0.7, shrinkA=2, shrinkB=3))
    put_source(fig, SRC + ". Fixed bricks.", h)
    save(fig, "f3_phantom_subsecond.png")


# ---------------------------------------------------------------------------
# f4 - spread as % of brick by year
# ---------------------------------------------------------------------------
def fig4():
    h = 3.9

    def v(lab, yr):
        s = cby[(cby.label == lab) & (cby.year == yr)]
        return float(s.spread_pct_of_brick.iloc[0])

    fig = new_fig(h)
    put_title(fig, [f"Spread took {v('$2.00', 2017):.0f}% of a $2 brick in 2017 and {v('$2.00', 2026):.0f}% in 2026;",
                    f"0.15xATR bricks went from {v('0.15xATR', 2018):.0f}% to {v('0.15xATR', 2026):.0f}%"], h)
    ax = fig.add_axes(rect(h, 0.62, 0.78, 4.25, 2.20))
    style_axes(ax)
    series = [("$2.00", "fixed $2", PATH, "-", "o"),
              ("$5.00", "fixed $5", PATH, (0, (5, 1.5, 1, 1.5)), "s"),
              ("$15.00", "fixed $15", PATH, (0, (1, 1.5)), "^"),
              ("0.15xATR", "0.15 x ATR", HILITE, "-", "o"),
              ("0.50xATR", "0.50 x ATR", HILITE, (0, (5, 1.5, 1, 1.5)), "s")]
    ax.set_yscale("log")
    for lab, name, col, ls, mk in series:
        s = cby[cby.label == lab].sort_values("year")
        ax.plot(s.year, s.spread_pct_of_brick, color=col, ls=ls, lw=1.7, marker=mk, ms=3.8, label=name, zorder=5)
    ax.set_xlim(2016.6, 2026.4)
    ax.set_ylim(0.7, 130)
    ax.set_xticks(range(2017, 2027))
    ax.set_xticklabels(["2017*"] + [str(y) for y in range(2018, 2026)] + ["2026*"])
    ax.yaxis.set_major_locator(FixedLocator([1, 2, 5, 10, 20, 50, 100]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}"))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_ylabel("Spread at closing tick (% of brick)")
    ax.tick_params(axis="x", labelsize=7.5)
    ax.annotate(f"2020: $2 at {v('$2.00', 2020):.0f}%,\n0.15xATR at {v('0.15xATR', 2020):.0f}%",
                xy=(2019.95, v("0.15xATR", 2020) * 0.95), xytext=(2016.8, 30), fontsize=7.5, ha="left",
                arrowprops=dict(arrowstyle="-", color=REF, lw=0.7, shrinkA=2, shrinkB=3))
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper left", bbox_to_anchor=(0.095, 1 - 0.66 / h), frameon=False,
               fontsize=7.5, ncol=5, handlelength=2.2, columnspacing=0.9, handletextpad=0.4)
    fig.text(0.02, 0.27 / h, "* 2017 is Oct-Dec only, 2026 runs to 2 Sep. ATR bricks use the previous quarter's\n"
             "average daily range, so they start in 2018.", fontsize=6.5, color=REF, va="bottom", linespacing=1.3)
    put_source(fig, SRC + ".", h)
    save(fig, "f4_spread_vs_brick_by_year.png")


# ---------------------------------------------------------------------------
# f5 - overshoot distribution
# ---------------------------------------------------------------------------
def fig5():
    h = 3.6
    q2 = oq.loc["fixed_2"]
    fig = new_fig(h)
    put_title(fig, [f"Typical overshoot is small (median {q2.p50:.2f} brick at $2),",
                    f"but {100 * q2.share_gt_0_5:.1f}% of $2 closing ticks pass half a brick"], h)
    ax = fig.add_axes(rect(h, 0.80, 0.70, 4.05, 2.30))
    style_axes(ax)
    specs = [("fixed_2", "fixed $2", PATH, (6, 5), None),
             ("fixed_10", "fixed $10", HILITE, None, None),
             ("atr_0.30", "0.30 x ATR", UP, (-8, -13), "both")]
    xs = np.linspace(0, 1, 501)
    for key, name, col, off, tag in specs:
        v = np.sort(pd.read_parquet(RES / f"overshoot_{key}.parquet").over_bricks.values)
        if len(v) != int(oq.loc[key].events):
            print("WARNING: parquet rows != events for", key, len(v), oq.loc[key].events)
        exc = 1.0 - np.searchsorted(v, xs, side="right") / len(v)
        exc = np.where(exc <= 0, np.nan, exc)
        ax.plot(xs, exc, color=col, lw=1.7, label=f"{name} ({len(v):,} closing ticks)", zorder=5)
        e5 = (v > 0.5).mean()
        ax.scatter([0.5], [e5], color=col, s=22, zorder=7, edgecolor="white", lw=0.6)
        if off is not None:
            lab = f"{100 * e5:.1f}%" + ("  ($10 and 0.30 x ATR)" if tag else "")
            ax.annotate(lab, xy=(0.5, e5), xytext=off, textcoords="offset points", fontsize=7.5,
                        color=TEXT if tag else col, fontweight="bold", ha="right" if tag else "left")
    ax.axvline(0.5, color=REF, lw=0.8, ls=(0, (4, 3)), zorder=2)
    ax.text(0.505, 1.4e-4, "half a brick", fontsize=7.5, color=REF, ha="left", va="bottom")
    ax.set_yscale("log")
    ax.set_xlim(0, 1.0)
    ax.set_ylim(1e-4, 1.5)
    ax.yaxis.set_major_locator(FixedLocator([1e-4, 1e-3, 1e-2, 1e-1, 1]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{100 * x:g}%"))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel("Overshoot x = |trigger price - last brick close| (in bricks)")
    ax.set_ylabel("Closing ticks with overshoot > x")
    ax.legend(loc="upper right", frameon=False, fontsize=7.5, handlelength=1.6, borderaxespad=0.2)
    put_source(fig, SRC + ".", h)
    save(fig, "f5_overshoot_distribution.png")


# ---------------------------------------------------------------------------
# f6 - pipeline diagram
# ---------------------------------------------------------------------------
def box(ax, x, y, w, hh, text, fc=NEUTRAL, ec=REF, fs=7.5, bold_first=True, tc=TEXT, lw=1.0):
    ax.add_patch(FancyBboxPatch((x, y), w, hh, boxstyle="round,pad=0,rounding_size=0.06", facecolor=fc,
                                edgecolor=ec, lw=lw, zorder=3))
    lines = text.split("\n")
    n = len(lines)
    lh = fs * 1.5 / 72
    y0 = y + hh / 2 + (n - 1) * lh / 2
    for i, ln in enumerate(lines):
        ax.text(x + w / 2, y0 - i * lh, ln, ha="center", va="center", fontsize=fs, color=tc,
                fontweight="bold" if (i == 0 and bold_first) else "normal", zorder=5)


def arr(ax, p0, p1, color=PATH, lw=1.3):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>", color=color, lw=lw, mutation_scale=8,
                                 shrinkA=0, shrinkB=0, zorder=6))


def fig6():
    h = 3.7
    fig = new_fig(h)
    put_title(fig, [f"One pass over {N_TICKS / 1e6:.1f}M ticks feeds all 25 brick",
                    "sizes at once, each with its own engine"], h)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, h)
    ax.axis("off")
    r1y, r1h = 2.32, 0.66
    mid = r1y + r1h / 2
    box(ax, 0.12, r1y, 1.30, r1h, "Tick CSV\n27 GB, UTC\nDateTime,Bid,Ask", fs=7.2)
    box(ax, 1.72, r1y, 1.46, r1h, "CTickCsvReader\n64 MB binary chunks\nbytes parsed by hand", fs=7.2)
    box(ax, 3.50, r1y, 1.38, r1h, "Tick filter\nbad bid/ask, time order,\nspread > 25 x running mean", fs=6.6)
    arr(ax, (1.42, mid), (1.72, mid))
    arr(ax, (3.18, mid), (3.50, mid))
    r2y, r2h = 0.95, 1.15
    box(ax, 0.12, r2y, 1.55, r2h, "CDailyRangeTracker\ndays 22:00-22:00 UTC\nprior-quarter ATR\n(completed days only)", fs=7.0)
    sx, sw = 2.12, 2.76
    ax.add_patch(FancyBboxPatch((sx, r2y), sw, r2h, boxstyle="round,pad=0,rounding_size=0.06", facecolor="white",
                                edgecolor=PATH, lw=1.2, zorder=2))
    ax.text(sx + sw / 2, r2y + r2h - 0.13, "25 x CSweepSlot", ha="center", va="center", fontsize=7.2,
            fontweight="bold", zorder=5)
    ax.text(sx + sw / 2, r2y + r2h - 0.32, "each owns a CRenkoEngine, bricks on bid", ha="center", va="center",
            fontsize=6.8, color=REF, zorder=5)
    box(ax, sx + 0.14, r2y + 0.38, sw - 0.28, 0.27, "16 fixed sizes: $0.50 ... $50", fs=7.0, bold_first=False)
    box(ax, sx + 0.14, r2y + 0.07, sw - 0.28, 0.27, "9 ATR sizes: 0.05 ... 1.00 x ATR", fs=7.0, bold_first=False)
    by = 2.20
    ax.plot([4.26, 4.26], [r1y, by], color=PATH, lw=1.3, zorder=6)
    ax.plot([0.9, 4.26], [by, by], color=PATH, lw=1.3, zorder=6)
    arr(ax, (0.9, by), (0.9, r2y + r2h))
    arr(ax, (3.5, by), (3.5, r2y + r2h))
    ax.text(2.5, by + 0.03, "each accepted tick", fontsize=6.8, color=REF, ha="center", va="bottom")
    arr(ax, (1.67, r2y + r2h / 2), (sx, r2y + r2h / 2), color=HILITE)
    ax.text(1.895, r2y + r2h / 2 + 0.05, "SetAtr()", fontsize=6.0, color=HILITE, ha="center", va="bottom",
            fontweight="bold")
    r3y, r3h = 0.22, 0.52
    box(ax, 0.12, r3y, 3.0, r3h, "Per-year accumulators\ncost | edge | net (next-tick fills at bid/ask)", fs=7.0)
    box(ax, 3.45, r3y, 1.43, r3h, "summary.csv\ndataset.csv", fs=7.0, fc="white", ec=PATH, bold_first=False)
    arr(ax, (3.0, r2y), (3.0, r3y + r3h))
    arr(ax, (1.0, r2y), (1.0, r3y + r3h))
    ax.text(1.06, (r2y + r3y + r3h) / 2, "day totals", fontsize=6.3, color=REF, va="center")
    arr(ax, (3.12, r3y + r3h / 2), (3.45, r3y + r3h / 2))
    put_source(fig, "Structure of RenkoSweep.mq5 and RenkoSweep.mqh.", h, y=0.04)
    save(fig, "f6_sweep_pipeline.png")


# ---------------------------------------------------------------------------
# f7 - effect of the bad-quote filter on phantom bricks
# ---------------------------------------------------------------------------
def fig7():
    h = 3.45
    d = fe[fe.label.str.startswith("$")].copy()
    d["size"] = d.label.str.replace("$", "", regex=False).astype(float)
    g = lambda lab, c: float(d[np.isclose(d["size"], lab)][c].iloc[0])
    fig = new_fig(h)
    put_title(fig, [f"Rejected quotes made up {g(20, 'phantom_from_bad_quotes_pct'):.0f}% of raw phantom bricks",
                    f"at $20 and {g(5, 'phantom_from_bad_quotes_pct'):.0f}% at $5"], h)
    ax = fig.add_axes(rect(h, 0.62, 0.70, 4.25, 2.15))
    style_axes(ax)
    x = d["size"].values
    ax.fill_between(x, d.phantom_pct.values, d.phantom_pct_raw.values, color=HILITE, alpha=0.22, lw=0, zorder=2)
    ax.plot(x, d.phantom_pct_raw.values, color=REF, lw=1.6, ls=(0, (4, 2)), marker="o", ms=3.2, zorder=4,
            label="raw ticks")
    ax.plot(x, d.phantom_pct.values, color=HILITE, lw=1.8, marker="o", ms=3.6, zorder=5,
            label="after the spread filter")
    log_x_sizes(ax)
    ax.set_ylim(0, d.phantom_pct_raw.max() * 1.12)
    ax.set_ylabel("Phantom bricks (% of bricks)")
    ax.legend(loc="upper right", frameon=False, fontsize=7.5, handlelength=2.0, borderaxespad=0.2)
    top = d.phantom_pct_raw.max()
    ax.annotate(f"$20: {g(20, 'phantom_pct_raw'):.2f}% to {g(20, 'phantom_pct'):.2f}%",
                xy=(20, g(20, 'phantom_pct_raw')), xytext=(8.5, top * 0.55), fontsize=7.5, color=TEXT,
                arrowprops=dict(arrowstyle="-", color=REF, lw=0.7, shrinkA=2, shrinkB=3))
    ax.annotate(f"$50: {g(50, 'phantom_pct_raw'):.2f}% to {g(50, 'phantom_pct'):.2f}%",
                xy=(50, g(50, 'phantom_pct_raw')), xytext=(10.5, top * 0.30), fontsize=7.5, color=TEXT,
                arrowprops=dict(arrowstyle="-", color=REF, lw=0.7, shrinkA=2, shrinkB=3))
    put_source(fig, SRC + ". Fixed bricks.", h)
    save(fig, "f7_filter_effect.png")


if __name__ == "__main__":
    fig1()
    fig2()
    fig3()
    fig4()
    fig5()
    fig6()
    fig7()
