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

        # sistemas OPEN/CLOSE tradicionales
        if status == "open":
            open_map[trade_id] = evt

        elif status == "close":
            close_map[trade_id] = evt

        else:
            # Caso: LOG condensado (OPEN + CLOSE en una sola línea)
            outcome = evt.get("outcome_real", "")
            if outcome in ("WIN","LOSS","win","loss"):
                close_map[trade_id] = evt
                if "candles" in evt.get("context", {}):
                    open_map[trade_id] = evt

    total_events = len(events)
    total_open = len(open_map)
    total_close = len(close_map)

    valid_pairs = []
    missing_close = 0
    missing_open = 0

    for tid in set(list(open_map.keys()) + list(close_map.keys())):
        if tid in open_map and tid in close_map:
            valid_pairs.append(tid)
        elif tid in open_map:
            missing_close += 1
        elif tid in close_map:
            missing_open += 1

    dataset_valid = []
    for tid in valid_pairs:
        evt_open = open_map[tid]
        ctx = evt_open.get("context") or {}
        candles = ctx.get("candles")

        if not candles or len(candles) < 50:
            continue

        evt_close = close_map[tid]
        outcome = str(evt_close.get("outcome_real", evt_close.get("result",""))).lower()

        if outcome not in ("win","loss"):
            continue

        dataset_valid.append(tid)

    wins = 0
    losses = 0
    for tid in dataset_valid:
        evt_close = close_map[tid]
        outcome = str(evt_close.get("outcome_real", evt_close.get("result",""))).lower()
        if outcome == "win":
            wins += 1
        elif outcome == "loss":
            losses += 1

    return {
        "total_events": total_events,
        "total_open": total_open,
        "total_close": total_close,
        "valid_pairs": len(valid_pairs),
        "missing_open": missing_open,
        "missing_close": missing_close,
        "dataset_valid": len(dataset_valid),
        "wins": wins,
        "losses": losses,
        "draws": len(dataset_valid) - wins - losses,
    }


def main():
    print("\n=== TradingLions AutoLearning Diagnostic ===\n")

    events = load_all_events()
    stats = count_trades(events)

    print(f"Eventos totales leídos: {stats['total_events']}")
    print(f"OPEN encontrados:       {stats['total_open']}")
    print(f"CLOSE encontrados:      {stats['total_close']}")

    print(f"\nTrades emparejados: {stats['valid_pairs']}")
    print(f"OPEN sin CLOSE:    {stats['missing_close']}")
    print(f"CLOSE sin OPEN:    {stats['missing_open']}")

    print("\n=== Dataset ===")
    print(f"Trades válidos: {stats['dataset_valid']}")
    print(f"WINS:           {stats['wins']}")
    print(f"LOSS:           {stats['losses']}")
    print(f"DRAW:           {stats['draws']}")
    print("\n============================================\n")


if __name__ == "__main__":
    main()
