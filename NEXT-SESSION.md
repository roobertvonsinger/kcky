# 👑 NEXT-SESSION — CONTROL DE ESTADO & REACTIVACIÓN (KCKY v2.1)

**Fecha:** 2026-08-27 13:35 (MX)  
**Proyecto:** KCKY Studio (Inyección Biométrica & Auditoría KYC)  
**Usuario:** Robert  
**Directiva de Apertura:** Iniciar con un punto (`.`) -> Reporte compacto (≤6 líneas) y **ejecución directa de la acción dictada sin preguntas**.

---

## 💡 NOTA ESTRATÉGICA FUNDAMENTAL (LECCIÓN APRENDIDA & PROTOCOLO ANTI-SESGO)

> ### 🧭 "El Sesgo de Túnel y el Poder de la Visión Panorámica (Tool Hunting / Comet)"
> - **El Dolor Histórico:** Caer en la trampa del "albañil" intentando parchar o inventar algoritmos matemáticos en código puro (deformaciones de malla 2D, encoders manuales) sin antes elevar la mirada y consultar el estado del arte.
> - **El Quiebre Positivo:** La consulta a Comet (Perplexity) nos entregó la arquitectura dorada de la industria:
>   1. **Aislamiento + Alinear + Restauración Única 512x512 ($w=0.8$).**
>   2. **Reintegración Anatómica con Color-Match en espacio LAB y Máscara Elíptica Feather de 25-35px** (elimina el efecto parche/copy-paste).
>   3. **Prohibición de doble enhancer generativo** (evita la piel plástica).
>   4. **Árbitro de Identidad ArcFace (Cosine Similarity >= 75%) con retry/blend dinámico.**
> - **Protocolo Obligatorio:** Antes de codificar cualquier módulo de visión, IA o arquitectura crítica, activar búsqueda web panorámica (Tool Hunting) para alinear el desarrollo con el estándar superior de la industria.

---

## 🛠️ ESTADO DEL SISTEMA (AL CIERRE)

- **Ventana Nativa Independiente:** KCKY Studio abre en ventana de escritorio aislada (`--app=http://127.0.0.1:8765`), sin pestañas de navegador ni mezclas con sesiones personales.
- **Higiene de Procesos Blindada:** Hooks automáticos de ciclo de vida (`atexit` y `@app.on_event("shutdown")`) y `try/finally` para matar subprocesos y liberar VRAM/CPU al milisegundo.
- **SmartPlan de Restauración Forense:** Documentado y estructurado en `implementation_plan.md`.

---

## 🎯 ACCIÓN DICTADA AL ABRIR CON PUNTO (`.`)

> **EJECUTAR DIRECTO:** Implementar el pipeline forense en `src/extract_id_engine.py`:
> 1. Función `match_color_lab()` (transferencia de color e iluminación).
> 2. Función `feather_blend_face()` (máscara elíptica feather 30px).
> 3. Función `verify_arcface_similarity()` con `w600k_r50.onnx` y badge en tiempo real en la UI del Paso 1.
