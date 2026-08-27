"""
config.py — Configuración Central de Onboarded
"""

import os
from pathlib import Path

# Rutas Base del Repositorio
REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = REPO_ROOT.parent.parent

# Directorios de Datos
DATA_DIR = REPO_ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
BUFFERS_DIR = DATA_DIR / "buffers"
SESSIONS_DIR = DATA_DIR / "sessions"
PRESETS_DIR = DATA_DIR / "presets"
SCRIPTS_DIR = REPO_ROOT / "scripts"
STATIC_DIR = REPO_ROOT / "static"

# Repositorios Externos y Modelos
DEEP_LIVE_CAM_DIR = WORKSPACE_ROOT / "repos" / "Deep-Live-Cam"
RITA_DIR = WORKSPACE_ROOT / "repos" / "rita"

# Crear directorios necesarios
for d in [UPLOADS_DIR, BUFFERS_DIR, SESSIONS_DIR, PRESETS_DIR, STATIC_DIR]:
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
