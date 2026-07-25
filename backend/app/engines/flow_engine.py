"""成交聚合为 footprint bar（按价位量/笔/delta）。"""
from __future__ import annotations

from ..models import FootprintBar, FootprintBin, Trade


def _bin_price(price: float, tick_size: float) -> float:
    if tick_size <= 0:
        return price
    # 用整数 tick index 减少浮点误差
    idx = round(price / tick_size)
    return idx * tick_size


class FlowEngine:
    def __init__(self, symbol: str, interval_ms: int = 60_000, tick_size: float = 0.1) -> None:
        self.symbol = symbol
        self.interval_ms = interval_ms
        self.tick_size = tick_size
        # start_ts -> price -> bin
        self._bars: dict[int, dict[float, FootprintBin]] = {}
        self._tape: list[Trade] = []
        self._tape_max = 500
        self.cumulative_delta: float = 0.0

    def on_trade(self, trade: Trade) -> None:
        if trade.symbol != self.symbol:
            return
        ts_ms = int(trade.ts if trade.ts > 10_000_000_000 else trade.ts * 1000)
        start = (ts_ms // self.interval_ms) * self.interval_ms
        bar = self._bars.setdefault(start, {})
        px = _bin_price(trade.price, self.tick_size)
        bin_ = bar.get(px)
        if bin_ is None:
            bin_ = FootprintBin(price=px)
            bar[px] = bin_
        if trade.side == "buy":
            bin_.buy_vol += trade.qty
            self.cumulative_delta += trade.qty
        else:
            bin_.sell_vol += trade.qty
            self.cumulative_delta -= trade.qty
        bin_.trade_count += 1

        self._tape.append(trade)
        if len(self._tape) > self._tape_max:
            self._tape = self._tape[-self._tape_max :]

    def get_bar(self, start_ts: int | None = None) -> FootprintBar | None:
        if not self._bars:
            return None
        if start_ts is None:
            start_ts = max(self._bars.keys())
        raw = self._bars.get(start_ts)
        if raw is None:
            return None
        bins = sorted(raw.values(), key=lambda b: b.price)
        return FootprintBar(
            symbol=self.symbol,
            interval_ms=self.interval_ms,
            start_ts=start_ts,
            bins=bins,
        )

    def recent_tape(self, limit: int = 50) -> list[Trade]:
        return self._tape[-limit:]

    def prune(self, keep_bars: int = 120) -> None:
        if len(self._bars) <= keep_bars:
            return
        for key in sorted(self._bars.keys())[:-keep_bars]:
            del self._bars[key]
