import os
import sys
import time
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Callable


def run_ffmpeg_with_progress(
    cmd: list,
    total_frames: int,
    progress_callback: Optional[Callable[[Dict[str, Any]], Any]] = None,
    base_percent: int = 5,
    max_percent: int = 90,
    phase_name: str = "Procesando"
) -> None:
    """Ejecuta FFmpeg capturando el progreso fotograma a fotograma y computando ETA con precisión."""
    cmd_with_prog = list(cmd)
    if "-progress" not in cmd_with_prog:
        idx = cmd_with_prog.index("-i") if "-i" in cmd_with_prog else 1
        cmd_with_prog = cmd_with_prog[:idx] + ["-progress", "pipe:1", "-nostats"] + cmd_with_prog[idx:]

    proc = subprocess.Popen(
        cmd_with_prog,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    t0 = time.time()
    for line in proc.stdout:
        line = line.strip()
        if line.startswith("frame="):
            try:
                curr_frame = int(line.split("=")[1].strip())
                if total_frames > 0 and progress_callback:
                    ratio = min(1.0, curr_frame / float(total_frames))
                    pct = int(base_percent + ratio * (max_percent - base_percent))
                    elapsed = time.time() - t0
                    fps_calc = curr_frame / max(0.1, elapsed)
                    rem_frames = max(0, total_frames - curr_frame)
                    eta_sec = round(rem_frames / max(0.1, fps_calc), 1)
                    eta_str = f"{int(eta_sec)}s" if eta_sec < 60 else f"{int(eta_sec//60)}m {int(eta_sec%60)}s"
                    progress_callback({
                        "percent": pct,
                        "current_frame": curr_frame,
                        "total_frames": total_frames,
                        "eta_text": eta_str,
                        "speed_text": f"{fps_calc:.1f} fps",
                        "status_text": f"{phase_name}: fotograma {curr_frame} de {total_frames} ({fps_calc:.1f} fps)"
                    })
            except Exception:
                pass

    proc.wait()
    if proc.returncode != 0:
        err = proc.stderr.read()
        raise RuntimeError(f"Error en FFmpeg (código {proc.returncode}):\n{err}")


def generate_synthetic_liveness(
    image_path: str,
    output_y4m_path: str,
    output_mp4_preview_path: Optional[str] = None,
    duration: int = 90,
    width: int = 1280,
    height: int = 720,
    fps: int = 30,
    framing_mode: str = "fill_crop",
    progress_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
) -> Dict[str, Any]:
    """
    Genera un stream continuo y fotorealista de video .y4m y preview .mp4 desde la foto restaurada.
    Aplica encuadre óptimo de estudio biométrico, micro-respiración senoidal (0.22 Hz) y ruido analógico CMOS,
    preservando 100% la anatomía facial sin distorsiones ni deformaciones artificiales de malla.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Imagen no encontrada: {image_path}")

    os.makedirs(os.path.dirname(os.path.abspath(output_y4m_path)), exist_ok=True)
    if output_mp4_preview_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_mp4_preview_path)), exist_ok=True)

    total_frames = duration * fps

    if progress_callback:
        progress_callback({
            "percent": 5,
            "current_frame": 0,
            "total_frames": total_frames,
            "eta_text": "Iniciando...",
            "speed_text": "",
            "status_text": "Generando matriz de liveness senoidal 3D..."
        })

    # Encuadre fotográfico de estudio (centrado natural con margen de hombros/pecho)
    if framing_mode == "fit_pad":
        scale_part = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x12141a,"
    else:
        # Encuadre selfie calibrado para marco circular KYC BetMexico
        # headroom 0.38 baja la cara al centro-superior del marco (antes 0.20 dejaba cara MUY arriba)
        scale_part = f"scale={width*2}:{height*2}:force_original_aspect_ratio=increase,crop={width*2}:{height*2}:(iw-ow)/2:'max(0, (ih-oh)*0.38)',"

    # Micro-movimientos cinemáticos senoidales (respiración y deriva analógica de 1-2px)
    # Zoom base 1.06 para que la cara llene ~65% del frame (antes 1.015 dejaba cara pequeña)
    vf_filter = (
        f"{scale_part}"
        f"zoompan=z='1.06+0.008*sin(2*3.14159*on/({fps}*4.5))':"
        f"x='iw/2-(iw/zoom/2)+1.2*sin(2*3.14159*on/({fps}*6.2))':"
        f"y='ih/2-(ih/zoom/2)+1.0*cos(2*3.14159*on/({fps}*4.0))':"
        f"d={total_frames}:fps={fps}:s={width}x{height},"
        f"noise=alls=2:allf=t+u,"
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

    run_ffmpeg_with_progress(
        cmd_y4m,
        total_frames=total_frames,
        progress_callback=progress_callback,
        base_percent=5,
        max_percent=85,
        phase_name="Sintetizando Liveness 3D"
    )

    if output_mp4_preview_path:
        if progress_callback:
            progress_callback({
                "percent": 88,
                "current_frame": total_frames,
                "total_frames": total_frames,
                "eta_text": "1s",
                "speed_text": "",
                "status_text": "Generando preview MP4 HD..."
            })
        cmd_mp4 = [
            "ffmpeg",
            "-y",
            "-i", output_y4m_path,
            "-t", "15",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            output_mp4_preview_path
        ]
        subprocess.run(cmd_mp4, capture_output=True, text=True)

    if progress_callback:
        progress_callback({
            "percent": 100,
            "current_frame": total_frames,
            "total_frames": total_frames,
            "eta_text": "0s",
            "speed_text": "",
            "status_text": "¡Flujo de cámara listo y armado!"
        })

    size_mb = os.path.getsize(output_y4m_path) / (1024 * 1024) if os.path.exists(output_y4m_path) else 0
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
    Analiza los primeros frames del video para detectar la posición del rostro con InsightFace
    y calcula el recorte exacto para que cuadre con el marco circular KYC de BetMexico.

    Calibración (marco circular BetMexico, 2026-08-28):
    - face_h / frame_h ≈ 0.65 (la cara llena el marco)
    - face_center_y / frame_h ≈ 0.45 (ligeramente arriba del centro)
    - face_center_x / frame_w ≈ 0.50 (centrado horizontal)
    """
    # Intentar usar quality_gate para el cálculo preciso
    try:
        from src.quality_gate import compute_oval_framing_crop
        return compute_oval_framing_crop(video_path, target_w, target_h)
    except Exception:
        pass

    # Fallback: cálculo directo con InsightFace
    FACE_HEIGHT_RATIO = 0.65
    FACE_CENTER_Y = 0.45
    target_ar = target_w / target_h

    try:
        import cv2
        import numpy as np

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return _default_framing_fallback(target_w, target_h)

        in_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        in_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        face_boxes = []
        # Intentar InsightFace primero (reutilizando singleton para evitar re-carga de 340MB)
        try:
            try:
                from src.quality_gate import _get_insightface_app
                face_app = _get_insightface_app()
            except Exception:
                import insightface
                global _liveness_insightface_cache
                try:
                    face_app = _liveness_insightface_cache
                except NameError:
                    face_app = insightface.app.FaceAnalysis(
                        name='buffalo_l', providers=['CPUExecutionProvider'],
                        allowed_modules=['detection']
                    )
                    face_app.prepare(ctx_id=0, det_size=(640, 640))
                    _liveness_insightface_cache = face_app

            for pos in [5, 15, 30, 45]:
                cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
                ret, frame = cap.read()
                if not ret:
                    continue
                faces = face_app.get(frame)
                if faces:
                    best = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]))
                    b = best.bbox.astype(int)
                    face_boxes.append((int(b[0]), int(b[1]), int(b[2]-b[0]), int(b[3]-b[1])))
        except Exception:
            # Fallback a Haar Cascade
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
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
                        face_boxes.append(tuple(faces[0]))

        cap.release()

        if face_boxes:
            avg_x = int(np.median([b[0] for b in face_boxes]))
            avg_y = int(np.median([b[1] for b in face_boxes]))
            avg_fw = int(np.median([b[2] for b in face_boxes]))
            avg_fh = int(np.median([b[3] for b in face_boxes]))

            face_cx = avg_x + avg_fw / 2.0
            face_cy = avg_y + avg_fh / 2.0

            # Calcular crop para que face_h/crop_h = FACE_HEIGHT_RATIO
            desired_crop_h = int(avg_fh / FACE_HEIGHT_RATIO)
            desired_crop_w = int(desired_crop_h * target_ar)

            if desired_crop_w > in_w:
                desired_crop_w = in_w
                desired_crop_h = int(in_w / target_ar)
            if desired_crop_h > in_h:
                desired_crop_h = in_h
                desired_crop_w = int(desired_crop_h * target_ar)

            # Posicionar para que face_center esté a FACE_CENTER_Y del crop
            crop_y = int(face_cy - (FACE_CENTER_Y * desired_crop_h))
            crop_x = int(face_cx - desired_crop_w / 2.0)

            crop_x = max(0, min(in_w - desired_crop_w, crop_x))
            crop_y = max(0, min(in_h - desired_crop_h, crop_y))

            desired_crop_w = (desired_crop_w // 2) * 2
            desired_crop_h = (desired_crop_h // 2) * 2
            crop_x = (crop_x // 2) * 2
            crop_y = (crop_y // 2) * 2

            return f"crop={desired_crop_w}:{desired_crop_h}:{crop_x}:{crop_y},scale={target_w}:{target_h}"
    except Exception:
        pass

    return _default_framing_fallback(target_w, target_h)


def _default_framing_fallback(target_w: int, target_h: int) -> str:
    """Fallback heurístico calibrado para marco circular KYC (headroom 35%)."""
    return f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h}:(iw-ow)/2:'max(0, (ih-oh)*0.35)'"


def convert_video_to_seamless_y4m(
    video_path: str,
    output_y4m_path: str,
    output_mp4_preview_path: Optional[str] = None,
    min_duration: int = 90,
    width: int = 1280,
    height: int = 720,
    fps: int = 30,
    framing_mode: str = "fill_crop",
    progress_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
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
        # Headroom 0.35 para centrar cara en marco circular KYC (antes 0.15 dejaba cara MUY arriba)
        vf_scale = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}:(iw-ow)/2:'max(0, (ih-oh)*0.35)'"
        filter_args = ["-vf", f"{vf_scale},noise=alls=2:allf=t+u,format=yuv420p"]

    total_frames = min_duration * fps

    if progress_callback:
        progress_callback({
            "percent": 86,
            "current_frame": 0,
            "total_frames": total_frames,
            "eta_text": "2s",
            "speed_text": "",
            "status_text": "Normalizando buffer continuo Y4M..."
        })

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

    run_ffmpeg_with_progress(
        cmd,
        total_frames=total_frames,
        progress_callback=progress_callback,
        base_percent=86,
        max_percent=96,
        phase_name="Escribiendo Buffer Y4M"
    )

    if output_mp4_preview_path:
        if progress_callback:
            progress_callback({
                "percent": 97,
                "current_frame": total_frames,
                "total_frames": total_frames,
                "eta_text": "1s",
                "speed_text": "",
                "status_text": "Generando preview MP4..."
            })
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

    if progress_callback:
        progress_callback({
            "percent": 100,
            "current_frame": total_frames,
            "total_frames": total_frames,
            "eta_text": "0s",
            "speed_text": "",
            "status_text": "¡Flujo de cámara generado y armado con éxito!"
        })

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
