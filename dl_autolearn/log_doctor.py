from pathlib import Path
import json
from typing import Dict, Any, List
from dataclasses import dataclass

# Directorio base de logs
LOG_DIR = Path("logs")


@dataclass
class RepairStats:
    files_seen: int = 0
    trades_seen: int = 0
    trades_with_open: int = 0
    trades_with_close: int = 0
    repaired_trades: int = 0


def load_events(path: Path) -> List[Dict[str, Any]]:
    """Carga todos los eventos JSONL de un archivo."""
    events: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                # No revienta: solo avisa y sigue
                print(f"[WARN] Línea inválida en {path}: {line[:120]}")
    return events


def build_index(events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Indexa eventos por trade_id.

    Para cada trade_id guardamos:
      - 'open': último evento OPEN visto
      - 'close': primer/último CLOSE visto (no importa, solo checamos existencia)
    """
    index: Dict[str, Dict[str, Any]] = {}
    for ev in events:
        tid = ev.get("trade_id")
        if not tid:
            continue

        bucket = index.setdefault(tid, {"open": None, "close": None})
        status = ev.get("status")

        if status == "OPEN":
            # Nos quedamos con el último OPEN (por si hubiera reintentos)
            bucket["open"] = ev
        elif status == "CLOSE":
            bucket["close"] = ev

    return index


def synth_close(open_ev: Dict[str, Any]) -> Dict[str, Any] | None:
    """
    Crea un CLOSE sintético a partir del OPEN y su contexto.

    Lógica:
      - Usa el último candle de context.candles como close_price.
      - Compara close_price vs entry_price según direction (call/put).
      - Calcula outcome_real y profit_real.
      - Estima close_time = open_time + candles_timeframe_sec (default 60).
    """
    ctx = open_ev.get("context") or open_ev.get("decision_context") or {}
    candles = ctx.get("candles") or []
    if not candles:
        # Sin velas, no podemos reparar bien este trade
        return None

    last_candle = candles[-1]
    last_price = float(last_candle.get("close", open_ev.get("entry_price", 0.0)))
    entry_price = float(open_ev.get("entry_price", last_price))

    # Dirección del trade
    direction = open_ev.get("direction")
    if not direction:
        decision = open_ev.get("decision") or {}
        direction = decision.get("direction")

    stake = float(open_ev.get("stake") or 1.0)
    payout = float(open_ev.get("payout") or 0.8)

    # Determinar outcome
    if abs(last_price - entry_price) < 1e-9:
        outcome = "DRAW"
        profit_real = 0.0
    else:
        if direction == "call":
            win = last_price > entry_price
        elif direction == "put":
            win = last_price < entry_price
        else:
            # Si por alguna razón no tenemos dirección, asumimos pérdida
            win = False

        if win:
            outcome = "WIN"
            profit_real = round(stake * payout, 2)
        else:
            outcome = "LOSS"
            profit_real = round(-stake, 2)

    # Estimar tiempos
    open_time = float(
        open_ev.get("open_time")
        or open_ev.get("timestamp")
        or last_candle.get("timestamp", 0.0)
    )
    tf = ctx.get("candles_timeframe_sec") or 60
    close_time = open_time + float(tf)

    close_event: Dict[str, Any] = {
        "timestamp": close_time,
        "status": "CLOSE",
        "trade_id": open_ev.get("trade_id"),
        "asset": open_ev.get("asset"),
        "direction": direction,
        "regime": open_ev.get("regime"),
        "reason": open_ev.get("reason"),
        "pattern": open_ev.get("pattern"),
        "score": open_ev.get("score"),
        "stake": stake,
        "payout": payout,
        "entry_price": entry_price,
        "close_price": last_price,
        "context": open_ev.get("context"),
        "decision": open_ev.get("decision"),
        "autolearn": open_ev.get("autolearn"),
        "outcome_real": outcome,
        "profit_real": profit_real,
        "open_time": open_time,
        "close_time": close_time,
        "duration_sec": close_time - open_time,
        # Marca para saber que este CLOSE es sintético
        "repaired": True,
    }
    return close_event


def repair_file(path: Path, stats: RepairStats, dry_run: bool = False) -> None:
    """Repara un archivo JSONL concreto."""
    print(f"=== Reparando archivo: {path.name} ===")
    events = load_events(path)
    index = build_index(events)

    stats.files_seen += 1
    stats.trades_seen += len(index)

    repaired_any = False
    new_events = list(events)

    for tid, bucket in index.items():
        open_ev = bucket.get("open")
        close_ev = bucket.get("close")

        if open_ev:
            stats.trades_with_open += 1
        if close_ev:
            stats.trades_with_close += 1

        # Solo nos interesan trades con OPEN y sin CLOSE
        if not open_ev or close_ev:
            continue

        # Si el propio OPEN ya tiene outcome_real/profit_real, asumimos que alguien lo parchó manualmente
        if open_ev.get("outcome_real") or open_ev.get("profit_real"):
            continue

        close_event = synth_close(open_ev)
        if not close_event:
            continue

        stats.repaired_trades += 1
        repaired_any = True
        new_events.append(close_event)

    if not repaired_any:
        print("  → Nada que reparar en este archivo.")
        return

    # Ordenamos por timestamp antes de guardar
    new_events.sort(key=lambda e: e.get("timestamp") or e.get("open_time") or 0.0)

    if dry_run:
        print(f"  → DRY RUN: se repararían {stats.repaired_trades} trades (acumulado). NO se escribió archivo.")
        return

    # Backup del archivo original
    backup_path = path.with_suffix(path.suffix + ".bak")
    path.rename(backup_path)

    # Escribimos el archivo reparado con el mismo nombre original
    with path.open("w", encoding="utf-8") as f:
        for ev in new_events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    print(f"  → Reparados {stats.repaired_trades} trades (acumulado).")
    print(f"    Archivo sobrescrito. Backup en: {backup_path.name}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Repara trades OPEN sin CLOSE en logs JSONL para AutoLearning."
    )
    parser.add_argument(
        "--logs-dir",
        type=str,
        default="logs",
        help="Directorio de logs (default: logs)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo mostrar qué se repararía, sin escribir archivos.",
    )
    args = parser.parse_args()

    global LOG_DIR
    LOG_DIR = Path(args.logs_dir)

    stats = RepairStats()

    jsonl_files = sorted(LOG_DIR.glob("trades_*.jsonl"))
    if not jsonl_files:
        print(f"No se encontraron archivos trades_*.jsonl en {LOG_DIR}")
        return

    for path in jsonl_files:
        repair_file(path, stats, dry_run=args.dry_run)

    print("\n=== RESUMEN GLOBAL ===")
    print(f"Archivos procesados:           {stats.files_seen}")
    print(f"Trades diferentes vistos:      {stats.trades_seen}")
    print(f"Trades con OPEN:               {stats.trades_with_open}")
    print(f"Trades con CLOSE (original):   {stats.trades_with_close}")
    print(f"Trades reparados (CLOSE fake): {stats.repaired_trades}")


if __name__ == "__main__":
    main()
