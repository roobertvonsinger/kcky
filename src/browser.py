"""
browser.py — Orquestador de Orbita / GoLogin Browser, Inyección WebRTC y CDP Bridge
"""

import asyncio
import json
import logging
import os
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable

from src.config import SCRIPTS_DIR, HARDWARE_PERSONAS

logger = logging.getLogger("KCKY_Browser")


def find_free_port() -> int:
    """Encuentra un puerto TCP libre disponible en localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def find_orbita_executable() -> Optional[str]:
    """Busca el ejecutable de Google Chrome u Orbita en el sistema en <1ms."""
    # 1. Google Chrome del sistema (estable, nativo, sin restricciones de perfil)
    for p in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe")
    ]:
        if os.path.isfile(p):
            return p

    sys_chrome = shutil.which("chrome") or shutil.which("google-chrome")
    if sys_chrome:
        return sys_chrome

    home = Path.home()
    # 2. Directorio principal de GoLogin Orbita
    primary_dir = home / ".gologin" / "browser"
    if primary_dir.is_dir():
        try:
            subdirs = [d for d in os.listdir(primary_dir) if d.startswith("orbita-browser-") and not d.endswith(".zip")]
            subdirs.sort(reverse=True)
            for d in subdirs:
                p = primary_dir / d / "chrome.exe"
                if p.is_file():
                    return str(p)
        except Exception:
            pass

    return None


def get_cached_gologin_profiles() -> List[Dict[str, Any]]:
    """Obtiene la lista de perfiles de GoLogin cacheados en el equipo local."""
    home = Path.home()
    profiles_dir = home / ".gologin" / "gologin-cached-profiles"
    results = [
        {"id": "temporary_clean_profile", "name": "Perfil Limpio Temporal (Recomendado)", "is_temp": True}
    ]

    if profiles_dir.is_dir():
        for entry in os.listdir(profiles_dir):
            full_path = profiles_dir / entry
            if full_path.is_dir():
                name = entry
                pref_file = full_path / "Default" / "Preferences"
                if pref_file.is_file():
                    try:
                        with open(pref_file, "r", encoding="utf-8", errors="ignore") as f:
                            prefs = json.load(f)
                            if "gologin" in prefs and "name" in prefs["gologin"]:
                                name = prefs["gologin"]["name"]
                    except Exception:
                        pass
                results.append({"id": entry, "name": f"GoLogin: {name}", "path": str(full_path), "is_temp": False})

    return results


def launch_browser_process(
    executable_path: str,
    y4m_path: str,
    target_url: str,
    cdp_port: int,
    user_data_dir: str
) -> subprocess.Popen:
    """Lanza el proceso de Chromium con flags de cámara y anti-throttling."""
    import tempfile
    import shutil

    # Chromium falla al parsear flags si la ruta del video tiene espacios (p. ej. 'TESTING DEV')
    clean_y4m = os.path.abspath(y4m_path)
    if " " in clean_y4m:
        temp_y4m = os.path.join(tempfile.gettempdir(), "kcky_stream.y4m")
        shutil.copy2(clean_y4m, temp_y4m)
        clean_y4m = temp_y4m

    cmd_args = [
        executable_path,
        f"--remote-debugging-port={cdp_port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
        f"--use-file-for-fake-video-capture={clean_y4m}",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        target_url
    ]

    return subprocess.Popen(cmd_args)


from src.config import SCRIPTS_DIR, HARDWARE_PERSONAS, IDENTITIES_DIR

async def attach_cdp_stealth_session(
    cdp_port: int,
    hardware_persona: str = "logitech_c920",
    identity_id: Optional[str] = None,
    account_id: Optional[str] = None,
    event_callback: Optional[Callable[[str, Any], Any]] = None,
    log_callback: Optional[Callable[[str, str], Any]] = None
) -> None:
    """Conecta Playwright sobre CDP con reintentos e inyecta evasión, sniffer y auto-inyección de documentos."""
    from src.account_automator import automator

    spoof_script_path = SCRIPTS_DIR / "webrtc_cam_spoof.js"
    sniffer_script_path = SCRIPTS_DIR / "kyc_sniffer.js"

    spoof_code = ""
    if spoof_script_path.is_file():
        with open(spoof_script_path, "r", encoding="utf-8") as f:
            spoof_code = f.read()
            hw_config = HARDWARE_PERSONAS.get(hardware_persona, HARDWARE_PERSONAS["logitech_c920"])
            spoof_code = spoof_code.replace("Integrated Camera (04f2:b614)", hw_config["label"])
            spoof_code = spoof_code.replace("Microphone (Realtek(R) Audio)", hw_config["mic_label"])

    sniffer_code = ""
    if sniffer_script_path.is_file():
        with open(sniffer_script_path, "r", encoding="utf-8") as f:
            sniffer_code = f.read()

    identity_folder = str(IDENTITIES_DIR / identity_id) if identity_id and (IDENTITIES_DIR / identity_id).is_dir() else None

    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = None
            # Bucle de reintentos para dar tiempo a que Chromium abra el puerto CDP
            for attempt in range(12):
                await asyncio.sleep(0.5)
                try:
                    browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
                    break
                except Exception:
                    if attempt == 11:
                        raise

            if not browser:
                raise ConnectionError("No fue posible conectar con el puerto CDP de Chromium.")

            if log_callback:
                await log_callback(f"Conectado a CDP en puerto :{cdp_port}.", "info")

            contexts = browser.contexts
            context = contexts[0] if contexts else await browser.new_context()

            # Preload scripts stealth para cualquier nueva página / iframe
            if spoof_code:
                await context.add_init_script(spoof_code)
            if sniffer_code:
                await context.add_init_script(sniffer_code)

            def attach_page_listeners(p):
                # 1. File Chooser interceptor para diálogos nativos de subida de archivos
                if identity_folder:
                    p.on("filechooser", lambda fc: asyncio.create_task(
                        automator.handle_file_chooser(fc, identity_folder, account_id, log_callback)
                    ))

                # 2. Interceptor de consola y eventos de telemetría
                def on_console(msg):
                    text = msg.text
                    if "[KYC_SNIFFER_EVENT]" in text:
                        try:
                            raw_json = text.split("[KYC_SNIFFER_EVENT]")[1].strip()
                            data = json.loads(raw_json)
                            event_type = data.get("type", "EVENT")
                            
                            if event_callback:
                                asyncio.create_task(event_callback(event_type, data))
                                
                            # Si se detectan inputs de archivo, disparar auto-upload inmediatamente
                            if event_type == "KYC_FILE_INPUT_DETECTED" and identity_folder:
                                asyncio.create_task(
                                    automator.auto_upload_kyc_documents_cdp(p, identity_folder, account_id, log_callback)
                                )
                        except Exception:
                            pass

                p.on("console", on_console)

            # Escuchar en todas las páginas abiertas actuales
            for p in context.pages:
                attach_page_listeners(p)

            # Escuchar en nuevas pestañas o popups generados por el flujo de onboarding
            context.on("page", lambda new_page: attach_page_listeners(new_page))

            if log_callback:
                await log_callback("🛡️ WebRTC Stealth Spoofing, KYC Sniffer & CDP Document Injector activos.", "success")

            while browser.is_connected():
                await asyncio.sleep(1)

    except Exception as e:
        logger.warning(f"Sesión CDP terminada: {e}")


async def inject_documents_to_active_browser(
    cdp_port: int,
    identity_folder: str,
    account_id: Optional[str] = None
) -> Dict[str, Any]:
    """Inyecta directamente los documentos de una identidad a la sesión de navegador CDP activa."""
    from src.account_automator import automator
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
        contexts = browser.contexts
        if not contexts or not contexts[0].pages:
            return {"status": "error", "message": "No hay páginas activas en el navegador."}
            
        page = contexts[0].pages[0]
        res = await automator.auto_upload_kyc_documents_cdp(page, identity_folder, account_id)
        return res
