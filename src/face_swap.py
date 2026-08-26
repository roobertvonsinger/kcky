"""
face_swap.py — Integración con Deep-Live-Cam y Aceleración DirectML
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Callable, Optional

from src.config import DEEP_LIVE_CAM_DIR
from src.liveness import convert_video_to_seamless_y4m


def get_deep_live_cam_python() -> Optional[str]:
    """Retorna la ruta al ejecutable de Python del venv de Deep-Live-Cam si existe."""
    venv_py = DEEP_LIVE_CAM_DIR / "venv" / "Scripts" / "python.exe"
    if venv_py.is_file():
        return str(venv_py)
    return None


async def execute_face_swap_directml(
    source_face_path: str,
    target_video_path: str,
    output_raw_mp4: str,
    log_callback: Optional[Callable[[str, str], Any]] = None
) -> None:
    """Ejecuta Deep-Live-Cam de forma asíncrona usando el proveedor DirectML (AMD GPU)."""
    python_exec = get_deep_live_cam_python() or sys.executable
    run_py = DEEP_LIVE_CAM_DIR / "run.py"

    if not run_py.is_file():
        raise FileNotFoundError(f"No se encontró run.py de Deep-Live-Cam en: {run_py}")

    cmd = [
        python_exec,
        str(run_py),
        "-s", source_face_path,
        "-t", target_video_path,
        "-o", output_raw_mp4,
        "--execution-provider", "dml",
        "--frame-processor", "face_swapper",
        "--video-encoder", "libx264"
    ]

    if log_callback:
        await log_callback(f"Lanzando Deep-Live-Cam (DirectML AMD RX 580)...", "info")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(DEEP_LIVE_CAM_DIR)
    )

    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="ignore").strip()
        if text and log_callback:
            await log_callback(text, "info")

    await proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"Deep-Live-Cam falló con código de salida: {proc.returncode}")


def launch_deep_live_cam_gui(source_face_path: Optional[str] = None) -> subprocess.Popen:
    """Lanza la interfaz interactiva de Deep-Live-Cam para Live Capture con Webcam física."""
    python_exec = get_deep_live_cam_python() or sys.executable
    run_py = DEEP_LIVE_CAM_DIR / "run.py"

    if not run_py.is_file():
        raise FileNotFoundError(f"No se encontró run.py de Deep-Live-Cam en: {run_py}")

    cmd = [
        python_exec,
        str(run_py),
        "--execution-provider", "dml",
        "--frame-processor", "face_swapper"
    ]
    if source_face_path and os.path.exists(source_face_path):
        cmd.extend(["-s", os.path.abspath(source_face_path)])

    return subprocess.Popen(cmd, cwd=str(DEEP_LIVE_CAM_DIR))
