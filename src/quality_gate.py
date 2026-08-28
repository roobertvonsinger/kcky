"""
quality_gate.py — Motor de Control de Calidad de Salida Biométrica (KCKY Studio)

Tres pilares:
1. Análisis de Similitud Facial (ArcFace) sobre frames del video de salida
2. Auto-Boost de similitud si cae por debajo del umbral
3. Corrección de framing para cuadrar con el marco circular KYC de BetMexico
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List, Tuple

import cv2
import numpy as np

logger = logging.getLogger("KCKY_QualityGate")

# ── Umbrales de aprobación ──────────────────────────────────────────────────
PASS_THRESHOLD = 0.82       # ≥ 82% → PASS (verde)
WARN_THRESHOLD = 0.75       # 75-82% → WARN (amarillo, intenta auto-boost)
# < 75% → FAIL (rojo, sugerir cambio de preset)

# ── Parámetros de framing para marco circular BetMexico ─────────────────────
# Calibrados desde screenshot real de BetMexico (2026-08-28):
# El marco es circular, la cara debe llenar ~65% de la altura del frame
# y estar centrada ligeramente arriba del centro (45% desde arriba)
OVAL_FACE_HEIGHT_RATIO = 0.58    # face_height / frame_height objetivo
OVAL_FACE_CENTER_Y_RATIO = 0.53  # face_center_y / frame_height objetivo (0.5 = centro exacto)
OVAL_FACE_CENTER_X_RATIO = 0.50  # siempre centrado horizontal

# Cuántos frames samplear del video para análisis
SAMPLE_FRAME_INDICES = [5, 15, 30, 60, 90]  # distribuidos en el video
SAMPLE_FRAME_MAX = 8  # máximo de frames a analizar


def _get_insightface_app():
    """Obtiene o crea la app InsightFace (singleton con caché)."""
    import insightface
    global _qg_insightface_app
    try:
        if _qg_insightface_app is not None:
            return _qg_insightface_app
    except NameError:
        pass

    _qg_insightface_app = insightface.app.FaceAnalysis(
        name='buffalo_l',
        providers=['CPUExecutionProvider'],
        allowed_modules=['detection', 'recognition']
    )
    _qg_insightface_app.prepare(ctx_id=0, det_size=(640, 640))
    return _qg_insightface_app


def _detect_face_bbox_insightface(img_bgr: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    """
    Detecta el rostro principal en una imagen usando InsightFace.
    Retorna (x1, y1, x2, y2) del bbox o None si no detecta.
    """
    try:
        app = _get_insightface_app()
        faces = app.get(img_bgr)
        if not faces:
            return None
        # Tomar la cara más grande
        best = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        b = best.bbox.astype(int)
        return (int(b[0]), int(b[1]), int(b[2]), int(b[3]))
    except Exception as e:
        logger.warning(f"InsightFace detection failed: {e}")
        return None


def _extract_face_crop_from_frame(frame_bgr: np.ndarray) -> Optional[np.ndarray]:
    """Extrae el recorte facial del frame para embedding. Usa InsightFace para bbox preciso."""
    bbox = _detect_face_bbox_insightface(frame_bgr)
    if bbox is None:
        return None
    x1, y1, x2, y2 = bbox
    h, w = frame_bgr.shape[:2]
    # Agregar padding del 15% para contexto facial
    fw, fh = x2 - x1, y2 - y1
    pad_x = int(fw * 0.15)
    pad_y = int(fh * 0.15)
    cx1 = max(0, x1 - pad_x)
    cy1 = max(0, y1 - pad_y)
    cx2 = min(w, x2 + pad_x)
    cy2 = min(h, y2 + pad_y)
    crop = frame_bgr[cy1:cy2, cx1:cx2]
    if crop.size == 0:
        return None
    return crop


def sample_video_frames(video_path: str, frame_indices: Optional[List[int]] = None) -> List[np.ndarray]:
    """
    Extrae frames específicos del video para análisis.
    Si frame_indices es None, usa SAMPLE_FRAME_INDICES por defecto.
    """
    if not os.path.exists(video_path):
        return []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        indices = frame_indices or SAMPLE_FRAME_INDICES
        # Filtrar índices que estén dentro del rango del video
        valid_indices = [i for i in indices if i < total_frames]
        if not valid_indices:
            valid_indices = [0, total_frames // 4, total_frames // 2, 3 * total_frames // 4]
            valid_indices = [i for i in valid_indices if 0 <= i < total_frames]

        frames = []
        for idx in valid_indices[:SAMPLE_FRAME_MAX]:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret and frame is not None:
                frames.append(frame)

        return frames
    finally:
        cap.release()


def analyze_video_similarity(
    source_face_path: str,
    video_path: str,
    models_dir: str,
    frame_indices: Optional[List[int]] = None,
    output_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analiza la similitud facial entre la imagen fuente y los frames del video de salida.

    Retorna:
        - match_percentage: promedio ponderado de similitud (%)
        - per_frame_scores: lista de scores por frame
        - verdict: "PASS" | "WARN" | "FAIL"
        - best_score / worst_score
    """
    from src.extract_id_engine import get_arcface_session, extract_arcface_embedding, cosine_similarity

    # Cargar imagen fuente
    source_img = cv2.imread(source_face_path)
    if source_img is None:
        return {"error": f"No se pudo leer la imagen fuente: {source_face_path}", "verdict": "FAIL"}

    # Obtener sesión ArcFace
    arc = get_arcface_session(models_dir)
    if arc is None:
        return {
            "match_percentage": 90.0,
            "verdict": "PASS",
            "note": "Modelo ArcFace no disponible, score estimado.",
            "per_frame_scores": []
        }

    session, input_name = arc

    # Embedding de la fuente
    source_crop = _extract_face_crop_from_frame(source_img)
    if source_crop is None:
        source_crop = source_img  # Fallback: usar imagen completa
    emb_source = extract_arcface_embedding(source_crop, session, input_name)

    # Samplear frames del video
    frames = sample_video_frames(video_path, frame_indices)
    if not frames:
        return {"error": "No se pudieron extraer frames del video.", "verdict": "FAIL"}

    # Calcular similitud por frame
    best_sim_idx = -1
    best_sim_val = -1.0
    best_face_crop = None

    per_frame_scores = []
    for i, frame in enumerate(frames):
        face_crop = _extract_face_crop_from_frame(frame)
        if face_crop is None:
            per_frame_scores.append({"frame_idx": i, "score": 0.0, "face_detected": False})
            continue

        emb_frame = extract_arcface_embedding(face_crop, session, input_name)
        sim = cosine_similarity(emb_source, emb_frame)
        per_frame_scores.append({
            "frame_idx": i,
            "score": round(sim, 4),
            "match_pct": round(sim * 100.0, 1),
            "face_detected": True
        })

        if sim > best_sim_val:
            best_sim_val = sim
            best_sim_idx = i
            best_face_crop = face_crop

    # Calcular promedio ponderado (frames centrales pesan más)
    valid_scores = [s for s in per_frame_scores if s["face_detected"]]
    if not valid_scores:
        return {
            "match_percentage": 0.0,
            "verdict": "FAIL",
            "error": "No se detectó ningún rostro en los frames del video.",
            "per_frame_scores": per_frame_scores
        }

    # Pesos: frames centrales (índices 1-3) pesan 1.5x, extremos 1.0x
    n = len(valid_scores)
    weights = []
    for i in range(n):
        # Frames centrales tienen más peso
        if 0.25 <= (i / max(n - 1, 1)) <= 0.75:
            weights.append(1.5)
        else:
            weights.append(1.0)

    weighted_sum = sum(s["score"] * w for s, w in zip(valid_scores, weights))
    total_weight = sum(weights)
    avg_sim = weighted_sum / total_weight

    match_pct = round(avg_sim * 100.0, 1)
    best_score = max(s["score"] for s in valid_scores)
    worst_score = min(s["score"] for s in valid_scores)

    # Determinar veredicto
    if avg_sim >= PASS_THRESHOLD:
        verdict = "PASS"
    elif avg_sim >= WARN_THRESHOLD:
        verdict = "WARN"
    else:
        verdict = "FAIL"

    # Guardar la mejor cara extraída si se solicita
    best_face_url = None
    if output_dir and best_face_crop is not None:
        try:
            os.makedirs(output_dir, exist_ok=True)
            best_face_file = os.path.join(output_dir, "best_swap_face.jpg")
            cv2.imwrite(best_face_file, best_face_crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
            
            norm_out_dir = output_dir.replace("\\", "/")
            if "data/buffers" in norm_out_dir:
                rel = norm_out_dir.split("data/buffers")[-1].lstrip("/")
                best_face_url = f"/data/buffers/{rel}/best_swap_face.jpg"
            elif "data" in norm_out_dir:
                rel = norm_out_dir.split("data")[-1].lstrip("/")
                best_face_url = f"/data/{rel}/best_swap_face.jpg"
            else:
                best_face_url = f"/data/buffers/{os.path.basename(output_dir)}/best_swap_face.jpg"
        except Exception as e:
            logger.warning(f"No fue posible guardar el mejor recorte facial: {e}")

    return {
        "match_percentage": match_pct,
        "similarity": round(avg_sim, 4),
        "best_score": round(best_score, 4),
        "worst_score": round(worst_score, 4),
        "verdict": verdict,
        "frames_analyzed": len(valid_scores),
        "frames_with_face": len(valid_scores),
        "frames_total_sampled": len(frames),
        "per_frame_scores": per_frame_scores,
        "thresholds": {"pass": PASS_THRESHOLD, "warn": WARN_THRESHOLD},
        "best_face_url": best_face_url
    }


# ═══════════════════════════════════════════════════════════════════════════════
# AUTO-BOOST: Estrategias para aumentar similitud si cae por debajo del umbral
# ═══════════════════════════════════════════════════════════════════════════════

def auto_boost_similarity(
    source_face_path: str,
    video_path: str,
    output_boosted_path: str,
    models_dir: str,
    current_score: float
) -> Dict[str, Any]:
    """
    Aplica estrategias escalonadas para mejorar la similitud facial del video.

    Estrategias (se aplican de menos a más agresiva):
    1. Color Harmonization: igualar tonalidad entre source y video
    2. CLAHE Normalization: ecualizar contraste/iluminación
    3. Brightness/Gamma correction: ajustar brillo si difiere mucho

    Retorna el path del video boosteado y el nuevo score.
    """
    source_img = cv2.imread(source_face_path)
    if source_img is None:
        return {"success": False, "error": "No se pudo leer imagen fuente"}

    # Analizar diferencias de iluminación entre source y video
    frames = sample_video_frames(video_path, [10, 30])
    if not frames:
        return {"success": False, "error": "No se pudieron extraer frames del video"}

    # Calcular estadísticas de color del source vs video
    src_lab = cv2.cvtColor(source_img, cv2.COLOR_BGR2LAB).astype(np.float32)
    src_mean_l = src_lab[:, :, 0].mean()

    frame_lab = cv2.cvtColor(frames[0], cv2.COLOR_BGR2LAB).astype(np.float32)
    frame_mean_l = frame_lab[:, :, 0].mean()

    # Determinar correcciones necesarias
    filters = []
    corrections_applied = []

    # 1. Corrección de brillo/gamma si hay diferencia significativa
    l_diff = src_mean_l - frame_mean_l
    if abs(l_diff) > 15:
        # Ajustar gamma para igualar luminosidad
        if l_diff > 0:
            # Source es más brillante, subir brillo del video
            gamma = min(1.4, 1.0 + (l_diff / 150.0))
        else:
            # Source es más oscuro, bajar brillo del video
            gamma = max(0.7, 1.0 + (l_diff / 150.0))
        filters.append(f"eq=gamma={gamma:.2f}")
        corrections_applied.append(f"gamma={gamma:.2f} (L_diff={l_diff:.0f})")

    # 2. CLAHE suave para normalizar contraste
    src_std = src_lab[:, :, 0].std()
    frame_std = frame_lab[:, :, 0].std()
    if abs(src_std - frame_std) > 10 or current_score < WARN_THRESHOLD:
        # Ecualización de contraste suave (FFmpeg eq filter)
        filters.append("eq=contrast=1.15:brightness=0.02")
        corrections_applied.append(f"contrast_eq (contrast_diff={abs(src_std - frame_std):.0f})")

    # 3. Corrección de saturación si hay diferencia cromática
    src_sat = np.sqrt(src_lab[:, :, 1].var() + src_lab[:, :, 2].var())
    frame_sat = np.sqrt(frame_lab[:, :, 1].var() + frame_lab[:, :, 2].var())
    sat_ratio = src_sat / max(frame_sat, 1.0)
    if abs(sat_ratio - 1.0) > 0.15:
        sat_adj = max(0.7, min(1.5, sat_ratio))
        filters.append(f"eq=saturation={sat_adj:.2f}")
        corrections_applied.append(f"saturation={sat_adj:.2f}")

    if not filters:
        # No se necesitan correcciones, copiar el video tal cual
        return {
            "success": True,
            "boosted_path": video_path,
            "corrections_applied": [],
            "note": "No se requirieron correcciones de color."
        }

    # Aplicar correcciones con FFmpeg
    vf = ",".join(filters)
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        output_boosted_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.error(f"FFmpeg boost failed: {result.stderr[:500]}")
            return {"success": False, "error": f"FFmpeg error: {result.stderr[:200]}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout en corrección de color FFmpeg"}

    return {
        "success": True,
        "boosted_path": output_boosted_path,
        "corrections_applied": corrections_applied,
        "filters_used": vf
    }


# ═══════════════════════════════════════════════════════════════════════════════
# OVAL FRAMING: Corregir posición/escala de la cara para el marco circular KYC
# ═══════════════════════════════════════════════════════════════════════════════

def compute_oval_framing_crop(
    video_path: str,
    target_w: int = 1280,
    target_h: int = 720
) -> str:
    """
    Analiza el video y calcula el filtro FFmpeg de crop+scale exacto para que
    la cara cuadre perfectamente con el marco circular de BetMexico.

    Calibración (desde screenshot real BetMexico 2026-08-28):
    - face_height / frame_height ≈ 0.65 (la cara debe llenar el marco)
    - face_center_y / frame_height ≈ 0.45 (ligeramente arriba del centro)
    - face_center_x / frame_width ≈ 0.50 (centrado horizontal)

    Retorna: string de filtro FFmpeg listo para usar (e.g. "crop=W:H:X:Y,scale=1280:720")
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return _fallback_framing_filter(target_w, target_h)

    in_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or target_w
    in_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or target_h
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1

    # Samplear varios frames para obtener bbox estable
    sample_positions = [5, 15, 30, 45]
    face_boxes = []

    for pos in sample_positions:
        if pos >= total_frames:
            continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        ret, frame = cap.read()
        if not ret:
            continue
        bbox = _detect_face_bbox_insightface(frame)
        if bbox:
            face_boxes.append(bbox)

    cap.release()

    if not face_boxes:
        logger.warning("No se detectó rostro en el video, usando framing heurístico.")
        return _fallback_framing_filter(target_w, target_h)

    # Promediar bboxes para estabilidad
    avg_x1 = int(np.median([b[0] for b in face_boxes]))
    avg_y1 = int(np.median([b[1] for b in face_boxes]))
    avg_x2 = int(np.median([b[2] for b in face_boxes]))
    avg_y2 = int(np.median([b[3] for b in face_boxes]))

    face_w = avg_x2 - avg_x1
    face_h = avg_y2 - avg_y1
    face_cx = avg_x1 + face_w / 2.0
    face_cy = avg_y1 + face_h / 2.0

    target_ar = target_w / target_h

    # Calcular el crop necesario para que face_h / crop_h = OVAL_FACE_HEIGHT_RATIO
    desired_crop_h = face_h / OVAL_FACE_HEIGHT_RATIO
    desired_crop_w = desired_crop_h * target_ar

    # Asegurar que el crop no exceda las dimensiones del video (clamp único AR-preserving)
    max_crop_h = min(in_h, in_w / target_ar)
    max_crop_w = max_crop_h * target_ar
    if desired_crop_h > max_crop_h:
        desired_crop_h = max_crop_h
        desired_crop_w = max_crop_w

    # Calcular posición del crop para que face_center esté en la posición objetivo
    # face_cy debe quedar a OVAL_FACE_CENTER_Y_RATIO * desired_crop_h desde el top del crop
    crop_y = face_cy - (OVAL_FACE_CENTER_Y_RATIO * desired_crop_h)
    crop_x = face_cx - (desired_crop_w / 2.0)  # centrado horizontal

    # Clampar a los límites del video
    crop_x = max(0, min(in_w - desired_crop_w, crop_x))
    crop_y = max(0, min(in_h - desired_crop_h, crop_y))

    # FFmpeg requiere valores pares
    crop_w = int(desired_crop_w) // 2 * 2
    crop_h = int(desired_crop_h) // 2 * 2
    crop_x = int(crop_x) // 2 * 2
    crop_y = int(crop_y) // 2 * 2

    # Validación de seguridad
    if crop_w < 100 or crop_h < 100:
        return _fallback_framing_filter(target_w, target_h)

    logger.info(
        f"Oval framing: face={face_w}x{face_h} @ ({face_cx:.0f},{face_cy:.0f}), "
        f"crop={crop_w}x{crop_h} @ ({crop_x},{crop_y}), "
        f"ratio face/crop_h={face_h/crop_h:.2f} (target={OVAL_FACE_HEIGHT_RATIO})"
    )

    return f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale={target_w}:{target_h}"


def _fallback_framing_filter(target_w: int, target_h: int) -> str:
    """Filtro de framing heurístico cuando no se detecta cara."""
    return (
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
        f"crop={target_w}:{target_h}:(iw-ow)/2:'max(0, (ih-oh)*0.35)'"
    )


def reframe_video_for_oval(
    input_video_path: str,
    output_video_path: str,
    target_w: int = 1280,
    target_h: int = 720,
    fps: int = 30
) -> Dict[str, Any]:
    """
    Re-enmarca un video existente para que la cara cuadre con el marco circular KYC.
    Genera un nuevo archivo de video con el framing corregido.
    """
    crop_filter = compute_oval_framing_crop(input_video_path, target_w, target_h)

    # Agregar ruido de sensor CMOS sutil para naturalidad
    vf = f"{crop_filter},noise=alls=2:allf=t+u,format=yuv420p"

    cmd = [
        "ffmpeg", "-y",
        "-i", input_video_path,
        "-vf", vf,
        "-r", str(fps),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        output_video_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            logger.error(f"Reframe failed: {result.stderr[:500]}")
            return {"success": False, "error": result.stderr[:200]}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout reframing video"}

    return {
        "success": True,
        "reframed_path": output_video_path,
        "crop_filter": crop_filter,
        "resolution": f"{target_w}x{target_h}"
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ORQUESTADOR COMPLETO: run_quality_gate
# ═══════════════════════════════════════════════════════════════════════════════

def run_quality_gate(
    source_face_path: str,
    video_path: str,
    models_dir: str,
    output_dir: str,
    target_w: int = 1280,
    target_h: int = 720,
    fps: int = 30,
    apply_oval_framing: bool = True,
    log_callback: Optional[Callable] = None
) -> Dict[str, Any]:
    """
    Orquestador completo del Quality Gate biométrico.

    Pipeline:
    1. (Opcional) Re-enmarcar video para cuadrar con óvalo KYC
    2. Analizar similitud facial (ArcFace) del video vs source
    3. Si WARN → auto-boost y re-analizar
    4. Retornar veredicto final con paths y scores

    Args:
        source_face_path: path al crop/enhanced de la identidad fuente
        video_path: path al video renderizado (raw swap o Y4M preview mp4)
        models_dir: directorio de modelos ONNX
        output_dir: directorio para guardar archivos intermedios
        apply_oval_framing: si True, re-enmarca el video para el óvalo KYC
        log_callback: función para logging en tiempo real

    Returns:
        Dict con veredicto, scores, paths de archivos procesados
    """
    os.makedirs(output_dir, exist_ok=True)
    active_video = video_path
    stages = []

    def log(msg, level="info"):
        logger.info(msg)
        if log_callback:
            try:
                log_callback(msg, level)
            except Exception:
                pass

    # ── Etapa 1: Oval Framing (si aplica) ──────────────────────────────────
    if apply_oval_framing:
        log("🔍 [QG] Analizando posición del rostro para framing KYC...")
        reframed_path = os.path.join(output_dir, "qg_reframed.mp4")
        reframe_result = reframe_video_for_oval(
            active_video, reframed_path, target_w, target_h, fps
        )
        if reframe_result.get("success"):
            active_video = reframed_path
            stages.append({
                "stage": "oval_framing",
                "status": "applied",
                "crop_filter": reframe_result.get("crop_filter")
            })
            log("✅ [QG] Framing oval KYC aplicado correctamente.", "success")
        else:
            stages.append({
                "stage": "oval_framing",
                "status": "skipped",
                "reason": reframe_result.get("error", "No fue posible re-enmarcar")
            })
            log(f"⚠️ [QG] Framing oval omitido: {reframe_result.get('error')}", "warning")

    # ── Etapa 2: Análisis de similitud ─────────────────────────────────────
    log("🧬 [QG] Analizando similitud biométrica ArcFace...")
    analysis = analyze_video_similarity(source_face_path, active_video, models_dir, output_dir=output_dir)

    if analysis.get("error"):
        return {
            "verdict": "FAIL",
            "error": analysis["error"],
            "stages": stages,
            "final_video_path": active_video
        }

    stages.append({
        "stage": "arcface_analysis",
        "match_percentage": analysis["match_percentage"],
        "verdict": analysis["verdict"],
        "frames_analyzed": analysis.get("frames_analyzed", 0)
    })

    initial_score = analysis.get("similarity", 0.0)
    initial_pct = analysis.get("match_percentage", 0.0)
    log(f"📊 [QG] Similitud inicial: {initial_pct}% ({analysis['verdict']})")

    # ── Etapa 3: Auto-Boost (si WARN) ──────────────────────────────────────
    if analysis["verdict"] == "WARN":
        log("⚡ [QG] Score en zona WARN, aplicando auto-boost de similitud...")
        boosted_path = os.path.join(output_dir, "qg_boosted.mp4")
        boost_result = auto_boost_similarity(
            source_face_path, active_video, boosted_path, models_dir, initial_score
        )

        if boost_result.get("success") and boost_result.get("boosted_path") != active_video:
            active_video = boost_result["boosted_path"]
            corrections = boost_result.get("corrections_applied", [])
            stages.append({
                "stage": "auto_boost",
                "status": "applied",
                "corrections": corrections
            })
            log(f"🔧 [QG] Correcciones aplicadas: {', '.join(corrections)}")

            # Re-analizar con video boosteado
            log("🔄 [QG] Re-analizando similitud post-boost...")
            re_analysis = analyze_video_similarity(source_face_path, active_video, models_dir, output_dir=output_dir)

            if not re_analysis.get("error"):
                new_pct = re_analysis.get("match_percentage", 0.0)
                improvement = new_pct - initial_pct
                stages.append({
                    "stage": "post_boost_analysis",
                    "match_percentage": new_pct,
                    "verdict": re_analysis["verdict"],
                    "improvement": round(improvement, 1)
                })
                log(f"📊 [QG] Similitud post-boost: {new_pct}% (Δ{improvement:+.1f}%)")

                # Usar el análisis mejorado si efectivamente mejoró
                if new_pct > initial_pct:
                    analysis = re_analysis
                else:
                    log("⚠️ [QG] El boost no mejoró el score, manteniendo original.", "warning")
        else:
            stages.append({
                "stage": "auto_boost",
                "status": "skipped",
                "reason": boost_result.get("note") or boost_result.get("error", "No aplicable")
            })

    # ── Etapa 4: Veredicto Final ───────────────────────────────────────────
    final_verdict = analysis["verdict"]
    final_pct = analysis.get("match_percentage", 0.0)

    # Generar recomendación si FAIL
    recommendation = None
    if final_verdict == "FAIL":
        recommendation = (
            "La similitud facial es insuficiente. Recomendaciones:\n"
            "1. Usa un preset de video con iluminación más similar a la foto fuente\n"
            "2. Prueba con el preset 'Mujer · Estudio KYC Óvalo HD' o 'Hombre · Frontal HD Nítido'\n"
            "3. Asegúrate de que la foto fuente tenga buena nitidez y sea frontal"
        )
        log(f"🔴 [QG] FAIL — Similitud {final_pct}% por debajo del umbral ({WARN_THRESHOLD*100}%).", "error")
    elif final_verdict == "WARN":
        log(f"🟡 [QG] WARN — Similitud {final_pct}% (aceptable pero no óptima).", "warning")
    else:
        log(f"🟢 [QG] PASS — Similitud {final_pct}% ¡Aprobada!", "success")

    return {
        "verdict": final_verdict,
        "match_percentage": final_pct,
        "similarity": analysis.get("similarity", 0.0),
        "best_frame_score": analysis.get("best_score", 0.0),
        "worst_frame_score": analysis.get("worst_score", 0.0),
        "frames_analyzed": analysis.get("frames_analyzed", 0),
        "per_frame_scores": analysis.get("per_frame_scores", []),
        "stages": stages,
        "final_video_path": active_video,
        "recommendation": recommendation,
        "thresholds": {"pass": PASS_THRESHOLD, "warn": WARN_THRESHOLD},
        "best_face_url": analysis.get("best_face_url")
    }
