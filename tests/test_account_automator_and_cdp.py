"""
test_account_automator_and_cdp.py — Pruebas de Autofill en Segundo Plano & Inyección Documental CDP (KCKY v2.5)
"""

import os
import sys
import unittest
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.account_automator import automator, AccountAutomator
from src.identity_manager import create_or_get_identity_session
from src.server import ensure_preset_thumbnail, PRESET_METADATA, app
from src.config import PRESETS_DIR, IDENTITIES_DIR
from src.db import get_identity
from fastapi.testclient import TestClient


class TestAccountAutomatorAndCDP(unittest.TestCase):
    """Pruebas para el automador de cuentas BetMexico y la inyección documental por CDP."""

    def setUp(self):
        self.automator = AccountAutomator(platform="BetMexico")
        self.test_identity_name = "TEST_CDP_AUTOFILL_USER"
        self.session = create_or_get_identity_session(self.test_identity_name)
        # Asegurar que la identidad esté registrada en BD para FK de accounts
        self.session.commit_to_database(full_name="Test CDP Autofill User")
        # Limpiar inputs_dir para pruebas aisladas
        for f in self.session.inputs_dir.glob("*"):
            try:
                f.unlink()
            except Exception:
                pass

    def tearDown(self):
        for f in self.session.inputs_dir.glob("*"):
            try:
                f.unlink()
            except Exception:
                pass

    def test_demographic_parsing_and_field_normalization(self):
        """Verifica la extracción y normalización de campos para el registro en BetMexico."""
        demographics = {
            "full_name": "MARIA ELENA HERNANDEZ LOPEZ",
            "curp": "HELM850315MDFRPR01",
            "gender": "Mujer",
            "birth_date": "1985-03-15",
            "address": "AV INSURGENTES SUR 123 CDMX"
        }
        credentials = {
            "username": "maria_elena_test",
            "email": "maria.test@example.com",
            "phone": "5512345678"
        }
        fields = self.automator.parse_demographic_fields(demographics, credentials)

        self.assertEqual(fields["first_name"], "MARIA ELENA")
        self.assertEqual(fields["last_name"], "HERNANDEZ")
        self.assertEqual(fields["second_last_name"], "LOPEZ")
        self.assertEqual(fields["curp"], "HELM850315MDFRPR01")
        self.assertEqual(fields["gender_code"], "M")
        self.assertEqual(fields["birth_date"], "1985-03-15")
        self.assertEqual(fields["username"], "maria_elena_test")
        self.assertEqual(fields["email"], "maria.test@example.com")
        self.assertEqual(fields["phone"], "5512345678")

    def test_get_identity_documents_resolution(self):
        """Verifica la detección tolerante a formatos de documentos (front, back, domicilio)."""
        # Crear archivos simulados en la carpeta de la identidad
        front_file = self.session.inputs_dir / "front.jpg"
        back_file = self.session.inputs_dir / "back.png"
        domicilio_file = self.session.inputs_dir / "domicilio.jpeg"

        front_file.write_bytes(b"mock_front_data")
        back_file.write_bytes(b"mock_back_data")
        domicilio_file.write_bytes(b"mock_domicilio_data")

        docs = self.automator.get_identity_documents(str(self.session.root_dir))
        self.assertIsNotNone(docs["front"])
        self.assertTrue(docs["front"].endswith("front.jpg"))
        self.assertIsNotNone(docs["back"])
        self.assertTrue(docs["back"].endswith("back.png"))
        self.assertIsNotNone(docs["domicilio"])
        self.assertTrue(docs["domicilio"].endswith("domicilio.jpeg"))

    def test_background_account_creation_persistence(self):
        """Verifica que create_account_in_background persista la cuenta en SQLite y retorne status success."""
        demographics = {
            "full_name": "CARLOS ALBERTO RAMIREZ PEREZ",
            "curp": "RAPC900101HDFRRN02",
            "gender": "Hombre"
        }
        acc_id = f"acc_test_{self.session.canonical_name}"
        
        loop = asyncio.new_event_loop()
        res = loop.run_until_complete(
            self.automator.create_account_in_background(
                account_id=acc_id,
                identity_id=self.session.canonical_name,
                demographics=demographics
            )
        )
        loop.close()

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["state"], "CREATED")
        self.assertEqual(res["fields"]["curp"], "RAPC900101HDFRRN02")

    def test_cdp_file_chooser_auto_selection(self):
        """Verifica que el interceptor filechooser inyecte automáticamente el documento correcto."""
        front_file = self.session.inputs_dir / "front.jpg"
        back_file = self.session.inputs_dir / "back.jpg"
        front_file.write_bytes(b"front_content")
        back_file.write_bytes(b"back_content")

        # Mock de Playwright FileChooser
        mock_file_chooser = AsyncMock()
        mock_file_chooser.set_files = AsyncMock()

        loop = asyncio.new_event_loop()
        # Primer llamado -> Debe inyectar front
        ok1 = loop.run_until_complete(
            self.automator.handle_file_chooser(mock_file_chooser, str(self.session.root_dir))
        )
        self.assertTrue(ok1)
        mock_file_chooser.set_files.assert_called_with(str(front_file))

        # Segundo llamado -> Debe inyectar back
        ok2 = loop.run_until_complete(
            self.automator.handle_file_chooser(mock_file_chooser, str(self.session.root_dir))
        )
        self.assertTrue(ok2)
        mock_file_chooser.set_files.assert_called_with(str(back_file))
        loop.close()

    def test_cdp_document_injection_simulation(self):
        """Verifica la inyección de documentos en inputs <input type='file'> vía CDP."""
        front_file = self.session.inputs_dir / "front.jpg"
        front_file.write_bytes(b"front_content")

        # Mock de Page y ElementHandle de Playwright
        mock_page = AsyncMock()
        mock_input = AsyncMock()
        mock_input.get_attribute = AsyncMock(side_effect=lambda attr: "id_front" if attr == "name" else "")
        mock_input.set_input_files = AsyncMock()
        mock_page.query_selector_all = AsyncMock(return_value=[mock_input])

        loop = asyncio.new_event_loop()
        res = loop.run_until_complete(
            self.automator.auto_upload_kyc_documents_cdp(
                mock_page,
                str(self.session.root_dir),
                account_id="acc_mock_test"
            )
        )
        loop.close()

        self.assertEqual(res["status"], "success")
        self.assertIn("front.jpg", res["injected_documents"])
        mock_input.set_input_files.assert_called_with(str(front_file))

    def test_preset_thumbnail_generation_and_metadata(self):
        """Verifica que ensure_preset_thumbnail genere archivos JPEG legibles y /api/presets los exponga."""
        clean_preset = PRESETS_DIR / "female_clean_kyc_base.mp4"
        if clean_preset.is_file():
            thumb_url = ensure_preset_thumbnail(clean_preset)
            self.assertTrue(thumb_url.startswith("/data/presets/thumbnails/"))
            
            thumb_path = PRESETS_DIR / "thumbnails" / f"{clean_preset.stem}.jpg"
            self.assertTrue(thumb_path.is_file())
            self.assertGreater(thumb_path.stat().st_size, 0)

        # Probar endpoint /api/presets con TestClient
        client = TestClient(app)
        resp = client.get("/api/presets")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("presets", data)
        self.assertGreater(len(data["presets"]), 0)
        first_preset = data["presets"][0]
        self.assertIn("thumbnail_url", first_preset)
        self.assertIn("badge", first_preset)

    def test_email_rotator_dot_trick_sequence(self):
        """Verifica que get_all_dot_aliases genere alias de 1 punto de derecha a izquierda round-robin."""
        from src.email_rotator import get_all_dot_aliases, generate_dot_variations_for_user
        
        vars_01 = generate_dot_variations_for_user("retirobetmex01")
        self.assertEqual(vars_01[0], "retirobetmex0.1")
        self.assertEqual(vars_01[-1], "r.etirobetmex01")
        
        all_aliases = get_all_dot_aliases(["retirobetmex01@gmail.com", "retirobetmex02@gmail.com"])
        self.assertEqual(all_aliases[0]["alias_email"], "retirobetmex0.1@gmail.com")
        self.assertEqual(all_aliases[1]["alias_email"], "retirobetmex0.2@gmail.com")

    def test_email_rotator_tracking_and_claiming(self):
        """Verifica la reserva atómica y tracking de alias en email_rotator_tracker."""
        from src.email_rotator import get_next_available_email, mark_email_as_used, get_and_claim_next_email
        import sqlite3
        
        # Usar base de datos en memoria para aislamiento absoluto del test
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE accounts (id TEXT PRIMARY KEY, email TEXT)")
        conn.commit()
        
        try:
            claimed = get_and_claim_next_email(conn, account_id="acc_unit_test_claim")
            self.assertIn("@gmail.com", claimed["alias_email"])
            
            # El siguiente llamado debe retornar un alias distinto
            claimed_next = get_and_claim_next_email(conn, account_id="acc_unit_test_claim_2")
            self.assertNotEqual(claimed["alias_email"], claimed_next["alias_email"])
        finally:
            conn.close()

    def test_realistic_mx_phone_generation(self):
        """Verifica la generación de teléfonos celulares mexicanos válidos a 10 dígitos."""
        from src.account_automator import generate_realistic_mx_phone
        phone1 = generate_realistic_mx_phone("CURP12345678")
        self.assertEqual(len(phone1), 10)
        self.assertTrue(phone1.isdigit())
        
        phone2 = generate_realistic_mx_phone()
        self.assertEqual(len(phone2), 10)
        self.assertTrue(phone2.isdigit())

    def test_submit_registration_form_cdp(self):
        """Verifica el envío del formulario de registro y click en botón #register."""
        mock_page = AsyncMock()
        mock_btn = AsyncMock()
        mock_btn.is_visible = AsyncMock(return_value=True)
        mock_btn.click = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=mock_btn)
        mock_page.wait_for_selector = AsyncMock(side_effect=Exception("No modal"))

        loop = asyncio.new_event_loop()
        ok = loop.run_until_complete(
            self.automator.submit_registration_form_cdp(mock_page)
        )
        loop.close()

        self.assertTrue(ok)
        mock_btn.click.assert_called_once()

    def test_handle_facial_verification_cdp(self):
        """Verifica la detección del modal 'Verificación facial' y el click de captura de selfie."""
        mock_page = AsyncMock()
        mock_btn = AsyncMock()
        mock_btn.is_visible = AsyncMock(return_value=True)
        mock_btn.click = AsyncMock()
        mock_page.wait_for_selector = AsyncMock(return_value=mock_btn)

        loop = asyncio.new_event_loop()
        ok = loop.run_until_complete(
            self.automator.handle_facial_verification_cdp(mock_page, account_id="acc_facial_test")
        )
        loop.close()

        self.assertTrue(ok)
        mock_btn.click.assert_called_once()

    def test_api_inject_documents_cdp_validation(self):
        """Verifica el endpoint REST /api/identities/{identity_id}/inject-documents-cdp."""
        client = TestClient(app)
        # Sin navegador activo debe rechazar con HTTP 400
        resp = client.post(f"/api/identities/{self.session.canonical_name}/inject-documents-cdp")
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
