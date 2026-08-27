"""
gui_app.py — Ventana de Escritorio Nativa para KCKY Studio (vía pywebview / WebView2)
"""

import os
import sys
import threading
import time
from pathlib import Path
import webview

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from src.config import DEFAULT_PORT
from run import run_web_studio, free_port_if_in_use

def start_server_thread():
    # Inicia uvicorn en hilo secundario si no está corriendo
    try:
        import urllib.request
        urllib.request.urlopen(f"http://127.0.0.1:{DEFAULT_PORT}/api/presets", timeout=1)
        print("[*] Servidor ya está activo en puerto", DEFAULT_PORT)
    except Exception:
        print("[*] Iniciando backend Uvicorn...")
        t = threading.Thread(target=run_web_studio, kwargs={"host": "127.0.0.1", "port": DEFAULT_PORT, "auto_open": False}, daemon=True)
        t.start()
        time.sleep(1.5)

def main():
    start_server_thread()
    url = f"http://127.0.0.1:{DEFAULT_PORT}"
    print(f"[*] Abriendo Ventana de Escritorio Nativa (WebView2) en: {url}")
    window = webview.create_window(
        title="👑 K.C.K.Y. Studio — Suite Biométrica HD & Evasión KYC",
        url=url,
        width=1420,
        height=920,
        resizable=True,
        min_size=(1024, 700)
    )
    webview.start(debug=False)

if __name__ == "__main__":
    main()
