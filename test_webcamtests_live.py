"""
test_webcamtests_live.py — Prueba de detección y certificación de cámara en webcamtests.com
"""

import asyncio
import os
import sys
import subprocess
import time
from pathlib import Path
from playwright.async_api import async_playwright

BASE_DIR = Path(r"C:\Users\rober\Dropbox\TESTING DEV\repos\onboarded")
sys.path.insert(0, str(BASE_DIR))

from src.config import SCRIPTS_DIR, HARDWARE_PERSONAS, BUFFERS_DIR, SESSIONS_DIR
from src.browser import find_orbita_executable, find_free_port, launch_browser_process
from src.liveness import generate_synthetic_liveness, convert_video_to_seamless_y4m


async def main():
    print("\n" + "="*70)
    print("  AUDITORIA DE DETECCION DE CAMARA EN VIVO (WEBCAMTESTS.COM)")
    print("="*70)

    # 1. Preparar buffer de video Y4M con auto-encuadre
    y4m_path = str(BUFFERS_DIR / "live_audit_stream.y4m")
    
    # Buscar si hay un video de selfie en Descargas
    sample_videos = [
        r"C:\Users\rober\Downloads\WhatsApp Video 2026-04-15 at 15.36.20.mp4",
        r"C:\Users\rober\Downloads\WhatsApp Video 2024-10-08 at 15.02.59.mp4",
        r"C:\Users\rober\Downloads\WhatsApp Video 2024-08-20 at 04.31.35.mp4"
    ]
    chosen_video = None
    for sv in sample_videos:
        if os.path.exists(sv) and os.path.getsize(sv) > 10000:
            chosen_video = sv
            break

    if chosen_video:
        print(f"\n[1/4] Usando video real de Descargas: {os.path.basename(chosen_video)}")
        print("  -> Aplicando Auto-Encuadre Quirurgico Biometrico...")
        res = convert_video_to_seamless_y4m(
            video_path=chosen_video,
            output_y4m_path=y4m_path,
            min_duration=30,
            width=1280,
            height=720,
            fps=30,
            framing_mode="fill_crop"
        )
        print(f"  [OK] Stream Y4M normalizado ({res['size_mb']} MB)")
    else:
        print("\n[1/4] Generando Liveness Sintetico 3D...")
        test_img = BASE_DIR / "data" / "uploads" / "audit_test_face.png"
        res = generate_synthetic_liveness(
            image_path=str(test_img),
            output_y4m_path=y4m_path,
            duration=30,
            width=1280,
            height=720,
            fps=30,
            framing_mode="fill_crop"
        )
        print(f"  [OK] Stream Y4M sintetizado ({res['size_mb']} MB)")

    # 2. Configurar hardware persona
    hw_persona = HARDWARE_PERSONAS["logitech_c920"]
    spoof_script = (SCRIPTS_DIR / "webrtc_cam_spoof.js").read_text(encoding="utf-8")
    spoof_script = spoof_script.replace("Integrated Camera (04f2:b614)", hw_persona["label"])
    spoof_script = spoof_script.replace("Microphone (Realtek(R) Audio)", hw_persona["mic_label"])

    # 3. Lanzar Navegador Orbita / Chromium
    print("\n[2/4] Lanzando Orbita con inyeccion stealth...")
    executable = find_orbita_executable()
    cdp_port = find_free_port()
    user_dir = os.path.join(os.environ.get("TEMP", "/tmp"), f"webcam_test_{cdp_port}")
    os.makedirs(user_dir, exist_ok=True)

    # Iniciar proceso con flags
    target_url = "https://webcamtests.com/"
    browser_proc = launch_browser_process(executable, y4m_path, "about:blank", cdp_port, user_dir)
    print(f"  [OK] Proceso activo (PID: {browser_proc.pid}, CDP Port: {cdp_port})")

    # 4. Conectar Playwright e inyectar scripts
    print("\n[3/4] Conectando CDP e inyectando Stealth Spoofer...")
    async with async_playwright() as pw:
        cdp_browser = None
        for _ in range(25):
            await asyncio.sleep(0.4)
            try:
                cdp_browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
                break
            except Exception:
                pass

        if not cdp_browser:
            print("  [!] Error conectando CDP directo. Intentando reintentos...")
            sys.exit(1)

        context = cdp_browser.contexts[0]
        # Otorgar permisos de camara automaticamente
        await context.grant_permissions(["camera", "microphone"], origin="https://webcamtests.com")
        await context.add_init_script(spoof_script)

        page = context.pages[0] if context.pages else await context.new_page()
        
        print(f"\n[4/4] Navegando a {target_url} y ejecutando test de camara...")
        await page.goto("https://webcamtests.com/", timeout=40000)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2.0)

        # Clic en el botón "Test my cam" de webcamtests.com
        test_btn = await page.query_selector("#webcam-launcher")
        if test_btn:
            print("  -> Iniciando prueba en webcamtests.com...")
            await test_btn.click()
            await asyncio.sleep(6.0)

        # Capturar datos de la prueba desde el DOM de webcamtests.com
        cam_name = await page.evaluate("""() => {
            const el = document.querySelector('#webcam-name, .webcam-name, #webcam-header h2');
            return el ? el.innerText : 'Desconocido';
        }""")

        res_info = await page.evaluate("""() => {
            const list = Array.from(document.querySelectorAll('#webcam-notice, #webcam-info table tr, #webcam-fps'));
            return list.map(e => e.innerText.trim()).filter(Boolean).slice(0, 8);
        }""")

        screenshot_path = SESSIONS_DIR / "webcamtests_live_result.png"
        await page.screenshot(path=str(screenshot_path), full_page=False)

        print("\n" + "="*70)
        print("  RESULTADOS DE WEBCAMTESTS.COM:")
        print("="*70)
        print(f"  - Camara Detectada por el Sitio: {cam_name}")
        print(f"  - Telemetria Recibida:\n    " + "\n    ".join(res_info))
        print(f"  - Captura de Pantalla: {screenshot_path}")
        print("="*70 + "\n")

        await cdp_browser.close()
        from src.server import kill_process_tree
        kill_process_tree(browser_proc)


if __name__ == "__main__":
    asyncio.run(main())
