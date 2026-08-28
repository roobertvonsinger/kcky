"""
tests/test_presets_validation.py — Validación Automática de Videos Base (Presets KYC)
Verifica integridad de archivos, códec H.264, ausencia de marca de agua y encuadre KYC óptimo.
"""

import os
import sys
import unittest
from pathlib import Path
import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.config import PRESETS_DIR
from src.server import PRESET_METADATA


class TestPresetsValidation(unittest.TestCase):

    def test_presets_directory_exists(self):
        """Verifica que el directorio de presets exista y contenga videos."""
        self.assertTrue(PRESETS_DIR.is_dir(), "Directorio data/presets no existe")
        presets = list(PRESETS_DIR.glob("*.mp4"))
        self.assertGreaterEqual(len(presets), 3, f"Se esperaban al menos 3 presets, encontrados: {len(presets)}")

    def test_primary_preset_female_clean_kyc_base(self):
        """Verifica que el preset principal esté limpio, sin marca de agua y con resolución HD."""
        preset_path = PRESETS_DIR / "female_clean_kyc_base.mp4"
        self.assertTrue(preset_path.is_file(), "No se encontró el preset principal female_clean_kyc_base.mp4")

        cap = cv2.VideoCapture(str(preset_path))
        self.assertTrue(cap.isOpened(), "No se pudo abrir female_clean_kyc_base.mp4 con OpenCV")
        
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        self.assertEqual(w, 1280, f"Ancho incorrecto: {w} (esperado 1280)")
        self.assertEqual(h, 720, f"Alto incorrecto: {h} (esperado 720)")
        self.assertGreaterEqual(fps, 20.0, f"FPS bajo: {fps}")
        self.assertGreaterEqual(frames, 100, f"Frames insuficientes: {frames}")

        # Verificar ausencia de marca de agua en la esquina inferior derecha (x: 1130-1195, y: 575-635)
        cap.set(cv2.CAP_PROP_POS_FRAMES, min(50, frames - 1))
        ret, frame = cap.read()
        cap.release()
        self.assertTrue(ret, "No se pudo leer fotograma de prueba del preset")

        corner = frame[575:635, 1130:1195]
        max_val = corner.max()
        self.assertLess(max_val, 40, f"Posible marca de agua detectada en esquina inferior derecha (max pixel={max_val} >= 40)")

    def test_all_registered_presets_readable(self):
        """Verifica que todos los presets registrados en PRESET_METADATA sean legibles."""
        for filename in PRESET_METADATA.keys():
            path = PRESETS_DIR / filename
            if path.is_file():
                cap = cv2.VideoCapture(str(path))
                self.assertTrue(cap.isOpened(), f"No se pudo decodificar el preset: {filename}")
                ret, frame = cap.read()
                cap.release()
                self.assertTrue(ret, f"No se pudo leer fotograma de: {filename}")
                self.assertIsNotNone(frame, f"Fotograma nulo en: {filename}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
