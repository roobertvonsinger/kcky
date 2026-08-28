"""
test_progress_and_ui.py — Verificación de Telemetría de Progreso y Estructura Mobile-First
"""

import sys
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from src.server import app, state, broadcast_progress
import asyncio

def test_progress_telemetry():
    client = TestClient(app)
    
    # 1. Verificar estado inicial
    res = client.get("/api/progress")
    assert res.status_code == 200, f"Error status: {res.status_code}"
    data = res.json()
    assert "percent" in data
    assert "eta_text" in data
    print("[PASS] Initial /api/progress response valid:", data)

    # 2. Simular actualización de progreso
    test_prog = {
        "percent": 45,
        "current_frame": 135,
        "total_frames": 300,
        "eta_text": "12s",
        "speed_text": "11.2 fps",
        "status_text": "Sintetizando fotograma 135 de 300 (11.2 fps)",
        "phase": "swapping"
    }
    asyncio.run(broadcast_progress(test_prog))
    
    res2 = client.get("/api/progress")
    data2 = res2.json()
    assert data2["percent"] == 45
    assert data2["current_frame"] == 135
    assert data2["eta_text"] == "12s"
    assert data2["phase"] == "swapping"
    print("[PASS] Broadcast progress updated state successfully:", data2)

def test_html_dom_elements():
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    html = res.text
    
    # Validar elementos clave de la barra de progreso
    required_ids = [
        "progress-percent-num",
        "progress-bar-fill",
        "progress-status-msg",
        "progress-frames-txt",
        "progress-eta-txt",
        "monitor-progress-layer",
        "seg-1", "seg-2", "seg-3",
        "step-panel-1", "step-panel-2", "step-panel-3",
        "identity-dropzone",
        "card-mode-swap", "card-mode-synthetic",
        "btn-launch-browser-action",
        "btn-toggle-vcam",
        "btn-download-video"
    ]
    
    for element_id in required_ids:
        assert f'id="{element_id}"' in html, f"Missing element ID in HTML: {element_id}"
        
    # Validar shell mobile
    assert 'class="mobile-shell"' in html
    assert 'class="theme-monochrome"' in html
    print(f"[PASS] All {len(required_ids)} required DOM element IDs verified in index.html")

if __name__ == "__main__":
    print("=== INICIANDO AUDITORÍA TÉCNICA DE TELEMETRÍA Y UI ===")
    test_progress_telemetry()
    test_html_dom_elements()
    print("=== TODOS LOS TESTS PASARON EXITOSAMENTE ===")
