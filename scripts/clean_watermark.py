"""
scripts/clean_watermark.py — Remueve la marca de agua de Gemini/Veo de los videos base
utilizando Inpainting Telea de alta fidelidad sin recorte destructivo.
"""

import cv2
import os
import sys
import time
import subprocess
from pathlib import Path
import numpy as np

def clean_watermark(input_path: str, output_path: str):
    if not os.path.exists(input_path):
        print(f"Error: {input_path} no existe")
        return False
        
    cap = cv2.VideoCapture(input_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    temp_raw = output_path + ".temp.mp4"
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(temp_raw, fourcc, fps, (w, h))
    
    # Máscara quirúrgica para la marca de agua de Gemini en la esquina inferior derecha
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[575:635, 1130:1195] = 255
    
    t0 = time.time()
    count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        inpainted = cv2.inpaint(frame, mask, inpaintRadius=7, flags=cv2.INPAINT_TELEA)
        out.write(inpainted)
        count += 1
        
    cap.release()
    out.release()
    
    # Remuxing con FFmpeg a H.264 CRF 17 (Calidad visual transparente sin pérdida)
    cmd = [
        "ffmpeg", "-y",
        "-i", temp_raw,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "17",
        output_path
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    if os.path.exists(temp_raw):
        os.remove(temp_raw)
        
    elapsed = time.time() - t0
    size_mb = os.path.getsize(output_path) / (1024 * 1024) if os.path.exists(output_path) else 0
    print(f"[OK] Video limpiado ({count} frames en {elapsed:.1f}s): {output_path} [{size_mb:.2f} MB]")
    return True

if __name__ == "__main__":
    v1 = r"C:\Users\rober\Downloads\sube_la_camara_un_mas_que.mp4"
    v2 = r"C:\Users\rober\Downloads\cambia_a_la_persona_de_la_imag.mp4"
    
    clean_watermark(v1, "data/presets/female_clean_kyc_base.mp4") # Reemplaza el preset principal con el mejor video sin lentes ni marca
    clean_watermark(v1, "data/presets/female_kyc_subecam_clean.mp4")
    clean_watermark(v2, "data/presets/female_kyc_cambia_clean.mp4")
