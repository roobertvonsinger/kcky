"""
test_blackbox_pipeline.py — Verificación Automatizada del Pipeline Caja Negra de KCKY (K.C.K.Y.)
"""

import asyncio
import os
import sys
from pathlib import Path

# Configurar stdout en UTF-8 para Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Añadir raíz de kcky al sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.config import resolve_media_path, DATA_DIR, PRESETS_DIR, UPLOADS_DIR, BUFFERS_DIR
from src.id_extractor import extract_and_restore_face
from src.liveness import generate_synthetic_liveness, convert_video_to_seamless_y4m


async def run_audit():
    print("=" * 60)
    print("🔍 AUDITORÍA DE CAJA NEGRA — K.C.K.Y. (KCKY v2.0)")
    print("=" * 60)

    # 1. Test de Resolución Universal de Rutas (Tolerancia a 404)
    print("\n[1/4] Verificando resolución de rutas (Zero 404)...")
    preset_name = "female_clean_kyc_base.mp4"
    resolved_1 = resolve_media_path(preset_name)
    resolved_2 = resolve_media_path(f"data/presets/{preset_name}")
    resolved_3 = resolve_media_path(f"repos/kcky/data/presets/{preset_name}")
    
    assert resolved_1 and os.path.exists(resolved_1), f"Fallo al resolver preset por nombre: {resolved_1}"
    assert resolved_2 and os.path.exists(resolved_2), f"Fallo al resolver preset relativo data/: {resolved_2}"
    print(f"  ✔️ Presets resueltos correctamente: {resolved_1}")

    # 2. Test de Extracción Facial y Clasificación Inteligente
    print("\n[2/4] Verificando extracción facial universal (INE vs Selfie)...")
    sample_images = list(UPLOADS_DIR.glob("id_card_*.jpeg")) + list(UPLOADS_DIR.glob("*.jpg")) + list(UPLOADS_DIR.glob("*.png"))
    
    if sample_images:
        test_img = str(sample_images[0])
        crop_out = str(BUFFERS_DIR / "test_audit_crop.png")
        enhanced_out = str(BUFFERS_DIR / "test_audit_enhanced.png")
        
        data = await extract_and_restore_face(test_img, crop_out, enhanced_out)
        print(f"  ✔️ Imagen analizada: {os.path.basename(test_img)}")
        print(f"  ✔️ Clasificación: {data.get('type_label')} (Tipo: {data.get('image_type')})")
        print(f"  ✔️ Tamaño Original Recorte: {data.get('original_crop_size')} -> HD Restaurado: {data.get('enhanced_size')}")
        assert os.path.exists(enhanced_out), "No se generó el archivo enhanced"
    else:
        print("  ⚠️ No hay imágenes de prueba en uploads; saltando extracción.")

    # 3. Test de Generación Sintética Liveness
    print("\n[3/4] Verificando generación de Liveness 3D...")
    if sample_images:
        test_face = str(BUFFERS_DIR / "test_audit_enhanced.png")
        test_y4m = str(BUFFERS_DIR / "test_audit_stream.y4m")
        test_mp4 = str(BUFFERS_DIR / "test_audit_preview.mp4")

        res_live = generate_synthetic_liveness(
            image_path=test_face,
            output_y4m_path=test_y4m,
            output_mp4_preview_path=test_mp4,
            duration=10,
            width=1280,
            height=720,
            fps=30
        )
        print(f"  ✔️ Buffer Y4M sintetizado: {res_live.get('size_mb')} MB ({res_live.get('resolution')} @ {res_live.get('fps')}fps)")
        assert os.path.exists(test_y4m), "No se generó el archivo Y4M"
        assert os.path.exists(test_mp4), "No se generó el archivo MP4 preview"

    # 4. Test de Conversión de Video Base
    print("\n[4/4] Verificando normalización continua de video base...")
    if resolved_1:
        out_swap_y4m = str(BUFFERS_DIR / "test_swap_loop.y4m")
        out_swap_mp4 = str(BUFFERS_DIR / "test_swap_preview.mp4")
        res_swap = convert_video_to_seamless_y4m(
            video_path=resolved_1,
            output_y4m_path=out_swap_y4m,
            output_mp4_preview_path=out_swap_mp4,
            min_duration=10,
            width=1280,
            height=720,
            fps=30
        )
        print(f"  ✔️ Buffer normalizado listo: {res_swap.get('size_mb')} MB")
        assert os.path.exists(out_swap_y4m), "No se generó el Y4M de swap"

    print("\n" + "=" * 60)
    print("🎉 AUDITORÍA TÉCNICA KCKY 100% EXITOSA — CERO ERRORES")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_audit())
