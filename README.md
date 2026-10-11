# Tick-Driven Renko in MQL5

Code and results for a four-part MQL5 article series. Renko bricks are built from
ticks inside the Expert Advisor, with no custom symbol. The series measures what a
Renko backtest hides and tests whether brick runs carry any persistence beyond a
random walk.

| Part | Article | Tag | What it adds |
|---|---|---|---|
| 1 | A Brick Engine That Cannot Repaint | `ep01` | `RenkoEngine.mqh`, `RenkoEngineTests.mq5` (10 hand-computed cases) |
| 2 | What a Renko Backtest Hides | `ep02` | `RenkoSweep.mq5/.mqh`, `TickCsvReader.mqh`, cost results |
| 3 | Measuring the Edge in Brick Runs | `ep03` | run-length results vs the random-walk mean of 3.0 |
| 4 | Making a Renko EA Pass Automatic Validation | `ep04` | `RenkoTickContinuationEA.mq5`, `MarketSafe.mqh` |

## Layout

```
mql5/Include/Renko/      RenkoEngine.mqh, RenkoSweep.mqh, TickCsvReader.mqh, MarketSafe.mqh
mql5/Scripts/Renko/      RenkoSweep.mq5, Tests/RenkoEngineTests.mq5
mql5/Experts/Renko/      RenkoTickContinuationEA.mq5
python/                  renko_engine.py (port + pytest), renko_sweep.py / renko_dump.py (numba), analyze.py
figures/                 make_epNN.py scripts and their PNGs, STYLE.md
results/                 sweep summaries, brick dumps, facts sheets per part
data/                    broker tick exports (not committed)
```

## Build and run

- MQL5: copy `mql5/` into your terminal's `MQL5/` folder and compile in MetaEditor.
  Built on MetaEditor 64-bit, 0 errors and 0 warnings for every file.
- Tests: run `Scripts/Renko/Tests/RenkoEngineTests` on any chart and read the Experts tab.
- Python: `cd python && python -m pytest -q` (engine port), then
  `python renko_sweep.py <ticks.csv> <prefix>` and `python analyze.py`.

## Provenance of the published numbers

The XAUUSD tables come from the Python/numba port of `RenkoSweep` run over
641.7 million ticks (Oct 2017 to 2 Sep 2026, one vendor's export, UTC). The port
reproduces the Python engine exactly on a 3M-tick sample and agrees with the
brick-level dump. Off-market quotes are rejected when the spread exceeds 25 times
its running mean, in both the port and `RenkoSweep.mq5` (`InpMaxSpreadMult`).
Rerun `RenkoSweep.mq5` on the same file before quoting the numbers as MQL5 output.

Nothing here is trading advice. Every figure is a historical simulation on tick data.
