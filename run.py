"""
run.py — Punto de Entrada Unificado para KCKY (CLI & Web Studio)
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

# Configurar encoding UTF-8 seguro para Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Agregar directorio actual al sys.path y fijar cwd
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)

from src.config import DEFAULT_HOST, DEFAULT_PORT, BUFFERS_DIR
from src.liveness import generate_synthetic_liveness, convert_video_to_seamless_y4m
from src.browser import find_orbita_executable, launch_browser_process, find_free_port
from src.dependency_manager import run_preflight_checks


def free_port_if_in_use(port: int):
    """Detecta y termina procesos huérfanos que tengan ocupado el puerto especificado en Windows."""
    try:
        import subprocess
        cmd = f'powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique"'
        output = subprocess.check_output(cmd, shell=True, text=True, errors="replace").strip()
        current_pid = os.getpid()
        for line in output.splitlines():
            line = line.strip()
            if line and line.isdigit():
                pid = int(line)
                if pid != current_pid and pid != 0:
                    print(f"[*] Liberando puerto {port} (Terminando proceso huérfano PID: {pid})...")
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
    except Exception:
        pass


def find_standalone_browser() -> Optional[str]:
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe")
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def open_autonomous_app_window(url: str):
    """Lanza la ventana de aplicación autónoma independiente con medidas de smartphone (430x900)."""
    import subprocess
    import sys
    
    # 1. Intentar lanzar WebView2 mediante subproceso interactivo independiente (hilo principal nativo propio)
    launch_script = BASE_DIR / "launch_window.py"
    if launch_script.is_file():
        try:
            subprocess.Popen([sys.executable, str(launch_script)])
            return
        except Exception:
            pass

    # 2. Fallback a Standalone App Window nativa (Chrome/Edge sin marcos de navegador)
    browser_exe = find_standalone_browser()
    if browser_exe:
        cmd = [
            browser_exe,
            f"--app={url}",
            "--window-size=430,900",
            "--window-position=500,50",
            "--new-window",
            "--disable-extensions",
            "--disable-plugins",
            "--disable-default-apps"
        ]
        try:
            subprocess.Popen(cmd)
            return
        except Exception:
            pass

    # 3. Fallback a navegador por defecto
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass


def run_web_studio(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, auto_open: bool = True):
    """Inicia el backend de KCKY Studio en hilo principal y sostiene la ventana autónoma permanentemente."""
    free_port_if_in_use(port)
    run_preflight_checks()

    import uvicorn
    import threading
    import time
    from src.server import app

    url = f"http://127.0.0.1:{port}"
    print("======================================================================")
    print("  K.C.K.Y. STUDIO -- Suite Biometrica HD (Ventana Autonoma)")
    print(f"  URL Backend: {url}")
    print("  GPU: AMD Radeon RX 580 (DirectML Enabled)")
    print("======================================================================")

    if auto_open:
        def _deferred_open():
            time.sleep(1.2)
            open_autonomous_app_window(url)
        threading.Thread(target=_deferred_open, daemon=True).start()

    # Uvicorn en hilo principal: NUNCA se cierra solo
    uvicorn.run(app, host=host, port=port, log_level="error")


def main():
    parser = argparse.ArgumentParser(description="KCKY — Plataforma de Evasión WebRTC & Auditoría KYC (K.C.K.Y.)")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host para Web Studio (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Puerto para Web Studio (default: {DEFAULT_PORT})")
    parser.add_argument("--no-open", action="store_true", help="No abrir navegador automáticamente")

    subparsers = parser.add_subparsers(dest="command", help="Comando a ejecutar (opcional)")

    # Subcomando Web
    web_parser = subparsers.add_parser("web", help="Iniciar Studio Web GUI")
    web_parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host (default: {DEFAULT_HOST})")
    web_parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Puerto (default: {DEFAULT_PORT})")
    web_parser.add_argument("--no-open", action="store_true", help="No abrir navegador automáticamente")

    # Subcomando Liveness CLI
    live_parser = subparsers.add_parser("liveness", help="Generar Liveness Sintético Y4M desde 1 foto")
    live_parser.add_argument("image", help="Ruta a la foto del rostro (INE / Selfie)")
    live_parser.add_argument("-o", "--output", help="Ruta de salida del archivo .y4m")
    live_parser.add_argument("-d", "--duration", type=int, default=90, help="Duración en segundos (default: 90)")
    live_parser.add_argument("-w", "--width", type=int, default=1280, help="Ancho (default: 1280)")
    live_parser.add_argument("-H", "--height", type=int, default=720, help="Alto (default: 720)")
    live_parser.add_argument("-fps", type=int, default=30, help="FPS (default: 30)")
    live_parser.add_argument("--framing", choices=["fill_crop", "fit_pad"], default="fill_crop", help="Modo de encuadre (default: fill_crop)")

    # Subcomando Launch Browser CLI
    launch_parser = subparsers.add_parser("launch", help="Lanzar Orbita con cámara Y4M inyectada")
    launch_parser.add_argument("y4m", help="Ruta al archivo .y4m")
    launch_parser.add_argument("url", nargs="?", default="about:blank", help="URL destino (default: about:blank)")

    # Subcomando Status
    subparsers.add_parser("status", help="Auditar estado de hardware y dependencias")

    args = parser.parse_args()

    if args.command == "liveness":
        out_y4m = args.output or str(BUFFERS_DIR / f"cli_liveness_{Path(args.image).stem}.y4m")
        res = generate_synthetic_liveness(
            image_path=args.image,
            output_y4m_path=out_y4m,
            duration=args.duration,
            width=args.width,
            height=args.height,
            fps=args.fps,
            framing_mode=args.framing
        )
        print(f"[+] Liveness completado: {res['y4m_path']} ({res['size_mb']} MB, {args.width}x{args.height})")

    elif args.command == "launch":
        executable = find_orbita_executable()
        if not executable:
            print("[!] Error: No se encontró ejecutable de Orbita o Chrome.")
            sys.exit(1)

        cdp_port = find_free_port()
        user_dir = os.path.join(os.environ.get("TEMP", "/tmp"), f"kcky_cli_{cdp_port}")
        os.makedirs(user_dir, exist_ok=True)

        print(f"[*] Lanzando Navegador con {args.y4m} hacia {args.url} (CDP :{cdp_port})...")
        proc = launch_browser_process(executable, args.y4m, args.url, cdp_port, user_dir)
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()

    elif args.command == "status":
        from src.server import find_orbita_executable, get_deep_live_cam_python
        print("=== ESTADO DEL SISTEMA KCKY ===")
        print(f"  Orbita/Chrome Browser: {find_orbita_executable() or 'No detectado'}")
        print(f"  Deep-Live-Cam Venv: {get_deep_live_cam_python() or 'No detectado'}")
        print(f"  DirectML GPU: AMD Radeon RX 580 (Activo)")

    else:
        # Por defecto corre la interfaz Web Studio
        host = getattr(args, "host", DEFAULT_HOST)
        port = getattr(args, "port", DEFAULT_PORT)
        no_open = getattr(args, "no_open", False)
        run_web_studio(host=host, port=port, auto_open=not no_open)


if __name__ == "__main__":
    main()
