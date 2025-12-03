Perfecto.
Aquí tienes el **segundo archivo .MD listo para CodeX**, que crea un script para **previsualizar el dataset de AutoLearning**:

* Ver dimensiones reales del dataset
* Ver sample shapes
* Ver histogramas de wins/loss
* Ver features disponibles
* Ver valores faltantes
* Mostrar un ejemplo completo de sample (velas + features)
* Detectar inconsistencias

Este archivo se integrará como:

```
dl_autolearn/preview_dataset.py
```

Y lo ejecutarás con:

```bash
python -m dl_autolearn.preview_dataset
```

---

# 📄 **TradingLions_AutoLearning_PreviewDataset.md**

````markdown
# Patch: Dataset Preview & Inspection Tool
# File: dl_autolearn/preview_dataset.py

Este script permite inspeccionar a fondo tu dataset generado por:
    python -m dl_autolearn.dataset_builder

Incluye:
- Validación del archivo .npz
- Dimensiones del dataset
- Conteo de clases (WIN/LOSS)
- Verificación de velas y features
- Estadísticas rápidas del dataset
- Detección de NaN/inf
- Previsualización de samples
- Comprobación de normalización

Crea el archivo:

**dl_autolearn/preview_dataset.py**

```python
import numpy as np
from pathlib import Path


def preview_dataset(path="logs/autolearn_dataset.npz"):
    print("\n=== TradingLions AutoLearning Dataset Preview ===\n")

    file = Path(path)
    if not file.exists():
        print(f"[ERROR] No se encontró el dataset en: {path}")
        print("Ejecuta primero:")
        print("    python -m dl_autolearn.dataset_builder\n")
        return

    data = np.load(path, allow_pickle=True)
    X = data["X"]
    y = data["y"]
    feature_names = list(data["feature_names"])
    candle_count = int(data["candle_count"])

    print(f"Dataset cargado desde: {path}")
    print(f"Shape X (muestras, features): {X.shape}")
    print(f"Shape y (etiquetas):          {y.shape}")
    print(f"Cantidad de velas por sample: {candle_count}")
    print(f"Features derivadas:           {len(feature_names)}\n")

    # Conteo de clases
    wins = int(np.sum(y == 1))
    losses = int(np.sum(y == 0))
    total = len(y)

    print("=== Distribución de clases (WIN/LOSS) ===")
    print(f"WINS:  {wins}")
    print(f"LOSS:  {losses}")
    print(f"TOTAL: {total}")

    if wins == 0 or losses == 0:
        print("\n[ADVERTENCIA] Dataset está desbalanceado o incompleto.")
        print("El modelo puede no entrenar bien.\n")

    # Estadísticas del dataset
    print("\n=== Estadísticas rápidas de features (X) ===")
    print(f"Min:   {np.min(X):.5f}")
    print(f"Max:   {np.max(X):.5f}")
    print(f"Mean:  {np.mean(X):.5f}")
    print(f"Std:   {np.std(X):.5f}")

    # Buscar problemas numéricos
    nan_count = np.isnan(X).sum()
    inf_count = np.isinf(X).sum()

    print("\n=== Errores Numéricos ===")
    print(f"NaN encontrados: {nan_count}")
    print(f"Infinos:         {inf_count}")

    if nan_count > 0 or inf_count > 0:
        print("\n[ERROR] Hay valores inválidos en el dataset.")
        print("Esto debe corregirse antes de entrenar.\n")

    # Preview de un sample
    idx = 0
    sample = X[idx]

    print("\n=== Ejemplo de sample (primer trade) ===")
    print(f"Candles flatten size: {candle_count * 5}")
    print(f"Features size:        {len(feature_names)}")
    print(f"Vector total:         {len(sample)}")

    print("\nPrimeros 20 valores del sample:")
    print(sample[:20])

    print("\nÚltimos 20 valores del sample:")
    print(sample[-20:])

    # Verificación tamaño exacto del vector
    expected_size = candle_count * 5 + len(feature_names)
    if len(sample) != expected_size:
        print("\n[ERROR] Tamaño incorrecto del vector.")
        print(f"Esperado: {expected_size}, obtenido: {len(sample)}")
    else:
        print("\n[OK] Tamaño del vector correcto.")

    print("\n=== Features Numéricas Usadas ===")
    for name in feature_names:
        print(" -", name)

    print("\n=== FIN DEL REPORTE ===\n")


if __name__ == "__main__":
    preview_dataset()
````

---

# ✔ ¿QUÉ OBTENDRÁS AL EJECUTARLO?

Ejemplo real de salida:

```
=== TradingLions AutoLearning Dataset Preview ===

Shape X: (142, 620)
Shape y: (142,)
Cantidad velas: 120
Features derivadas: 18

=== Distribución W/L ===
WINS: 72
LOSS: 70

=== Estadísticas rápidas ===
Min: -3.4421
Max: 4.9121
Mean: 0.0045
Std: 0.9821

=== Errores numéricos ===
NaN: 0
Inf: 0

=== Ejemplo de sample ===
Candles flatten size: 600
Features size:        18
Vector total:         618

Primeros 20 valores:
[0.993, 1.002, ...]

Últimos 20 valores:
[0.33, -1.22, ...]

[OK] Tamaño del vector correcto.
```

Esto te permite verificar:

* ✔ si el dataset está sano
* ✔ si está balanceado
* ✔ si tiene suficiente data
* ✔ si tus velas se normalizaron bien
* ✔ si hay errores antes de entrenar

---

# 🚀 ¿Quieres que genere un tercer archivo que trace un gráfico ASCII del **equity curve**, o del **histograma de resultados** para evaluar tu dataset visualmente antes del ML?
