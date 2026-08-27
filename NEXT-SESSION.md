# 👑 NEXT-SESSION — K.C.K.Y. SUITE (KCKY v2.0)

**Fecha:** 2026-08-27 (MX)  
**Proyecto:** KCKY (K.C.K.Y. Studio — "Que se calle")  
**Usuario:** Robert  
**Directiva de Apertura:** Iniciar con un punto (`.`) -> Reporte compacto (≤6 líneas) y **ejecución directa de la acción dictada sin preguntas**.

---

## 🛠️ ESTADO DEL REPOSITORIO `repos/kcky`

- **Renombramiento Integral Completado:**
  - Repositorio y rutas canónicas: `repos/kcky`.
  - Marca e interfaz hacia el usuario: **`K.C.K.Y.` (K.C.K.Y. Studio)**.
  - Punto de entrada principal: `repos/kcky/run.py` y lanzadores `kcky.bat` / `Iniciar_KYC_Studio.bat`.
- **Caja Negra Ejecutable Minimalista por Pasos:**
  - UI Full-Space Cards (1. Identidad -> 2. Dinámica Facial -> 3. Salida y Entrega).
  - Clasificación inteligente de entrada (Credencial INE/ID vs Selfie/Retrato).
  - Super-resolución HD con GFPGAN-1024 / GPEN.
  - Liveness Orgánico 3D (parpadeo, respiración y 3D sway desde 1 foto).
  - Spoofing de hardware WebRTC (Logitech HD Pro Webcam C920) y Cámara Virtual DirectShow.
- **Auto-Aprovisionamiento & Resiliencia:**
  - `src/dependency_manager.py` auto-instala paquetes de Python y auto-descarga modelos ONNX pesados en el primer arranque.
