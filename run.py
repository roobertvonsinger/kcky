"""
run.py — Punto de Entrada Unificado para Onboarded (CLI & Web Studio)
"""

import argparse
import os
import sys
import webbrowser
from pathlib import Path

# Agregar directorio actual al sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from src.config import DEFAULT_HOST, DEFAULT_PORT, BUFFERS_DIR
from src.liveness import generate_synthetic_liveness, convert_video_to_seamless_y4m
from src.browser import find_orbita_executable, launch_browser_process, find_free_port


def run_native_app(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
    """Inicia el servidor backend y abre una Ventana Nativa de Escritorio (Desktop App) en Windows."""
    import uvicorn
    import threading
    import time
    from src.server import app

    url = f"http://{host}:{port}"
    print("======================================================================")
    print("  ONBOARDED — Suite de Inyeccion Biometrica & Auditoria KYC (Desktop)")
    print(f"  URL Backend: {url}")
    print("  GPU: AMD Radeon RX 580 (DirectML Enabled)")
    print("======================================================================")

    # Iniciar servidor Uvicorn en hilo secundario daemon
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    time.sleep(1.0)

    try:
        import webview
        print("[*] Abriendo ventana nativa de escritorio...")
        window = webview.create_window(
            title="ONBOARDED — Suite de Inyección Biométrica & KYC (DirectML AMD RX 580)",
            url=url,
            width=1320,
            height=860,
            resizable=True,
            min_size=(1040, 700)
        )
        webview.start()
    except Exception as err:
        print(f"[!] PyWebView no disponible o fallo ({err}), abriendo en navegador...")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


def run_web_studio(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, auto_open: bool = True):
    """Inicia el servidor web FastAPI con Uvicorn."""
    run_native_app(host, port)


def main():
    parser = argparse.ArgumentParser(description="ONBOARDED — Plataforma de Evasión WebRTC & Auditoría KYC")
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
        user_dir = os.path.join(os.environ.get("TEMP", "/tmp"), f"onboarded_cli_{cdp_port}")
        os.makedirs(user_dir, exist_ok=True)

        print(f"[*] Lanzando Orbita con {args.y4m} hacia {args.url} (CDP :{cdp_port})...")
        proc = launch_browser_process(executable, args.y4m, args.url, cdp_port, user_dir)
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()

    elif args.command == "status":
        from src.server import find_orbita_executable, get_deep_live_cam_python
        print("=== ESTADO DEL SISTEMA ONBOARDED ===")
        print(f"  Orbita Browser: {find_orbita_executable() or 'No detectado'}")
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
