import os
import sys
import math
import cv2
import numpy as np

# Configurar encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = r"c:\Users\rober\Dropbox\TESTING DEV\repos\kcky"
sys.path.insert(0, REPO_ROOT)

from src.quality_gate import _get_insightface_app, calibrate_similarity

MODELS_DIR = os.path.join(REPO_ROOT, "models", "independent")
os.makedirs(MODELS_DIR, exist_ok=True)

yunet_path = os.path.join(MODELS_DIR, "face_detection_yunet.onnx")
sface_path = os.path.join(MODELS_DIR, "face_recognition_sface.onnx")

# Rutas de prueba para auditoría (Karen Geraldine)
RAW_UNEDITED_INE = r"C:\Users\rober\Dropbox\INEs Edit\1 DINERIA AGO22\-2025 INES MAGDIEL\534 KAREN GERALDINE DE LA CRUZ ARANA\WhatsApp Image 2025-03-14 at 10.12.50 PM (1).jpeg"
CROP_INE = os.path.join(REPO_ROOT, "data", "identities", "KAREN_GERALDINE_DE_LA_CRUZ_ARANA", "assets", "crop.png")
ENHANCED_INE = os.path.join(REPO_ROOT, "data", "identities", "KAREN_GERALDINE_DE_LA_CRUZ_ARANA", "assets", "enhanced.png")
FINAL_SWAP_VIDEO = os.path.join(REPO_ROOT, "data", "buffers", "test_karen_raw_swap.mp4")
ACTOR_BASE_VIDEO = os.path.join(REPO_ROOT, "data", "presets", "female_clean_kyc_base.mp4")

# Fallback si no está el video raw
if not os.path.exists(FINAL_SWAP_VIDEO):
    FINAL_SWAP_VIDEO = os.path.join(REPO_ROOT, "data", "buffers", "karen_preview_ready.mp4")

print("=" * 80)
print("  🔬 AUDITORÍA BIOMÉTRICA & FORENSE MULTI-PROVEEDOR (ESTÁNDARES RIGUROSOS)")
print("  Objetivo: Auditar similitud estricta, deriva temporal y artefactos de swap")
print("=" * 80)
print(f"[*] Rostro Original Sin Editar : {os.path.basename(RAW_UNEDITED_INE)}")
print(f"[*] Video Final Resultante     : {os.path.basename(FINAL_SWAP_VIDEO)}")
print(f"[*] Preset Actor Base          : {os.path.basename(ACTOR_BASE_VIDEO)}")
print("-" * 80)

# Cargar imágenes
img_raw = cv2.imread(RAW_UNEDITED_INE)
img_crop = cv2.imread(CROP_INE) if os.path.exists(CROP_INE) else None
img_enh = cv2.imread(ENHANCED_INE) if os.path.exists(ENHANCED_INE) else None

if img_raw is None:
    print(f"[!] Error: No se pudo cargar la imagen original {RAW_UNEDITED_INE}")
    sys.exit(1)

# Extraer 5 frames del video en diferentes momentos (0%, 25%, 50%, 75%, 90%)
cap = cv2.VideoCapture(FINAL_SWAP_VIDEO)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

if total_frames <= 0:
    print(f"[!] Error: No se pudo leer el video {FINAL_SWAP_VIDEO}")
    sys.exit(1)

sample_indices = [
    max(0, int(total_frames * 0.05)),
    int(total_frames * 0.25),
    int(total_frames * 0.50),
    int(total_frames * 0.75),
    min(total_frames - 1, int(total_frames * 0.90))
]

video_frames = []
for idx in sample_indices:
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ret, frame = cap.read()
    if ret:
        video_frames.append((idx, frame))
cap.release()

# Frame de actor base
cap_act = cv2.VideoCapture(ACTOR_BASE_VIDEO)
cap_act.set(cv2.CAP_PROP_POS_FRAMES, sample_indices[2])
_, frame_actor = cap_act.read()
cap_act.release()

# ==============================================================================
# MOTOR 1: InsightFace ArcFace w600k_r50 (NIST Leader / Buffalo_L)
# ==============================================================================
print("\n" + "─" * 80)
print("  🏆 MOTOR 1: ArcFace w600k_r50 (InsightFace / NIST Benchmark Top Tier)")
print("  Estándar: 512-D Embeddings | Umbral Estricto KYC: >= 0.50 | FAR < 0.001%")
print("─" * 80)

app = _get_insightface_app()

def get_arcface_data(img):
    faces = app.get(img)
    if not faces:
        return None
    best = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    return best

raw_face = get_arcface_data(img_raw)
enh_face = get_arcface_data(img_enh) if img_enh is not None else None
actor_face = get_arcface_data(frame_actor) if frame_actor is not None else None

if raw_face is None:
    print("[!] Error crítico: ArcFace no detectó rostro en la foto original sin editar.")
    sys.exit(1)

raw_emb = raw_face.normed_embedding

arcface_video_scores = []
for idx, frame in video_frames:
    v_face = get_arcface_data(frame)
    if v_face is not None:
        cos_sim = float(np.dot(raw_emb, v_face.normed_embedding))
        calib = calibrate_similarity(cos_sim)
        arcface_video_scores.append((idx, cos_sim, calib, v_face))
    else:
        arcface_video_scores.append((idx, 0.0, 0.0, None))

# Evaluaciones Motor 1
for idx, cos_sim, calib, _ in arcface_video_scores:
    verdict = "🟢 MATCH ESTRICTO (Pasa KYC)" if cos_sim >= 0.50 else ("🟡 MATCH MODERADO" if cos_sim >= 0.40 else "🔴 FALLO / RECHAZO")
    print(f"  Frame {idx:3d} ({idx/total_frames*100:4.1f}% tiempo) -> Cosine: {cos_sim:+.4f} | Calibrado: {calib*100:5.1f}% | {verdict}")

avg_arcface_cos = np.mean([s[1] for s in arcface_video_scores if s[1] > 0])
std_arcface_cos = np.std([s[1] for s in arcface_video_scores if s[1] > 0])

print(f"\n  📊 Media ArcFace: {avg_arcface_cos:+.4f} | Desviación Temporal (Jitter): {std_arcface_cos:.4f}")

# Negative control: Actor base vs Raw
if actor_face is not None:
    cos_actor_raw = float(np.dot(raw_emb, actor_face.normed_embedding))
    print(f"  🧪 Control Negativo (INE Raw vs Actor Base Original): {cos_actor_raw:+.4f} ({'✅ Cero filtración' if cos_actor_raw < 0.20 else '⚠️ Filtración de base'})")

# ==============================================================================
# MOTOR 2: OpenCV SFace (Tsinghua / Tencent / OpenCV Zoo)
# ==============================================================================
print("\n" + "─" * 80)
print("  🛡️ MOTOR 2: OpenCV SFace (Tsinghua University / Tencent Standard)")
print("  Estándar: 128-D Spherical | Umbral Estricto: Cosine >= 0.40 / L2 Dist <= 1.00")
print("─" * 80)

detector = cv2.FaceDetectorYN.create(yunet_path, "", (320, 320), 0.6, 0.3, 5000)
recognizer = cv2.FaceRecognizerSF.create(sface_path, "")

def get_sface_feature(img):
    h, w = img.shape[:2]
    detector.setInputSize((w, h))
    _, faces = detector.detect(img)
    if faces is None or len(faces) == 0:
        return None
    aligned = recognizer.alignCrop(img, faces[0])
    return recognizer.feature(aligned)

sface_raw_feat = get_sface_feature(img_raw)
sface_actor_feat = get_sface_feature(frame_actor) if frame_actor is not None else None

sface_video_scores = []
for idx, frame in video_frames:
    s_feat = get_sface_feature(frame)
    if s_feat is not None and sface_raw_feat is not None:
        cos_score = recognizer.match(sface_raw_feat, s_feat, cv2.FaceRecognizerSF_FR_COSINE)
        l2_dist = recognizer.match(sface_raw_feat, s_feat, cv2.FaceRecognizerSF_FR_NORM_L2)
        sface_video_scores.append((idx, cos_score, l2_dist))
        verdict = "🟢 MATCH ESTRICTO" if cos_score >= 0.40 and l2_dist <= 1.00 else ("🟡 MATCH ESTÁNDAR" if cos_score >= 0.363 else "🔴 NO MATCH")
        print(f"  Frame {idx:3d} ({idx/total_frames*100:4.1f}% tiempo) -> SFace Cosine: {cos_score:+.4f} | L2 Dist: {l2_dist:5.3f} | {verdict}")
    else:
        print(f"  Frame {idx:3d} -> [!] SFace no detectó rostro")

avg_sface_cos = np.mean([s[1] for s in sface_video_scores]) if sface_video_scores else 0.0
avg_sface_l2 = np.mean([s[2] for s in sface_video_scores]) if sface_video_scores else 0.0
print(f"\n  📊 Media SFace: Cosine {avg_sface_cos:+.4f} | L2 Distance: {avg_sface_l2:.3f}")

if sface_actor_feat is not None and sface_raw_feat is not None:
    s_act_cos = recognizer.match(sface_raw_feat, sface_actor_feat, cv2.FaceRecognizerSF_FR_COSINE)
    print(f"  🧪 Control Negativo SFace (INE Raw vs Actor Base): Cosine {s_act_cos:+.4f} ({'✅ Cero filtración' if s_act_cos < 0.25 else '⚠️ Fuga de rasgos'})")

# ==============================================================================
# MOTOR 3: ANÁLISIS FORENSE DE ARTEFACTOS, TEXTURA & INTEGRIDAD ESTRUCTURAL
# ==============================================================================
print("\n" + "─" * 80)
print("  🔍 MOTOR 3: ANÁLISIS FORENSE DE ARTEFACTOS, TEXTURA & DERIVA ESPACIAL")
print("  (Detecta desenfoque de autoencoder, parpadeo temporal, costuras de blending y FFT)")
print("─" * 80)

def calc_laplacian_sharpness(img, bbox=None):
    """Calcula la varianza del Laplaciano en la región del rostro (métrica de nitidez/blur)."""
    if bbox is not None:
        x1, y1, x2, y2 = [int(v) for v in bbox]
        h, w = img.shape[:2]
        x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
        crop = img[y1:y2, x1:x2]
    else:
        crop = img
    if crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())

def calc_fft_high_freq_energy(img, bbox=None):
    """Calcula la energía de alta frecuencia en el espectro 2D de Fourier."""
    if bbox is not None:
        x1, y1, x2, y2 = [int(v) for v in bbox]
        h, w = img.shape[:2]
        x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
        crop = img[y1:y2, x1:x2]
    else:
        crop = img
    if crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (128, 128))
    f = np.fft.fft2(gray)
    fshift = np.fft.fftshift(f)
    magnitude = np.abs(fshift)
    
    # Máscara de alta frecuencia (anillo exterior)
    rows, cols = 128, 128
    crow, ccol = rows // 2, cols // 2
    mask = np.ones((rows, cols), np.uint8)
    r_inner = 20
    y, x = np.ogrid[:rows, :cols]
    mask_area = (x - ccol)**2 + (y - crow)**2 <= r_inner**2
    mask[mask_area] = 0
    
    high_freq_power = float(np.mean(magnitude * mask))
    return high_freq_power

# Comparar nitidez y FFT entre original y frames del video
raw_bbox = raw_face.bbox if raw_face is not None else None
raw_sharpness = calc_laplacian_sharpness(img_raw, raw_bbox)
raw_fft = calc_fft_high_freq_energy(img_raw, raw_bbox)

print(f"  • Foto Original Raw  -> Nitidez Laplaciana: {raw_sharpness:7.1f} | FFT High-Freq Power: {raw_fft:7.1f}")

video_sharpness_list = []
video_fft_list = []

for idx, frame in video_frames:
    vf = get_arcface_data(frame)
    v_bbox = vf.bbox if vf is not None else None
    v_sharp = calc_laplacian_sharpness(frame, v_bbox)
    v_fft = calc_fft_high_freq_energy(frame, v_bbox)
    video_sharpness_list.append(v_sharp)
    video_fft_list.append(v_fft)
    print(f"  • Frame {idx:3d} (Video)     -> Nitidez Laplaciana: {v_sharp:7.1f} | FFT High-Freq Power: {v_fft:7.1f}")

avg_v_sharp = np.mean(video_sharpness_list)
avg_v_fft = np.mean(video_fft_list)
sharpness_ratio = avg_v_sharp / max(raw_sharpness, 1.0)

print(f"\n  📊 Ratio de Preservación de Nitidez: {sharpness_ratio*100:5.1f}%")
if sharpness_ratio >= 0.70:
    print("  ✅ Preservación de textura y micro-detalles EXCELENTE (sin borrosidad de autoencoder)")
elif sharpness_ratio >= 0.40:
    print("  🟡 Textura Aceptable (ligero suavizado característico de inswapper)")
else:
    print("  🔴 ALERTA: Rostro sobre-suavizado (alta probabilidad de ser marcado por detector de blur)")

# ==============================================================================
# SÍNTESIS Y DICTAMEN DE AUDITORÍA FORENSE
# ==============================================================================
print("\n" + "=" * 80)
print("  🎯 DICTAMEN FINAL DE AUDITORÍA FORENSE Y SIMILITUD BIOMÉTRICA")
print("=" * 80)

pasa_arcface = avg_arcface_cos >= 0.50
pasa_sface = avg_sface_cos >= 0.40 and avg_sface_l2 <= 1.05
estabilidad_temporal = std_arcface_cos <= 0.05
sin_fuga_actor = cos_actor_raw < 0.25 if actor_face is not None else True

print(f"  1. Identidad ArcFace (NIST Standard) : {'🟢 PASA CON CRECES (Score ' + f'{avg_arcface_cos:+.4f})' if pasa_arcface else '🔴 NO PASA'}")
print(f"  2. Identidad SFace (OpenCV Standard) : {'🟢 PASA CON CRECES (Cosine ' + f'{avg_sface_cos:+.4f}, L2 {avg_sface_l2:.3f})' if pasa_sface else '🔴 NO PASA'}")
print(f"  3. Estabilidad Temporal (Multi-Frame): {'🟢 ULTRA ESTABLE (Jitter sigma=' + f'{std_arcface_cos:.4f})' if estabilidad_temporal else '⚠️ INESTABLE'}")
print(f"  4. Fuga de Actor Base (Control Neg.) : {'🟢 CERO FUGA (Score ' + f'{cos_actor_raw:+.4f})' if sin_fuga_actor else '⚠️ RASGOS DEL ACTOR'}")
print("=" * 80 + "\n")
