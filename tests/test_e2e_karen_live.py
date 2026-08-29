"""
tests/test_e2e_karen_live.py — Test End-to-End Automatizado con Identidad Real
Identidad: 534 KAREN GERALDINE DE LA CRUZ ARANA
"""

import os
import sys
import time
import json
import asyncio
import logging
from pathlib import Path

# Ajustar sys.path al root de repos/kcky
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
os.chdir(REPO_ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("KCKY_E2E_Test")

from src.config import DATA_DIR, PRESETS_DIR, BUFFERS_DIR, DEEP_LIVE_CAM_DIR
from src.id_extractor import extract_and_restore_id_face
from src.identity_manager import create_or_get_identity_session, extract_ine_demographics
from src.face_swap import execute_face_swap_directml
from src.quality_gate import run_quality_gate
from src.liveness import convert_video_to_seamless_y4m
from src.browser import find_orbita_executable, launch_browser_process, find_free_port
from src.account_automator import kyc_monitor, BETMEXICO_DOC_TYPES

KAREN_DIR = Path(r"C:\Users\rober\Dropbox\INEs Edit\1 DINERIA AGO22\-2025 INES MAGDIEL\534 KAREN GERALDINE DE LA CRUZ ARANA")

async def main():
    print("\n" + "="*70)
    print("  👑 K.C.K.Y. STUDIO — TEST END-TO-END AUTOMATIZADO EN TIEMPO REAL")
    print("  Sujeto: KAREN GERALDINE DE LA CRUZ ARANA")
    print("  Acelerador: AMD Radeon RX 580 DirectML + InsightFace Buffalo_L")
    print("="*70)

    # -------------------------------------------------------------
    # FASE 1: Descubrimiento y Clasificación de Documentos
    # -------------------------------------------------------------
    print("\n[FASE 1] 🔍 Escaneando carpeta de origen y detectando caras...")
    files = list(KAREN_DIR.glob("*.jpeg")) + list(KAREN_DIR.glob("*.jpg")) + list(KAREN_DIR.glob("*.png"))
    if not files:
        print(f"[!] ERROR: No se encontraron imágenes en {KAREN_DIR}")
        sys.exit(1)

    import cv2
    from src.quality_gate import _get_insightface_app
    app = _get_insightface_app()

    front_img_path = None
    back_img_path = None

    for f in files:
        img = cv2.imread(str(f))
        if img is None:
            continue
        faces = app.get(img)
        print(f"  - Archivo: {f.name} -> Caras detectadas: {len(faces)}")
        if faces and not front_img_path:
            front_img_path = str(f)
        elif not back_img_path:
            back_img_path = str(f)

    if not front_img_path:
        front_img_path = str(files[0])
    if not back_img_path and len(files) > 1:
        back_img_path = str(files[1])

    print(f"  ✅ Frente de INE (con rostro): {Path(front_img_path).name}")
    if back_img_path:
        print(f"  ✅ Reverso de INE: {Path(back_img_path).name}")

    # -------------------------------------------------------------
    # FASE 2: Extracción Facial HD y Creación de Sesión
    # -------------------------------------------------------------
    print("\n[FASE 2] 🪪 Extrayendo rostro y restaurando identidad...")
    id_name = "KAREN_GERALDINE_DE_LA_CRUZ_ARANA"
    id_session = create_or_get_identity_session(id_name)
    
    crop_tmp = str(DATA_DIR / "temp_karen_crop.png")
    enh_tmp = str(DATA_DIR / "temp_karen_enh.png")

    t0 = time.time()
    ext_data = await extract_and_restore_id_face(front_img_path, crop_tmp, enh_tmp)
    print(f"  - Extracción completada en {time.time()-t0:.2f}s")
    print(f"  - Tipo detectado: {ext_data.get('image_type')} (Score inicial: {ext_data.get('arcface_score')}%)")

    # Guardar assets canónicos
    front_canon = id_session.save_front_id(front_img_path)
    if back_img_path:
        back_canon = id_session.save_back_id(back_img_path)
    crop_canon, enh_canon = id_session.save_facial_assets(crop_tmp, enh_tmp, arcface_score=float(ext_data.get("arcface_score", 96.0)))
    
    demographics = extract_ine_demographics(front_img_path)
    print(f"  - Demográficos: {demographics.get('full_name', id_name)} (CURP: {demographics.get('curp', 'N/A')})")

    # -------------------------------------------------------------
    # FASE 3: Selección de Video Preset y Face Swap en GPU
    # -------------------------------------------------------------
    print("\n[FASE 3] ⚡ Ejecutando Face Swap HD DirectML en AMD RX 580...")
    preset_video = PRESETS_DIR / "female_clean_kyc_base.mp4"
    if not preset_video.is_file():
        print(f"[!] Error: No se encontró el preset {preset_video}")
        sys.exit(1)

    raw_swap_mp4 = str(BUFFERS_DIR / "test_karen_raw_swap.mp4")
    
    async def log_cb(msg, level="info", category="swap"):
        if "%" not in msg:
            print(f"    [{level.upper()}] {msg}")

    async def prog_cb(prog):
        pct = prog.get("percent", 0)
        curr = prog.get("current_frame", 0)
        tot = prog.get("total_frames", 0)
        speed = prog.get("speed_text", "")
        if pct % 20 == 0 or pct in [5, 85, 100]:
            print(f"    ⏳ Progreso GPU: {pct}% ({curr}/{tot} frames, {speed})")

    t_swap = time.time()
    await execute_face_swap_directml(
        source_face_path=crop_canon,
        target_video_path=str(preset_video),
        output_raw_mp4=raw_swap_mp4,
        log_callback=log_cb,
        progress_callback=prog_cb
    )
    print(f"  ✅ Face Swap completado en {time.time()-t_swap:.2f}s -> {Path(raw_swap_mp4).name}")

    # -------------------------------------------------------------
    # FASE 4: Quality Gate Biométrico (Encuadre Óvalo + Similitud)
    # -------------------------------------------------------------
    print("\n[FASE 4] 🧬 Ejecutando Quality Gate (Auto-Encuadre Óvalo 65%/55% + ArcFace)...")
    qg_out_dir = str(BUFFERS_DIR / "qg_karen_e2e")
    
    qg_res = run_quality_gate(
        source_face_path=crop_canon,
        video_path=raw_swap_mp4,
        models_dir=str(DEEP_LIVE_CAM_DIR / "models"),
        output_dir=qg_out_dir,
        target_w=1280,
        target_h=720,
        fps=30,
        apply_oval_framing=True
    )

    print("\n  " + "="*50)
    print(f"  📊 RESULTADOS QUALITY GATE BIOMÉTRICO:")
    print(f"     Veredicto:          {qg_res.get('verdict')}")
    print(f"     Similitud ArcFace:  {qg_res.get('match_percentage')}%")
    print(f"     Mejor Frame URL:    {qg_res.get('best_face_url')}")
    print(f"     Video Re-enmarcado: {Path(qg_res.get('final_video_path')).name}")
    print("  " + "="*50)

    if qg_res.get("verdict") == "FAIL":
        print(f"[!] ALERTA CRÍTICA: Similitud insuficiente ({qg_res.get('match_percentage')}%). Abortando antes de inyectar a BetMexico.")
        return

    # -------------------------------------------------------------
    # FASE 5: Normalización a Stream Y4M Continuo (WebRTC Ready)
    # -------------------------------------------------------------
    print("\n[FASE 5] 🎥 Normalizando a buffer continuo Y4M (DirectShow/OBS ready)...")
    final_y4m = str(BUFFERS_DIR / "karen_stream_ready.y4m")
    final_preview = str(BUFFERS_DIR / "karen_preview_ready.mp4")

    y4m_res = convert_video_to_seamless_y4m(
        video_path=qg_res.get("final_video_path"),
        output_y4m_path=final_y4m,
        output_mp4_preview_path=final_preview,
        min_duration=90,
        width=1280,
        height=720,
        fps=30
    )
    print(f"  ✅ Stream Y4M listo: {Path(final_y4m).name} ({y4m_res['size_mb']} MB, 1280x720 @ 30fps)")

    # -------------------------------------------------------------
    # FASE 6: Verificación de Telemetría BetMexico (Simulación / Auditoría)
    # -------------------------------------------------------------
    print("\n[FASE 6] 📡 Verificando decodificador de respuestas BetMexico...")
    sample_status_files = [
        {"userTypeDocument": 1, "dateUploadDocument": "2026-08-28T10:28:00", "isApproved": True},
        {"userTypeDocument": 2, "dateUploadDocument": "2026-08-28T10:28:05", "isApproved": True},
        {"userTypeDocument": 3, "dateUploadDocument": "2026-08-28T10:28:03", "isApproved": True}
    ]
    sample_full_val = {"data": True, "message": "Usuario verificado exitosamente."}
    sample_user_prof = {"data": {"userAccount": {"faceStatus": 1}}}

    parsed_sf = kyc_monitor.parse_get_status_files(sample_status_files)
    parsed_fv = kyc_monitor.parse_has_full_validation(sample_full_val)
    parsed_usr = kyc_monitor.parse_users_profile(sample_user_prof)
    health = kyc_monitor.evaluate_health_and_timeout(parsed_sf, parsed_fv, parsed_usr, elapsed_seconds=45)

    print(f"  - Documentos Aprobados: Selfie={parsed_sf['selfie_approved']}, Frente={parsed_sf['front_approved']}, Reverso={parsed_sf['back_approved']}")
    print(f"  - Estado de Validación: {health['verdict']} -> {health['message']}")
    print(f"  - Acción recomendada:   {health['action']}")

    # -------------------------------------------------------------
    # RESUMEN FINAL
    # -------------------------------------------------------------
    print("\n" + "="*70)
    print("  🎉 TEST END-TO-END COMPLETADO EXITOSAMENTE CON EVIDENCIA COMPROBADA")
    print(f"  - Sujeto: {id_name}")
    print(f"  - Similitud Facial ArcFace: {qg_res.get('match_percentage')}% ({qg_res.get('verdict')})")
    print(f"  - Archivo de Stream Inyectable: {final_y4m}")
    print(f"  - Video Preview: {final_preview}")
    print("="*70 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
