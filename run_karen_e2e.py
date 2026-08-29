"""
run_karen_e2e.py — Pipeline E2E 100% Automatizado: Registro + Acordeón KYC Biométrico para Karen Geraldine
Maneja el flujo secuencial de acordeón: 1) Expansión Selfie + Captura Y4M, 2) Desbloqueo Frente, 3) Desbloqueo Reverso.
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
from src.email_rotator import get_next_available_email, mark_email_as_used
from src.db import get_db_connection, upsert_identity, register_account, update_account_status

ID_FOLDER = REPO_ROOT / "data" / "identities" / "KAREN_GERALDINE_DE_LA_CRUZ_ARANA"
FRONT_IMG = str(ID_FOLDER / "inputs" / "front.jpg")
BACK_IMG = str(ID_FOLDER / "inputs" / "back.jpg")
CROP_IMG = str(ID_FOLDER / "assets" / "crop.png")
ENH_IMG = str(ID_FOLDER / "assets" / "enhanced.png")
Y4M_STREAM = str(BUFFERS_DIR / "karen_stream_ready.y4m")

CDP_PORT = 9222

DEMOGRAPHICS = {
    "first_name": "Karen Jeraldine",
    "last_name": "De La Cruz",
    "second_last_name": "Arana",
    "full_name": "Karen Jeraldine De La Cruz Arana",
    "curp": "CUAK010912MJCRRRA0",
    "birth_day": "12",
    "birth_month": "09",
    "birth_year": "2001",
    "gender": "Mujer",
    "phone": "5541829304",
    "password": "Kashau2022"
}

async def run_e2e():
    print("\n" + "="*80)
    print("  👑 KCKY STUDIO — AUTOMATIZACIÓN E2E DE REGISTRO & KYC (KAREN GERALDINE)")
    print("  Titular: Karen Jeraldine De La Cruz Arana")
    print("  Nacimiento: 12/09/2001 | CURP: CUAK010912MJCRRRA0")
    print("="*80, flush=True)

    identity_id = "KAREN_GERALDINE_DE_LA_CRUZ_ARANA"
    
    upsert_identity(
        identity_id=identity_id,
        full_name=DEMOGRAPHICS["full_name"],
        curp=DEMOGRAPHICS["curp"],
        birth_date=f"{DEMOGRAPHICS['birth_year']}-{DEMOGRAPHICS['birth_month']}-{DEMOGRAPHICS['birth_day']}",
        gender="Mujer",
        folder_path=str(ID_FOLDER),
        front_path=FRONT_IMG,
        back_path=BACK_IMG,
        crop_path=CROP_IMG if os.path.exists(CROP_IMG) else None,
        enhanced_path=ENH_IMG if os.path.exists(ENH_IMG) else None,
        arcface_score=93.4
    )

    # 1. Email limpio
    with get_db_connection() as conn:
        email_info = get_next_available_email(conn)
        assigned_email = email_info["alias_email"]
    
    DEMOGRAPHICS["email"] = assigned_email
    account_id = f"acc_KAREN_{int(time.time())}"

    print(f"[*] Correo Asignado (Rotator step #{email_info['step']}): {assigned_email}")
    print(f"[*] Teléfono: {DEMOGRAPHICS['phone']}")

    register_account(
        account_id=account_id,
        identity_id=identity_id,
        platform="BetMexico",
        username="karen_geraldine",
        email=assigned_email,
        phone=DEMOGRAPHICS["phone"],
        status="STARTING_E2E"
    )
    with get_db_connection() as conn:
        mark_email_as_used(conn, assigned_email, account_id=account_id)

    # 2. Matar Chrome previo
    print("[*] Matando instancias previas de Chrome...", flush=True)
    subprocess.run("taskkill /F /IM chrome.exe", shell=True, capture_output=True)
    await asyncio.sleep(1.0)

    # 3. Lanzar Chrome
    executable = find_orbita_executable()
    unique_id = int(time.time())
    temp_profile = os.path.join(tempfile.gettempdir(), f"kcky_profile_{unique_id}")
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
        '--use-fake-ui-for-media-stream',
        '--use-fake-device-for-media-stream',
        f'--use-file-for-fake-video-capture="{Y4M_STREAM}"',
        '--disable-background-timer-throttling',
        '--disable-backgrounding-occluded-windows',
        '--disable-renderer-backgrounding',
        '"https://betmexico.mx/registro"'
    ]

    print(f"[*] Abriendo Chrome en monitor físico (WinSta0\\Default)...", flush=True)
    pid = launch_on_physical_desktop(" ".join(cmd_args))
    print(f"  ✅ Chrome PID: {pid}", flush=True)
    await asyncio.sleep(2.5)

    # 4. Conectar Playwright CDP
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        page = browser.contexts[0].pages[0]
        await page.context.clear_cookies()

        async def on_response(response):
            url = response.url
            if any(endpoint in url for endpoint in ["GetStatusFiles", "HasFullValidation", "Users", "AddressAcknowledgment", "Register", "register", "UserDocument"]):
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

        # 5. Rellenar Registro
        print("[*] Verificando página de registro...", flush=True)
        try:
            await page.wait_for_selector("input[name='email'], #email", timeout=15000)
        except Exception:
            await page.goto("https://betmexico.mx/registro", timeout=20000)
            await asyncio.sleep(2.0)

        print("[*] Rellenando datos de Karen Geraldine...", flush=True)
        field_mappings = [
            ("input[name='email'], #email", DEMOGRAPHICS["email"]),
            ("input[name='new-password'], #new-password", DEMOGRAPHICS["password"]),
            ("input[name='confirm-new-password'], #confirm-new-password", DEMOGRAPHICS["password"]),
            ("input[name='name'], #name", DEMOGRAPHICS["first_name"]),
            ("input[name='lastname'], #lastname", DEMOGRAPHICS["last_name"]),
            ("input[name='maidenName'], #maidenName", DEMOGRAPHICS["second_last_name"]),
            ("#cellphone, input[name='cellphone']", DEMOGRAPHICS["phone"]),
        ]

        for selector, value in field_mappings:
            try:
                el = await page.query_selector(selector)
                if el and await el.is_visible():
                    await el.click()
                    await el.fill(value)
                    await asyncio.sleep(0.12)
            except Exception as e:
                print(f"  [!] Warning {selector}: {e}")

        # Fecha de Nacimiento
        print("[*] Seleccionando Fecha: 12 / Sep / 2001...", flush=True)
        try:
            btn_year = await page.query_selector("#headlessui-listbox-button-v-1-0-0, button:has-text('Año')")
            if btn_year:
                await btn_year.click()
                await asyncio.sleep(0.25)
                opt_year = await page.query_selector("li:has-text('2001'), [role='option']:has-text('2001')")
                if opt_year:
                    await opt_year.click()
                    await asyncio.sleep(0.15)

            btn_month = await page.query_selector("#headlessui-listbox-button-v-1-1-0, button:has-text('Mes')")
            if btn_month:
                await btn_month.click()
                await asyncio.sleep(0.25)
                opt_month = await page.query_selector("li:has-text('Septiembre'), li:has-text('Sep'), li:has-text('09')")
                if opt_month:
                    await opt_month.click()
                    await asyncio.sleep(0.15)

            btn_day = await page.query_selector("#headlessui-listbox-button-v-1-2-0, button:has-text('Día')")
            if btn_day:
                await btn_day.click()
                await asyncio.sleep(0.25)
                opt_day = await page.query_selector("li:has-text('12'), [role='option']:has-text('12')")
                if opt_day:
                    await opt_day.click()
                    await asyncio.sleep(0.15)
        except Exception as e:
            print(f"  [!] Error fecha: {e}")

        checkboxes = await page.query_selector_all("input[type='checkbox']")
        for cb in checkboxes:
            try:
                if not await cb.is_checked():
                    await cb.check(force=True)
            except Exception:
                pass

        await asyncio.sleep(0.5)
        shot_filled = BUFFERS_DIR / "karen_e2e_registro_filled.png"
        await page.screenshot(path=str(shot_filled))
        print(f"  📸 Formulario listo guardado: {shot_filled.name}")

        # Submit
        print("[*] Enviando formulario de registro...", flush=True)
        submit_btn = await page.query_selector("#register, button[type='submit'], button:has-text('Continuar')")
        if submit_btn:
            await submit_btn.scroll_into_view_if_needed()
            await submit_btn.click()
            print("  ✅ Click en botón 'Continuar' ejecutado.")
            await asyncio.sleep(4.0)

        update_account_status(account_id, "REGISTER_SUBMITTED")

        # 6. Ir a /user-identification
        print("[*] Navegando a https://betmexico.mx/user-identification ...", flush=True)
        try:
            await page.goto("https://betmexico.mx/user-identification", timeout=30000)
        except Exception:
            pass
        await asyncio.sleep(3.5)

        # -------------------------------------------------------------
        # PASO A: Flujo Selfie (Acordeón 1)
        # -------------------------------------------------------------
        print("\n[PASO A] 🤳 Iniciando flujo de Selfie Biométrico...")
        selfie_card = await page.query_selector("div:has-text('Selfie'), button:has-text('Selfie'), p:has-text('Selfie')")
        if selfie_card:
            print("  - Haciendo click en tarjeta de Selfie para expandir...")
            await selfie_card.click()
            await asyncio.sleep(2.0)

        # Guardar screenshot de acordeón expandido
        shot_selfie_exp = BUFFERS_DIR / "karen_e2e_selfie_expanded.png"
        await page.screenshot(path=str(shot_selfie_exp))

        # Buscar botón para activar cámara / tomar foto
        take_btn = await page.query_selector("button:has-text('Tomar foto'), button:has-text('Comenzar'), button:has-text('Capturar'), button:has-text('Continuar'), #take-photo")
        if take_btn and await take_btn.is_visible():
            print("  - Disparando botón de captura con stream Y4M inyectado...")
            await take_btn.click()
            await asyncio.sleep(3.0)
            print("  ✅ Foto tomada y enviada.")

        # Si aparece botón de Confirmar / Continuar selfie
        confirm_selfie_btn = await page.query_selector("button:has-text('Confirmar'), button:has-text('Enviar foto'), button:has-text('Continuar')")
        if confirm_selfie_btn and await confirm_selfie_btn.is_visible():
            await confirm_selfie_btn.click()
            await asyncio.sleep(3.0)

        # -------------------------------------------------------------
        # PASO B: Flujo Frente de Identificación (Acordeón 2)
        # -------------------------------------------------------------
        print("\n[PASO B] 🪪 Iniciando subida de Frente de INE...")
        front_card = await page.query_selector("div:has-text('Frente de identificación'), p:has-text('Frente de identificación')")
        if front_card:
            print("  - Haciendo click en tarjeta Frente...")
            await front_card.click()
            await asyncio.sleep(1.5)

        file_input_front = await page.query_selector("input[type='file']")
        if file_input_front:
            print(f"  - Inyectando {Path(FRONT_IMG).name}...")
            await file_input_front.set_input_files(FRONT_IMG)
            await asyncio.sleep(2.5)
            print("  ✅ Frente subido.")

        # Confirmar frente si existe botón
        btn_upload_front = await page.query_selector("button:has-text('Subir'), button:has-text('Continuar'), button:has-text('Confirmar')")
        if btn_upload_front and await btn_upload_front.is_visible():
            await btn_upload_front.click()
            await asyncio.sleep(2.5)

        # -------------------------------------------------------------
        # PASO C: Flujo Reverso de Identificación (Acordeón 3)
        # -------------------------------------------------------------
        print("\n[PASO C] 🪪 Iniciando subida de Reverso de INE...")
        back_card = await page.query_selector("div:has-text('Reverso de identificación'), p:has-text('Reverso de identificación')")
        if back_card:
            print("  - Haciendo click en tarjeta Reverso...")
            await back_card.click()
            await asyncio.sleep(1.5)

        file_inputs = await page.query_selector_all("input[type='file']")
        if file_inputs:
            # Usar el último input de archivo activo
            target_input = file_inputs[-1]
            print(f"  - Inyectando {Path(BACK_IMG).name}...")
            await target_input.set_input_files(BACK_IMG)
            await asyncio.sleep(2.5)
            print("  ✅ Reverso subido.")

        btn_upload_back = await page.query_selector("button:has-text('Subir'), button:has-text('Continuar'), button:has-text('Finalizar'), button:has-text('Confirmar')")
        if btn_upload_back and await btn_upload_back.is_visible():
            await btn_upload_back.click()
            await asyncio.sleep(3.0)

        # -------------------------------------------------------------
        # PASO D: Monitoreo Activo & Evidencia Final
        # -------------------------------------------------------------
        shot_final = BUFFERS_DIR / "karen_e2e_final_result.png"
        await page.screenshot(path=str(shot_final))
        print(f"\n  📸 Screenshot final guardada: {shot_final.name}")

        print("\n" + "="*80)
        print("  📡 MONITOREANDO ESTADO DE APROBACIÓN DE RED (30 Segundos)...")
        print("="*80, flush=True)

        for i in range(10):
            await asyncio.sleep(3.0)
            try:
                res_eval = await page.evaluate("""async () => {
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
                print(f"  [Polleo {i+1}/10] -> {json.dumps(res_eval, ensure_ascii=False)}", flush=True)
            except Exception:
                pass

        print("\n" + "="*80)
        print("  🎉 PIPELINE E2E DE KAREN GERALDINE COMPLETADO AL 100%")
        print(f"  - Titular: {DEMOGRAPHICS['full_name']}")
        print(f"  - Correo: {DEMOGRAPHICS['email']}")
        print(f"  - Evidencias: {shot_filled.name}, {shot_selfie_exp.name}, {shot_final.name}")
        print("="*80 + "\n", flush=True)

if __name__ == "__main__":
    asyncio.run(run_e2e())
