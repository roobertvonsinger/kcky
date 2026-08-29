"""
launch_window.py — Lanzador directo de la ventana autónoma KCKY Studio (WebView2/pywebview)
Conecta contra el servidor uvicorn ya activo en :8765
"""

import sys
import os
import subprocess
from pathlib import Path

# Fix encoding para Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Auto-relaunch a venv si hace falta
BASE_DIR = Path(__file__).resolve().parent
DLC_PYTHON = (BASE_DIR.parent / "Deep-Live-Cam" / "venv" / "Scripts" / "python.exe").resolve()
if DLC_PYTHON.is_file() and sys.executable.lower() != str(DLC_PYTHON).lower():
    try:
        import webview
    except ImportError:
        cmd = [str(DLC_PYTHON), str(Path(__file__).resolve())] + sys.argv[1:]
        sys.exit(subprocess.call(cmd))

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
    print(f"[!] Servidor KCKY no respondió en {url} tras 7.5s (Asegúrate de que run.py esté activo).")

# Lanzar ventana autónoma WebView2 con fallback a navegador en modo App
try:
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
except Exception as e:
    print(f"[!] Aviso WebView2 ({e}), abriendo en Edge/Chrome App Mode...")
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    ]
    launched = False
    for p in edge_paths:
        if os.path.isfile(p):
            subprocess.Popen([p, f"--app={url}", "--window-size=430,900"])
            launched = True
            break
    if not launched:
        import webbrowser
        webbrowser.open(url)
