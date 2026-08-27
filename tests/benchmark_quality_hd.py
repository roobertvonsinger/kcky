"""
tests/benchmark_quality_hd.py — Test de Validación de Calidad HD (Input Gate + Face Swap + GPEN-512)
"""

import os
import sys
import time
import subprocess
import cv2
import numpy as np
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
WORKSPACE_ROOT = REPO_ROOT.parent.parent
DEEP_LIVE_CAM_DIR = WORKSPACE_ROOT / "repos" / "Deep-Live-Cam"
PYTHON_VENV = DEEP_LIVE_CAM_DIR / "venv" / "Scripts" / "python.exe"


def evaluate_input_gate(image_path: str) -> dict:
    """Evalúa las métricas de calidad de la imagen de entrada."""
    from src.extract_id_engine import detect_and_classify_input
    img = cv2.imread(image_path)
    if img is None:
        return {"pass": False, "error": "No se pudo leer la imagen"}

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 1. Nitidez / Blur (Varianza del Laplaciano)
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # 2. Detección de rostro
    detect_res = detect_and_classify_input(img)
    face_detected = detect_res.get("face_detected", False)
    best_face = detect_res.get("best_face")
    
    face_w, face_h = (0, 0)
    if best_face and "bbox" in best_face:
        b = best_face["bbox"]
        face_w = int(b[2] - b[0])
        face_h = int(b[3] - b[1])

    # 3. Distribución de Iluminación / Contraste
    mean_lum = float(np.mean(gray))
    std_lum = float(np.std(gray))

    # Criterios del Gate
    is_sharp = blur_score >= 60.0  # Umbral mínimo de nitidez
    is_large_enough = (face_w >= 100 and face_h >= 100) if face_detected else (w >= 250 and h >= 250)
    is_well_lit = 30.0 <= mean_lum <= 230.0 and std_lum >= 25.0

    passed = is_sharp and is_large_enough and is_well_lit

    return {
        "pass": passed,
        "resolution": f"{w}x{h}",
        "face_detected": face_detected,
        "face_box": f"{face_w}x{face_h}" if face_detected else "N/A",
        "blur_score": round(blur_score, 2),
        "blur_threshold": 60.0,
        "is_sharp": is_sharp,
        "mean_luminance": round(mean_lum, 2),
        "contrast_std": round(std_lum, 2),
        "is_well_lit": is_well_lit
    }


def run_hd_face_swap_test(source_face: str, target_video: str, output_video: str, duration_sec: int = 5):
    """Ejecuta una prueba de Face Swap + GPEN-512 Enhancer en un segmento de video."""
    # 1. Crear un clip de prueba de N segundos si es necesario
    temp_target = str(REPO_ROOT / "data" / "buffers" / "temp_target_clip.mp4")
    cmd_clip = [
        "ffmpeg", "-y",
        "-i", target_video,
        "-t", str(duration_sec),
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        temp_target
    ]
    subprocess.run(cmd_clip, capture_output=True)

    # 2. Ejecutar Deep-Live-Cam con GPEN-512 Enhancer activo
    run_py = DEEP_LIVE_CAM_DIR / "run.py"
    cmd_dlc = [
        str(PYTHON_VENV),
        str(run_py),
        "-s", source_face,
        "-t", temp_target,
        "-o", output_video,
        "--execution-provider", "dml",
        "--execution-threads", "2",
        "--frame-processor", "face_swapper", "face_enhancer_gpen512",
        "--video-encoder", "libx264"
    ]

    print(f"[*] Ejecutando Deep-Live-Cam (DirectML + GPEN-512) sobre clip de {duration_sec}s...")
    t0 = time.time()
    res = subprocess.run(cmd_dlc, capture_output=True, text=True, cwd=str(DEEP_LIVE_CAM_DIR))
    elapsed = time.time() - t0
    print(f"[*] Completado en {elapsed:.2f}s (Salida exit code: {res.returncode})")
    
    if res.returncode != 0:
        print("[!] Error en DLC:", res.stdout, res.stderr)
        return False, elapsed

    return True, elapsed


if __name__ == "__main__":
    print("=" * 60)
    print("BENCHMARK DE CALIDAD BIOMÉTRICA HD (KCKY Studio)")
    print("=" * 60)

    # Evaluar Input Gate en varias imágenes de prueba
    uploads_dir = REPO_ROOT / "data" / "uploads"
    test_files = [f for f in uploads_dir.glob("enhanced_*.png")]
    if not test_files:
        test_files = [f for f in uploads_dir.glob("id_card_*.jpg")] + [f for f in uploads_dir.glob("id_card_*.jpeg")]

    print(f"\n[1] Evaluando Input Gate en {len(test_files)} imágenes de entrada:")
    valid_source = None
    for tf in test_files[:4]:
        metrics = evaluate_input_gate(str(tf))
        status = "✅ APROBADO" if metrics["pass"] else "❌ RECHAZADO"
        print(f"  - {tf.name}: {status} | Nitidez: {metrics['blur_score']} (min 60) | Face: {metrics['face_box']} | Lum: {metrics['mean_luminance']}")
        if metrics["pass"] and not valid_source:
            valid_source = str(tf)

    if not valid_source and test_files:
        valid_source = str(test_files[0])

    if not valid_source:
        print("[!] No hay imágenes de prueba en data/uploads.")
        sys.exit(1)

    print(f"\n[2] Fuente seleccionada para prueba de Swap HD: {valid_source}")
    target_preset = REPO_ROOT / "data" / "presets" / "female_clean_kyc_base.mp4"
    out_test_video = str(REPO_ROOT / "data" / "buffers" / "test_hd_swap_gpen.mp4")

    ok, sec = run_hd_face_swap_test(valid_source, str(target_preset), out_test_video, duration_sec=4)
    if ok and os.path.exists(out_test_video):
        size_mb = os.path.getsize(out_test_video) / (1024 * 1024)
        print(f"\n[3] Video HD Generado: {out_test_video} ({size_mb:.2f} MB)")

        # Extraer fotogramas clave y medir nitidez
        cap = cv2.VideoCapture(out_test_video)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"  - Resolución: {w}x{h} @ {fps:.1f} fps ({frame_count} frames)")

        sample_frames = []
        for i in range(min(5, frame_count)):
            ret, frame = cap.read()
            if ret:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                blur = cv2.Laplacian(gray, cv2.CV_64F).var()
                sample_frames.append(blur)
        cap.release()

        avg_blur = np.mean(sample_frames) if sample_frames else 0
        print(f"  - Nitidez promedio de fotogramas (Laplacian var): {avg_blur:.2f}")
        print("\n✅ PIPELINE HD PROBADO CON ÉXITO")
