//+------------------------------------------------------------------+
//|                                     RenkoTickContinuationEA.mq5  |
//|  Renko continuation strategy on tick-driven bricks, written to   |
//|  run unchanged on any symbol and timeframe.                      |
//|                                                                  |
//|  Rules (port of RenkoContinuationEA_V1)                          |
//|   1. Bricks come from CRenkoEngine, fed with every tick. Only    |
//|      CLOSED bricks are used, so a signal never repaints. The     |
//|      chart timeframe plays no role.                              |
//|   2. Entry: when a run of same-direction bricks FIRST reaches    |
//|      InpSameBricks (default 2) open a trade in that direction:   |
//|         up, up -> BUY          down, down -> SELL                |
//|      Longer runs do not re-trigger.                              |
//|   3. Stop loss InpSLBricks bricks from entry (default 2).        |
//|      Optional take profit InpTPBricks bricks (0 = none).         |
//|   4. Opposite signal: close and reverse (InpCloseOnOpposite),    |
//|      otherwise ignore it while a trade is open. If the position  |
//|      is inside the freeze level the reversal stays pending and   |
//|      is retried on later ticks; it is dropped if the position    |
//|      disappears or a newer signal follows the position.         |
//|   5. One position per symbol + magic number.                     |
//|   6. A tick that closes several bricks (a gap) is ONE decision:  |
//|      the engine returns n > 1 and we evaluate once, at the real  |
//|      bid/ask of that tick, never once per phantom brick.         |
//|                                                                  |
//|  Brick size                                                      |
//|   Default: InpAtrFraction x ATR(14) of the last COMPLETED D1     |
//|   bar, rounded to the symbol tick size. A fixed dollar size      |
//|   means nothing across symbols; a fraction of the daily range    |
//|   does. The size is refitted when a new D1 bar opens. If the ATR |
//|   is not available yet the EA waits (no trades) and, after       |
//|   InpAtrWaitMinutes, falls back to InpBrickPoints.               |
//|                                                                  |
//|  Market safety (see MarketSafe.mqh)                              |
//|   Before every order: trade permissions and symbol trade mode,   |
//|   lot normalised to step/min/max, free margin, volume limit,     |
//|   SL/TP widened to the stops/freeze level, optional spread cap.  |
//|   Every trade request result is checked and logged.              |
//|                                                                  |
//|  Warm-up                                                         |
//|   Optionally replays InpWarmupDays of tick history into the      |
//|   engine. Off by default (0) so the many passes of the Market    |
//|   validator stay fast; 2 days is a sensible live setting. If the |
//|   terminal has no ticks (e.g. in the tester) the EA keeps        |
//|   building bricks live. No trade is opened until InpWarmupBricks |
//|   bricks exist.                                                  |
//|                                                                  |
//|  Risk disclaimer                                                 |
//|   Trading involves risk of loss. Past results do not guarantee   |
//|   future performance.                                            |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Ninad K"
#property link      "https://www.mql5.com"
#property version   "1.00"
#property description "Trades the continuation of tick-driven Renko bricks, with a stop two bricks away. The brick size is a fraction of the daily ATR, so the same settings fit any symbol."

#include <Trade/Trade.mqh>
#include <Renko/RenkoEngine.mqh>
#include <Renko/MarketSafe.mqh>

//--- how the brick size is chosen
enum ENUM_BRICK_MODE
  {
   BRICK_ATR_FRACTION = 0,   // Fraction of the daily ATR
   BRICK_FIXED_POINTS = 1    // Fixed size in points
  };

//--- how the lot size is chosen
enum ENUM_LOT_MODE
  {
   LOT_FIXED        = 0,     // Fixed lot
   LOT_RISK_PERCENT = 1      // Percent of balance risked at the stop loss
  };

input group "Brick size"
input ENUM_BRICK_MODE InpBrickMode    = BRICK_ATR_FRACTION;  // Brick size mode
input double          InpAtrFraction  = 0.25;                // ATR mode: brick = fraction x daily ATR
input int             InpAtrPeriod    = 14;                  // ATR mode: daily ATR period
input int             InpAtrWaitMinutes = 60;                // ATR mode: minutes to wait for the ATR before using the fixed size
input int             InpBrickPoints  = 300;                 // Fixed mode (and ATR fallback): brick size in points

input group "Strategy"
input int             InpSameBricks   = 2;                   // Same-direction bricks needed for entry
input double          InpSLBricks     = 2.0;                 // Stop loss (bricks from entry)
input double          InpTPBricks     = 0.0;                 // Take profit (bricks from entry, 0 = none)
input bool            InpCloseOnOpposite = true;             // Close and reverse on an opposite signal

input group "Warm-up"
input int             InpWarmupBricks = 3;                   // Bricks needed before the first trade
input int             InpWarmupDays   = 0;                   // Days of tick history replayed at start (0 = off, 2 for live use)

input group "Money management"
input ENUM_LOT_MODE   InpLotMode      = LOT_FIXED;           // Lot size mode
input double          InpFixedLots    = 0.01;                // Fixed lot
input double          InpRiskPercent  = 1.0;                 // Risk mode: percent of balance per trade

input group "Trade filters and execution"
input int             InpMaxSpreadPoints = 0;                // Maximum spread to open a trade in points (0 = off)
input int             InpSlippagePoints  = 30;               // Maximum price deviation in points
input long            InpMagic        = 26100401;            // Magic number

//--- constants
#define EA_NAME            "RenkoTick"
#define EA_COMMENT         "RenkoTick"
#define ENGINE_HISTORY     256       // closed bricks kept by the engine
#define ATR_RETRY_SECONDS  10        // pause between ATR reads while the ATR is not ready
#define REFIT_BAND         0.05      // ignore daily brick changes smaller than 5 percent

//--- state
CTrade       g_trade;
CRenkoEngine g_engine;

int      g_atr_handle    = INVALID_HANDLE;  // one iATR(D1) handle, created in OnInit
bool     g_engine_ready  = false;           // engine initialised with a brick size
bool     g_brick_from_atr = false;          // current brick size comes from the ATR
bool     g_need_atr      = false;           // an ATR read is due (start-up or new D1 bar)
datetime g_last_d1       = 0;               // open time of the D1 bar last seen
datetime g_first_tick    = 0;               // time of the first tick, for the ATR timeout
datetime g_last_atr_try  = 0;               // time of the last ATR read attempt
bool     g_warm_reported = false;           // "warm-up complete" printed once
bool     g_spread_noted  = false;           // narrow-brick warning printed once
int      g_pending_dir   = 0;               // reversal wanted but blocked by the freeze level (+1 buy, -1 sell, 0 none)
datetime g_pending_try   = 0;               // tick time of the last retry, one retry per second

//+------------------------------------------------------------------+
//| Brick size helpers                                                |
//+------------------------------------------------------------------+
//--- round a price distance to the tick size, never below one tick
double RoundBrick(const double size)
  {
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick <= 0.0)
      tick = _Point;
   double b = MathRound(size / tick) * tick;
   if(b < tick)
      b = tick;
   return NormalizeDouble(b, _Digits);
  }

//--- fixed size in points as a price distance
double PointsBrick(void)
  {
   return RoundBrick((double)InpBrickPoints * _Point);
  }

//--- InpAtrFraction x ATR of the last completed D1 bar. False while the ATR is not ready.
bool ReadAtrBrick(double &brick)
  {
   if(g_atr_handle == INVALID_HANDLE)
      return false;
   double buf[1];
   if(CopyBuffer(g_atr_handle, 0, 1, 1, buf) != 1)   // shift 1 = last completed D1 bar
      return false;
   if(!MathIsValidNumber(buf[0]) || buf[0] <= 0.0 || buf[0] == EMPTY_VALUE)
      return false;
   brick = RoundBrick(InpAtrFraction * buf[0]);
   return brick > 0.0;
  }

//+------------------------------------------------------------------+
//| Engine start-up: initialise, then optionally replay tick history  |
//+------------------------------------------------------------------+
void StartEngine(const double brick, const datetime now, const bool from_atr)
  {
   if(!g_engine.Init(brick, ENGINE_HISTORY, RENKO_PRICE_BID))
     {
      PrintFormat("%s: engine could not be initialised with brick %s", EA_NAME, DoubleToString(brick, _Digits));
      return;
     }
   g_engine_ready   = true;
   g_brick_from_atr = from_atr;
   PrintFormat("%s: brick size %s (%s)", EA_NAME, DoubleToString(brick, _Digits),
               from_atr ? "daily ATR fraction" : "fixed points");

   if(InpWarmupDays > 0)
     {
      const uint t0 = GetTickCount();
      const long built = g_engine.FeedHistory(_Symbol, now - (datetime)InpWarmupDays * 86400, now);
      if(built > 0)
         PrintFormat("%s: warm-up replayed %d day(s) of ticks, %I64d bricks built in %u ms",
                     EA_NAME, InpWarmupDays, built, GetTickCount() - t0);
      else
         PrintFormat("%s: no tick history for warm-up, bricks will be built from live ticks", EA_NAME);
     }
  }

//+------------------------------------------------------------------+
//| Keeps the brick size current. Called on every tick; cheap unless  |
//| an ATR read is due.                                               |
//+------------------------------------------------------------------+
void ServiceBrickSize(const datetime now)
  {
   if(g_first_tick == 0)
      g_first_tick = now;

   //--- fixed size: set once
   if(InpBrickMode == BRICK_FIXED_POINTS)
     {
      if(!g_engine_ready)
         StartEngine(PointsBrick(), now, false);
      return;
     }

   //--- ATR mode: no handle means the ATR can never be read, start with the fixed size now
   if(g_atr_handle == INVALID_HANDLE)
     {
      if(!g_engine_ready)
         StartEngine(PointsBrick(), now, false);
      return;
     }

   //--- a new D1 bar makes a new "last completed bar": schedule a refit
   const datetime d1 = iTime(_Symbol, PERIOD_D1, 0);
   if(d1 != 0 && d1 != g_last_d1)
     {
      g_last_d1  = d1;
      g_need_atr = true;
     }
   if(!g_need_atr || now - g_last_atr_try < ATR_RETRY_SECONDS)
      return;
   g_last_atr_try = now;

   double brick = 0.0;
   if(ReadAtrBrick(brick))
     {
      g_need_atr = false;
      if(!g_engine_ready)
         StartEngine(brick, now, true);
      else
        {
         const double cur = g_engine.BrickSize();
         //--- small daily drifts are ignored so the brick grid is not re-anchored every day
         if(!g_brick_from_atr || MathAbs(brick - cur) >= REFIT_BAND * cur)
           {
            g_engine.SetBrickSize(brick);
            g_brick_from_atr = true;
            PrintFormat("%s: brick size refitted to %s (was %s)", EA_NAME,
                        DoubleToString(brick, _Digits), DoubleToString(cur, _Digits));
           }
        }
      return;
     }

   //--- ATR not ready: wait, but never forever
   if(!g_engine_ready && now - g_first_tick >= (datetime)InpAtrWaitMinutes * 60)
     {
      PrintFormat("%s: daily ATR not available after %d minute(s), using the fixed brick size", EA_NAME, InpAtrWaitMinutes);
      StartEngine(PointsBrick(), now, false);   // g_need_atr stays true: the ATR replaces it once ready
     }
  }

//+------------------------------------------------------------------+
//| Position helpers                                                  |
//+------------------------------------------------------------------+
//--- Finds our position. Returns +1 long, -1 short, 0 none.
//--- foreign is set when a netting account already holds another EA's position on this symbol.
int FindPosition(ulong &ticket, bool &foreign)
  {
   ticket  = 0;
   foreign = false;
   const bool hedging = ((ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      if(PositionGetSymbol(i) != _Symbol)
         continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic)
        {
         if(!hedging)
            foreign = true;   // netting: one position per symbol, it is not ours
         continue;
        }
      ticket = (ulong)PositionGetInteger(POSITION_TICKET);
      return (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
     }
   return 0;
  }

//--- true when the last CTrade request was accepted
bool RequestAccepted(void)
  {
   const uint rc = g_trade.ResultRetcode();
   return (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_PLACED || rc == TRADE_RETCODE_DONE_PARTIAL);
  }

//--- smallest distance from price at which SL/TP are accepted
double MinStopDistance(void)
  {
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick <= 0.0)
      tick = _Point;
   const long stops  = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   const long freeze = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   //--- one extra tick: the broker rule is "farther than", not "at least"
   return (double)MathMax(stops, freeze) * _Point + tick;
  }

//--- round a price to the tick grid, up or down (always away from the market when used for SL/TP)
double TickFloor(const double price)
  {
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick <= 0.0)
      tick = _Point;
   return NormalizeDouble(MathFloor(price / tick + 1e-9) * tick, _Digits);
  }

double TickCeil(const double price)
  {
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick <= 0.0)
      tick = _Point;
   return NormalizeDouble(MathCeil(price / tick - 1e-9) * tick, _Digits);
  }

//+------------------------------------------------------------------+
//| Close our position (used before a reversal)                       |
//+------------------------------------------------------------------+
bool ClosePosition(const ulong ticket, const int pos_dir)
  {
   if(TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) == 0 || MQLInfoInteger(MQL_TRADE_ALLOWED) == 0)
     {
      PrintFormat("%s: cannot close, algo trading is disabled in the terminal or program settings", EA_NAME);
      return false;
     }
   if(!PositionSelectByTicket(ticket))
      return false;
   //--- a position whose SL/TP sit inside the freeze level cannot be changed or closed now
   if(!MS_FreezeOk(_Symbol, pos_dir > 0, PositionGetDouble(POSITION_SL), PositionGetDouble(POSITION_TP)))
     {
      if(g_pending_dir != -pos_dir)   // remember the wanted direction, log the change once
        {
         g_pending_dir = -pos_dir;
         PrintFormat("%s: reversal to %s pending, #%I64u is inside the freeze level, retrying on later ticks",
                     EA_NAME, g_pending_dir > 0 ? "BUY" : "SELL", ticket);
        }
      return false;
     }
   ResetLastError();
   g_trade.PositionClose(ticket);
   if(!RequestAccepted())
     {
      PrintFormat("%s: close of #%I64u failed, code %u (%s)", EA_NAME, ticket,
                  g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());
      return false;
     }
   g_pending_dir = 0;
   PrintFormat("%s: position #%I64u closed on the opposite signal", EA_NAME, ticket);
   return true;
  }

//+------------------------------------------------------------------+
//| Open a market position in direction dir (+1 buy, -1 sell)         |
//+------------------------------------------------------------------+
bool OpenPosition(const int dir, const MqlTick &tick)
  {
   const bool is_buy = (dir > 0);
   const string side = is_buy ? "BUY" : "SELL";

   //--- optional spread cap
   if(InpMaxSpreadPoints > 0)
     {
      const double spread_pts = (tick.ask - tick.bid) / _Point;
      if(spread_pts > (double)InpMaxSpreadPoints)
        {
         PrintFormat("%s: %s skipped, spread %.0f points is above the limit of %d", EA_NAME, side, spread_pts, InpMaxSpreadPoints);
         return false;
        }
     }

   //--- stop loss and take profit, measured from the entry price
   const double brick    = g_engine.BrickSize();
   const double entry    = is_buy ? tick.ask : tick.bid;
   const double min_dist = MinStopDistance();
   double sl = 0.0, tp = 0.0;
   if(is_buy)
     {
      sl = MathMin(entry - InpSLBricks * brick, tick.bid - min_dist);   // widen to the minimum distance
      sl = TickFloor(sl);
      if(InpTPBricks > 0.0)
         tp = TickCeil(MathMax(entry + InpTPBricks * brick, tick.bid + min_dist));
     }
   else
     {
      sl = MathMax(entry + InpSLBricks * brick, tick.ask + min_dist);
      sl = TickCeil(sl);
      if(InpTPBricks > 0.0)
        {
         tp = TickFloor(MathMin(entry - InpTPBricks * brick, tick.ask - min_dist));
         if(tp <= 0.0)
            tp = 0.0;   // a target at or below zero is impossible: trade without it
        }
     }
   if(sl <= 0.0)
     {
      PrintFormat("%s: %s skipped, the stop loss would be at or below zero", EA_NAME, side);
      return false;
     }

   //--- lot size, always on the volume step and inside min/max
   double lots = 0.0;
   if(InpLotMode == LOT_RISK_PERCENT)
      lots = MS_LotsForRisk(_Symbol, AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPercent / 100.0, MathAbs(entry - sl));
   else
      lots = MS_NormalizeVolume(_Symbol, InpFixedLots);
   if(lots <= 0.0)
     {
      PrintFormat("%s: %s skipped, the lot size could not be calculated", EA_NAME, side);
      return false;
     }

   //--- permissions, symbol trade mode, free margin, volume limit, stops level
   const ENUM_ORDER_TYPE type = is_buy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   if(!MS_CheckMarketOrder(_Symbol, type, lots, sl, tp))
     {
      PrintFormat("%s: %s skipped by the pre-trade checks", EA_NAME, side);
      return false;
     }

   //--- send and verify
   ResetLastError();
   if(is_buy)
      g_trade.Buy(lots, _Symbol, 0.0, sl, tp, EA_COMMENT);
   else
      g_trade.Sell(lots, _Symbol, 0.0, sl, tp, EA_COMMENT);
   if(!RequestAccepted())
     {
      PrintFormat("%s: %s %.2f lots failed, code %u (%s)", EA_NAME, side, lots,
                  g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());
      return false;
     }
   PrintFormat("%s: %s %.2f lots opened at %s, SL %s, TP %s", EA_NAME, side, lots,
               DoubleToString(g_trade.ResultPrice(), _Digits), DoubleToString(sl, _Digits),
               tp > 0.0 ? DoubleToString(tp, _Digits) : "none");
   return true;
  }

//--- drop a pending reversal and say why
void CancelPending(const string why)
  {
   PrintFormat("%s: pending %s reversal cancelled, %s", EA_NAME, g_pending_dir > 0 ? "BUY" : "SELL", why);
   g_pending_dir = 0;
  }

//+------------------------------------------------------------------+
//| Act on a signal: keep, reverse, or open                           |
//+------------------------------------------------------------------+
void ExecuteSignal(const int dir, const MqlTick &tick)
  {
   ulong ticket;
   bool  foreign;
   const int pos = FindPosition(ticket, foreign);
   if(foreign)
     {
      PrintFormat("%s: signal ignored, another program holds the netting position on %s", EA_NAME, _Symbol);
      return;
     }
   if(pos == dir)
     {
      if(g_pending_dir != 0)
         CancelPending("a newer signal follows the open position");
      return;                               // already positioned this way
     }
   if(pos == -dir)
     {
      if(!InpCloseOnOpposite)
         return;                            // opposite signal ignored while a trade is open
      if(!ClosePosition(ticket, pos))
         return;
     }
   OpenPosition(dir, tick);
  }

//+------------------------------------------------------------------+
//| Retry a reversal that was blocked by the freeze level             |
//+------------------------------------------------------------------+
void RetryPendingReversal(const MqlTick &tick)
  {
   if(g_pending_dir == 0 || tick.time == g_pending_try)
      return;
   g_pending_try = tick.time;
   ulong ticket;
   bool  foreign;
   if(FindPosition(ticket, foreign) != -g_pending_dir)
     {
      CancelPending("the position is gone, no trade opened");   // e.g. stopped out
      return;
     }
   ExecuteSignal(g_pending_dir, tick);   // closes once MS_FreezeOk passes, then opens through the normal checks
  }

//+------------------------------------------------------------------+
//| Called once for each tick that closed at least one brick          |
//+------------------------------------------------------------------+
void OnBricksClosed(const int n, const MqlTick &tick)
  {
   if(g_engine.TotalBricks() < InpWarmupBricks)
      return;
   if(!g_warm_reported)
     {
      g_warm_reported = true;
      PrintFormat("%s: warm-up complete, %I64d bricks built", EA_NAME, g_engine.TotalBricks());
     }

   //--- narrow bricks make a stop that sits inside the spread; say so once
   if(!g_spread_noted && g_engine.BrickSize() < 2.0 * (tick.ask - tick.bid))
     {
      g_spread_noted = true;
      PrintFormat("%s: the brick (%s) is smaller than twice the spread, expect costly trades",
                  EA_NAME, DoubleToString(g_engine.BrickSize(), _Digits));
     }

   //--- the run counts bricks in the current direction. A signal exists when the run
   //--- reached InpSameBricks during THIS tick (n bricks were added by it).
   const int dir = g_engine.Direction();
   const int run = g_engine.RunLength();
   if(dir == 0 || run < InpSameBricks || run - n >= InpSameBricks)
      return;
   ExecuteSignal(dir, tick);
  }

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit(void)
  {
   if(InpSameBricks < 1 || InpSLBricks <= 0.0 || InpTPBricks < 0.0 || InpWarmupBricks < 0 ||
      InpWarmupDays < 0 || InpAtrFraction <= 0.0 || InpAtrPeriod < 1 || InpAtrWaitMinutes < 0 ||
      InpBrickPoints < 1 || InpFixedLots <= 0.0 || InpRiskPercent <= 0.0 ||
      InpMaxSpreadPoints < 0 || InpSlippagePoints < 0)
     {
      PrintFormat("%s: invalid input parameters, please check the values", EA_NAME);
      return INIT_PARAMETERS_INCORRECT;
     }
   if(_Point <= 0.0)
     {
      PrintFormat("%s: symbol %s has no valid point size", EA_NAME, _Symbol);
      return INIT_FAILED;
     }

   g_trade.SetExpertMagicNumber((ulong)InpMagic);
   g_trade.SetDeviationInPoints((ulong)InpSlippagePoints);
   if(!g_trade.SetTypeFillingBySymbol(_Symbol))
      g_trade.SetTypeFilling(ORDER_FILLING_RETURN);   // exchange symbols that only allow "return"

   //--- the only indicator handle, created once
   g_atr_handle = INVALID_HANDLE;
   if(InpBrickMode == BRICK_ATR_FRACTION)
     {
      g_atr_handle = iATR(_Symbol, PERIOD_D1, InpAtrPeriod);
      if(g_atr_handle == INVALID_HANDLE)
         PrintFormat("%s: could not create the daily ATR, using the fixed brick size", EA_NAME);
     }

   g_engine_ready   = false;
   g_brick_from_atr = false;
   g_need_atr       = (InpBrickMode == BRICK_ATR_FRACTION);
   g_last_d1        = 0;
   g_first_tick     = 0;
   g_last_atr_try   = 0;
   g_warm_reported  = false;
   g_spread_noted   = false;
   g_pending_dir    = 0;
   g_pending_try    = 0;

   PrintFormat("%s: started on %s, %s account", EA_NAME, _Symbol,
               ((ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
               ? "hedging" : "netting or exchange");
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
//| Expert deinitialization                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(g_atr_handle != INVALID_HANDLE)
      IndicatorRelease(g_atr_handle);
  }

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTick(void)
  {
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick) || tick.bid <= 0.0 || tick.ask <= 0.0)
      return;

   ServiceBrickSize(tick.time);          // wait for / refit the brick size
   if(!g_engine_ready)
      return;                            // no brick size yet: no trades, but never blocked for ever

   RetryPendingReversal(tick);           // a reversal blocked by the freeze level

   const int n = g_engine.OnTick(tick);  // bricks closed by this tick
   if(n > 0)
      OnBricksClosed(n, tick);           // one decision per tick, even after a gap
  }
//+------------------------------------------------------------------+
