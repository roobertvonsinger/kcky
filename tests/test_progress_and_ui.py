"""
tests/test_progress_and_ui.py — Verificación de Telemetría de Progreso y Estructura Mobile-First
"""

import sys
import os
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from src.server import app, state, broadcast_progress
import asyncio


class TestProgressAndUI(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_progress_telemetry(self):
        # 1. Verificar estado inicial
        res = self.client.get("/api/progress")
        self.assertEqual(res.status_code, 200, f"Error status: {res.status_code}")
        data = res.json()
        self.assertIn("percent", data)
        self.assertIn("eta_text", data)

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
        
        res2 = self.client.get("/api/progress")
        data2 = res2.json()
        self.assertEqual(data2["percent"], 45)
        self.assertEqual(data2["current_frame"], 135)
        self.assertEqual(data2["eta_text"], "12s")
        self.assertEqual(data2["phase"], "swapping")

    def test_html_dom_elements(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
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
            self.assertIn(f'id="{element_id}"', html, f"Missing element ID in HTML: {element_id}")
            
        # Validar shell mobile
        self.assertIn('class="mobile-shell"', html)
        self.assertIn('class="theme-monochrome"', html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
