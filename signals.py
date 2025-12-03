"""Price action helpers for TradingLions Reforged."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence, Tuple

from indicators import body_ratio, detect_micro_range, wick_ratio

Candle = Mapping[str, Any]
PatternSignal = Tuple[Optional[str], Optional[str]]


def detect_bullish_pattern(candles: Sequence[Candle]) -> PatternSignal:
    """Return (pattern, reason) if a bullish setup is present."""

    if len(candles) < 2:
        return None, None
    last3 = candles[-3:]
    if detect_micro_range(last3, lookback=len(last3), compression_ratio=0.18):
        return None, "micro range"

    prev = last3[-2]
    last = last3[-1]
    if _engulfing(prev, last, bullish=True):
        return "engulfing", "bullish engulfing"
    if _momentum_bar(last, bullish=True):
        return "momentum", "bullish impulse"
    if _reversal(prev, last, bullish=True):
        return "reversal", "bullish rejection"
    return None, None


def detect_bearish_pattern(candles: Sequence[Candle]) -> PatternSignal:
    """Return (pattern, reason) if a bearish setup is present."""

    if len(candles) < 2:
        return None, None
    last3 = candles[-3:]
    if detect_micro_range(last3, lookback=len(last3), compression_ratio=0.18):
        return None, "micro range"

    prev = last3[-2]
    last = last3[-1]
    if _engulfing(prev, last, bullish=False):
        return "engulfing", "bearish engulfing"
    if _momentum_bar(last, bullish=False):
        return "momentum", "bearish impulse"
    if _reversal(prev, last, bullish=False):
        return "reversal", "bearish rejection"
    return None, None


def _engulfing(prev: Candle, last: Candle, bullish: bool) -> bool:
    prev_high = float(prev.get("max", prev.get("high", 0.0)))
    prev_low = float(prev.get("min", prev.get("low", 0.0)))
    last_open = float(last.get("open", last.get("o", 0.0)))
    last_close = float(last.get("close", last.get("c", 0.0)))
    if bullish:
        return last_close > last_open and last_close >= prev_high and last_open <= prev_low
    return last_close < last_open and last_close <= prev_low and last_open >= prev_high


def _momentum_bar(candle: Candle, bullish: bool) -> bool:
    ratio = body_ratio(candle)
    lower_wick, upper_wick = wick_ratio(candle)
    open_ = float(candle.get("open", 0.0))
    close = float(candle.get("close", 0.0))
    if bullish:
        return close > open_ and ratio >= 0.6 and upper_wick <= 0.25
    return close < open_ and ratio >= 0.6 and lower_wick <= 0.25


def _reversal(prev: Candle, last: Candle, bullish: bool) -> bool:
    lower_wick, upper_wick = wick_ratio(last)
    ratio = body_ratio(last)
    open_ = float(last.get("open", 0.0))
    close = float(last.get("close", 0.0))
    if bullish:
        # Hammer-like rejection at lows
        return close > open_ and lower_wick >= 0.5 and ratio <= 0.4
    return close < open_ and upper_wick >= 0.5 and ratio <= 0.4


def describe_pattern(pattern: Optional[str], fallback: str = "pattern") -> str:
    if not pattern:
        return fallback
    return pattern


__all__ = [
    "detect_bullish_pattern",
    "detect_bearish_pattern",
    "describe_pattern",
]
