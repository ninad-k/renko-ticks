"""numba port of mql5/Scripts/Renko/RenkoSweep.mq5 + Include/Renko/RenkoSweep.mqh.

One pass over a tick CSV, every brick size at once, the same accumulators
and the same CSV layout as the MQL5 script. Use it for runs too large to
babysit in the terminal; rerun RenkoSweep.mq5 to confirm anything you publish.

    python renko_sweep.py <ticks.csv> <out_prefix>
"""

from __future__ import annotations

import sys
import time

import numba as nb
import numpy as np
import polars as pl
import pyarrow as pa
import pyarrow.csv as pacsv

FIXED = [0.5, 1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50]
ATR_FRACTIONS = [0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.75, 1.00]
IMPULSE_MIN, PULLBACK_MAX = 3, 2
COMMISSION_SIDE = 0.035
LATENCY_MS = 0
SPREAD_MULT = 25.0      # reject a tick whose spread > SPREAD_MULT x running mean spread (0 = off)
SPREAD_EMA_ALPHA = 1.0 / 1000
RING = 64  # unused by the port (only the last brick is read), kept for parity

YEAR0, YEARS = 2000, 64
TOTAL = YEARS
NHIST = 7
EPS_REL = 1e-6

# ---- per-slot engine/strategy state: float64 columns -----------------------
(E_BRICK, E_EPS, E_ANCHOR, E_UP, E_DN, E_LASTCLOSE, E_LASTSIZE, E_LASTTRIG, E_LASTSPREAD,
 S_PARAM) = range(10)
NF = 10
# ---- per-slot int64 columns -------------------------------------------------
(I_ATRMODE, I_ACTIVE, I_STARTED, I_K, I_DIR, I_RUN, I_TOTAL, I_PREVCLOSE_T, I_PREVRUN,
 I_HASPEND, I_NOTBEFORE) = range(11)
NI = 11
# ---- per-slot per-strategy state -------------------------------------------
P_POSDIR, P_PENDEXIT, P_PENDENTRYDIR = range(3)              # int
Q_ENTRYREAL, Q_ENTRYTHEO, Q_PENDEXITTHEO, Q_PENDENTRYTHEO = range(4)  # float

# ---- accumulators: acc[slot, year_idx, field] (float64) ---------------------
(A_BRICKS, A_UP, A_FLIPS, A_PHANTOM, A_SUBSEC, A_EVENTS, A_SIZE, A_SPREAD, A_OVER, A_OVERMAX,
 A_RUNS, A_RUNSUM, A_RUNMAX) = range(13)
A_HIST = 13                       # 7 buckets
A_STRAT = A_HIST + NHIST          # per strategy: trades, wins, theo, net, gprofit, gloss, eq, peak, mdd
(T_TRADES, T_WINS, T_THEO, T_NET, T_GP, T_GL, T_EQ, T_PEAK, T_MDD) = range(9)
NT = 9
NACC = A_STRAT + 2 * NT

# ---- global state: g[] float64, gi[] int64 ---------------------------------
(G_HI, G_LO, G_LAST, G_PREVCLOSE, G_QSUM, G_ATR, G_FINTR, G_PREVBID, G_SPREMA) = range(9)
(GI_DAY, GI_HASPREV, GI_QUARTER, GI_QN, GI_DAYYEAR, GI_FINYEAR, GI_LASTT, GI_BAD, GI_N, GI_SPRREJ) = range(10)
# dataset: data[year_idx, field]
D_TICKS, D_DAYS, D_TRDAYS, D_SPREAD, D_PATH, D_TRSUM = range(6)


@nb.njit(cache=True, inline="always")
def _yi(year):
    i = year - YEAR0
    if i < 0:
        return 0
    if i >= YEARS:
        return YEARS - 1
    return i


@nb.njit(cache=True)
def _update_levels(f, iv, s):
    k = iv[s, I_K]
    if iv[s, I_DIR] > 0:
        ku, kd = k + 1, k - 2
    else:
        ku, kd = k + 2, k - 1
    f[s, E_UP] = f[s, E_ANCHOR] + ku * f[s, E_BRICK] - f[s, E_EPS]
    f[s, E_DN] = f[s, E_ANCHOR] + kd * f[s, E_BRICK] + f[s, E_EPS]


@nb.njit(cache=True)
def _engine_init(f, iv, s, brick):
    f[s, E_BRICK] = brick
    f[s, E_EPS] = brick * EPS_REL
    f[s, E_ANCHOR] = 0.0
    iv[s, I_K] = 0
    iv[s, I_DIR] = 0
    iv[s, I_RUN] = 0
    iv[s, I_STARTED] = 0
    iv[s, I_TOTAL] = 0
    f[s, E_UP] = np.inf
    f[s, E_DN] = -np.inf


@nb.njit(cache=True)
def _set_brick_size(f, iv, s, brick):
    if iv[s, I_STARTED]:
        f[s, E_ANCHOR] = f[s, E_ANCHOR] + iv[s, I_K] * f[s, E_BRICK]
        iv[s, I_K] = 0
    f[s, E_BRICK] = brick
    f[s, E_EPS] = brick * EPS_REL
    if iv[s, I_STARTED]:
        _update_levels(f, iv, s)


@nb.njit(cache=True)
def _push(f, iv, s, d, k_close, p, spread):
    if d == iv[s, I_DIR]:
        iv[s, I_RUN] += 1
    else:
        iv[s, I_RUN] = 1
    iv[s, I_DIR] = d
    iv[s, I_K] = k_close
    iv[s, I_TOTAL] += 1
    f[s, E_LASTCLOSE] = f[s, E_ANCHOR] + k_close * f[s, E_BRICK]
    f[s, E_LASTSIZE] = f[s, E_BRICK]
    f[s, E_LASTTRIG] = p
    f[s, E_LASTSPREAD] = spread


@nb.njit(cache=True)
def _engine_tick(f, iv, s, bid, ask):
    p = bid
    if not iv[s, I_STARTED]:
        iv[s, I_K] = np.int64(np.floor(p / f[s, E_BRICK] + EPS_REL))
        iv[s, I_STARTED] = 1
        _update_levels(f, iv, s)
        return 0
    if p < f[s, E_UP] and p > f[s, E_DN]:
        return 0
    n = 0
    spread = ask - bid
    while True:
        if p >= f[s, E_UP]:
            ko = iv[s, I_K] if iv[s, I_DIR] > 0 else iv[s, I_K] + 1
            _push(f, iv, s, 1, ko + 1, p, spread)
        elif p <= f[s, E_DN]:
            ko = iv[s, I_K] - 1 if iv[s, I_DIR] > 0 else iv[s, I_K]
            _push(f, iv, s, -1, ko - 1, p, spread)
        else:
            break
        _update_levels(f, iv, s)
        n += 1
    return n


@nb.njit(cache=True)
def _add_run(acc, s, a, length):
    acc[s, a, A_RUNS] += 1
    acc[s, a, A_RUNSUM] += length
    if length > acc[s, a, A_RUNMAX]:
        acc[s, a, A_RUNMAX] = length
    if length <= 3:
        b = length - 1
    elif length <= 5:
        b = 3
    elif length <= 9:
        b = 4
    elif length <= 19:
        b = 5
    else:
        b = 6
    acc[s, a, A_HIST + b] += 1


@nb.njit(cache=True)
def _add_trade(acc, s, a, st, real, theo):
    o = A_STRAT + st * NT
    acc[s, a, o + T_TRADES] += 1
    if real > 0:
        acc[s, a, o + T_WINS] += 1
        acc[s, a, o + T_GP] += real
    else:
        acc[s, a, o + T_GL] -= real
    acc[s, a, o + T_THEO] += theo
    acc[s, a, o + T_NET] += real
    acc[s, a, o + T_EQ] += real
    if acc[s, a, o + T_EQ] > acc[s, a, o + T_PEAK]:
        acc[s, a, o + T_PEAK] = acc[s, a, o + T_EQ]
    dd = acc[s, a, o + T_PEAK] - acc[s, a, o + T_EQ]
    if dd > acc[s, a, o + T_MDD]:
        acc[s, a, o + T_MDD] = dd


@nb.njit(cache=True)
def _fill(iv, pi, pf, acc, s, yi, bid, ask, commission):
    for st in range(2):
        if pi[s, st, P_PENDEXIT] and pi[s, st, P_POSDIR] != 0:
            d = pi[s, st, P_POSDIR]
            px = bid if d > 0 else ask
            real = d * (px - pf[s, st, Q_ENTRYREAL]) - 2.0 * commission
            theo = d * (pf[s, st, Q_PENDEXITTHEO] - pf[s, st, Q_ENTRYTHEO])
            _add_trade(acc, s, yi, st, real, theo)
            _add_trade(acc, s, TOTAL, st, real, theo)
            pi[s, st, P_POSDIR] = 0
        pi[s, st, P_PENDEXIT] = 0
        if pi[s, st, P_PENDENTRYDIR] != 0:
            d = pi[s, st, P_PENDENTRYDIR]
            pi[s, st, P_POSDIR] = d
            pf[s, st, Q_ENTRYREAL] = ask if d > 0 else bid
            pf[s, st, Q_ENTRYTHEO] = pf[s, st, Q_PENDENTRYTHEO]
            pi[s, st, P_PENDENTRYDIR] = 0
    iv[s, I_HASPEND] = 0


@nb.njit(cache=True)
def _signal(pi, pf, s, st, d, theo, enter):
    if pi[s, st, P_POSDIR] != 0 and pi[s, st, P_POSDIR] != d and not pi[s, st, P_PENDEXIT]:
        pi[s, st, P_PENDEXIT] = 1
        pf[s, st, Q_PENDEXITTHEO] = theo
    pi[s, st, P_PENDENTRYDIR] = 0
    if enter:
        pi[s, st, P_PENDENTRYDIR] = d
        pf[s, st, Q_PENDENTRYTHEO] = theo


@nb.njit(cache=True)
def _on_bricks(f, iv, pi, pf, acc, s, n, dir_before, run_before, t, yi, impulse_min, pullback_max, latency):
    d = iv[s, I_DIR]
    size = f[s, E_LASTSIZE]
    last_close = f[s, E_LASTCLOSE]
    first_close = last_close - d * (n - 1) * size
    over = abs(f[s, E_LASTTRIG] - last_close)
    subsec = iv[s, I_PREVCLOSE_T] > 0 and t - iv[s, I_PREVCLOSE_T] < 1000
    turn = d != dir_before
    for pass_ in range(2):
        a = yi if pass_ == 0 else TOTAL
        acc[s, a, A_BRICKS] += n
        if d > 0:
            acc[s, a, A_UP] += n
        acc[s, a, A_PHANTOM] += n - 1
        acc[s, a, A_EVENTS] += 1
        acc[s, a, A_SIZE] += n * size
        acc[s, a, A_SPREAD] += f[s, E_LASTSPREAD]
        acc[s, a, A_OVER] += over
        if over > acc[s, a, A_OVERMAX]:
            acc[s, a, A_OVERMAX] = over
        if subsec:
            acc[s, a, A_SUBSEC] += 1
        if turn and dir_before != 0:
            acc[s, a, A_FLIPS] += 1
            _add_run(acc, s, a, run_before)
    iv[s, I_PREVCLOSE_T] = t
    if not turn:
        return
    _signal(pi, pf, s, 0, d, first_close, True)
    pattern = dir_before != 0 and iv[s, I_PREVRUN] >= impulse_min and run_before <= pullback_max
    _signal(pi, pf, s, 1, d, first_close, pattern)
    iv[s, I_PREVRUN] = run_before if dir_before != 0 else 0
    iv[s, I_HASPEND] = 1
    iv[s, I_NOTBEFORE] = t + latency


@nb.njit(cache=True)
def process(ts, bids, asks, years, months, f, iv, pi, pf, acc, g, gi, data,
            impulse_min, pullback_max, commission, latency, spread_mult):
    nslots = f.shape[0]
    for i in range(ts.shape[0]):
        t = ts[i]
        bid = bids[i]
        ask = asks[i]
        if bid <= 0 or ask < bid or t < gi[GI_LASTT]:
            gi[GI_BAD] += 1
            continue
        gi[GI_LASTT] = t
        # ---- bad-quote filter: a spread far above the running mean marks an off-market quote.
        # Live-implementable (no look-ahead); the EMA only learns from accepted ticks.
        spr = ask - bid
        if g[G_SPREMA] <= 0:
            g[G_SPREMA] = spr
        elif spread_mult > 0 and spr > spread_mult * g[G_SPREMA]:
            gi[GI_SPRREJ] += 1
            continue
        g[G_SPREMA] += SPREAD_EMA_ALPHA * (spr - g[G_SPREMA])
        year = years[i]
        month = months[i]
        yi = _yi(year)
        # ---- CDailyRangeTracker.OnTick
        new_day = False
        new_atr = False
        day = (t + 7200000) // 86400000
        if day != gi[GI_DAY]:
            if gi[GI_DAY] >= 0:
                h = g[G_HI]
                lo = g[G_LO]
                if gi[GI_HASPREV]:
                    if g[G_PREVCLOSE] > h:
                        h = g[G_PREVCLOSE]
                    if g[G_PREVCLOSE] < lo:
                        lo = g[G_PREVCLOSE]
                g[G_FINTR] = h - lo
                gi[GI_FINYEAR] = gi[GI_DAYYEAR]
                g[G_QSUM] += g[G_FINTR]
                gi[GI_QN] += 1
                g[G_PREVCLOSE] = g[G_LAST]
                gi[GI_HASPREV] = 1
            else:
                g[G_FINTR] = -1.0
            gi[GI_DAY] = day
            gi[GI_DAYYEAR] = year
            g[G_HI] = bid
            g[G_LO] = bid
            new_day = True
        else:
            if bid > g[G_HI]:
                g[G_HI] = bid
            if bid < g[G_LO]:
                g[G_LO] = bid
        g[G_LAST] = bid
        q = year * 4 + (month - 1) // 3
        if q != gi[GI_QUARTER]:
            if gi[GI_QUARTER] >= 0 and gi[GI_QN] >= 20:
                g[G_ATR] = g[G_QSUM] / gi[GI_QN]
                new_atr = True
            gi[GI_QUARTER] = q
            g[G_QSUM] = 0.0
            gi[GI_QN] = 0
        if new_day:
            data[yi, D_DAYS] += 1
            data[TOTAL, D_DAYS] += 1
            if g[G_FINTR] >= 0:
                fy = _yi(gi[GI_FINYEAR])
                data[fy, D_TRSUM] += g[G_FINTR]
                data[fy, D_TRDAYS] += 1
                data[TOTAL, D_TRSUM] += g[G_FINTR]
                data[TOTAL, D_TRDAYS] += 1
        if new_atr:
            atr = g[G_ATR]
            for s in range(nslots):
                if iv[s, I_ATRMODE] and atr > 0:
                    size = np.floor(f[s, S_PARAM] * atr * 100.0 + 0.5) / 100.0
                    if size < 0.05:
                        size = 0.05
                    if not iv[s, I_ACTIVE]:
                        _engine_init(f, iv, s, size)
                        iv[s, I_ACTIVE] = 1
                    else:
                        _set_brick_size(f, iv, s, size)
        step = abs(bid - g[G_PREVBID]) if g[G_PREVBID] > 0 else 0.0
        g[G_PREVBID] = bid
        for pass_ in range(2):
            a = yi if pass_ == 0 else TOTAL
            data[a, D_TICKS] += 1
            data[a, D_SPREAD] += ask - bid
            data[a, D_PATH] += step
        # ---- slots
        for s in range(nslots):
            if not iv[s, I_ACTIVE]:
                continue
            if iv[s, I_HASPEND] and t >= iv[s, I_NOTBEFORE]:
                _fill(iv, pi, pf, acc, s, yi, bid, ask, commission)
            dir_before = iv[s, I_DIR]
            run_before = iv[s, I_RUN]
            n = _engine_tick(f, iv, s, bid, ask)
            if n > 0:
                _on_bricks(f, iv, pi, pf, acc, s, n, dir_before, run_before, t, yi,
                           impulse_min, pullback_max, latency)
        gi[GI_N] += 1


def make_state(fixed=FIXED, atr_fractions=ATR_FRACTIONS):
    labels, modes, params = [], [], []
    for p in fixed:
        labels.append(f"${p:g}" if p < 0.01 else f"${p:.2f}"); modes.append("FIXED"); params.append(float(p))
    for p in atr_fractions:
        labels.append(f"{p:.2f}xATR"); modes.append("ATR_Q"); params.append(float(p))
    ns = len(params)
    f = np.zeros((ns, NF))
    iv = np.zeros((ns, NI), dtype=np.int64)
    for s, (m, p) in enumerate(zip(modes, params)):
        f[s, S_PARAM] = p
        iv[s, I_ATRMODE] = 1 if m == "ATR_Q" else 0
        if m == "FIXED":
            _engine_init(f, iv, s, p)
            iv[s, I_ACTIVE] = 1
    pi = np.zeros((ns, 2, 3), dtype=np.int64)
    pf = np.zeros((ns, 2, 4))
    acc = np.zeros((ns, YEARS + 1, NACC))
    g = np.zeros(9)
    gi = np.zeros(10, dtype=np.int64)
    gi[GI_DAY] = -1
    gi[GI_QUARTER] = -1
    data = np.zeros((YEARS + 1, 6))
    return labels, modes, params, f, iv, pi, pf, acc, g, gi, data


HEADER = ("label,mode,param,year,avg_brick,days,bricks,bricks_per_day,flips,flips_per_day,"
          "phantom_pct,subsec_pct,avg_spread,spread_pct_of_brick,avg_overshoot,max_overshoot,"
          "runs,mean_run_len,run1_pct,run2_pct,run3_pct,run4_5_pct,run6_9_pct,run10_19_pct,run20p_pct,max_run,"
          "A_trades,A_win_pct,A_theo,A_net,A_net_per_trade,A_cost_per_trade,A_pf,A_maxdd,"
          "B_trades,B_win_pct,B_theo,B_net,B_net_per_trade,B_cost_per_trade,B_pf,B_maxdd")


def write_outputs(prefix, labels, modes, params, acc, data):
    rows = [HEADER]
    for s, (lab, mode, par) in enumerate(zip(labels, modes, params)):
        for i in range(YEARS + 1):
            a = acc[s, i]
            if a[A_BRICKS] == 0:
                continue
            d = max(data[i, D_DAYS], 1)
            nbk, ne = a[A_BRICKS], a[A_EVENTS]
            avg_brick = a[A_SIZE] / nbk
            avg_spread = a[A_SPREAD] / ne
            runs = a[A_RUNS]
            cols = [lab, mode, f"{par:.4f}", "ALL" if i == TOTAL else str(YEAR0 + i),
                    f"{avg_brick:.3f}", f"{int(data[i, D_DAYS])}", f"{int(nbk)}", f"{nbk / d:.2f}",
                    f"{int(a[A_FLIPS])}", f"{a[A_FLIPS] / d:.2f}",
                    f"{100 * a[A_PHANTOM] / nbk:.3f}", f"{100 * a[A_SUBSEC] / ne:.3f}",
                    f"{avg_spread:.4f}", f"{100 * avg_spread / avg_brick:.2f}",
                    f"{a[A_OVER] / ne:.4f}", f"{a[A_OVERMAX]:.2f}",
                    f"{int(runs)}", f"{(a[A_RUNSUM] / runs if runs else 0):.4f}"]
            cols += [f"{(100 * a[A_HIST + b] / runs if runs else 0):.2f}" for b in range(NHIST)]
            cols.append(f"{int(a[A_RUNMAX])}")
            for st in range(2):
                o = A_STRAT + st * NT
                nt = max(a[o + T_TRADES], 1)
                cols += [f"{int(a[o + T_TRADES])}", f"{100 * a[o + T_WINS] / nt:.2f}",
                         f"{a[o + T_THEO]:.2f}", f"{a[o + T_NET]:.2f}", f"{a[o + T_NET] / nt:.4f}",
                         f"{(a[o + T_THEO] - a[o + T_NET]) / nt:.4f}",
                         f"{(a[o + T_GP] / a[o + T_GL] if a[o + T_GL] > 0 else 0):.3f}",
                         f"{a[o + T_MDD]:.2f}"]
            rows.append(",".join(cols))
    with open(f"{prefix}_summary.csv", "w", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")
    ds = ["year,ticks,days,avg_spread,daily_atr,tick_path_per_day,path_to_atr"]
    for i in range(YEARS + 1):
        if data[i, D_TICKS] == 0:
            continue
        d = max(data[i, D_DAYS], 1)
        atr = data[i, D_TRSUM] / data[i, D_TRDAYS] if data[i, D_TRDAYS] > 0 else 0
        path_day = data[i, D_PATH] / d
        ds.append(",".join(["ALL" if i == TOTAL else str(YEAR0 + i), str(int(data[i, D_TICKS])),
                            str(int(data[i, D_DAYS])), f"{data[i, D_SPREAD] / data[i, D_TICKS]:.4f}",
                            f"{atr:.2f}", f"{path_day:.2f}", f"{(path_day / atr if atr > 0 else 0):.2f}"]))
    with open(f"{prefix}_dataset.csv", "w", newline="\n") as fh:
        fh.write("\n".join(ds) + "\n")


def main(csv_path: str, prefix: str, fixed=FIXED, atr_fractions=ATR_FRACTIONS,
         commission: float = COMMISSION_SIDE, from_ms: int = 0, spread_mult: float = SPREAD_MULT) -> None:
    labels, modes, params, f, iv, pi, pf, acc, g, gi, data = make_state(fixed, atr_fractions)
    started = time.time()
    reader = pacsv.open_csv(
        csv_path,
        read_options=pacsv.ReadOptions(block_size=256 << 20),
        convert_options=pacsv.ConvertOptions(
            include_columns=["DateTime", "Bid", "Ask"],
            column_types={"DateTime": pa.string(), "Bid": pa.float64(), "Ask": pa.float64()}))
    total = 0
    for batch in reader:
        df = pl.from_arrow(batch).rename({"DateTime": "dt", "Bid": "bid", "Ask": "ask"}).with_columns(
            pl.col("dt").str.strptime(pl.Datetime("ms"), "%Y%m%d %H:%M:%S%.3f", strict=False).alias("ts"))
        bad_dt = df["ts"].null_count()
        df = df.drop_nulls("ts")
        if from_ms:
            df = df.filter(pl.col("ts").dt.epoch("ms") >= from_ms)
            if df.height == 0:
                continue
        ts = df["ts"].dt.epoch("ms").to_numpy().astype(np.int64)
        years = df["ts"].dt.year().to_numpy().astype(np.int64)
        months = df["ts"].dt.month().to_numpy().astype(np.int64)
        process(ts, df["bid"].to_numpy(), df["ask"].to_numpy(), years, months, f, iv, pi, pf, acc, g, gi,
                data, IMPULSE_MIN, PULLBACK_MAX, commission, LATENCY_MS, spread_mult)
        total += len(ts)
        el = time.time() - started
        print(f"{total / 1e6:8.1f}M ticks  up to {df['dt'][-1]}  {el:7.0f}s  bad_dt={bad_dt}", flush=True)
    write_outputs(prefix, labels, modes, params, acc, data)
    print(f"done: {gi[GI_N]} ticks used, {gi[GI_BAD]} rejected (time/price), {gi[GI_SPRREJ]} rejected "
          f"(spread > {spread_mult:g}x running mean), {time.time() - started:.0f}s", flush=True)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("prefix")
    ap.add_argument("--fixed", help="comma list of brick sizes in price units")
    ap.add_argument("--atr", help="comma list of prior-quarter ATR fractions ('' for none)")
    ap.add_argument("--commission", type=float, default=COMMISSION_SIDE, help="per side, price units per unit")
    ap.add_argument("--from-date", help="YYYY-MM-DD (UTC); ticks before it are skipped entirely")
    ap.add_argument("--spread-mult", type=float, default=SPREAD_MULT, help="bad-quote filter, 0 = off")
    a = ap.parse_args()
    lst = lambda v, d: d if v is None else [float(x) for x in v.split(",") if x.strip()]  # noqa: E731
    fm = 0
    if a.from_date:
        import datetime as _dt
        fm = int(_dt.datetime.fromisoformat(a.from_date).replace(tzinfo=_dt.timezone.utc).timestamp() * 1000)
    main(a.csv, a.prefix, lst(a.fixed, FIXED), lst(a.atr, ATR_FRACTIONS), a.commission, fm, a.spread_mult)
