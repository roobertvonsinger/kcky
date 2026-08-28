"""
config.py — Configuración Central de KCKY (K.C.K.Y. Studio)
"""

import os
from pathlib import Path
from typing import Optional

# Rutas Base del Repositorio
REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = REPO_ROOT.parent.parent

# Directorios de Datos
DATA_DIR = REPO_ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
BUFFERS_DIR = DATA_DIR / "buffers"
SESSIONS_DIR = DATA_DIR / "sessions"
PRESETS_DIR = DATA_DIR / "presets"
IDENTITIES_DIR = DATA_DIR / "identities"
MODELS_DIR = REPO_ROOT / "models"
SCRIPTS_DIR = REPO_ROOT / "scripts"
STATIC_DIR = REPO_ROOT / "static"
DB_PATH = DATA_DIR / "kcky.db"

# Repositorios Externos y Modelos
DEEP_LIVE_CAM_DIR = WORKSPACE_ROOT / "repos" / "Deep-Live-Cam"
RITA_DIR = WORKSPACE_ROOT / "repos" / "rita"

# Crear directorios necesarios
for d in [UPLOADS_DIR, BUFFERS_DIR, SESSIONS_DIR, PRESETS_DIR, IDENTITIES_DIR, MODELS_DIR, STATIC_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Servidor Web
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

# Presets de Hardware de Cámara
HARDWARE_PERSONAS = {
    "logitech_c920": {
        "name": "Logitech HD Pro Webcam C920",
        "vid": "046D",
        "pid": "082D",
        "label": "Logitech HD Pro Webcam C920",
        "mic_label": "Microphone (Logitech HD Pro Webcam C920)",
        "desc": "Estándar de la industria, menor scoring de riesgo en KYC."
    },
    "integrated": {
        "name": "Integrated Camera",
        "vid": "04F2",
        "pid": "B614",
        "label": "Integrated Camera (04f2:b614)",
        "mic_label": "Microphone (Realtek(R) Audio)",
        "desc": "Cámara OEM para laptops Windows 10/11."
    },
    "hp_wide": {
        "name": "HP Wide Vision HD Camera",
        "vid": "05C8",
        "pid": "03A2",
        "label": "HP Wide Vision HD Camera",
        "mic_label": "Internal Microphone (Conexant ISST Audio)",
        "desc": "Emulación nativa de equipos HP Pavilion / Envy."
    }
}


def resolve_media_path(path_str: Optional[str]) -> Optional[str]:
    """
    Resuelve de forma tolerante a fallos cualquier ruta de archivo de medios en KCKY
    (rutas absolutas, relativas a REPO_ROOT, relativas a DATA_DIR o nombres simples de presets).
    """
    if not path_str:
        return None

    p = Path(path_str)
    # 1. Si ya es ruta absoluta y existe
    if p.is_absolute() and p.is_file():
        return str(p)

    # 2. Relativo a REPO_ROOT (repos/kcky)
    candidate = (REPO_ROOT / p).resolve()
    if candidate.is_file():
        return str(candidate)

    # 3. Relativo a DATA_DIR
    candidate = (DATA_DIR / p).resolve()
    if candidate.is_file():
        return str(candidate)

    # 4. En la carpeta de presets (por nombre de archivo)
    candidate = (PRESETS_DIR / p.name).resolve()
    if candidate.is_file():
        return str(candidate)

    # 5. En la carpeta de uploads
    candidate = (UPLOADS_DIR / p.name).resolve()
    if candidate.is_file():
        return str(candidate)

    # 6. Fallback a presets por defecto si es target de video
    default_preset = PRESETS_DIR / "female_clean_kyc_base.mp4"
    if default_preset.is_file():
        return str(default_preset)

    return None
