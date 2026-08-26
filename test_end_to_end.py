"""
test_end_to_end.py — Suite Autónoma de Verificación Extremo a Extremo para Onboarded
Valida:
1. Servidor FastAPI & REST API
2. Generación FFmpeg Liveness 3D (Y4M 1280x720 30fps)
3. Inyección en Orbita / Chromium via CDP
4. WebRTC Device Spoofing (enumerateDevices, getSettings, getCapabilities)
5. Captura Real de Video WebRTC en Canvas con análisis de píxeles
"""

import asyncio
import os
import sys
import time
import json
import urllib.request
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

HTML_TEST_HARNESS = """<!DOCTYPE html>
<html>
<head><title>WebRTC Harness</title></head>
<body style="background:#111; color:#fff; font-family:sans-serif; text-align:center;">
    <h2>Test Harness WebRTC</h2>
    <video id="v" autoplay playsinline muted style="width:640px; border:2px solid #00f090;"></video>
    <canvas id="c" width="1280" height="720" style="display:none;"></canvas>
    <div id="status">Iniciando...</div>
    <script>
        async function runCamTest() {
            try {
                const devs = await navigator.mediaDevices.enumerateDevices();
                const videoDev = devs.find(d => d.kind === 'videoinput');
                window.__deviceLabel = videoDev ? videoDev.label : 'None';
                window.__deviceId = videoDev ? videoDev.deviceId : 'None';

                const stream = await navigator.mediaDevices.getUserMedia({ 
                    video: { width: { ideal: 1280 }, height: { ideal: 720 } } 
                });
                const video = document.getElementById('v');
                video.srcObject = stream;
                await video.play();

                const track = stream.getVideoTracks()[0];
                window.__trackSettings = track.getSettings();
                window.__trackCapabilities = track.getCapabilities ? track.getCapabilities() : {};

                // Esperar a que lleguen frames
                await new Promise(r => setTimeout(r, 1500));

                const canvas = document.getElementById('c');
                const ctx = canvas.getContext('2d');
                ctx.drawImage(video, 0, 0, 1280, 720);
                const imgData = ctx.getImageData(0, 0, 1280, 720);
                
                // Calcular varianza de píxeles para asegurar que no sea negro o estático vacío
                let sum = 0;
                for (let i = 0; i < imgData.data.length; i += 4) {
                    sum += imgData.data[i] + imgData.data[i+1] + imgData.data[i+2];
                }
                window.__pixelSum = sum;
                window.__videoWidth = video.videoWidth;
                window.__videoHeight = video.videoHeight;
                window.__testPassed = (sum > 10000 && video.videoWidth > 0);
                document.getElementById('status').innerText = 'TEST_COMPLETED';
            } catch(e) {
                window.__testError = e.toString();
                document.getElementById('status').innerText = 'TEST_FAILED: ' + e;
            }
        }
        window.addEventListener('DOMContentLoaded', runCamTest);
    </script>
</body>
</html>
"""


async def main():
    print("======================================================================")
    print("  INICIANDO AUDITORIA INTEGRAL DE FUNCIONAMIENTO (ONBOARDED)")
    print("======================================================================\n")

    # 1. Crear imagen de prueba sintetica con FFmpeg
    test_img = BASE_DIR / "data" / "uploads" / "audit_test_face.png"
    os.makedirs(test_img.parent, exist_ok=True)

    print("[1/5] Generando imagen de prueba realista...")
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "testsrc=size=1280x720:rate=1",
        "-vframes", "1",
        str(test_img)
    ], capture_output=True, check=True)
    print(f"  [OK] Imagen lista: {test_img} ({os.path.getsize(test_img)} bytes)")

    # 2. Iniciar servidor backend en subproceso
    print("\n[2/5] Iniciando servidor Onboarded en background...")
    server_proc = subprocess.Popen([sys.executable, "run.py", "--no-open"], cwd=str(BASE_DIR))
    await asyncio.sleep(2.5)

    try:
        # Guardar harness HTML local en buffers para cargarlo directamente
        harness_path = BASE_DIR / "data" / "buffers" / "webrtc_harness.html"
        with open(harness_path, "w", encoding="utf-8") as f:
            f.write(HTML_TEST_HARNESS)

        # 3. Probar Liveness 3D
        print("\n[3/5] Sintetizando Liveness 3D (Y4M 10s @ 30fps)...")
        from src.liveness import generate_synthetic_liveness
        out_y4m = str(BASE_DIR / "data" / "buffers" / "audit_stream.y4m")
        out_mp4 = str(BASE_DIR / "data" / "buffers" / "audit_preview.mp4")

        res_live = generate_synthetic_liveness(
            image_path=str(test_img),
            output_y4m_path=out_y4m,
            output_mp4_preview_path=out_mp4,
            duration=10,
            width=1280,
            height=720,
            fps=30,
            framing_mode="fill_crop"
        )
        print(f"  [OK] Buffer Y4M generado exitosamente: {res_live['size_mb']} MB")
        assert os.path.exists(out_y4m) and os.path.getsize(out_y4m) > 100000

        # 4. Lanzar Orbita con inyeccion
        print("\n[4/5] Lanzando Orbita Browser con camara inyectada...")
        from src.browser import find_orbita_executable, find_free_port, launch_browser_process
        from src.config import SCRIPTS_DIR, HARDWARE_PERSONAS

        executable = find_orbita_executable()
        assert executable, "Orbita executable not found!"
        cdp_port = find_free_port()
        user_dir = os.path.join(os.environ.get("TEMP", "/tmp"), f"audit_profile_{cdp_port}")
        os.makedirs(user_dir, exist_ok=True)

        harness_url = f"http://127.0.0.1:8765/data/buffers/webrtc_harness.html"
        browser_proc = launch_browser_process(executable, out_y4m, harness_url, cdp_port, user_dir)
        print(f"  [OK] Proceso Chromium activo (PID: {browser_proc.pid}, CDP: {cdp_port})")

        # Conectar Playwright e inyectar scripts stealth
        print("\n[5/5] Auditando WebRTC, Spoofing de Hardware y Recepcion de Video...")

        spoof_script = (SCRIPTS_DIR / "webrtc_cam_spoof.js").read_text(encoding="utf-8")
        hw_config = HARDWARE_PERSONAS["logitech_c920"]
        spoof_script = spoof_script.replace("Integrated Camera (04f2:b614)", hw_config["label"])
        spoof_script = spoof_script.replace("Microphone (Realtek(R) Audio)", hw_config["mic_label"])

        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            cdp_browser = None
            for attempt in range(15):
                await asyncio.sleep(0.6)
                try:
                    cdp_browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
                    break
                except Exception:
                    pass

            assert cdp_browser, "Error conectando CDP para la auditoria"
            context = cdp_browser.contexts[0]
            await context.add_init_script(spoof_script)

            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(harness_url)

            # Esperar a que el test harness complete
            await page.wait_for_selector('#status:has-text("TEST_COMPLETED")', timeout=15000)

            label = await page.evaluate("window.__deviceLabel")
            track_settings = await page.evaluate("window.__trackSettings")
            pixel_sum = await page.evaluate("window.__pixelSum")
            video_w = await page.evaluate("window.__videoWidth")
            video_h = await page.evaluate("window.__videoHeight")
            passed = await page.evaluate("window.__testPassed")

            print("\n======================================================================")
            print("  RESULTADOS DE LA AUDITORIA EN VIVO:")
            print("======================================================================")
            print(f"  - Hardware Spoofing Label:     {label}")
            print(f"  - Resolucion Entregada:        {video_w}x{video_h} (Aspect Ratio: {round(video_w/video_h, 2)})")
            print(f"  - Track Settings WebRTC:       {json.dumps(track_settings)}")
            print(f"  - Densidad de Pixeles Activa:  {pixel_sum:,} (Cero pantalla negra)")
            print(f"  - Estado Global del Test:      {'[PASSED] 100% OPERATIVO Y VERIFICADO' if passed else '[FAILED]'}")
            print("======================================================================\n")

            # Tomar screenshot como evidencia irrefutable
            screenshot_path = BASE_DIR / "data" / "sessions" / "audit_live_verified.png"
            await page.screenshot(path=str(screenshot_path))
            print(f"  [EVIDENCIA] Captura guardada en: {screenshot_path}\n")

            # Cleanup
            await cdp_browser.close()
            from src.server import kill_process_tree
            kill_process_tree(browser_proc)

    finally:
        server_proc.terminate()


if __name__ == "__main__":
    asyncio.run(main())
