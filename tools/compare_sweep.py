#!/usr/bin/env python3
"""Compare the MQL5 RenkoSweep output with the Python reference output.

Reads
    <Common>\\Files\\RenkoSweep_XAUUSD_MQL5_summary.csv   (candidate, from the MQL5 script)
    <Common>\\Files\\RenkoSweep_XAUUSD_MQL5_dataset.csv
and compares them with
    results\\sweep\\RenkoSweep_XAUUSD_summary.csv          (reference, from the Python port)
    results\\sweep\\RenkoSweep_XAUUSD_dataset.csv

Rules, per (label, year) row of the summary and per year row of the dataset:
  * integer columns (days, bricks, flips, runs, max_run, A_trades, B_trades,
    and ticks/days in the dataset) must match exactly;
  * every other numeric column passes if |diff| <= 0.01 OR |diff| <= 1e-6 * max(|a|,|b|);
  * a row that exists on one side only is a FAIL.

Output: a PASS/FAIL table on stdout and results\\verification\\sweep_compare.md.
Exit code: 0 = everything PASS, 1 = at least one FAIL, 2 = input problem.

Only the Python standard library is used.
Usage:  python -I tools\\compare_sweep.py [--cand CSV] [--ref CSV] [--cand-dataset CSV]
                                          [--ref-dataset CSV] [--out MD] [--max-detail N]
"""
import argparse
import csv
import datetime
import os
import sys

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
COMMON = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal", "Common", "Files")

SUMMARY_KEY = ("label", "year")
SUMMARY_TEXT = {"label", "mode", "year"}          # not compared numerically (label/year are the key)
SUMMARY_INT = {"days", "bricks", "flips", "runs", "max_run", "A_trades", "B_trades"}
DATASET_KEY = ("year",)
DATASET_TEXT = {"year"}
DATASET_INT = {"ticks", "days"}

ABS_TOL = 0.01
REL_TOL = 1e-6


def read_csv(path):
    """Return (header, rows) where rows is a list of dicts. Tolerates BOM / ANSI."""
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        rd = csv.reader(f)
        try:
            header = [h.strip() for h in next(rd)]
        except StopIteration:
            raise ValueError("empty file: " + path)
        rows = []
        for r in rd:
            if not r or all(not c.strip() for c in r):
                continue
            rows.append({h: (r[i].strip() if i < len(r) else "") for i, h in enumerate(header)})
    return header, rows


def to_float(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def compare_tables(name, cand_path, ref_path, key_cols, text_cols, int_cols):
    """Return dict with per-row results."""
    ch, crows = read_csv(cand_path)
    rh, rrows = read_csv(ref_path)
    result = {"name": name, "cand": cand_path, "ref": ref_path, "rows": [], "cells_checked": 0,
              "header_problems": []}
    if ch != rh:
        only_c = [c for c in ch if c not in rh]
        only_r = [c for c in rh if c not in ch]
        if only_c:
            result["header_problems"].append("columns only in candidate: " + ", ".join(only_c))
        if only_r:
            result["header_problems"].append("columns only in reference: " + ", ".join(only_r))
        if not only_c and not only_r:
            result["header_problems"].append("same columns, different order (compared by name)")
    cols = [c for c in rh if c in ch and c not in text_cols]

    def keyof(row):
        return tuple(row.get(k, "") for k in key_cols)

    cmap = {}
    for r in crows:
        cmap.setdefault(keyof(r), r)
    seen = set()
    for rr in rrows:
        k = keyof(rr)
        seen.add(k)
        cr = cmap.get(k)
        entry = {"key": k, "status": "PASS", "fails": [], "worst": 0.0}
        if cr is None:
            entry["status"] = "FAIL"
            entry["fails"].append(("(row)", "missing in candidate", "", ""))
            result["rows"].append(entry)
            continue
        for c in cols:
            a, b = cr.get(c, ""), rr.get(c, "")
            result["cells_checked"] += 1
            fa, fb = to_float(a), to_float(b)
            if fa is None or fb is None:
                if a != b:
                    entry["fails"].append((c, "non-numeric differs", a, b))
                continue
            d = abs(fa - fb)
            if c in int_cols:
                if fa != fb:
                    entry["fails"].append((c, "integer differs", a, b))
                    entry["worst"] = max(entry["worst"], d)
            else:
                scale = max(abs(fa), abs(fb))
                if d > ABS_TOL and d > REL_TOL * scale:
                    entry["fails"].append((c, "|diff|=%.6g" % d, a, b))
                    entry["worst"] = max(entry["worst"], d)
        if entry["fails"]:
            entry["status"] = "FAIL"
        result["rows"].append(entry)
    for k, cr in cmap.items():
        if k not in seen:
            result["rows"].append({"key": k, "status": "FAIL", "worst": 0.0,
                                   "fails": [("(row)", "extra in candidate", "", "")]})
    result["n_pass"] = sum(1 for e in result["rows"] if e["status"] == "PASS")
    result["n_fail"] = sum(1 for e in result["rows"] if e["status"] == "FAIL")
    return result


def label_summary(res):
    """Aggregate summary rows per label."""
    agg = {}
    order = []
    for e in res["rows"]:
        lab = e["key"][0]
        if lab not in agg:
            agg[lab] = {"rows": 0, "fail": 0, "cols": set(), "years_failing": []}
            order.append(lab)
        a = agg[lab]
        a["rows"] += 1
        if e["status"] == "FAIL":
            a["fail"] += 1
            a["years_failing"].append(e["key"][1] if len(e["key"]) > 1 else "")
            for f in e["fails"]:
                a["cols"].add(f[0])
    return [(lab, agg[lab]) for lab in order]


def render_text(results, max_detail):
    out = []
    overall = all(r["n_fail"] == 0 for r in results)
    for r in results:
        out.append("")
        out.append("== %s ==" % r["name"])
        out.append("candidate: %s" % r["cand"])
        out.append("reference: %s" % r["ref"])
        for h in r["header_problems"]:
            out.append("note: " + h)
        out.append("rows: %d   PASS: %d   FAIL: %d   cells checked: %d" %
                   (len(r["rows"]), r["n_pass"], r["n_fail"], r["cells_checked"]))
        if r["name"] == "summary":
            out.append("")
            out.append("%-12s %5s %5s %5s  %s" % ("label", "rows", "pass", "fail", "result / columns that differ"))
            for lab, a in label_summary(r):
                ok = a["fail"] == 0
                cols = "" if ok else (", ".join(sorted(a["cols"]))[:70] + "  years: " + ",".join(a["years_failing"]))
                out.append("%-12s %5d %5d %5d  %s %s" % (lab, a["rows"], a["rows"] - a["fail"], a["fail"],
                                                        "PASS" if ok else "FAIL", cols[:110]))
        else:
            out.append("")
            out.append("%-8s %s" % ("year", "result"))
            for e in r["rows"]:
                out.append("%-8s %s %s" % (e["key"][0], e["status"],
                                           "" if not e["fails"] else "; ".join("%s %s (%s vs %s)" % f for f in e["fails"][:4])))
        fails = [(e["key"], f) for e in r["rows"] for f in e["fails"]]
        if fails:
            out.append("")
            out.append("first %d of %d differing cells (candidate vs reference):" % (min(max_detail, len(fails)), len(fails)))
            for key, f in fails[:max_detail]:
                out.append("  %s  %-18s %-22s cand=%s  ref=%s" % ("/".join(key), f[0], f[1], f[2], f[3]))
    out.append("")
    out.append("OVERALL: " + ("PASS" if overall else "FAIL"))
    return "\n".join(out), overall


def render_md(results, overall, args):
    L = []
    L.append("# RenkoSweep comparison: MQL5 vs Python")
    L.append("")
    L.append("Generated: %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    L.append("")
    L.append("**Overall: %s**" % ("PASS" if overall else "FAIL"))
    L.append("")
    L.append("Rules: integer columns (days, bricks, flips, runs, max_run, A_trades, B_trades; ticks and days in the dataset) "
             "must match exactly. Other numeric columns pass if |diff| <= %g or |diff| <= %g x max(|a|,|b|)." % (ABS_TOL, REL_TOL))
    for r in results:
        L.append("")
        L.append("## %s" % r["name"])
        L.append("")
        L.append("- candidate: `%s`" % r["cand"])
        L.append("- reference: `%s`" % r["ref"])
        for h in r["header_problems"]:
            L.append("- note: " + h)
        L.append("- rows %d, PASS %d, FAIL %d, cells checked %d" % (len(r["rows"]), r["n_pass"], r["n_fail"], r["cells_checked"]))
        L.append("")
        if r["name"] == "summary":
            L.append("| label | rows | pass | fail | result | columns that differ | years failing |")
            L.append("|---|---:|---:|---:|---|---|---|")
            for lab, a in label_summary(r):
                ok = a["fail"] == 0
                L.append("| %s | %d | %d | %d | %s | %s | %s |" % (
                    lab.replace("|", "/"), a["rows"], a["rows"] - a["fail"], a["fail"], "PASS" if ok else "FAIL",
                    ", ".join(sorted(a["cols"])), ",".join(a["years_failing"])))
        else:
            L.append("| year | result | differences |")
            L.append("|---|---|---|")
            for e in r["rows"]:
                L.append("| %s | %s | %s |" % (e["key"][0], e["status"],
                                               "; ".join("%s %s (%s vs %s)" % f for f in e["fails"][:6])))
        fails = [(e["key"], f) for e in r["rows"] for f in e["fails"]]
        if fails:
            L.append("")
            L.append("Differing cells (first %d of %d):" % (min(args.max_detail, len(fails)), len(fails)))
            L.append("")
            L.append("| row | column | problem | candidate | reference |")
            L.append("|---|---|---|---|---|")
            for key, f in fails[:args.max_detail]:
                L.append("| %s | %s | %s | %s | %s |" % ("/".join(key).replace("|", "/"), f[0], f[1], f[2], f[3]))
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cand", default=os.path.join(COMMON, "RenkoSweep_XAUUSD_MQL5_summary.csv"))
    ap.add_argument("--ref", default=os.path.join(REPO, "results", "sweep", "RenkoSweep_XAUUSD_summary.csv"))
    ap.add_argument("--cand-dataset", default=None, help="default: derived from --cand (_summary -> _dataset)")
    ap.add_argument("--ref-dataset", default=None, help="default: derived from --ref")
    ap.add_argument("--out", default=os.path.join(REPO, "results", "verification", "sweep_compare.md"))
    ap.add_argument("--max-detail", type=int, default=60, help="how many differing cells to list")
    args = ap.parse_args()

    def ds(p):
        return p.replace("_summary.csv", "_dataset.csv") if p.endswith("_summary.csv") else None

    cd = args.cand_dataset or ds(args.cand)
    rd = args.ref_dataset or ds(args.ref)

    missing = [p for p in (args.cand, args.ref) if not os.path.isfile(p)]
    if missing:
        for p in missing:
            print("ERROR: file not found: " + p, file=sys.stderr)
        if args.cand in missing:
            print("The MQL5 output is written by RenkoSweep to the Common\\Files folder; "
                  "run tools\\run_checks.ps1 -Mode Sweep first.", file=sys.stderr)
        return 2
    try:
        results = [compare_tables("summary", args.cand, args.ref, SUMMARY_KEY, SUMMARY_TEXT, SUMMARY_INT)]
        if cd and rd and os.path.isfile(cd) and os.path.isfile(rd):
            results.append(compare_tables("dataset", cd, rd, DATASET_KEY, DATASET_TEXT, DATASET_INT))
        else:
            print("note: dataset files not compared (missing: %s)" %
                  ", ".join(p for p in (cd, rd) if not p or not os.path.isfile(p)))
    except (ValueError, OSError) as e:
        print("ERROR: " + str(e), file=sys.stderr)
        return 2

    text, overall = render_text(results, args.max_detail)
    print(text)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(render_md(results, overall, args))
    print("\nwritten: " + args.out)
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
