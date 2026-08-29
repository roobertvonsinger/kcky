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
        "desc": "Estándar de la industria, menor scoring de riesgo en KYC.",
        # Fingerprint de hardware para evasión anti-bot completa
        "gpu_vendor": "Google Inc. (AMD)",
        "gpu_renderer": "ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "hardware_concurrency": 8,
        "device_memory": 8,
        "max_touch_points": 0,
        "platform": "Win32",
        "screen_width": 1920,
        "screen_height": 1080,
        "screen_color_depth": 24,
        "pixel_ratio": 1.0,
    },
    "integrated": {
        "name": "Integrated Camera",
        "vid": "04F2",
        "pid": "B614",
        "label": "Integrated Camera (04f2:b614)",
        "mic_label": "Microphone (Realtek(R) Audio)",
        "desc": "Cámara OEM para laptops Windows 10/11.",
        "gpu_vendor": "Google Inc. (Intel)",
        "gpu_renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "hardware_concurrency": 8,
        "device_memory": 8,
        "max_touch_points": 0,
        "platform": "Win32",
        "screen_width": 1920,
        "screen_height": 1080,
        "screen_color_depth": 24,
        "pixel_ratio": 1.0,
    },
    "hp_wide": {
        "name": "HP Wide Vision HD Camera",
        "vid": "05C8",
        "pid": "03A2",
        "label": "HP Wide Vision HD Camera",
        "mic_label": "Internal Microphone (Conexant ISST Audio)",
        "desc": "Emulación nativa de equipos HP Pavilion / Envy.",
        "gpu_vendor": "Google Inc. (Intel)",
        "gpu_renderer": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "hardware_concurrency": 12,
        "device_memory": 16,
        "max_touch_points": 10,
        "platform": "Win32",
        "screen_width": 1920,
        "screen_height": 1080,
        "screen_color_depth": 24,
        "pixel_ratio": 1.5,
    }
}


def resolve_media_path(path_str: Optional[str]) -> Optional[str]:
    """
    Resuelve de forma tolerante a fallos cualquier ruta de archivo de medios en KCKY
    (rutas absolutas Windows, relativas a REPO_ROOT, relativas a DATA_DIR, URLs web /data/... o nombres de presets).
    """
    if not path_str:
        return None

    clean_str = path_str.strip()

    # 1. Si es ruta absoluta Windows existente (ej. C:\...)
    try:
        p = Path(clean_str)
        if p.is_absolute() and p.is_file():
            return str(p)
    except Exception:
        pass

    # 2. Si viene como URL web (ej. "/data/identities/.../assets/enhanced.png" o "/data/presets/...")
    norm_str = clean_str.replace("\\", "/")
    if norm_str.startswith("/data/") or norm_str.startswith("data/"):
        sub = norm_str.split("data/", 1)[1].lstrip("/")
        cand = (DATA_DIR / sub).resolve()
        if cand.is_file():
            return str(cand)

    # 3. Relativo directo a DATA_DIR
    rel_clean = clean_str.lstrip("/\\")
    cand = (DATA_DIR / rel_clean).resolve()
    if cand.is_file():
        return str(cand)

    # 4. Relativo a REPO_ROOT
    cand = (REPO_ROOT / rel_clean).resolve()
    if cand.is_file():
        return str(cand)

    # 5. Por nombre de archivo en PRESETS_DIR
    try:
        cand = (PRESETS_DIR / Path(clean_str).name).resolve()
        if cand.is_file():
            return str(cand)
    except Exception:
        pass

    # 6. Por nombre de archivo en UPLOADS_DIR
    try:
        cand = (UPLOADS_DIR / Path(clean_str).name).resolve()
        if cand.is_file():
            return str(cand)
    except Exception:
        pass

    return None
