"""The ten cases of RenkoEngineTests.mq5, mirrored one for one."""

import pytest

from renko_engine import PRICE_MID, RenkoEngine

approx = lambda v: pytest.approx(v, abs=1e-9)  # noqa: E731


class Feeder:
    def __init__(self) -> None:
        self.t = 0

    def __call__(self, rk: RenkoEngine, bid: float, spread: float = 0.0) -> int:
        self.t += 1000
        return rk.on_tick(self.t, bid, bid + spread)


def make(brick=1.0, history=1024, src=0):
    rk = RenkoEngine()
    assert rk.init(brick, history, src)
    return rk, Feeder()


def test_first_brick_needs_full_travel():
    rk, feed = make()
    assert feed(rk, 100.3) == 0
    assert feed(rk, 101.9) == 0
    assert feed(rk, 99.1) == 0
    assert rk.up_level() == approx(102.0)
    assert rk.down_level() == approx(99.0)
    assert feed(rk, 102.0) == 1
    b = rk.get_brick(0)
    assert (b.open, b.close, b.dir, b.run_length) == (approx(101.0), approx(102.0), 1, 1)


def test_continue_one_reverse_two():
    rk, feed = make()
    feed(rk, 100.3)
    feed(rk, 102.0)
    assert feed(rk, 103.0) == 1
    assert feed(rk, 101.5) == 0
    assert rk.down_level() == approx(101.0)
    assert feed(rk, 101.0) == 1
    b = rk.get_brick(0)
    assert (b.dir, b.open, b.close, b.run_length) == (-1, approx(102.0), approx(101.0), 1)
    assert feed(rk, 100.0) == 1
    assert rk.get_brick(0).run_length == 2


def test_gap_prints_phantom_bricks():
    rk, feed = make()
    for p in (100.3, 102.0, 103.0, 101.0):
        feed(rk, p)
    assert feed(rk, 106.2, 0.3) == 4
    for s in range(4):
        b = rk.get_brick(s)
        assert b.burst_index == 3 - s
        assert b.run_length == 4 - s
        assert b.close == approx(106.0 - s)
        assert b.trigger_price == approx(106.2)
        assert b.spread == approx(0.3)
        assert b.time_close_msc == feed.t
    assert rk.get_brick(3).open == approx(102.0)


def test_no_repaint():
    rk, feed = make()
    feed(rk, 100.3)
    feed(rk, 102.0)
    before = rk.get_brick(0)
    stored = rk.stored()
    for p in (102.9, 100.2, 102.5, 100.01, 102.99):
        assert feed(rk, p) == 0
    assert rk.stored() == stored
    assert rk.get_brick(0) == before
    assert rk.last_price == approx(102.99)
    assert rk.form_ticks == 5


def test_deterministic_grid():
    a, b = RenkoEngine(), RenkoEngine()
    a.init(1.0)
    b.init(1.0)
    a.on_tick(1000, 100.3, 100.3)
    b.on_tick(1000, 99.7, 99.7)
    assert a.on_tick(2000, 102.0, 102.0) == 1
    assert b.on_tick(2000, 102.0, 102.0) == 2
    assert a.last_close() == approx(b.last_close())
    for i, p in enumerate((103.0, 104.4, 102.0, 101.0, 105.6, 99.2)):
        t = 3000 + i * 1000
        assert a.on_tick(t, p, p) == b.on_tick(t, p, p)
    for s in range(5):
        assert a.get_brick(s).close == approx(b.get_brick(s).close)
        assert a.get_brick(s).dir == b.get_brick(s).dir


def test_floating_point_levels():
    rk, feed = make(0.0010)
    feed(rk, 1.10050)
    assert feed(rk, 1.10199) == 0
    assert feed(rk, 1.10200) == 1
    assert rk.get_brick(0).close == approx(1.102)
    assert feed(rk, 1.10300) == 1


def test_ring_buffer():
    rk, feed = make(1.0, 3)
    feed(rk, 100.3)
    assert feed(rk, 106.0) == 5
    assert rk.stored() == 3
    assert rk.total == 5
    assert rk.get_brick(0).id == 5
    assert rk.get_brick(2).id == 3
    assert rk.get_brick(3) is None
    assert rk.get_brick(-1) is None


def test_set_brick_size():
    rk, feed = make()
    feed(rk, 100.3)
    feed(rk, 103.0)
    rk.set_brick_size(2.0)
    assert rk.brick == approx(2.0)
    assert rk.last_close() == approx(103.0)
    assert rk.up_level() == approx(105.0)
    assert rk.down_level() == approx(99.0)
    assert rk.run == 2
    assert feed(rk, 105.0) == 1
    b = rk.get_brick(0)
    assert b.size == approx(2.0)
    assert b.run_length == 3


def test_source_and_input():
    assert not RenkoEngine().init(0.0)
    assert not RenkoEngine().init(1.0, 0)
    mid = RenkoEngine()
    mid.init(1.0, 16, PRICE_MID)
    mid.on_tick(1000, 100.3, 100.3)
    assert mid.on_tick(2000, 101.6, 102.2) == 0
    assert mid.on_tick(3000, 101.8, 102.2) == 1
    assert mid.on_tick(4000, 0.0, 0.0) == 0
    assert mid.last_price == approx(102.0)


def test_tiny_price_scale():
    rk, feed = make(0.0000001)
    feed(rk, 0.00001234)
    assert feed(rk, 0.00001249) == 0
    assert feed(rk, 0.00001221) == 0
    assert feed(rk, 0.00001250) == 1
    assert rk.get_brick(0).close == approx(0.0000125)
