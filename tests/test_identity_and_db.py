"""
tests/test_identity_and_db.py — Suite de Pruebas de Jerarquía de Identidades & Base de Datos SQLite
Verifica la creación estructurada en data/identities/<NOMBRE_COMPLETO>/ y las operaciones CRUD de kcky.db.
"""

import os
import sys
import unittest
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.identity_manager import (
    sanitize_identity_name,
    infer_name_from_path,
    create_or_get_identity_session,
    IdentitySession
)
from src.db import (
    upsert_identity,
    get_identity,
    list_identities,
    register_account,
    update_account_status,
    record_kyc_session
)
from src.account_automator import automator
from src.config import IDENTITIES_DIR, DB_PATH
import asyncio


class TestIdentityAndDB(unittest.TestCase):

    def setUp(self):
        self.test_name = "TEST_USUARIO_VERIFICACION"
        self.test_folder = IDENTITIES_DIR / self.test_name
        if self.test_folder.exists():
            shutil.rmtree(self.test_folder)

    def tearDown(self):
        if self.test_folder.exists():
            shutil.rmtree(self.test_folder)

    def test_sanitize_identity_name(self):
        """Verifica la sanitización a mayúsculas con guiones bajos sin acentos."""
        self.assertEqual(sanitize_identity_name("Blanca Estrella Quintero Frías"), "BLANCA_ESTRELLA_QUINTERO_FRIAS")
        self.assertEqual(sanitize_identity_name("josé ángel lópez  pérez"), "JOSE_ANGEL_LOPEZ_PEREZ")
        self.assertEqual(sanitize_identity_name("  --María__del_Carmen-- "), "MARIA_DEL_CARMEN")

    def test_infer_name_from_path(self):
        """Verifica la inferencia de nombres desde rutas de archivo."""
        path = r"C:\Users\rober\Dropbox\INEs Edit\BLANCA ESTRELLA QUINTERO FRIAS\FRONT.jpeg"
        inferred = infer_name_from_path(path)
        self.assertEqual(inferred, "BLANCA ESTRELLA QUINTERO FRIAS")

    def test_identity_session_hierarchy(self):
        """Verifica que se creen las subcarpetas inputs/, assets/, outputs/."""
        session = IdentitySession(self.test_name)
        self.assertTrue(session.root_dir.is_dir())
        self.assertTrue(session.inputs_dir.is_dir())
        self.assertTrue(session.assets_dir.is_dir())
        self.assertTrue(session.outputs_dir.is_dir())

    def test_database_crud_flow(self):
        """Verifica el ciclo de vida completo en SQLite kcky.db."""
        session = IdentitySession(self.test_name)
        
        # 1. Guardar Identidad
        record = session.commit_to_database(
            full_name="Test Usuario Verificacion",
            demographics={"curp": "TEST900101HMCTST01", "gender": "Hombre"},
            arcface_score=94.5
        )
        self.assertEqual(record["full_name"], "Test Usuario Verificacion")
        self.assertEqual(record["curp"], "TEST900101HMCTST01")

        # 2. Consultar Identidad
        fetched = get_identity(self.test_name)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["id"], self.test_name)

        # 3. Registrar Cuenta de Plataforma
        acc = register_account(
            account_id=f"acc_{self.test_name}",
            identity_id=self.test_name,
            platform="BetMexico",
            username="bet_user_test",
            status="CREATING"
        )
        self.assertEqual(acc["status"], "CREATING")

        # 4. Actualizar Estado de Cuenta a CREATED y APPROVED
        update_account_status(f"acc_{self.test_name}", "CREATED")
        update_account_status(f"acc_{self.test_name}", "APPROVED")

        # 5. Registrar Sesión KYC
        kyc = record_kyc_session(
            session_id="kyc_test_001",
            identity_id=self.test_name,
            preset_used="female_clean_kyc_base.mp4",
            similarity_score=0.88,
            outcome="APPROVED",
            account_id=f"acc_{self.test_name}"
        )
        self.assertEqual(kyc["outcome"], "APPROVED")
        self.assertEqual(kyc["similarity_score"], 0.88)

    def test_account_automator_background_hook(self):
        """Verifica la ejecución no bloqueante del hook de creación de cuenta."""
        session = IdentitySession(self.test_name)
        session.commit_to_database(
            full_name="Test Usuario Auto",
            demographics={"curp": "AUTO900101HMCTST01"},
            arcface_score=95.0
        )
        
        acc_id = f"acc_auto_{self.test_name}"
        res = asyncio.run(
            automator.create_account_in_background(
                account_id=acc_id,
                identity_id=self.test_name,
                demographics={"curp": "AUTO900101HMCTST01"},
                credentials={"username": "auto_tester"}
            )
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["state"], "CREATED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
