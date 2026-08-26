"""
Test de cálculo dinámico de Auto-Encuadre Biométrico Facial para videos selfie
"""

import cv2
import numpy as np

def compute_smart_biometric_crop(
    video_path: str,
    target_w: int = 1280,
    target_h: int = 720
) -> str:
    """
    Analiza los primeros frames del video con OpenCV para detectar el centro y tamaño del rostro.
    Calcula las coordenadas exactas de crop (x, y, w, h) para que el rostro ocupe ~58% de la altura
    con el headroom superior óptimo (22% arriba de la frente), garantizando que encaje perfecto en el óvalo KYC.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h}"

    in_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    in_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    target_ar = target_w / target_h
    face_boxes = []

    # Cascade detector
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    detector = cv2.CascadeClassifier(cascade_path) if cv2.data.haarcascades else None

    # Muestrear hasta 15 frames para obtener una estimación estable del rostro
    for _ in range(15):
        ret, frame = cap.read()
        if not ret:
            break
        if detector and not detector.empty():
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(60, 60))
            if len(faces) > 0:
                # Tomar la cara con mayor área
                faces = sorted(faces, key=lambda f: f[2]*f[3], reverse=True)
                face_boxes.append(faces[0])

    cap.release()

    if face_boxes:
        # Promediar las posiciones de la cara
        avg_x = int(np.median([b[0] for b in face_boxes]))
        avg_y = int(np.median([b[1] for b in face_boxes]))
        avg_fw = int(np.median([b[2] for b in face_boxes]))
        avg_fh = int(np.median([b[3] for b in face_boxes]))
    else:
        # Heurística por defecto para selfies si no detecta rostro
        avg_fw = int(in_w * 0.40)
        avg_fh = int(in_h * 0.35)
        avg_x = int((in_w - avg_fw) / 2)
        avg_y = int(in_h * 0.18)

    # El rostro debe ocupar ~58% de la altura vertical de la cámara de onboarding
    desired_crop_h = int(avg_fh / 0.58)
    desired_crop_w = int(desired_crop_h * target_ar)

    # Si el crop deseado excede las dimensiones del video, ajustar respetando target_ar
    if desired_crop_w > in_w or desired_crop_h > in_h:
        if (in_w / in_h) > target_ar:
            desired_crop_h = in_h
            desired_crop_w = int(in_h * target_ar)
        else:
            desired_crop_w = in_w
            desired_crop_h = int(in_w / target_ar)

    # Centrar horizontalmente sobre el rostro
    face_center_x = avg_x + avg_fw / 2.0
    crop_x = int(face_center_x - desired_crop_w / 2.0)

    # Posicionar verticalmente con 22% de headroom arriba de la frente
    crop_y = int(avg_y - desired_crop_h * 0.22)

    # Clamping dentro de los límites del video
    crop_x = max(0, min(in_w - desired_crop_w, crop_x))
    crop_y = max(0, min(in_h - desired_crop_h, crop_y))

    # Asegurar números pares para codificadores YUV420P
    desired_crop_w = (desired_crop_w // 2) * 2
    desired_crop_h = (desired_crop_h // 2) * 2
    crop_x = (crop_x // 2) * 2
    crop_y = (crop_y // 2) * 2

    return f"crop={desired_crop_w}:{desired_crop_h}:{crop_x}:{crop_y},scale={target_w}:{target_h}"


print("Helper script ready")
