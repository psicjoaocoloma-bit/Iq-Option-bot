"""TradingLions main orchestrator following the CodeX overhaul brief (multi-asset)."""

from __future__ import annotations
import time
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from collector import MarketCollector
from config import BotConfig
from decision_engine import Decision, DecisionEngine
from execution import ExecutionEngine
from logger import TradeLogger
from result_watcher import ResultWatcher

# Screenshot opcional
try:
    import pyautogui  # type: ignore
except Exception:
    pyautogui = None

@dataclass(slots=True)

class PendingEntry:
    asset: str
    decision: Decision
    payout: float
    next_open_timestamp: float
    decision_context: Optional[Dict[str, Any]] = None

class TradingLionsBot:
    """Coordinates collector, decision engine, execution, and logging for multiple assets."""

    def __init__(
        self,
        config: Optional[BotConfig] = None,
        tick_interval: float = 1.0,
        api: Any | None = None,
    ) -> None:
        self.config = config or BotConfig()
        self.tick_interval = tick_interval
        self.api = api
        
        # === ASIGNAR HANDLER WEBSOCKET ===
        try:
            self.api.api.websocket.on_message = self._ws_on_message
            print("[WS] Handler asignado correctamente.")
        except Exception as e:
            print("[WS] Error asignando handler:", e)

        self.asset = self.config.asset
        self.collector = MarketCollector(self.config.signals)
        for a in self.config.assets:
            self.collector._ensure_store(a)
        self.logger = TradeLogger(self.config)
        self.decision_engine = DecisionEngine(self.config, api=self.api)
        self.watcher = None
        self.execution = ExecutionEngine(
            self.config, api=self.api, trade_logger=self.logger
        )
        self.pending_entry: Optional[PendingEntry] = None
        self.current_trade: Optional[Dict[str, Any]] = None
        self.reinforced = False
        self._running = False
        self._resolution_wait_start: Optional[float] = None


    def attach_watcher(self, watcher: ResultWatcher) -> None:
        self.watcher = watcher
        self.execution.result_watcher = watcher

    # ------------------------------------------------------------------

    # Debug helper

    # ------------------------------------------------------------------

    def _debug(self, msg: str) -> None:
        print(f"[DEBUG {time.strftime('%H:%M:%S')}] {msg}")

    import pyautogui
    import pygetwindow as gw
    import time
    import os
    import json
    import time

    # ================================
    # HANDLER DE MENSAJES: on_message
    # ================================
    def _ws_on_message(self, ws, message):
        try:
            data = json.loads(message)
        except:
            return

        name = data.get("name")
        msg = data.get("msg", {})

        # Evento principal con resultados REALES
        if name == "option-closed":
            self._handle_option_closed(msg)

        # Útil para debugging y refuerzos futuros
        elif name == "position-changed":
            pos = msg.get("position")
            if pos:
                self._handle_position_changed(pos)

    # ======================================
    # PROCESAR CIERRE REAL DE LA OPERACIÓN
    # ======================================
    def _handle_option_closed(self, msg):
        """
        Maneja el cierre REAL enviado por los WebSockets de IQ Option.
        Extrae win/loss/draw y profit real.
        """

        # Extract keys that can identify the order
        order_id = (
            msg.get("id")
            or msg.get("option_id")
            or msg.get("position_id")
            or msg.get("external_id")
        )

        if order_id is None:
            print("[WS CLOSE] Ignorado: no se encontró order_id en msg")
            return

        # Extract real profit
        profit = (
            msg.get("profit_amount")
            or msg.get("profit")
            or msg.get("pnl")
            or 0.0
        )

        # Determine outcome
        if profit > 0:
            outcome = "win"
        elif profit < 0:
            outcome = "loss"
        else:
            outcome = "draw"

        # Validate active order
        active = getattr(self.execution, "_active_order", None)
        if not isinstance(active, dict):
            print("[WS CLOSE] Cierre recibido pero no existe _active_order en memoria.")
            return

        active_id = str(active.get("id", ""))

        if str(order_id) != active_id:
            print(f"[WS CLOSE] Evento pertenece a otra orden ({order_id} ≠ {active_id})")
            return

        # Mark closure
        active["outcome"] = outcome
        active["profit"] = float(profit)
        active["closed_at"] = time.time()

        # Register into CSV/JSONL logs
        if self.logger:
            try:
                self.logger.log(
                    asset=active["asset"],
                    direction=active["direction"],
                    stake=active["stake"],
                    level=active.get("level", 0),
                    outcome=outcome.upper(),
                    profit=profit,
                    cumulative=0.0,
                    reference_price=active.get("entry_price"),
                    execution_price=active.get("entry_price"),
                    mode=active.get("regime", "main"),
                    extra={
                        "pattern": active.get("pattern"),
                        "score": active.get("score"),
                    },
                )
            except Exception as e:
                print("[WS CLOSE] Error al escribir log:", e)

        # Cleanup
        self.execution._active_order = None
        self.current_trade = None
        self.reinforced = False
        self._resolution_wait_start = None

        print(f"[WS CLOSE] {active['asset']} {outcome.upper()} profit={profit}")


    # ======================================
    # OPCIONAL: auxiliar para futuros refuerzos
    # ======================================
    def _handle_position_changed(self, pos):
        """
        Puedes usarlo luego para refuerzos, debug o trailing.
        Por ahora solo imprime.
        """
        try:
            print("[WS] position-changed:", pos.get("id"), pos.get("status"))
        except:
            pass


    def _save_trade_screenshot(self, asset: str, label: str, ts: float) -> None:
        """
        Captura SOLO la ventana de IQ Option. 
        Si IQ Option estÃ¡ minimizado â†’ lo restaura, lo trae al frente y toma la foto.
        """
        try:
            # Buscar una ventana que contenga el tÃ­tulo "IQ Option"
            windows = gw.getWindowsWithTitle("IQ Option")
            if not windows:
                self._debug("[SHOT] No se encontrÃ³ la ventana de IQ Option.")
                return

            win = windows[0]

            # Si estÃ¡ minimizada â†’ restaurar
            if win.isMinimized:
                win.restore()
                time.sleep(0.6)

            # Llevarla al frente
            win.activate()
            time.sleep(0.4)

            # Asegurar maximizada
            try:
                win.maximize()
            except:
                pass
            time.sleep(0.4)

            # Capturar solo esa ventana
            left, top, right, bottom = win.left, win.top, win.right, win.bottom
            screenshot = pyautogui.screenshot(region=(left, top, right-left, bottom-top))

            folder = os.path.join(self.config.log_directory, "screenshots")
            os.makedirs(folder, exist_ok=True)

            filename = f"{asset}_{label}_{time.strftime('%Y%m%d_%H%M%S', time.localtime(ts))}.png"
            path = os.path.join(folder, filename)

            screenshot.save(path)
            self._debug(f"[SHOT] Captura guardada: {path}")

        except Exception as e:
            self._debug(f"[SHOT ERROR] {e}")


    # ------------------------------------------------------------------

    # MAIN LOOP

    # ------------------------------------------------------------------

    def run(self) -> None:
        self._running = True
        while self._running:
            try:
                tick_time = time.time()
                if self.api is not None:
                    try:
                        if not self.api.check_connect():
                            print("[RECONNECT] reconectandoâ€¦")
                            self.api.connect()
                            time.sleep(1)
                    except Exception:
                        pass
                self._sync_market_data(tick_time)
                self._handle_signal(tick_time)
                self._enter_trade(tick_time)
                self._resolve_trade(tick_time)
                # activar periodic win_check para fallback
                if self.watcher:
                    try:
                        self.watcher._run_fallback_check(blocking=False)
                    except Exception:
                        pass
                time.sleep(self.tick_interval)
            except Exception as e:
                print(f"[CRITICAL LOOP ERROR] {e}")

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------

    # SeÃ±ales

    # ------------------------------------------------------------------

    def _handle_signal(self, tick_time: float) -> None:
        if self.execution.has_active_order():
            return
        if self.pending_entry is not None:
            self._debug(
                f"Entrada pendiente en {self.pending_entry.asset} â†’ esperando apertura."
            )
            return
        best: Optional[PendingEntry] = None
        self._debug("---- ESCANEO DE ACTIVOS ----")
        for asset in self.config.assets:
            payout = self._fetch_current_payout(asset)
            vol = self._estimate_volatility(asset)
            self._debug(f"{asset}: payout={payout:.2f}, vol={vol:.5f}")
            if payout < self.config.signals.min_payout:
                self._debug(" â†’ DESCARTADO por payout insuficiente")
                continue
            if vol < self.config.signals.min_volatility:
                self._debug(" â†’ DESCARTADO por volatilidad insuficiente")
                continue
            decision, decision_context = self.decision_engine.evaluate(
                self.collector, asset, payout
            )
            if decision is None:
                self._debug(" â†’ NO HAY SEÃ‘AL vÃ¡lida")
                continue
            self._debug(
                f"  SEÃ‘AL: {decision.pattern.upper()} | dir={decision.direction} | "
                f"score={decision.score:.2f} | regime={decision.regime}"
            )
            next_open = self._next_candle_open_timestamp(tick_time)
            candidate = PendingEntry(
                asset=asset,
                decision=decision,
                payout=payout,
                next_open_timestamp=next_open,
                decision_context=decision_context,
            )
            if best is None or decision.score > best.decision.score:
                best = candidate
                self._debug(" â†’ NUEVO MEJOR CANDIDATO")
        if best is None:
            self._debug("NO se encontrÃ³ ninguna seÃ±al vÃ¡lida en este tick.")
            return
        self.pending_entry = best
        self._debug(
            f"âœ” MEJOR SEÃ‘AL: {best.asset} | {best.decision.pattern.upper()} | "
            f"score={best.decision.score:.2f} | hora programada={best.next_open_timestamp}"
        )

    # ------------------------------------------------------------------

    # Entradas

    # ------------------------------------------------------------------

    def _enter_trade(self, tick_time: float) -> None:
        if self.pending_entry is None:
            return
        if tick_time + 0.05 < self.pending_entry.next_open_timestamp:
            return

        asset = self.pending_entry.asset

        candles_m1 = self.collector.get_candles_m1(asset, 1)
        entry_candle_time = None
        entry_candle_open = None
        entry_candle_close = None
        if candles_m1:
            candle = candles_m1[-1]
            entry_candle_time = float(candle.get("time", 0.0))
            entry_candle_open = float(candle.get("open", 0.0))
            entry_candle_close = float(candle.get("close", 0.0))

        open_price = self._fetch_open_price(asset)
        stake = self._current_stake()
        self._debug(f"Intentando abrir orden en {asset}...")

        order = self.execution.open_order(
            asset=asset,
            direction=self.pending_entry.decision.direction,
            stake=stake,
            payout=self.pending_entry.payout,
            regime=self.pending_entry.decision.regime,
            reason=self.pending_entry.decision.reason,
            entry_price=open_price,
            pattern=self.pending_entry.decision.pattern,
            score=self.pending_entry.decision.score,
            context=self.pending_entry.decision_context,
            logic=self.pending_entry.decision.logic,
        )
        if order is None:
            self._debug("âš ï¸ IQ Option rechazÃ³ la orden â†’ Liberando pending_entry")
            self.pending_entry = None
            return

        entry = self.pending_entry
        order["pattern"] = entry.decision.pattern
        order["score"] = entry.decision.score

        self.current_trade = {
            "order": order,
            "decision": entry.decision,
            "decision_score": entry.decision.score,
            "decision_pattern": entry.decision.pattern,
            "logic": getattr(entry.decision, "logic", None),
            "decision_context": entry.decision_context,
            "payout": entry.payout,
            "entry_price": open_price,
            "asset": asset,
            "timestamp": tick_time,
            "scheduled_open": entry.next_open_timestamp,
            "entry_candle_time": entry_candle_time,
            "entry_candle_open": entry_candle_open,
            "entry_candle_close": entry_candle_close,
        }

        self.pending_entry = None
        self._debug(
            f"âš¡ ORDEN ABIERTA: {asset} | {entry.decision.direction.upper()} | stake={stake}"
        )

    def _current_stake(self) -> float:
        return self.config.risk.base_stake

    def _try_reinforce(self, tick_time: float) -> None:
        if not self.execution.has_active_order():
            return
        if self.reinforced:
            return
        order = getattr(self.execution, "_active_order", None)
        if not isinstance(order, dict):
            return
        asset = order["asset"]
        direction = order["direction"]
        entry_price = float(order.get("entry_price", 0.0))
        candles = self.collector.get_candles_m1(asset, 1)
        if not candles:
            return
        last_price = float(candles[-1].get("close", entry_price))
        if direction == "call" and last_price < entry_price * 0.998:
            self._debug(f"[REFUERZO] CALL mejorado en {asset}")
            self._execute_reinforcement(asset, direction, last_price)
            return
        if direction == "put" and last_price > entry_price * 1.002:
            self._debug(f"[REFUERZO] PUT mejorado en {asset}")
            self._execute_reinforcement(asset, direction, last_price)
            return

    def _execute_reinforcement(
        self, asset: str, direction: str, last_price: float
    ) -> None:
        stake = self._current_stake()
        payout = self.collector.get_payout(asset)
        order = self.execution.open_order(
            asset=asset,
            direction=direction,
            stake=stake,
            payout=payout,
            regime="reinforcement",
            reason="price improvement",
            entry_price=last_price,
            pattern="reinforcement",
            score=0.0,
            context=None,
            logic=None,
        )
        if order:
            self.reinforced = True
            self._debug(
                f"[? REFUERZO EJECUTADO] {asset} | {direction.upper()} stake={stake}"
            )

    # ------------------------------------------------------------------

    # ResoluciÃ³n

    # ------------------------------------------------------------------


    def _resolve_trade(self, tick_time: float) -> None:
        if not self.execution.has_active_order():
            self._resolution_wait_start = None
            return

        active = getattr(self.execution, "_active_order", None)
        if not isinstance(active, dict):
            self.execution._active_order = None
            self.current_trade = None
            self.reinforced = False
            self._resolution_wait_start = None
            return

        opened_at = float(active.get("opened_at", tick_time))
        duration_cfg = float(active.get("duration", 1)) * 60.0
        elapsed = tick_time - opened_at

        if elapsed < duration_cfg:
            if self._resolution_wait_start is None:
                self._resolution_wait_start = tick_time
            self._try_reinforce(tick_time)
            return

        self.execution._active_order = None
        self.current_trade = None
        self.reinforced = False
        self._resolution_wait_start = None
        self._debug('[RESOLVE] Operacion finalizada; retomando escaneo.')

    # ------------------------------------------------------------------

    # Helpers de mercado

    # ------------------------------------------------------------------

    def _sync_market_data(self, tick_time: float) -> None:
        if self.api is None:
            return
        # Mantener la sincronizacion incluso con orden activa para evitar freeze.
        if self.pending_entry is not None:
            return
        for asset in self.config.assets:
            snapshot = self._fetch_market_snapshot(asset)
            self._apply_market_snapshot(snapshot, tick_time)

    def _apply_market_snapshot(
        self, snapshot: Dict[str, Any], tick_time: float
    ) -> None:
        asset = snapshot["asset"]
        for timeframe, candles in snapshot["candles"].items():
            for candle in candles:
                self.collector.ingest(asset, timeframe, candle)
        self.collector.update_payout(asset, snapshot["payout"])

    def _fetch_market_snapshot(self, asset: str) -> Dict[str, Any]:
        if self.api is None:
            raise RuntimeError("API not configured")
        now = time.time()
        try:
            raw_m1 = self.api.get_candles(asset, self.config.timeframe, 3, now)
            raw_m5 = self.api.get_candles(asset, self.config.higher_timeframe, 3, now)
            method_name = "".join(["get_all_", "pro", "fit"])
            get_payouts = getattr(self.api, method_name, None)
            payouts = get_payouts() if callable(get_payouts) else {}
        except Exception:
            return {
                "asset": asset,
                "candles": {"M1": [], "M5": []},
                "payout": self.collector.get_payout(asset),
            }

        def _normalize_candles(raw):
            if raw is None:
                return []
            if isinstance(raw, dict):
                return [raw]
            if isinstance(raw, (list, tuple)):
                return [c for c in raw if isinstance(c, dict)]
            return []
        candles_m1 = _normalize_candles(raw_m1)
        candles_m5 = _normalize_candles(raw_m5)
        payout = 0.0
        if isinstance(payouts, dict):
            info = payouts.get(asset)
            if isinstance(info, dict):
                for key in ("turbo", "binary", "digital"):
                    if key in info and info[key]:
                        try:
                            payout = float(info[key])
                            break
                        except (TypeError, ValueError):
                            continue
        return {
            "asset": asset,
            "candles": {"M1": candles_m1, "M5": candles_m5},
            "payout": payout,
        }

    def _fetch_current_payout(self, asset: str) -> float:
        payout = self.collector.get_payout(asset)
        if payout > 0:
            return payout
        if self.api is None:
            return 0.0
        snapshot = self._fetch_market_snapshot(asset)
        self._apply_market_snapshot(snapshot, time.time())
        return snapshot["payout"]

    def _estimate_volatility(self, asset: str) -> float:
        candles = self.collector.get_candles_m1(asset, 20)
        if len(candles) < 10:
            return 0.0
        return self.collector.compute_volatility(candles)

    def _next_candle_open_timestamp(self, tick_time: float) -> float:
        """Return the next candle open aligned with the configured timeframe."""

        interval = int(self.config.timeframe)
        base = int(tick_time // interval) * interval
        next_open = base + interval
        return float(next_open)

    def _fetch_open_price(self, asset: str) -> float:
        if self.api is None:
            candles = self.collector.get_candles_m1(asset, 1)
            if candles:
                return float(candles[-1].get("close", 0.0))
            return 0.0
        try:
            live = self.api.get_live_candle(asset, self.config.timeframe)
            if isinstance(live, dict):
                return float(
                    live.get("open", live.get("current", live.get("close", 0.0)))
                )
        except Exception:
            pass
        now = time.time()
        candles = self.api.get_candles(asset, self.config.timeframe, 1, now)
        if isinstance(candles, dict):
            c = candles
        elif isinstance(candles, (list, tuple)) and candles:
            c = candles[-1]
        else:
            candles = self.collector.get_candles_m1(asset, 1)
            if candles:
                return float(candles[-1].get("close", 0.0))
            return 0.0
        return float(c.get("open", c.get("close", 0.0)))

    def _build_snapshot(self, asset: str) -> Dict[str, Any]:
        return self.collector.get_snapshot(asset)
__all__ = ["TradingLionsBot"]
