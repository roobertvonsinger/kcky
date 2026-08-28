"""
launch_window.py — Lanzador directo de la ventana autónoma KCKY Studio (WebView2/pywebview)
Conecta contra el servidor uvicorn ya activo en :8765
"""

import sys
import os

# Fix encoding para Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import time
import urllib.request

PORT = 8765
url = f"http://127.0.0.1:{PORT}"

server_ready = False
for _ in range(15):
    try:
        resp = urllib.request.urlopen(f"{url}/api/presets", timeout=1)
        if resp.getcode() == 200:
            server_ready = True
            break
    except Exception:
        time.sleep(0.5)

if not server_ready:
    print(f"[!] Servidor KCKY no respondió en {url} tras 7.5s")
    sys.exit(1)

# Lanzar ventana autónoma WebView2
import webview

print(f"[*] Abriendo ventana independiente KCKY Studio (Medidas Smartphone 430x900)...")
window = webview.create_window(
    title="KCKY Studio",
    url=url,
    width=430,
    height=900,
    resizable=True,
    min_size=(380, 720)
)
webview.start(debug=False)
