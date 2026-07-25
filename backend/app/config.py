"""Runtime configuration loaded exclusively from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    bind_host: str = "127.0.0.1"
    http_port: int = 3811
    trading_enabled: bool = True
    md_mode: str = "mock"  # mock | lighter
    trade_mode: str = "mock"
    lighter_host: str = "mainnet.zklighter.elliot.ai"
    lighter_market_id: int = 1
    lighter_symbol: str = "BTC"
    tick_size: float = 0.1
    bar_interval_ms: int = 60_000
    lighter_rest_poll_sec: float = 0.4
    lighter_prefer_ws: bool = True
    max_order_qty: float = 100.0
    max_order_notional: float = 10_000.0
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:3810",
        "http://localhost:3810",
        "https://pxy.xyz.hr",
        "http://pxy.xyz.hr",
    )

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            bind_host=os.getenv("OF_BIND_HOST", "127.0.0.1"),
            http_port=int(os.getenv("OF_HTTP_PORT", "3811")),
            trading_enabled=_env_bool("OF_TRADING", True),
            md_mode=os.getenv("OF_MD_MODE", "mock").lower(),
            trade_mode=os.getenv("OF_TRADE_MODE", "mock").lower(),
            lighter_host=os.getenv("OF_LIGHTER_HOST", "mainnet.zklighter.elliot.ai"),
            lighter_market_id=int(os.getenv("OF_LIGHTER_MARKET_ID", "1")),
            lighter_symbol=os.getenv("OF_LIGHTER_SYMBOL", "BTC"),
            tick_size=float(os.getenv("OF_TICK_SIZE", "0.1")),
            bar_interval_ms=int(os.getenv("OF_BAR_INTERVAL_MS", "60000")),
            lighter_rest_poll_sec=float(os.getenv("OF_LIGHTER_REST_POLL_SEC", "0.4")),
            lighter_prefer_ws=_env_bool("OF_LIGHTER_PREFER_WS", True),
            max_order_qty=float(os.getenv("OF_MAX_ORDER_QTY", "100")),
            max_order_notional=float(
                os.getenv("OF_MAX_ORDER_NOTIONAL", "10000")
            ),
        )


settings = Settings.from_env()
