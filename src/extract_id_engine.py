"""
extract_id_engine.py — Motor de Detección de Rostros en Credenciales y Super-Resolución HD (GFPGAN / GPEN)
Ejecutado en el entorno Python de Deep-Live-Cam (con OpenCV + InsightFace + ONNX Runtime DirectML/CPU).
"""

import os
import sys
import json
import argparse
import numpy as np
import cv2
import onnxruntime as ort

# Template estándar FFHQ 512x512 para alineación facial
FFHQ_TEMPLATE_512 = np.array(
    [
        [192.98138, 239.94708],
        [318.90277, 240.19366],
        [256.63416, 314.01935],
        [201.26117, 371.41043],
        [313.08905, 371.15118],
    ],
    dtype=np.float32,
)


def get_onnx_session(model_path: str) -> ort.InferenceSession:
    """Crea una sesión ONNX usando DirectML si está disponible o CPU."""
    available = ort.get_available_providers()
    providers = []
    if 'DmlExecutionProvider' in available:
        providers.append('DmlExecutionProvider')
    providers.append('CPUExecutionProvider')
    
    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(model_path, sess_options=opts, providers=providers)


def enhance_face_crop_gfpgan(crop_bgr: np.ndarray, model_path: str) -> np.ndarray:
    """Aplica el modelo GFPGAN / GPEN sobre el recorte facial para restaurar calidad a 1024x1024 / 512x512."""
    session = get_onnx_session(model_path)
    input_shape = session.get_inputs()[0].shape
    
    # Determinar resolución esperada por el modelo (512x512 o 1024x1024)
    target_h = input_shape[2] if isinstance(input_shape[2], int) else 512
    target_w = input_shape[3] if isinstance(input_shape[3], int) else 512

    resized = cv2.resize(crop_bgr, (target_w, target_h), interpolation=cv2.INTER_CUBIC)
    
    # Normalizar de BGR [0, 255] a RGB [-1.0, 1.0] (formato estándar de GFPGAN/GPEN)
    img_rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    img_norm = (img_rgb - 0.5) / 0.5
    img_input = np.transpose(img_norm, (2, 0, 1))[None, ...].astype(np.float32)

    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: img_input})
    output_tensor = outputs[0][0]

    # De-normalizar a BGR [0, 255]
    output_img = np.transpose(output_tensor, (1, 2, 0))
    output_img = (output_img * 0.5 + 0.5) * 255.0
    output_img = np.clip(output_img, 0, 255).astype(np.uint8)
    enhanced_bgr = cv2.cvtColor(output_img, cv2.COLOR_RGB2BGR)

    # Post-proceso sutil con Unsharp Masking para ultra definición
    gaussian = cv2.GaussianBlur(enhanced_bgr, (0, 0), 2.0)
    unsharp = cv2.addWeighted(enhanced_bgr, 1.25, gaussian, -0.25, 0)
    return unsharp


def process_id_card(
    image_path: str,
    output_crop_path: str,
    output_enhanced_path: str,
    models_dir: str
) -> dict:
    if not os.path.exists(image_path):
        return {"success": False, "error": f"Archivo no encontrado: {image_path}"}

    img = cv2.imread(image_path)
    if img is None:
        return {"success": False, "error": "No se pudo decodificar la imagen de la credencial."}

    h, w = img.shape[:2]

    # 1. Detección Facial usando InsightFace / RetinaFace o Haar Cascade
    face_box = None
    try:
        import insightface
        fa = insightface.app.FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'], allowed_modules=['detection'])
        fa.prepare(ctx_id=0, det_size=(640, 640))
        faces = fa.get(img)
        if faces:
            # Seleccionar la cara con mayor área o score de confianza
            faces.sort(key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]), reverse=True)
            b = faces[0].bbox.astype(int)
            face_box = (b[0], b[1], b[2], b[3])
    except Exception:
        pass

    # Fallback a Haar Cascade si InsightFace no detectó
    if face_box is None:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Intentar cargar cascade local
        cascade_paths = [
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml',
            os.path.join(os.path.dirname(cv2.__file__), 'data', 'haarcascade_frontalface_default.xml')
        ]
        for cp in cascade_paths:
            if os.path.exists(cp):
                detector = cv2.CascadeClassifier(cp)
                detected = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(60, 60))
                if len(detected) > 0:
                    x, y, fw, fh = detected[0]
                    face_box = (x, y, x + fw, y + fh)
                    break

    # Si no se detectó cara (p. ej. foto muy pequeña), centrar en el tercio superior izquierdo común de credenciales
    if face_box is None:
        # Bounding box heurístico de credenciales INE (foto a la izquierda)
        face_box = (int(w * 0.05), int(h * 0.15), int(w * 0.45), int(h * 0.85))

    x1, y1, x2, y2 = face_box
    fw = x2 - x1
    fh = y2 - y1

    # Margen proporcional inteligente para encuadre tipo retrato/pasaporte
    pad_x = int(fw * 0.40)
    pad_y_top = int(fh * 0.50)
    pad_y_bottom = int(fh * 0.35)

    cx1 = max(0, x1 - pad_x)
    cy1 = max(0, y1 - pad_y_top)
    cx2 = min(w, x2 + pad_x)
    cy2 = min(h, y2 + pad_y_bottom)

    crop = img[cy1:cy2, cx1:cx2]
    if crop.size == 0:
        crop = img

    # Guardar recorte inicial
    os.makedirs(os.path.dirname(os.path.abspath(output_crop_path)), exist_ok=True)
    cv2.imwrite(output_crop_path, crop)

    # 2. Restauración Facial y Super-Resolución HD con GFPGAN / GPEN
    gfpgan_model = os.path.join(models_dir, "gfpgan-1024.onnx")
    gpen_model = os.path.join(models_dir, "GPEN-BFR-512.onnx")

    model_to_use = None
    if os.path.exists(gfpgan_model):
        model_to_use = gfpgan_model
    elif os.path.exists(gpen_model):
        model_to_use = gpen_model

    enhanced_crop = None
    if model_to_use:
        try:
            enhanced_crop = enhance_face_crop_gfpgan(crop, model_to_use)
        except Exception as e:
            print(f"[!] Warning en mejora AI: {e}", file=sys.stderr)

    if enhanced_crop is None:
        # Fallback de mejora con interpolación Bicúbica y filtro bilateral
        enhanced_crop = cv2.resize(crop, (1024, 1024), interpolation=cv2.INTER_LANCZOS4)
        enhanced_crop = cv2.bilateralFilter(enhanced_crop, 9, 75, 75)

    os.makedirs(os.path.dirname(os.path.abspath(output_enhanced_path)), exist_ok=True)
    cv2.imwrite(output_enhanced_path, enhanced_crop)

    return {
        "success": True,
        "cropped_path": output_crop_path,
        "enhanced_path": output_enhanced_path,
        "original_crop_size": f"{crop.shape[1]}x{crop.shape[0]}",
        "enhanced_size": f"{enhanced_crop.shape[1]}x{enhanced_crop.shape[0]}",
        "bbox": [int(x1), int(y1), int(x2), int(y2)]
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, help="Ruta de la credencial / INE")
    parser.add_argument("--output-crop", required=True, help="Ruta de salida del recorte")
    parser.add_argument("--output-enhanced", required=True, help="Ruta de salida del rostro HD restaurado")
    parser.add_argument("--models-dir", required=True, help="Directorio de modelos ONNX")

    args = parser.parse_args()
    res = process_id_card(args.image, args.output_crop, args.output_enhanced, args.models_dir)
    print(json.dumps(res))


if __name__ == "__main__":
    main()
