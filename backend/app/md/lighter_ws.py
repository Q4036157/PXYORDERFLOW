"""Lighter public market data with WebSocket and REST fallback.

The adapter is read-only and independent from execution services.

说明：
- 官方 SDK 在 connected 后再 subscribe
- 部分网络环境对 wss://.../stream 握手返回 400；此时用
  GET /api/v1/orderBookOrders 与 /api/v1/recentTrades 保底画梯子
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import defaultdict
from typing import Awaitable, Callable, Optional

logger = logging.getLogger("of.md.lighter")

OnBookSnap = Callable[[str, list, list, float, Optional[int]], Awaitable[None] | None]
OnBookDelta = Callable[[str, list, list, float, Optional[int], Optional[int]], Awaitable[None] | None]
OnTrade = Callable[[str, float, float, str, float, str], Awaitable[None] | None]


def _aggregate_orders(rows: list[dict]) -> list[dict]:
    """Lighter orderBookOrders 是订单级；聚合为价位 qty。"""
    buckets: dict[str, float] = defaultdict(float)
    for row in rows or []:
        try:
            px = str(row.get("price") or "")
            qty = float(row.get("remaining_base_amount") or row.get("size") or row.get("qty") or 0)
        except (TypeError, ValueError):
            continue
        if not px or qty <= 0:
            continue
        buckets[px] += qty
    # 保持字符串价，BookEngine 会规范化
    return [{"price": p, "size": f"{q:.8f}"} for p, q in buckets.items()]


class LighterMarketData:
    """
    订阅:
      - order_book/{market_id}
      - trade/{market_id}
    主网: wss://mainnet.zklighter.elliot.ai/stream
    回退 REST:
      - /api/v1/orderBookOrders?market_id=&limit=
      - /api/v1/recentTrades?market_id=&limit=
    """

    def __init__(
        self,
        *,
        market_id: int,
        symbol: str,
        host: str = "mainnet.zklighter.elliot.ai",
        on_book_snapshot: OnBookSnap | None = None,
        on_book_delta: OnBookDelta | None = None,
        on_trade: OnTrade | None = None,
        prefer_ws: bool = True,
        rest_poll_sec: float = 0.4,
        rest_depth: int = 80,
    ) -> None:
        self.market_id = market_id
        self.symbol = symbol
        self.host = host
        self.ws_url = f"wss://{host}/stream"
        self.rest_base = f"https://{host}"
        self.on_book_snapshot = on_book_snapshot
        self.on_book_delta = on_book_delta
        self.on_trade = on_trade
        self.prefer_ws = prefer_ws
        self.rest_poll_sec = rest_poll_sec
        self.rest_depth = rest_depth
        self._task: asyncio.Task | None = None
        self._stopping = False
        self._ws = None
        self._seen_trades: set[str] = set()
        self._mode = "init"

    @property
    def mode(self) -> str:
        return self._mode

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name=f"lighter-md-{self.market_id}")

    async def stop(self) -> None:
        self._stopping = True
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def _run(self) -> None:
        # 先试 WS 若干次；连续失败后切 REST 轮询（仍可后台偶发重试 WS）
        ws_fails = 0
        while not self._stopping:
            if self.prefer_ws and ws_fails < 3:
                ok = await self._run_ws_once()
                if ok:
                    ws_fails = 0
                    continue
                ws_fails += 1
                logger.warning(
                    "Lighter WS 失败 %s/3，将%s",
                    ws_fails,
                    "重试" if ws_fails < 3 else "切换 REST 轮询",
                )
                await asyncio.sleep(min(2**ws_fails, 8))
                continue
            # REST fallback loop
            self._mode = "rest"
            logger.info(
                "Lighter MD REST poll market_id=%s symbol=%s every %.2fs",
                self.market_id,
                self.symbol,
                self.rest_poll_sec,
            )
            rest_started = time.time()
            while not self._stopping:
                try:
                    await self._poll_rest_once()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("Lighter REST poll error: %s", exc)
                await asyncio.sleep(self.rest_poll_sec)
                # 每 45s 再试一次 WS
                if self.prefer_ws and (time.time() - rest_started) >= 45:
                    ws_fails = 2  # 只再给 1 次 WS 机会
                    break

    async def _run_ws_once(self) -> bool:
        """跑一轮 WS；正常断线返回 True（外层继续），握手/不可用返回 False。"""
        try:
            import websockets
        except ImportError as exc:
            logger.error("需要 websockets 包: %s", exc)
            return False

        try:
            connect_kwargs: dict = {
                "ping_interval": 20,
                "ping_timeout": 20,
                "max_queue": 2048,
                "open_timeout": 15,
                "max_size": 10 * 1024 * 1024,
            }
            # 可选 Origin（部分边缘节点敏感）
            origin = os.getenv("OF_LIGHTER_WS_ORIGIN", "").strip()
            if origin:
                connect_kwargs["origin"] = origin

            async with websockets.connect(self.ws_url, **connect_kwargs) as ws:
                self._ws = ws
                self._mode = "ws"
                logger.info(
                    "Lighter MD WS open market_id=%s symbol=%s — wait connected",
                    self.market_id,
                    self.symbol,
                )
                subscribed = False
                async for raw in ws:
                    if self._stopping:
                        break
                    # 官方协议：先收到 connected 再 subscribe
                    try:
                        msg = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
                    except (TypeError, ValueError):
                        continue
                    mtype = str(msg.get("type", ""))
                    if mtype == "connected" and not subscribed:
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "subscribe",
                                    "channel": f"order_book/{self.market_id}",
                                }
                            )
                        )
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "subscribe",
                                    "channel": f"trade/{self.market_id}",
                                }
                            )
                        )
                        subscribed = True
                        logger.info("Lighter MD subscribed order_book+trade/%s", self.market_id)
                        continue
                    await self._handle(msg if isinstance(msg, dict) else raw)
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Lighter WS error: %s", exc)
            return False
        finally:
            self._ws = None

    async def _poll_rest_once(self) -> None:
        import httpx

        params_ob = {"market_id": self.market_id, "limit": self.rest_depth}
        params_tr = {"market_id": self.market_id, "limit": 50}
        async with httpx.AsyncClient(timeout=10.0) as client:
            r_ob, r_tr = await asyncio.gather(
                client.get(f"{self.rest_base}/api/v1/orderBookOrders", params=params_ob),
                client.get(f"{self.rest_base}/api/v1/recentTrades", params=params_tr),
                return_exceptions=True,
            )

        ts = time.time()
        if not isinstance(r_ob, Exception) and getattr(r_ob, "status_code", 0) == 200:
            try:
                body = r_ob.json()
            except Exception:
                body = {}
            bids = _aggregate_orders(body.get("bids") or [])
            asks = _aggregate_orders(body.get("asks") or [])
            if self.on_book_snapshot and (bids or asks):
                await _maybe_await(
                    self.on_book_snapshot(self.symbol, bids, asks, ts, None)
                )

        if not isinstance(r_tr, Exception) and getattr(r_tr, "status_code", 0) == 200:
            try:
                body = r_tr.json()
            except Exception:
                body = {}
            trades = body.get("trades") or []
            # 新→旧；我们按时间正序推，避免 tape 颠倒
            fresh = []
            for t in trades:
                tid = str(t.get("trade_id") or t.get("trade_id_str") or t.get("id") or "")
                if not tid or tid in self._seen_trades:
                    continue
                fresh.append(t)
            # 控制 seen 集合
            for t in fresh:
                tid = str(t.get("trade_id") or t.get("trade_id_str") or "")
                self._seen_trades.add(tid)
            if len(self._seen_trades) > 5000:
                # 粗暴裁剪
                self._seen_trades = set(list(self._seen_trades)[-2000:])
            # API 通常新在前；倒序推送
            for t in reversed(fresh):
                price = float(t.get("price") or 0)
                size = float(t.get("size") or t.get("qty") or 0)
                side = _infer_trade_side(t)
                tid = str(t.get("trade_id") or t.get("trade_id_str") or "")
                t_ts = float(t.get("timestamp") or t.get("transaction_time") or ts)
                if t_ts > 10_000_000_000:
                    # transaction_time 可能是微秒
                    if t_ts > 10_000_000_000_000:
                        t_ts /= 1_000_000.0
                    else:
                        t_ts /= 1000.0
                if self.on_trade and price > 0 and size > 0:
                    await _maybe_await(
                        self.on_trade(self.symbol, price, size, side, t_ts, tid)
                    )

    async def _handle(self, raw) -> None:
        try:
            msg = raw if isinstance(raw, dict) else json.loads(raw)
        except (TypeError, ValueError):
            return
        mtype = str(msg.get("type", ""))
        if mtype == "ping":
            if self._ws is not None:
                await self._ws.send(json.dumps({"type": "pong"}))
            return
        if mtype in {"connected", "subscribed"}:
            return

        ts = float(msg.get("timestamp") or time.time())
        if ts > 10_000_000_000:
            ts = ts / 1000.0

        if mtype in {"subscribed/order_book", "update/order_book"} or mtype.endswith(
            "order_book"
        ):
            ob = msg.get("order_book") or {}
            bids = ob.get("bids") or []
            asks = ob.get("asks") or []
            # WS 可能已是价位级；若含 remaining_base_amount 则聚合
            if bids and isinstance(bids[0], dict) and "remaining_base_amount" in bids[0]:
                bids = _aggregate_orders(bids)
                asks = _aggregate_orders(asks)
            nonce = ob.get("nonce")
            begin_nonce = ob.get("begin_nonce")
            if mtype.startswith("subscribed") or "subscribed" in mtype:
                if self.on_book_snapshot:
                    await _maybe_await(
                        self.on_book_snapshot(self.symbol, bids, asks, ts, nonce)
                    )
            else:
                if self.on_book_delta:
                    await _maybe_await(
                        self.on_book_delta(
                            self.symbol, bids, asks, ts, nonce, begin_nonce
                        )
                    )
            return

        if mtype.endswith("trade") or "trade" in mtype:
            trades = msg.get("trades") or []
            if isinstance(trades, dict):
                trades = [trades]
            if not trades and "price" in msg:
                trades = [msg]
            for t in trades:
                price = float(t.get("price") or 0)
                size = float(t.get("size") or t.get("qty") or 0)
                side = _infer_trade_side(t)
                tid = str(t.get("trade_id") or t.get("id") or "")
                t_ts = float(t.get("timestamp") or t.get("transaction_time") or ts)
                if t_ts > 10_000_000_000:
                    if t_ts > 10_000_000_000_000:
                        t_ts /= 1_000_000.0
                    else:
                        t_ts /= 1000.0
                if self.on_trade and price > 0 and size > 0:
                    await _maybe_await(
                        self.on_trade(self.symbol, price, size, side, t_ts, tid)
                    )


def _infer_trade_side(t: dict) -> str:
    """尽量推断主动买卖；不确定时默认 buy 仅作着色，不用于策略。"""
    if "side" in t:
        s = str(t["side"]).lower()
        if s in {"buy", "bid", "b"}:
            return "buy"
        if s in {"sell", "ask", "s"}:
            return "sell"
    # is_maker_ask: maker 是卖 → taker 是买
    if "is_maker_ask" in t:
        return "buy" if t["is_maker_ask"] else "sell"
    if t.get("type") in {0, "buy"}:
        return "buy"
    if t.get("type") in {1, "sell"}:
        return "sell"
    return "buy"


async def _maybe_await(result) -> None:
    if asyncio.iscoroutine(result):
        await result


class MockMarketData:
    """无网/开发用模拟盘口与成交。"""

    def __init__(
        self,
        symbol: str = "BTC",
        on_book_snapshot: OnBookSnap | None = None,
        on_trade: OnTrade | None = None,
        mid: float = 100.0,
    ) -> None:
        self.symbol = symbol
        self.on_book_snapshot = on_book_snapshot
        self.on_trade = on_trade
        self.mid = mid
        self._task: asyncio.Task | None = None
        self._stopping = False
        self.mode = "mock"

    async def start(self) -> None:
        self._stopping = False
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def _run(self) -> None:
        import random

        while not self._stopping:
            bids = [
                {
                    "price": f"{self.mid - (i + 1) * 0.1:.2f}",
                    "size": f"{random.random() * 5:.4f}",
                }
                for i in range(30)
            ]
            asks = [
                {
                    "price": f"{self.mid + (i + 1) * 0.1:.2f}",
                    "size": f"{random.random() * 5:.4f}",
                }
                for i in range(30)
            ]
            ts = time.time()
            if self.on_book_snapshot:
                await _maybe_await(self.on_book_snapshot(self.symbol, bids, asks, ts, None))
            if self.on_trade:
                side = "buy" if random.random() > 0.5 else "sell"
                px = self.mid + (random.random() - 0.5) * 0.5
                await _maybe_await(
                    self.on_trade(
                        self.symbol, px, random.random(), side, ts, str(int(ts * 1000))
                    )
                )
            self.mid += (random.random() - 0.5) * 0.05
            await asyncio.sleep(0.25)
