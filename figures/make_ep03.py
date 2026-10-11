"""Figures for Part 3: Do Renko Bricks Have Memory? A Random-Walk Test.

Run:  python make_ep03.py   (writes figures/ep03/*.png, 750 px wide, STYLE.md colours)
Reads results/ep03/*.csv. Nothing is re-simulated.
"""
import math
import os
from statistics import NormalDist

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
from matplotlib.lines import Line2D
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ep03")
RES = os.path.join(HERE, "..", "results", "ep03")
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
    "legend.fontsize": 8,
    "figure.dpi": 150,
    "savefig.dpi": 150,
    "axes.edgecolor": REF,
    "axes.labelcolor": INK,
    "xtick.color": INK,
    "ytick.color": INK,
})
W_IN = 5.0
DPI = 150
SRC_XAU = "XAUUSD ticks 2017-10 to 2026-09-02, Python port of RenkoSweep"
BONF_Z = NormalDist().inv_cdf(1 - 0.05 / 25 / 2)   # 25 sizes, two-sided 5 %: 3.09
HEAT_MIN_RUNS = 50                                  # cells with fewer runs are hatched


# ------------------------------------------------------------------ helpers
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


def tint(hexcol, alpha):
    h = hexcol.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02X%02X%02X" % tuple(round(255 - (255 - c) * alpha) for c in (r, g, b))


def title_lines(text):
    return wrap(text, W_IN - 0.3, 11, "bold")


def put_title(fig, h_in, text):
    """Finding-style title, left aligned, wrapped. Returns its height in inches."""
    lines = title_lines(text)
    y = h_in - 0.1
    for ln in lines:
        fig.text(0.15 / W_IN, y / h_in, ln, fontsize=11, fontweight="bold", color=INK, ha="left", va="top")
        y -= 0.19
    return 0.1 + 0.19 * len(lines) + 0.06


def put_source(fig, h_in, text):
    fig.text(0.15 / W_IN, 0.12 / h_in, text, fontsize=6.5, color=FORM, ha="left", va="center")


def style_ax(ax, axis="y"):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(REF)
    ax.spines["bottom"].set_color(REF)
    if axis == "y":
        ax.yaxis.grid(True, color=GRID, lw=0.8)
        ax.xaxis.grid(False)
    else:
        ax.xaxis.grid(True, color=GRID, lw=0.8)
        ax.yaxis.grid(False)
    ax.set_axisbelow(True)
    ax.tick_params(length=3, color=REF)


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=DPI, bbox_inches=None, facecolor="white")
    plt.close(fig)
    im = Image.open(path).convert("RGB")
    if os.path.getsize(path) > 200 * 1024:
        im = im.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    im.save(path, optimize=True)
    im = Image.open(path)
    print(name, im.size, round(os.path.getsize(path) / 1024, 1), "KB")
    assert im.size[0] == 750, "width must be exactly 750"
    assert os.path.getsize(path) < 300 * 1024


def fmt_size(label):
    return label.replace("xATR", "×ATR")


# ------------------------------------------------------------------ data
bysize = pd.read_csv(os.path.join(RES, "runs_by_size.csv"))
byyear = pd.read_csv(os.path.join(RES, "runs_by_year.csv"))
geo = pd.read_csv(os.path.join(RES, "geometric_expected.csv"))
updown = pd.read_csv(os.path.join(RES, "updown_by_year.csv"))
cross = pd.read_csv(os.path.join(RES, "cross_market.csv"))
assert len(bysize) == 25
bysize["sig"] = bysize["z"].abs() > BONF_Z


# ------------------------------------------------------------------ Figure 1
def figure1():
    H = 4.3
    fig = plt.figure(figsize=(W_IN, H), dpi=DPI, facecolor="white")
    put_title(fig, H, "From the last close, a driftless walk continues with probability 2/3 and runs average 3 bricks")

    # --- left: ladder
    axl = fig.add_axes([0.04, 0.27, 0.36, 0.52])
    axl.set_xlim(0, 1)
    axl.set_ylim(-3.0, 2.0)
    axl.axis("off")
    axl.add_patch(Rectangle((0.0, -2), 1.0, 3, fc=NEUT, ec="none", zorder=0))
    axl.plot([0, 1], [1, 1], color=UP, lw=1.6, zorder=2)
    axl.plot([0, 1], [-2, -2], color=DN, lw=1.6, zorder=2)
    axl.plot([0, 1], [0, 0], color=REF, lw=1.0, ls="--", zorder=2)
    px = np.linspace(0.05, 0.9, 9)
    py = [0, -0.7, 0.35, -0.5, -1.25, -0.55, 0.3, -0.2, 1.0]
    axl.plot(px, py, color=PATH, lw=1.2, zorder=3)
    axl.plot(px[0], py[0], "o", color=PATH, ms=3.5, zorder=4)
    axl.plot(px[-1], py[-1], "o", color=UP_E, ms=4, zorder=4)
    axl.text(1.04, 1, "+1 brick", color=UP_E, fontsize=8, va="center", ha="left", fontweight="bold")
    axl.text(1.04, 0, "last close", color=REF, fontsize=8, va="center", ha="left")
    axl.text(1.04, -2, "\u22122 bricks", color=DN_E, fontsize=8, va="center", ha="left", fontweight="bold")
    axl.text(0.5, 1.5, "continue: up brick\np = 2/3", color=UP_E, fontsize=8, ha="center", va="center", fontweight="bold")
    axl.text(0.5, -2.5, "reverse: down brick\nq = 1/3", color=DN_E, fontsize=8, ha="center", va="center", fontweight="bold")
    axl.text(0.5, -1.7, "dead zone: no brick", color=REF, fontsize=7.5, ha="center", va="center")

    # --- right: geometric distribution
    axr = fig.add_axes([0.665, 0.27, 0.315, 0.46])
    k = np.arange(1, 10)
    pk = (2 / 3) ** (k - 1) * (1 / 3) * 100
    axr.bar(k, pk, color=tint(PATH, 0.55), ec=PATH, lw=0.6, width=0.75, zorder=2)
    axr.axvline(3.0, color=HI, lw=1.4, zorder=3)
    axr.text(3.3, 31, "mean 3", color=HI, fontsize=8, fontweight="bold", va="center", ha="left")
    axr.set_xticks(k)
    axr.set_xlabel("Run length L (bricks)")
    axr.set_ylabel("P(L = k), %")
    axr.set_ylim(0, 36)
    axr.set_xlim(0.4, 9.6)
    style_ax(axr, "y")
    fig.text(0.665 + 0.315 / 2, 0.27 + 0.46 + 0.07, "P(L=k) = (2/3)^(k\u22121) \u00d7 (1/3)\nsd = 2.45",
             fontsize=7.5, color=INK, ha="center", va="center", linespacing=1.2)

    # --- bottom: flip-follow bookkeeping
    bx = fig.add_axes([0.03, 0.035, 0.94, 0.12])
    bx.set_xlim(0, 1)
    bx.set_ylim(0, 1)
    bx.axis("off")
    bx.add_patch(FancyBboxPatch((0.0, 0.02), 1.0, 0.96, boxstyle="round,pad=0,rounding_size=0.03",
                                fc=tint(HI, 0.12), ec=HI, lw=0.8))
    bx.text(0.5, 0.70, "Flip-follow gains L\u22121 bricks along the run and loses 2 at the reversal.",
            fontsize=8, color=INK, ha="center", va="center")
    bx.text(0.5, 0.28, "Per run: L \u2212 3.   With mean run 3, the mean is 0.", fontsize=8, color=INK,
            ha="center", va="center", fontweight="bold")
    save(fig, "f1_random_walk_derivation.png")


# ------------------------------------------------------------------ Figure 2
def figure2():
    fx = bysize[bysize.kind == "fixed"].copy()
    at = bysize[bysize.kind == "atr"].copy()
    n_sig = int(bysize.sig.sum())
    H = 3.7
    fig = plt.figure(figsize=(W_IN, H), dpi=DPI, facecolor="white")
    title = "Small fixed bricks average above 3; from 0.10×ATR up, only 1.00×ATR passes Bonferroni"
    put_title(fig, H, title)
    top = 0.80
    bot = 0.24
    axa = fig.add_axes([0.095, bot, 0.46, top - bot])
    axb = fig.add_axes([0.63, bot, 0.35, top - bot], sharey=axa)

    ymin, ymax = 2.55, 4.0
    for ax, df, xs, xlog in ((axa, fx, fx.avg_brick.values, True), (axb, at, at.param.values, True)):
        base = df[~df.sig]
        sig = df[df.sig]
        xcol = "avg_brick" if ax is axa else "param"
        ax.axhline(3.0, color=REF, lw=1.0, ls="--", zorder=1)
        ax.errorbar(base[xcol], base.mean_run_len, yerr=base.two_se, fmt="o", color=PATH, ecolor=FORM,
                    elinewidth=1.0, capsize=2, ms=3.6, zorder=3)
        ax.errorbar(sig[xcol], sig.mean_run_len, yerr=sig.two_se, fmt="o", color=HI, ecolor=HI,
                    mec=INK, mew=0.5, elinewidth=1.0, capsize=2, ms=5.2, zorder=4)
        if xlog:
            ax.set_xscale("log")
        style_ax(ax, "y")
        ax.set_ylim(ymin, ymax)
    axa.set_xticks([0.5, 1, 2, 5, 10, 20, 50])
    axa.set_xticklabels(["0.5", "1", "2", "5", "10", "20", "50"])
    axa.minorticks_off()
    axa.set_xlabel("Fixed brick size ($ per oz)")
    axa.set_ylabel("Mean run length ± 2 SE (bricks)")
    axb.set_xticks([0.05, 0.1, 0.2, 0.5, 1.0])
    axb.set_xticklabels(["0.05", "0.1", "0.2", "0.5", "1.0"])
    axb.minorticks_off()
    axb.set_xlabel("Brick size (× quarterly ATR)")
    plt.setp(axb.get_yticklabels(), visible=False)
    axa.text(0.03, 0.96, "Fixed $ bricks", transform=axa.transAxes, fontsize=8, fontweight="bold", color=INK,
             va="top")
    axb.text(0.05, 0.96, "ATR bricks", transform=axb.transAxes, fontsize=8, fontweight="bold", color=INK, va="top")
    axa.text(0.03, 2.97, "random walk: 3.0", transform=axa.get_yaxis_transform(), fontsize=7.5, color=REF,
             ha="left", va="top")
    # legend row
    handles = [Line2D([], [], marker="o", color=HI, mec=INK, mew=0.5, ls="none", ms=5.2,
                      label=f"|z| > {BONF_Z:.2f} (Bonferroni, 25 sizes)"),
               Line2D([], [], marker="o", color=PATH, ls="none", ms=3.6, label="not significant")]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.05), ncol=2, frameon=False,
               fontsize=7.5, handletextpad=0.3, columnspacing=1.4)
    put_source(fig, H, SRC_XAU + ". Bars are ±2 SE.")
    save(fig, "f2_mean_run_by_size.png")
    print("  significant points:", ", ".join(bysize[bysize.sig].label), f"({n_sig})")


# ------------------------------------------------------------------ Figure 3
def figure3():
    cats = ["1", "2", "3", "4–5", "6–9", "10–19", "20+"]
    cols = ["run1_pct", "run2_pct", "run3_pct", "run4_5_pct", "run6_9_pct", "run10_19_pct", "run20p_pct"]
    exp = geo.expected_pct.values
    H = 3.45
    fig = plt.figure(figsize=(W_IN, H), dpi=DPI, facecolor="white")
    gap = max(np.abs(bysize[bysize.label == lab][cols].values.astype(float)[0] - exp).max() for lab in ("$5.00", "0.30xATR"))
    gap_txt = f"{math.ceil(gap * 2) / 2:g}"
    put_title(fig, H, f"Run-length shares stay within {gap_txt} points of the geometric curve in every bucket, at both sizes")
    top, bot = 0.82, 0.27
    axs = []
    picks = [("$5.00", "$5 bricks"), ("0.30xATR", "0.30×ATR bricks")]
    maxdiff = 0
    for i, (lab, name) in enumerate(picks):
        ax = fig.add_axes([0.10 + i * 0.465, bot, 0.43, top - bot], sharey=axs[0] if axs else None)
        row = bysize[bysize.label == lab].iloc[0]
        obs = row[cols].values.astype(float)
        maxdiff = max(maxdiff, np.abs(obs - exp).max())
        x = np.arange(len(cats))
        ax.bar(x - 0.19, exp, width=0.36, color=NEUT, ec=REF, lw=0.7, zorder=2, label="random walk")
        ax.bar(x + 0.19, obs, width=0.36, color=tint(PATH, 0.85), ec=PATH, lw=0.5, zorder=2, label="observed")
        ax.set_xticks(x)
        ax.set_xticklabels(cats, fontsize=6.3)
        ax.set_xlabel("Run length (bricks)")
        style_ax(ax, "y")
        ax.set_ylim(0, 38)
        ax.text(0.97, 0.96, f"{name}\n{int(row.runs):,} runs\nmean {row.mean_run_len:.3f}", transform=ax.transAxes,
                fontsize=7.5, va="top", ha="right", color=INK)
        if i == 0:
            ax.set_ylabel("Share of runs (%)")
        else:
            plt.setp(ax.get_yticklabels(), visible=False)
        axs.append(ax)
    handles = [Rectangle((0, 0), 1, 1, fc=NEUT, ec=REF, lw=0.7), Rectangle((0, 0), 1, 1, fc=tint(PATH, 0.85), ec=PATH, lw=0.5)]
    fig.legend(handles, ["random walk (geometric)", "observed"], loc="lower center", bbox_to_anchor=(0.5, 0.05),
               ncol=2, frameon=False, fontsize=7.5, handletextpad=0.4, columnspacing=1.4)
    put_source(fig, H, SRC_XAU)
    save(fig, "f3_run_histogram_vs_geometric.png")
    print(f"  largest bucket gap: {maxdiff:.2f} points")


# ------------------------------------------------------------------ Figure 4
def figure4():
    order = ["fixed_2", "fixed_5", "fixed_10", "fixed_20", "fixed_50",
             "atr_0.10", "atr_0.20", "atr_0.30", "atr_0.50", "atr_1.00"]
    names = {"fixed_2": "$2", "fixed_5": "$5", "fixed_10": "$10", "fixed_20": "$20", "fixed_50": "$50",
             "atr_0.10": "0.10×ATR", "atr_0.20": "0.20×ATR", "atr_0.30": "0.30×ATR",
             "atr_0.50": "0.50×ATR", "atr_1.00": "1.00×ATR"}
    rows = updown[updown.year == "ALL"].set_index("label").loc[order]
    all_up = bool((rows.up_mean > rows.down_mean).all())
    all_lower = bool((rows.mean_ex_phantom <= rows["mean"] + 1e-9).all())
    print("  up>down at every dumped size:", all_up, "; ex-phantom below mean at every size:", all_lower)
    assert all_up and all_lower
    H = 4.35
    fig = plt.figure(figsize=(W_IN, H), dpi=DPI, facecolor="white")
    put_title(fig, H, "Up runs beat down runs at all ten sizes tested; removing gap bricks never raises a mean")
    ax = fig.add_axes([0.20, 0.23, 0.69, 0.60])
    y = np.arange(len(order))[::-1].astype(float)
    # split the fixed and ATR groups with a gap
    y = np.array([9.6, 8.6, 7.6, 6.6, 5.6, 3.9, 2.9, 1.9, 0.9, -0.1])
    ax.axvline(3.0, color=REF, lw=1.0, ls="--", zorder=1)
    for yi, (lab, r) in zip(y, rows.iterrows()):
        ax.plot([r.down_mean, r.up_mean], [yi, yi], color=FORM, lw=1.6, zorder=2, solid_capstyle="round")
    ax.scatter(rows.up_mean, y, s=34, color=UP, ec=UP_E, lw=0.6, zorder=4, label="up runs")
    ax.scatter(rows.down_mean, y, s=34, color=DN, ec=DN_E, lw=0.6, zorder=4, label="down runs")
    ax.scatter(rows["mean"], y, s=16, marker="|", color=INK, linewidths=1.2, zorder=5, label="all runs")
    ax.scatter(rows.mean_ex_phantom, y, s=40, marker="D", color=HI, ec=INK, lw=0.5, zorder=5,
               label="all runs, gap bricks removed")
    ax.set_yticks(y)
    ax.set_yticklabels([names[k] for k in order])
    ax.set_xlim(2.7, 4.1)
    ax.set_ylim(-0.7, 10.7)
    ax.set_xlabel("Mean run length (bricks)")
    style_ax(ax, "x")
    ax.text(3.0 + 0.012, 10.45, "random walk: 3.0", fontsize=7.5, color=REF, va="center", ha="left")
    # run counts as small grey text to the right of each row
    for yi, (lab, r) in zip(y, rows.iterrows()):
        ax.text(1.02, yi, f"{int(r.up_runs + r.down_runs):,}", transform=ax.get_yaxis_transform(), fontsize=7,
                color=REF, va="center", ha="left")
    ax.text(1.02, 10.45, "runs", transform=ax.get_yaxis_transform(), fontsize=7, color=REF, va="center", ha="left")
    handles = [
        Line2D([], [], marker="o", color=UP, mec=UP_E, ls="none", ms=5.5, label="up runs"),
        Line2D([], [], marker="o", color=DN, mec=DN_E, ls="none", ms=5.5, label="down runs"),
        Line2D([], [], marker="|", color=INK, ls="none", ms=7, mew=1.2, label="all runs"),
        Line2D([], [], marker="D", color=HI, mec=INK, mew=0.5, ls="none", ms=5, label="all runs, gap bricks removed"),
    ]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.045), ncol=4, frameon=False,
               fontsize=7, handletextpad=0.2, columnspacing=0.9)
    put_source(fig, H, SRC_XAU + " (brick-level dumps)")
    save(fig, "f4_up_vs_down_runs.png")


# ------------------------------------------------------------------ Figure 5
def figure5():
    order = list(bysize.label)                     # 16 fixed, then 9 ATR (file order)
    years = sorted(byyear.year.unique())
    mean = np.full((len(order), len(years)), np.nan)
    cnt = np.zeros((len(order), len(years)), dtype=int)
    for _, r in byyear.iterrows():
        i = order.index(r.label)
        j = years.index(r.year)
        if r.runs > 0:
            mean[i, j] = r.mean_run_len
            cnt[i, j] = r.runs
    cmap = LinearSegmentedColormap.from_list("rk", [DN, "#FFFFFF", UP])
    norm = Normalize(vmin=2.5, vmax=3.5)
    # gap row between fixed and ATR blocks
    nrow = len(order)
    H = 5.75
    fig = plt.figure(figsize=(W_IN, H), dpi=DPI, facecolor="white")
    put_title(fig, H, "Mean runs sit near 3 most years: long at small fixed sizes in 2026, short in 2020")
    ax = fig.add_axes([0.17, 0.115, 0.66, 0.735])
    ypos = np.array([i if i < 16 else i + 0.6 for i in range(nrow)], dtype=float)
    for i in range(nrow):
        for j in range(len(years)):
            m = mean[i, j]
            y0 = ypos[i]
            if np.isnan(m):
                ax.add_patch(Rectangle((j - 0.5, y0 - 0.5), 1, 1, fc=NEUT, ec="white", lw=0.5, zorder=2))
                continue
            fc = cmap(norm(m))
            few = cnt[i, j] < HEAT_MIN_RUNS
            if few:
                ax.add_patch(Rectangle((j - 0.5, y0 - 0.5), 1, 1, fc="#F4F5F7", ec=FORM, lw=0, hatch="////", zorder=2))
            else:
                ax.add_patch(Rectangle((j - 0.5, y0 - 0.5), 1, 1, fc=fc, ec="white", lw=0.5, zorder=2))
    ax.set_xlim(-0.5, len(years) - 0.5)
    ax.set_ylim(ypos[-1] + 0.5, -0.5)
    ax.set_xticks(range(len(years)))
    ax.set_xticklabels([str(y) for y in years], rotation=0, fontsize=7)
    ax.xaxis.tick_top()
    ax.tick_params(axis="x", length=0, pad=2)
    ax.set_yticks(ypos)
    ax.set_yticklabels([fmt_size(l) for l in order], fontsize=7)
    ax.tick_params(axis="y", length=0, pad=2)
    for s in ax.spines.values():
        s.set_visible(False)
    plt.rcParams["hatch.linewidth"] = 0.5
    # colourbar
    cax = fig.add_axes([0.87, 0.115, 0.025, 0.735])
    grad = np.linspace(3.5, 2.5, 256).reshape(-1, 1)
    cax.imshow(grad, aspect="auto", cmap=cmap, norm=norm, extent=[0, 1, 2.5, 3.5])
    cax.set_xticks([])
    cax.yaxis.tick_right()
    cax.set_yticks([2.5, 3.0, 3.5])
    cax.set_yticklabels(["≤2.5", "3.0", "≥3.5"], fontsize=7)
    cax.tick_params(length=2, color=REF)
    for s in cax.spines.values():
        s.set_visible(False)
    fig.text(0.885, 0.115 + 0.735 + 0.012, "mean\nrun", fontsize=7, color=INK, ha="center", va="bottom", linespacing=0.9)
    # legend for hatch
    fig.patches.append(Rectangle((0.17, 0.052), 0.022, 0.016, transform=fig.transFigure, fc="#F4F5F7", ec=FORM,
                                 hatch="////", lw=0.5))
    fig.text(0.2, 0.060, f"fewer than {HEAT_MIN_RUNS} runs that year (SE above {math.sqrt(6)/math.sqrt(HEAT_MIN_RUNS):.2f}); plain grey: no runs",
             fontsize=7, color=INK, va="center", ha="left")
    put_source(fig, H, SRC_XAU + ". 2026 is partial (to 2 Sep).")
    save(fig, "f5_mean_run_heatmap.png")


# ------------------------------------------------------------------ Figure 6
def figure6():
    n_tests = len(cross)
    z_line = NormalDist().inv_cdf(1 - 0.05 / n_tests / 2)
    zmax = cross.z.abs().max()
    H = 3.7
    fig = plt.figure(figsize=(W_IN, H), dpi=DPI, facecolor="white")
    ze = cross[cross.symbol == "EURUSD"].z.abs().max()
    zu = cross[cross.symbol == "US500"].z.abs().max()
    put_title(fig, H, f"May to Sep 2026: EURUSD sizes sit within {ze:.1f} SE of 3.0 and US500 within {zu:.1f} SE")
    top, bot = 0.785, 0.27
    axs = []
    for i, sym in enumerate(("EURUSD", "US500")):
        ax = fig.add_axes([0.095 + i * 0.475, bot, 0.41, top - bot], sharey=axs[0] if axs else None)
        d = cross[cross.symbol == sym].reset_index(drop=True)
        x = np.arange(len(d))
        ax.axhline(3.0, color=REF, lw=1.0, ls="--", zorder=1)
        ax.errorbar(x, d.mean_run_len, yerr=d.two_se, fmt="o", color=PATH, ecolor=FORM, elinewidth=1.0, capsize=2,
                    ms=3.8, zorder=3)
        out = d[d.z.abs() > 1.96]
        if len(out):
            ax.errorbar(out.index.values, out.mean_run_len, yerr=out.two_se, fmt="o", color=HI, ecolor=HI, mec=INK,
                        mew=0.5, elinewidth=1.0, capsize=2, ms=5, zorder=4)
        ax.set_xticks(x)
        ax.set_xticklabels([f"{a:g}" for a in d.atr_fraction], fontsize=7)
        for xi, n in zip(x, d.runs):
            ax.text(xi, 1.015, f"{int(n)}", transform=ax.get_xaxis_transform(), fontsize=6.3, color=REF, ha="center", va="bottom")
        ax.set_xlim(-0.6, len(d) - 0.4)
        ax.set_ylim(0.8, 5.3)
        style_ax(ax, "y")
        ax.text(0.04, 0.96, sym, transform=ax.transAxes, fontsize=8.5, fontweight="bold", color=INK, va="top")
        if i == 0:
            ax.set_ylabel("Mean run length ± 2 SE (bricks)")
        else:
            plt.setp(ax.get_yticklabels(), visible=False)
        axs.append(ax)
    fig.text(0.5, 0.115, "Brick size, fraction of April 2026 average daily range (runs at top)",
             fontsize=7.5, color=INK, ha="center", va="center")
    handles = [Line2D([], [], marker="o", color=HI, mec=INK, mew=0.5, ls="none", ms=5, label="|z| > 1.96"),
               Line2D([], [], marker="o", color=PATH, ls="none", ms=3.8, label="|z| ≤ 1.96")]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.045), ncol=2, frameon=False, fontsize=7.5,
               handletextpad=0.3, columnspacing=1.4)
    put_source(fig, H, "EURUSD and US500 tick history, IC Markets demo terminal, 2026-05 to 2026-09. Bars cut at the axis.")
    save(fig, "f6_cross_market.png")
    print(f"  cross-market: {n_tests} tests, Bonferroni z = {z_line:.2f}, max |z| = {zmax:.2f}")


if __name__ == "__main__":
    print(f"Bonferroni z (25 sizes): {BONF_Z:.3f}")
    figure1()
    figure2()
    figure3()
    figure4()
    figure5()
    figure6()
