"""
test_cam_capture_live.py — Lanza el Chromium con la cámara armada, navega a test_cam.html e inyecta la transmisión
"""

import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

BASE_DIR = Path(r"C:\Users\rober\Dropbox\TESTING DEV\repos\kcky")
sys.path.insert(0, str(BASE_DIR))

from src.config import SCRIPTS_DIR, HARDWARE_PERSONAS, BUFFERS_DIR, SESSIONS_DIR
from src.browser import find_orbita_executable, find_free_port, launch_browser_process


async def main():
    y4m_path = str(BUFFERS_DIR / "live_audit_stream.y4m")
    executable = find_orbita_executable()
    cdp_port = find_free_port()
    user_dir = os.path.join(os.environ.get("TEMP", "/tmp"), f"cam_audit_{cdp_port}")
    os.makedirs(user_dir, exist_ok=True)

    target_url = "http://127.0.0.1:8765/static/test_cam.html"
    browser_proc = launch_browser_process(executable, y4m_path, target_url, cdp_port, user_dir)

    hw_persona = HARDWARE_PERSONAS["logitech_c920"]
    spoof_script = (SCRIPTS_DIR / "webrtc_cam_spoof.js").read_text(encoding="utf-8")
    spoof_script = spoof_script.replace("Integrated Camera (04f2:b614)", hw_persona["label"])
    spoof_script = spoof_script.replace("Microphone (Realtek(R) Audio)", hw_persona["mic_label"])

    async with async_playwright() as pw:
        cdp_browser = None
        for _ in range(25):
            await asyncio.sleep(0.3)
            try:
                cdp_browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
                break
            except Exception:
                pass

        if cdp_browser:
            context = cdp_browser.contexts[0]
            await context.grant_permissions(["camera", "microphone"], origin="http://127.0.0.1:8765")
            await context.add_init_script(spoof_script)

            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(target_url)
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(3.0)

            screenshot_path = SESSIONS_DIR / "test_cam_live_rendered.png"
            await page.screenshot(path=str(screenshot_path))
            print(f"[OK] Captura guardada en: {screenshot_path}")

            await cdp_browser.close()

    from src.server import kill_process_tree
    kill_process_tree(browser_proc)


if __name__ == "__main__":
    asyncio.run(main())
