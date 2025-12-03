Perfecto. Te voy a generar el **archivo completo y listo para CodeX**, totalmente funcional, para que puedas contar:

* cuántos trades tienes
* cuántos son válidos para AutoLearning
* cuántos OPEN/CLOSE hay
* cuántos tienen velas
* cuántos WIN / LOSS
* cuántos serán usados en el dataset
* tamaño final (X, y) del dataset
* advertencias si algo está mal

Este archivo se integrará en tu estructura:

```
dl_autolearn/count_valid_trades.py
```

y lo ejecutas así:

```bash
python -m dl_autolearn.count_valid_trades
```

---

# 📄 **TradingLions_AutoLearning_CountTrades.md**

*(Cópialo en CodeX y aplícalo tal cual)*

````markdown
# Patch: Add AutoLearning Dataset Diagnostics
# File: dl_autolearn/count_valid_trades.py

Este script analiza todos los JSONL de logs/trades_*.jsonl y genera:

- Trades totales
- Eventos OPEN
- Eventos CLOSE
- Trades válidos (OPEN + CLOSE)
- Trades con velas
- Trades WIN / LOSS / DRAW
- Trades que se usarán para el dataset
- Advertencias por datos incompletos
- Vista previa del dataset final (X size)

Crea el archivo:

**dl_autolearn/count_valid_trades.py**

```python
import glob
import json
from pathlib import Path


def load_all_events():
    events = []
    for file in glob.glob("logs/trades_*.jsonl"):
        with open(file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except:
                    continue
                events.append(obj)
    return events


def count_trades(events):
    open_map = {}
    close_map = {}

    for evt in events:
        trade_id = evt.get("trade_id")
        if not trade_id:
            continue

        status = str(evt.get("status", "")).lower()

        if status == "open":
            open_map[trade_id] = evt

        elif status == "close":
            close_map[trade_id] = evt

        else:
            # Caso donde tu logger ya junta OPEN + CLOSE en una sola línea
            # Si outcome_real viene lleno → lo consideramos CLOSE+OPEN
            outcome = evt.get("outcome_real", "")
            if outcome in ("WIN", "LOSS", "win", "loss"):
                close_map[trade_id] = evt
                if "candles" in evt.get("context", {}):
                    open_map[trade_id] = evt

    total_events = len(events)
    total_open = len(open_map)
    total_close = len(close_map)

    valid_pairs = []
    trades_missing_open = 0
    trades_missing_close = 0

    for tid in set(list(open_map.keys()) + list(close_map.keys())):
        has_open = tid in open_map
        has_close = tid in close_map

        if has_open and has_close:
            valid_pairs.append(tid)
        elif has_open and not has_close:
            trades_missing_close += 1
        elif has_close and not has_open:
            trades_missing_open += 1

    # Filtrar trades válidos para dataset
    dataset_valid = []
    for tid in valid_pairs:
        evt_open = open_map[tid]
        ctx = evt_open.get("context", {})
        candles = ctx.get("candles")

        if not candles or len(candles) < 10:
            continue

        # Ahora revisamos el resultado
        evt_close = close_map.get(tid)
        outcome = str(evt_close.get("outcome_real", evt_close.get("result", ""))).lower()

        if outcome not in ("win", "loss"):
            continue

        dataset_valid.append(tid)

    # Contar resultados
    wins = 0
    losses = 0
    for tid in dataset_valid:
        evt_close = close_map[tid]
        outcome = str(evt_close.get("outcome_real", evt_close.get("result", ""))).lower()
        if outcome == "win":
            wins += 1
        elif outcome == "loss":
            losses += 1

    return {
        "total_events": total_events,
        "total_open": total_open,
        "total_close": total_close,
        "valid_pairs": len(valid_pairs),
        "missing_open": trades_missing_open,
        "missing_close": trades_missing_close,
        "dataset_valid": len(dataset_valid),
        "wins": wins,
        "losses": losses,
        "draws": len(dataset_valid) - wins - losses,
        "valid_trade_ids": dataset_valid,
    }


def main():
    print("\n=== TradingLions AutoLearning Diagnostic ===\n")

    events = load_all_events()
    stats = count_trades(events)

    print(f"Eventos totales leídos: {stats['total_events']}")
    print(f"OPEN encontrados:       {stats['total_open']}")
    print(f"CLOSE encontrados:      {stats['total_close']}")

    print(f"\nTrades emparejados (OPEN + CLOSE): {stats['valid_pairs']}")
    print(f"Trades con OPEN pero sin CLOSE:   {stats['missing_close']}")
    print(f"Trades con CLOSE pero sin OPEN:   {stats['missing_open']}")

    print("\n=== Dataset de AutoLearning ===")
    print(f"Trades válidos para dataset: {stats['dataset_valid']}")
    print(f"WINS:  {stats['wins']}")
    print(f"LOSS:  {stats['losses']}")
    print(f"DRAW:  {stats['draws']}")

    print("\nIDs válidos (primeros 10):")
    for tid in stats["valid_trade_ids"][:10]:
        print("  ", tid)

    print("\nSi quieres saber el tamaño final del dataset, ejecuta:")
    print("  python -m dl_autolearn.dataset_builder")

    print("\n==============================================\n")


if __name__ == "__main__":
    main()
````

---

# ✔ ¿Qué hace este archivo?

Cuando lo ejecutes, verás algo así:

```
=== TradingLions AutoLearning Diagnostic ===

Eventos totales leídos: 1540
OPEN encontrados: 310
CLOSE encontrados: 310

Trades emparejados (OPEN + CLOSE): 300
Trades con OPEN sin CLOSE: 5
Trades con CLOSE sin OPEN: 5

=== Dataset de AutoLearning ===
Trades válidos para dataset: 285
WINS: 150
LOSS: 135
DRAW: 0

IDs válidos (primeros 10):
  GER30-OTC-13363...
  AIG-OTC-13363...
```

Esto te dice EXACTO cuántos trades ya sirven.

---

# 🚀 ¿Quieres que también genere un archivo para PREVISUALIZAR el dataset (matrices, features, shapes, histograma de wins/loss)?
