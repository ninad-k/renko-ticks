//+------------------------------------------------------------------+
//|                                                  RenkoEngine.mqh |
//|                                          Copyright 2026, Ninad K |
//|  Tick-driven Renko brick builder. Source-agnostic: feed it live  |
//|  MqlTicks, terminal tick history, or ticks parsed from a file.   |
//|                                                                  |
//|  Guarantees                                                      |
//|   - No repaint: GetBrick() only ever returns CLOSED bricks. The  |
//|     forming brick is exposed separately (Forming*()) and is      |
//|     never stored.                                                |
//|   - Classic construction: continuation needs 1 brick of travel,  |
//|     reversal needs 2.                                            |
//|   - Deterministic grid: with a fixed size, brick boundaries are  |
//|     multiples of the brick size, so the chart does not depend on |
//|     where the history happens to start.                          |
//|   - Gap / spike aware: when one tick prints several bricks, the  |
//|     extras are tagged burst_index > 0 ("phantom" bricks nobody   |
//|     could have traded). Treat the whole tick as ONE decision.    |
//|   - Honest fills: every brick records the real price and spread  |
//|     of the tick that closed it, not just the brick boundary.     |
//|                                                                  |
//|  Usage in an EA                                                  |
//|     CRenkoEngine rk;                                             |
//|     rk.Init(15.0);                                  // $15 brick |
//|     rk.FeedHistory(_Symbol, TimeCurrent()-30*86400, TimeCurrent());
//|     void OnTick() {                                              |
//|        MqlTick t; SymbolInfoTick(_Symbol, t);                    |
//|        if(rk.OnTick(t) > 0) {        // >=1 brick closed         |
//|           RenkoBrick b; rk.GetBrick(0, b);  // last CLOSED brick |
//|           ...signal logic on closed bricks only...               |
//|        }                                                         |
//|     }                                                            |
//+------------------------------------------------------------------+
#ifndef RENKO_ENGINE_MQH
#define RENKO_ENGINE_MQH

//--- level tolerance as a fraction of the brick, so it scales with the symbol's price
#define RENKO_EPS_REL 1e-6

enum ENUM_RENKO_PRICE
  {
   RENKO_PRICE_BID = 0,   // Bid (matches MT5 charts)
   RENKO_PRICE_MID = 1    // Mid (bid+ask)/2
  };

struct RenkoBrick
  {
   long              id;              // sequential number of the brick, 1-based
   long              time_open_msc;   // when formation started (= close time of the previous brick)
   long              time_close_msc;  // time of the tick that closed the brick
   double            open;
   double            close;
   double            size;            // brick size in price units at the time it closed
   int               dir;             // +1 up, -1 down
   int               run_length;      // position inside its same-direction run (1 = reversal brick)
   int               burst_index;     // 0 = first brick printed by its closing tick, >0 = phantom
   double            trigger_price;   // actual source price of the closing tick
   double            spread;          // ask-bid on the closing tick
   long              ticks;           // ticks consumed while the brick was forming
  };

class CRenkoEngine
  {
private:
   double            m_brick;
   double            m_eps;           // level tolerance in price units = brick * RENKO_EPS_REL
   double            m_anchor;        // price of grid index 0
   long              m_k;             // grid index of the last close
   int               m_dir;           // direction of the last closed brick (0 = none yet)
   int               m_run;           // length of the current same-direction run
   bool              m_started;
   ENUM_RENKO_PRICE  m_src;
   double            m_upCmp;         // next up-close level   (minus eps)
   double            m_dnCmp;         // next down-close level (plus eps)
   long              m_formStart;
   long              m_formTicks;
   double            m_lastPrice;
   long              m_lastTime;
   long              m_total;
   RenkoBrick        m_ring[];
   int               m_cap;
   int               m_head;          // slot the next brick is written to
   int               m_count;

   double            Level(const long k) const { return m_anchor + (double)k * m_brick; }

   void              UpdateLevels()
     {
      //--- before the first brick (m_dir == 0) m_k is the grid cell [k, k+1) holding the first
      //--- price; the price must clear that cell by a full brick either way, so brick #1 is real
      long ku = (m_dir > 0) ? m_k + 1 : m_k + 2;
      long kd = (m_dir > 0) ? m_k - 2 : m_k - 1;
      m_upCmp = Level(ku) - m_eps;
      m_dnCmp = Level(kd) + m_eps;
     }

   void              Push(const int dir, const long kOpen, const long kClose, const long t,
                          const double p, const double spread, const int burst)
     {
      m_run = (dir == m_dir) ? m_run + 1 : 1;
      m_dir = dir;
      m_k   = kClose;
      m_total++;
      RenkoBrick b;
      b.id             = m_total;
      b.time_open_msc  = m_formStart;
      b.time_close_msc = t;
      b.open           = Level(kOpen);
      b.close          = Level(kClose);
      b.size           = m_brick;
      b.dir            = dir;
      b.run_length     = m_run;
      b.burst_index    = burst;
      b.trigger_price  = p;
      b.spread         = spread;
      b.ticks          = m_formTicks;
      m_ring[m_head] = b;
      m_head = (m_head + 1) % m_cap;
      if(m_count < m_cap)
         m_count++;
      m_formStart = t;
      m_formTicks = 0;
     }

public:
                     CRenkoEngine() : m_brick(0), m_eps(0), m_anchor(0), m_k(0), m_dir(0), m_run(0), m_started(false),
                        m_src(RENKO_PRICE_BID), m_upCmp(DBL_MAX), m_dnCmp(-DBL_MAX), m_formStart(0),
                        m_formTicks(0), m_lastPrice(0), m_lastTime(0), m_total(0), m_cap(0), m_head(0), m_count(0) {}

   //--- brick: size in price units. history: closed bricks kept for GetBrick().
   bool              Init(const double brick, const int history = 1024,
                          const ENUM_RENKO_PRICE src = RENKO_PRICE_BID)
     {
      if(brick <= 0 || history < 1)
         return false;
      m_brick = brick;
      m_eps = brick * RENKO_EPS_REL;
      m_anchor = 0;
      m_k = 0;
      m_dir = 0;
      m_run = 0;
      m_started = false;
      m_src = src;
      m_total = 0;
      m_cap = history;
      m_head = 0;
      m_count = 0;
      m_formTicks = 0;
      m_upCmp = DBL_MAX;
      m_dnCmp = -DBL_MAX;
      return ArrayResize(m_ring, m_cap) == m_cap;
     }

   //--- Feed one tick. Returns the number of bricks this tick closed (0 almost always).
   //--- If it returns n > 1 the tick was a gap/spike: bricks 1..n-1 are phantom, act once.
   int               OnTick(const long time_msc, const double bid, const double ask)
     {
      if(bid <= 0 || m_cap == 0)
         return 0;
      double p = (m_src == RENKO_PRICE_BID) ? bid : 0.5 * (bid + ask);
      m_lastPrice = p;
      m_lastTime  = time_msc;
      if(!m_started)
        {
         m_k = (long)MathFloor(p / m_brick + RENKO_EPS_REL);
         m_started = true;
         m_formStart = time_msc;
         m_formTicks = 0;
         UpdateLevels();
         return 0;
        }
      m_formTicks++;
      if(p < m_upCmp && p > m_dnCmp)
         return 0;
      int n = 0;
      double spread = ask - bid;
      while(true)
        {
         if(p >= m_upCmp)
           {
            long ko = (m_dir > 0) ? m_k : m_k + 1;
            Push(+1, ko, ko + 1, time_msc, p, spread, n);
           }
         else
            if(p <= m_dnCmp)
              {
               long ko = (m_dir > 0) ? m_k - 1 : m_k;
               Push(-1, ko, ko - 1, time_msc, p, spread, n);
              }
            else
               break;
         UpdateLevels();
         n++;
        }
      return n;
     }

   int               OnTick(const MqlTick &t) { return OnTick(t.time_msc, t.bid, t.ask); }

   //--- Warm the engine up from the terminal tick history. Returns bricks built.
   long              FeedHistory(const string symbol, const datetime from, const datetime to)
     {
      long before = m_total;
      long f = (long)from * 1000, end = (long)to * 1000;
      const long step = 5 * 86400 * 1000L;
      MqlTick ticks[];
      while(f < end && !IsStopped())
        {
         long t = MathMin(f + step, end);
         int got = CopyTicksRange(symbol, ticks, COPY_TICKS_INFO, f, t - 1);
         for(int i = 0; i < got; i++)
            OnTick(ticks[i].time_msc, ticks[i].bid, ticks[i].ask);
         f = t;
        }
      return m_total - before;
     }

   //--- Change the brick size on the fly (e.g. quarterly ATR re-fit). The grid is re-anchored
   //--- on the last close; direction and run length carry over. Takes effect for the next brick.
   void              SetBrickSize(const double brick)
     {
      if(brick <= 0)
         return;
      if(m_started)
        {
         m_anchor = Level(m_k);
         m_k = 0;
        }
      m_brick = brick;
      m_eps = brick * RENKO_EPS_REL;
      if(m_started)
         UpdateLevels();
     }

   //--- Closed bricks only. shift 0 = most recently closed brick.
   bool              GetBrick(const int shift, RenkoBrick &out) const
     {
      if(shift < 0 || shift >= m_count)
         return false;
      int idx = (m_head - 1 - shift) % m_cap;
      if(idx < 0)
         idx += m_cap;
      out = m_ring[idx];
      return true;
     }

   int               Stored()      const { return m_count; }
   long              TotalBricks() const { return m_total; }
   int               Direction()   const { return m_dir; }
   int               RunLength()   const { return m_run; }
   double            BrickSize()   const { return m_brick; }
   bool              Started()     const { return m_started; }
   double            LastClose()   const { return Level(m_k); }
   //--- Levels at which the next brick would close
   double            UpLevel()     const { return m_upCmp + m_eps; }
   double            DownLevel()   const { return m_dnCmp - m_eps; }
   //--- Forming (unconfirmed, repainting) state - never use for signals
   double            FormingPrice() const { return m_lastPrice; }
   long              FormingTicks() const { return m_formTicks; }
   long              FormingStart() const { return m_formStart; }
  };

#endif
