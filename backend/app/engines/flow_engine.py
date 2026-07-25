"""成交聚合为 footprint bar（按价位量/笔/delta）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..models import FootprintBar, FootprintBin, Trade


def _bin_price(price: float, tick_size: float) -> float:
    if tick_size <= 0:
        return price
    # 用整数 tick index 减少浮点误差
    idx = round(price / tick_size)
    return idx * tick_size


@dataclass
class _BarStats:
    """OHLCV kept alongside footprint bins for the rolling chart window."""

    open: float
    high: float
    low: float
    close: float
    buy_vol: float = 0.0
    sell_vol: float = 0.0
    unknown_vol: float = 0.0
    trade_count: int = 0

    def add(self, price: float, qty: float, side: str) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.trade_count += 1
        if side == "buy":
            self.buy_vol += qty
        elif side == "sell":
            self.sell_vol += qty
        else:
            self.unknown_vol += qty

    @property
    def volume(self) -> float:
        return self.buy_vol + self.sell_vol + self.unknown_vol

    @property
    def delta(self) -> float:
        return self.buy_vol - self.sell_vol


class FlowEngine:
    def __init__(self, symbol: str, interval_ms: int = 60_000, tick_size: float = 0.1) -> None:
        self.symbol = symbol
        self.interval_ms = interval_ms
        self.tick_size = tick_size
        # start_ts -> price -> bin
        self._bars: dict[int, dict[float, FootprintBin]] = {}
        self._stats: dict[int, _BarStats] = {}
        self._tape: list[Trade] = []
        self._tape_max = 500
        self.cumulative_delta: float = 0.0
        # When old bars are pruned, retain their delta so the first retained bar
        # still has an honest cumulative-delta value.
        self._pruned_cvd: float = 0.0

    def on_trade(self, trade: Trade) -> None:
        if trade.symbol != self.symbol:
            return
        ts_ms = int(trade.ts if trade.ts > 10_000_000_000 else trade.ts * 1000)
        start = (ts_ms // self.interval_ms) * self.interval_ms
        bar = self._bars.setdefault(start, {})
        stats = self._stats.get(start)
        if stats is None:
            stats = _BarStats(open=trade.price, high=trade.price, low=trade.price, close=trade.price)
            self._stats[start] = stats
        stats.add(trade.price, trade.qty, trade.side)
        px = _bin_price(trade.price, self.tick_size)
        bin_ = bar.get(px)
        if bin_ is None:
            bin_ = FootprintBin(price=px)
            bar[px] = bin_
        if trade.side == "buy":
            bin_.buy_vol += trade.qty
            self.cumulative_delta += trade.qty
        elif trade.side == "sell":
            bin_.sell_vol += trade.qty
            self.cumulative_delta -= trade.qty
        else:
            # Unknown aggressor direction belongs on the tape/volume histogram but
            # must not be fabricated into CVD or a buy/sell footprint imbalance.
            bin_.unknown_vol += trade.qty
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

    def chart_snapshot(self, limit: int = 120) -> dict[str, Any]:
        """Return the bounded, self-contained model used by the chart canvas.

        ``startTs`` and ``endTs`` are Unix milliseconds.  ``cvd`` is the closing
        cumulative delta for that bar.  ``footprint.bins`` is sorted by price and
        contains the buy/sell volume at every traded tick.  The source is only the
        trade stream received since this OF process started; no invented history is
        returned before the first observed trade.
        """
        keys = sorted(self._bars.keys())[-max(1, limit):]
        # A limited request can begin after retained bars.  Include preceding bars
        # in the running calculation so CVD remains continuous at its left edge.
        all_keys = sorted(self._bars.keys())
        first = keys[0] if keys else None
        cvd = self._pruned_cvd
        out: list[dict[str, Any]] = []
        for start in all_keys:
            footprint = self.get_bar(start)
            stats = self._stats.get(start)
            if footprint is None or stats is None:
                continue
            cvd += footprint.total_delta
            if first is not None and start >= first:
                out.append(
                    {
                        "startTs": start,
                        "endTs": start + self.interval_ms,
                        "open": stats.open,
                        "high": stats.high,
                        "low": stats.low,
                        "close": stats.close,
                        "volume": stats.volume,
                        "buyVol": stats.buy_vol,
                        "sellVol": stats.sell_vol,
                        "unknownVol": stats.unknown_vol,
                        "delta": footprint.total_delta,
                        "cvd": cvd,
                        "tradeCount": stats.trade_count,
                        "footprint": footprint.to_dict(),
                    }
                )
        return {
            "symbol": self.symbol,
            "intervalMs": self.interval_ms,
            "bars": out,
            "cvd": self.cumulative_delta,
        }

    def prune(self, keep_bars: int = 120) -> None:
        if len(self._bars) <= keep_bars:
            return
        for key in sorted(self._bars.keys())[:-keep_bars]:
            raw = self._bars[key]
            self._pruned_cvd += sum(bin_.delta for bin_ in raw.values())
            del self._bars[key]
            self._stats.pop(key, None)
