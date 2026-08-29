"""
run_karen_kyc_only.py — Ejecución Quirúrgica de KYC Biométrico para Karen Geraldine (Cuenta Existente)
NO crea registros nuevos. Inicia sesión con la cuenta existente y completa el flujo documental y selfie.
"""

import os
import sys
import time
import json
import asyncio
import tempfile
import subprocess
from pathlib import Path
from playwright.async_api import async_playwright

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT.parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from src.config import DATA_DIR, BUFFERS_DIR
from src.browser import find_orbita_executable
from tools.launch_desktop_window import launch_on_physical_desktop
from src.account_automator import kyc_monitor
from src.db import get_db_connection, update_account_status

ID_FOLDER = REPO_ROOT / "data" / "identities" / "KAREN_GERALDINE_DE_LA_CRUZ_ARANA"
FRONT_IMG = str(ID_FOLDER / "inputs" / "front.jpg")
BACK_IMG = str(ID_FOLDER / "inputs" / "back.jpg")
Y4M_STREAM = str(BUFFERS_DIR / "karen_stream_ready.y4m")
MP4_STREAM = str(BUFFERS_DIR / "karen_stream_ready.mp4")

CDP_PORT = 9222

ACCOUNT_EMAIL = "retirobetme.x0.1@gmail.com"
ACCOUNT_PASS = "Kashau2022"

async def run_kyc():
    print("\n" + "="*80)
    print("  👑 KCKY STUDIO — KYC BIOMÉTRICO (CUENTA EXISTENTE / CERO DUPLICADOS)")
    print(f"  Usuario: {ACCOUNT_EMAIL}")
    print(f"  Frente: {Path(FRONT_IMG).name} | Reverso: {Path(BACK_IMG).name}")
    print(f"  Stream Y4M: {Path(Y4M_STREAM).name} / MP4: {Path(MP4_STREAM).name}")
    print("="*80, flush=True)

    # 1. Matar instancias previas de Chrome
    print("[*] Cerrando instancias previas de Chrome...", flush=True)
    subprocess.run("taskkill /F /IM chrome.exe", shell=True, capture_output=True)
    await asyncio.sleep(1.0)

    # 2. Lanzar Chrome SIN flags de fake device (usa OBS Virtual Camera)
    executable = find_orbita_executable()
    unique_id = int(time.time())
    temp_profile = os.path.join(tempfile.gettempdir(), f"kcky_kyc_prof_{unique_id}")
    os.makedirs(temp_profile, exist_ok=True)

    cmd_args = [
        f'"{executable}"',
        f'--remote-debugging-port={CDP_PORT}',
        '--remote-allow-origins=*',
        f'--user-data-dir="{temp_profile}"',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-infobars',
        '--disable-blink-features=AutomationControlled',
        '--disable-background-timer-throttling',
        '--disable-backgrounding-occluded-windows',
        '--disable-renderer-backgrounding',
        '"https://betmexico.mx/"'
    ]

    print(f"[*] Abriendo Chrome en monitor físico (WinSta0\Default)...", flush=True)
    pid = launch_on_physical_desktop(" ".join(cmd_args))
    print(f"  ✅ Chrome PID: {pid}", flush=True)
    await asyncio.sleep(2.5)

    # 3. Conectar Playwright CDP
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        page = browser.contexts[0].pages[0]

        # === PASO 1: INYECCIÓN DE SCRIPTS DE SPOOFING WEBRTC Y STEALTH ===
        print("[*] Inyectando scripts de spoofing WebRTC y evasiones stealth...", flush=True)
        page.add_init_script(path=str(REPO_ROOT / "scripts" / "stealth_evasions.js"))
        page.add_init_script(path=str(REPO_ROOT / "scripts" / "webrtc_cam_spoof.js"))
        page.evaluate("""() => {
            window.__hw_persona = {
                camLabel: 'Logitech HD Pro Webcam C920',
                micLabel: 'Microphone (Realtek(R) Audio)',
                gpu_vendor: 'Google Inc. (AMD)',
                gpu_renderer: 'ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)',
                hardware_concurrency: 8,
                device_memory: 8,
                platform: 'Win32'
            };
        }""")

        async def on_response(response):
            url = response.url
            if any(endpoint in url for endpoint in ["GetStatusFiles", "HasFullValidation", "Users", "AddressAcknowledgment", "Login", "login", "UserDocument"]):
                try:
                    res_json = await response.json()
                    t = time.strftime("%H:%M:%S")
                    if "GetStatusFiles" in url:
                        parsed = kyc_monitor.parse_get_status_files(res_json)
                        s = "✅ Aprobada" if parsed["selfie_approved"] else "⏳ En revisión"
                        f = "✅ Aprobado" if parsed["front_approved"] else "⏳ En revisión"
                        b = "✅ Aprobado" if parsed["back_approved"] else "⏳ En revisión"
                        print(f"\n  [{t}] 📄 [RED] GetStatusFiles -> Selfie: {s} | Frente: {f} | Reverso: {b}", flush=True)
                    elif "HasFullValidation" in url:
                        parsed = kyc_monitor.parse_has_full_validation(res_json)
                        emoji = "🎉" if parsed["has_full_validation"] else "⏳"
                        print(f"\n  [{t}] {emoji} [RED] HasFullValidation -> {parsed['message']} (Val: {parsed['has_full_validation']})", flush=True)
                    elif "Users" in url:
                        parsed = kyc_monitor.parse_users_profile(res_json)
                        print(f"\n  [{t}] 👤 [RED] Users -> Titular: '{parsed['full_name']}' | faceStatus: {parsed['face_status']}", flush=True)
                except Exception:
                    pass

        page.on("response", lambda r: asyncio.create_task(on_response(r)))

        # 4. Iniciar Sesión en BetMexico con eventos reactivos
        print(f"[*] Navegando e iniciando sesión con {ACCOUNT_EMAIL}...", flush=True)
        await page.goto("https://betmexico.mx/", timeout=30000)
        await asyncio.sleep(2.5)

        # Buscar botón Ingresar
        login_btn = await page.query_selector("button:has-text('Ingresar'), a:has-text('Ingresar')")
        if login_btn:
            await login_btn.click()
            await asyncio.sleep(1.5)

        # Llenar modal de login con tecleo reactivo
        email_inp = await page.query_selector("input[type='email'], input[name*='email' i], input[placeholder*='correo' i], input[name='username'], #email")
        pass_inp = await page.query_selector("input[type='password'], input[name*='pass' i], #password")

        if email_inp and pass_inp:
            print("  - Tecleando credenciales de acceso con eventos de teclado...")
            await email_inp.click()
            await email_inp.type(ACCOUNT_EMAIL, delay=25)
            await asyncio.sleep(0.2)
            await pass_inp.click()
            await pass_inp.type(ACCOUNT_PASS, delay=25)
            await asyncio.sleep(0.5)

            # Click en botón de login
            submit_login = await page.query_selector("form button[type='submit'], button:has-text('Iniciar sesión'), button:has-text('Ingresar'), form button.btn-primary")
            if submit_login:
                try:
                    await submit_login.click(timeout=5000)
                except Exception:
                    await submit_login.dispatch_event("click")
                print("  ✅ Login enviado.")
                await asyncio.sleep(4.0)

        # 5. Navegar a /user-identification
        print("[*] Navegando a https://betmexico.mx/user-identification ...", flush=True)
        try:
            await page.goto("https://betmexico.mx/user-identification", timeout=30000)
        except Exception:
            pass
        await asyncio.sleep(3.5)

        shot_portal = BUFFERS_DIR / "karen_kyc_portal_logged.png"
        await page.screenshot(path=str(shot_portal))
        print(f"  📸 Screenshot portal KYC: {shot_portal.name}")

        # 6. Interactuar con el Acordeón de Selfie
        print("\n[*] 🤳 Paso 1: Abriendo sección de Selfie...", flush=True)
        
        # Click en la tarjeta de Selfie
        await page.evaluate("""() => {
            const svg = document.querySelector('svg[name="data-selfie"]');
            if (svg) {
                const row = svg.closest('.cursor-pointer') || svg.closest('div.flex') || svg.parentElement;
                if (row) row.click();
            }
        }""")
        await asyncio.sleep(1.5)

        # Fallback click directo
        selfie_card = await page.query_selector("svg[name='data-selfie'], div.cursor-pointer:has-text('Selfie')")
        if selfie_card:
            await selfie_card.click()
            await asyncio.sleep(2.0)

        shot_selfie_open = BUFFERS_DIR / "karen_kyc_selfie_opened.png"
        await page.screenshot(path=str(shot_selfie_open))
        print(f"  📸 Screenshot Selfie abierta: {shot_selfie_open.name}")

        # Buscar botón de captura de selfie
        capture_btn = await page.query_selector("button:has-text('Tomar foto'), button:has-text('Comenzar'), button:has-text('Capturar'), button:has-text('Continuar'), #take-photo, button.btn-primary")
        if capture_btn and await capture_btn.is_visible():
            print("  - 📷 Disparando captura de cámara (Stream WebRTC OBS)...", flush=True)
            await capture_btn.click()
            await asyncio.sleep(3.0)
            print("  ✅ Selfie capturada.")

            confirm_btn = await page.query_selector("button:has-text('Confirmar'), button:has-text('Enviar foto'), button:has-text('Continuar')")
            if confirm_btn and await confirm_btn.is_visible():
                await confirm_btn.click()
                await asyncio.sleep(3.0)

        # 7. Subida de Frente de Identificación
        print("\n[*] 🪪 Paso 2: Abriendo sección Frente de Identificación...", flush=True)
        await page.evaluate("""() => {
            const allDivs = Array.from(document.querySelectorAll('div, p, span'));
            const frontText = allDivs.find(d => d.textContent.includes('Frente de'));
            if (frontText) {
                const row = frontText.closest('.cursor-pointer') || frontText.closest('div.flex') || frontText;
                row.click();
            }
        }""")
        await asyncio.sleep(2.0)

        file_inputs = await page.query_selector_all("input[type='file']")
        if file_inputs:
            print(f"  - Inyectando Frente ({Path(FRONT_IMG).name})...")
            await file_inputs[0].set_input_files(FRONT_IMG)
            await asyncio.sleep(2.5)

            btn_subir_front = await page.query_selector("button:has-text('Subir'), button:has-text('Continuar'), button:has-text('Confirmar')")
            if btn_subir_front and await btn_subir_front.is_visible():
                await btn_subir_front.click()
                await asyncio.sleep(2.5)

        # 8. Subida de Reverso de Identificación
        print("\n[*] 🪪 Paso 3: Abriendo sección Reverso de Identificación...", flush=True)
        await page.evaluate("""() => {
            const allDivs = Array.from(document.querySelectorAll('div, p, span'));
            const backText = allDivs.find(d => d.textContent.includes('Reverso de'));
            if (backText) {
                const row = backText.closest('.cursor-pointer') || backText.closest('div.flex') || backText;
                row.click();
            }
        }""")
        await asyncio.sleep(2.0)

        file_inputs = await page.query_selector_all("input[type='file']")
        if file_inputs:
            print(f"  - Inyectando Reverso ({Path(BACK_IMG).name})...")
            await file_inputs[-1].set_input_files(BACK_IMG)
            await asyncio.sleep(2.5)

            btn_subir_back = await page.query_selector("button:has-text('Subir'), button:has-text('Continuar'), button:has-text('Confirmar')")
            if btn_subir_back and await btn_subir_back.is_visible():
                await btn_subir_back.click()
                await asyncio.sleep(3.0)

        # 9. Screenshot final y telemetría
        shot_done = BUFFERS_DIR / "karen_kyc_done.png"
        await page.screenshot(path=str(shot_done))
        print(f"\n  📸 Screenshot final: {shot_done.name}")

        # Polleo de validación
        print("\n" + "="*80)
        print("  📡 CONSULTANDO ESTADO FINAL DE VERIFICACIÓN BETMEXICO...")
        print("="*80, flush=True)

        for i in range(5):
            await asyncio.sleep(3.0)
            try:
                eval_res = await page.evaluate("""async () => {
                    const r = {};
                    try {
                        const res = await fetch('https://betmexico.mx/api/UserDocument/GetStatusFiles');
                        r.statusFiles = await res.json();
                    } catch(e) { r.statusFiles = e.toString(); }
                    try {
                        const val = await fetch('https://betmexico.mx/api/Users/Validate/HasFullValidation');
                        r.fullVal = await val.json();
                    } catch(e) { r.fullVal = e.toString(); }
                    return r;
                }""")
                print(f"  [Status {i+1}/5] -> {json.dumps(eval_res, ensure_ascii=False)}")
            except Exception:
                pass

        print("\n" + "="*80)
        print("  🎉 PROCESO KYC FINALIZADO")
        print(f"  - Cuenta: {ACCOUNT_EMAIL}")
        print(f"  - Screenshots: {shot_portal.name}, {shot_selfie_open.name}, {shot_done.name}")
        print("="*80 + "\n", flush=True)

if __name__ == "__main__":
    asyncio.run(run_kyc())
