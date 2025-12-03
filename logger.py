"""Logging utilities for TradingLions_Reforged."""
from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

from config import BotConfig

CSV_HEADER = [
    "timestamp",
    "trade_id",
    "status",
    "asset",
    "direction",
    "regime",
    "reason",
    "pattern",
    "score",
    "stake",
    "payout",
    "entry_price",
    "context",
    "decision_context",
    "logic",
    "logic_flat",
    "metadata",
    "outcome_real",
    "profit_real",
    "close_price",
    "open_time",
    "close_time",
    "duration_sec",
]

LEGACY_HEADER_V1 = [
    "timestamp",
    "status",
    "trade_id",
    "asset",
    "direction",
    "regime",
    "reason",
    "pattern",
    "score",
    "stake",
    "payout",
    "entry_price",
    "context",
    "decision_context",
    "logic",
    "metadata",
    "outcome_real",
    "profit_real",
    "close_price",
    "open_time",
    "close_time",
]


def ensure_csv_header(csv_path: str) -> None:
    """Garantiza que el CSV tenga el encabezado canonical, reescribiendo si es necesario."""
    path = Path(csv_path)
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(CSV_HEADER)
        return

    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            rows = list(reader)
    except Exception:
        return
    if not rows:
        with path.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(CSV_HEADER)
        return

    header = rows[0]
    if header == CSV_HEADER:
        return

    data_rows: Iterable[Iterable[str]] = rows[1:]
    dict_rows = []
    for raw in data_rows:
        entry = dict(zip(header, raw))
        if header == LEGACY_HEADER_V1:
            entry = _upgrade_legacy_v1(entry)
        dict_rows.append(entry)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADER)
        for row in dict_rows:
            writer.writerow([row.get(key, "") for key in CSV_HEADER])


def _upgrade_legacy_v1(entry: Dict[str, Any]) -> Dict[str, Any]:
    upgraded = dict(entry)
    status = str(entry.get("status", ""))
    trade_id = str(entry.get("trade_id", ""))
    if trade_id.upper() in {"OPEN", "CLOSE"} and status.upper() not in {"OPEN", "CLOSE"}:
        upgraded["trade_id"] = status
        upgraded["status"] = trade_id
    else:
        upgraded["trade_id"] = trade_id
        upgraded["status"] = status
    upgraded.setdefault("decision_context", entry.get("context"))
    upgraded.setdefault("logic", entry.get("logic"))
    upgraded.setdefault("logic_flat", "")
    upgraded.setdefault("metadata", entry.get("metadata", {}))
    upgraded.setdefault("outcome_real", entry.get("outcome_real", ""))
    upgraded.setdefault("profit_real", entry.get("profit_real", ""))
    upgraded.setdefault("close_price", entry.get("close_price", ""))
    upgraded.setdefault("open_time", entry.get("open_time", ""))
    upgraded.setdefault("close_time", entry.get("close_time", ""))
    upgraded.setdefault("duration_sec", "")
    return upgraded


class TradeLogger:
    """Handles CSV/JSON logging for trade lifecycle events."""

    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.log_dir = self.config.log_directory
        os.makedirs(self.log_dir, exist_ok=True)

        date = time.strftime("%Y-%m-%d")
        self.csv_path = os.path.join(self.log_dir, f"trades_{date}.csv")
        self.jsonl_path = os.path.join(self.log_dir, f"trades_{date}.jsonl")

        ensure_csv_header(self.csv_path)

    def log_trade_open(self, order: Dict[str, Any]) -> None:
        try:
            payload: Dict[str, Any] = {
                "timestamp": time.time(),
                "trade_id": order.get("trade_id"),
                "status": "OPEN",
                "asset": order.get("asset", ""),
                "direction": order.get("direction", ""),
                "regime": order.get("regime", ""),
                "reason": order.get("reason", ""),
                "pattern": order.get("pattern", ""),
                "score": float(order.get("score", 0.0)),
                "stake": float(order.get("stake", 0.0)),
                "payout": float(order.get("payout", 0.0)),
                "entry_price": float(order.get("entry_price", 0.0)),
                "context": order.get("context"),
                "decision_context": order.get("context"),
                "logic": order.get("logic"),
                "logic_flat": "",
                "metadata": {},
                "outcome_real": "",
                "profit_real": "",
                "close_price": "",
                "open_time": order.get("opened_at"),
                "close_time": "",
                "duration_sec": "",
            }

            with open(self.jsonl_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

            self._write_csv_row(payload)
        except Exception as exc:
            print(f"[LOGGER ERROR] No se pudo registrar OPEN: {exc}")

    def log_final_result(self, payload: Mapping[str, Any]) -> None:
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
            "logic_flat": payload.get("logic_flat"),
            "metadata": payload.get("metadata"),
            "outcome_real": payload.get("outcome_real"),
            "profit_real": payload.get("profit_real"),
            "close_price": payload.get("close_price"),
            "open_time": payload.get("open_time"),
            "close_time": payload.get("close_time", ts),
            "duration_sec": payload.get("duration_sec"),
        }

        with open(self.jsonl_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

        self._write_csv_row(record)

    def _write_csv_row(self, payload: Mapping[str, Any]) -> None:
        row = []
        for key in CSV_HEADER:
            value = payload.get(key, "")
            if key in {"context", "decision_context", "logic", "metadata"}:
                if value not in (None, ""):
                    value = json.dumps(value, ensure_ascii=False)
                else:
                    value = ""
            row.append(value)
        with open(self.csv_path, "a", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(row)


class DecisionLogger:
    """Optional logger for debugging decision engine."""

    def __init__(self, log_path: str = "decisions.jsonl") -> None:
        self.log_path = log_path

    def log_decision(self, decision: Dict[str, Any]) -> None:
        with open(self.log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(decision, ensure_ascii=False) + "\n")


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


__all__ = ["TradeLogger", "DecisionLogger", "StandaloneResultLogger", "CSV_HEADER", "ensure_csv_header"]
