"""
dependency_manager.py — Gestor Autónomo de Dependencias y Descarga Automática de Modelos IA para KCKY
Asegura que el entorno esté 100% listo para ejecutarse sin configuración manual previa.
"""

import importlib
import logging
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Dict, List

from src.config import REPO_ROOT, MODELS_DIR, DEEP_LIVE_CAM_DIR

logger = logging.getLogger("KCKY_Dependencies")

# Enlaces a modelos ONNX oficiales en HuggingFace / GitHub
AI_MODELS_MANIFEST: Dict[str, Dict[str, str]] = {
    "gfpgan-1024.onnx": {
        "url": "https://huggingface.co/hacksider/deep-live-cam/resolve/main/gfpgan-1024.onnx",
        "description": "GFPGAN 1024 HD Face Restorer",
        "size_mb": 340
    },
    "GPEN-BFR-512.onnx": {
        "url": "https://huggingface.co/hacksider/deep-live-cam/resolve/main/GPEN-BFR-512.onnx",
        "description": "GPEN 512 Face Restoration",
        "size_mb": 280
    },
    "inswapper_128.onnx": {
        "url": "https://huggingface.co/hacksider/deep-live-cam/resolve/main/inswapper_128.onnx",
        "description": "InsightFace Inswapper 128",
        "size_mb": 528
    }
}


def check_and_install_python_packages():
    """Verifica e instala automáticamente las dependencias de Python faltantes de requirements.txt."""
    req_file = REPO_ROOT / "requirements.txt"
    if not req_file.is_file():
        return

    required_modules = [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("cv2", "opencv-python"),
        ("numpy", "numpy"),
        ("scipy", "scipy"),
        ("playwright", "playwright"),
        ("pyvirtualcam", "pyvirtualcam")
    ]

    missing = []
    for mod_name, pkg_name in required_modules:
        try:
            importlib.import_module(mod_name)
        except ImportError:
            missing.append(pkg_name)

    if missing:
        print(f"[*] KCKY: Instalando dependencias de Python faltantes: {', '.join(missing)}...")
        try:
            cmd = [sys.executable, "-m", "pip", "install", *missing]
            subprocess.run(cmd, check=True)
            print("[+] KCKY: Dependencias instaladas exitosamente.")
        except Exception as e:
            print(f"[!] Advertencia al auto-instalar paquetes en KCKY: {e}", file=sys.stderr)


def download_file_with_progress(url: str, destination: Path, desc: str):
    """Descarga un archivo con feedback visual en consola."""
    print(f"[*] KCKY: Descargando {desc} ({destination.name})...")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_dest = destination.with_suffix(".tmp")

    def _progress_hook(block_num, block_size, total_size):
        if total_size > 0:
            percent = min(100, int(block_num * block_size * 100 / total_size))
            downloaded_mb = (block_num * block_size) / (1024 * 1024)
            total_mb = total_size / (1024 * 1024)
            sys.stdout.write(f"\r    -> Progreso: {percent}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)")
            sys.stdout.flush()

    try:
        urllib.request.urlretrieve(url, temp_dest, reporthook=_progress_hook)
        sys.stdout.write("\n")
        if temp_dest.is_file():
            temp_dest.replace(destination)
        print(f"[+] KCKY: {desc} descargado correctamente.")
    except Exception as e:
        sys.stdout.write("\n")
        if temp_dest.is_file():
            temp_dest.unlink(missing_ok=True)
        print(f"[!] Error al descargar {destination.name}: {e}", file=sys.stderr)


def ensure_ai_models():
    """Verifica la existencia de los modelos ONNX y los descarga automáticamente si no están."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    dlc_models_dir = DEEP_LIVE_CAM_DIR / "models"

    for model_name, info in AI_MODELS_MANIFEST.items():
        local_path = MODELS_DIR / model_name
        dlc_path = dlc_models_dir / model_name

        if local_path.is_file() or (dlc_path.is_file() and dlc_path.stat().st_size > 1000):
            continue

        if model_name in ["gfpgan-1024.onnx", "GPEN-BFR-512.onnx"]:
            download_file_with_progress(info["url"], local_path, info["description"])


def ensure_playwright_browsers():
    """Asegura que los binarios de Chromium de Playwright estén instalados."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
                browser.close()
            except Exception:
                print("[*] KCKY: Instalando Chromium para Playwright...")
                subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    except Exception:
        pass


def run_preflight_checks():
    """Ejecuta todas las verificaciones previas al arranque de KCKY."""
    check_and_install_python_packages()
    ensure_ai_models()
