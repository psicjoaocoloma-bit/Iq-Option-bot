import sys
import os
import time
import threading
import json
from pathlib import Path

# Asegurar que iqoptionapi estÃ¡ en el path, como antes
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "iqoptionapi"))

from iqoptionapi.stable_api import IQ_Option
from bot import TradingLionsBot
from config import BotConfig
from result_watcher import ResultWatcher
from logger import StandaloneResultLogger


CONFIG_PATH = Path(__file__).with_name("config.json")


def load_start_settings() -> dict:
    """Lee credenciales y ajustes basicos desde config.json si existe."""
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
    except FileNotFoundError:
        print(f"[CONFIG] No se encontro {CONFIG_PATH.name}.")
    except json.JSONDecodeError as exc:
        print(f"[CONFIG] Error de formato en {CONFIG_PATH.name}: {exc}")
    return {}


def connect_api(email: str, password: str) -> IQ_Option:
    print("[CONNECT] Iniciando conexiÃ³n con IQ Option...")
    api = IQ_Option(email, password)
    api.connect()

    for _ in range(30):
        if api.check_connect():
            print("[CONNECT] AutenticaciÃ³n correcta.")
            return api
        time.sleep(1)

    raise RuntimeError("No se pudo conectar a IQ Option.")


def main() -> None:
    settings = load_start_settings()
    email = settings.get("email") or os.getenv("IQ_EMAIL")
    password = settings.get("password") or os.getenv("IQ_PASSWORD")

    if not email or not password:
        print("[CONFIG] Define email y password en config.json o en variables de entorno IQ_EMAIL/IQ_PASSWORD.")
        return

    try:
        api = connect_api(email, password)
    except Exception as e:
        print("[CONNECT] Error fatal:", e)
        return

    config = BotConfig()
    if "log_dir" in settings and settings["log_dir"]:
        config.log_directory = settings["log_dir"]
    bot = TradingLionsBot(config=config, tick_interval=1.0, api=api)

    logger = StandaloneResultLogger(log_dir=config.log_directory)
    watcher = ResultWatcher(api, logger=logger)

    # El bot debe llamar watcher.register_open_trade(...) cuando abra una operaciÃ³n
    bot.attach_watcher(watcher)

    watcher.start()
    threading.Thread(target=watcher.watcher_loop, daemon=True).start()

    try:
        print("[BOT] Iniciando TradingLions_Reforged...")
        bot.run()
    except KeyboardInterrupt:
        print("\n[BOT] Detenido por el usuario.")
    finally:
        print("[BOT] Cerrando conexiÃ³n...")
        watcher.stop()
        try:
            api.close()
        except Exception:
            pass
        time.sleep(1)


if __name__ == "__main__":
    main()
