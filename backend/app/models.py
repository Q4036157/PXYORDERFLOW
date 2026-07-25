"""共享类型与常量。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal

Side = Literal["buy", "sell"]
AccountMode = Literal["live", "demo"]

OF_CLIENT_PREFIX = "OF-"
SOURCE_ORDERFLOW = "orderflow"


@dataclass
class Account:
    id: str
    name: str
    mode: AccountMode
    can_trade: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Instrument:
    symbol: str
    market_id: int
    tick_size: float
    lot_size: float
    price_decimals: int = 2
    size_decimals: int = 4

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BookLevel:
    price: float
    qty: float

    def to_dict(self) -> dict[str, Any]:
        return {"price": self.price, "qty": self.qty}


@dataclass
class BookSnapshot:
    symbol: str
    bids: list[BookLevel]
    asks: list[BookLevel]
    ts: float
    nonce: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "bids": [b.to_dict() for b in self.bids],
            "asks": [a.to_dict() for a in self.asks],
            "ts": self.ts,
            "nonce": self.nonce,
        }


@dataclass
class Trade:
    symbol: str
    price: float
    qty: float
    side: Side
    ts: float
    trade_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FootprintBin:
    price: float
    buy_vol: float = 0.0
    sell_vol: float = 0.0
    trade_count: int = 0

    @property
    def delta(self) -> float:
        return self.buy_vol - self.sell_vol

    def to_dict(self) -> dict[str, Any]:
        return {
            "price": self.price,
            "buyVol": self.buy_vol,
            "sellVol": self.sell_vol,
            "tradeCount": self.trade_count,
            "delta": self.delta,
        }


@dataclass
class FootprintBar:
    symbol: str
    interval_ms: int
    start_ts: int
    bins: list[FootprintBin] = field(default_factory=list)

    @property
    def total_delta(self) -> float:
        return sum(b.delta for b in self.bins)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "intervalMs": self.interval_ms,
            "startTs": self.start_ts,
            "bins": [b.to_dict() for b in self.bins],
            "totalDelta": self.total_delta,
        }


@dataclass
class PlaceLimitRequest:
    account_id: str
    symbol: str
    side: Side
    price: float
    qty: float
    of_client_id: str
    post_only: bool = False


@dataclass
class OrderView:
    account_id: str
    order_id: str
    of_client_id: str
    symbol: str
    side: Side
    price: float
    qty: float
    filled_qty: float = 0.0
    status: str = "new"
    source: str = SOURCE_ORDERFLOW
    ts: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_of_client_id(suffix: str) -> str:
    return f"{OF_CLIENT_PREFIX}{suffix}"
