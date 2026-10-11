//+------------------------------------------------------------------+
//|                                                   MarketSafe.mqh |
//|   Copyright 2026, Ninad K. Pre-trade checks for MQL5 Market      |
//|   validation.                                                    |
//+------------------------------------------------------------------+
//
// Usage (MQL5):
//
//   #include "MarketSafe.mqh"
//
//   CMSNewBar g_newbar;
//
//   void OnTick()
//     {
//      if(!g_newbar.Check(_Symbol, _Period))
//         return;
//      if(!MS_HistoryReady(_Symbol, _Period, 200))
//         return;
//
//      double sl_dist = ...;                              // price distance
//      double lots    = MS_LotsForRisk(_Symbol, AccountInfoDouble(ACCOUNT_EQUITY) * 0.01, sl_dist);
//      double ask     = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
//      double sl      = ask - sl_dist;
//      double tp      = ask + 2.0 * sl_dist;
//
//      if(MS_CheckMarketOrder(_Symbol, ORDER_TYPE_BUY, lots, sl, tp))
//         trade.Buy(lots, _Symbol, 0.0, sl, tp);
//     }
//
// Every check prints the reason when it fails, so the tester journal
// explains why a trade was skipped instead of showing a trade error.
//+------------------------------------------------------------------+
#ifndef MARKET_SAFE_MQH
#define MARKET_SAFE_MQH

//+------------------------------------------------------------------+
//| True for sell-side order types                                    |
//+------------------------------------------------------------------+
bool MS_IsSellType(const ENUM_ORDER_TYPE type)
  {
   return(type == ORDER_TYPE_SELL || type == ORDER_TYPE_SELL_LIMIT ||
          type == ORDER_TYPE_SELL_STOP || type == ORDER_TYPE_SELL_STOP_LIMIT);
  }

//+------------------------------------------------------------------+
//| Terminal, program, account and symbol all allow this direction    |
//+------------------------------------------------------------------+
bool MS_TradingAllowed(const string symbol, const bool is_buy)
  {
   if(TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) == 0 || MQLInfoInteger(MQL_TRADE_ALLOWED) == 0)
     {
      Print("MarketSafe: algo trading is disabled in the terminal or program settings");
      return(false);
     }
   if(AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) == 0 || AccountInfoInteger(ACCOUNT_TRADE_EXPERT) == 0)
     {
      Print("MarketSafe: trading is not allowed on this account");
      return(false);
     }
   long mode = SymbolInfoInteger(symbol, SYMBOL_TRADE_MODE);
   if(mode == SYMBOL_TRADE_MODE_DISABLED || mode == SYMBOL_TRADE_MODE_CLOSEONLY ||
      (is_buy && mode == SYMBOL_TRADE_MODE_SHORTONLY) ||
      (!is_buy && mode == SYMBOL_TRADE_MODE_LONGONLY))
     {
      PrintFormat("MarketSafe: %s does not allow opening %s trades now (trade mode %d)",
                  symbol, is_buy ? "buy" : "sell", (int)mode);
      return(false);
     }
   return(true);
  }

//+------------------------------------------------------------------+
//| Round a volume down to the symbol step and clamp it to min/max.   |
//| Note: a result equal to the minimum volume may carry more risk    |
//| than requested; the margin check still applies afterwards.        |
//+------------------------------------------------------------------+
double MS_NormalizeVolume(const string symbol, const double lots)
  {
   double vmin  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double vmax  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double vstep = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   if(vstep <= 0.0)
      vstep = vmin;
   if(vstep <= 0.0)
      return(0.0);

   double volume = MathFloor(lots / vstep + 1e-7) * vstep;
   if(volume < vmin)
      volume = vmin;
   if(vmax > 0.0 && volume > vmax)
      volume = vmax;

   int digits = (int)MathMax(0.0, MathCeil(-MathLog10(vstep) - 1e-9));
   return(NormalizeDouble(volume, digits));
  }

//+------------------------------------------------------------------+
//| Division that cannot raise "zero divide"                          |
//+------------------------------------------------------------------+
double MS_SafeDiv(const double numerator, const double denominator, const double fallback = 0.0)
  {
   if(MathAbs(denominator) < 1e-12)
      return(fallback);
   return(numerator / denominator);
  }

//+------------------------------------------------------------------+
//| Volume that risks roughly risk_money if price moves sl_distance   |
//| (a price distance, not points) against the position.              |
//+------------------------------------------------------------------+
double MS_LotsForRisk(const string symbol, const double risk_money, const double sl_distance)
  {
   double tick_value = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
   double tick_size  = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
   double loss_per_lot = MS_SafeDiv(sl_distance, tick_size) * tick_value;
   if(loss_per_lot <= 0.0 || risk_money <= 0.0)
      return(0.0);
   return(MS_NormalizeVolume(symbol, risk_money / loss_per_lot));
  }

//+------------------------------------------------------------------+
//| Free margin covers the order (market or pending)                  |
//+------------------------------------------------------------------+
bool MS_HasMargin(const string symbol, const ENUM_ORDER_TYPE type, const double lots, double price = 0.0)
  {
   bool is_sell = MS_IsSellType(type);
   if(price <= 0.0)
     {
      MqlTick tick;
      if(!SymbolInfoTick(symbol, tick))
        {
         PrintFormat("MarketSafe: no current tick for %s", symbol);
         return(false);
        }
      price = is_sell ? tick.bid : tick.ask;
     }

   double margin = 0.0;
   ResetLastError();
   if(!OrderCalcMargin(is_sell ? ORDER_TYPE_SELL : ORDER_TYPE_BUY, symbol, lots, price, margin))
     {
      PrintFormat("MarketSafe: OrderCalcMargin failed for %s, error %d", symbol, GetLastError());
      return(false);
     }
   double free_margin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   if(margin > free_margin)
     {
      PrintFormat("MarketSafe: not enough money for %.2f lots %s (needs %.2f, free %.2f)",
                  lots, symbol, margin, free_margin);
      return(false);
     }
   return(true);
  }

//+------------------------------------------------------------------+
//| The account limit on pending orders is not reached                |
//+------------------------------------------------------------------+
bool MS_CanPlacePending(void)
  {
   long limit = AccountInfoInteger(ACCOUNT_LIMIT_ORDERS);
   if(limit > 0 && OrdersTotal() >= limit)
     {
      PrintFormat("MarketSafe: pending order limit reached (%d)", (int)limit);
      return(false);
     }
   return(true);
  }

//+------------------------------------------------------------------+
//| Positions + pending orders on the symbol stay within              |
//| SYMBOL_VOLUME_LIMIT after adding add_volume                       |
//+------------------------------------------------------------------+
bool MS_VolumeLimitOk(const string symbol, const double add_volume)
  {
   double limit = SymbolInfoDouble(symbol, SYMBOL_VOLUME_LIMIT);
   if(limit <= 0.0)
      return(true);

   double used = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      if(PositionGetSymbol(i) == symbol)
         used += PositionGetDouble(POSITION_VOLUME);
     }
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong ticket = OrderGetTicket(i);
      if(ticket > 0 && OrderGetString(ORDER_SYMBOL) == symbol)
         used += OrderGetDouble(ORDER_VOLUME_CURRENT);
     }
   if(used + add_volume > limit + 1e-8)
     {
      PrintFormat("MarketSafe: volume limit %.2f on %s would be exceeded (in use %.2f, adding %.2f)",
                  limit, symbol, used, add_volume);
      return(false);
     }
   return(true);
  }

//+------------------------------------------------------------------+
//| SL/TP lie on the correct side and further than distance from the  |
//| closing price (Bid for buys, Ask for sells). 0 = level not set.   |
//+------------------------------------------------------------------+
bool MS_LevelsClear(const bool is_buy, const MqlTick &tick, const double sl, const double tp, const double distance)
  {
   if(is_buy)
     {
      if(sl > 0.0 && tick.bid - sl <= distance)
         return(false);
      if(tp > 0.0 && tp - tick.bid <= distance)
         return(false);
     }
   else
     {
      if(sl > 0.0 && sl - tick.ask <= distance)
         return(false);
      if(tp > 0.0 && tick.ask - tp <= distance)
         return(false);
     }
   return(true);
  }

//+------------------------------------------------------------------+
//| SL/TP respect SYMBOL_TRADE_STOPS_LEVEL (new orders, new levels).  |
//| buffer_points adds safety for servers that report 0 but still     |
//| reject stops placed inside the spread.                            |
//+------------------------------------------------------------------+
bool MS_StopsOk(const string symbol, const bool is_buy, const double sl, const double tp, const int buffer_points = 0)
  {
   MqlTick tick;
   if(!SymbolInfoTick(symbol, tick))
      return(false);
   double point    = SymbolInfoDouble(symbol, SYMBOL_POINT);
   double distance = (double)(SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL) + buffer_points) * point;
   if(!MS_LevelsClear(is_buy, tick, sl, tp, distance))
     {
      PrintFormat("MarketSafe: SL %.5f / TP %.5f too close to price or on the wrong side for %s (min distance %.5f)",
                  sl, tp, symbol, distance);
      return(false);
     }
   return(true);
  }

//+------------------------------------------------------------------+
//| An existing position's current SL/TP are outside the freeze level |
//| so it may be modified or closed now                               |
//+------------------------------------------------------------------+
bool MS_FreezeOk(const string symbol, const bool is_buy, const double current_sl, const double current_tp)
  {
   MqlTick tick;
   if(!SymbolInfoTick(symbol, tick))
      return(false);
   double point    = SymbolInfoDouble(symbol, SYMBOL_POINT);
   double distance = (double)SymbolInfoInteger(symbol, SYMBOL_TRADE_FREEZE_LEVEL) * point;
   if(distance <= 0.0)
      return(true);
   if(!MS_LevelsClear(is_buy, tick, current_sl, current_tp, distance))
     {
      PrintFormat("MarketSafe: %s position is inside the freeze level (%.5f); not modifying now", symbol, distance);
      return(false);
     }
   return(true);
  }

//+------------------------------------------------------------------+
//| A level really changed (avoids "no changes" modify requests)      |
//+------------------------------------------------------------------+
bool MS_PriceChanged(const string symbol, const double old_price, const double new_price)
  {
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   return(NormalizeDouble(old_price, digits) != NormalizeDouble(new_price, digits));
  }

//+------------------------------------------------------------------+
//| Enough synchronised history to calculate on                       |
//+------------------------------------------------------------------+
bool MS_HistoryReady(const string symbol, const ENUM_TIMEFRAMES tf, const int bars_needed)
  {
   if(SeriesInfoInteger(symbol, tf, SERIES_SYNCHRONIZED) == 0)
      return(false);
   return(Bars(symbol, tf) >= bars_needed);
  }

//+------------------------------------------------------------------+
//| New-bar detector; call from OnTick so a tick always exists.       |
//| Use one instance per symbol/timeframe pair.                       |
//+------------------------------------------------------------------+
class CMSNewBar
  {
private:
   datetime          m_last_bar;

public:
                     CMSNewBar(void) : m_last_bar(0) {}

   bool              Check(const string symbol, const ENUM_TIMEFRAMES tf)
     {
      datetime bar_time = iTime(symbol, tf, 0);
      if(bar_time == 0 || bar_time == m_last_bar)
         return(false);
      m_last_bar = bar_time;
      return(true);
     }
  };

//+------------------------------------------------------------------+
//| All checks for a new market order in one call                     |
//| (lots should already come from MS_NormalizeVolume/MS_LotsForRisk) |
//+------------------------------------------------------------------+
bool MS_CheckMarketOrder(const string symbol, const ENUM_ORDER_TYPE type, const double lots,
                         const double sl, const double tp)
  {
   bool is_buy = !MS_IsSellType(type);
   if(lots <= 0.0)
     {
      Print("MarketSafe: volume is zero, skipping trade");
      return(false);
     }
   if(MathAbs(MS_NormalizeVolume(symbol, lots) - lots) > 1e-8)
     {
      PrintFormat("MarketSafe: volume %.4f is not valid for %s; use MS_NormalizeVolume()", lots, symbol);
      return(false);
     }
   return(MS_TradingAllowed(symbol, is_buy) &&
          MS_HasMargin(symbol, type, lots) &&
          MS_VolumeLimitOk(symbol, lots) &&
          MS_StopsOk(symbol, is_buy, sl, tp));
  }

#endif // MARKET_SAFE_MQH
//+------------------------------------------------------------------+
