import threading
import time
from watcher import main as watcher_main


def start_background_watcher():
    """
    Ejecuta watcher.py en segundo plano.
    Se importa desde el bot:
        from tradinglions import start_background_watcher
        start_background_watcher()
    """
    thread = threading.Thread(target=watcher_main, daemon=True)
    thread.start()
    time.sleep(1)
    print("[AUTO-WATCHER] Background watcher iniciado.")
