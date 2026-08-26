"""
id_extractor.py — Conector Asíncrono para Extracción y Super-Resolución de Rostros desde Credenciales
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

from src.config import DEEP_LIVE_CAM_DIR
from src.face_swap import get_deep_live_cam_python

logger = logging.getLogger("Onboarded_ID_Extractor")


async def extract_and_restore_id_face(
    id_card_path: str,
    output_crop_path: str,
    output_enhanced_path: str
) -> Dict[str, Any]:
    """
    Ejecuta la extracción de rostro de credencial y super-resolución HD con GFPGAN/GPEN.
    """
    if not os.path.exists(id_card_path):
        raise FileNotFoundError(f"Credencial no encontrada: {id_card_path}")

    python_exec = get_deep_live_cam_python() or sys.executable
    engine_script = Path(__file__).resolve().parent / "extract_id_engine.py"
    models_dir = DEEP_LIVE_CAM_DIR / "models"

    cmd = [
        python_exec,
        str(engine_script),
        "--image", id_card_path,
        "--output-crop", output_crop_path,
        "--output-enhanced", output_enhanced_path,
        "--models-dir", str(models_dir)
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="ignore").strip()
        logger.error(f"Error en extract_id_engine: {err_msg}")
        raise RuntimeError(f"Fallo al procesar credencial: {err_msg}")

    try:
        raw_output = stdout.decode("utf-8", errors="ignore").strip()
        # Tomar la última línea con formato JSON
        json_line = [line for line in raw_output.splitlines() if line.startswith("{")][-1]
        data = json.loads(json_line)
        return data
    except Exception as e:
        logger.error(f"Error parseando resultado de extracción: {e}, Raw: {stdout}")
        raise RuntimeError(f"Error procesando resultado: {e}")
