"""
tests/test_biometric_extraction.py — Suite de Pruebas Unitarias de Extracción y Biometría Facial
Verifica: Input Gate, Clasificación INE/Selfie, Color Match LAB, Feather Blend, y ArcFace Similarity.
"""

import os
import sys
import unittest
from pathlib import Path
import numpy as np
import cv2

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.extract_id_engine import (
    evaluate_input_gate,
    match_color_lab,
    feather_blend_face,
    verify_arcface_similarity,
    detect_and_classify_input,
    process_id_card
)
from src.config import MODELS_DIR, UPLOADS_DIR


class TestBiometricExtraction(unittest.TestCase):
    
    def setUp(self):
        # Crear imagen sintética nítida para pruebas de Input Gate
        self.sharp_img = np.zeros((300, 300, 3), dtype=np.uint8)
        cv2.circle(self.sharp_img, (150, 150), 80, (200, 200, 200), -1)
        cv2.rectangle(self.sharp_img, (100, 100), (200, 200), (50, 50, 50), 3)

        # Imagen borrosa
        self.blurry_img = cv2.GaussianBlur(self.sharp_img, (31, 31), 15.0)

        # Imagen demasiado oscura
        self.dark_img = np.full((300, 300, 3), 10, dtype=np.uint8)

    def test_input_gate_sharpness(self):
        """Verifica que el Input Gate apruebe imágenes nítidas y rechace imágenes borrosas."""
        res_sharp = evaluate_input_gate(self.sharp_img)
        self.assertTrue(res_sharp["is_sharp"], f"Fallo en detección de nitidez: {res_sharp}")

        res_blur = evaluate_input_gate(self.blurry_img)
        self.assertFalse(res_blur["is_sharp"], f"No detectó imagen borrosa: {res_blur}")
        self.assertLess(res_blur["blur_score"], 50.0)

    def test_input_gate_luminance(self):
        """Verifica que el Input Gate detecte iluminación insuficiente."""
        res_dark = evaluate_input_gate(self.dark_img)
        self.assertFalse(res_dark["is_well_lit"], f"No rechazó imagen oscura: {res_dark}")

    def test_color_match_lab(self):
        """Verifica la transferencia cromática Reinhard en espacio L*a*b*."""
        src = np.full((100, 100, 3), (50, 120, 200), dtype=np.uint8) # Tonalidad cálida
        tgt = np.full((100, 100, 3), (200, 100, 50), dtype=np.uint8) # Tonalidad fría
        
        matched = match_color_lab(source_bgr=src, target_bgr=tgt)
        self.assertEqual(matched.shape, tgt.shape)
        # La media debe aproximarse a la fuente
        src_mean = cv2.cvtColor(src, cv2.COLOR_BGR2LAB)[:, :, 0].mean()
        matched_mean = cv2.cvtColor(matched, cv2.COLOR_BGR2LAB)[:, :, 0].mean()
        self.assertAlmostEqual(src_mean, matched_mean, delta=15.0)

    def test_feather_blend_face(self):
        """Verifica la reintegración anatómica elíptica con degradado gaussiano."""
        base = np.zeros((200, 200, 3), dtype=np.uint8)
        restored = np.full((200, 200, 3), 255, dtype=np.uint8)
        
        blended = feather_blend_face(base, restored, feather_px=20)
        self.assertEqual(blended.shape, (200, 200, 3))
        # Centro debe ser cercano a 255 (núcleo facial)
        center_val = blended[100, 100, 0]
        self.assertGreater(center_val, 200)
        # Esquinas deben ser cercanas a 0 (fondo base preservado)
        corner_val = blended[5, 5, 0]
        self.assertLess(corner_val, 50)

    def test_arcface_similarity_calculation(self):
        """Verifica el cálculo de similitud coseno con ArcFace."""
        face1 = np.full((112, 112, 3), 128, dtype=np.uint8)
        cv2.circle(face1, (56, 56), 30, (220, 180, 150), -1)
        
        res = verify_arcface_similarity(face1, face1, str(MODELS_DIR))
        self.assertIn("similarity", res)
        self.assertIn("match_percentage", res)
        self.assertGreaterEqual(res["similarity"], 0.70)


if __name__ == "__main__":
    unittest.main(verbosity=2)
