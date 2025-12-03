"""Unified configuration module for TradingLions_Reforged."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List


# ================================================================
# TIMEFRAMES
# ================================================================
TIMEFRAME_MAIN = 60    # M1 en segundos
TIMEFRAME_TREND = 300  # M5 en segundos


# ================================================================
# RISK SETTINGS
# ================================================================
@dataclass(slots=True)
class RiskSettings:
    base_stake: float = 1.0



# ================================================================
# SIGNAL SETTINGS
# ================================================================
@dataclass(slots=True)
class SignalSettings:
    min_payout: float = 0.75
    min_volatility: float = 0.0
    ema_period: int = 20
    trend_bias_threshold: float = 0.3
    range_tolerance: float = 0.35
    min_signal_score: float = 0.55


# ================================================================
# MAIN BOT CONFIG
# ================================================================
@dataclass(slots=True)
class BotConfig:
    # Lista de activos a vigilar
    assets: List[str] = field(default_factory=lambda: [
        "EURUSD-OTC",
        "GBPUSD-OTC",
        "AUDUSD-OTC",
        "USDMXN-OTC",
        "JP225-OTC",
        "XAUUSD-OTC",
        "AIG-OTC",
        "AUS200-OTC",
        "SP35-OTC",
        "AUDJPY-OTC",
        "UK100-OTC",
        "FR40-OTC",
        "GER30-OTC",
        "HK33-OTC",
    ])

    # Activo principal de referencia / fallback
    asset: str = "EURUSD-OTC"

    # Timeframes
    timeframe: int = TIMEFRAME_MAIN
    higher_timeframe: int = TIMEFRAME_TREND

    # Ajustes de riesgo y se�ales
    risk: RiskSettings = field(default_factory=RiskSettings)
    signals: SignalSettings = field(default_factory=SignalSettings)

    # AutoLearning gate defaults
    autolearn_enabled: bool = True
    autolearn_min_prob: float = 0.55
    autolearn_model_path: str = "dl_autolearn/autolearn_model.joblib"
    autolearn_candle_count: int = 120

    # Carpeta de logs
    log_directory: str = "logs" 

    # Duraci�n de la operaci�n (minutos)
    trade_duration: int = 1


__all__ = [
    "TIMEFRAME_MAIN",
    "TIMEFRAME_TREND",
    "RiskSettings",
    "SignalSettings",
    "BotConfig",
]

