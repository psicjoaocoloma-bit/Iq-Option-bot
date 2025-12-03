import glob
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from .features import extract_numeric_features_from_context, normalize_candles


LOG_PATTERN = "logs/trades_*.jsonl"
DEFAULT_CANDLE_COUNT = 120


def _collect_events() -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for path in glob.glob(LOG_PATTERN):
        file_path = Path(path)
        with file_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                trade_id = payload.get("trade_id")
                if not trade_id:
                    continue
                grouped.setdefault(trade_id, []).append(payload)
    return grouped


def _pick_open_close(events: List[Dict[str, Any]]) -> Tuple[Dict[str, Any] | None, Dict[str, Any] | None]:
    open_evt = None
    close_evt = None
    for evt in events:
        status = str(evt.get("status", "")).upper()
        if status == "OPEN" and open_evt is None:
            open_evt = evt
        elif status == "CLOSE":
            close_evt = evt
    return open_evt, close_evt


def _label_from_close(close_evt: Dict[str, Any]) -> int:
    outcome = close_evt.get("outcome_real")
    if isinstance(outcome, str) and outcome:
        normalized = outcome.lower()
    else:
        broker_event = close_evt.get("broker_event", {}) or {}
        normalized = str(broker_event.get("result", "")).lower()

    if normalized == "win":
        return 1
    if normalized == "loss":
        return 0
    raise ValueError("Unsupported result")


def build_dataset(
    candle_count: int = DEFAULT_CANDLE_COUNT,
    output_path: str = "logs/autolearn_dataset.npz",
) -> None:
    events_by_id = _collect_events()

    X_samples: List[np.ndarray] = []
    y_samples: List[int] = []
    feature_names: List[str] = []

    for trade_id, events in events_by_id.items():
        open_evt, close_evt = _pick_open_close(events)
        if open_evt is None or close_evt is None:
            continue

        try:
            label = _label_from_close(close_evt)
        except ValueError:
            continue

        ctx = open_evt.get("context") or {}
        candles = ctx.get("candles") or []
        if len(candles) < 5:
            continue

        candle_tensor = normalize_candles(candles, candle_count=candle_count)
        candles_flat = candle_tensor.reshape(-1)

        numeric_vec, names = extract_numeric_features_from_context(ctx)
        if not feature_names:
            feature_names = names

        sample_vec = np.concatenate([candles_flat, numeric_vec], axis=0)
        X_samples.append(sample_vec.astype("float32"))
        y_samples.append(int(label))

    if not X_samples:
        raise RuntimeError(
            "No samples generated. Confirm context['candles'] is being logged."
        )

    X = np.vstack(X_samples).astype("float32")
    y_arr = np.array(y_samples, dtype="int64")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        output_path,
        X=X,
        y=y_arr,
        feature_names=np.array(feature_names),
        candle_count=int(candle_count),
    )

    print(f"[dataset_builder] Dataset saved to {output_path}")
    print(f"[dataset_builder] X shape={X.shape}, y shape={y_arr.shape}")


if __name__ == "__main__":
    build_dataset()
