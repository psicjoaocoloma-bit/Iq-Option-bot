"""Market collector feeding the TradingLions decision stack."""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Deque, Dict, Mapping, MutableMapping, Optional, Sequence

from config import SignalSettings
from indicators import (
    atr as indicator_atr,
    average_range,
    detect_micro_range as indicator_detect_micro_range,
    ema as indicator_ema,
    ema_series,
    impulse_direction,
    momentum_score,
)

PriceCandle = Mapping[str, Any]

DEFAULT_SIGNAL_SETTINGS = SignalSettings()


class MarketCollector:
    """Stores candles per asset/timeframe and exposes context metrics."""

    def __init__(
        self,
        signals_config: Optional[SignalSettings] = None,
        maxlen_m1: int = 720,
        maxlen_m5: int = 288,
    ) -> None:
        self.maxlen_m1 = maxlen_m1
        self.maxlen_m5 = maxlen_m5
        self._stores: Dict[str, Dict[str, Deque[MutableMapping[str, Any]]]] = {}
        self._payouts: Dict[str, float] = {}
        self._last_updates: Dict[str, float] = {}
        self._signals = signals_config or DEFAULT_SIGNAL_SETTINGS

    # ------------------------------------------------------------------
    # Ingestion / payout updates
    # ------------------------------------------------------------------
    def ingest(self, asset: str, timeframe: str, candle: Mapping[str, Any]) -> None:
        store = self._ensure_store(asset)
        tf_key = timeframe.upper()
        if tf_key not in store:
            return

        normalized = self._normalize_candle(candle)
        store[tf_key].append(normalized)
        self._last_updates[asset] = normalized.get("time", time.time())

    def update_payout(self, asset: str, payout: float) -> None:
        try:
            self._payouts[asset] = float(payout)
        except (TypeError, ValueError):
            self._payouts[asset] = 0.0

    # ------------------------------------------------------------------
    # Candle retrieval helpers
    # ------------------------------------------------------------------
    def get_candles_m1(self, asset: str, count: int = 180) -> Sequence[PriceCandle]:
        return list(self._ensure_store(asset)["M1"])[-count:]

    def get_candles_m5(self, asset: str, count: int = 120) -> Sequence[PriceCandle]:
        return list(self._ensure_store(asset)["M5"])[-count:]

    def get_payout(self, asset: str) -> float:
        return self._payouts.get(asset, 0.0)

    # ------------------------------------------------------------------
    # Technical computations
    # ------------------------------------------------------------------
    def compute_volatility(self, candles: Sequence[PriceCandle], window: int = 14) -> float:
        if len(candles) < 2:
            return 0.0
        sample = candles[-max(window, 2) :]
        period = max(1, min(window, len(sample) - 1))
        atr_value = indicator_atr(sample, period)
        if atr_value is None:
            return average_range(sample)
        return float(atr_value)

    def compute_ema(self, candles: Sequence[PriceCandle], period: int) -> float:
        closes = self._extract_closes(candles)
        if not closes:
            return 0.0
        value = indicator_ema(closes, period)
        return float(value) if value is not None else 0.0

    def compute_atr(self, candles: Sequence[PriceCandle], period: int = 14) -> float:
        if len(candles) < 2:
            return 0.0
        value = indicator_atr(candles, period)
        return float(value) if value is not None else 0.0

    def compute_otc_pivots(self, candles: Sequence[PriceCandle], lookback: int = 20) -> Dict[str, float]:
        """Calculate basic floor-trader pivots for OTC context."""

        if len(candles) < 2:
            return {}

        recent = candles[-max(lookback, 2):]
        highs: list[float] = []
        lows: list[float] = []
        closes: list[float] = []
        for candle in recent:
            try:
                highs.append(float(candle.get('max', candle.get('high', candle.get('close', 0.0)))))
                lows.append(float(candle.get('min', candle.get('low', candle.get('close', 0.0)))))
                closes.append(float(candle.get('close', 0.0)))
            except (TypeError, ValueError):
                continue

        if not highs or not lows or not closes:
            return {}

        high = max(highs)
        low = min(lows)
        close = closes[-1]
        pivot = (high + low + close) / 3.0
        range_ = high - low
        r1 = 2 * pivot - low
        s1 = 2 * pivot - high
        r2 = pivot + range_
        s2 = pivot - range_
        r3 = high + 2 * (pivot - low)
        s3 = low - 2 * (high - pivot)
        return {
            'pivot': pivot,
            'r1': r1,
            's1': s1,
            'r2': r2,
            's2': s2,
            'r3': r3,
            's3': s3,
            'high': high,
            'low': low,
        }


    def detect_range(self, candles: Sequence[PriceCandle], lookback: int = 40) -> Dict[str, float]:
        if len(candles) < 5:
            return {"lower": 0.0, "upper": 0.0, "width": 0.0, "tolerance": 0.0}
        recent = candles[-lookback:]
        lows = [float(c.get("min", c.get("low", 0.0))) for c in recent]
        highs = [float(c.get("max", c.get("high", 0.0))) for c in recent]
        raw_lower = min(lows)
        raw_upper = max(highs)
        width = raw_upper - raw_lower
        tolerance_pct = getattr(self._signals, "range_tolerance", 0.35)
        padding = width * max(0.0, min(1.0, tolerance_pct))
        lower = raw_lower + padding
        upper = raw_upper - padding
        if lower > upper:
            midpoint = (raw_lower + raw_upper) / 2.0
            lower = midpoint
            upper = midpoint
        return {
            "lower": lower,
            "upper": upper,
            "width": width,
            "raw_lower": raw_lower,
            "raw_upper": raw_upper,
            "tolerance": padding,
        }

    def detect_micro_range(self, candles: Sequence[PriceCandle], lookback: int = 6) -> bool:
        return indicator_detect_micro_range(
            candles,
            lookback=lookback,
            compression_ratio=0.25,
        )

    def detect_momentum(self, candles: Sequence[PriceCandle], lookback: int = 8) -> Dict[str, Any]:
        closes = self._extract_closes(candles)
        score = momentum_score(closes, lookback)
        atr_value = self.compute_volatility(candles, window=max(3, lookback))
        impulse: Optional[str] = None
        if candles:
            impulse = impulse_direction(candles[-1], atr_value)
            if impulse is None and len(candles) > 1:
                impulse = impulse_direction(candles[-2], atr_value)
        return {"last_impulse": impulse, "strength": float(score)}

    def detect_trend_bias(self, candles_m5: Sequence[PriceCandle]) -> Dict[str, Any]:
        fast_period = getattr(self._signals, "ema_period", 20)
        slow_period = fast_period * 2
        closes = self._extract_closes(candles_m5)
        if len(closes) < slow_period:
            return {
                "bias": 0.0,
                "ema_fast": 0.0,
                "ema_slow": 0.0,
                "ema_slope": 0.0,
                "state": "range",
            }

        fast_series = ema_series(closes, fast_period)
        slow_series = ema_series(closes, slow_period)
        ema_fast = fast_series[-1]
        ema_prev = fast_series[-2] if len(fast_series) >= 2 else ema_fast
        ema_slow = slow_series[-1] if len(slow_series) >= 1 else ema_fast
        ema_slope = ema_fast - ema_prev
        spread = ema_fast - ema_slow
        slope_threshold = getattr(self._signals, "trend_bias_threshold", 0.3)

        bias = 0.0
        if ema_fast > ema_slow and ema_slope > slope_threshold:
            bias = 1.0
        elif ema_fast < ema_slow and ema_slope < -slope_threshold:
            bias = -1.0

        state = "range"
        if bias > 0:
            state = "trend_up"
        elif bias < 0:
            state = "trend_down"

        return {
            "bias": bias,
            "ema_fast": float(ema_fast),
            "ema_slow": float(ema_slow),
            "ema_slope": float(ema_slope),
            "spread": float(spread),
            "state": state,
        }

    # ------------------------------------------------------------------
    # Snapshot interface
    # ------------------------------------------------------------------
    def get_snapshot(self, asset: str) -> Dict[str, Any]:
        candles_m1 = self.get_candles_m1(asset)
        candles_m5 = self.get_candles_m5(asset)

        ema_data = {
            "m1": {
                20: self.compute_ema(candles_m1, 20),
                50: self.compute_ema(candles_m1, 50),
            },
            "m5": {
                20: self.compute_ema(candles_m5, 20),
                50: self.compute_ema(candles_m5, 50),
            },
        }
        atr_data = {
            "m1": self.compute_atr(candles_m1, 14),
            "m5": self.compute_atr(candles_m5, 14),
        }

        pivots = self.compute_otc_pivots(candles_m1)

        price_range = self.detect_range(candles_m1)
        trend = self.detect_trend_bias(candles_m5)
        volatility = self.compute_volatility(candles_m1)
        micro_range = self.detect_micro_range(candles_m1)
        momentum = self.detect_momentum(candles_m1)
        last_update = self._last_updates.get(asset, 0.0)

        snapshot = {
            "asset": asset,
            "m1": candles_m1,
            "m5": candles_m5,
            "ema": ema_data,
            "atr": atr_data,
            "trend": trend,
            "range": price_range,
            "volatility": volatility,
            "micro_range": micro_range,
            "momentum": momentum,
            "pivots": pivots,
            "payout": self.get_payout(asset),
            "last_update": last_update,
            "timestamp": time.time(),
        }
        return snapshot

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_store(self, asset: str) -> Dict[str, Deque[MutableMapping[str, Any]]]:
        if asset not in self._stores:
            self._stores[asset] = {
                "M1": deque(maxlen=self.maxlen_m1),
                "M5": deque(maxlen=self.maxlen_m5),
            }
        return self._stores[asset]

    @staticmethod
    def _normalize_candle(candle: Mapping[str, Any]) -> MutableMapping[str, Any]:
        normalized: MutableMapping[str, Any] = {
            "open": float(candle.get("open", candle.get("o", 0.0))),
            "close": float(candle.get("close", candle.get("c", 0.0))),
            "min": float(candle.get("min", candle.get("low", 0.0))),
            "max": float(candle.get("max", candle.get("high", 0.0))),
        }
        if "time" in candle:
            normalized["time"] = float(candle["time"])
        elif "timestamp" in candle:
            normalized["time"] = float(candle["timestamp"])
        else:
            normalized["time"] = time.time()
        return normalized

    @staticmethod
    def _extract_closes(candles: Sequence[PriceCandle]) -> Sequence[float]:
        return [float(c.get("close", 0.0)) for c in candles]


__all__ = ["MarketCollector"]
