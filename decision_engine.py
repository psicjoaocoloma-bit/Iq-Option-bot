"""Decision engine orchestrating TradingLions SPEC A+B."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from collector import MarketCollector
from signals import detect_bearish_pattern, detect_bullish_pattern
from indicators import atr_micro, bollinger_extreme, fibo_zones
from dl_autolearn.context_capture import attach_candles_to_context
from dl_autolearn.inference import autolearn_gate


@dataclass(slots=True)
class Decision:
    direction: str
    regime: str
    reason: str
    pattern: str
    score: float
    asset: str
    # ?? NUEVO: snapshot de la lógica que llevó a esta señal
    logic: Dict[str, Any] | None = None


class DecisionEngine:
    """Evaluate snapshots and return the best scoring setup."""

    def __init__(
        self,
        config: Mapping[str, Any],
        api: Any | None = None,
    ) -> None:

        self.config = config
        self.api = api
        self._context_timeframe = int(getattr(config, 'timeframe', 60))
        self._context_candle_count = int(getattr(config, 'autolearn_candle_count', 120))
        self._autolearn_model_path = getattr(
            config, 'autolearn_model_path', 'dl_autolearn/autolearn_model.joblib'
        )
        self._autolearn_min_prob = float(getattr(config, 'autolearn_min_prob', 0.55))
        self._autolearn_enabled = bool(getattr(config, 'autolearn_enabled', True))



    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def evaluate(
        self,
        collector: MarketCollector,
        asset: str,
        payout: float,
    ) -> Tuple[Optional[Decision], Optional[Dict[str, Any]]]:
        snapshot = collector.get_snapshot(asset)
        candles_m1 = list(snapshot.get("m1", []))
        if len(candles_m1) < 3:
            return None, None

        trend_data = snapshot.get("trend", {})
        range_data = snapshot.get("range", {})
        volatility = float(snapshot.get("volatility", 0.0))

        signals_cfg = getattr(self.config, "signals", None)
        min_payout = getattr(signals_cfg, "min_payout", 0.75)
        min_volatility = getattr(signals_cfg, "min_volatility", 0.0)
        min_score = getattr(signals_cfg, "min_signal_score", 0.55)

        regime = "trend" if self._in_trend(trend_data) else "range"
        decision_context = self._build_decision_context(
            asset=asset,
            snapshot=snapshot,
            payout=payout,
            regime=regime,
            volatility=volatility,
        )

        if payout < min_payout:
            return None, decision_context
        if volatility < min_volatility:
            return None, decision_context

        candidates: List[Decision] = []

        if regime == "trend":
            candidate = self._trend_candidate(
                asset, candles_m1, trend_data, payout, volatility
            )
            if candidate:
                candidates.append(candidate)
        else:
            candidate = self._range_candidate(
                asset, candles_m1, range_data, payout, volatility
            )
            if candidate:
                candidates.append(candidate)

        if not candidates:
            return None, decision_context

        best = max(candidates, key=lambda decision: decision.score)
        if best.score < min_score:
            return None, decision_context

        final_context = dict(decision_context or {})
        final_context.setdefault("decision", {})
        final_context["decision"] = {
            "pattern": best.pattern,
            "direction": best.direction,
            "score": best.score,
            "reason": best.reason,
        }

        if self._autolearn_enabled:
            prob_win, allow = autolearn_gate(
                final_context,
                model_path=self._autolearn_model_path,
                min_prob=self._autolearn_min_prob,
            )
            if prob_win is not None:
                auto_block = final_context.setdefault("autolearn", {})
                auto_block["prob_win"] = prob_win
                auto_block["min_prob"] = self._autolearn_min_prob
                auto_block["allowed"] = bool(allow)
            if not allow:
                return None, final_context

        return best, final_context

    # ------------------------------------------------------------------
    # Candidate builders
    # ------------------------------------------------------------------
    def _trend_candidate(
        self,
        asset: str,
        candles_m1: List[Mapping[str, float]],
        trend_m5: Mapping[str, float],
        payout: float,
        volatility: float,
    ) -> Optional[Decision]:
        bias = float(trend_m5.get("bias", 0.0))
        if bias == 0.0:
            return None

        if bias > 0:
            pattern, base_reason = detect_bullish_pattern(candles_m1)
            direction = "call"
        else:
            pattern, base_reason = detect_bearish_pattern(candles_m1)
            direction = "put"

        if not pattern:
            return None

        reason = base_reason or "trend continuation"
        score = self._compute_signal_score(
            regime="trend",
            pattern=pattern,
            payout=payout,
            volatility=volatility,
            bias=bias,
            candles=candles_m1[-3:],
        )

        # ?? Snapshot de lógica para contexto
        last3 = candles_m1[-3:]
        last3_compact = [
            {
                "open": float(c.get("open", 0.0)),
                "close": float(c.get("close", 0.0)),
                "high": float(c.get("max", c.get("high", 0.0))),
                "low": float(c.get("min", c.get("low", 0.0))),
            }
            for c in last3
        ]

        logic: Dict[str, Any] = {
            "regime": "trend",
            "pattern": pattern,
            "reason": reason,
            "payout": payout,
            "volatility": volatility,
            "bias": bias,
            "trend_state": trend_m5.get("state", ""),
            "last3_candles": last3_compact,
        }

        return Decision(
            direction=direction,
            regime="trend",
            reason=f"{reason} / bias={bias:+.2f}",
            pattern=pattern,
            score=score,
            asset=asset,
            logic=logic,
        )

    def _range_candidate(
        self,
        asset: str,
        candles_m1: List[Mapping[str, float]],
        range_bounds: Mapping[str, float],
        payout: float,
        volatility: float,
    ) -> Optional[Decision]:
        lower = float(range_bounds.get("lower", 0.0))
        upper = float(range_bounds.get("upper", 0.0))
        width = float(range_bounds.get("width", 0.0))
        tolerance = float(range_bounds.get("tolerance", width * 0.15))
        if width <= 0:
            return None

        last_close = float(candles_m1[-1].get("close", 0.0))
        direction: Optional[str] = None
        pattern: Optional[str]
        reason: Optional[str]

        if last_close <= lower + tolerance:
            pattern, reason = detect_bullish_pattern(candles_m1)
            direction = "call"
        elif last_close >= upper - tolerance:
            pattern, reason = detect_bearish_pattern(candles_m1)
            direction = "put"
        else:
            return None

        if not pattern or not direction:
            return None

        score = self._compute_signal_score(
            regime="range",
            pattern=pattern,
            payout=payout,
            volatility=volatility,
            bias=0.0,
            candles=candles_m1[-3:],
        )
        reason = reason or "range reversal"

        last3 = candles_m1[-3:]
        last3_compact = [
            {
                "open": float(c.get("open", 0.0)),
                "close": float(c.get("close", 0.0)),
                "high": float(c.get("max", c.get("high", 0.0))),
                "low": float(c.get("min", c.get("low", 0.0))),
            }
            for c in last3
        ]

        logic: Dict[str, Any] = {
            "regime": "range",
            "pattern": pattern,
            "reason": reason,
            "payout": payout,
            "volatility": volatility,
            "range_lower": lower,
            "range_upper": upper,
            "range_width": width,
            "tolerance": tolerance,
            "last_close": last_close,
            "last3_candles": last3_compact,
        }

        return Decision(
            direction=direction,
            regime="range",
            reason=f"{reason} / bounds[{lower:.5f}, {upper:.5f}]",
            pattern=pattern,
            score=score,
            asset=asset,
            logic=logic,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _in_trend(self, trend_data: Mapping[str, Any]) -> bool:
        bias = float(trend_data.get("bias", 0.0))
        state = trend_data.get("state", "range")
        return bias != 0.0 or state in {"trend_up", "trend_down"}

    def _compute_signal_score(
        self,
        regime: str,
        pattern: str,
        payout: float,
        volatility: float,
        bias: float,
        candles: List[Mapping[str, float]],
    ) -> float:
        base_map = {
            "engulfing": 0.7,
            "momentum": 0.65,
            "reversal": 0.6,
        }
        base = base_map.get(pattern, 0.55)

        last = candles[-1]
        open_ = float(last.get("open", 0.0))
        close = float(last.get("close", 0.0))
        high = float(last.get("max", last.get("high", 0.0)))
        low = float(last.get("min", last.get("low", 0.0)))
        body = abs(close - open_)
        range_ = max(high - low, 1e-6)
        momentum_ratio = min(body / range_, 1.0)
        momentum_score = 0.2 * momentum_ratio

        signals_cfg = getattr(self.config, "signals", None)
        min_payout = getattr(signals_cfg, "min_payout", 0.75)
        payout_norm = max(
            0.0, min(1.0, (payout - min_payout) / max(1e-6, 1.0 - min_payout))
        )
        payout_score = 0.1 * payout_norm

        bias_score = 0.0
        if regime == "trend":
            bias_norm = min(abs(bias), 1.0)
            bias_score = 0.15 * bias_norm

        raw_score = base + momentum_score + payout_score + bias_score
        return max(0.0, min(1.0, raw_score))

    def _build_decision_context(
        self,
        asset: str,
        snapshot: Mapping[str, Any],
        payout: float,
        regime: str,
        volatility: float,
    ) -> Dict[str, Any]:
        candles_m1: List[Mapping[str, Any]] = list(snapshot.get("m1", []))
        candles_dicts = [dict(c) for c in candles_m1]

        fibo_sample = candles_dicts[-50:]
        atr_sample = candles_dicts[-10:]
        fibo_levels = fibo_zones(fibo_sample) if fibo_sample else {}
        atr_value = atr_micro(atr_sample) if atr_sample else 0.0
        bollinger = self._compute_bollinger_context(candles_m1)

        context = {
            "asset": asset,
            "payout": payout,
            "regime": regime,
            "volatility": volatility,
            "atr_micro": atr_value,
            "fibo_zones": fibo_levels,
            "pivots": snapshot.get("pivots", {}),
            "bollinger": bollinger,
            "trend": snapshot.get("trend", {}),
            "range": snapshot.get("range", {}),
            "micro_range": snapshot.get("micro_range"),
            "timestamp": snapshot.get("timestamp"),
        }
        context = attach_candles_to_context(
            api=self.api,
            context=context,
            asset=asset,
            timeframe_sec=self._context_timeframe,
            candle_count=self._context_candle_count,
        )
        return context

    def _compute_bollinger_context(
        self,
        candles: List[Mapping[str, Any]],
        period: int = 20,
        std_multiplier: float = 2.0,
    ) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "basis": None,
            "upper": None,
            "lower": None,
            "std": None,
            "extreme_side": None,
            "is_extreme": False,
        }
        if len(candles) < 2:
            return info

        closes: List[float] = []
        window = candles[-period:]
        for candle in window:
            close = candle.get("close")
            if close is None:
                continue
            try:
                closes.append(float(close))
            except (TypeError, ValueError):
                continue

        if len(closes) < 2:
            return info

        mean = sum(closes) / len(closes)
        variance = sum((value - mean) ** 2 for value in closes) / len(closes)
        std = variance ** 0.5
        upper = mean + std_multiplier * std
        lower = mean - std_multiplier * std
        last_candle = candles[-1]
        side, is_extreme = bollinger_extreme(last_candle, upper, lower)
        info.update(
            {
                "basis": mean,
                "upper": upper,
                "lower": lower,
                "std": std,
                "extreme_side": side,
                "is_extreme": is_extreme,
            }
        )
        return info



__all__ = ["Decision", "DecisionEngine"]
