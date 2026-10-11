# Verification kit

Three files, run by you on your own machine:

| File | Purpose |
|---|---|
| `run_checks.ps1` | Starts MetaTrader 5 as a script runner or as the Strategy Tester, waits for the result, closes the terminal, writes the evidence. |
| `compare_sweep.py` | Compares the MQL5 sweep output with the Python reference (`results\sweep\`). Also called by `run_checks.ps1 -Mode Sweep`. |
| `README.md` | This file. |

## Before you start

1. **Close MetaTrader 5 completely** (File > Exit, then check the tray). The kit refuses to start while `terminal64.exe` from `C:\Program Files\MetaTrader 5\` is running and tells you to close it.
2. The terminal's last-used account must be a **demo account**. The kit asks you to type `YES` before it launches anything.
3. Compile in MetaEditor (F7) if the kit warns that a `.ex5` is older than its source. At the time of writing `Scripts\Renko\Tests\RenkoEngineTests.mq5` is newer than its `.ex5`, so recompile that one first.
4. Open a normal (not elevated) PowerShell window in the repository folder, `<path to your renko-ticks clone>`.

What the kit does not do: it does not place orders, does not use charts other than the one a script needs, and never reads or writes your account, server, password or `common.ini` data. Every generated `/config` file has `[Experts] AllowLiveTrading=0`, so no Expert Advisor on a chart restored at start-up can trade; the Strategy Tester trades only on its own simulated account.

## Run it

```powershell
cd <path to your renko-ticks clone>
powershell -NoProfile -ExecutionPolicy Bypass -File tools\run_checks.ps1 -Mode Tests
powershell -NoProfile -ExecutionPolicy Bypass -File tools\run_checks.ps1 -Mode Sweep
powershell -NoProfile -ExecutionPolicy Bypass -File tools\run_checks.ps1 -Mode Validation
powershell -NoProfile -ExecutionPolicy Bypass -File tools\run_checks.ps1 -Mode All     # Tests, Sweep, Validation in that order
```

Useful options (all optional):

```powershell
-Cases 1,2,9                          # Validation: only these case ids
-Symbols @{Index='US500.cash'}        # Validation: broker-specific names (keys: Forex Jpy Gold Index Crypto Any)
-SymbolSuffix '.r'                    # Validation: suffix added to every default symbol you did not override
-Model 0                              # Validation: tester model 0 (every tick) instead of 4 (real ticks)
-NoFallback                           # Validation: do not retry with model 0 when model 4 gives no report
-HistoryDays 14                       # Validation: window length, ending yesterday (default 28)
-SweepTimeoutMin 240                  # Sweep: timeout in minutes (default 180)
-CaseTimeoutMin 90                    # Validation: timeout per run (default 60)
-Login 1234567                        # account NUMBER only, written to [Common]; never a password
-ShowAllLog                           # Tests/Sweep: echo every new Experts-log line, not only the Renko ones
-IgnoreRegex 'Market closed'          # Validation: error-pattern matches to ignore
```

Syntax check without launching anything:

```powershell
powershell -NoProfile -Command "[ScriptBlock]::Create((Get-Content tools\run_checks.ps1 -Raw)) | Out-Null"
```

## Modes

### Tests (about 1 minute)

Generates `results\verification\run_Tests_<stamp>\tests\tests.ini` with `[StartUp] Script=Renko\Tests\RenkoEngineTests`, `Symbol=EURUSD`, `Period=H1`, `ShutdownTerminal=1`, `[Experts] AllowLiveTrading=0`. Starts the terminal, polls the newest `MQL5\Logs\YYYYMMDD.log` (only lines added after the start), waits for `RenkoEngineTests: N passed, M failed`, lets the terminal exit, otherwise closes it (CloseMainWindow, then `Stop-Process` with a warning after `-CloseGraceSec`, default 60 s). Prints the summary and every `FAIL [...]` line.

**PASS** = a summary line was seen with 0 failed, more than 0 passed and no `FAIL` lines.

### Sweep (30 to 90 minutes, up to 3 hours)

Writes `MQL5\Presets\RenkoVerify_sweep.set` (source CSV `XAUUSD_ticks.csv`, `InpOutPrefix=RenkoSweep_XAUUSD_MQL5`, `InpMaxSpreadMult=25`, everything else at the script defaults), starts the terminal with `ScriptParameters=RenkoVerify_sweep.set`, and waits for `RenkoSweep: done.` The script prints no progress of its own, so you get a heartbeat every minute (elapsed time, terminal CPU seconds and memory). It stops early on `RenkoSweep: cannot open ...`. When the script is done the kit runs `compare_sweep.py` on `Common\Files\RenkoSweep_XAUUSD_MQL5_summary.csv` and `_dataset.csv`.

**PASS** = the script finished (not `STOPPED EARLY`), the output files are newer than the start, and the comparer says OVERALL: PASS.

Comparer rules, per label and year: integer columns (`days bricks flips runs max_run A_trades B_trades`, and `ticks days` in the dataset) must match exactly; every other number passes if `|diff| <= 0.01` or `|diff| <= 1e-6 x max(|a|,|b|)`; a row on one side only is a FAIL. You can also run it alone:

```powershell
python -I tools\compare_sweep.py
python -I tools\compare_sweep.py --cand <csv> --ref <csv>     # any two summary files
```

### Validation (about 18 Strategy Tester runs, 1 to 3 hours)

The self-test checklist in `docs\series\renko-ticks\drafts\ep04.md` has **15 rows**; rows 7 and 8 have several deposits, so the kit makes 18 runs (ids `1 2 3 4 5 6 7a 7b 7c 8a 8b 9 10 11 12 13 14 15`). For each run it writes `MQL5\Profiles\Tester\RenkoVerify_case<id>.set` (all 17 EA inputs explicit, defaults plus the case's changes) and a tester `.ini`: `Expert=Renko\RenkoTickContinuationEA`, `Model=4` (fallback `0`), `Deposit`, `Currency=USD`, `Leverage=1:100`, `FromDate/ToDate` (28 days ending yesterday; case 10 uses 3 days, case 15 starts on a Monday), `Report=RenkoVerify\ep04_<case>.htm`, `ReplaceReport=1`, `ShutdownTerminal=1`, `AllowLiveTrading=0`. It runs the cases one at a time, waits for the terminal to exit by itself (timeout `-CaseTimeoutMin`), copies the report to `results\ep04\tester\`, reads the **trade count only** from it, and scans the new lines of the tester logs for `failed`, `error`, `[100`, `array out of range`, `zero divide`, `initialization failed`.

Logs scanned: `<data folder>\Tester\logs`, `<data folder>\Tester\Agent-*\logs` (if present) and `%APPDATA%\MetaQuotes\Tester\<data folder id>\Agent-*\logs`, which on this machine is where the agents write the EA's `Print` output. Only bytes added after the launch are read.

| Case | Symbol (default) | TF | Deposit | Changed inputs | Extra rule beyond "no errors, enough trades" |
|---|---|---|---|---|---|
| 1 | EURUSD | M1 | 10000 | - | journal line `brick size ... (daily ATR fraction)` |
| 2 | EURUSD | H4 | 10000 | - | same line; **trade count equal to case 1** |
| 3 | USDJPY | M15 | 10000 | - | - |
| 4 | XAUUSD | H1 | 10000 | - | - |
| 5 | US500 | M5 | 10000 | - | - |
| 6 | BTCUSD | D1 | 10000 | - | - |
| 7a, 7b, 7c | EURUSD | M1 | 1, 10, 100 | - | 0 trades allowed; `MarketSafe: not enough money` count is reported |
| 8a, 8b | EURUSD | H1 | 100, 10000 | `InpLotMode=1` (risk percent, 1 %) | at least 1 trade at 100 |
| 9 | EURUSD | H1 | 10000 | `InpBrickMode=1` | journal line `(fixed points)` |
| 10 | EURUSD | H1 | 10000 | - (3-day window) | journal shows the brick size line or `daily ATR not available`; 0 trades allowed |
| 11 | EURUSD | M5 | 10000 | `InpTPBricks=1`, `InpSameBricks=1` | - |
| 12 | EURUSD | M5 | 10000 | `InpCloseOnOpposite=false` | - |
| 13 | EURUSD | M5 | 10000 | `InpMaxSpreadPoints=1` | journal line `skipped, spread ... is above the limit`; 0 trades allowed |
| 14 | EURUSD | H1 | 10000 | - | `started on ... hedging / netting` line; recorded in notes |
| 15 | EURUSD | H1 | 10000 | - (Monday-to-Friday window) | at least 1 trade |

Minimum trades elsewhere: 3. Result per run: **PASS**, **FAIL**, or **SKIP** (no report was produced, normally because the broker does not have the symbol or the history; the note gives the first matching tester-log line).

`results\ep04\tester\summary.md` has the table `case | symbol | tf | deposit | trades | errors found | result`, plus notes, the first error lines per case, the first EA journal lines per case, and the list of checks that remain manual (stop distance of about 2 bricks in case 1, one position at a time in cases 11 and 12, the gap behaviour of case 15, both account types for case 14).

Validation passes as a whole when there is no FAIL and at least one PASS; SKIP rows must be explained in the article (symbol not offered by the server).

## Outputs

| Path | Content |
|---|---|
| `results\verification\run_checks_<Mode>_<stamp>.log` | Timestamped transcript of the run |
| `results\verification\run_<Mode>_<stamp>\` | Every generated `.ini` and `.set` (audit trail) |
| `results\verification\sweep_compare.md` | Comparer result (Sweep) |
| `results\ep04\tester\summary.md` and `ep04_case*.htm` | Validation table and the tester reports |
| `<data folder>\RenkoVerify\` | Where the terminal writes the reports first (the `Report=` key is relative to the data folder) |
| `Common\Files\RenkoSweep_XAUUSD_MQL5_*.csv` | Raw MQL5 sweep output |

Exit code of `run_checks.ps1`: 0 all passed, 1 something failed, 2 could not start (terminal running, prerequisites missing, not confirmed).

## What to paste into the articles

- **Part 1 (engine and tests).** The Experts-tab screenshot has to be your own: attach `RenkoEngineTests` to a chart once by hand and capture the Experts tab. The kit's transcript line `RenkoEngineTests: N passed, M failed` must show the same numbers; quote them in the text (N counts checks, not the ten cases).
- **Part 2 and Part 3 (sweep).** Once `sweep_compare.md` says OVERALL: PASS, add a sentence that the MQL5 script reproduces the Python tables: row and cell counts from the comparer, integer columns exact, floats within 0.01. Use the numbers printed under `rows:` and `cells checked:`. If it fails, do not publish the sentence; the file lists the differing cells.
- **Part 4 (self-test checklist).** Copy the rows of `results\ep04\tester\summary.md` into the checklist table in `ep04.md` (Result column: PASS / SKIP with reason, trade count), remove the `[[TODO: run and record results]]` placeholders only for cases you actually ran, and complete the manual checks listed at the end of the summary. Keep the statement that no performance figure is claimed.

## MT5 config keys: what was checked

Checked against the official page https://www.metatrader5.com/en/terminal/help/start_advanced/start (fetched 2026-10-11 with `curl`, because the WebFetch tool could not resolve the host):

- Command line: `/config:<path>`, read-only use of a custom file.
- `[Experts]`: `AllowLiveTrading`, `AllowDllImport`, `Enabled`, `Account`, `Profile`.
- `[StartUp]`: `Script`, `ScriptParameters` (file in `MQL5\Presets`), `Symbol`, `Period`, `ShutdownTerminal` (scripts only).
- `[Tester]`: `Expert`, `ExpertParameters` (file in `MQL5\Profiles\Tester`), `Symbol`, `Period`, `Model` (0 every tick, 4 every tick based on real ticks), `ExecutionMode`, `Optimization`, `FromDate`, `ToDate` (`YYYY.MM.DD`), `ForwardMode`, `Deposit`, `Currency`, `Leverage` (`1:100`), `UseLocal`, `UseRemote`, `UseCloud`, `Visual`, `Report`, `ReplaceReport`, `ShutdownTerminal`.
- `[Common] Login` (account number; the page says the terminal reads the rest from its own account database).
- `Report` is documented as relative to the trading platform (data) directory with an existing subfolder, which is why the kit writes to `<data folder>\RenkoVerify\` and copies.

Not covered by the page, so check them on the first run:

- Whether the terminal logs in to its last account on its own when the custom config has no `[Common]` section. If the tester says the symbol is unknown or the terminal sits on "no connection", start the kit with `-Login <account number>`.
- Whether `[Experts] AllowLiveTrading=0` is ignored by the Strategy Tester. It is not meant to affect it; if every case shows 0 trades and a "trading disabled" message, tell me.
- Report parsing expects the English report ("Total Trades:"); a localised terminal needs the label adjusted in `Read-TesterReport`.
- Log file names and the UTF-16 format of the tester logs were taken from the existing files on this machine.

## If something goes wrong

- *Terminal appears to hang after the check finished.* The kit closes it with CloseMainWindow, waits 60 s, then force-closes and prints a warning. Look for a dialog box in the terminal.
- *Tests: no summary line.* Open `MQL5\Logs` for the day and look for `RenkoEngineTests`; recompile the script; check `EURUSD` exists on the server (change with `-ChartSymbol`).
- *Sweep: `cannot open ... in Common\Files`.* The hard link `Common\Files\XAUUSD_ticks.csv` is missing (see the header of `RenkoSweep.mq5`).
- *Validation: many SKIP.* The symbol names differ on your server; pass `-Symbols`/`-SymbolSuffix`. Model 4 needs the server to deliver real ticks; the kit retries once with model 0 unless you pass `-NoFallback`.
- *Errors found > 0 but nothing wrong.* The patterns are deliberately broad (`failed`, `error`); lines such as `failed ... [Market closed]` count. Read the lines in `summary.md` and use `-IgnoreRegex` if a line is harmless.
