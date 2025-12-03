"""Execution engine for TradingLions_Reforged."""

from __future__ import annotations

import time
import winsound
from typing import Any, Dict, Mapping, Optional

from iqoptionapi.stable_api import IQ_Option  # type: ignore

from logger import TradeLogger
from result_watcher import ResultWatcher


class ExecutionEngine:
    """
    Maneja el ciclo de vida de UNA orden binaria OTC:

    - Abre trades con reintentos.
    - Solo delega el log de la apertura en TradeLogger.
    """

    MAX_RETRIES = 3
    RETRY_DELAY = 0.3

    def __init__(
        self,
        config: Mapping[str, Any],
        api: Optional[IQ_Option] = None,
        trade_logger: Optional[TradeLogger] = None,
        result_watcher: Optional[ResultWatcher] = None,
    ) -> None:
        self.config = config
        self.api = api
        self.logger = trade_logger or TradeLogger(config)  # config es BotConfig
        self.result_watcher = result_watcher
        self._active_order: Optional[Dict[str, Any]] = None
        self._duration = getattr(self.config, "trade_duration", 1)

    def open_order(
        self,
        asset: str,
        direction: str,
        stake: float,
        payout: float,
        regime: str,
        reason: str,
        entry_price: float,
        pattern: str = "",
        score: float = 0.0,
        context: Optional[Dict[str, Any]] = None,
        logic: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:

        if self.api is None:
            raise RuntimeError("ExecutionEngine requires an IQ Option API instance")

        direction = direction.lower()
        if direction not in {"call", "put"}:
            raise ValueError("direction must be 'call' or 'put'")

        opened = False
        order_id = None

        for _ in range(self.MAX_RETRIES):
            try:
                opened, order_id = self.api.buy(stake, asset, direction, self._duration)
            except Exception:
                opened, order_id = False, None

            if opened and order_id is not None:
                break
            time.sleep(self.RETRY_DELAY)

        if not opened or order_id is None:
            return None

        opened_at = time.time()

        # IQ Option suele devolver el id como str/int; normalizamos a int para check_win_v3.
        option_id = order_id
        try:
            option_id = int(str(order_id).strip())
        except (TypeError, ValueError):
            option_id = order_id

        trade_id = f"{asset}-{option_id}"

        order: Dict[str, Any] = {
            "order_id": option_id,
            "trade_id": trade_id,
            "asset": asset,
            "stake": float(stake),
            "payout": float(payout),
            "direction": direction,
            "regime": regime,
            "reason": reason,
            "entry_price": float(entry_price),
            "opened_at": opened_at,
            "duration": float(self._duration),
            "pattern": pattern,
            "score": float(score),
            "context": context,
        }

        decision_block = context.get("decision") if isinstance(context, dict) else None
        autolearn_block = context.get("autolearn") if isinstance(context, dict) else None
        order["open_time"] = opened_at
        order["decision_context"] = context
        order["logic"] = logic
        order["logic_flat"] = order.get("logic_flat", "")
        order["metadata"] = order.get("metadata", {})
        order["decision"] = decision_block
        order["autolearn"] = autolearn_block
        order["close_price"] = order.get("entry_price")
        order["order_id_raw"] = order_id
        order["broker_event"] = {"option_id": option_id}
        order["timestamp"] = opened_at

        self._active_order = order
        self.logger.log_trade_open(order)

        if self.result_watcher is not None:
            try:
                self.result_watcher.register_open_trade(dict(order))
            except Exception:
                pass

        try:
            winsound.Beep(1500, 600)
        except Exception:
            pass

        return order

    def has_active_order(self) -> bool:
        return self._active_order is not None


__all__ = ["ExecutionEngine"]
