````markdown
# TradingLions_Reforged_AUTOLEARNING_CONTEXT_PATCH.md

Este patch hace tres cosas principales:

1. **Extiende el `context` de cada operación** para incluir:
   - Las **últimas N velas crudas** (OHLCV).
   - Las **features derivadas** compartidas entre logging y autolearning.

2. **Crea un pipeline de AutoLearning** en `dl_autolearn/` que:
   - Lee los JSONL (`logs/trades_*.jsonl`).
   - Une eventos `OPEN` y `CLOSE` por `trade_id`.
   - Extrae **matrices de velas + vectores de features**.
   - Entrena un modelo supervisado (RandomForest) para predecir `WIN/LOSS`.

3. **Provee una puerta de decisión (`gate`) reutilizable** para que el Decision Engine pueda:
   - Cargar el modelo entrenado.
   - Calcular `probabilidad_de_WIN` para el contexto actual.
   - Aceptar o vetar operaciones según un `min_prob` configurable.

---

## 0. Dependencias nuevas (para que todo funcione)

Instala estas librerías en tu entorno (idealmente en tu venv del bot):

```bash
pip install numpy scikit-learn joblib
````

---

## 1. Nuevo módulo: `dl_autolearn/context_capture.py`

**Objetivo:** tener una función estándar para obtener N velas crudas desde IQ Option y adjuntarlas al `context` que ya guardas en los JSONL.

Crea el archivo:

**`dl_autolearn/context_capture.py`**

```python
import time
from typing import Any, Dict, List, Optional


def fetch_candles(
    api: Any,
    asset: str,
    timeframe_sec: int = 60,
    count: int = 120,
    end_from: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Obtiene las últimas `count` velas OHLCV desde IQ Option para el par/timeframe dado.

    api: instancia conectada de IQ_Option (iqoptionapi).
    asset: string del activo, por ej. 'EURUSD-OTC'.
    timeframe_sec: periodo de cada vela en segundos (60 = M1, 300 = M5, etc.).
    count: número de velas a capturar.
    end_from: timestamp final (segundos). Si es None, usa time.time().
    """
    if api is None:
        return []

    if end_from is None:
        end_from = int(time.time())

    try:
        raw_candles = api.get_candles(asset, timeframe_sec, count, end_from)
    except Exception:
        return []

    candles: List[Dict[str, Any]] = []
    for c in raw_candles:
        # Formato típico de iqoptionapi.get_candles:
        # {
        #   "id": 123,
        #   "from": 1700000000,
        #   "to": 1700000060,
        #   "open": ...,
        #   "close": ...,
        #   "min": ...,
        #   "max": ...,
        #   "volume": ...
        # }
        candles.append(
            {
                "timestamp": c.get("from"),
                "open": float(c.get("open", 0.0)),
                "high": float(c.get("max", 0.0)),
                "low": float(c.get("min", 0.0)),
                "close": float(c.get("close", 0.0)),
                "volume": float(c.get("volume", 0.0)),
            }
        )

    # Ordenar de más antiguo a más reciente por seguridad
    candles.sort(key=lambda x: x["timestamp"] or 0)
    return candles


def attach_candles_to_context(
    api: Any,
    context: Dict[str, Any],
    asset: str,
    timeframe_sec: int = 60,
    candle_count: int = 120,
) -> Dict[str, Any]:
    """
    Adjunta un bloque 'candles' al dict context utilizado en los JSONL.

    Si ya existe `context["candles"]`, no lo pisa (para evitar duplicados).
    """
    if context is None:
        context = {}

    if "candles" in context and context["candles"]:
        # Ya hay velas adjuntas
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
```

---

## 2. Nuevo módulo compartido de features: `dl_autolearn/features.py`

**Objetivo:** tener una **única forma** de convertir el `context` (lo que ya guardas) en un vector numérico estable, reutilizable tanto para entrenamiento como para inferencia.

Crea:

**`dl_autolearn/features.py`**

```python
from typing import Any, Dict, List, Tuple
import numpy as np


# Orden fija de features derivadas desde context["context"]
DEFAULT_NUMERIC_FEATURE_KEYS: List[str] = [
    # contexto general
    "payout",
    "volatility",
    "atr_micro",
    # trend
    "trend_angle",
    "trend_strength",
    "trend_slope",
    # rango
    "range_width",
    "range_tolerance",
    # bollinger
    "boll_width",
    "boll_zscore",
    # donchian
    "donchian_position",
    "donchian_width",
    # micro estructura
    "micro_demand_strength",
    "micro_supply_strength",
]


def _safe_get(d: Dict[str, Any], *keys: str, default: float = 0.0) -> float:
    """
    Acceso seguro a un path de keys anidadas: _safe_get(ctx, "trend", "angle").
    Devuelve default si falta alguno.
    """
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return float(default)
        cur = cur[k]
    try:
        return float(cur)
    except Exception:
        return float(default)


def extract_numeric_features_from_context(
    ctx: Dict[str, Any],
    feature_keys: List[str] = None,
) -> Tuple[np.ndarray, List[str]]:
    """
    Extrae un vector de features numéricas desde el dict context que ya guardas
    en los JSONL (ctx["context"]).

    Devuelve:
        vector: np.ndarray shape (n_features,)
        feature_names: lista de nombres en el mismo orden que el vector.
    """
    if feature_keys is None:
        feature_keys = DEFAULT_NUMERIC_FEATURE_KEYS

    # Mapping lógico entre nombre lógico y ruta dentro del contexto
    # Ajustable según los campos reales de tu Decision Engine.
    mapping = {
        "payout": ("payout",),
        "volatility": ("volatility",),
        "atr_micro": ("atr_micro",),
        "trend_angle": ("trend", "angle"),
        "trend_strength": ("trend", "strength"),
        "trend_slope": ("trend", "slope"),
        "range_width": ("range", "width"),
        "range_tolerance": ("range", "tolerance"),
        "boll_width": ("bollinger", "width"),
        "boll_zscore": ("bollinger", "zscore"),
        "donchian_position": ("donchian", "position"),
        "donchian_width": ("donchian", "width"),
        "micro_demand_strength": ("micro", "demand_strength"),
        "micro_supply_strength": ("micro", "supply_strength"),
    }

    values: List[float] = []
    used_names: List[str] = []

    for key in feature_keys:
        path = mapping.get(key)
        if path is None:
            # si no hay mapeo, usar 0.0
            values.append(0.0)
            used_names.append(key)
            continue

        v = _safe_get(ctx, *path, default=0.0)
        values.append(v)
        used_names.append(key)

    return np.array(values, dtype="float32"), used_names


def normalize_candles(
    candles: List[Dict[str, Any]],
    candle_count: int,
) -> np.ndarray:
    """
    Normaliza y empaqueta las velas en un tensor [candle_count, 5] (OHLCV).

    - Rellena con ceros si hay menos velas.
    - Toma las últimas `candle_count` si hay más.
    - Normaliza precios dividiéndolos por el close medio de la ventana.
    """
    if not candles:
        return np.zeros((candle_count, 5), dtype="float32")

    # Tomar solo las últimas N
    if len(candles) > candle_count:
        candles = candles[-candle_count:]

    # Rellenar al inicio si faltan
    if len(candles) < candle_count:
        pad = candle_count - len(candles)
        zeros = [{"open": 0, "high": 0, "low": 0, "close": 0, "volume": 0}] * pad
        candles = zeros + candles

    o = np.array([c.get("open", 0.0) for c in candles], dtype="float32")
    h = np.array([c.get("high", 0.0) for c in candles], dtype="float32")
    l = np.array([c.get("low", 0.0) for c in candles], dtype="float32")
    c_ = np.array([c.get("close", 0.0) for c in candles], dtype="float32")
    v = np.array([c.get("volume", 0.0) for c in candles], dtype="float32")

    # Normalización por el close medio (evita overflow por precios grandes)
    mean_close = float(np.mean(c_)) if float(np.mean(c_)) != 0 else 1.0
    o /= mean_close
    h /= mean_close
    l /= mean_close
    c_ /= mean_close

    # Normalizar volumen logarítmico aproximado
    v = np.log1p(v)

    mat = np.stack([o, h, l, c_, v], axis=1)  # [N, 5]
    return mat.astype("float32")
```

---

## 3. Nuevo dataset builder: `dl_autolearn/dataset_builder.py`

**Objetivo:** leer `logs/trades_*.jsonl`, unir OPEN/CLOSE por `trade_id`, extraer:

* `X_candles`: matriz de velas normalizadas (flattened).
* `X_features`: vector de features.
* `y`: etiqueta (1 = WIN, 0 = LOSS, se descartan DRAW).

Crea / reemplaza:

**`dl_autolearn/dataset_builder.py`**

```python
import glob
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from .features import (
    extract_numeric_features_from_context,
    normalize_candles,
)


LOG_PATTERN = "logs/trades_*.jsonl"
DEFAULT_CANDLE_COUNT = 120


def _collect_events() -> Dict[str, List[Dict[str, Any]]]:
    """
    Lee todos los JSONL de logs y agrupa los eventos por trade_id.
    """
    by_id: Dict[str, List[Dict[str, Any]]] = {}

    for path in glob.glob(LOG_PATTERN):
        p = Path(path)
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                trade_id = obj.get("trade_id")
                if not trade_id:
                    continue
                by_id.setdefault(trade_id, []).append(obj)

    return by_id


def _pick_open_close(events: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Dado el listado de eventos de un trade_id,
    selecciona OPEN y CLOSE (último CLOSE).
    """
    open_evt = None
    close_evt = None

    for evt in events:
        status = evt.get("status")
        if status == "OPEN" and open_evt is None:
            open_evt = evt
        elif status == "CLOSE":
            close_evt = evt

    return open_evt, close_evt


def _label_from_close(close_evt: Dict[str, Any]) -> int:
    """
    Devuelve 1 (WIN) o 0 (LOSS) a partir del evento CLOSE.

    Usa outcome_real si está, de lo contrario cae a broker_event["result"].
    Ignora DRAW (levanta ValueError).
    """
    if close_evt is None:
        raise ValueError("No close_evt")

    outcome = close_evt.get("outcome_real")
    if isinstance(outcome, str):
        result = outcome.lower()
    else:
        # fallback a broker_event
        broker = close_evt.get("broker_event", {})
        result = str(broker.get("result", "")).lower()

    if result == "win":
        return 1
    if result == "loss":
        return 0

    # DRAW u otros estados -> ignorar este trade
    raise ValueError(f"Unsupported result={result}")


def build_dataset(
    candle_count: int = DEFAULT_CANDLE_COUNT,
    output_path: str = "logs/autolearn_dataset.npz",
) -> None:
    """
    Construye el dataset para autolearning y lo guarda en un archivo .npz:

        - X: features combinadas [n_samples, n_flat_features]
        - y: etiquetas [n_samples]
        - feature_names: nombres de las features derivadas
        - candle_count: N de velas usado

    X se compone de:
        [ candles_flat (candle_count * 5) || numeric_features ]
    """
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
            # resultado no soportado (DRAW, etc.)
            continue

        ctx = open_evt.get("context") or {}
        candles = ctx.get("candles") or []

        if len(candles) < 5:
            # si aún no se está guardando candles, lo saltamos
            continue

        candles_tensor = normalize_candles(candles, candle_count=candle_count)
        candles_flat = candles_tensor.reshape(-1)  # [candle_count * 5]

        numeric_vec, names = extract_numeric_features_from_context(ctx)
        if not feature_names:
            feature_names = names

        # concatenar: [candles_flat || numeric_vec]
        sample_vec = np.concatenate([candles_flat, numeric_vec], axis=0)

        X_samples.append(sample_vec)
        y_samples.append(label)

    if not X_samples:
        raise RuntimeError("No se generaron muestras para autolearning. "
                           "¿Ya estás guardando context['candles'] en los JSONL?")

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

    print(f"[dataset_builder] Dataset guardado en {output_path}")
    print(f"[dataset_builder] X shape={X.shape}, y shape={y_arr.shape}")


if __name__ == "__main__":
    build_dataset()
```

---

## 4. Nuevo módulo de modelo: `dl_autolearn/model.py`

**Objetivo:** encapsular el modelo de ML (RandomForest) y su serialización.

Crea / reemplaza:

**`dl_autolearn/model.py`**

```python
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
        """
        Devuelve la probabilidad de WIN para cada muestra.
        X shape: [n_samples, n_features]
        """
        proba = self.classifier.predict_proba(X)
        # índice 1 = clase "WIN"
        return proba[:, 1]

    def save(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "candle_count": self.candle_count,
            "feature_names": self.feature_names,
            "classifier": self.classifier,
        }
        joblib.dump(payload, path)

    @classmethod
    def load(cls, path: str) -> "AutoLearnModel":
        payload = joblib.load(path)
        return cls(
            candle_count=payload["candle_count"],
            feature_names=list(payload["feature_names"]),
            classifier=payload["classifier"],
        )
```

---

## 5. Nuevo módulo de entrenamiento: `dl_autolearn/train.py`

**Objetivo:** cargar el dataset `.npz`, entrenar el RandomForest, guardar el modelo.

Crea / reemplaza:

**`dl_autolearn/train.py`**

```python
from pathlib import Path
from typing import Tuple

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split

from .model import AutoLearnModel


def _load_dataset(path: str) -> Tuple[np.ndarray, np.ndarray, int, list]:
    data = np.load(path, allow_pickle=True)
    X = data["X"].astype("float32")
    y = data["y"].astype("int64")
    feature_names = list(data["feature_names"])
    candle_count = int(data["candle_count"])
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
    print("[train] Reporte de validación:")
    print(classification_report(y_val, y_pred, digits=4))

    model = AutoLearnModel(
        candle_count=candle_count,
        feature_names=feature_names,
        classifier=clf,
    )
    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    model.save(model_path)
    print(f"[train] Modelo guardado en {model_path}")


if __name__ == "__main__":
    train_autolearn()
```

---

## 6. Nuevo módulo de inferencia / gate: `dl_autolearn/inference.py`

**Objetivo:** ofrecer una función reutilizable que, dado un `context` (el mismo que logueas en los JSONL, con `candles` + features), construya el mismo vector que el dataset y devuelva probabilidad de WIN y sugerencia de si abrir trade o no.

Crea:

**`dl_autolearn/inference.py`**

```python
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np

from .features import (
    extract_numeric_features_from_context,
    normalize_candles,
)
from .model import AutoLearnModel

_MODEL_CACHE: Optional[AutoLearnModel] = None
_MODEL_PATH_CACHE: Optional[str] = None


def _load_model_if_needed(model_path: str) -> Optional[AutoLearnModel]:
    global _MODEL_CACHE, _MODEL_PATH_CACHE
    path = str(model_path)

    if _MODEL_CACHE is not None and _MODEL_PATH_CACHE == path:
        return _MODEL_CACHE

    if not Path(path).exists():
        return None

    model = AutoLearnModel.load(path)
    _MODEL_CACHE = model
    _MODEL_PATH_CACHE = path
    return model


def autolearn_gate(
    context: Dict[str, Any],
    model_path: str = "dl_autolearn/autolearn_model.joblib",
    min_prob: float = 0.55,
) -> Tuple[Optional[float], bool]:
    """
    Calcula la probabilidad de WIN para el contexto dado y decide si
    pasa o no el gate de AutoLearning.

    Devuelve:
        (prob_win, allow_trade)
        - prob_win: None si no hay modelo o falta info.
        - allow_trade: bool (True si prob_win >= min_prob o si no hay modelo).
    """
    model = _load_model_if_needed(model_path)
    if model is None:
        # Sin modelo, no bloqueamos el trade
        return None, True

    candles = context.get("candles") or []
    if len(candles) < 5:
        return None, True

    candle_count = model.candle_count
    numeric_vec, _ = extract_numeric_features_from_context(context)
    candles_tensor = normalize_candles(candles, candle_count=candle_count)
    candles_flat = candles_tensor.reshape(-1)

    sample_vec = np.concatenate([candles_flat, numeric_vec], axis=0)[None, :]  # [1, F]
    prob = float(model.predict_proba(sample_vec)[0])

    allow = prob >= float(min_prob)
    return prob, allow
```

---

## 7. Integrar velas al `context` que ya guardas en los JSONL

Ahora que existen las funciones de captura de velas, hay que **adjuntar las velas al `context` en el momento en que se construye** (antes de loguear el OPEN).

En tu repo ya existe un lugar donde se construye el dict `context` con:

```python
{
    "asset": ...,
    "payout": ...,
    "regime": ...,
    "volatility": ...,
    "atr_micro": ...,
    "fibo_zones": ...,
    "pivots": ...,
    "bollinger": ...,
    "trend": ...,
    "range": ...,
    "micro_range": ...,
    "timestamp": ...,
    "decision": {...}
}
```

### 7.1. En el archivo donde se construye este `context` (normalmente el Decision Engine):

* Importa la función:

```python
from dl_autolearn.context_capture import attach_candles_to_context
```

* Una vez que tengas armado el dict `context`, justo **antes de retornarlo** o de loguear el evento `OPEN`, añade algo como:

```python
# Ejemplo genérico, ajusta nombres de variables según tu clase/métodos
timeframe_sec = 60  # o el timeframe real de tu bot (M1 = 60, M5 = 300, etc.)

context = attach_candles_to_context(
    api=self.api,            # instancia IQ_Option que ya usas
    context=context,
    asset=asset,             # mismo asset del trade
    timeframe_sec=timeframe_sec,
    candle_count=120,        # o el número de velas que quieras guardar
)
```

> ⚠️ Deja que CodeX adapte `self.api`, `asset` y `timeframe_sec` a tu estructura real (clase/función).
> Lo importante es que **antes de loguear el OPEN, context ya incluya `candles`**.

Una vez hecho esto, los nuevos JSONL contendrán:

```json
"context": {
  "asset": "...",
  "payout": 0.85,
  "regime": "range",
  "volatility": ...,
  "...": "...",
  "candles_timeframe_sec": 60,
  "candles_count": 120,
  "candles": [
    {"timestamp": ..., "open": ..., "high": ..., "low": ..., "close": ..., "volume": ...},
    ...
  ]
}
```

---

## 8. (Opcional pero recomendado) Integrar el `autolearn_gate` en el Decision Engine

En el mismo módulo donde decides abrir la operación (cuando ya tienes el `context` y el `score`):

1. Importa el gate:

```python
from dl_autolearn.inference import autolearn_gate
```

2. En la parte donde estás a punto de abrir el trade (cuando ya decidiste `direction`, `score`, etc.), añade:

```python
# context es el mismo dict que luego se loguea en JSONL
prob_win, allow = autolearn_gate(
    context,
    model_path="dl_autolearn/autolearn_model.joblib",
    min_prob=0.55,  # ajustable según tu tolerancia al riesgo
)

# Guardar info en el contexto para análisis posterior
if prob_win is not None:
    context.setdefault("autolearn", {})["prob_win"] = prob_win
    context["autolearn"]["min_prob"] = 0.55
    context["autolearn"]["allowed"] = bool(allow)

# Si AutoLearning dice que NO:
if not allow:
    # Puedes loguear un "veto" y no abrir operación
    # o simplemente bajar el score para que no pase tu threshold normal.
    return None  # o lo que en tu código signifique "no operar"
```

> De nuevo, deja que CodeX adapte esto al método exacto donde se decide abrir operaciones (`should_open_trade`, `evaluate_signal`, etc.).
> Lo clave es: **el gate ve el mismo `context` que se loguea, construye las mismas features, aplica el modelo y veta o no el trade.**

---

## 9. Flujo de trabajo recomendado

1. **Actualizar el bot con este patch** (CodeX).

2. Ejecutar el bot un tiempo hasta que los nuevos JSONL tengan `context.candles`.

3. Construir dataset:

   ```bash
   python -m dl_autolearn.dataset_builder
   ```

4. Entrenar modelo:

   ```bash
   python -m dl_autolearn.train
   ```

5. Activar el `autolearn_gate` en el Decision Engine (como en el punto 8).

6. Ajustar `min_prob` según veas en los resultados.

---

Con esto tienes:

* ✅ Logs ricos: features + 100+ velas por trade.
* ✅ Pipeline completo de AutoLearning (dataset → modelo → gate).
* ✅ Integración suave con tu lógica actual de trading sin romper nada.

```markdown
```
