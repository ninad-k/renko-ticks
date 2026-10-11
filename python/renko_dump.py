"""Brick-level dump for a handful of brick sizes, reusing the sweep's numba engine.

Writes one parquet per slot: time_close_msc, year, dir, n_on_tick (bricks closed
by that tick), burst_index, close, trigger, spread. Used for Part 2/3 figures and
for the run-length checks the summary CSV cannot answer (bursts collapsed,
up vs down runs).

    python renko_dump.py <ticks.csv> <out_dir>
"""

from __future__ import annotations

import os
import sys
import time

import numba as nb
import numpy as np
import polars as pl
import pyarrow as pa
import pyarrow.csv as pacsv

from renko_sweep import (SPREAD_EMA_ALPHA, SPREAD_MULT, E_BRICK, E_LASTCLOSE, E_LASTSPREAD, E_LASTTRIG, I_ACTIVE, I_DIR, NF, NI, S_PARAM,
                         _engine_init, _engine_tick, _set_brick_size)

FIXED = [2, 5, 10, 20, 50]
ATR_FRACTIONS = [0.10, 0.20, 0.30, 0.50, 1.00]
CAP = 400_000


@nb.njit(cache=True)
def dump_chunk(ts, bids, asks, years, months, f, iv, atrmode, st, cnt,
               o_t, o_year, o_dir, o_n, o_burst, o_close, o_trig, o_spread, o_size):
    # st: [day, hi, lo, last, prevclose, hasprev, quarter, qsum, qn, lastT, spread_ema, rejected]
    nslots = f.shape[0]
    for i in range(ts.shape[0]):
        t = ts[i]
        bid = bids[i]
        ask = asks[i]
        if bid <= 0 or ask < bid or t < st[9]:
            continue
        st[9] = t
        spr = ask - bid
        if st[10] <= 0:
            st[10] = spr
        elif SPREAD_MULT > 0 and spr > SPREAD_MULT * st[10]:
            st[11] += 1
            continue
        st[10] += SPREAD_EMA_ALPHA * (spr - st[10])
        year = years[i]
        day = (t + 7200000) // 86400000
        if day != st[0]:
            if st[0] >= 0:
                h = st[1]
                lo = st[2]
                if st[5] > 0:
                    h = max(h, st[4])
                    lo = min(lo, st[4])
                st[7] += h - lo
                st[8] += 1
                st[4] = st[3]
                st[5] = 1
            st[0] = day
            st[1] = bid
            st[2] = bid
        else:
            st[1] = max(st[1], bid)
            st[2] = min(st[2], bid)
        st[3] = bid
        q = year * 4 + (months[i] - 1) // 3
        if q != st[6]:
            if st[6] >= 0 and st[8] >= 20:
                atr = st[7] / st[8]
                for s in range(nslots):
                    if atrmode[s]:
                        size = np.floor(f[s, S_PARAM] * atr * 100.0 + 0.5) / 100.0
                        if size < 0.05:
                            size = 0.05
                        if not iv[s, I_ACTIVE]:
                            _engine_init(f, iv, s, size)
                            iv[s, I_ACTIVE] = 1
                        else:
                            _set_brick_size(f, iv, s, size)
            st[6] = q
            st[7] = 0.0
            st[8] = 0
        for s in range(nslots):
            if not iv[s, I_ACTIVE]:
                continue
            n = _engine_tick(f, iv, s, bid, ask)
            if n > 0:
                d = iv[s, I_DIR]
                size = f[s, E_BRICK]
                for j in range(n):
                    c = cnt[s]
                    if c >= o_t.shape[1]:
                        break
                    o_t[s, c] = t
                    o_year[s, c] = year
                    o_dir[s, c] = d
                    o_n[s, c] = n
                    o_burst[s, c] = j
                    o_close[s, c] = f[s, E_LASTCLOSE] - d * (n - 1 - j) * size
                    o_trig[s, c] = f[s, E_LASTTRIG]
                    o_spread[s, c] = f[s, E_LASTSPREAD]
                    o_size[s, c] = size
                    cnt[s] = c + 1


def main(csv_path: str, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    labels = [f"fixed_{p}" for p in FIXED] + [f"atr_{p:.2f}" for p in ATR_FRACTIONS]
    params = [float(p) for p in FIXED] + ATR_FRACTIONS
    ns = len(params)
    f = np.zeros((ns, NF))
    iv = np.zeros((ns, NI), dtype=np.int64)
    atrmode = np.array([0] * len(FIXED) + [1] * len(ATR_FRACTIONS), dtype=np.int64)
    for s, p in enumerate(params):
        f[s, S_PARAM] = p
        if not atrmode[s]:
            _engine_init(f, iv, s, p)
            iv[s, I_ACTIVE] = 1
    st = np.array([-1, 0, 0, 0, 0, 0, -1, 0, 0, 0, 0, 0], dtype=np.float64)
    cnt = np.zeros(ns, dtype=np.int64)
    o_t = np.zeros((ns, CAP), dtype=np.int64)
    o_year = np.zeros((ns, CAP), dtype=np.int64)
    o_dir = np.zeros((ns, CAP), dtype=np.int64)
    o_n = np.zeros((ns, CAP), dtype=np.int64)
    o_burst = np.zeros((ns, CAP), dtype=np.int64)
    o_close = np.zeros((ns, CAP))
    o_trig = np.zeros((ns, CAP))
    o_spread = np.zeros((ns, CAP))
    o_size = np.zeros((ns, CAP))
    reader = pacsv.open_csv(
        csv_path, read_options=pacsv.ReadOptions(block_size=256 << 20),
        convert_options=pacsv.ConvertOptions(
            include_columns=["DateTime", "Bid", "Ask"],
            column_types={"DateTime": pa.string(), "Bid": pa.float64(), "Ask": pa.float64()}))
    started = time.time()
    for batch in reader:
        df = pl.from_arrow(batch).with_columns(
            pl.col("DateTime").str.strptime(pl.Datetime("ms"), "%Y%m%d %H:%M:%S%.3f", strict=False).alias("ts")
        ).drop_nulls("ts")
        dump_chunk(df["ts"].dt.epoch("ms").to_numpy().astype(np.int64), df["Bid"].to_numpy(), df["Ask"].to_numpy(),
                   df["ts"].dt.year().to_numpy().astype(np.int64), df["ts"].dt.month().to_numpy().astype(np.int64),
                   f, iv, atrmode, st, cnt, o_t, o_year, o_dir, o_n, o_burst, o_close, o_trig, o_spread, o_size)
        print(f"{df['DateTime'][-1]}  {time.time() - started:6.0f}s  bricks={cnt.tolist()}", flush=True)
    for s, lab in enumerate(labels):
        c = cnt[s]
        if c >= CAP:
            print(f"WARNING {lab}: capacity {CAP} reached, dump truncated")
        pl.DataFrame({"time_close_msc": o_t[s, :c], "year": o_year[s, :c], "dir": o_dir[s, :c],
                      "n_on_tick": o_n[s, :c], "burst_index": o_burst[s, :c], "close": o_close[s, :c],
                      "trigger": o_trig[s, :c], "spread": o_spread[s, :c], "size": o_size[s, :c]}
                     ).write_parquet(os.path.join(out_dir, f"{lab}.parquet"))
    print("done", dict(zip(labels, cnt.tolist())), f"spread-rejected {int(st[11])}", f"{time.time() - started:.0f}s")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
