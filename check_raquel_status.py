"""
check_raquel_status.py — Consulta rápida del estado KYC de RAQUEL LOMELI MENDEZ
Usa el mismo approach que run_karen_kyc_only.py: Chrome visible + CDP + fetch en contexto autenticado.
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

CDP_PORT = 9222
ACCOUNT_EMAIL = "retirobetme.x0.2@gmail.com"
ACCOUNT_PASS = "Kashau2022"


async def check_status():
    print("\n" + "=" * 80)
    print("  🔍 KCKY — VERIFICACIÓN KYC (RAQUEL LOMELI MENDEZ)")
    print(f"  Cuenta: {ACCOUNT_EMAIL}")
    print("=" * 80, flush=True)

    # 1. Matar instancias previas
    subprocess.run("taskkill /F /IM chrome.exe", shell=True, capture_output=True)
    await asyncio.sleep(1.0)

    # 2. Lanzar Chrome en monitor físico
    executable = find_orbita_executable()
    if not executable:
        print("❌ No se encontró Chrome. Abortando.")
        return

    unique_id = int(time.time())
    temp_profile = os.path.join(tempfile.gettempdir(), f"kcky_check_{unique_id}")
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
        '"https://betmexico.mx/"'
    ]

    print(f"[*] Abriendo Chrome en monitor físico (WinSta0\\Default)...", flush=True)
    pid = launch_on_physical_desktop(" ".join(cmd_args))
    print(f"  ✅ Chrome PID: {pid}", flush=True)
    await asyncio.sleep(3.0)

    # 3. Conectar CDP
    async with async_playwright() as pw:
        print("[*] Conectando via CDP...", flush=True)
        browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        page = browser.contexts[0].pages[0]

        # Sniffer de respuestas
        async def on_response(response):
            url = response.url
            if any(ep in url for ep in ["GetStatusFiles", "HasFullValidation", "Users/"]):
                try:
                    res_json = await response.json()
                    t = time.strftime("%H:%M:%S")
                    if "GetStatusFiles" in url:
                        parsed = kyc_monitor.parse_get_status_files(res_json)
                        s = "✅ Aprobada" if parsed["selfie_approved"] else "⏳ En revisión"
                        f = "✅ Aprobado" if parsed["front_approved"] else "⏳ En revisión"
                        b = "✅ Aprobado" if parsed["back_approved"] else "⏳ En revisión"
                        print(f"\n  [{t}] 📄 GetStatusFiles -> Selfie: {s} | Frente: {f} | Reverso: {b}", flush=True)
                    elif "HasFullValidation" in url:
                        parsed = kyc_monitor.parse_has_full_validation(res_json)
                        emoji = "🎉" if parsed["has_full_validation"] else "⏳"
                        print(f"\n  [{t}] {emoji} HasFullValidation -> {parsed['message']} (Val: {parsed['has_full_validation']})", flush=True)
                    elif "Users" in url and "Validate" not in url:
                        parsed = kyc_monitor.parse_users_profile(res_json)
                        print(f"\n  [{t}] 👤 Users -> Titular: '{parsed['full_name']}' | faceStatus: {parsed['face_status']}", flush=True)
                except Exception:
                    pass

        page.on("response", lambda r: asyncio.create_task(on_response(r)))

        # 4. Login
        print(f"[*] Navegando e iniciando sesión con {ACCOUNT_EMAIL}...", flush=True)
        await page.goto("https://betmexico.mx/", timeout=30000)
        await asyncio.sleep(2.5)

        login_btn = await page.query_selector("button:has-text('Ingresar'), a:has-text('Ingresar')")
        if login_btn:
            await login_btn.click()
            await asyncio.sleep(1.5)

        email_inp = await page.query_selector("input[type='email'], input[name*='email' i], input[placeholder*='correo' i], input[name='username'], #email")
        pass_inp = await page.query_selector("input[type='password'], input[name*='pass' i], #password")

        if email_inp and pass_inp:
            print("  - Tecleando credenciales...", flush=True)
            await email_inp.click()
            await email_inp.type(ACCOUNT_EMAIL, delay=25)
            await asyncio.sleep(0.2)
            await pass_inp.click()
            await pass_inp.type(ACCOUNT_PASS, delay=25)
            await asyncio.sleep(0.5)

            submit_login = await page.query_selector("form button[type='submit'], button:has-text('Iniciar sesión'), button:has-text('Ingresar'), form button.btn-primary")
            if submit_login:
                try:
                    await submit_login.click(timeout=5000)
                except Exception:
                    await submit_login.dispatch_event("click")
                print("  ✅ Login enviado.", flush=True)
                await asyncio.sleep(4.0)
        else:
            print("  ⚠️ No se encontraron inputs de login. ¿Ya logueado?", flush=True)

        # 5. Navegar a /user-identification para disparar GetStatusFiles
        print("[*] Navegando a /user-identification ...", flush=True)
        try:
            await page.goto("https://betmexico.mx/user-identification", timeout=30000)
        except Exception:
            pass
        await asyncio.sleep(3.5)

        # 6. Polleo directo de estado
        print("\n" + "=" * 80)
        print("  📡 CONSULTANDO ESTADO DE VERIFICACIÓN BETMEXICO...")
        print("=" * 80, flush=True)

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
                    try {
                        const usr = await fetch('https://betmexico.mx/api/Users/');
                        r.user = await usr.json();
                    } catch(e) { r.user = e.toString(); }
                    return r;
                }""")

                t = time.strftime("%H:%M:%S")

                # Parse StatusFiles
                sf = eval_res.get("statusFiles", {})
                if isinstance(sf, list) or (isinstance(sf, dict) and "error" not in sf):
                    parsed = kyc_monitor.parse_get_status_files(sf)
                    s = "✅" if parsed["selfie_approved"] else "⏳"
                    f = "✅" if parsed["front_approved"] else "⏳"
                    b = "✅" if parsed["back_approved"] else "⏳"
                    print(f"  [{t}] 📄 Selfie: {s} | Frente: {f} | Reverso: {b} | Críticos OK: {parsed['all_critical_approved']}")
                else:
                    print(f"  [{t}] 📄 StatusFiles: {json.dumps(sf, ensure_ascii=False)[:200]}")

                # Parse HasFullValidation
                fv = eval_res.get("fullVal", {})
                if isinstance(fv, dict):
                    parsed_fv = kyc_monitor.parse_has_full_validation(fv)
                    icon = "🎉" if parsed_fv["has_full_validation"] else "⏳"
                    print(f"  [{t}] {icon} FullValidation: {parsed_fv['has_full_validation']} — {parsed_fv.get('message','')}")

                # Parse Users
                usr = eval_res.get("user", {})
                if isinstance(usr, dict) and "data" in usr:
                    parsed_u = kyc_monitor.parse_users_profile(usr)
                    print(f"  [{t}] 👤 {parsed_u['full_name']} | faceStatus: {parsed_u['face_status']}")

            except Exception as e:
                print(f"  [Error poll {i+1}]: {e}")

        # Screenshot final
        shot = BUFFERS_DIR / "raquel_kyc_check.png"
        await page.screenshot(path=str(shot))
        print(f"\n  📸 Screenshot: {shot.name}")

        print("\n" + "=" * 80)
        print("  ✅ VERIFICACIÓN COMPLETADA — Chrome queda abierto para inspección manual")
        print("=" * 80 + "\n", flush=True)


if __name__ == "__main__":
    asyncio.run(check_status())
