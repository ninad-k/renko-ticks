//+------------------------------------------------------------------+
//|                                                   RenkoSweep.mqh |
//|                                          Copyright 2026, Ninad K |
//|  One CSweepSlot = one brick size under test. Each slot owns a    |
//|  CRenkoEngine and accumulates, per calendar year and in total:   |
//|                                                                  |
//|   COST side  - bricks/day, flips/day, phantom (gap) bricks,      |
//|                sub-second bricks, spread as % of brick, fill     |
//|                overshoot beyond the brick boundary               |
//|   EDGE side  - run-length distribution. With 1-brick continue /  |
//|                2-brick reverse, a random walk has mean run = 3.0 |
//|                and a flip-follow system earns (L-3) bricks per   |
//|                run. Mean run length above 3 IS the Renko edge.   |
//|   NET        - two reference systems, filled on the NEXT tick at |
//|                real bid/ask (never at the brick boundary):       |
//|                A: always-in flip-follow                          |
//|                B: impulse >= N bricks, pullback <= M bricks,     |
//|                   enter on resumption brick, exit on the first   |
//|                   opposite brick (= 2-brick trailing stop)       |
//|                "theo" columns are the same trades filled at the  |
//|                brick boundary with zero spread - the number a    |
//|                naive backtest reports. theo - net = the lie.     |
//|                                                                  |
//|  P&L is in price units per 1 unit of the instrument ($/oz).      |
//+------------------------------------------------------------------+
#ifndef RENKO_SWEEP_MQH
#define RENKO_SWEEP_MQH

#include "RenkoEngine.mqh"

#define SWEEP_YEAR0    2000
#define SWEEP_YEARS    64            // 2000..2063
#define SWEEP_TOTAL    SWEEP_YEARS   // index of the all-years accumulator
#define SWEEP_NSTRAT   2
#define SWEEP_NHIST    7             // run length buckets: 1,2,3,4-5,6-9,10-19,20+

#define DAYFLAG_NEW_DAY  1
#define DAYFLAG_NEW_ATR  2

int SweepYearIndex(const int year)
  {
   int i = year - SWEEP_YEAR0;
   if(i < 0)
      return 0;
   if(i >= SWEEP_YEARS)
      return SWEEP_YEARS - 1;
   return i;
  }

struct SweepAcc
  {
   long              bricks, up, flips, phantom, subsec, events;
   double            size_sum, spread_sum, over_sum, over_max;
   long              runs, run_sum, run_max;
   long              run_hist[SWEEP_NHIST];
   long              trades[SWEEP_NSTRAT], wins[SWEEP_NSTRAT];
   double            theo[SWEEP_NSTRAT], net[SWEEP_NSTRAT], gprofit[SWEEP_NSTRAT], gloss[SWEEP_NSTRAT];
   double            eq[SWEEP_NSTRAT], peak[SWEEP_NSTRAT], mdd[SWEEP_NSTRAT];

   void              Reset()
     {
      bricks = up = flips = phantom = subsec = events = 0;
      size_sum = spread_sum = over_sum = over_max = 0;
      runs = run_sum = run_max = 0;
      ArrayInitialize(run_hist, 0);
      ArrayInitialize(trades, 0);
      ArrayInitialize(wins, 0);
      ArrayInitialize(theo, 0);
      ArrayInitialize(net, 0);
      ArrayInitialize(gprofit, 0);
      ArrayInitialize(gloss, 0);
      ArrayInitialize(eq, 0);
      ArrayInitialize(peak, 0);
      ArrayInitialize(mdd, 0);
     }

   void              AddRun(const int len)
     {
      runs++;
      run_sum += len;
      if(len > run_max)
         run_max = len;
      int b = (len <= 3) ? len - 1 : (len <= 5) ? 3 : (len <= 9) ? 4 : (len <= 19) ? 5 : 6;
      run_hist[b]++;
     }

   void              AddTrade(const int s, const double real, const double theoretical)
     {
      trades[s]++;
      if(real > 0)
        {
         wins[s]++;
         gprofit[s] += real;
        }
      else
         gloss[s] -= real;
      theo[s] += theoretical;
      net[s]  += real;
      eq[s]   += real;
      if(eq[s] > peak[s])
         peak[s] = eq[s];
      if(peak[s] - eq[s] > mdd[s])
         mdd[s] = peak[s] - eq[s];
     }
  };

//+------------------------------------------------------------------+
//| Trading-day ranges and the quarterly ATR used for adaptive bricks |
//| A trading day runs 22:00 -> 22:00 UTC so the Sunday open belongs  |
//| to Monday. The ATR published at the first tick of a quarter uses  |
//| only COMPLETED days of the previous quarter: no lookahead.        |
//+------------------------------------------------------------------+
class CDailyRangeTracker
  {
private:
   long              m_day;
   double            m_hi, m_lo, m_last, m_prevClose;
   bool              m_hasPrev;
   int               m_quarter;
   double            m_qSum;
   int               m_qN;
   double            m_atr;
   double            m_finishedTR;
   int               m_dayYear, m_finishedYear;
   int               m_minDays;

public:
                     CDailyRangeTracker() : m_day(-1), m_hi(0), m_lo(0), m_last(0), m_prevClose(0), m_hasPrev(false),
                        m_quarter(-1), m_qSum(0), m_qN(0), m_atr(0), m_finishedTR(0), m_dayYear(0), m_finishedYear(0),
                        m_minDays(20) {}

   int               OnTick(const long t_msc, const int year, const int month, const double bid)
     {
      int flags = 0;
      long day = (t_msc + 7200000) / 86400000;
      if(day != m_day)
        {
         if(m_day >= 0)
           {
            double h = m_hi, l = m_lo;
            if(m_hasPrev)
              {
               if(m_prevClose > h)
                  h = m_prevClose;
               if(m_prevClose < l)
                  l = m_prevClose;
              }
            m_finishedTR = h - l;
            m_finishedYear = m_dayYear;
            m_qSum += m_finishedTR;
            m_qN++;
            m_prevClose = m_last;
            m_hasPrev = true;
           }
         else
            m_finishedTR = -1;
         m_day = day;
         m_dayYear = year;
         m_hi = bid;
         m_lo = bid;
         flags |= DAYFLAG_NEW_DAY;
        }
      else
        {
         if(bid > m_hi)
            m_hi = bid;
         if(bid < m_lo)
            m_lo = bid;
        }
      m_last = bid;
      int q = year * 4 + (month - 1) / 3;
      if(q != m_quarter)
        {
         if(m_quarter >= 0 && m_qN >= m_minDays)
           {
            m_atr = m_qSum / m_qN;
            flags |= DAYFLAG_NEW_ATR;
           }
         m_quarter = q;
         m_qSum = 0;
         m_qN = 0;
        }
      return flags;
     }

   double            Atr()          const { return m_atr; }
   double            FinishedTR()   const { return m_finishedTR; }   // -1 when no day has finished yet
   int               FinishedYear() const { return m_finishedYear; }
  };

//+------------------------------------------------------------------+
class CSweepSlot
  {
private:
   CRenkoEngine      m_eng;
   ENUM_RENKO_PRICE  m_src;
   bool              m_atrMode;
   double            m_param;          // $ size, or fraction of quarterly ATR
   bool              m_active;
   int               m_ring;
   SweepAcc          m_acc[SWEEP_YEARS + 1];
   long              m_prevCloseTime;
   int               m_prevRunLen;     // run completed BEFORE the most recently completed one
   //--- reference strategies
   int               m_impulseMin, m_pullbackMax;
   double            m_commission;     // per side, price units
   long              m_latency;
   int               m_posDir[SWEEP_NSTRAT];
   double            m_entryReal[SWEEP_NSTRAT], m_entryTheo[SWEEP_NSTRAT];
   bool              m_pendExit[SWEEP_NSTRAT];
   double            m_pendExitTheo[SWEEP_NSTRAT];
   int               m_pendEntryDir[SWEEP_NSTRAT];
   double            m_pendEntryTheo[SWEEP_NSTRAT];
   bool              m_hasPending;
   long              m_notBefore;
   int               m_dump;

   void              Fill(const int yi, const double bid, const double ask)
     {
      for(int s = 0; s < SWEEP_NSTRAT; s++)
        {
         if(m_pendExit[s] && m_posDir[s] != 0)
           {
            double px   = (m_posDir[s] > 0) ? bid : ask;
            double real = m_posDir[s] * (px - m_entryReal[s]) - 2.0 * m_commission;
            double theo = m_posDir[s] * (m_pendExitTheo[s] - m_entryTheo[s]);
            m_acc[yi].AddTrade(s, real, theo);
            m_acc[SWEEP_TOTAL].AddTrade(s, real, theo);
            m_posDir[s] = 0;
           }
         m_pendExit[s] = false;
         if(m_pendEntryDir[s] != 0)
           {
            m_posDir[s]    = m_pendEntryDir[s];
            m_entryReal[s] = (m_posDir[s] > 0) ? ask : bid;
            m_entryTheo[s] = m_pendEntryTheo[s];
            m_pendEntryDir[s] = 0;
           }
        }
      m_hasPending = false;
     }

   void              Signal(const int s, const int dir, const double theo, const bool enter)
     {
      if(m_posDir[s] != 0 && m_posDir[s] != dir && !m_pendExit[s])
        {
         m_pendExit[s] = true;
         m_pendExitTheo[s] = theo;
        }
      m_pendEntryDir[s] = 0;            // an entry that never got filled is cancelled
      if(enter)
        {
         m_pendEntryDir[s]  = dir;
         m_pendEntryTheo[s] = theo;
        }
     }

   void              OnBricks(const int n, const int dirBefore, const int runBefore, const long t, const int yi)
     {
      RenkoBrick last;
      m_eng.GetBrick(0, last);
      int    dir        = last.dir;
      double firstClose = last.close - dir * (n - 1) * last.size;
      double over       = MathAbs(last.trigger_price - last.close);
      bool   subsec     = (m_prevCloseTime > 0 && t - m_prevCloseTime < 1000);
      bool   turn       = (dir != dirBefore);
      for(int pass = 0; pass < 2; pass++)
        {
         int a = (pass == 0) ? yi : SWEEP_TOTAL;
         m_acc[a].bricks  += n;
         if(dir > 0)
            m_acc[a].up   += n;
         m_acc[a].phantom += n - 1;
         m_acc[a].events++;
         m_acc[a].size_sum   += n * last.size;
         m_acc[a].spread_sum += last.spread;
         m_acc[a].over_sum   += over;
         if(over > m_acc[a].over_max)
            m_acc[a].over_max = over;
         if(subsec)
            m_acc[a].subsec++;
         if(turn && dirBefore != 0)
           {
            m_acc[a].flips++;
            m_acc[a].AddRun(runBefore);
           }
        }
      m_prevCloseTime = t;
      if(m_dump != INVALID_HANDLE)
         DumpBricks(n);
      if(!turn)
         return;
      //--- A: always-in flip-follow
      Signal(0, dir, firstClose, true);
      //--- B: impulse -> shallow pullback -> resumption
      bool pattern = (dirBefore != 0 && m_prevRunLen >= m_impulseMin && runBefore <= m_pullbackMax);
      Signal(1, dir, firstClose, pattern);
      m_prevRunLen = (dirBefore != 0) ? runBefore : 0;
      m_hasPending = true;
      m_notBefore  = t + m_latency;
     }

   void              DumpBricks(const int n)
     {
      int m = MathMin(n, m_eng.Stored());
      RenkoBrick b;
      for(int j = m - 1; j >= 0; j--)
        {
         m_eng.GetBrick(j, b);
         FileWriteString(m_dump, StringFormat("%I64d,%I64d,%I64d,%.2f,%.2f,%d,%d,%d,%.3f,%.3f,%I64d\n",
                         b.id, b.time_open_msc, b.time_close_msc, b.open, b.close, b.dir, b.run_length,
                         b.burst_index, b.trigger_price, b.spread, b.ticks));
        }
     }

public:
                     CSweepSlot() : m_src(RENKO_PRICE_BID), m_atrMode(false), m_param(0), m_active(false), m_ring(64),
                        m_prevCloseTime(0), m_prevRunLen(0), m_impulseMin(3), m_pullbackMax(2), m_commission(0),
                        m_latency(0), m_hasPending(false), m_notBefore(0), m_dump(INVALID_HANDLE) {}

   bool              Setup(const bool atr_mode, const double param, const ENUM_RENKO_PRICE src,
                           const int impulse_min, const int pullback_max,
                           const double commission_per_side, const int latency_ms)
     {
      m_atrMode = atr_mode;
      m_param = param;
      m_src = src;
      m_impulseMin = impulse_min;
      m_pullbackMax = pullback_max;
      m_commission = commission_per_side;
      m_latency = latency_ms;
      for(int i = 0; i <= SWEEP_YEARS; i++)
         m_acc[i].Reset();
      ArrayInitialize(m_posDir, 0);
      ArrayInitialize(m_pendEntryDir, 0);
      ArrayInitialize(m_pendExit, false);
      m_hasPending = false;
      m_prevCloseTime = 0;
      m_prevRunLen = 0;
      m_active = false;
      if(!m_atrMode)
         m_active = m_eng.Init(m_param, m_ring, m_src);
      return m_atrMode || m_active;
     }

   //--- write every closed brick of this slot to an already opened text file
   void              EnableDump(const int file_handle)
     {
      m_dump = file_handle;
      m_ring = 16384;
      if(!m_atrMode)
         m_active = m_eng.Init(m_param, m_ring, m_src);
      FileWriteString(m_dump, "id,time_open_msc,time_close_msc,open,close,dir,run_length,burst_index,trigger_price,spread,ticks\n");
     }

   //--- ATR slots only: new quarterly ATR -> new brick size (rounded to cents)
   void              SetAtr(const double atr)
     {
      if(!m_atrMode || atr <= 0)
         return;
      double size = MathRound(m_param * atr * 100.0) / 100.0;
      if(size < 0.05)
         size = 0.05;
      if(!m_active)
         m_active = m_eng.Init(size, m_ring, m_src);
      else
         m_eng.SetBrickSize(size);
     }

   void              OnTick(const long t, const int year, const double bid, const double ask)
     {
      if(!m_active)
         return;
      if(m_hasPending && t >= m_notBefore)
         Fill(SweepYearIndex(year), bid, ask);
      int dirBefore = m_eng.Direction();
      int runBefore = m_eng.RunLength();
      int n = m_eng.OnTick(t, bid, ask);
      if(n > 0)
         OnBricks(n, dirBefore, runBefore, t, SweepYearIndex(year));
     }

   bool              IsAtr()  const { return m_atrMode; }
   double            Param()  const { return m_param; }
   string            Label()  const { return m_atrMode ? StringFormat("%.2fxATR", m_param) : StringFormat("$%.2f", m_param); }

   static string     Header()
     {
      return "label,mode,param,year,avg_brick,days,bricks,bricks_per_day,flips,flips_per_day," +
             "phantom_pct,subsec_pct,avg_spread,spread_pct_of_brick,avg_overshoot,max_overshoot," +
             "runs,mean_run_len,run1_pct,run2_pct,run3_pct,run4_5_pct,run6_9_pct,run10_19_pct,run20p_pct,max_run," +
             "A_trades,A_win_pct,A_theo,A_net,A_net_per_trade,A_cost_per_trade,A_pf,A_maxdd," +
             "B_trades,B_win_pct,B_theo,B_net,B_net_per_trade,B_cost_per_trade,B_pf,B_maxdd\n";
     }

   //--- one row per year that has data, plus an ALL row. days[] is indexed like m_acc[].
   void              WriteRows(const int h, const long &days[])
     {
      for(int i = 0; i <= SWEEP_YEARS; i++)
        {
         if(m_acc[i].bricks == 0)
            continue;
         double d  = (double)MathMax(days[i], 1);
         double nb = (double)m_acc[i].bricks;
         double ne = (double)m_acc[i].events;
         double avgBrick  = m_acc[i].size_sum / nb;
         double avgSpread = m_acc[i].spread_sum / ne;
         string row = Label() + "," + (m_atrMode ? "ATR_Q" : "FIXED") + "," + DoubleToString(m_param, 4) + ","
                      + (i == SWEEP_TOTAL ? "ALL" : IntegerToString(SWEEP_YEAR0 + i)) + ","
                      + DoubleToString(avgBrick, 3) + "," + IntegerToString(days[i]) + ","
                      + IntegerToString(m_acc[i].bricks) + "," + DoubleToString(nb / d, 2) + ","
                      + IntegerToString(m_acc[i].flips) + "," + DoubleToString(m_acc[i].flips / d, 2) + ","
                      + DoubleToString(100.0 * m_acc[i].phantom / nb, 3) + ","
                      + DoubleToString(100.0 * m_acc[i].subsec / ne, 3) + ","
                      + DoubleToString(avgSpread, 4) + "," + DoubleToString(100.0 * avgSpread / avgBrick, 2) + ","
                      + DoubleToString(m_acc[i].over_sum / ne, 4) + "," + DoubleToString(m_acc[i].over_max, 2) + ","
                      + IntegerToString(m_acc[i].runs) + ","
                      + DoubleToString(m_acc[i].runs > 0 ? (double)m_acc[i].run_sum / m_acc[i].runs : 0, 4);
         for(int b = 0; b < SWEEP_NHIST; b++)
            row += "," + DoubleToString(m_acc[i].runs > 0 ? 100.0 * m_acc[i].run_hist[b] / m_acc[i].runs : 0, 2);
         row += "," + IntegerToString(m_acc[i].run_max);
         for(int s = 0; s < SWEEP_NSTRAT; s++)
           {
            double nt = (double)MathMax(m_acc[i].trades[s], 1);
            row += "," + IntegerToString(m_acc[i].trades[s])
                   + "," + DoubleToString(100.0 * m_acc[i].wins[s] / nt, 2)
                   + "," + DoubleToString(m_acc[i].theo[s], 2)
                   + "," + DoubleToString(m_acc[i].net[s], 2)
                   + "," + DoubleToString(m_acc[i].net[s] / nt, 4)
                   + "," + DoubleToString((m_acc[i].theo[s] - m_acc[i].net[s]) / nt, 4)
                   + "," + DoubleToString(m_acc[i].gloss[s] > 0 ? m_acc[i].gprofit[s] / m_acc[i].gloss[s] : 0, 3)
                   + "," + DoubleToString(m_acc[i].mdd[s], 2);
           }
         FileWriteString(h, row + "\n");
        }
     }
  };

#endif
