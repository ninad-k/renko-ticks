"""Line-for-line Python port of mql5/Include/Renko/RenkoEngine.mqh.

Used for the unit tests, the article figures and as the reference for the
numba sweep. Keep it in step with the MQL5 file: same names, same rules.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

RENKO_EPS_REL = 1e-6
PRICE_BID, PRICE_MID = 0, 1


@dataclass
class RenkoBrick:
    id: int
    time_open_msc: int
    time_close_msc: int
    open: float
    close: float
    size: float
    dir: int
    run_length: int
    burst_index: int
    trigger_price: float
    spread: float
    ticks: int


class RenkoEngine:
    def __init__(self) -> None:
        self.cap = 0

    def init(self, brick: float, history: int = 1024, src: int = PRICE_BID) -> bool:
        if brick <= 0 or history < 1:
            return False
        self.brick = brick
        self.eps = brick * RENKO_EPS_REL
        self.anchor = 0.0
        self.k = 0
        self.dir = 0
        self.run = 0
        self.started = False
        self.src = src
        self.total = 0
        self.cap = history
        self.ring: list[RenkoBrick] = []
        self.form_start = 0
        self.form_ticks = 0
        self.last_price = 0.0
        self.up_cmp = math.inf
        self.dn_cmp = -math.inf
        return True

    def level(self, k: int) -> float:
        return self.anchor + k * self.brick

    def _update_levels(self) -> None:
        ku = self.k + 1 if self.dir > 0 else self.k + 2
        kd = self.k - 2 if self.dir > 0 else self.k - 1
        self.up_cmp = self.level(ku) - self.eps
        self.dn_cmp = self.level(kd) + self.eps

    def _push(self, d: int, k_open: int, k_close: int, t: int, p: float, spread: float, burst: int) -> None:
        self.run = self.run + 1 if d == self.dir else 1
        self.dir = d
        self.k = k_close
        self.total += 1
        b = RenkoBrick(self.total, self.form_start, t, self.level(k_open), self.level(k_close),
                       self.brick, d, self.run, burst, p, spread, self.form_ticks)
        self.ring.append(b)
        if len(self.ring) > self.cap:
            self.ring.pop(0)
        self.form_start = t
        self.form_ticks = 0

    def on_tick(self, time_msc: int, bid: float, ask: float) -> int:
        if bid <= 0 or self.cap == 0:
            return 0
        p = bid if self.src == PRICE_BID else 0.5 * (bid + ask)
        self.last_price = p
        if not self.started:
            self.k = math.floor(p / self.brick + RENKO_EPS_REL)
            self.started = True
            self.form_start = time_msc
            self.form_ticks = 0
            self._update_levels()
            return 0
        self.form_ticks += 1
        if self.dn_cmp < p < self.up_cmp:
            return 0
        n = 0
        spread = ask - bid
        while True:
            if p >= self.up_cmp:
                ko = self.k if self.dir > 0 else self.k + 1
                self._push(+1, ko, ko + 1, time_msc, p, spread, n)
            elif p <= self.dn_cmp:
                ko = self.k - 1 if self.dir > 0 else self.k
                self._push(-1, ko, ko - 1, time_msc, p, spread, n)
            else:
                break
            self._update_levels()
            n += 1
        return n

    def set_brick_size(self, brick: float) -> None:
        if brick <= 0:
            return
        if self.started:
            self.anchor = self.level(self.k)
            self.k = 0
        self.brick = brick
        self.eps = brick * RENKO_EPS_REL
        if self.started:
            self._update_levels()

    def get_brick(self, shift: int) -> RenkoBrick | None:
        if shift < 0 or shift >= len(self.ring):
            return None
        return self.ring[-1 - shift]

    def stored(self) -> int:
        return len(self.ring)

    def last_close(self) -> float:
        return self.level(self.k)

    def up_level(self) -> float:
        return self.up_cmp + self.eps

    def down_level(self) -> float:
        return self.dn_cmp - self.eps
