from pathlib import Path
from typing import List, Tuple

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split

from .model import AutoLearnModel


def _load_dataset(path: str) -> Tuple[np.ndarray, np.ndarray, int, List[str]]:
    data = np.load(path, allow_pickle=True)
    X = data["X"].astype("float32")
    y = data["y"].astype("int64")
    candle_count = int(data["candle_count"])
    feature_names = list(data["feature_names"])
    return X, y, candle_count, feature_names


def train_autolearn(
    dataset_path: str = "logs/autolearn_dataset.npz",
    model_path: str = "dl_autolearn/autolearn_model.joblib",
) -> None:
    X, y, candle_count, feature_names = _load_dataset(dataset_path)

    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    clf = RandomForestClassifier(
        n_estimators=200,
        max_depth=None,
        min_samples_split=4,
        min_samples_leaf=2,
        n_jobs=-1,
        random_state=42,
    )
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_val)
    print("[train] Validation report:")
    print(classification_report(y_val, y_pred, digits=4))

    model = AutoLearnModel(
        candle_count=candle_count,
        feature_names=feature_names,
        classifier=clf,
    )
    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    model.save(model_path)
    print(f"[train] Model saved to {model_path}")


if __name__ == "__main__":
    train_autolearn()
