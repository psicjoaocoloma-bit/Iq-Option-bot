from dataclasses import dataclass
from pathlib import Path
from typing import List

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier


@dataclass
class AutoLearnModel:
    candle_count: int
    feature_names: List[str]
    classifier: RandomForestClassifier

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Return P(win) for each row in X."""
        proba = self.classifier.predict_proba(X)
        return proba[:, 1]

    def save(self, path: str) -> None:
        payload = {
            "candle_count": self.candle_count,
            "feature_names": self.feature_names,
            "classifier": self.classifier,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(payload, path)

    @classmethod
    def load(cls, path: str) -> "AutoLearnModel":
        payload = joblib.load(path)
        return cls(
            candle_count=int(payload["candle_count"]),
            feature_names=list(payload["feature_names"]),
            classifier=payload["classifier"],
        )
