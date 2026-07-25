"""book / flow / risk / order_map 单测（stdlib unittest，无外部服务）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(ROOT))

from app.engines.book_engine import BookEngine
from app.engines.flow_engine import FlowEngine
from app.models import PlaceLimitRequest, Trade
from app.risk.risk_of import RiskOf
from app.trade.order_map import OrderIdMapper


class TestBookEngine(unittest.TestCase):
    def test_snapshot_and_delta_remove(self):
        eng = BookEngine("BTC")
        eng.apply_snapshot(
            bids=[(100.0, 1.5), (99.5, 2.0)],
            asks=[(100.5, 1.0), (101.0, 3.0)],
            ts=1.0,
            nonce=10,
        )
        snap = eng.snapshot()
        self.assertEqual(snap.bids[0].price, 100.0)
        self.assertEqual(snap.asks[0].price, 100.5)
        ok = eng.apply_delta("bid", 100.0, 0, ts=2.0, nonce=11, begin_nonce=10)
        self.assertTrue(ok)
        snap2 = eng.snapshot()
        self.assertTrue(all(b.price != 100.0 for b in snap2.bids))

    def test_nonce_gap(self):
        eng = BookEngine("BTC")
        eng.apply_snapshot(bids=[(1, 1)], asks=[(2, 1)], ts=1, nonce=5)
        ok = eng.apply_delta("bid", 1, 2, ts=2, nonce=9, begin_nonce=7)
        self.assertFalse(ok)


class TestFlowEngine(unittest.TestCase):
    def test_bins_and_delta(self):
        flow = FlowEngine("BTC", interval_ms=60_000, tick_size=0.1)
        flow.on_trade(Trade("BTC", 100.04, 1.0, "buy", ts=1_700_000_000_000))
        flow.on_trade(Trade("BTC", 100.06, 0.5, "sell", ts=1_700_000_000_100))
        bar = flow.get_bar()
        self.assertIsNotNone(bar)
        assert bar is not None
        self.assertAlmostEqual(bar.total_delta, 0.5)
        self.assertTrue(any(b.trade_count >= 1 for b in bar.bins))


class TestOrderMapAndRisk(unittest.TestCase):
    def test_mapper_int_index(self):
        m = OrderIdMapper(start_index=42)
        e = m.allocate(
            "OF-abc",
            account_id="a1",
            symbol="BTC",
            side="buy",
            price=1,
            qty=1,
        )
        self.assertEqual(e.client_order_index, 42)
        self.assertIsInstance(e.client_order_index, int)
        with self.assertRaises(ValueError):
            m.allocate("BAD", account_id="a1", symbol="BTC", side="buy", price=1, qty=1)

    def test_risk_cancel_all_gate(self):
        risk = RiskOf()
        with self.assertRaises(PermissionError):
            risk.assert_cancel_all(False)
        risk.assert_cancel_all(True)
        req = PlaceLimitRequest("a", "BTC", "buy", 1.0, 1.0, "OF-1")
        risk.assert_place(req)


class TestMockTradeOpenOrders(unittest.IsolatedAsyncioTestCase):
    async def test_place_list_cancel_all(self):
        from app.trade.clients import MockTradeClient
        from app.trade.order_map import OrderIdMapper
        from app.models import PlaceLimitRequest

        client = MockTradeClient(OrderIdMapper(start_index=7))
        req = PlaceLimitRequest("demo-1", "BTC", "buy", 100.0, 0.01, "OF-t1")
        res = await client.place_limit(req)
        self.assertTrue(res.success)
        opens = await client.list_open_orders("demo-1")
        self.assertEqual(len(opens), 1)
        self.assertEqual(opens[0].order_id, res.order_id)
        all_res = await client.cancel_all("demo-1", "BTC", confirmed=True)
        self.assertTrue(all_res.success)
        self.assertEqual(await client.list_open_orders("demo-1"), [])


if __name__ == "__main__":
    unittest.main()
