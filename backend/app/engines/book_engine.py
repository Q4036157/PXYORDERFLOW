"""增量 L2 订单簿引擎。"""
from __future__ import annotations

from ..models import BookLevel, BookSnapshot


def _price_key(price: float | str) -> str:
    """规范化价位 key，避免 float map 抖动。"""
    if isinstance(price, str):
        raw = price.strip()
    else:
        raw = f"{float(price):.12f}"
    if "." in raw:
        raw = raw.rstrip("0").rstrip(".")
    return raw or "0"


class BookEngine:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self._bids: dict[str, float] = {}
        self._asks: dict[str, float] = {}
        self.ts: float = 0.0
        self.nonce: int | None = None
        self.last_nonce: int | None = None

    def apply_snapshot(
        self,
        bids: list[tuple[float | str, float | str]],
        asks: list[tuple[float | str, float | str]],
        ts: float,
        nonce: int | None = None,
    ) -> None:
        self._bids.clear()
        self._asks.clear()
        for price, qty in bids:
            q = float(qty)
            if q > 0:
                self._bids[_price_key(price)] = q
        for price, qty in asks:
            q = float(qty)
            if q > 0:
                self._asks[_price_key(price)] = q
        self.ts = ts
        if nonce is not None:
            self.nonce = nonce
            self.last_nonce = nonce

    def apply_delta(
        self,
        side: str,
        price: float | str,
        qty: float | str,
        ts: float,
        nonce: int | None = None,
        begin_nonce: int | None = None,
    ) -> bool:
        """
        应用单档增量。
        若提供 begin_nonce 且与 last_nonce 不连续，返回 False（调用方应重订阅快照）。
        """
        if (
            begin_nonce is not None
            and self.last_nonce is not None
            and begin_nonce != self.last_nonce
        ):
            return False

        key = _price_key(price)
        q = float(qty)
        book = self._bids if side in {"bid", "bids", "buy"} else self._asks
        if q <= 0:
            book.pop(key, None)
        else:
            book[key] = q
        self.ts = ts
        if nonce is not None:
            self.nonce = nonce
            self.last_nonce = nonce
        return True

    def apply_side_deltas(
        self,
        *,
        bids: list[dict] | None = None,
        asks: list[dict] | None = None,
        ts: float,
        nonce: int | None = None,
        begin_nonce: int | None = None,
    ) -> bool:
        if (
            begin_nonce is not None
            and self.last_nonce is not None
            and begin_nonce != self.last_nonce
        ):
            return False
        for row in bids or []:
            self.apply_delta("bid", row["price"], row.get("size", row.get("qty", 0)), ts)
        for row in asks or []:
            self.apply_delta("ask", row["price"], row.get("size", row.get("qty", 0)), ts)
        if nonce is not None:
            self.nonce = nonce
            self.last_nonce = nonce
        self.ts = ts
        return True

    def snapshot(self, depth: int = 50) -> BookSnapshot:
        bids = self._sorted(self._bids, reverse=True)[:depth]
        asks = self._sorted(self._asks, reverse=False)[:depth]
        return BookSnapshot(
            symbol=self.symbol,
            bids=bids,
            asks=asks,
            ts=self.ts,
            nonce=self.nonce,
        )

    @staticmethod
    def _sorted(book: dict[str, float], reverse: bool) -> list[BookLevel]:
        items = [BookLevel(price=float(p), qty=q) for p, q in book.items()]
        items.sort(key=lambda x: x.price, reverse=reverse)
        return items
