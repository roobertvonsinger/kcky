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

logger = logging.getLogger("Onboarded_Browser")


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
    cmd_args = [
        executable_path,
        f"--remote-debugging-port={cdp_port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
        f"--use-file-for-fake-video-capture={os.path.abspath(y4m_path)}",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        target_url
    ]

    return subprocess.Popen(cmd_args)


async def attach_cdp_stealth_session(
    cdp_port: int,
    hardware_persona: str = "logitech_c920",
    event_callback: Optional[Callable[[str, Any], Any]] = None,
    log_callback: Optional[Callable[[str, str], Any]] = None
) -> None:
    """Conecta Playwright sobre CDP con reintentos e inyecta los scripts de evasión y sniffer."""
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
                def on_console(msg):
                    text = msg.text
                    if "[KYC_SNIFFER_EVENT]" in text:
                        try:
                            raw_json = text.split("[KYC_SNIFFER_EVENT]")[1].strip()
                            data = json.loads(raw_json)
                            if event_callback:
                                asyncio.create_task(event_callback(data.get("type", "EVENT"), data))
                        except Exception:
                            pass

                p.on("console", on_console)

            # Escuchar en todas las páginas abiertas actuales
            for p in context.pages:
                attach_page_listeners(p)

            # Escuchar en nuevas pestañas o popups generados por el flujo de onboarding
            context.on("page", lambda new_page: attach_page_listeners(new_page))

            if log_callback:
                await log_callback("🛡️ WebRTC Stealth Spoofing & KYC Sniffer activos en todas las pestañas.", "success")

            while browser.is_connected():
                await asyncio.sleep(1)

    except Exception as e:
        logger.warning(f"Sesión CDP terminada: {e}")
