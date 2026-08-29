import os
import sys
import urllib.request
import cv2
import numpy as np

# Configurar UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = r"c:\Users\rober\Dropbox\TESTING DEV\repos\kcky"
sys.path.insert(0, REPO_ROOT)

from src.quality_gate import _get_insightface_app, calibrate_similarity

MODELS_DIR = os.path.join(REPO_ROOT, "models", "independent")
os.makedirs(MODELS_DIR, exist_ok=True)

YUNET_URL = "https://github.com/opencv/opencv_zoo/raw/master/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
SFACE_URL = "https://github.com/opencv/opencv_zoo/raw/master/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"

yunet_path = os.path.join(MODELS_DIR, "face_detection_yunet.onnx")
sface_path = os.path.join(MODELS_DIR, "face_recognition_sface.onnx")

def download_if_missing(url, dest):
    if not os.path.exists(dest) or os.path.getsize(dest) < 1000:
        print(f"[*] Descargando modelo independiente: {os.path.basename(dest)}...")
        urllib.request.urlretrieve(url, dest)
        print(f"[+] Descarga completa: {os.path.getsize(dest)} bytes")

try:
    download_if_missing(YUNET_URL, yunet_path)
    download_if_missing(SFACE_URL, sface_path)
except Exception as e:
    print(f"[!] Aviso al descargar OpenCV Zoo: {e}")

# Rutas de los 4 elementos
ine_raw_img = r"C:\Users\rober\Dropbox\INEs Edit\1 DINERIA AGO22\-2025 INES MAGDIEL\534 KAREN GERALDINE DE LA CRUZ ARANA\WhatsApp Image 2025-03-14 at 10.12.50 PM (1).jpeg"
ine_crop_img = os.path.join(REPO_ROOT, "data", "identities", "KAREN_GERALDINE_DE_LA_CRUZ_ARANA", "assets", "crop.png")
ine_enh_img = os.path.join(REPO_ROOT, "data", "identities", "KAREN_GERALDINE_DE_LA_CRUZ_ARANA", "assets", "enhanced.png")
actor_base_video = os.path.join(REPO_ROOT, "data", "presets", "female_clean_kyc_base.mp4")
swap_video = os.path.join(REPO_ROOT, "data", "buffers", "test_karen_raw_swap.mp4")

# 1. Extraer frame del actor base
cap_act = cv2.VideoCapture(actor_base_video)
cap_act.set(cv2.CAP_PROP_POS_FRAMES, 15)
_, frame_actor = cap_act.read()
cap_act.release()

# 2. Extraer frame del video swap sintetizado
cap_swap = cv2.VideoCapture(swap_video)
cap_swap.set(cv2.CAP_PROP_POS_FRAMES, 15)
_, frame_swap = cap_swap.read()
cap_swap.release()

img_ine = cv2.imread(ine_raw_img)
img_crop = cv2.imread(ine_crop_img)
img_enh = cv2.imread(ine_enh_img)

app = _get_insightface_app()

def get_insight_emb(img):
    faces = app.get(img)
    if not faces:
        return None, None
    best = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]))
    return best.normed_embedding, best

emb_ine, face_ine = get_insight_emb(img_ine)
emb_crop, face_crop = get_insight_emb(img_crop)
emb_enh, face_enh = get_insight_emb(img_enh)
emb_actor, face_actor = get_insight_emb(frame_actor)
emb_swap, face_swap = get_insight_emb(frame_swap)

print("\n" + "="*75)
print("  🧬 AUDITORÍA BIOMÉTRICA MULTI-ÁNGULO (INE vs ACTOR vs SELFIE SWAP)")
print("  Modelo Principal: ArcFace w600k_r50 (InsightFace Buffalo_L)")
print("="*75)

comparisons = [
    ("1. INE Original vs INE Crop Normalizado", emb_ine, emb_crop),
    ("2. INE Original vs INE Restaurada (GPEN)", emb_ine, emb_enh),
    ("3. INE Original vs Selfie Salida (Swap Video)", emb_ine, emb_swap),
    ("4. INE Restaurada vs Selfie Salida (Swap Video)", emb_enh, emb_swap),
    ("5. Actor Base Original vs Selfie Salida (Swap)", emb_actor, emb_swap),
    ("6. INE Original vs Actor Base Original (Sin Swap)", emb_ine, emb_actor)
]

for label, e1, e2 in comparisons:
    if e1 is not None and e2 is not None:
        raw_cos = float(np.dot(e1, e2))
        calib = calibrate_similarity(raw_cos)
        verdict = "MATCH (Aprobado)" if raw_cos >= 0.35 else "DISTINTO (No match)"
        print(f"  {label:<48} | Cosine: {raw_cos:+.4f} | Calibrado: {calib*100:5.1f}% | {verdict}")

# -------------------------------------------------------------
# MOTOR 2: OpenCV SFace (Motor Independiente)
# -------------------------------------------------------------
if os.path.exists(yunet_path) and os.path.exists(sface_path):
    print("\n" + "-"*75)
    print("  🛡️ MOTOR 2 INDEPENDIENTE: OpenCV SFace (Tsinghua / Tencent Standard)")
    print("-"*75)
    
    detector = cv2.FaceDetectorYN.create(yunet_path, "", (320, 320), 0.6, 0.3, 5000)
    recognizer = cv2.FaceRecognizerSF.create(sface_path, "")

    def get_sface_emb(img):
        h, w = img.shape[:2]
        detector.setInputSize((w, h))
        _, faces = detector.detect(img)
        if faces is None or len(faces) == 0:
            return None
        aligned = recognizer.alignCrop(img, faces[0])
        feature = recognizer.feature(aligned)
        return feature

    s_ine = get_sface_emb(img_ine)
    s_enh = get_sface_emb(img_enh)
    s_swap = get_sface_emb(frame_swap)
    s_actor = get_sface_emb(frame_actor)

    s_comps = [
        ("INE Original vs Selfie Salida (Swap Video)", s_ine, s_swap),
        ("INE Restaurada vs Selfie Salida (Swap Video)", s_enh, s_swap),
        ("Actor Base vs Selfie Salida (Swap Video)", s_actor, s_swap),
        ("INE Original vs Actor Base Original", s_ine, s_actor)
    ]

    for label, feat1, feat2 in s_comps:
        if feat1 is not None and feat2 is not None:
            # SFace cosine similarity threshold is 0.363
            cos_score = recognizer.match(feat1, feat2, cv2.FaceRecognizerSF_FR_COSINE)
            l2_dist = recognizer.match(feat1, feat2, cv2.FaceRecognizerSF_FR_NORM_L2)
            verdict = "MATCH (Misma persona)" if cos_score >= 0.363 else "DISTINTO"
            print(f"  [SFace] {label:<40} | Cosine: {cos_score:+.4f} | L2 Dist: {l2_dist:.3f} | {verdict}")

print("="*75 + "\n")
