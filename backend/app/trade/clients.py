"""Execution adapter contract and the built-in mock implementation.

Real exchange credentials and private execution gateways belong in a separate
adapter. Implement ``TradeClient`` and inject it into ``OrderFlowRuntime``.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..models import Account, PlaceLimitRequest, make_of_client_id
from .order_map import OrderIdMapper


@dataclass
class TradeResult:
    success: bool
    order_id: str = ""
    of_client_id: str = ""
    client_order_index: int | None = None
    message: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class OpenOrder:
    order_id: str
    account_id: str
    symbol: str
    side: str
    price: float
    qty: float
    filled_qty: float = 0.0
    status: str = "open"
    client_order_id: str = ""
    source: str = "orderflow"

    def to_dict(self) -> dict[str, Any]:
        return {
            "orderId": self.order_id,
            "accountId": self.account_id,
            "symbol": self.symbol,
            "side": self.side,
            "price": self.price,
            "qty": self.qty,
            "filledQty": self.filled_qty,
            "status": self.status,
            "clientOrderId": self.client_order_id,
            "source": self.source,
        }


class TradeClient(Protocol):
    """Minimal contract required by the order-flow UI."""

    async def list_accounts(self) -> list[Account]: ...
    async def place_limit(self, req: PlaceLimitRequest) -> TradeResult: ...
    async def cancel(
        self, account_id: str, order_id: str, symbol: str = ""
    ) -> TradeResult: ...
    async def cancel_all(
        self, account_id: str, symbol: str | None, confirmed: bool
    ) -> TradeResult: ...
    async def list_open_orders(
        self, account_id: str, symbol: str | None = None
    ) -> list[OpenOrder]: ...


class MockTradeClient:
    """In-memory execution adapter for development and demonstrations."""

    def __init__(self, mapper: OrderIdMapper) -> None:
        self.mapper = mapper
        self._orders: dict[str, dict[str, Any]] = {}

    async def list_accounts(self) -> list[Account]:
        return [Account(id="demo-1", name="Order Flow Demo", mode="demo")]

    async def place_limit(self, req: PlaceLimitRequest) -> TradeResult:
        entry = self.mapper.allocate(
            req.of_client_id,
            account_id=req.account_id,
            symbol=req.symbol,
            side=req.side,
            price=req.price,
            qty=req.qty,
        )
        order_id = f"mock-{entry.client_order_index}"
        self.mapper.bind_exchange_id(req.of_client_id, order_id)
        self._orders[order_id] = {
            "account_id": req.account_id,
            "symbol": req.symbol,
            "side": req.side,
            "price": req.price,
            "qty": req.qty,
            "of_client_id": req.of_client_id,
            "status": "open",
        }
        return TradeResult(
            success=True,
            order_id=order_id,
            of_client_id=req.of_client_id,
            client_order_index=entry.client_order_index,
            message="mock order accepted",
        )

    async def cancel(
        self, account_id: str, order_id: str, symbol: str = ""
    ) -> TradeResult:
        order = self._orders.get(order_id)
        if not order or order["account_id"] != account_id:
            return TradeResult(success=False, order_id=order_id, message="order not found")
        self._orders.pop(order_id)
        return TradeResult(success=True, order_id=order_id, message="mock order canceled")

    async def cancel_all(
        self, account_id: str, symbol: str | None, confirmed: bool
    ) -> TradeResult:
        if not confirmed:
            return TradeResult(success=False, message="confirmed required")
        order_ids = [
            order_id
            for order_id, order in self._orders.items()
            if order["account_id"] == account_id
            and (symbol is None or order["symbol"] == symbol)
        ]
        for order_id in order_ids:
            self._orders.pop(order_id)
        return TradeResult(success=True, message=f"mock canceled {len(order_ids)} orders")

    async def list_open_orders(
        self, account_id: str, symbol: str | None = None
    ) -> list[OpenOrder]:
        orders: list[OpenOrder] = []
        for order_id, order in self._orders.items():
            if order["account_id"] != account_id:
                continue
            if symbol and order["symbol"] != symbol:
                continue
            orders.append(
                OpenOrder(
                    order_id=order_id,
                    account_id=account_id,
                    symbol=order["symbol"],
                    side=order["side"],
                    price=float(order["price"]),
                    qty=float(order["qty"]),
                    status=order["status"],
                    client_order_id=order["of_client_id"],
                )
            )
        return orders


def new_of_client_id() -> str:
    return make_of_client_id(f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}")
