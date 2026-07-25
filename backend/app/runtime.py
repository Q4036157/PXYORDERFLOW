"""把 MD / book / flow / trade 粘合在一起的运行时。"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .config import Settings, settings
from .engines.book_engine import BookEngine
from .engines.flow_engine import FlowEngine
from .md.lighter_ws import LighterMarketData, MockMarketData
from .models import PlaceLimitRequest, Trade
from .risk.risk_of import RiskConfig, RiskOf
from .trade.clients import (
    MockTradeClient,
    TradeClient,
    new_of_client_id,
)
from .trade.order_map import OrderIdMapper

logger = logging.getLogger("of.runtime")


class OrderFlowRuntime:
    def __init__(self, cfg: Settings | None = None) -> None:
        self.cfg = cfg or settings
        self.symbol = self.cfg.lighter_symbol
        self.book = BookEngine(self.symbol)
        self.flow = FlowEngine(
            self.symbol,
            interval_ms=self.cfg.bar_interval_ms,
            tick_size=self.cfg.tick_size,
        )
        self.mapper = OrderIdMapper()
        self.risk = RiskOf(
            RiskConfig(
                trading_enabled=self.cfg.trading_enabled,
                max_order_qty=self.cfg.max_order_qty,
                max_order_notional=self.cfg.max_order_notional,
            )
        )
        if self.cfg.trade_mode != "mock":
            raise RuntimeError(
                "The public build includes only the mock execution adapter. "
                "Implement TradeClient for your exchange or execution gateway."
            )
        self.trade: TradeClient = MockTradeClient(self.mapper)

        self._md = None
        self._subscribers: set[asyncio.Queue] = set()
        self._push_task: asyncio.Task | None = None
        self._last_book_push = 0.0
        self.current_account_id: str | None = None

    async def start(self) -> None:
        async def on_snap(symbol, bids, asks, ts, nonce):
            pairs_b = [(x.get("price"), x.get("size", x.get("qty", 0))) for x in bids]
            pairs_a = [(x.get("price"), x.get("size", x.get("qty", 0))) for x in asks]
            self.book.apply_snapshot(pairs_b, pairs_a, ts, nonce)
            await self._broadcast_book(force=True)

        async def on_delta(symbol, bids, asks, ts, nonce, begin_nonce):
            ok = self.book.apply_side_deltas(
                bids=bids, asks=asks, ts=ts, nonce=nonce, begin_nonce=begin_nonce
            )
            if not ok:
                logger.warning("book nonce gap — need resubscribe snapshot")
            await self._broadcast_book(force=False)

        async def on_trade(symbol, price, qty, side, ts, trade_id):
            self.flow.on_trade(
                Trade(
                    symbol=symbol,
                    price=price,
                    qty=qty,
                    side=side,  # type: ignore[arg-type]
                    ts=ts,
                    trade_id=trade_id,
                )
            )
            await self._broadcast(
                {
                    "type": "trade",
                    "data": {
                        "symbol": symbol,
                        "price": price,
                        "qty": qty,
                        "side": side,
                        "ts": ts,
                        "id": trade_id,
                    },
                }
            )

        if self.cfg.md_mode == "lighter":
            self._md = LighterMarketData(
                market_id=self.cfg.lighter_market_id,
                symbol=self.symbol,
                host=self.cfg.lighter_host,
                on_book_snapshot=on_snap,
                on_book_delta=on_delta,
                on_trade=on_trade,
                prefer_ws=self.cfg.lighter_prefer_ws,
                rest_poll_sec=self.cfg.lighter_rest_poll_sec,
            )
        else:
            self._md = MockMarketData(
                symbol=self.symbol,
                on_book_snapshot=on_snap,
                on_trade=on_trade,
            )
        await self._md.start()
        self._push_task = asyncio.create_task(self._periodic_push())

    async def stop(self) -> None:
        if self._md:
            await self._md.stop()
        if self._push_task:
            self._push_task.cancel()
            try:
                await self._push_task
            except (asyncio.CancelledError, Exception):
                pass

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def _broadcast(self, msg: dict[str, Any]) -> None:
        dead = []
        for q in self._subscribers:
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                except Exception:
                    pass
                try:
                    q.put_nowait(msg)
                except Exception:
                    dead.append(q)
        for q in dead:
            self._subscribers.discard(q)

    async def _broadcast_book(self, force: bool = False) -> None:
        now = time.time()
        if not force and now - self._last_book_push < 0.025:
            return
        self._last_book_push = now
        snap = self.book.snapshot(depth=80)
        await self._broadcast({"type": "book", "data": snap.to_dict()})

    async def _periodic_push(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            bar = self.flow.get_bar()
            if bar:
                await self._broadcast(
                    {
                        "type": "footprint",
                        "data": {
                            **bar.to_dict(),
                            "cvd": self.flow.cumulative_delta,
                        },
                    }
                )
            self.flow.prune()

    async def place_from_ladder(
        self,
        *,
        account_id: str,
        side: str,
        price: float,
        qty: float,
        post_only: bool = False,
    ) -> dict[str, Any]:
        of_id = new_of_client_id()
        req = PlaceLimitRequest(
            account_id=account_id,
            symbol=self.symbol,
            side=side,  # type: ignore[arg-type]
            price=price,
            qty=qty,
            of_client_id=of_id,
            post_only=post_only,
        )
        self.risk.assert_place(req)
        result = await self.trade.place_limit(req)
        payload = {
            "success": result.success,
            "orderId": result.order_id,
            "ofClientId": result.of_client_id,
            "clientOrderIndex": result.client_order_index,
            "message": result.message,
            "side": side,
            "price": price,
            "qty": qty,
            "source": "orderflow",
        }
        await self._broadcast({"type": "order", "data": payload})
        return payload

    async def cancel(
        self, account_id: str, order_id: str, symbol: str = ""
    ) -> dict[str, Any]:
        result = await self.trade.cancel(account_id, order_id, symbol or self.symbol)
        return {
            "success": result.success,
            "orderId": result.order_id,
            "message": result.message,
        }

    async def cancel_all(
        self, account_id: str, confirmed: bool, symbol: str | None = None
    ) -> dict[str, Any]:
        self.risk.assert_cancel_all(confirmed)
        result = await self.trade.cancel_all(account_id, symbol or self.symbol, confirmed)
        payload = {"success": result.success, "message": result.message}
        await self._broadcast({"type": "orders_cleared", "data": payload})
        return payload

    async def list_open_orders(
        self, account_id: str, symbol: str | None = None
    ) -> list[dict[str, Any]]:
        rows = await self.trade.list_open_orders(account_id, symbol or self.symbol)
        return [r.to_dict() for r in rows]

    def state_snapshot(self) -> dict[str, Any]:
        bar = self.flow.get_bar()
        return {
            "symbol": self.symbol,
            "book": self.book.snapshot(80).to_dict(),
            "footprint": bar.to_dict() if bar else None,
            "cvd": self.flow.cumulative_delta,
            "tape": [t.to_dict() for t in self.flow.recent_tape(30)],
            "tradingEnabled": self.risk.cfg.trading_enabled,
            "mdMode": self.cfg.md_mode,
            "mdTransport": getattr(self._md, "mode", None) if self._md else None,
            "tradeMode": self.cfg.trade_mode,
            "tickSize": self.cfg.tick_size,
            "marketId": self.cfg.lighter_market_id,
        }


runtime = OrderFlowRuntime()
