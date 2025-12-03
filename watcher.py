from __future__ import annotations

import csv
import glob
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import curses

try:
    from iqoptionapi.stable_api import IQ_Option  # type: ignore
except Exception:  # pragma: no cover
    IQ_Option = None  # type: ignore


def _discover_log_dir() -> Path:
    cfg_path = Path("config.json")
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            value = data.get("log_dir")
            if isinstance(value, str) and value.strip():
                return Path(value)
        except Exception:
            pass
    try:
        from config import BotConfig  # type: ignore

        return Path(BotConfig().log_directory)
    except Exception:
        return Path("logs")


LOG_DIR = _discover_log_dir()
REFRESH_SECONDS = 1.0


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None, ""):
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


class SafeScreen:
    def __init__(self, screen: curses.window):
        self._screen = screen

    def __getattr__(self, name: str):
        return getattr(self._screen, name)

    def addstr(self, y: int, x: int, text: object, *args) -> None:
        try:
            max_y, max_x = self._screen.getmaxyx()
        except Exception:
            max_y = max_x = 0
        if y < 0 or (max_y and y >= max_y):
            return
        if x < 0:
            x = 0
        if isinstance(text, bytes):
            text = text.decode("utf-8", "ignore")
        text = str(text)
        available = max_x - x if max_x else None
        if available is not None and available > 0 and len(text) > available:
            text = text[: max(1, available - 1)]
        try:
            if args:
                self._screen.addstr(y, x, text, *args)
            else:
                self._screen.addstr(y, x, text)
        except Exception:
            pass


def init_colors() -> None:
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)
    curses.init_pair(2, curses.COLOR_RED, -1)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)
    curses.init_pair(4, curses.COLOR_CYAN, -1)
    curses.init_pair(5, curses.COLOR_WHITE, -1)


def profit_bar(value: float, width: int = 40, scale: float = 50.0) -> str:
    half = max(1, width // 2)
    if scale <= 0:
        scale = 1.0
    ratio = max(-1.0, min(1.0, value / scale))
    fill = int(round(ratio * half))
    left_fill = min(0, fill)
    right_fill = max(0, fill)
    left = "-" * (half + left_fill) + " " * (-left_fill)
    right = "+" * right_fill + " " * (half - right_fill)
    return f"[{left}|{right}]"


@dataclass
class DashboardData:
    total: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    profit: float = 0.0
    recent: List[Dict[str, Any]] = None
    wins_value: float = 0.0
    losses_value: float = 0.0
    max_profit: float = 0.0
    max_loss: float = 0.0


def read_latest_trades() -> DashboardData:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(LOG_DIR.glob("trades_*.csv"))
    if not files:
        return DashboardData(total=0, wins=0, losses=0, draws=0, profit=0.0, recent=[])

    path = files[-1]
    rows: List[Dict[str, str]] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if str(row.get("status", "")).upper() != "CLOSE":
                continue
            rows.append(row)

    if not rows:
        return DashboardData(total=0, wins=0, losses=0, draws=0, profit=0.0, recent=[])

    wins = losses = draws = 0
    profit = 0.0
    wins_value = 0.0
    losses_value = 0.0
    running_total = 0.0
    max_running = 0.0
    min_running = 0.0
    ordered_rows = sorted(
        rows,
        key=lambda row: safe_float(
            row.get("close_time") or row.get("timestamp"), 0.0
        ),
    )
    recent: List[Dict[str, Any]] = []

    for row in ordered_rows:
        outcome = str(row.get("outcome_real", "")).upper()
        p = safe_float(row.get("profit_real"), 0.0)
        profit += p
        if p >= 0:
            wins_value += p
        else:
            losses_value += p
        running_total += p
        max_running = max(max_running, running_total)
        min_running = min(min_running, running_total)
        if outcome == "WIN":
            wins += 1
        elif outcome == "LOSS":
            losses += 1
        elif outcome == "DRAW":
            draws += 1

    for row in ordered_rows[-10:]:
        recent.append(
            {
                "trade_id": row.get("trade_id"),
                "asset": row.get("asset"),
                "outcome": row.get("outcome_real"),
                "profit": safe_float(row.get("profit_real"), 0.0),
                "entry_price": row.get("entry_price"),
                "close_price": row.get("close_price"),
                "time": datetime.fromtimestamp(float(row.get("close_time", 0.0))).strftime("%H:%M:%S")
                if row.get("close_time")
                else "",
            }
        )

    return DashboardData(
        total=wins + losses + draws,
        wins=wins,
        losses=losses,
        draws=draws,
        profit=profit,
        recent=recent,
        wins_value=wins_value,
        losses_value=losses_value,
        max_profit=max_running,
        max_loss=min_running,
    )


def dashboard(stdscr: curses.window) -> None:
    screen = SafeScreen(stdscr)
    curses.curs_set(0)
    stdscr.nodelay(True)
    init_colors()

    while True:
        screen.erase()
        now = datetime.now().strftime("%H:%M:%S")
        data = read_latest_trades()

        if data.total > 0:
            winrate = data.wins / data.total * 100.0
        else:
            winrate = 0.0

        screen.addstr(0, 2, "=== TRADING LIONS DASHBOARD (solo lectura de logs) ===", curses.color_pair(4))
        screen.addstr(1, 2, f"Hora local: {now}", curses.color_pair(5))

        y = 3
        screen.addstr(y, 2, f"Trades totales: {data.total}", curses.color_pair(5))
        y += 1
        screen.addstr(y, 2, f"Wins: {data.wins}   Losses: {data.losses}   Draws: {data.draws}", curses.color_pair(5))
        y += 1
        screen.addstr(y, 2, f"Winrate: {winrate:.1f} %", curses.color_pair(3))
        y += 1

        color_profit = 1 if data.profit >= 0 else 2
        screen.addstr(y, 2, f"Profit acumulado (neto): {data.profit:+.2f} USD", curses.color_pair(color_profit))
        y += 1
        screen.addstr(y, 2, f"Ganado: +{data.wins_value:.2f} USD   Perdido: -{abs(data.losses_value):.2f} USD", curses.color_pair(5))
        y += 1
        screen.addstr(y, 2, profit_bar(data.profit), curses.color_pair(3))
        y += 1
        screen.addstr(y, 2, f"Top profit del dia: {data.max_profit:+.2f} USD", curses.color_pair(1 if data.max_profit >= 0 else 2))
        y += 1
        screen.addstr(y, 2, f"Top perdida acumulada: {data.max_loss:+.2f} USD", curses.color_pair(2 if data.max_loss < 0 else 5))
        y += 2
        screen.addstr(y, 2, "Ultimos cierres:", curses.color_pair(3))
        y += 1
        for t in data.recent:
            outcome = str(t.get("outcome", "")).upper()
            col = 1 if outcome == "WIN" else 2 if outcome == "LOSS" else 3
            screen.addstr(
                y,
                4,
                f"{t['time']} {t['trade_id']} {t['asset']} {outcome} {t['profit']:+.2f} ({t['entry_price']} -> {t['close_price']})",
                curses.color_pair(col),
            )
            y += 1
            if y > curses.LINES - 3:
                break

        screen.addstr(curses.LINES - 2, 2, "Presiona 'q' para salir del dashboard.", curses.color_pair(5))
        screen.refresh()

        ch = stdscr.getch()
        if ch in (ord("q"), ord("Q")):
            break
        time.sleep(REFRESH_SECONDS)


def main() -> None:
    curses.wrapper(dashboard)


if __name__ == "__main__":
    main()
