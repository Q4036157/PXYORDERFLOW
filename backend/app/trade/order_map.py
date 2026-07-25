"""本地 OF- client id ↔ int client_order_index 映射。"""
from __future__ import annotations

import itertools
import threading
import time
from dataclasses import dataclass, field


@dataclass
class OrderMapEntry:
    of_client_id: str
    client_order_index: int
    account_id: str
    symbol: str
    side: str
    price: float
    qty: float
    exchange_order_id: str = ""
    status: str = "new"
    ts: float = field(default_factory=time.time)


class OrderIdMapper:
    """
    Some venues use an integer client_order_index while the UI uses an
    OF-prefixed string. This table maintains both forms.
    """

    def __init__(self, start_index: int = 1_000_000) -> None:
        self._lock = threading.Lock()
        self._seq = itertools.count(start_index)
        self._by_of: dict[str, OrderMapEntry] = {}
        self._by_index: dict[int, OrderMapEntry] = {}
        self._by_exchange: dict[str, OrderMapEntry] = {}

    def allocate(
        self,
        of_client_id: str,
        *,
        account_id: str,
        symbol: str,
        side: str,
        price: float,
        qty: float,
    ) -> OrderMapEntry:
        if not of_client_id.startswith("OF-"):
            raise ValueError("of_client_id must start with OF-")
        with self._lock:
            if of_client_id in self._by_of:
                return self._by_of[of_client_id]
            idx = next(self._seq)
            entry = OrderMapEntry(
                of_client_id=of_client_id,
                client_order_index=idx,
                account_id=account_id,
                symbol=symbol,
                side=side,
                price=price,
                qty=qty,
            )
            self._by_of[of_client_id] = entry
            self._by_index[idx] = entry
            return entry

    def bind_exchange_id(self, of_client_id: str, exchange_order_id: str) -> None:
        with self._lock:
            entry = self._by_of.get(of_client_id)
            if not entry:
                return
            entry.exchange_order_id = exchange_order_id
            self._by_exchange[exchange_order_id] = entry

    def get_by_of(self, of_client_id: str) -> OrderMapEntry | None:
        return self._by_of.get(of_client_id)

    def get_by_exchange(self, exchange_order_id: str) -> OrderMapEntry | None:
        return self._by_exchange.get(exchange_order_id)

    def list_for_account(self, account_id: str) -> list[OrderMapEntry]:
        return [e for e in self._by_of.values() if e.account_id == account_id]
