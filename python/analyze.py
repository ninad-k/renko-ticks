"""Turn sweep summaries + brick dumps into the tidy CSVs and fact sheets for Parts 2 and 3.

    python analyze.py
Reads  results/sweep/, results/cross/, results/dump_xauusd/
Writes results/ep02/*.csv + facts.md, results/ep03/*.csv + facts.md
"""

from __future__ import annotations

import math
import os

import numpy as np
import polars as pl

ROOT = os.path.join(os.path.dirname(__file__), "..", "results")
SW = os.path.join(ROOT, "sweep", "RenkoSweep_XAUUSD_summary.csv")
DS = os.path.join(ROOT, "sweep", "RenkoSweep_XAUUSD_dataset.csv")
DUMP = os.path.join(ROOT, "dump_xauusd")
SD_GEOM = math.sqrt(6.0)  # sd of run length under the random walk (p continue = 2/3)


def load_summary(path):
    s = pl.read_csv(path)
    return s.with_columns(
        pl.when(pl.col("mode") == "FIXED").then(pl.lit("fixed")).otherwise(pl.lit("atr")).alias("kind"))


def ep02(s: pl.DataFrame, ds: pl.DataFrame) -> list[str]:
    out = os.path.join(ROOT, "ep02")
    os.makedirs(out, exist_ok=True)
    a = s.filter(pl.col("year") == "ALL").with_columns(
        (pl.col("A_theo") / pl.col("A_trades")).alias("A_theo_per_trade"),
        (pl.col("B_theo") / pl.col("B_trades")).alias("B_theo_per_trade"),
        (100 * pl.col("A_cost_per_trade") / pl.col("avg_brick")).alias("A_cost_pct_brick"),
        (100 * pl.col("avg_overshoot") / pl.col("avg_brick")).alias("overshoot_pct_brick"),
        (100 * 0.07 / pl.col("avg_brick")).alias("commission_pct_brick"),
    )
    cols = ["label", "kind", "param", "avg_brick", "bricks_per_day", "flips_per_day", "phantom_pct", "subsec_pct",
            "avg_spread", "spread_pct_of_brick", "avg_overshoot", "overshoot_pct_brick", "commission_pct_brick",
            "A_trades", "A_win_pct", "A_theo", "A_net", "A_theo_per_trade", "A_net_per_trade", "A_cost_per_trade",
            "A_cost_pct_brick", "A_pf", "B_trades", "B_theo", "B_net", "B_theo_per_trade", "B_net_per_trade",
            "B_cost_per_trade", "B_pf"]
    a.select(cols).write_csv(os.path.join(out, "cost_by_size.csv"))
    ds.write_csv(os.path.join(out, "market_by_year.csv"))
    yr = s.filter((pl.col("year") != "ALL") & pl.col("label").is_in(["$2.00", "$5.00", "$15.00", "0.15xATR", "0.50xATR"]))
    yr.select("label", "year", "avg_brick", "spread_pct_of_brick", "phantom_pct", "A_trades",
              "A_cost_per_trade", "A_net_per_trade").write_csv(os.path.join(out, "cost_by_year.csv"))
    # overshoot distribution from the dump: first brick of each closing tick, overshoot in bricks
    rows = []
    for lab in ("fixed_2", "fixed_10", "atr_0.30"):
        p = os.path.join(DUMP, f"{lab}.parquet")
        if not os.path.exists(p):
            continue
        d = pl.read_parquet(p).filter(pl.col("burst_index") == pl.col("n_on_tick") - 1)  # last brick of each tick
        d = d.with_columns(((pl.col("trigger") - pl.col("close")).abs() / pl.col("size")).alias("over_bricks"))
        q = d["over_bricks"].quantile
        rows.append({"label": lab, "events": d.height, "p50": q(0.5), "p90": q(0.9), "p99": q(0.99),
                     "max": d["over_bricks"].max(), "share_gt_0_5": (d["over_bricks"] > 0.5).mean()})
        d.select("year", "over_bricks", "n_on_tick").write_parquet(os.path.join(out, f"overshoot_{lab}.parquet"))
    if rows:
        pl.DataFrame(rows).write_csv(os.path.join(out, "overshoot_quantiles.csv"))

    f = []
    g = lambda lab: a.filter(pl.col("label") == lab).row(0, named=True)  # noqa: E731
    one, half, two, five, twenty = g("$1.00"), g("$0.50"), g("$2.00"), g("$5.00"), g("$20.00")
    allds = ds.filter(pl.col("year") == "ALL").row(0, named=True)
    f.append(f"- Data: {allds['ticks']:,} XAUUSD ticks, {allds['days']} trading days (22:00 UTC day), 2017-10 to 2026-09-02.")
    for y in ("2017", "2020", "2024", "2025", "2026"):
        r = ds.filter(pl.col("year") == y).row(0, named=True)
        f.append(f"- {y}: avg spread ${r['avg_spread']:.4f}, avg daily range ${r['daily_atr']:.2f}, ticks {r['ticks']:,}")
    for r in (half, one, two, five, twenty):
        f.append(f"- {r['label']}: flip-follow A {r['A_trades']:,} trades, theo {r['A_theo']:+,.0f} "
                 f"({r['A_theo_per_trade']:+.3f}/trade), net {r['A_net']:+,.0f} ({r['A_net_per_trade']:+.3f}/trade), "
                 f"gap {r['A_cost_per_trade']:.3f}/trade = {r['A_cost_pct_brick']:.0f}% of a brick; phantom {r['phantom_pct']:.2f}%, "
                 f"sub-second {r['subsec_pct']:.2f}%, spread {r['spread_pct_of_brick']:.1f}% of brick, "
                 f"overshoot ${r['avg_overshoot']:.3f}")
    pos_theo = a.filter((pl.col("kind") == "fixed") & (pl.col("A_theo") > 0)).height
    pos_net = a.filter((pl.col("kind") == "fixed") & (pl.col("A_net") > 0))["label"].to_list()
    f.append(f"- Fixed sizes with positive theo for A: {pos_theo} of 16; positive net: {pos_net}")
    pos_net_atr = a.filter((pl.col("kind") == "atr") & (pl.col("A_net") > 0))["label"].to_list()
    f.append(f"- ATR sizes with positive net for A: {pos_net_atr}")
    if rows:
        for r in rows:
            f.append(f"- Overshoot {r['label']}: {r['events']:,} closing ticks, median {r['p50']:.3f} bricks, p90 {r['p90']:.3f}, "
                     f"p99 {r['p99']:.3f}, max {r['max']:.1f}, share > 0.5 brick {100 * r['share_gt_0_5']:.2f}%")
    return f


def runs_from_dump(path):
    d = pl.read_parquet(path)
    dirs = d["dir"].to_numpy()
    years = d["year"].to_numpy()
    phantom = (d["burst_index"].to_numpy() > 0).astype(np.int64)
    change = np.flatnonzero(np.diff(dirs) != 0) + 1
    starts = np.concatenate(([0], change))
    ends = np.concatenate((change, [len(dirs)]))
    # only completed runs (a run completes when the next brick reverses): drop the last
    starts, ends = starts[:-1], ends[:-1]
    lengths = ends - starts
    ph = np.add.reduceat(phantom, starts) if len(starts) else np.array([])
    return pl.DataFrame({"dir": dirs[starts], "year": years[ends], "len": lengths, "phantom": ph})


def ep03(s: pl.DataFrame) -> list[str]:
    out = os.path.join(ROOT, "ep03")
    os.makedirs(out, exist_ok=True)
    a = s.filter(pl.col("year") == "ALL").with_columns(
        ((pl.col("mean_run_len") - 3) / (SD_GEOM / pl.col("runs").sqrt())).alias("z"),
        (2 * SD_GEOM / pl.col("runs").sqrt()).alias("two_se"))
    a.select("label", "kind", "param", "avg_brick", "runs", "mean_run_len", "two_se", "z", "run1_pct", "run2_pct",
             "run3_pct", "run4_5_pct", "run6_9_pct", "run10_19_pct", "run20p_pct", "max_run",
             "A_trades", "A_theo", "A_net", "A_net_per_trade").write_csv(os.path.join(out, "runs_by_size.csv"))
    yr = s.filter(pl.col("year") != "ALL").select("label", "kind", "year", "runs", "mean_run_len", "A_net_per_trade")
    yr.write_csv(os.path.join(out, "runs_by_year.csv"))
    # geometric expectation of the histogram buckets
    p = 2 / 3
    pk = lambda k: p ** (k - 1) * (1 - p)  # noqa: E731
    geo = [pk(1), pk(2), pk(3), pk(4) + pk(5), sum(pk(k) for k in range(6, 10)), sum(pk(k) for k in range(10, 20)),
           p ** 19]
    pl.DataFrame({"bucket": ["1", "2", "3", "4-5", "6-9", "10-19", "20+"], "expected_pct": [100 * x for x in geo]}
                 ).write_csv(os.path.join(out, "geometric_expected.csv"))
    # dump-based: up vs down runs, phantom contribution
    rows = []
    for lab in ("fixed_2", "fixed_5", "fixed_10", "fixed_20", "fixed_50", "atr_0.10", "atr_0.20", "atr_0.30",
                "atr_0.50", "atr_1.00"):
        pth = os.path.join(DUMP, f"{lab}.parquet")
        if not os.path.exists(pth):
            continue
        r = runs_from_dump(pth)
        for (y,), grp in sorted(r.group_by(["year"]), key=lambda t: t[0]):
            up = grp.filter(pl.col("dir") > 0)["len"]
            dn = grp.filter(pl.col("dir") < 0)["len"]
            rows.append({"label": lab, "year": str(y), "runs": grp.height, "mean": grp["len"].mean(),
                         "up_runs": up.len(), "up_mean": up.mean(), "down_runs": dn.len(), "down_mean": dn.mean(),
                         "mean_ex_phantom": (grp["len"] - grp["phantom"]).mean()})
        up = r.filter(pl.col("dir") > 0)["len"]
        dn = r.filter(pl.col("dir") < 0)["len"]
        rows.append({"label": lab, "year": "ALL", "runs": r.height, "mean": r["len"].mean(), "up_runs": up.len(),
                     "up_mean": up.mean(), "down_runs": dn.len(), "down_mean": dn.mean(),
                     "mean_ex_phantom": (r["len"] - r["phantom"]).mean()})
    ud = pl.DataFrame(rows)
    ud.write_csv(os.path.join(out, "updown_by_year.csv"))

    cross = []
    for sym in ("EURUSD", "US500"):
        c = load_summary(os.path.join(ROOT, "cross", f"RenkoSweep_{sym}_summary.csv")).filter(pl.col("year") == "ALL")
        fr = [0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.75, 1.00]
        c = c.with_columns(pl.Series("atr_fraction", fr[: c.height]), pl.lit(sym).alias("symbol"),
                           ((pl.col("mean_run_len") - 3) / (SD_GEOM / pl.col("runs").sqrt())).alias("z"),
                           (2 * SD_GEOM / pl.col("runs").sqrt()).alias("two_se"))
        cross.append(c.select("symbol", "label", "atr_fraction", "avg_brick", "runs", "mean_run_len", "two_se", "z",
                              "A_trades", "A_theo", "A_net", "A_cost_per_trade", "spread_pct_of_brick", "phantom_pct"))
    cr = pl.concat(cross)
    cr.write_csv(os.path.join(out, "cross_market.csv"))

    f = []
    bonf = 3.09
    f.append(f"- Random-walk baseline: P(continue)=2/3, mean run 3.0, sd {SD_GEOM:.3f}; 25 sizes tested -> Bonferroni |z| > {bonf} (two-sided 5%).")
    for r in a.sort("kind", "param").iter_rows(named=True):
        f.append(f"- {r['label']}: runs {r['runs']:,}, mean {r['mean_run_len']:.3f} +/- {r['two_se']:.3f} (2 SE), z {r['z']:+.2f}, "
                 f"run1/2/3 = {r['run1_pct']:.1f}/{r['run2_pct']:.1f}/{r['run3_pct']:.1f}% (expected 33.3/22.2/14.8)")
    for r in ud.filter(pl.col("year") == "ALL").iter_rows(named=True):
        f.append(f"- {r['label']} up runs {r['up_runs']:,} mean {r['up_mean']:.3f}; down runs {r['down_runs']:,} mean "
                 f"{r['down_mean']:.3f}; mean with phantom bricks removed {r['mean_ex_phantom']:.3f}")
    for r in cr.iter_rows(named=True):
        f.append(f"- {r['symbol']} {r['atr_fraction']:.2f}xApr-range ({r['label']}): runs {r['runs']}, mean {r['mean_run_len']:.3f}, "
                 f"z {r['z']:+.2f}, A theo {r['A_theo']:+.4g} net {r['A_net']:+.4g}")
    return f


def main():
    s = load_summary(SW)
    ds = pl.read_csv(DS, schema_overrides={"year": pl.Utf8})
    f2 = ep02(s, ds)
    with open(os.path.join(ROOT, "ep02", "facts.md"), "w", encoding="utf-8") as fh:
        fh.write("# Part 2 facts (computed by python/analyze.py from the Python port of RenkoSweep)\n\n"
                 "Units: $ per oz per 1 unit traded. Commission 0.035 per side. Fills on the next tick at real bid/ask.\n"
                 "A = always-in flip-follow; B = impulse>=3 / pullback<=2 / resumption. theo = same trades filled at\n"
                 "the brick boundary with zero spread and no commission.\n\n" + "\n".join(f2) + "\n")
    f3 = ep03(s)
    with open(os.path.join(ROOT, "ep03", "facts.md"), "w", encoding="utf-8") as fh:
        fh.write("# Part 3 facts (computed by python/analyze.py)\n\n" + "\n".join(f3) + "\n")
    print("\n".join(f2 + [""] + f3))


if __name__ == "__main__":
    main()
