"""
launch_visible_now.py — Abre Chrome directamente en el monitor de Robert con la cámara inyectada
"""

import os
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(r"C:\Users\rober\Dropbox\TESTING DEV\repos\onboarded")
y4m_path = str(BASE_DIR / "data" / "buffers" / "live_audit_stream.y4m")

if not os.path.exists(y4m_path):
    print("Generando buffer rapido...")
    from src.liveness import generate_synthetic_liveness
    test_img = BASE_DIR / "data" / "uploads" / "audit_test_face.png"
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
temp_profile = os.path.join(os.environ.get("TEMP", r"C:\Windows\Temp"), "onboarded_demo_profile")
os.makedirs(temp_profile, exist_ok=True)

target_url = "https://webcamtests.com/"

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

print(f"Lanzando Chrome visible con camara inyectada...")
proc = subprocess.Popen(cmd)
print(f"[OK] Proceso Chrome lanzado con PID: {proc.pid}")
