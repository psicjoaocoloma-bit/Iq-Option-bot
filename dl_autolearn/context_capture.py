import time
from typing import Any, Dict, List, Optional


def fetch_candles(
    api: Any,
    asset: str,
    timeframe_sec: int = 60,
    count: int = 120,
    end_from: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return the latest `count` candles from IQ Option in OHLCV format."""
    if api is None:
        return []

    if end_from is None:
        end_from = int(time.time())

    try:
        raw_candles = api.get_candles(asset, timeframe_sec, count, end_from)
    except Exception:
        return []

    candles: List[Dict[str, Any]] = []
    for candle in raw_candles:
        candles.append(
            {
                "timestamp": candle.get("from"),
                "open": float(candle.get("open", 0.0)),
                "high": float(candle.get("max", candle.get("high", 0.0))),
                "low": float(candle.get("min", candle.get("low", 0.0))),
                "close": float(candle.get("close", 0.0)),
                "volume": float(candle.get("volume", 0.0)),
            }
        )

    candles.sort(key=lambda item: item.get("timestamp") or 0)
    return candles


def attach_candles_to_context(
    api: Any,
    context: Optional[Dict[str, Any]],
    asset: str,
    timeframe_sec: int = 60,
    candle_count: int = 120,
) -> Dict[str, Any]:
    """Attach a `candles` block to the context dict if it is missing."""
    if context is None:
        context = {}

    if context.get("candles"):
        return context

    candles = fetch_candles(
        api=api,
        asset=asset,
        timeframe_sec=timeframe_sec,
        count=candle_count,
    )

    context["candles"] = candles
    context["candles_timeframe_sec"] = timeframe_sec
    context["candles_count"] = len(candles)
    return context
