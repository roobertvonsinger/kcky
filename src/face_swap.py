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


import re

async def execute_face_swap_directml(
    source_face_path: str,
    target_video_path: str,
    output_raw_mp4: str,
    enable_enhancer: bool = True,
    log_callback: Optional[Callable[[str, str], Any]] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
) -> None:
    """Ejecuta Deep-Live-Cam de forma asíncrona usando el proveedor DirectML (AMD GPU) y restauración GFPGAN con telemetría de progreso fotograma a fotograma."""
    python_exec = get_deep_live_cam_python() or sys.executable
    run_py = DEEP_LIVE_CAM_DIR / "run.py"

    if not run_py.is_file():
        raise FileNotFoundError(f"No se encontró run.py de Deep-Live-Cam en: {run_py}")

    processors = ["face_swapper"]
    if enable_enhancer:
        processors.append("face_enhancer_gpen512")

    abs_source = str(Path(source_face_path).resolve())
    abs_target = str(Path(target_video_path).resolve())
    abs_output = str(Path(output_raw_mp4).resolve())
    Path(abs_output).parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        python_exec,
        "-u", # Unbuffered output para captura instantánea en tiempo real
        str(run_py),
        "-s", abs_source,
        "-t", abs_target,
        "-o", abs_output,
        "--execution-provider", "dml",
        "--execution-threads", "2",
        "--frame-processor", *processors,
        "--video-encoder", "libx264"
    ]

    if log_callback:
        await log_callback("Iniciando Deep-Live-Cam DirectML...", "info")

    if progress_callback:
        await progress_callback({
            "percent": 5,
            "current_frame": 0,
            "total_frames": 0,
            "eta_text": "Calculando...",
            "speed_text": "",
            "status_text": "Inicializando red neuronal DirectML..."
        })

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(DEEP_LIVE_CAM_DIR)
    )

    tqdm_regex = re.compile(r'(\d+)%\|.*?\|\s*(\d+)/(\d+)\s*\[([^<]+)<([^,]+),\s*([^\]]+)\]')
    simple_tqdm_regex = re.compile(r'(\d+)%')
    frame_ratio_regex = re.compile(r'(\d+)/(\d+)')

    try:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="ignore").strip()
            if not text:
                continue

            if log_callback and not ("%" in text and "|" in text):
                await log_callback(text, "info")

            # Parsear progreso en tiempo real
            m = tqdm_regex.search(text)
            if m and progress_callback:
                raw_pct = int(m.group(1))
                curr = int(m.group(2))
                tot = int(m.group(3))
                elapsed = m.group(4).strip()
                eta = m.group(5).strip()
                speed = m.group(6).strip()

                # Mapear de 5% a 85% para dejar margen a inicialización y Y4M seamless final
                mapped_pct = int(5 + (raw_pct * 0.80))
                await progress_callback({
                    "percent": mapped_pct,
                    "current_frame": curr,
                    "total_frames": tot,
                    "eta_text": eta,
                    "speed_text": speed,
                    "status_text": f"Sintetizando fotograma {curr} de {tot} ({speed})"
                })
            else:
                m_simple = simple_tqdm_regex.search(text)
                if m_simple and progress_callback:
                    try:
                        raw_pct = int(m_simple.group(1))
                        mapped_pct = int(5 + (raw_pct * 0.80))
                        m_ratio = frame_ratio_regex.search(text)
                        curr = int(m_ratio.group(1)) if m_ratio else 0
                        tot = int(m_ratio.group(2)) if m_ratio else 0
                        await progress_callback({
                            "percent": mapped_pct,
                            "current_frame": curr,
                            "total_frames": tot,
                            "eta_text": "En proceso",
                            "speed_text": "",
                            "status_text": f"Procesando en GPU DirectML ({raw_pct}%)..."
                        })
                    except Exception:
                        pass

        await proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"Deep-Live-Cam falló con código de salida: {proc.returncode}")
    finally:
        if proc and proc.returncode is None:
            try:
                proc.kill()
            except Exception:
                pass


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
