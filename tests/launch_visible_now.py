"""
launch_visible_now.py — Abre Chrome directamente en la pantalla de Robert con la cámara inyectada y el monitor activo
"""

import os
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(r"C:\Users\rober\Dropbox\TESTING DEV\repos\onboarded")
y4m_path = str(BASE_DIR / "data" / "buffers" / "live_audit_stream.y4m")

if not os.path.exists(y4m_path):
    print("Generando buffer de prueba...")
    from src.liveness import generate_synthetic_liveness
    test_img = BASE_DIR / "data" / "uploads" / "audit_test_face.png"
    if not os.path.exists(test_img):
        # Usar cualquier imagen de upload
        uploads = list((BASE_DIR / "data" / "uploads").glob("*.png")) + list((BASE_DIR / "data" / "uploads").glob("*.jpg"))
        test_img = uploads[0] if uploads else str(test_img)

    generate_synthetic_liveness(
        image_path=str(test_img),
        output_y4m_path=y4m_path,
        duration=30,
        width=1280,
        height=720,
        fps=30,
        framing_mode="fill_crop"
    )

chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
temp_profile = os.path.join(os.environ.get("TEMP", r"C:\Windows\Temp"), "onboarded_live_test_profile")
os.makedirs(temp_profile, exist_ok=True)

target_url = "http://127.0.0.1:8765/static/test_cam.html"

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
    target_url
]

print(f"Lanzando Chrome visible en tu pantalla con cámara inyectada...")
proc = subprocess.Popen(cmd)
print(f"[OK] Proceso Chrome lanzado con PID: {proc.pid}")
print(f"Abierto en: {target_url}")
