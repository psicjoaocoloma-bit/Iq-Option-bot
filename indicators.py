"""Technical indicator helpers for TradingLions Reforged."""

from __future__ import annotations

from typing import Dict, List, Mapping, MutableSequence, Optional, Sequence, Tuple

Number = float


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def ema(values: Sequence[float], period: int) -> Optional[float]:
    """Compute the EMA of the provided values."""

    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < 1:
        return None

    multiplier = 2.0 / (period + 1.0)
    ema_value = values[0]
    for price in values[1:]:
        ema_value = (price - ema_value) * multiplier + ema_value
    return ema_value


def ema_series(values: Sequence[float], period: int) -> Sequence[float]:
    """Return an EMA value for every point in the sequence."""

    if len(values) < 1:
        return []
    multiplier = 2.0 / (period + 1.0)
    series: MutableSequence[float] = [values[0]]
    for price in values[1:]:
        series.append((price - series[-1]) * multiplier + series[-1])
    return series


def true_ranges(candles: Sequence[Mapping[str, Number]]) -> Sequence[float]:
    if len(candles) < 2:
        return []
    result: list[float] = []
    prev_close = _to_float(candles[0].get("close", 0.0))
    for candle in candles[1:]:
        high = _to_float(candle.get("max", candle.get("high", 0.0)))
        low = _to_float(candle.get("min", candle.get("low", 0.0)))
        close = _to_float(candle.get("close", prev_close))
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        result.append(tr)
        prev_close = close
    return result


def atr(candles: Sequence[Mapping[str, Number]], period: int = 14) -> Optional[float]:
    """Average true range (simple average of the last *period* true ranges)."""

    if period <= 0:
        raise ValueError("period must be positive")
    series = true_ranges(candles)
    if not series:
        return None
    sample = series[-period:]
    if not sample:
        return None
    return sum(sample) / len(sample)


def body_ratio(candle: Mapping[str, Number]) -> float:
    """Body size divided by total range (0-1)."""

    open_ = _to_float(candle.get("open", candle.get("o", 0.0)))
    close = _to_float(candle.get("close", candle.get("c", 0.0)))
    high = _to_float(candle.get("max", candle.get("high", 0.0)))
    low = _to_float(candle.get("min", candle.get("low", 0.0)))
    full_range = max(high - low, 1e-9)
    return abs(close - open_) / full_range


def wick_ratio(candle: Mapping[str, Number]) -> Tuple[float, float]:
    """Return (lower_wick_ratio, upper_wick_ratio)."""

    open_ = _to_float(candle.get("open", candle.get("o", 0.0)))
    close = _to_float(candle.get("close", candle.get("c", 0.0)))
    high = _to_float(candle.get("max", candle.get("high", 0.0)))
    low = _to_float(candle.get("min", candle.get("low", 0.0)))
    lower = min(open_, close)
    upper = max(open_, close)
    range_ = max(high - low, 1e-9)
    lower_wick = lower - low
    upper_wick = high - upper
    return lower_wick / range_, upper_wick / range_


def range_width(candles: Sequence[Mapping[str, Number]]) -> float:
    if not candles:
        return 0.0
    highs = [_to_float(c.get("max", c.get("high", 0.0))) for c in candles]
    lows = [_to_float(c.get("min", c.get("low", 0.0))) for c in candles]
    return max(highs) - min(lows)


def average_range(candles: Sequence[Mapping[str, Number]]) -> float:
    if not candles:
        return 0.0
    segments = [_to_float(c.get("max", c.get("high", 0.0))) - _to_float(c.get("min", c.get("low", 0.0))) for c in candles]
    return sum(segments) / len(segments)


def momentum_score(closes: Sequence[float], lookback: int = 5) -> float:
    if lookback <= 0 or len(closes) < lookback:
        return 0.0
    subset = closes[-lookback:]
    if len(subset) < 2:
        return 0.0
    delta = subset[-1] - subset[0]
    amplitude = max(subset) - min(subset)
    amplitude = amplitude or 1e-9
    return delta / amplitude


def detect_micro_range(
    candles: Sequence[Mapping[str, Number]],
    lookback: int = 5,
    compression_ratio: float = 0.2,
) -> bool:
    if len(candles) < lookback:
        return False
    recent = candles[-lookback:]
    width = range_width(recent)
    avg = average_range(recent)
    if avg <= 0:
        return True
    return width <= avg * compression_ratio


def impulse_direction(
    candle: Mapping[str, Number],
    baseline_range: float,
    body_threshold: float = 0.6,
    range_multiplier: float = 1.4,
) -> Optional[str]:
    """Detect whether the candle qualifies as an impulse."""

    high = _to_float(candle.get("max", candle.get("high", 0.0)))
    low = _to_float(candle.get("min", candle.get("low", 0.0)))
    open_ = _to_float(candle.get("open", candle.get("o", 0.0)))
    close = _to_float(candle.get("close", candle.get("c", 0.0)))
    range_ = high - low
    if baseline_range <= 0:
        baseline_range = range_
    if range_ < baseline_range * range_multiplier:
        return None
    if body_ratio(candle) < body_threshold:
        return None
    if close > open_:
        return "bullish"
    if close < open_:
        return "bearish"
    return None


def multi_timeframe_alignment(lower_bias: float, higher_bias: float) -> float:
    """Return signed confirmation (+1, -1 or 0)."""

    if lower_bias == 0 or higher_bias == 0:
        return 0.0
    if (lower_bias > 0 and higher_bias > 0) or (lower_bias < 0 and higher_bias < 0):
        return float(lower_bias)
    return 0.0


def price_position(price: float, lower: float, upper: float) -> float:
    """Return price position inside a range (0 bottom, 1 top)."""

    if upper <= lower:
        return 0.5
    return (price - lower) / (upper - lower)



def bollinger_extreme(candle: Dict, upper: float, lower: float) -> Tuple[Optional[str], bool]:
    """Return which side of the Bollinger band was breached, if any."""

    close = candle.get("close")
    if close is None:
        return None, False

    try:
        close_value = float(close)
    except (TypeError, ValueError):
        return None, False

    if close_value > upper:
        return "upper", True
    if close_value < lower:
        return "lower", True
    return None, False



def atr_micro(candles: List[Dict]) -> float:
    """Simplified ATR using the true range of the last few candles."""

    if len(candles) < 2:
        return 0.0

    trs: List[float] = []
    for i in range(1, len(candles)):
        high = candles[i].get("max")
        low = candles[i].get("min")
        prev_close = candles[i - 1].get("close")

        if high is None or low is None or prev_close is None:
            continue

        try:
            high_f = float(high)
            low_f = float(low)
            prev_close_f = float(prev_close)
        except (TypeError, ValueError):
            continue

        tr1 = high_f - low_f
        tr2 = abs(high_f - prev_close_f)
        tr3 = abs(low_f - prev_close_f)
        trs.append(max(tr1, tr2, tr3))

    if not trs:
        return 0.0
    return sum(trs) / len(trs)



def fibo_zones(candles: List[Dict]) -> Dict[str, float]:
    """Compute Fibonacci-like zones from the full range of the candles."""

    if not candles:
        return {}

    highs = [c.get("max") for c in candles if c.get("max") is not None]
    lows = [c.get("min") for c in candles if c.get("min") is not None]

    if not highs or not lows:
        return {}

    try:
        high = max(float(h) for h in highs)
        low = min(float(l) for l in lows)
    except (TypeError, ValueError):
        return {}

    rng = high - low
    if rng <= 0:
        level = (high + low) / 2.0
        return {key: level for key in ("0.382", "0.5", "0.618", "0.786")}

    def _level(ratio: float) -> float:
        return high - rng * ratio

    return {
        "0.382": _level(0.382),
        "0.5": _level(0.5),
        "0.618": _level(0.618),
        "0.786": _level(0.786),
    }


__all__ = [
    "ema",
    "ema_series",
    "true_ranges",
    "atr",
    "body_ratio",
    "wick_ratio",
    "range_width",
    "average_range",
    "momentum_score",
    "detect_micro_range",
    "impulse_direction",
    "multi_timeframe_alignment",
    "price_position",
    "bollinger_extreme",
    "atr_micro",
    "fibo_zones",
]
