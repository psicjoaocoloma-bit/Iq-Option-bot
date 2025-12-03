from typing import Any, Dict, List, Tuple

import numpy as np


DEFAULT_NUMERIC_FEATURE_KEYS: List[str] = [
    "payout",
    "volatility",
    "atr_micro",
    "trend_bias",
    "trend_slope",
    "trend_spread",
    "range_width",
    "range_tolerance",
    "bollinger_std",
    "bollinger_width",
    "bollinger_extreme",
    "micro_range_flag",
]


def _safe_get(data: Dict[str, Any], *keys: str, default: float = 0.0) -> float:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return float(default)
        current = current[key]
    try:
        return float(current)
    except Exception:
        return float(default)


def _bollinger_width(ctx: Dict[str, Any]) -> float:
    info = ctx.get("bollinger") or {}
    upper = info.get("upper")
    lower = info.get("lower")
    try:
        return float(upper) - float(lower)
    except Exception:
        return 0.0


def _bollinger_extreme(ctx: Dict[str, Any]) -> float:
    info = ctx.get("bollinger") or {}
    side = str(info.get("extreme_side", "") or "").lower()
    if side in {"upper", "up", "high"}:
        return 1.0
    if side in {"lower", "down", "low"}:
        return -1.0
    return 0.0


def extract_numeric_features_from_context(
    ctx: Dict[str, Any],
    feature_keys: List[str] | None = None,
) -> Tuple[np.ndarray, List[str]]:
    """Convert the persisted context dict into a numeric feature vector."""
    if feature_keys is None:
        feature_keys = DEFAULT_NUMERIC_FEATURE_KEYS

    mapping = {
        "payout": ("payout",),
        "volatility": ("volatility",),
        "atr_micro": ("atr_micro",),
        "trend_bias": ("trend", "bias"),
        "trend_slope": ("trend", "ema_slope"),
        "trend_spread": ("trend", "spread"),
        "range_width": ("range", "width"),
        "range_tolerance": ("range", "tolerance"),
        "bollinger_std": ("bollinger", "std"),
    }

    values: List[float] = []
    used_names: List[str] = []

    for key in feature_keys:
        if key == "bollinger_width":
            values.append(float(_bollinger_width(ctx)))
        elif key == "bollinger_extreme":
            values.append(float(_bollinger_extreme(ctx)))
        elif key == "micro_range_flag":
            values.append(1.0 if bool(ctx.get("micro_range")) else 0.0)
        else:
            path = mapping.get(key)
            if path is None:
                values.append(0.0)
            else:
                values.append(_safe_get(ctx, *path, default=0.0))
        used_names.append(key)

    return np.array(values, dtype="float32"), used_names


def normalize_candles(
    candles: List[Dict[str, Any]],
    candle_count: int,
) -> np.ndarray:
    """Normalize the last N OHLCV candles into a tensor of shape [N, 5]."""
    if not candles:
        return np.zeros((candle_count, 5), dtype="float32")

    if len(candles) > candle_count:
        candles = candles[-candle_count:]

    if len(candles) < candle_count:
        pad = candle_count - len(candles)
        filler = [{"open": 0, "high": 0, "low": 0, "close": 0, "volume": 0} for _ in range(pad)]
        candles = filler + candles

    opens = np.array([float(c.get("open", 0.0)) for c in candles], dtype="float32")
    highs = np.array([float(c.get("high", 0.0)) for c in candles], dtype="float32")
    lows = np.array([float(c.get("low", 0.0)) for c in candles], dtype="float32")
    closes = np.array([float(c.get("close", 0.0)) for c in candles], dtype="float32")
    volumes = np.array([float(c.get("volume", 0.0)) for c in candles], dtype="float32")

    mean_close = float(np.mean(closes)) or 1.0
    if mean_close == 0:
        mean_close = 1.0

    opens /= mean_close
    highs /= mean_close
    lows /= mean_close
    closes /= mean_close
    volumes = np.log1p(np.maximum(volumes, 0.0))

    stacked = np.stack([opens, highs, lows, closes, volumes], axis=1)
    return stacked.astype("float32")
