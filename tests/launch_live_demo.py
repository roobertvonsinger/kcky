"""
launch_live_demo.py — Lanza el navegador visible en el escritorio para que Robert lo vea en tiempo real
"""

import asyncio
import os
import sys
import subprocess
import time
from pathlib import Path

BASE_DIR = Path(r"C:\Users\rober\Dropbox\TESTING DEV\repos\onboarded")
sys.path.insert(0, str(BASE_DIR))

from src.config import SCRIPTS_DIR, HARDWARE_PERSONAS, BUFFERS_DIR
from src.browser import find_orbita_executable, find_free_port, launch_browser_process
from src.liveness import convert_video_to_seamless_y4m, generate_synthetic_liveness


async def main():
    print("\n" + "="*70)
    print("  LANZANDO DEMO VISIBLE EN ESCRITORIO (WEBCAMTESTS.COM)")
    print("="*70)

    # 1. Preparar stream Y4M
    y4m_path = str(BUFFERS_DIR / "live_audit_stream.y4m")
    sample_video = r"C:\Users\rober\Downloads\WhatsApp Video 2026-04-15 at 15.36.20.mp4"

    if os.path.exists(sample_video):
        print(f"  [1/3] Usando video de Descargas con auto-encuadre biometrico...")
        convert_video_to_seamless_y4m(
            video_path=sample_video,
            output_y4m_path=y4m_path,
            min_duration=60,
            width=1280,
            height=720,
            fps=30,
            framing_mode="fill_crop"
        )
    else:
        print("  [1/3] Generando Liveness 3D sintetico...")
        test_img = BASE_DIR / "data" / "uploads" / "audit_test_face.png"
        generate_synthetic_liveness(
            image_path=str(test_img),
            output_y4m_path=y4m_path,
            duration=60,
            width=1280,
            height=720,
            fps=30,
            framing_mode="fill_crop"
        )

    # 2. Configurar spoofer de hardware
    hw_persona = HARDWARE_PERSONAS["logitech_c920"]
    spoof_script = (SCRIPTS_DIR / "webrtc_cam_spoof.js").read_text(encoding="utf-8")
    spoof_script = spoof_script.replace("Integrated Camera (04f2:b614)", hw_persona["label"])
    spoof_script = spoof_script.replace("Microphone (Realtek(R) Audio)", hw_persona["mic_label"])

    executable = find_orbita_executable()
    cdp_port = find_free_port()
    user_dir = os.path.join(os.environ.get("TEMP", "/tmp"), f"onboarded_live_{cdp_port}")
    os.makedirs(user_dir, exist_ok=True)

    print(f"  [2/3] Abriendo navegador visible en tu pantalla (Chrome)...")
    target_url = "https://webcamtests.com/"
    browser_proc = launch_browser_process(executable, y4m_path, target_url, cdp_port, user_dir)
    print(f"  [OK] Navegador abierto en pantalla (PID: {browser_proc.pid})")

    # 3. Conectar Playwright para automatizar el clic y la inyección
    print("  [3/3] Inyectando spoofer y activando camara automaticamente...")
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        cdp_browser = None
        for _ in range(30):
            await asyncio.sleep(0.3)
            try:
                cdp_browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
                break
            except Exception:
                pass

        if cdp_browser:
            context = cdp_browser.contexts[0]
            await context.grant_permissions(["camera", "microphone"], origin="https://webcamtests.com")
            await context.add_init_script(spoof_script)

            page = context.pages[0] if context.pages else await context.new_page()
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(1.5)

            # Presionar el botón "Test my cam" automáticamente en webcamtests.com
            test_btn = await page.query_selector("#webcam-launcher")
            if test_btn:
                await test_btn.click()
                print("  [OK] Boton 'Test my cam' presionado. La camara esta activa en tu pantalla!")

            # Mantener la sesión abierta para que Robert la observe
            print("\n" + "="*70)
            print("  LISTO: El navegador esta visible en tu pantalla transmitiendo el video.")
            print("  Presiona Ctrl+C o cierra la ventana cuando desees terminar.")
            print("="*70)

            # Esperar 45 segundos para que Robert lo vea
            for i in range(45):
                await asyncio.sleep(1.0)
                if browser_proc.poll() is not None:
                    break

            try:
                await cdp_browser.close()
            except Exception:
                pass

    from src.server import kill_process_tree
    kill_process_tree(browser_proc)


if __name__ == "__main__":
    asyncio.run(main())
