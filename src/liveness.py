"""
liveness.py — Motor de Generación de Liveness Sintético 3D y Normalización Y4M
"""

import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional


def generate_synthetic_liveness(
    image_path: str,
    output_y4m_path: str,
    output_mp4_preview_path: Optional[str] = None,
    duration: int = 90,
    width: int = 1280,
    height: int = 720,
    fps: int = 30,
    framing_mode: str = "fill_crop"
) -> Dict[str, Any]:
    """
    Genera un stream continuo de video .y4m y preview .mp4 desde una imagen estática.
    Soporta modos de encuadre:
    - 'fill_crop': Llena todo el sensor de cámara recortando al centro sin barras negras ni distorsión.
    - 'fit_pad': Mantiene imagen completa ajustada con padding centrado.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Imagen no encontrada: {image_path}")

    os.makedirs(os.path.dirname(os.path.abspath(output_y4m_path)), exist_ok=True)
    if output_mp4_preview_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_mp4_preview_path)), exist_ok=True)

    total_frames = duration * fps

    if framing_mode == "fit_pad":
        scale_pad_part = f"scale={width*2}:{height*2}:force_original_aspect_ratio=decrease,pad={width*2}:{height*2}:(ow-iw)/2:(oh-ih)/2,"
    else:
        # fill_crop (Primer cuadro selfie): llena el marco y deja headroom superior natural para frente/ojos
        scale_pad_part = f"scale={width*2}:{height*2}:force_original_aspect_ratio=increase,crop={width*2}:{height*2}:(iw-ow)/2:'max(0, (ih-oh)*0.20)',"

    vf_filter = (
        f"{scale_pad_part}"
        f"zoompan=z='1.02+0.015*sin(2*3.14159*on/({fps}*4.5))':"
        f"x='iw/2-(iw/zoom/2)+2.0*sin(2*3.14159*on/({fps}*6.2))':"
        f"y='ih/2-(ih/zoom/2)+1.5*cos(2*3.14159*on/({fps}*3.8))':"
        f"d={total_frames}:fps={fps}:s={width}x{height},"
        f"eq=brightness='0.004*sin(2*3.14159*t/8.0)':contrast='1.0+0.008*cos(2*3.14159*t/7.0)',"
        f"noise=alls=3:allf=t+u,"
        f"format=yuv420p"
    )

    cmd_y4m = [
        "ffmpeg",
        "-y",
        "-loop", "1",
        "-i", image_path,
        "-t", str(duration),
        "-vf", vf_filter,
        "-r", str(fps),
        "-pix_fmt", "yuv420p",
        output_y4m_path
    ]

    res_y4m = subprocess.run(cmd_y4m, capture_output=True, text=True)
    if res_y4m.returncode != 0:
        raise RuntimeError(f"Error generando Y4M con FFmpeg:\n{res_y4m.stderr}")

    if output_mp4_preview_path:
        cmd_mp4 = [
            "ffmpeg",
            "-y",
            "-i", output_y4m_path,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            output_mp4_preview_path
        ]
        subprocess.run(cmd_mp4, capture_output=True, text=True)

    size_mb = os.path.getsize(output_y4m_path) / (1024 * 1024)
    return {
        "status": "success",
        "y4m_path": output_y4m_path,
        "mp4_preview_path": output_mp4_preview_path,
        "duration": duration,
        "resolution": f"{width}x{height}",
        "fps": fps,
        "framing": framing_mode,
        "size_mb": round(size_mb, 2)
    }


def compute_smart_biometric_crop(
    video_path: str,
    target_w: int = 1280,
    target_h: int = 720
) -> str:
    """
    Analiza los primeros frames del video selfie para detectar la posición del rostro
    y calcula el recorte quirúrgico exacto para que encaje a la perfección en el óvalo KYC.
    """
    target_ar = target_w / target_h
    try:
        import cv2
        import numpy as np

        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            in_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            in_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            face_boxes = []
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            detector = cv2.CascadeClassifier(cascade_path) if cv2.data.haarcascades else None

            for _ in range(12):
                ret, frame = cap.read()
                if not ret:
                    break
                if detector and not detector.empty():
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(60, 60))
                    if len(faces) > 0:
                        faces = sorted(faces, key=lambda f: f[2]*f[3], reverse=True)
                        face_boxes.append(faces[0])
            cap.release()

            if face_boxes:
                avg_x = int(np.median([b[0] for b in face_boxes]))
                avg_y = int(np.median([b[1] for b in face_boxes]))
                avg_fw = int(np.median([b[2] for b in face_boxes]))
                avg_fh = int(np.median([b[3] for b in face_boxes]))

                # El rostro debe ocupar ~58% de la altura vertical de la cámara de onboarding
                desired_crop_h = int(avg_fh / 0.58)
                desired_crop_w = int(desired_crop_h * target_ar)

                if desired_crop_w > in_w or desired_crop_h > in_h:
                    if (in_w / in_h) > target_ar:
                        desired_crop_h = in_h
                        desired_crop_w = int(in_h * target_ar)
                    else:
                        desired_crop_w = in_w
                        desired_crop_h = int(in_w / target_ar)

                face_center_x = avg_x + avg_fw / 2.0
                crop_x = int(face_center_x - desired_crop_w / 2.0)
                crop_y = int(avg_y - desired_crop_h * 0.22)

                crop_x = max(0, min(in_w - desired_crop_w, crop_x))
                crop_y = max(0, min(in_h - desired_crop_h, crop_y))

                desired_crop_w = (desired_crop_w // 2) * 2
                desired_crop_h = (desired_crop_h // 2) * 2
                crop_x = (crop_x // 2) * 2
                crop_y = (crop_y // 2) * 2

                return f"crop={desired_crop_w}:{desired_crop_h}:{crop_x}:{crop_y},scale={target_w}:{target_h}"
    except Exception:
        pass

    # Fallback heurístico de encuadre selfie primer cuadro con headroom superior
    return f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h}:(iw-ow)/2:'max(0, (ih-oh)*0.25)'"


def convert_video_to_seamless_y4m(
    video_path: str,
    output_y4m_path: str,
    output_mp4_preview_path: Optional[str] = None,
    min_duration: int = 90,
    width: int = 1280,
    height: int = 720,
    fps: int = 30,
    framing_mode: str = "fill_crop"
) -> Dict[str, Any]:
    """Normaliza, encuadra quirúrgicamente y extiende un video a un bucle continuo de 90s+ en formato Y4M."""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video no encontrado: {video_path}")

    os.makedirs(os.path.dirname(os.path.abspath(output_y4m_path)), exist_ok=True)

    # Detectar dimensiones nativas del video de entrada
    in_w, in_h = 1280, 720
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            in_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or in_w
            in_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or in_h
            cap.release()
    except Exception:
        pass

    is_portrait = (in_w / (in_h or 1)) < 1.0

    if framing_mode == "fit_pad":
        filter_args = [
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,noise=alls=2:allf=t+u,format=yuv420p"
        ]
    elif is_portrait and (width > height):
        # Video vertical (selfie móvil) en salida horizontal (16:9 webcam):
        # Mantiene 100% de la cabeza/pecho centrado sin cortes y añade fondo ambiental desenfocado en los flancos
        filter_complex = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=25:5,eq=brightness=-0.18[bg];"
            f"[0:v]scale=-2:{height}[fg];"
            f"[bg][fg]overlay=(W-w)/2:0,noise=alls=2:allf=t+u,format=yuv420p"
        )
        filter_args = ["-filter_complex", filter_complex]
    else:
        # Video horizontal o relación 16:9 / 4:3
        vf_scale = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}:(iw-ow)/2:'max(0, (ih-oh)*0.15)'"
        filter_args = ["-vf", f"{vf_scale},noise=alls=2:allf=t+u,format=yuv420p"]

    cmd = [
        "ffmpeg",
        "-y",
        "-stream_loop", "-1",
        "-i", video_path,
        "-t", str(min_duration),
        *filter_args,
        "-r", str(fps),
        "-pix_fmt", "yuv420p",
        output_y4m_path
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Error normalizando video con FFmpeg:\n{res.stderr}")

    if output_mp4_preview_path:
        cmd_mp4 = [
            "ffmpeg",
            "-y",
            "-i", output_y4m_path,
            "-t", "15",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            output_mp4_preview_path
        ]
        subprocess.run(cmd_mp4, capture_output=True, text=True)

    size_mb = os.path.getsize(output_y4m_path) / (1024 * 1024)
    return {
        "status": "success",
        "y4m_path": output_y4m_path,
        "mp4_preview_path": output_mp4_preview_path,
        "duration": min_duration,
        "resolution": f"{width}x{height}",
        "fps": fps,
        "size_mb": round(size_mb, 2)
    }
