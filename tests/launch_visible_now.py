"""
launch_visible_now.py — Abre Chrome directamente en la pantalla de Robert con la cámara inyectada y el monitor activo
"""

import os
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

y4m_path = str(BASE_DIR / "data" / "buffers" / "live_audit_stream.y4m")

if not os.path.exists(y4m_path):
    print("Generando buffer de prueba...")
    from src.liveness import generate_synthetic_liveness
    test_img = BASE_DIR / "data" / "uploads" / "audit_test_face.png"
    if not os.path.exists(test_img):
        uploads = list((BASE_DIR / "data" / "uploads").glob("*.png")) + list((BASE_DIR / "data" / "uploads").glob("*.jpg"))
        test_img = uploads[0] if uploads else str(test_img)

    generate_synthetic_liveness(
        image_path=str(test_img),
        output_y4m_path=y4m_path,
        duration=60,
        width=1280,
        height=720,
        fps=30,
        framing_mode="fill_crop"
    )

chrome_candidates = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
]
chrome_path = next((p for p in chrome_candidates if os.path.isfile(p)), "chrome.exe")

temp_profile = os.path.join(os.environ.get("TEMP", r"C:\Windows\Temp"), "kcky_live_test_profile")
os.makedirs(temp_profile, exist_ok=True)

target_url = "http://127.0.0.1:8765"

cmd = [
    chrome_path,
    f"--user-data-dir={temp_profile}",
    "--no-first-run",
    "--no-default-browser-check",
    "--use-fake-ui-for-media-stream",
    "--use-fake-device-for-media-stream",
    f"--use-file-for-fake-video-capture={y4m_path}",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    f"--app={target_url}"
]

print(f"Lanzando Chrome visible en tu pantalla con cámara inyectada y KCKY Studio...")
proc = subprocess.Popen(cmd)
print(f"[OK] Proceso Chrome lanzado con PID: {proc.pid}")
print(f"Abierto en: {target_url}")
