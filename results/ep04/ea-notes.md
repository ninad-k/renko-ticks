# RenkoTickContinuationEA 1.00 - design notes and self-test sheet

Files
- EA: `MQL5\Experts\Renko\RenkoTickContinuationEA.mq5` (copy in `mql5\Experts\Renko\`)
- Helpers: `MQL5\Include\Renko\MarketSafe.mqh` (copy in `mql5\Include\Renko\`), `RenkoEngine.mqh` (unchanged)
- Status: compiled and scanned (0 errors, 0 warnings; scanner clean). **Never run in the Strategy Tester** (not allowed in this task). Everything in section 4 is still to be done by hand.

## 1. Design decisions and the validation risk each one addresses

The Market validator runs the EA on symbols and timeframes it chooses, with small deposits, on the MetaQuotes-Demo server, and rejects it for runtime errors or for never trading.

| Validation risk | Decision in the EA |
|---|---|
| **"There are no trading operations"** - defaults only fit one symbol | Brick size is `InpAtrFraction` (0.25) x ATR(14) of the last completed D1 bar, so a brick is always a sensible fraction of the symbol's daily range. Bricks are tick-driven, so the chart timeframe is irrelevant and the validator's timeframe choice cannot starve the EA of "bars". |
| **Fixed dollar brick sizes mean nothing on other symbols** (V1 default 1.0 = $1 on gold, EURUSD would never move 1.0) | Size mode enum: ATR fraction (default) or fixed points. The ATR is rounded to `SYMBOL_TRADE_TICK_SIZE`, minimum one tick. Refitted when a new D1 bar opens through `SetBrickSize`. Changes under 5 % are ignored so the grid is not re-anchored every day. |
| **ATR not ready at start / short history** | One `iATR(D1)` handle created in `OnInit`, never in `OnTick`. `CopyBuffer` result is checked (`!= 1` means not ready), the value is checked for NaN/zero/EMPTY_VALUE. While waiting: no trades. After `InpAtrWaitMinutes` (60) the EA starts with `InpBrickPoints` instead, and keeps retrying the ATR every 10 s, switching to it once available. An invalid handle falls back immediately. |
| **Warm-up starvation** (V1 needed 500 bricks) | `InpWarmupBricks` default 3. Optional tick replay of `InpWarmupDays` through `FeedHistory`, **off by default (0)** so the validator's many passes stay fast (2 is a sensible live setting); replay never produces trades (return values ignored), so old signals cannot fire. |
| **No tick history in the tester** | If `FeedHistory` builds 0 bricks the EA prints one line and keeps building bricks from live ticks. There is no dependence on the replay. |
| **"invalid volume" [10014]** | Fixed lot or risk-% lot both pass through `MS_NormalizeVolume`: round down to `SYMBOL_VOLUME_STEP`, clamp to MIN/MAX. `MS_CheckMarketOrder` re-verifies the volume is on the step. Zero or uncomputable volume skips the trade with a message. |
| **"not enough money" [10019]** | `MS_CheckMarketOrder` runs `OrderCalcMargin` against `ACCOUNT_MARGIN_FREE` before every order, plus `SYMBOL_VOLUME_LIMIT`. On failure the trade is skipped and the reason is printed. (The installed `Trade.mqh` sends `PositionOpen` straight to `OrderSend` without `OrderCheck`, so `MS_CheckMarketOrder` is the only margin gate.) Margin is checked after the old position is closed on a reversal, so the freed margin counts. |
| **"invalid stops" [10016]** | SL/TP are computed from the entry, then pushed out to `max(STOPS_LEVEL, FREEZE_LEVEL) + 1 tick` from bid (buy) / ask (sell), rounded to the tick grid in the direction away from the market. Buy SL is measured against bid, sell SL against ask (the prices that trigger them). `MS_StopsOk` re-verifies. An SL that would be <= 0 skips the trade. A sell TP <= 0 is dropped. |
| **Frozen position [10029]** | `MS_FreezeOk` before closing. If frozen, the wanted direction is kept in `g_pending_dir` (logged once) and `RetryPendingReversal` tries again on later ticks (at most once per tick-second) through `ExecuteSignal`, so close and open face every normal check. The pending reversal is cancelled and logged if the position disappears (stopped out: nothing is opened) or a newer signal in the position's own direction arrives. The EA never modifies positions, so there is no "no changes" [10025] risk. |
| **Trading disabled / close-only / long-only / short-only** | `MS_TradingAllowed` checks `TERMINAL_TRADE_ALLOWED`, `MQL_TRADE_ALLOWED`, account permissions and `SYMBOL_TRADE_MODE` per direction. The close path checks the two terminal/program permissions only, so a close-only symbol can still be closed. |
| **Netting vs hedging** | `ACCOUNT_MARGIN_MODE` is read. Hedging: find the position by symbol + magic. Netting: the same, and if a position with a different magic already sits on the symbol the signal is ignored (opening would silently merge into it). Reversal is always close-then-open, which is correct on both. |
| **Filling mode** | `SetTypeFillingBySymbol`, with `ORDER_FILLING_RETURN` when the symbol allows only that. `CTrade` adjusts further per execution mode. |
| **Unchecked trade results** | Every `Buy/Sell/PositionClose` is followed by a retcode check (DONE, PLACED, DONE_PARTIAL) and an English message with the code and description. |
| **Max spread / wide-spread symbols** | `InpMaxSpreadPoints` (0 = off, so the validator sees trades). One-time warning if the brick is under twice the spread. |
| **Gap / spike ticks** | `OnTick` of the engine returns n. The EA evaluates once per tick; the signal condition is `run >= InpSameBricks && run - n < InpSameBricks` (the run *first* reached the threshold during this tick), the same rule as V1 `Evaluate`. Phantom bricks never trigger extra trades. |
| **Rules / structure of the Market** | No `#import`, `WebRequest`, sockets, `iCustom`, files, `MessageBox`, `Alert`, `Comment`, links (only `#property link` to mql5.com), no account/server/broker checks, no expiry, no `MQL_TESTER` branch (identical behaviour in tester and live). English inputs/messages, input groups, `#property version "1.00"`. |
| **Runtime errors (array range, zero divide)** | Single-element buffer read with count check; brick >= 1 tick; `MS_SafeDiv` inside risk sizing; engine rejects bid <= 0; bad inputs return `INIT_PARAMETERS_INCORRECT` with a message. |

Inputs and defaults (version 1.00)

| Group | Input | Default |
|---|---|---|
| Brick size | `InpBrickMode` | ATR fraction |
| | `InpAtrFraction` / `InpAtrPeriod` / `InpAtrWaitMinutes` | 0.25 / 14 / 60 |
| | `InpBrickPoints` (fixed mode and ATR fallback) | 300 |
| Strategy | `InpSameBricks` / `InpSLBricks` / `InpTPBricks` | 2 / 2.0 / 0 (none) |
| | `InpCloseOnOpposite` | true |
| Warm-up | `InpWarmupBricks` | 3 |
| | `InpWarmupDays` | **0** (replay off; 2 for live use) |
| Money management | `InpLotMode` / `InpFixedLots` / `InpRiskPercent` | fixed / 0.01 / 1.0 |
| Filters and execution | `InpMaxSpreadPoints` / `InpSlippagePoints` | 0 (off) / 30 |
| | `InpMagic` | 26100401 |

Identity: `#property copyright "Copyright 2026, Ninad K"`, one `#property description` line (two short sentences), version 1.00.

Decisions that deviate from, or extend, V1
- V1 SL used entry minus distance with a post-hoc skip if inside the stops level. The new EA widens instead of skipping, because a skipped trade on a symbol with a large stops level is exactly the "no trading operations" failure.
- V1's chart-window/indicator attachment (`iCustom`, `ChartIndicatorAdd`, `MQL_TESTER`) is removed.
- V1's fixed SL/TP in points inputs are dropped (fixed points are the thing that does not transfer between symbols).
- The order comment and the engine history length are constants, not inputs.

## 2. MarketSafe.mqh

Code copied unchanged from the skill. Only the header comment was edited: the GitHub URL and the GPL-3.0 line are gone, replaced by "Copyright 2026, Ninad K. Pre-trade checks for MQL5 Market validation." It compiles with 0 errors and 0 warnings as part of the EA.

Helpers used: `MS_NormalizeVolume`, `MS_LotsForRisk`, `MS_CheckMarketOrder` (which calls `MS_TradingAllowed`, `MS_HasMargin`, `MS_VolumeLimitOk`, `MS_StopsOk`), `MS_FreezeOk`. Not used: `CMSNewBar`, `MS_HistoryReady` (no bar logic, bricks are tick-driven), `MS_CanPlacePending` (market orders only), `MS_PriceChanged` (no modifications).

Known behaviour of the helper worth remembering: `MS_NormalizeVolume` clamps *up* to the minimum lot, so in risk-% mode a very small risk budget still opens the minimum lot. The margin check then decides whether it is affordable.

## 3. Results

Compile (`MetaEditor64.exe`, log in `compile.log`):

```
Result: 0 errors, 0 warnings, 566 ms elapsed, cpu='X64 Regular'
```
Includes compiled: Trade\Trade.mqh (and its dependencies), Renko\RenkoEngine.mqh, Renko\MarketSafe.mqh.

Scanner (`scan_mq5.py`), `scan_before.txt` = RenkoContinuationEA_V1.mq5, `scan_after.txt` = RenkoTickContinuationEA.mq5:

| Finding | V1 (before) | New EA (after) |
|---|---|---|
| Errors | 0 | 0 |
| Warnings | 2 | 0 |
| warning `icustom-resource` (iCustom without `::` resource path) | line 130 | gone - no `iCustom` |
| warning `margin-check` (orders without margin check) | line 322 | gone - `MS_CheckMarketOrder` (OrderCalcMargin) |
| info `property-link` | line 1 | gone - `#property link` added |
| info `tester-behaviour` (MQL_TESTER) | lines 135, 142 | gone - no tester-dependent code |
| info `trade-mode` | line 322 | gone - `MS_TradingAllowed` checks `SYMBOL_TRADE_MODE` |
| Verdict | NEEDS REVIEW | No issues found by heuristics |

No warning remained in the new EA, so there was nothing to fix and no false positive to argue. `MarketSafe.mqh` and `RenkoEngine.mqh` also scan clean.

Caveat: the scanner is name-based (it accepts `MS_CheckMarketOrder` or `OrderCalcMargin` anywhere in the file). A clean scan means the checks exist, not that they work. Only the tester run shows that.

## 4. Strategy Tester self-test checklist (to be run by you)

Settings for all runs: expert `RenkoTickContinuationEA`, **default inputs** unless stated, model "Every tick" or "Every tick based on real ticks", about 2-4 weeks, MetaQuotes-Demo if you can connect to it (it is the validator's environment). Open the Journal tab, use the log viewer and filter to errors.

Pass criteria for every run: no red error lines, no `[10014]`, `[10016]`, `[10019]`, `[10029]`, no "array out of range", no "zero divide", at least a few trades, no `initialization failed`.

| # | Symbol | Timeframe | Deposit | What to check |
|---|---|---|---|---|
| 1 | EURUSD | M1 | 10 000 | Journal shows `brick size ... (daily ATR fraction)` and trades; SL distance about 2 bricks. |
| 2 | EURUSD | H4 | 10 000 | Same trade count as run 1 (timeframe must not matter). |
| 3 | GBPJPY or USDJPY | M15 | 10 000 | 3-digit symbol: brick rounded to tick size, stops valid. |
| 4 | XAUUSD | H1 | 10 000 | Large point value; lots 0.01 valid; trades occur. |
| 5 | A stock index (e.g. US500/DE40 equivalent on the demo) | M5 | 10 000 | Different tick size / lot step; stops level. |
| 6 | A crypto or exotic CFD if available | D1 | 10 000 | Very large price; lot step may be 0.01 or larger. |
| 7 | EURUSD | M1 | **1** (and 10, 100) | Expect `MarketSafe: not enough money ...` messages and **no** error 10019 from the server. This is the "tiny deposit" validator case. Note that with 1 USD an affordable minimum lot may not exist: the EA then correctly makes no trades. Check that this is a skipped trade with a printed reason, not an error. |
| 8 | Any, risk mode: `InpLotMode = Risk percent`, 1 % | H1 | 100 and 10 000 | No `[10014]`; lots on the volume step; at 100 USD the minimum lot is used. |
| 9 | Any, `InpBrickMode = Fixed points` | H1 | 10 000 | Starts immediately with `fixed points`. |
| 10 | Any symbol with sparse D1 history or a fresh tester start | any | 10 000 | Either ATR becomes ready, or after 60 minutes you see `daily ATR not available ..., using the fixed brick size`. The EA must never sit idle forever. |
| 11 | Any, `InpTPBricks = 1`, `InpSameBricks = 1` | M5 | 10 000 | TP orders accepted (no `[10016]`); many reversals; one position at a time. |
| 12 | Any, `InpCloseOnOpposite = false` | M5 | 10 000 | Opposite signals ignored while a trade is open. |
| 13 | Any, `InpMaxSpreadPoints = 1` | M5 | 10 000 | Trades skipped with a spread message, no errors. |
| 14 | Netting account if you have one (and a hedging one) | any | 10 000 | Never two positions on the symbol; reversal = close then open. |
| 15 | Tester start day = a Monday morning / after a weekend gap | any | 10 000 | Gap ticks produce one trade, not several. |
| 16 | Any symbol with a freeze level | M5 | 10 000 | Opposite signal while inside the freeze level → reversal retried on a later tick, no `[10029]`/frozen errors. Journal shows `reversal to ... pending` once, then either the close and the new order or `pending ... reversal cancelled`. |

Also read in the first journal lines: `started on <symbol>, hedging|netting account`, `brick size ...`, and, only when `InpWarmupDays` > 0, the warm-up line (`replayed N day(s) ...` or `no tick history for warm-up`). The default is 0, so make one extra pass with 2 to see the replay time in ms; the submission build keeps 0.

Before uploading
- Raise `#property version` for every later upload.
- Compile in the same MetaEditor build the Market uses, check `0 errors, 0 warnings`, and upload the single `.ex5`.

## 5. Unresolved / limits

- **Not run in the tester.** Compile and static scan only. All behaviour above is by design and code reading, not by observation.
- **A frozen reversal waits and can come late.** The pending reversal has no time limit, so it can execute some bricks after the signal, at the price of the retry tick. While the position stays frozen, `MS_FreezeOk` prints its own line on each retry (at most one per tick-second). Not exercised yet: see self-test row 16.
- **Fallback brick is symbol-dependent.** `InpBrickPoints = 300` (0.00300 = 30 pips on 5-digit EURUSD, about 45% of its daily range; 3 USD on gold; 3 index points on US500) only applies when the ATR cannot be read, or in fixed mode.
- **Tiny deposits can legitimately mean zero trades.** If the minimum lot's margin is above free margin, the EA skips every signal. Whether the validator accepts that depends on its deposit; the EA does the right thing (no server error).
- **Risk mode can exceed the requested risk** when the calculated lot is below the symbol minimum (helper clamps up).
- **Brick under 2 x spread** on a symbol with a wide spread or a tiny daily range: trades are allowed, only one warning is printed.
- The tick source for the engine is bid; entries use the real ask/bid of the signalling tick.
