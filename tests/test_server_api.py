"""
tests/test_server_api.py — Suite de Pruebas de Integración de la API REST / FastAPI
Verifica endpoints de presets, hardware personas, subida de archivos, y extracción de credenciales.
"""

import os
import sys
import unittest
from pathlib import Path
import io
import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from src.server import app


class TestServerAPI(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_root_and_dom_integrity(self):
        """Verifica que el dashboard web cargue con HTTP 200 y contenga los componentes clave."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("KCKY Studio", res.text)
        self.assertIn("progress-bar-fill", res.text)

    def test_get_presets_endpoint(self):
        """Verifica que /api/presets retorne la lista de videos base disponibles con metadatos."""
        res = self.client.get("/api/presets")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("presets", data)
        self.assertIsInstance(data["presets"], list)
        self.assertGreaterEqual(len(data["presets"]), 1)
        
        first = data["presets"][0]
        self.assertIn("id", first)
        self.assertIn("name", first)
        self.assertIn("resolution", first)
        self.assertIn("preview_url", first)

    def test_get_hardware_personas_endpoint(self):
        """Verifica que /api/hardware-personas retorne los perfiles de webcam física."""
        res = self.client.get("/api/hardware-personas")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("personas", data)
        self.assertIn("logitech_c920", data["personas"])

    def test_get_virtual_cam_status(self):
        """Verifica el endpoint de estado de la cámara virtual."""
        res = self.client.get("/api/virtual-cam/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("active", data)

    def test_upload_face_valid_image(self):
        """Verifica la carga de un archivo de rostro válido."""
        # Generar imagen JPEG en memoria
        img = np.full((120, 120, 3), 180, dtype=np.uint8)
        _, buf = cv2.imencode(".jpg", img)
        file_bytes = io.BytesIO(buf.tobytes())

        res = self.client.post(
            "/api/upload-face",
            files={"file": ("test_face.jpg", file_bytes, "image/jpeg")}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("file_path", data)
        self.assertTrue(os.path.exists(data["file_path"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
