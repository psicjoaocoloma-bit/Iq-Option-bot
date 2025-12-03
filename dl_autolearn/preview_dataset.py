import numpy as np
from pathlib import Path


def preview_dataset(path="logs/autolearn_dataset.npz"):
    print("\n=== TradingLions AutoLearning Dataset Preview ===\n")

    file = Path(path)
    if not file.exists():
        print(f"[ERROR] No se encontro el dataset en: {path}")
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

    wins = int(np.sum(y == 1))
    losses = int(np.sum(y == 0))
    total = len(y)

    print("=== Distribucion de clases (WIN/LOSS) ===")
    print(f"WINS:  {wins}")
    print(f"LOSS:  {losses}")
    print(f"TOTAL: {total}")

    if wins == 0 or losses == 0:
        print("\n[ADVERTENCIA] Dataset esta desbalanceado o incompleto.")
        print("El modelo puede no entrenar bien.\n")

    print("\n=== Estadisticas rapidas de features (X) ===")
    print(f"Min:   {np.min(X):.5f}")
    print(f"Max:   {np.max(X):.5f}")
    print(f"Mean:  {np.mean(X):.5f}")
    print(f"Std:   {np.std(X):.5f}")

    nan_count = np.isnan(X).sum()
    inf_count = np.isinf(X).sum()

    print("\n=== Errores Numericos ===")
    print(f"NaN encontrados: {nan_count}")
    print(f"Infinos:         {inf_count}")

    if nan_count > 0 or inf_count > 0:
        print("\n[ERROR] Hay valores invalidos en el dataset.")
        print("Esto debe corregirse antes de entrenar.\n")

    if len(X) == 0:
        print("\n[ERROR] El dataset no contiene muestras.")
        return

    sample = X[0]

    print("\n=== Ejemplo de sample (primer trade) ===")
    print(f"Candles flatten size: {candle_count * 5}")
    print(f"Features size:        {len(feature_names)}")
    print(f"Vector total:         {len(sample)}")

    print("\nPrimeros 20 valores del sample:")
    print(sample[:20])

    print("\nUltimos 20 valores del sample:")
    print(sample[-20:])

    expected_size = candle_count * 5 + len(feature_names)
    if len(sample) != expected_size:
        print("\n[ERROR] Tamano incorrecto del vector.")
        print(f"Esperado: {expected_size}, obtenido: {len(sample)}")
    else:
        print("\n[OK] Tamano del vector correcto.")

    print("\n=== Features Numericas Usadas ===")
    for name in feature_names:
        print(" -", name)

    print("\n=== FIN DEL REPORTE ===\n")


if __name__ == "__main__":
    preview_dataset()
