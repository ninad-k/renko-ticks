# Part 2 facts (computed by python/analyze.py from the Python port of RenkoSweep)

Units: $ per oz per 1 unit traded. Commission 0.035 per side. Fills on the next tick at real bid/ask.
A = always-in flip-follow; B = impulse>=3 / pullback<=2 / resumption. theo = same trades filled at
the brick boundary with zero spread and no commission.

- Data: 641,645,959 XAUUSD ticks, 2301 trading days (22:00 UTC day), 2017-10 to 2026-09-02.
- 2017: avg spread $0.0921, avg daily range $11.48, ticks 10,667,893
- 2020: avg spread $0.2950, avg daily range $30.91, ticks 143,862,879
- 2024: avg spread $0.1588, avg daily range $33.06, ticks 55,999,032
- 2025: avg spread $0.3514, avg daily range $60.88, ticks 68,007,695
- 2026: avg spread $0.6617, avg daily range $129.39, ticks 66,818,305
- $0.50: flip-follow A 1,020,953 trades, theo +283,420 (+0.278/trade), net -831,746 (-0.815/trade), gap 1.092/trade = 218% of a brick; phantom 10.36%, sub-second 20.72%, spread 135.9% of brick, overshoot $0.096
- $1.00: flip-follow A 308,952 trades, theo +95,064 (+0.308/trade), net -300,788 (-0.974/trade), gap 1.281/trade = 128% of a brick; phantom 5.55%, sub-second 11.94%, spread 80.1% of brick, overshoot $0.143
- $2.00: flip-follow A 87,223 trades, theo +23,974 (+0.275/trade), net -99,952 (-1.146/trade), gap 1.421/trade = 71% of a brick; phantom 2.76%, sub-second 5.86%, spread 46.0% of brick, overshoot $0.198
- $5.00: flip-follow A 14,739 trades, theo +7,110 (+0.482/trade), net -17,102 (-1.160/trade), gap 1.643/trade = 33% of a brick; phantom 1.57%, sub-second 1.53%, spread 20.5% of brick, overshoot $0.278
- $20.00: flip-follow A 938 trades, theo +2,720 (+2.900/trade), net +788 (+0.840/trade), gap 2.059/trade = 10% of a brick; phantom 0.51%, sub-second 0.20%, spread 6.1% of brick, overshoot $0.487
- Fixed sizes with positive theo for A: 16 of 16; positive net: ['$20.00', '$25.00', '$30.00', '$40.00', '$50.00']
- ATR sizes with positive net for A: ['0.40xATR', '0.50xATR', '0.75xATR', '1.00xATR']
- Overshoot fixed_2: 266,115 closing ticks, median 0.040 bricks, p90 0.270, p99 0.775, max 1.0, share > 0.5 brick 3.63%
- Overshoot fixed_10: 11,479 closing ticks, median 0.011 bricks, p90 0.093, p99 0.538, max 1.0, share > 0.5 brick 1.14%
- Overshoot atr_0.30: 8,070 closing ticks, median 0.006 bricks, p90 0.058, p99 0.554, max 1.0, share > 0.5 brick 1.14%

## Bad-quote filter (spread > 25x running mean spread, EMA over ~1000 accepted ticks, no look-ahead)

- XAUUSD: 18,279 of 641,664,238 ticks rejected (0.0028%). By year (>$20 spreads, unfiltered scan): 2020 4, 2023 12, 2024 81, 2025 2,722, 2026 2,112.
- Worst example: 2026-05-01 00:00:00.049 UTC bid 4326.34 ask 4626.12 (spread $299.78, market ~4628): unfiltered it printed 150 $2 bricks down and the next tick 148 back up. Another: 2023-05-05 00:00:00.197 bid 1989.97 ask 2049.95 (spread $59.98).
- EURUSD (May-Sep 2026 broker data): 1,873 of 8.57M ticks rejected. US500: 0.
- Effect on phantom bricks (unfiltered -> filtered):
  - $1.00: phantom 5.76% -> 5.55% (4% of the raw phantom bricks came from rejected quotes); A theo +97,158 -> +95,064; mean run 3.314 -> 3.308
  - $2.00: phantom 3.11% -> 2.76% (12% of the raw phantom bricks came from rejected quotes); A theo +25,846 -> +23,974; mean run 3.148 -> 3.137
  - $5.00: phantom 2.21% -> 1.57% (30% of the raw phantom bricks came from rejected quotes); A theo +8,170 -> +7,110; mean run 3.110 -> 3.096
  - $10.00: phantom 1.69% -> 0.90% (48% of the raw phantom bricks came from rejected quotes); A theo +4,420 -> +4,220; mean run 3.117 -> 3.113
  - $20.00: phantom 1.37% -> 0.51% (63% of the raw phantom bricks came from rejected quotes); A theo +2,680 -> +2,720; mean run 3.141 -> 3.145
  - $50.00: phantom 1.17% -> 0.00% (100% of the raw phantom bricks came from rejected quotes); A theo +3,500 -> +3,100; mean run 3.483 -> 3.428
  - 0.30xATR: phantom 1.68% -> 1.14% (32% of the raw phantom bricks came from rejected quotes); A theo +2,603 -> +2,403; mean run 3.043 -> 3.036
  - 1.00xATR: phantom 0.40% -> 0.13% (67% of the raw phantom bricks came from rejected quotes); A theo +4,527 -> +4,817; mean run 3.559 -> 3.559
