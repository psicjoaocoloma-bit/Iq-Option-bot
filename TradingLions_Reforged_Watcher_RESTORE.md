✅ 1. CREAR StandaloneResultLogger EN logger.py
Acción:

En logger.py, al final del archivo, después de DecisionLogger, AGREGAR la siguiente clase completa:

class StandaloneResultLogger:
    """
    Logger para el watcher de resultados.
    Escribe SOLO eventos CLOSE en el mismo CSV/JSONL que TradeLogger,
    usando el encabezado CSV_HEADER.
    """

    def __init__(self, log_dir: str = "logs") -> None:
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)

        date = time.strftime("%Y-%m-%d")
        self.csv_path = os.path.join(self.log_dir, f"trades_{date}.csv")
        self.jsonl_path = os.path.join(self.log_dir, f"trades_{date}.jsonl")

        ensure_csv_header(self.csv_path)

    def log_close(self, payload: Mapping[str, Any]) -> None:
        """
        Recibe el payload final que arma ResultWatcher._resolve_and_log
        y lo persiste en CSV + JSONL.
        """
        try:
            try:
                ts = float(payload.get("timestamp", time.time()))
            except (TypeError, ValueError):
                ts = time.time()

            record: Dict[str, Any] = {
                "timestamp": ts,
                "status": payload.get("status", "CLOSE"),
                "trade_id": payload.get("trade_id"),
                "asset": payload.get("asset"),
                "direction": payload.get("direction"),
                "regime": payload.get("regime"),
                "reason": payload.get("reason"),
                "pattern": payload.get("pattern"),
                "score": payload.get("score"),
                "stake": payload.get("stake"),
                "payout": payload.get("payout"),
                "entry_price": payload.get("entry_price"),
                "context": payload.get("context"),
                "decision_context": payload.get("decision_context"),
                "logic": payload.get("logic"),
                "logic_flat": payload.get("logic_flat", ""),
                "metadata": payload.get("metadata", {}),
                "outcome_real": payload.get("outcome_real"),
                "profit_real": payload.get("profit_real"),
                "close_price": payload.get("close_price"),
                "open_time": payload.get("open_time"),
                "close_time": payload.get("close_time", ts),
                "duration_sec": payload.get("duration_sec"),
            }

            with open(self.jsonl_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

            row = []
            for key in CSV_HEADER:
                value = record.get(key, "")
                if key in {"context", "decision_context", "logic", "metadata"}:
                    if value not in (None, ""):
                        value = json.dumps(value, ensure_ascii=False)
                    else:
                        value = ""
                row.append(value)

            with open(self.csv_path, "a", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerow(row)

        except Exception as exc:
            print(f"[RESULT LOGGER ERROR] No se pudo registrar CLOSE: {exc}")

✅ 2. CORREGIR IMPORTS EN result_watcher.py
Acción:

Cambiar esta línea:

from utils.logger import StandaloneResultLogger


por esta:

from logger import StandaloneResultLogger

✅ 3. HACER QUE bot.py REGISTRE LAS OPERACIONES ABIERTAS (OPEN)
Acción:

En bot.py, dentro del método _enter_trade, justo después de confirmar que la orden se abrió correctamente, AGREGAR este bloque:

📍 Insertar después de:
if order is None:
    self._debug("⚠️ IQ Option rechazó la orden → Liberando pending_entry")
    self.pending_entry = None
    return

📌 AGREGAR ESTE BLOQUE COMPLETO:
        # --- REGISTRO PARA EL WATCHER (OPEN) ---
        if self.watcher is not None:
            try:
                open_time = float(order.get("opened_at", tick_time))
                duration_min = float(order.get("duration", 1))
            except (TypeError, ValueError):
                open_time = tick_time
                duration_min = 1.0

            open_payload = {
                "trade_id": order.get("trade_id"),
                "asset": asset,
                "direction": order.get("direction"),
                "stake": float(order.get("stake", stake)),
                "payout": float(order.get("payout", self.pending_entry.payout)),
                "entry_price": float(order.get("entry_price", open_price)),
                "regime": self.pending_entry.decision.regime,
                "reason": self.pending_entry.decision.reason,
                "pattern": self.pending_entry.decision.pattern,
                "score": float(self.pending_entry.decision.score),
                "open_time": open_time,
                "duration": duration_min,
                "context": {
                    "decision": getattr(self.pending_entry.decision, "__dict__", None)
                    or self.pending_entry.decision_context
                    or {},
                    "decision_context": self.pending_entry.decision_context,
                },
                "decision_context": self.pending_entry.decision_context,
                "logic": getattr(self.pending_entry.decision, "logic", None),
                "logic_flat": "",
                "metadata": {},
            }

            self.watcher.register_open_trade(open_payload)

✅ 4. UNIFICAR DIRECTORIOS PARA LOGS
Acción:

Si en config.json usas:

{
  "log_dir": "logs_trading"
}


entonces en watcher.py reemplazar:

LOG_DIR = Path("logs")


por:

LOG_DIR = Path("logs_trading")


(usar el mismo que config.log_directory).

✅ 5. Resultado esperado

Después de esta restauración:

✔️ Los OPEN se registran correctamente en ResultWatcher.pending.
✔️ El watcher resuelve CLOSE vía WebSocket y fallback.
✔️ Cada trade genera:

Línea OPEN en CSV/JSONL (TradeLogger)

Línea CLOSE en CSV/JSONL (StandaloneResultLogger)

✔️ watcher.py vuelve a mostrar:

winrate

profit

últimas 10 operaciones

gráficas de progreso

✔️ Autolearning vuelve a tener datos completos.