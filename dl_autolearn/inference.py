from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np

from .features import extract_numeric_features_from_context, normalize_candles
from .model import AutoLearnModel


_MODEL_CACHE: Optional[AutoLearnModel] = None
_MODEL_PATH_CACHE: Optional[str] = None


def _load_model_if_needed(model_path: str) -> Optional[AutoLearnModel]:
    global _MODEL_CACHE, _MODEL_PATH_CACHE

    resolved = str(model_path)
    if _MODEL_CACHE is not None and _MODEL_PATH_CACHE == resolved:
        return _MODEL_CACHE

    if not Path(resolved).exists():
        return None

    model = AutoLearnModel.load(resolved)
    _MODEL_CACHE = model
    _MODEL_PATH_CACHE = resolved
    return model


def autolearn_gate(
    context: Dict[str, Any],
    model_path: str = "dl_autolearn/autolearn_model.joblib",
    min_prob: float = 0.55,
) -> Tuple[Optional[float], bool]:
    """Return (prob_win, allow_trade) for the given context."""
    model = _load_model_if_needed(model_path)
    if model is None:
        return None, True

    candles = context.get("candles") or []
    if len(candles) < 5:
        return None, True

    candle_tensor = normalize_candles(candles, candle_count=model.candle_count)
    candles_flat = candle_tensor.reshape(-1)

    numeric_vec, _ = extract_numeric_features_from_context(context)
    sample = np.concatenate([candles_flat, numeric_vec], axis=0)[None, :]

    prob = float(model.predict_proba(sample)[0])
    allow = prob >= float(min_prob)
    return prob, allow
