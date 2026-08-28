"""
tests/run_all_tests.py — Orquestador Maestro de Pruebas Automatizadas de KCKY Studio
Ejecuta la suite completa de pruebas organizada en niveles (Biometría, Presets, UI, API).
"""

import os
import sys
import time
import unittest
from pathlib import Path

# Fijar codificación UTF-8 para salida en Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
os.chdir(REPO_ROOT)

from tests.test_biometric_extraction import TestBiometricExtraction
from tests.test_presets_validation import TestPresetsValidation
from tests.test_progress_and_ui import TestProgressAndUI
from tests.test_server_api import TestServerAPI
from tests.test_identity_and_db import TestIdentityAndDB
from tests.test_account_automator_and_cdp import TestAccountAutomatorAndCDP


def run_test_suite():
    print("=" * 70)
    print(" 🧪 SUITE DE PRUEBAS AUTOMATIZADAS — K.C.K.Y. STUDIO (KCKY v2.5)")
    print("=" * 70)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        ("Biometria & Input Gate", TestBiometricExtraction),
        ("Presets & Marca de Agua", TestPresetsValidation),
        ("Telemetria UI & Dom", TestProgressAndUI),
        ("API REST & Endpoints", TestServerAPI),
        ("Identidades & BD SQLite", TestIdentityAndDB),
        ("Autofill & CDP Injector", TestAccountAutomatorAndCDP)
    ]

    total_tests = 0
    start_time = time.time()

    for name, test_class in test_classes:
        try:
            mod_suite = loader.loadTestsFromTestCase(test_class)
            suite.addTests(mod_suite)
            count = mod_suite.countTestCases()
            total_tests += count
            print(f" [+] Modulo cargado: {name:<26} ({count} pruebas)")
        except Exception as e:
            print(f" [!] Error cargando {test_class}: {e}")

    print("-" * 70)
    print(f" Ejecutando {total_tests} pruebas automatizadas...\n")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    elapsed = time.time() - start_time

    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print(f" 🎉 TODAS LAS PRUEBAS PASARON EXITOSAMENTE (100% OK)")
        print(f" 📊 Total: {result.testsRun} ejecutadas | Fallos: 0 | Errores: 0 | ⏱️ {elapsed:.2f}s")
        print("=" * 70)
        return 0
    else:
        print(f" ❌ HUBO FALLOS EN LA SUITE DE PRUEBAS")
        print(f" 📊 Total: {result.testsRun} | Fallos: {len(result.failures)} | Errores: {len(result.errors)} | ⏱️ {elapsed:.2f}s")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(run_test_suite())
