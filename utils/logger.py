from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any, Mapping

from logger import CSV_HEADER, ensure_csv_header


class StandaloneResultLogger:
    """Lightweight logger to persist CLOSE events for AutoLearning."""

    def __init__(self, log_dir: str | Path) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _paths_for_timestamp(self, ts: float) -> tuple[Path, Path]:
        date_label = time.strftime("%Y-%m-%d", time.localtime(ts))
        csv_path = self.log_dir / f"trades_{date_label}.csv"
        jsonl_path = self.log_dir / f"trades_{date_label}.jsonl"
        return csv_path, jsonl_path

    def _write_jsonl(self, path: Path, payload: Mapping[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _write_csv(self, path: Path, payload: Mapping[str, Any]) -> None:
        row: list[Any] = []
        for key in CSV_HEADER:
            value = payload.get(key, "")
            if key in {"context", "decision_context", "logic", "metadata"}:
                if value not in (None, ""):
                    value = json.dumps(value, ensure_ascii=False)
                else:
                    value = ""
            row.append(value)
        with path.open("a", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(row)

    def log_close(self, payload: Mapping[str, Any]) -> None:
        record = dict(payload)
        ts = float(record.get("timestamp", time.time()))
        record["timestamp"] = ts
        record["status"] = "CLOSE"
        csv_path, jsonl_path = self._paths_for_timestamp(ts)
        ensure_csv_header(str(csv_path))
        self._write_jsonl(jsonl_path, record)
        self._write_csv(csv_path, record)

    def log_final_result(self, payload: Mapping[str, Any]) -> None:
        """Backward compatible alias for legacy callers."""
        self.log_close(payload)


__all__ = ["StandaloneResultLogger"]
