"""Deterministic helpers shared by collector and decision engine."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def safe_float(value: Any, default: float = 0.0) -> float:
    """Convert arbitrary values to float, falling back to a safe default."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def candle_range(candle: Mapping[str, Any]) -> float:
    """Return candle high-low distance using either max/min or high/low keys."""

    high = safe_float(candle.get("max", candle.get("high", 0.0)))
    low = safe_float(candle.get("min", candle.get("low", 0.0)))
    return high - low


def is_candle_bullish(candle: Mapping[str, Any]) -> bool:
    """True when close is strictly above open (green candle)."""

    return safe_float(candle.get("close")) > safe_float(candle.get("open"))


def is_candle_bearish(candle: Mapping[str, Any]) -> bool:
    """True when close is strictly below open (red candle)."""

    return safe_float(candle.get("close")) < safe_float(candle.get("open"))


def normalize_direction(direction: Any) -> str:
    """Normalize miscellaneous direction flags into 'call' or 'put'."""

    value = str(direction or "").strip().lower()
    if value in {"call", "buy", "long", "up", "bull"}:
        return "call"
    if value in {"put", "sell", "short", "down", "bear"}:
        return "put"
    raise ValueError("direction must normalize to 'call' or 'put'")


def ema(values: Sequence[Any], period: int) -> float:
    """Simple EMA tailored for short M5 trend windows."""

    sequence = [safe_float(v) for v in values]
    if not sequence:
        return 0.0
    period = max(1, int(period))
    multiplier = 2 / (period + 1)
    ema_value = sequence[0]
    for price in sequence[1:]:
        ema_value = (price - ema_value) * multiplier + ema_value
    return ema_value


__all__ = [
    "safe_float",
    "candle_range",
    "is_candle_bullish",
    "is_candle_bearish",
    "normalize_direction",
    "ema",
]
