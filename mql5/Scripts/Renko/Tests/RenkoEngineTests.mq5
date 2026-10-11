//+------------------------------------------------------------------+
//|                                            RenkoEngineTests.mq5  |
//|  Unit tests for Include\Renko\RenkoEngine.mqh.                   |
//|  Ten cases. Feeds hand-made tick sequences and checks every     |
//|  brick against values worked out on paper. Run on any chart;     |
//|  results go to the Experts tab. Summary line:                    |
//|  "RenkoEngineTests: N passed, M failed" (N counts checks).       |
//+------------------------------------------------------------------+
#property version     "1.00"
#property description "Unit tests for the tick-driven Renko engine (RenkoEngine.mqh)."

#include <Renko\RenkoEngine.mqh>

int g_pass = 0, g_fail = 0;
string g_case = "";

//--- assertion helpers --------------------------------------------
void Check(const bool ok, const string what)
  {
   if(ok)
      g_pass++;
   else
     {
      g_fail++;
      PrintFormat("FAIL [%s] %s", g_case, what);
     }
  }

void CheckEq(const long got, const long want, const string what)
  {
   Check(got == want, StringFormat("%s: got %I64d, want %I64d", what, got, want));
  }

void CheckNear(const double got, const double want, const string what)
  {
   Check(MathAbs(got - want) < 1e-9, StringFormat("%s: got %.10f, want %.10f", what, got, want));
  }

//--- feed one tick at a fixed spread, time advances 1 s per call ---
long g_t = 0;
int Feed(CRenkoEngine &rk, const double bid, const double spread = 0.0)
  {
   g_t += 1000;
   return rk.OnTick(g_t, bid, bid + spread);
  }

void Begin(const string name)
  {
   g_case = name;
   g_t = 0;
  }

//+------------------------------------------------------------------+
//| 1. The first tick only places the engine on the grid.            |
//|    Brick 1, start 100.3: cell [100,101). Up needs 102, down 99.  |
//+------------------------------------------------------------------+
void TestFirstBrickNeedsFullTravel()
  {
   Begin("first brick");
   CRenkoEngine rk;
   Check(rk.Init(1.0), "Init(1.0)");
   CheckEq(Feed(rk, 100.3), 0, "first tick prints nothing");
   CheckEq(Feed(rk, 101.9), 0, "101.9 is inside the start cell + 1 brick");
   CheckEq(Feed(rk, 99.1), 0, "99.1 has not cleared the cell downwards");
   CheckNear(rk.UpLevel(), 102.0, "up level before the first brick");
   CheckNear(rk.DownLevel(), 99.0, "down level before the first brick");
   CheckEq(Feed(rk, 102.0), 1, "102.0 closes exactly one brick");
   RenkoBrick b;
   Check(rk.GetBrick(0, b), "brick 0 exists");
   CheckNear(b.open, 101.0, "first brick open");
   CheckNear(b.close, 102.0, "first brick close");
   CheckEq(b.dir, 1, "first brick direction");
   CheckEq(b.run_length, 1, "first brick run length");
  }

//+------------------------------------------------------------------+
//| 2. Continuation needs 1 brick of travel, reversal needs 2,       |
//|    and a reversal brick opens at the previous brick's open.      |
//+------------------------------------------------------------------+
void TestContinueOneReverseTwo()
  {
   Begin("continue/reverse");
   CRenkoEngine rk;
   rk.Init(1.0);
   Feed(rk, 100.3);
   Feed(rk, 102.0);                         // up 101->102
   CheckEq(Feed(rk, 103.0), 1, "one brick of travel continues");
   CheckEq(Feed(rk, 101.5), 0, "1.5 bricks against the trend is not a reversal");
   CheckNear(rk.DownLevel(), 101.0, "reversal level is two bricks below the close");
   CheckEq(Feed(rk, 101.0), 1, "two bricks against the trend reverse");
   RenkoBrick b;
   rk.GetBrick(0, b);
   CheckEq(b.dir, -1, "reversal brick direction");
   CheckNear(b.open, 102.0, "reversal brick opens at the previous brick's open");
   CheckNear(b.close, 101.0, "reversal brick close");
   CheckEq(b.run_length, 1, "reversal brick starts a new run");
   CheckEq(Feed(rk, 100.0), 1, "down continuation");
   rk.GetBrick(0, b);
   CheckEq(b.run_length, 2, "second brick of the down run");
  }

//+------------------------------------------------------------------+
//| 3. One tick that jumps several bricks prints all of them, tags   |
//|    the extras as phantom (burst_index > 0) and records the real  |
//|    tick price and spread on every one of them.                   |
//+------------------------------------------------------------------+
void TestGapPrintsPhantomBricks()
  {
   Begin("gap");
   CRenkoEngine rk;
   rk.Init(1.0);
   Feed(rk, 100.3);
   Feed(rk, 102.0);                         // up   101->102
   Feed(rk, 103.0);                         // up   102->103
   Feed(rk, 101.0);                         // down 102->101
   CheckEq(Feed(rk, 106.2, 0.3), 4, "a gap to 106.2 closes four bricks on one tick");
   for(int s = 0; s < 4; s++)
     {
      RenkoBrick b;
      rk.GetBrick(s, b);
      string at = StringFormat("shift %d", s);
      CheckEq(b.burst_index, 3 - s, at + " burst index");
      CheckEq(b.run_length, 4 - s, at + " run length");
      CheckNear(b.close, 106.0 - s, at + " close on the grid");
      CheckNear(b.trigger_price, 106.2, at + " trigger price is the real tick");
      CheckNear(b.spread, 0.3, at + " spread of the closing tick");
      CheckEq(b.time_close_msc, g_t, at + " all closed by the same tick");
     }
   RenkoBrick first;
   rk.GetBrick(3, first);
   CheckNear(first.open, 102.0, "gap reversal brick opens at the previous brick's open");
  }

//+------------------------------------------------------------------+
//| 4. Nothing below a level is ever stored: the forming brick moves |
//|    with price but closed bricks never change.                    |
//+------------------------------------------------------------------+
void TestNoRepaint()
  {
   Begin("no repaint");
   CRenkoEngine rk;
   rk.Init(1.0);
   Feed(rk, 100.3);
   Feed(rk, 102.0);
   RenkoBrick before, after;
   rk.GetBrick(0, before);
   int stored = rk.Stored();
   double path[] = {102.9, 100.2, 102.5, 100.01, 102.99};
   for(int i = 0; i < ArraySize(path); i++)
      CheckEq(Feed(rk, path[i]), 0, StringFormat("tick %.2f prints nothing", path[i]));
   CheckEq(rk.Stored(), stored, "stored brick count unchanged");
   rk.GetBrick(0, after);
   CheckEq(after.id, before.id, "last closed brick id unchanged");
   CheckNear(after.close, before.close, "last closed brick close unchanged");
   CheckNear(rk.FormingPrice(), 102.99, "forming price follows the last tick");
   CheckEq(rk.FormingTicks(), 5, "forming tick count");
  }

//+------------------------------------------------------------------+
//| 5. Brick boundaries sit on multiples of the brick size, so two   |
//|    engines that start at different prices agree once both have   |
//|    printed a brick in the same place.                            |
//+------------------------------------------------------------------+
void TestDeterministicGrid()
  {
   Begin("grid");
   CRenkoEngine a, b;
   a.Init(1.0);
   b.Init(1.0);
   g_t = 0;
   a.OnTick(1000, 100.3, 100.3);            // cell [100,101)
   b.OnTick(1000, 99.7, 99.7);              // cell [99,100)
   CheckEq(a.OnTick(2000, 102.0, 102.0), 1, "engine A prints 101->102");
   CheckEq(b.OnTick(2000, 102.0, 102.0), 2, "engine B prints 100->101->102");
   CheckNear(a.LastClose(), b.LastClose(), "both engines close at 102");
   double path[] = {103.0, 104.4, 102.0, 101.0, 105.6, 99.2};
   for(int i = 0; i < ArraySize(path); i++)
     {
      long t = 3000 + i * 1000;
      CheckEq(a.OnTick(t, path[i], path[i]), b.OnTick(t, path[i], path[i]),
              StringFormat("same brick count at %.1f", path[i]));
     }
   RenkoBrick ba, bb;
   for(int s = 0; s < 5; s++)
     {
      a.GetBrick(s, ba);
      b.GetBrick(s, bb);
      CheckNear(ba.close, bb.close, StringFormat("shift %d close identical", s));
      CheckEq(ba.dir, bb.dir, StringFormat("shift %d direction identical", s));
     }
  }

//+------------------------------------------------------------------+
//| 6. A price exactly on a level closes the brick even with         |
//|    five-digit floating point (EURUSD-sized bricks).              |
//+------------------------------------------------------------------+
void TestFloatingPointLevels()
  {
   Begin("float levels");
   CRenkoEngine rk;
   rk.Init(0.0010);
   Feed(rk, 1.10050);                       // cell [1.100,1.101)
   CheckEq(Feed(rk, 1.10199), 0, "one point short of the level");
   CheckEq(Feed(rk, 1.10200), 1, "exactly on 1.10200 closes the brick");
   RenkoBrick b;
   rk.GetBrick(0, b);
   CheckNear(b.close, 1.102, "close on the grid");
   CheckEq(Feed(rk, 1.10300), 1, "exactly on 1.10300 continues");
  }

//+------------------------------------------------------------------+
//| 7. The history ring keeps the newest N closed bricks.            |
//+------------------------------------------------------------------+
void TestRingBuffer()
  {
   Begin("ring");
   CRenkoEngine rk;
   rk.Init(1.0, 3);
   Feed(rk, 100.3);
   CheckEq(Feed(rk, 106.0), 5, "five bricks 101..106");
   CheckEq(rk.Stored(), 3, "only three kept");
   CheckEq(rk.TotalBricks(), 5, "total counts all bricks");
   RenkoBrick b;
   rk.GetBrick(0, b);
   CheckEq(b.id, 5, "shift 0 is the newest");
   rk.GetBrick(2, b);
   CheckEq(b.id, 3, "shift 2 is the oldest kept");
   Check(!rk.GetBrick(3, b), "shift 3 is out of range");
   Check(!rk.GetBrick(-1, b), "negative shift is rejected");
  }

//+------------------------------------------------------------------+
//| 8. Changing the size re-anchors the grid on the last close.      |
//+------------------------------------------------------------------+
void TestSetBrickSize()
  {
   Begin("resize");
   CRenkoEngine rk;
   rk.Init(1.0);
   Feed(rk, 100.3);
   Feed(rk, 103.0);                         // up to 103, direction +1
   rk.SetBrickSize(2.0);
   CheckNear(rk.BrickSize(), 2.0, "new size");
   CheckNear(rk.LastClose(), 103.0, "last close kept");
   CheckNear(rk.UpLevel(), 105.0, "continuation is one new brick above");
   CheckNear(rk.DownLevel(), 99.0, "reversal is two new bricks below");
   CheckEq(rk.RunLength(), 2, "run length carried over");
   CheckEq(Feed(rk, 105.0), 1, "continuation at the new size");
   RenkoBrick b;
   rk.GetBrick(0, b);
   CheckNear(b.size, 2.0, "brick records the size it closed with");
   CheckEq(b.run_length, 3, "run continues across the resize");
  }

//+------------------------------------------------------------------+
//| 9. Mid-price source and bad input.                               |
//+------------------------------------------------------------------+
void TestSourceAndInput()
  {
   Begin("source/input");
   CRenkoEngine bad;
   Check(!bad.Init(0.0), "zero brick size is rejected");
   Check(!bad.Init(1.0, 0), "zero history is rejected");
   CRenkoEngine mid;
   mid.Init(1.0, 16, RENKO_PRICE_MID);
   mid.OnTick(1000, 100.3, 100.3);
   CheckEq(mid.OnTick(2000, 101.6, 102.2), 0, "bid 101.6 / ask 102.2: mid 101.9 is short");
   CheckEq(mid.OnTick(3000, 101.8, 102.2), 1, "mid 102.0 closes the brick");
   CheckEq(mid.OnTick(4000, 0.0, 0.0), 0, "zero bid is ignored");
   CheckNear(mid.FormingPrice(), 102.0, "ignored tick does not move the forming price");
  }

//+------------------------------------------------------------------+
//| 10. Tiny prices: the level tolerance scales with the brick.      |
//|     With a fixed 1e-7 tolerance a 1e-7 brick would close early.  |
//+------------------------------------------------------------------+
void TestTinyPriceScale()
  {
   Begin("tiny prices");
   CRenkoEngine rk;
   rk.Init(0.0000001);
   Feed(rk, 0.00001234);                    // cell [123,124) x 1e-7
   CheckEq(Feed(rk, 0.00001249), 0, "0.00001249 is still below the up level");
   CheckEq(Feed(rk, 0.00001221), 0, "0.00001221 is still above the down level 0.0000122");
   CheckEq(Feed(rk, 0.00001250), 1, "0.00001250 closes the first brick");
   RenkoBrick b;
   rk.GetBrick(0, b);
   CheckNear(b.close, 0.0000125, "close on the grid");
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   TestFirstBrickNeedsFullTravel();
   TestContinueOneReverseTwo();
   TestGapPrintsPhantomBricks();
   TestNoRepaint();
   TestDeterministicGrid();
   TestFloatingPointLevels();
   TestRingBuffer();
   TestSetBrickSize();
   TestSourceAndInput();
   TestTinyPriceScale();
   PrintFormat("RenkoEngineTests: %d passed, %d failed", g_pass, g_fail);
  }
//+------------------------------------------------------------------+
