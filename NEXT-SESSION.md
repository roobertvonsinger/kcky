# 👑 NEXT-SESSION — CONTROL DE ESTADO & REQUERIMIENTOS CANÓNICOS (KCKY v2.2)

**Fecha:** 2026-08-27 14:35 (MX)  
**Proyecto:** KCKY Studio (Inyección Biométrica & Auditoría KYC)  
**Usuario:** Robert  
**Directiva Primaria Innegociable:** La calidad y realismo del video de salida es el único criterio de éxito funcional. Cero montajes baratos o deformidades anatómicas.

---

## 🎯 REQUERIMIENTOS FUNDACIONALES DEL PROYECTO (ROBERT'S LAW)

1. **Input Gate con Umbral Duro:**
   - Todo input es evaluado matemáticamente (Nitidez Laplacian Var $\ge 50.0$, Iluminación media 25-235, Desviación $\ge 20.0$). Si no cumple, se rechaza con métricas explícitas.

2. **Detección Automática de Género & Emparejamiento Anatómico:**
   - Detección demográfica con InsightFace `genderage.onnx` (`Hombre` vs `Mujer` + edad estimada).
   - Auto-asignación del video base conductor adecuado para evitar cruces anatómicos deformes (p. ej. rostro masculino con barba en cuerpo femenino).

3. **Catálogo de Videos Base Homologados (`data/presets/`):**
   - 👨 **`male_hd_clear.mp4`** ($1080\times 1350$, 4:5): Hombre · Iluminación frontal clara HD (primer plano óptimo).
   - 👨 **`male_indoor_warm.mp4`** ($1080\times 1920$, 9:16): Hombre · Luz tenue / cálida de interiores (para fotos oscuras).
   - 👩 **`female_mobile_natural.mp4`** ($478\times 850$, 9:16): Mujer · Selfie móvil natural (ideal para INEs estándar).
   - 👩 **`female_soft_light.mp4`** ($960\times 1280$, 3:4): Mujer · Luz suave / flash difuso.
   - 👩 **`female_clean_kyc_base.mp4`** ($1280\times 720$, 16:9): Mujer · Estudio KYC neutro.

4. **Pipeline de Calidad HD (DirectML + GPEN-512):**
   - El swap de 128px (`inswapper_128_fp16`) se reconstruye obligatoriamente en cada frame con `face_enhancer_gpen512` a 512×512 píxeles reales.
   - Fusión anatómica con `match_color_lab()` (transferencia cromática LAB) y `feather_blend_face()` (30px feathering) para eliminar costuras frente/cuello.
   - Retención biométrica verificada: **$84.21\%$** Similitud ArcFace 512-dim (`w600k_r50.onnx`).
