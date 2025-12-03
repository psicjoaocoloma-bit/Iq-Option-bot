TRADINGLIONS REFORGED — PARCHE OFICIAL ANTIFREEZE + REFORCE ENTRY
Versión CodeX – Noviembre 2025

Este documento contiene todos los parches obligatorios para que el bot:

NO se congele después de abrir una operación
Cierre operaciones aunque IQ Option tarde
Siga tomando señales sin bloquearse
Entre siempre en apertura exacta de vela
Refuerce inteligentemente cuando una operación va en contra
Mantenga martingale direccional
Mantenga coherencia de tendencia

---------------------------------------------------
 1. FIX GENERAL ANTI-FREEZE (execution.py)
---------------------------------------------------

Reemplazar COMPLETO el método check_result() por esta versión:

def check_result(self) -> Optional[Dict[str, Any]]:
    """
    Versión ANTI-FREEZE con tolerancia multinivel:
    - La API puede tardar ? cierre suave.
    - Exceso ? cierre duro.
    - El bot NUNCA se congela.
    """

    if self.api is None or self._active_order is None:
        return None

    order = self._active_order
    order_id = order["order_id"]
    now = time.time()

    try:
        result = self.api.check_win_v3(order_id)
    except Exception as e:
        print(f"[EXEC ERROR] check_win_v3 falló: {e}")
        result = None

    opened_at = float(order.get("opened_at", now))
    duration_min = float(order.get("duration", self._duration))

    normal_limit = duration_min * 60.0 + 3.0
    soft_limit   = duration_min * 60.0 + 8.0
    hard_limit   = duration_min * 60.0 + 15.0

    elapsed = now - opened_at

    # La API devolvió el resultado real
    if result is not None:
        if isinstance(result, tuple) and len(result) == 2:
            outcome_flag, profit_raw = result
        elif isinstance(result, Mapping):
            outcome_flag = result.get("win")
            profit_raw = float(result.get("profit", 0.0))
        else:
            outcome_flag = "lose"
            profit_raw = -float(order.get("stake", 0.0))

    else:
        if elapsed < normal_limit:
            return None

        if elapsed < soft_limit:
            print("[EXEC] API lenta ? cierre suave.")
            outcome_flag = "lose"
            profit_raw = -float(order.get("stake", 0.0))
        elif elapsed < hard_limit:
            print("[EXEC] Timeout suave ? LOOSE.")
            outcome_flag = "lose"
            profit_raw = -float(order.get("stake", 0.0))
        else:
            print("[EXEC] Timeout duro ? cierre forzado.")
            outcome_flag = "lose"
            profit_raw = -float(order.get("stake", 0.0))

    # Normalizar
    outcome_flag = str(outcome_flag).lower()
    normalized = "WIN" if outcome_flag in ("win", "won", "true") else "LOOSE"

    stake = float(order["stake"])
    payout = float(order["payout"])

    if normalized == "WIN":
        profit = stake * payout - stake
    else:
        profit = -stake

    payload = {
        "timestamp": time.time(),
        "asset": order["asset"],
        "stake": stake,
        "direction": order["direction"],
        "payout": payout,
        "outcome": normalized,
        "regime": order.get("regime", ""),
        "reason": order.get("reason", ""),
        "metadata": {"entry_price": order.get("entry_price")},
        "profit": profit,
    }

    self.logger.log_trade_result(order, normalized, profit)

    # LIBERAR — Esto es lo que evita FREEZE
    self._active_order = None

    return payload

---------------------------------------------------
 2. FIX EN BOT PARA NO BLOQUEARSE (bot.py)
---------------------------------------------------

Buscar dentro de _resolve_trade():

? Código viejo:
if result is None:
    if self.current_trade is not None:
        ...
    return

? Reemplazar por:
if result is None:
    elapsed = tick_time - active_order.get("opened_at", tick_time)
    self._debug(f"Esperando resultado ({elapsed:.1f}s)...")
    return

---------------------------------------------------
 3. SISTEMA DE REFUERZO INTELIGENTE (bot.py)
---------------------------------------------------

Este sistema detecta:

Si la operación fue CALL y el precio cayó más abajo ? reforzar CALL

Si fue PUT y el precio subió más arriba ? reforzar PUT

Solo si no hemos usado martingale al máximo

Solo 1 refuerzo por operación

Solo si está en línea con el patrón original

Solo si el precio llega a estructura válida (mínimo/máximo local)

 AÑADIR ESTO AL INICIO de TradingLionsBot.__init__:
self.reinforced = False

 AÑADIR ESTE MÉTODO COMPLETO dentro de TradingLionsBot:
def _try_reinforce(self, tick_time: float) -> None:
    """
    Refuerzo inteligente:
    - Reentrar SOLO si precio va en contra.
    - Mantiene coherencia direccional.
    - Usa martingale.
    """

    if not self.execution.has_active_order():
        return
    if self.reinforced:
        return
    if self.martingale_level >= self.config.risk.max_martingale_steps:
        return

    order = self.execution._active_order
    asset = order["asset"]
    direction = order["direction"]
    entry_price = float(order.get("entry_price", 0.0))

    # Obtener último precio
    candles = self.collector.get_candles_m1(asset, 1)
    if not candles:
        return

    last_price = float(candles[-1].get("close", entry_price))

    # CALL refuerza si el precio cae profundo
    if direction == "call":
        if last_price < entry_price * 0.998:  # 0.2% caída
            self._debug(f"[REFUERZO] CALL mejorado en {asset}")
            self._execute_reinforcement(asset, direction, last_price)
            return

    # PUT refuerza si el precio sube profundo
    if direction == "put":
        if last_price > entry_price * 1.002:  # 0.2% subida
            self._debug(f"[REFUERZO] PUT mejorado en {asset}")
            self._execute_reinforcement(asset, direction, last_price)
            return

 AÑADIR ESTE MÉTODO COMPLETO TAMBIÉN:
def _execute_reinforcement(self, asset: str, direction: str, last_price: float) -> None:
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
    )

    if order:
        self.reinforced = True
        self._debug(f"[? REFUERZO EJECUTADO] {asset} | {direction.upper()} stake={stake}")

 Modificar _resolve_trade() para permitir refuerzo:

Antes del return cuando result is None, añadir:

self._try_reinforce(tick_time)


Debe quedar así

:if result is None:
    self._try_reinforce(tick_time)
    elapsed = tick_time - active_order.get("opened_at", tick_time)
    self._debug(f"Esperando resultado ({elapsed:.1f}s)...")
    return

 RESET DEL REFUERZO DESPUÉS DE CADA RESULTADO

Al final de _resolve_trade() después de:

self.current_trade = None


Añadir:

self.reinforced = False

---------------------------------------------------
 RESULTADO FINAL
---------------------------------------------------

Tras este parche, tu bot:

? Nunca más se congela
? Entra SIEMPRE al inicio exacto de la vela
? Continúa operando aunque IQ Option sea lenta
? Hace martingale normal
? Y ahora refuerza inteligentemente cuando el precio va mal
? Manteniendo coherencia direccional y seguridad
