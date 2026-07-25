"""OF 专用风控门闩。"""
from __future__ import annotations

from dataclasses import dataclass

from ..models import OF_CLIENT_PREFIX, PlaceLimitRequest, SOURCE_ORDERFLOW


@dataclass
class RiskConfig:
    trading_enabled: bool = True
    max_order_qty: float = 100.0
    max_order_notional: float = 1_000_000.0


class RiskOf:
    def __init__(self, cfg: RiskConfig | None = None) -> None:
        self.cfg = cfg or RiskConfig()

    def assert_place(self, req: PlaceLimitRequest) -> None:
        if not self.cfg.trading_enabled:
            raise PermissionError("OF_TRADING disabled")
        if not req.of_client_id.startswith(OF_CLIENT_PREFIX):
            raise ValueError("of_client_id must start with OF-")
        if req.qty <= 0:
            raise ValueError("qty must be > 0")
        if req.qty > self.cfg.max_order_qty:
            raise ValueError(f"qty exceeds max_order_qty={self.cfg.max_order_qty}")
        if req.price <= 0:
            raise ValueError("price must be > 0")
        notional = req.price * req.qty
        if notional > self.cfg.max_order_notional:
            raise ValueError("notional too large")

    def assert_cancel_all(self, confirmed: bool) -> None:
        if not self.cfg.trading_enabled:
            raise PermissionError("OF_TRADING disabled")
        if not confirmed:
            raise PermissionError("cancelAll requires UI second confirm (confirmed=true)")
