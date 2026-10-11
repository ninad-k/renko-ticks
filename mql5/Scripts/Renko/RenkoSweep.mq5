//+------------------------------------------------------------------+
//|                                                   RenkoSweep.mq5 |
//|                                          Copyright 2026, Ninad K |
//|  Brick-size sweep over raw tick data, one pass, all sizes at once |
//|                                                                  |
//|  Tick source                                                     |
//|   SRC_CSV_COMMON : a tick CSV inside <Common>\Files (MQL5 cannot |
//|                    read outside its sandbox). For a QuantData-   |
//|                    Manager export, hard-link it instead of       |
//|                    copying 27 GB:                                |
//|     mklink /H "%APPDATA%\MetaQuotes\Terminal\Common\Files\XAUUSD_ticks.csv" ^
//|               "C:\QuantDataManager125\export\<export>.csv"       |
//|   SRC_TERMINAL   : the terminal's own tick history of InpSymbol  |
//|                                                                  |
//|  Output (written to <Common>\Files)                              |
//|   <prefix>_summary.csv : one row per brick size per year + ALL   |
//|   <prefix>_dataset.csv : per-year ticks, spread, ATR, path length|
//|   <prefix>_bricks.csv  : every brick of InpDumpBrick (optional)  |
//+------------------------------------------------------------------+
#property script_show_inputs
#property copyright "Copyright 2026, Ninad K"
#property link      "https://www.mql5.com/en/users/nkulkarni"
#property version   "1.00"
#property description "Renko brick-size sweep on tick data: cost, edge and net per brick size."

#include <Renko\RenkoSweep.mqh>
#include <Renko\TickCsvReader.mqh>

enum ENUM_SWEEP_SOURCE
  {
   SRC_CSV_COMMON = 0,   // Tick CSV in Common\Files
   SRC_TERMINAL   = 1    // Terminal tick history
  };

input ENUM_SWEEP_SOURCE InpSource          = SRC_CSV_COMMON;
input string            InpCsvFile         = "XAUUSD_ticks.csv";   // CSV file name in Common\Files
input string            InpSymbol          = "XAUUSD";             // Symbol (terminal source)
input datetime          InpFrom            = 0;                    // From (0 = start of data)
input datetime          InpTo              = 0;                    // To   (0 = end of data)
input string            InpFixedSizes      = "0.5,1,2,3,4,5,6,8,10,12,15,20,25,30,40,50"; // Fixed brick sizes, price units
input string            InpAtrFractions    = "0.05,0.10,0.15,0.20,0.30,0.40,0.50,0.75,1.00"; // Bricks as fraction of prior-quarter ATR
input ENUM_RENKO_PRICE  InpPrice           = RENKO_PRICE_BID;      // Price that builds bricks
input int               InpImpulseMin      = 3;                    // Strategy B: min impulse bricks
input int               InpPullbackMax     = 2;                    // Strategy B: max pullback bricks
input double            InpCommissionSide  = 0.035;                // Commission per side, price units per unit ($7/lot RT = 0.035)
input int               InpLatencyMs       = 0;                    // Order latency, ms (0 = fill on next tick)
input double            InpDumpBrick       = 0;                    // Dump all bricks of this fixed size (0 = off)
input string            InpOutPrefix       = "RenkoSweep_XAUUSD";  // Output file prefix
input double            InpMaxSpreadMult   = 25.0;                 // Reject ticks with spread > N x running mean spread (0 = off)

struct DatasetAcc
  {
   long              ticks, days, trDays;
   double            spreadSum, pathSum, trSum;
  };

CSweepSlot *g_slots[];
DatasetAcc  g_data[SWEEP_YEARS + 1];

//--- terminal tick source state
MqlTick     g_ticks[];
int         g_tickPos = 0, g_tickCount = 0;
long        g_cursor = 0, g_end = 0;

//+------------------------------------------------------------------+
int ParseList(const string text, double &out[])
  {
   string parts[];
   int n = StringSplit(text, ',', parts);
   ArrayResize(out, 0);
   for(int i = 0; i < n; i++)
     {
      StringTrimLeft(parts[i]);
      StringTrimRight(parts[i]);
      double v = StringToDouble(parts[i]);
      if(v > 0)
        {
         int k = ArraySize(out);
         ArrayResize(out, k + 1);
         out[k] = v;
        }
     }
   return ArraySize(out);
  }

//+------------------------------------------------------------------+
bool NextTerminalTick(long &t, double &bid, double &ask)
  {
   while(g_tickPos >= g_tickCount)
     {
      if(g_cursor >= g_end || IsStopped())
         return false;
      long to = MathMin(g_cursor + 5 * 86400 * 1000L, g_end);
      g_tickCount = CopyTicksRange(InpSymbol, g_ticks, COPY_TICKS_INFO, g_cursor, to - 1);
      if(g_tickCount < 0)
         g_tickCount = 0;
      g_tickPos = 0;
      g_cursor = to;
     }
   t   = g_ticks[g_tickPos].time_msc;
   bid = g_ticks[g_tickPos].bid;
   ask = g_ticks[g_tickPos].ask;
   g_tickPos++;
   return true;
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   double fixedSizes[], atrFracs[];
   int nFixed = ParseList(InpFixedSizes, fixedSizes);
   int nAtr   = ParseList(InpAtrFractions, atrFracs);
   if(nFixed + nAtr == 0)
     {
      Print("RenkoSweep: no brick sizes given");
      return;
     }

//--- slots
   int nSlots = nFixed + nAtr;
   ArrayResize(g_slots, nSlots);
   int dumpHandle = INVALID_HANDLE;
   for(int i = 0; i < nSlots; i++)
     {
      bool atr = (i >= nFixed);
      double param = atr ? atrFracs[i - nFixed] : fixedSizes[i];
      g_slots[i] = new CSweepSlot();
      g_slots[i].Setup(atr, param, InpPrice, InpImpulseMin, InpPullbackMax, InpCommissionSide, InpLatencyMs);
      if(!atr && InpDumpBrick > 0 && dumpHandle == INVALID_HANDLE && MathAbs(param - InpDumpBrick) < 1e-9)
        {
         dumpHandle = FileOpen(InpOutPrefix + "_bricks.csv", FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
         if(dumpHandle != INVALID_HANDLE)
            g_slots[i].EnableDump(dumpHandle);
        }
     }
   if(InpDumpBrick > 0 && dumpHandle == INVALID_HANDLE)
      Print("RenkoSweep: InpDumpBrick is not in InpFixedSizes (or the file could not be opened) - no brick dump");
   for(int i = 0; i <= SWEEP_YEARS; i++)
      ZeroMemory(g_data[i]);

//--- source
   CTickCsvReader reader;
   long fromMs = (long)InpFrom * 1000;
   long toMs   = (long)InpTo * 1000;
   if(InpSource == SRC_CSV_COMMON)
     {
      if(!reader.Open(InpCsvFile, true))
        {
         PrintFormat("RenkoSweep: cannot open '%s' in Common\\Files (error %d). See the header of this script for the mklink command.",
                     InpCsvFile, GetLastError());
         Cleanup(dumpHandle);
         return;
        }
      PrintFormat("RenkoSweep: %s, %.2f GB, %d brick sizes", InpCsvFile, reader.Size() / 1073741824.0, nSlots);
     }
   else
     {
      g_cursor = (fromMs > 0) ? fromMs : (long)D'2010.01.01' * 1000;
      g_end    = (toMs > 0) ? toMs : (long)TimeCurrent() * 1000 + 1000;
      PrintFormat("RenkoSweep: terminal ticks of %s, %d brick sizes", InpSymbol, nSlots);
     }

//--- single pass
   CDailyRangeTracker tracker;
   ulong started = GetMicrosecondCount();
   long  n = 0, bad = 0, lastT = 0, curUday = -1;
   int   year = 1970, month = 1;
   double prevBid = 0;
   double sprEma = 0;
   long  sprRejected = 0;
   long  t = 0;
   double bid = 0, ask = 0;
   MqlDateTime st;
   while(!IsStopped())
     {
      bool ok = (InpSource == SRC_CSV_COMMON) ? reader.Next(t, bid, ask) : NextTerminalTick(t, bid, ask);
      if(!ok)
         break;
      if(t < fromMs)
         continue;
      if(toMs > 0 && t >= toMs)
         break;
      if(bid <= 0 || ask < bid || t < lastT)
        {
         bad++;
         continue;
        }
      lastT = t;
      //--- bad-quote filter: an off-market quote shows up as a spread far above the running mean.
      //--- No look-ahead, so a live EA can apply the same rule. The mean learns from accepted ticks only.
      double spr = ask - bid;
      if(sprEma <= 0)
         sprEma = spr;
      else
         if(InpMaxSpreadMult > 0 && spr > InpMaxSpreadMult * sprEma)
           {
            sprRejected++;
            continue;
           }
      sprEma += (spr - sprEma) / 1000.0;
      long uday = t / 86400000;
      if(uday != curUday)
        {
         curUday = uday;
         TimeToStruct((datetime)(t / 1000), st);
         year = st.year;
         month = st.mon;
        }
      int yi = SweepYearIndex(year);

      int flags = tracker.OnTick(t, year, month, bid);
      if((flags & DAYFLAG_NEW_DAY) != 0)
        {
         g_data[yi].days++;
         g_data[SWEEP_TOTAL].days++;
         if(tracker.FinishedTR() >= 0)
           {
            int fy = SweepYearIndex(tracker.FinishedYear());
            g_data[fy].trSum += tracker.FinishedTR();
            g_data[fy].trDays++;
            g_data[SWEEP_TOTAL].trSum += tracker.FinishedTR();
            g_data[SWEEP_TOTAL].trDays++;
           }
        }
      if((flags & DAYFLAG_NEW_ATR) != 0)
         for(int i = nFixed; i < nSlots; i++)
            g_slots[i].SetAtr(tracker.Atr());

      double step = (prevBid > 0) ? MathAbs(bid - prevBid) : 0;
      prevBid = bid;
      g_data[yi].ticks++;
      g_data[yi].spreadSum += ask - bid;
      g_data[yi].pathSum += step;
      g_data[SWEEP_TOTAL].ticks++;
      g_data[SWEEP_TOTAL].spreadSum += ask - bid;
      g_data[SWEEP_TOTAL].pathSum += step;

      for(int i = 0; i < nSlots; i++)
         g_slots[i].OnTick(t, year, bid, ask);

      n++;
      if((n & 0x3FFFFF) == 0)
        {
         double sec = (GetMicrosecondCount() - started) / 1e6;
         if(InpSource == SRC_CSV_COMMON)
            Comment(StringFormat("RenkoSweep  %.1f%%   %I64d ticks   %s   %.0fs   %.1fM ticks/s",
                                 100.0 * reader.Progress(), n, TimeToString((datetime)(t / 1000)), sec, n / sec / 1e6));
         else
            Comment(StringFormat("RenkoSweep  %I64d ticks   %s   %.0fs", n, TimeToString((datetime)(t / 1000)), sec));
        }
     }
   double elapsed = (GetMicrosecondCount() - started) / 1e6;
   reader.Close();

//--- output
   long days[SWEEP_YEARS + 1];
   for(int i = 0; i <= SWEEP_YEARS; i++)
      days[i] = g_data[i].days;

   int h = FileOpen(InpOutPrefix + "_summary.csv", FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(h != INVALID_HANDLE)
     {
      FileWriteString(h, CSweepSlot::Header());
      for(int i = 0; i < nSlots; i++)
         g_slots[i].WriteRows(h, days);
      FileClose(h);
     }
   else
      PrintFormat("RenkoSweep: cannot write summary (error %d)", GetLastError());

   h = FileOpen(InpOutPrefix + "_dataset.csv", FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(h != INVALID_HANDLE)
     {
      FileWriteString(h, "year,ticks,days,avg_spread,daily_atr,tick_path_per_day,path_to_atr\n");
      for(int i = 0; i <= SWEEP_YEARS; i++)
        {
         if(g_data[i].ticks == 0)
            continue;
         double d   = (double)MathMax(g_data[i].days, 1);
         double atr = g_data[i].trDays > 0 ? g_data[i].trSum / g_data[i].trDays : 0;
         double pathDay = g_data[i].pathSum / d;
         FileWriteString(h, (i == SWEEP_TOTAL ? "ALL" : IntegerToString(SWEEP_YEAR0 + i)) + ","
                         + IntegerToString(g_data[i].ticks) + "," + IntegerToString(g_data[i].days) + ","
                         + DoubleToString(g_data[i].spreadSum / g_data[i].ticks, 4) + ","
                         + DoubleToString(atr, 2) + "," + DoubleToString(pathDay, 2) + ","
                         + DoubleToString(atr > 0 ? pathDay / atr : 0, 2) + "\n");
        }
      FileClose(h);
     }

   Comment("");
   PrintFormat("RenkoSweep: done. %I64d ticks (%I64d rejected, %I64d spread-filtered, %I64d malformed lines) in %.0fs. Output: Common\\Files\\%s_*.csv%s",
               n, bad, sprRejected, reader.BadLines(), elapsed, InpOutPrefix, IsStopped() ? "  [STOPPED EARLY - partial results]" : "");
   Cleanup(dumpHandle);
  }

//+------------------------------------------------------------------+
void Cleanup(const int dumpHandle)
  {
   if(dumpHandle != INVALID_HANDLE)
      FileClose(dumpHandle);
   for(int i = 0; i < ArraySize(g_slots); i++)
      if(CheckPointer(g_slots[i]) == POINTER_DYNAMIC)
         delete g_slots[i];
   ArrayResize(g_slots, 0);
  }
//+------------------------------------------------------------------+
