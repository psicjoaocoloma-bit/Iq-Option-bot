"""Result watcher with forced CLOSE logging for AutoLearning."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional, Sequence, Tuple

from logger import StandaloneResultLogger


class ResultWatcher:
    """Tracks open trades and enforces CLOSE events via polling fallback."""

    def __init__(self, api, logger: StandaloneResultLogger):
        self.api = api
        self.logger = logger
        self.pending: Dict[Any, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.running = True
        self.verbose = True
        self._fallback_event = threading.Event()
        self._fallback_thread = threading.Thread(
            target=self._fallback_loop, daemon=True
        )
        self._fallback_thread.start()

    def start(self) -> None:
        """Legacy compatibility hook (no-op)."""
        return

    def watcher_loop(self) -> None:
        """Legacy compatibility loop (kept for start.py threads)."""
        while self.running:
            time.sleep(1)

    def register_open_trade(self, open_payload: Dict[str, Any]) -> None:
        if not isinstance(open_payload, dict):
            return
        tid = open_payload.get("trade_id")
        if not tid:
            return
        open_time_exact = self._safe_float(open_payload.get("open_time"), time.time())
        open_ts = round(open_time_exact)
        expire_ts = self._compute_expire_ts(open_payload, open_time_exact)
        option_id = self._normalize_option_id(
            open_payload.get("broker_event", {}).get("option_id")
            or open_payload.get("option_id")
            or open_payload.get("order_id")
        )

        # NO sobrescribir si ya existe un option_id válido y el nuevo viene vacío
        if tid in self.pending:
            existing = self.pending[tid]
            if existing.get("option_id") and not option_id:
                self._log(f"[skip overwrite vacío] {tid}")
                return

        bucket = {
            "open": open_payload,
            "open_ts": open_ts,
            "expire_ts": expire_ts,
            "resolved": False,
            "option_id": option_id,
            "order_ref": open_payload.get("order_id_raw")
            or open_payload.get("order_id"),
        }
        with self.lock:
            self.pending[tid] = bucket
        self._fallback_event.set()
        self._log(
            f"registrado {tid} option_id={option_id} open={open_time_exact:.2f} expire={expire_ts:.2f}"
        )

    def handle_websocket_close(self, close_event: Dict[str, Any]) -> None:
        close_ts = close_event.get("close_time") or close_event.get("actual_expire")
        if not close_ts:
            return
        try:
            close_ts = round(float(close_ts))
        except (TypeError, ValueError):
            return

        with self.lock:
            for tid, bucket in list(self.pending.items()):
                if abs(bucket["open_ts"] - close_ts) <= 2:
                    self._resolve_and_log(bucket["open"], close_event)
                    bucket["resolved"] = True
                    del self.pending[tid]
                    break

    def _fallback_loop(self) -> None:
        while self.running:
            self._fallback_event.wait(timeout=3)
            self._fallback_event.clear()
            try:
                self._execute_fallback_pass()
            except Exception as exc:  # pragma: no cover - defensive logging
                self._log(f"[error] fallback_loop: {exc}")

    def _run_fallback_check(self, *, blocking: bool = False) -> None:
        if blocking:
            self._execute_fallback_pass()
        else:
            self._fallback_event.set()

    def _execute_fallback_pass(self) -> None:
        if not self.api:
            return
        with self.lock:
            snapshot = {
                tid: dict(bucket)
                for tid, bucket in self.pending.items()
                if not bucket.get("resolved")
            }
        if not snapshot:
            return
        now = time.time()
        closed_cache: Optional[Sequence[Dict[str, Any]]] = None
        for tid, bucket in snapshot.items():
            open_payload = bucket["open"]
            expire_ts = float(bucket.get("expire_ts") or 0.0)
            if expire_ts and now < expire_ts - 0.5:
                self._log(
                    f"skip {tid} antes de expirar (now={now:.2f} < {expire_ts:.2f})"
                )
                continue
            option_id = bucket.get("option_id")
            if option_id is None:
                option_id = self._normalize_option_id(
                    open_payload.get("broker_event", {}).get("option_id")
                    or open_payload.get("option_id")
                    or open_payload.get("order_id")
                    or bucket.get("order_ref")
                )
                if option_id is not None:
                    with self.lock:
                        live = self.pending.get(tid)
                        if live:
                            live["option_id"] = option_id
            if option_id is None:
                self._log(f"[skip] {tid} sin option_id")
                continue
            if closed_cache is None:
                closed_cache = self._fetch_closed_options()
                if closed_cache is None:
                    return
            outcome, profit_amt, entry = self._extract_result_from_closed(
                closed_cache, option_id
            )
            if outcome is None:
                self._log(f"[wait] {tid} sin resultado en optioninfo")
                continue
            close_time = float(
                entry.get("actual_expire")
                or entry.get("expiration_time")
                or entry.get("close_time")
                or time.time()
            )
            close_event = {
                "status": "CLOSE",
                "result": outcome,
                "profit_amount": profit_amt,
                "close_time": close_time,
                "value": entry.get(
                    "value",
                    open_payload.get(
                        "close_price", open_payload.get("entry_price", 0)
                    ),
                ),
                "option_id": entry.get("option_id") or option_id,
                "raw_event": entry,
            }
            self._resolve_and_log(open_payload, close_event)
            with self.lock:
                bucket_live = self.pending.get(tid)
                if bucket_live:
                    bucket_live["resolved"] = True
                    self.pending.pop(tid, None)

    def _fetch_closed_options(self) -> Optional[Sequence[Dict[str, Any]]]:
        try:
            payload = self.api.get_optioninfo_v2(50)
        except Exception as exc:
            self._log(f"[error] optioninfo_v2: {exc}")
            return None
        if not isinstance(payload, dict):
            return None
        msg = payload.get("msg") or payload
        closed = msg.get("closed_options") or msg.get("closed")
        if isinstance(closed, list):
            return closed
        return None

    def _extract_result_from_closed(
        self, entries: Sequence[Dict[str, Any]], option_id: Any
    ) -> Tuple[Optional[str], float, Optional[Dict[str, Any]]]:
        target = str(option_id)
        for entry in entries:
            candidate = entry.get("option_id")
            if candidate is None:
                raw_id = entry.get("id")
                if isinstance(raw_id, (list, tuple)) and raw_id:
                    candidate = raw_id[0]
            if candidate is None:
                continue
            if str(candidate) != target:
                continue
            raw_outcome = entry.get("result") or entry.get("win")
            outcome = self._normalize_outcome_label(raw_outcome) or raw_outcome
            profit_amt = self._coerce_profit_amount(entry.get("profit_amount"))
            if profit_amt == 0.0:
                try:
                    win_amount = float(entry.get("win_amount", 0) or 0.0)
                    amount = float(entry.get("amount", 0) or 0.0)
                    profit_amt = abs(win_amount - amount)
                except (TypeError, ValueError):
                    profit_amt = 0.0
            return outcome, profit_amt, entry
        return None, 0.0, None

    def _interpret_check_win_result(self, result: Any) -> tuple[Optional[str], float]:
        if result is None:
            return None, 0.0

        if isinstance(result, (list, tuple)):
            if not result:
                return None, 0.0
            # Some wrappers return (check_flag, payload) or (status, profit).
            if len(result) == 2 and isinstance(result[0], bool):
                check_flag, payload = result
                if not check_flag:
                    return None, 0.0
                result = payload
            else:
                status_candidate = result[0]
                profit_candidate = result[1] if len(result) > 1 else None
                outcome = self._normalize_outcome_label(status_candidate)
                profit_amt = self._coerce_profit_amount(profit_candidate)
                if outcome:
                    if profit_amt == 0.0 and isinstance(status_candidate, (int, float)):
                        profit_amt = abs(float(status_candidate))
                    elif profit_amt == 0.0 and isinstance(profit_candidate, (int, float)):
                        profit_amt = abs(float(profit_candidate))
                    return outcome, profit_amt
                if isinstance(status_candidate, (int, float)):
                    amount = float(status_candidate)
                    return (
                        'win' if amount > 0 else 'loss' if amount < 0 else 'draw',
                        abs(amount),
                    )
                fallback_outcome = self._normalize_outcome_label(profit_candidate)
                if fallback_outcome:
                    amount = self._coerce_profit_amount(status_candidate)
                    return fallback_outcome, amount
                result = status_candidate

        outcome: Optional[str] = None
        profit_amt: float = 0.0
        if isinstance(result, (int, float)):
            profit_amt = abs(float(result))
            if result > 0:
                outcome = 'win'
            elif result < 0:
                outcome = 'loss'
            else:
                outcome = 'draw'
        elif isinstance(result, dict):
            raw_flag = (
                result.get('result')
                or result.get('status')
                or result.get('win')
                or result.get('code')
                or result.get('flag')
                or result.get('outcome')
            )
            profit_amt = self._coerce_profit_amount(
                result.get('profit_amount') or result.get('profit') or result.get('payout')
            )

            outcome = self._normalize_outcome_label(raw_flag) or raw_flag
            if outcome is None:
                try:
                    amount = float(result.get('amount'))
                except (TypeError, ValueError):
                    amount = 0.0
                if amount > 0:
                    outcome = 'win'
                elif amount < 0:
                    outcome = 'loss'
                else:
                    outcome = 'draw'

            if profit_amt == 0.0:
                try:
                    win_amount = float(result.get('win_amount', 0) or 0.0)
                    stake = float(result.get('amount', 0) or 0.0)
                    profit_amt = abs(win_amount - stake)
                except (TypeError, ValueError):
                    profit_amt = 0.0
        else:
            label = self._normalize_outcome_label(result)
            if label:
                return label, 0.0

        if outcome not in {'win', 'loss', 'draw'}:
            if profit_amt > 0:
                outcome = 'win'
            elif profit_amt < 0:
                outcome = 'loss'
            else:
                outcome = 'draw'
        return outcome, profit_amt

    @staticmethod
    def _normalize_outcome_label(label: Any) -> Optional[str]:
        if not isinstance(label, str):
            return None
        normalized = label.strip().lower()
        if not normalized:
            return None
        if normalized in {'win', 'won', 'success', 'victory', 'gana'}:
            return 'win'
        if normalized in {'loss', 'loose', 'lost', 'fail', 'failed', 'defeat', 'losses', 'perdida'}:
            return 'loss'
        if normalized in {'draw', 'tie', 'equal', 'refund', 'refunded', 'igual'}:
            return 'draw'
        return None

    @staticmethod
    def _coerce_profit_amount(value: Any) -> float:
        try:
            return abs(float(value))
        except (TypeError, ValueError):
            return 0.0

    def _resolve_and_log(self, open_payload: Dict[str, Any], close_event: Dict[str, Any]) -> None:
        raw_result = str(close_event.get("result", "")).strip().lower()
        profit_amt = float(close_event.get("profit_amount", 0) or 0.0)
        stake = float(open_payload.get("stake", 0) or 0.0)
        payout = float(open_payload.get("payout", 0) or 0.0)
        if raw_result in {"win", "won", "success", "victory"}:
            outcome = "WIN"
            profit_real = round(abs(profit_amt), 2)
            if profit_real == 0.0 and stake > 0:
                profit_real = round(stake * payout, 2)
        elif raw_result in {"loss", "loose", "lost", "fail", "failed", "defeat"}:
            outcome = "LOSS"
            profit_real = round(-abs(profit_amt), 2)
            if profit_real == 0.0 and stake > 0:
                profit_real = round(-stake, 2)
        else:
            outcome = "DRAW"
            profit_real = 0.0
        close_time = float(close_event.get("close_time", time.time()))
        open_time = float(open_payload.get("open_time", close_time))
        duration = close_time - open_time
        context = open_payload.get("context")
        decision_payload = open_payload.get("decision")
        if not decision_payload and isinstance(context, dict):
            decision_payload = context.get("decision")
        autolearn_payload = open_payload.get("autolearn")
        if not autolearn_payload and isinstance(context, dict):
            autolearn_payload = context.get("autolearn")
        final = {
            "timestamp": close_time,
            "status": "CLOSE",
            "trade_id": open_payload.get("trade_id"),
            "asset": open_payload.get("asset"),
            "direction": open_payload.get("direction"),
            "regime": open_payload.get("regime"),
            "reason": open_payload.get("reason"),
            "pattern": open_payload.get("pattern"),
            "score": open_payload.get("score"),
            "stake": open_payload.get("stake"),
            "payout": open_payload.get("payout"),
            "entry_price": open_payload.get("entry_price"),
            "context": context,
            "decision_context": open_payload.get("decision_context", context),
            "logic": open_payload.get("logic"),
            "logic_flat": open_payload.get("logic_flat", ""),
            "metadata": open_payload.get("metadata", {}),
            "outcome_real": outcome,
            "profit_real": profit_real,
            "close_price": close_event.get("value"),
            "open_time": open_time,
            "close_time": close_time,
            "duration_sec": duration,
            "decision": decision_payload,
            "autolearn": autolearn_payload,
            "broker_event": close_event,
        }
        self.logger.log_close(final)
        self._log(
            f"cerrado {final.get('trade_id')} outcome={final.get('outcome_real')} profit={final.get('profit_real')}"
        )

    def _log(self, msg: str) -> None:
        if not getattr(self, 'verbose', False):
            return
        try:
            print(f"[WATCHER] {msg}")
        except Exception:
            pass

    @staticmethod
    def _normalize_option_id(raw: Any) -> Optional[int]:
        if raw is None:
            return None
        if isinstance(raw, (list, tuple)) and raw:
            raw = raw[0]
        try:
            return int(str(raw).strip())
        except (TypeError, ValueError, AttributeError):
            return None

    def stop(self) -> None:
        self.running = False
        self._fallback_event.set()

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _compute_expire_ts(self, open_payload: Dict[str, Any], open_time: float) -> float:
        base_time = open_time if open_time > 0 else time.time()
        duration_min = self._safe_float(open_payload.get("duration"), 1.0)
        if duration_min <= 0:
            duration_min = 1.0
        return base_time + (duration_min * 60.0)
