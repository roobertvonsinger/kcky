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
    fps: int = 30
) -> Dict[str, Any]:
    """
    Genera un stream continuo de video .y4m y preview .mp4 desde una imagen estática.
    Aplica micro-movimiento senoidal armónico (respiración/pulso), micro-luz ambiental y ruido CMOS.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Imagen no encontrada: {image_path}")

    os.makedirs(os.path.dirname(os.path.abspath(output_y4m_path)), exist_ok=True)
    if output_mp4_preview_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_mp4_preview_path)), exist_ok=True)

    total_frames = duration * fps

    vf_filter = (
        f"scale={width*2}:{height*2}:force_original_aspect_ratio=decrease,"
        f"pad={width*2}:{height*2}:(ow-iw)/2:(oh-ih)/2,"
        f"zoompan=z='1.02+0.015*sin(2*3.14159*on/({fps}*4.5))':"
        f"x='iw/2-(iw/zoom/2)+2.0*sin(2*3.14159*on/({fps}*6.2))':"
        f"y='ih/2-(ih/zoom/2)+1.5*cos(2*3.14159*on/({fps}*3.8))':"
        f"d={total_frames}:s={width}x{height},"
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
        "size_mb": round(size_mb, 2)
    }


def convert_video_to_seamless_y4m(
    video_path: str,
    output_y4m_path: str,
    output_mp4_preview_path: Optional[str] = None,
    min_duration: int = 90,
    width: int = 1280,
    height: int = 720,
    fps: int = 30
) -> Dict[str, Any]:
    """Normaliza y extiende un video (p. ej. de face swap) a un bucle continuo de 90s+ en formato Y4M."""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video no encontrado: {video_path}")

    os.makedirs(os.path.dirname(os.path.abspath(output_y4m_path)), exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-stream_loop", "10",
        "-i", video_path,
        "-t", str(min_duration),
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,noise=alls=2:allf=t+u,format=yuv420p",
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
