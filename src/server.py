"""
server.py — Backend FastAPI + WebSockets + REST API para K.C.K.Y.
"""

import asyncio
import json
import logging
import os
import subprocess
import uuid
from pathlib import Path
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.config import (
    UPLOADS_DIR, BUFFERS_DIR, SESSIONS_DIR, PRESETS_DIR, IDENTITIES_DIR, STATIC_DIR, DB_PATH,
    DEFAULT_HOST, DEFAULT_PORT, HARDWARE_PERSONAS, resolve_media_path
)
from src.liveness import generate_synthetic_liveness, convert_video_to_seamless_y4m
from src.face_swap import execute_face_swap_directml, get_deep_live_cam_python
from src.browser import (
    find_orbita_executable, get_cached_gologin_profiles,
    find_free_port, launch_browser_process, attach_cdp_stealth_session
)
from src.virtual_cam_broadcaster import (
    start_system_virtual_cam, stop_system_virtual_cam, get_virtual_cam_status
)
from src.db import (
    upsert_identity, get_identity, list_identities,
    register_account, update_account_status, record_kyc_session
)
from src.identity_manager import create_or_get_identity_session, extract_ine_demographics, sanitize_identity_name
from src.account_automator import automator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("KCKY_Server")

import time
from contextlib import asynccontextmanager

async def cleanup_old_files_task():
    while True:
        try:
            now = time.time()
            for directory in [UPLOADS_DIR, BUFFERS_DIR]:
                for f in directory.glob("*"):
                    if f.is_file() and f.name != ".gitkeep" and now - f.stat().st_mtime > 86400:
                        try:
                            f.unlink()
                        except Exception:
                            pass
        except Exception as e:
            logger.error(f"Error en cleanup_old_files_task: {e}")
        await asyncio.sleep(3600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_task = asyncio.create_task(cleanup_old_files_task())
    yield
    cleanup_task.cancel()
    auto_cleanup_all_processes()

app = FastAPI(title="K.C.K.Y. — Suite de Inyección Biométrica & KYC (KCKY)", version="2.4.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


import atexit

class AppState:
    def __init__(self):
        self.websockets: List[WebSocket] = []
        self.active_y4m: Optional[str] = None
        self.active_mp4_preview: Optional[str] = None
        self.active_identity_id: Optional[str] = None
        self.browser_proc: Optional[subprocess.Popen] = None
        self.active_subprocesses: List[subprocess.Popen] = []
        self.cdp_port: Optional[int] = None
        self.browser_running: bool = False
        self.is_processing: bool = False
        self.detected_sdks: List[Dict[str, Any]] = []
        self.current_progress: Dict[str, Any] = {
            "percent": 0,
            "current_frame": 0,
            "total_frames": 0,
            "eta_text": "0s",
            "speed_text": "",
            "status_text": "Listo",
            "phase": "idle"
        }

state = AppState()


def auto_cleanup_all_processes():
    """Higiene estricta de procesos y purga de temporales efímeros (Zero Zombies)."""
    # 1. Terminar subprocesos en árbol
    if state.browser_proc:
        try:
            kill_process_tree(state.browser_proc)
            state.browser_proc = None
        except Exception:
            pass
    for proc in state.active_subprocesses:
        try:
            kill_process_tree(proc)
        except Exception:
            pass
    state.active_subprocesses.clear()
    stop_system_virtual_cam()

    # 2. Purgar archivos de renderizado temporales y efímeros
    try:
        for pattern in ["*.temp.mp4", "*.tmp", "temp_*.mp4"]:
            for d in [BUFFERS_DIR, UPLOADS_DIR]:
                for f in d.glob(pattern):
                    try:
                        f.unlink()
                    except Exception:
                        pass
    except Exception:
        pass

atexit.register(auto_cleanup_all_processes)


# Shutdown manejado en el lifespan de FastAPI


async def broadcast_log(msg: str, level: str = "info", category: str = "system"):
    payload = {
        "type": "log",
        "category": category,
        "level": level,
        "message": msg,
        "timestamp": asyncio.get_event_loop().time()
    }
    dead = []
    for ws in state.websockets:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for d in dead:
        if d in state.websockets:
            state.websockets.remove(d)


async def broadcast_telemetry(event_type: str, data: Any):
    payload = {
        "type": "telemetry",
        "event_type": event_type,
        "data": data
    }
    dead = []
    for ws in state.websockets:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for d in dead:
        if d in state.websockets:
            state.websockets.remove(d)


async def broadcast_progress(data: Dict[str, Any]):
    state.current_progress.update(data)
    await broadcast_telemetry("RENDER_PROGRESS", state.current_progress)


# -------------------------------------------------------------
# REST ENDPOINTS
# -------------------------------------------------------------

@app.get("/api/progress")
async def get_render_progress():
    return state.current_progress


@app.get("/api/status")
async def get_status():
    orbita_path = find_orbita_executable()
    deep_cam_py = get_deep_live_cam_python()
    preview_url = None
    if state.active_mp4_preview and os.path.exists(state.active_mp4_preview):
        preview_url = f"/data/buffers/{os.path.basename(state.active_mp4_preview)}"

    vcam_status = get_virtual_cam_status()

    return {
        "app": "K.C.K.Y.",
        "version": "2.0.0",
        "orbita_installed": orbita_path is not None,
        "orbita_path": orbita_path,
        "deep_live_cam_installed": deep_cam_py is not None,
        "directml_acceleration": True,
        "gpu_vendor": "AMD Radeon RX 580 (DirectML Enabled)",
        "active_buffer": {
            "y4m": state.active_y4m,
            "preview_mp4": preview_url
        },
        "virtual_cam": vcam_status,
        "browser_running": state.browser_running,
        "cdp_port": state.cdp_port,
        "detected_sdks": state.detected_sdks
    }


@app.post("/api/virtual-cam/start")
async def api_start_virtual_cam(media_path: Optional[str] = Form(None)):
    target = media_path or state.active_mp4_preview or state.active_y4m
    if not target or not os.path.exists(target):
        raise HTTPException(status_code=400, detail="No hay ningún medio activo para transmitir.")
    
    ok = start_system_virtual_cam(target, width=1280, height=720, fps=30)
    if ok:
        await broadcast_log("Cámara Virtual DirectShow (OBS/Sistema) activa y transmitiendo.", "success")
        return {"status": "started", "info": get_virtual_cam_status()}
    else:
        raise HTTPException(status_code=500, detail="No fue posible iniciar el dispositivo de cámara virtual.")


@app.post("/api/virtual-cam/stop")
async def api_stop_virtual_cam():
    stop_system_virtual_cam()
    await broadcast_log("Cámara Virtual DirectShow detenida.", "info")
    return {"status": "stopped"}


@app.get("/api/virtual-cam/status")
async def api_get_virtual_cam_status():
    return get_virtual_cam_status()


@app.get("/api/profiles")
async def list_profiles():
    profiles = get_cached_gologin_profiles()
    return {"profiles": profiles}


@app.get("/api/hardware-personas")
async def list_hardware_personas():
    return {"personas": HARDWARE_PERSONAS}


PRESET_METADATA = {
    "female_clean_kyc_base.mp4": {
        "name": "👩 Mujer · Estudio KYC Limpio HD (Óvalo)",
        "gender": "Mujer",
        "resolution": "1280x720 (16:9)",
        "badge": "Óvalo KYC HD",
        "desc": "Encuadre elevado y centrado para óvalo KYC, sin lentes, sin reflejos ni marcas de agua"
    },
    "female_kyc_subecam_clean.mp4": {
        "name": "👩 Mujer · Ángulo Elevado WebCam",
        "gender": "Mujer",
        "resolution": "1280x720 (16:9)",
        "badge": "Cámara Alta",
        "desc": "Perspectiva frontal limpia simulando webcam física de monitor"
    },
    "female_kyc_cambia_clean.mp4": {
        "name": "👩 Mujer · Frontal Neutro Natural",
        "gender": "Mujer",
        "resolution": "1280x720 (16:9)",
        "badge": "Luz Natural",
        "desc": "Movimiento frontal sutil con iluminación uniforme"
    },
    "female_mobile_natural.mp4": {
        "name": "👩 Mujer · Selfie Móvil Natural",
        "gender": "Mujer",
        "resolution": "478x850 (9:16)",
        "badge": "INE / Celular",
        "desc": "Excelente para credenciales estándar y fotos de móvil"
    },
    "female_soft_light.mp4": {
        "name": "👩 Mujer · Luz Suave / Flash",
        "gender": "Mujer",
        "resolution": "960x1280 (3:4)",
        "badge": "Alta Exposición",
        "desc": "Para fotos claras, pálidas o con flash frontal"
    },
    "male_hd_clear.mp4": {
        "name": "👨 Hombre · Frontal HD Nítido",
        "gender": "Hombre",
        "resolution": "1080x1350 (4:5)",
        "badge": "HD Nítido",
        "desc": "Iluminación frontal clara, primer plano KYC óptimo"
    },
    "male_indoor_warm.mp4": {
        "name": "👨 Hombre · Interior Cálido",
        "gender": "Hombre",
        "resolution": "1080x1920 (9:16)",
        "badge": "Luz Tenue",
        "desc": "Para credenciales oscuras o fotos con luz de habitación"
    }
}


@app.get("/api/presets")
async def list_presets():
    presets = []
    if PRESETS_DIR.is_dir():
        for p in PRESETS_DIR.glob("*.mp4"):
            meta = PRESET_METADATA.get(p.name, {
                "name": p.stem.replace("_", " ").title(),
                "gender": "Universal",
                "resolution": "HD",
                "badge": "Estándar",
                "desc": "Video base de estudio"
            })
            presets.append({
                "id": p.name,
                "name": meta["name"],
                "gender": meta["gender"],
                "resolution": meta["resolution"],
                "badge": meta["badge"],
                "desc": meta["desc"],
                "path": str(p),
                "preview_url": f"/data/presets/{p.name}"
            })
    return {"presets": presets}


@app.post("/api/upload-face")
async def upload_face(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]:
        raise HTTPException(status_code=400, detail="Formato no soportado. Usa JPG o PNG.")

    file_id = uuid.uuid4().hex[:8]
    dest = UPLOADS_DIR / f"face_{file_id}{ext}"
    with open(dest, "wb") as f:
        content = await file.read()
        f.write(content)

    await broadcast_log(f"Rostro cargado: {file.filename} -> {dest.name}", "success")
    return {
        "status": "success",
        "file_path": str(dest),
        "filename": dest.name,
        "preview_url": f"/data/uploads/{dest.name}"
    }


@app.post("/api/extract-id-face")
async def api_extract_id_face(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]:
        raise HTTPException(status_code=400, detail="Formato de imagen no soportado.")

    file_id = uuid.uuid4().hex[:8]
    id_card_path = str(UPLOADS_DIR / f"id_card_{file_id}{ext}")
    crop_path = str(UPLOADS_DIR / f"crop_{file_id}.png")
    enhanced_path = str(UPLOADS_DIR / f"enhanced_{file_id}.png")

    with open(id_card_path, "wb") as f:
        content = await file.read()
        f.write(content)

    await broadcast_log(f"Credencial/INE cargada: {file.filename}. Detectando rostro y aplicando AI Super-Resolución...", "info")

    from src.id_extractor import extract_and_restore_id_face
    try:
        t0 = time.time()
        data = await extract_and_restore_id_face(id_card_path, crop_path, enhanced_path)
        elapsed = time.time() - t0
        
        if not data.get("success"):
            raise RuntimeError(data.get("error", "Error desconocido extrayendo rostro de credencial."))

        data["processing_time_sec"] = round(elapsed, 2)

        # 1. Extracción de Demográficos y Organización Canónica en data/identities/<NOMBRE>/
        demographics = extract_ine_demographics(id_card_path)
        inferred_name = demographics.get("full_name") or Path(file.filename).stem
        id_session = create_or_get_identity_session(inferred_name)
        
        front_canon = id_session.save_front_id(id_card_path)
        crop_canon, enh_canon = id_session.save_facial_assets(
            crop_path, enhanced_path, arcface_score=float(data.get("arcface_score", 95.0))
        )
        
        db_identity = id_session.commit_to_database(
            full_name=inferred_name.replace("_", " ").title(),
            demographics=demographics,
            arcface_score=float(data.get("arcface_score", 95.0)),
            front_path=front_canon,
            crop_path=crop_canon,
            enhanced_path=enh_canon
        )
        state.active_identity_id = id_session.canonical_name

        is_id = data.get("image_type") == "ID_CARD"
        await broadcast_log(
            f"Identidad organizada: {id_session.canonical_name} ({'INE / Credencial' if is_id else 'Selfie / Retrato'}). [⏱️ {elapsed:.2f}s]",
            "success"
        )

        return {
            "status": "success",
            "identity_id": id_session.canonical_name,
            "folder_path": str(id_session.root_dir),
            "image_type": data.get("image_type", "PORTRAIT_SELFIE"),
            "requires_back_upload": is_id,
            "id_card_url": f"/data/identities/{id_session.canonical_name}/inputs/front{ext}",
            "crop_url": f"/data/identities/{id_session.canonical_name}/assets/crop.png",
            "enhanced_url": f"/data/identities/{id_session.canonical_name}/assets/enhanced.png",
            "enhanced_file_path": enh_canon,
            "crop_file_path": crop_canon,
            "demographics": demographics,
            "metadata": data
        }
    except Exception as e:
        logger.error(f"Error procesando credencial: {e}", exc_info=True)
        await broadcast_log(f"Error en extracción de credencial: {str(e)}", "error")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/identities/{identity_id}/upload-back")
async def api_upload_back_id(identity_id: str, file: UploadFile = File(...)):
    """Sube el reverso de la credencial INE y lo archiva en inputs/back.jpg."""
    id_session = create_or_get_identity_session(identity_id)
    ext = os.path.splitext(file.filename)[1].lower()
    temp_path = UPLOADS_DIR / f"back_{identity_id}_{uuid.uuid4().hex[:6]}{ext}"
    
    with open(temp_path, "wb") as f:
        content = await file.read()
        f.write(content)
        
    back_canon = id_session.save_back_id(str(temp_path))
    try:
        os.remove(temp_path)
    except Exception:
        pass
        
    # Actualizar en BD
    upsert_identity(
        identity_id=id_session.canonical_name,
        full_name=identity_id.replace("_", " ").title(),
        folder_path=str(id_session.root_dir),
        back_path=back_canon
    )
    await broadcast_log(f"Reverso de credencial guardado para {id_session.canonical_name}", "success")
    return {"status": "success", "back_path": back_canon}


@app.post("/api/identities/{identity_id}/upload-domicilio")
async def api_upload_domicilio(identity_id: str, file: UploadFile = File(...)):
    """Sube el comprobante de domicilio y lo archiva en inputs/domicilio.jpg."""
    id_session = create_or_get_identity_session(identity_id)
    ext = os.path.splitext(file.filename)[1].lower()
    temp_path = UPLOADS_DIR / f"dom_{identity_id}_{uuid.uuid4().hex[:6]}{ext}"
    
    with open(temp_path, "wb") as f:
        content = await file.read()
        f.write(content)
        
    dom_canon = id_session.save_domicilio(str(temp_path))
    try:
        os.remove(temp_path)
    except Exception:
        pass
        
    # Actualizar en BD
    upsert_identity(
        identity_id=id_session.canonical_name,
        full_name=identity_id.replace("_", " ").title(),
        folder_path=str(id_session.root_dir),
        domicilio_path=dom_canon
    )
    await broadcast_log(f"Comprobante de domicilio guardado para {id_session.canonical_name}", "success")
    return {"status": "success", "domicilio_path": dom_canon}


@app.get("/api/identities")
async def api_list_identities():
    """Lista las identidades registradas en el sistema."""
    return {"identities": list_identities(limit=50)}


@app.post("/api/upload-target")
async def upload_target(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".mp4", ".mov", ".webm", ".avi", ".mkv"]:
        raise HTTPException(status_code=400, detail="Formato de video no soportado.")

    file_id = uuid.uuid4().hex[:8]
    dest = UPLOADS_DIR / f"target_{file_id}{ext}"
    with open(dest, "wb") as f:
        content = await file.read()
        f.write(content)

    await broadcast_log(f"Video base objetivo cargado: {file.filename}", "info")
    return {
        "status": "success",
        "file_path": str(dest),
        "filename": dest.name
    }


@app.post("/api/generate-liveness")
async def api_generate_liveness(
    face_path: str = Form(...),
    duration: int = Form(90),
    width: int = Form(1280),
    height: int = Form(720),
    fps: int = Form(30),
    framing_mode: str = Form("fill_crop")
):
    resolved_face = resolve_media_path(face_path)
    if not resolved_face or not os.path.exists(resolved_face):
        raise HTTPException(status_code=404, detail=f"Archivo de rostro no encontrado: {face_path}")

    state.is_processing = True
    stream_id = uuid.uuid4().hex[:8]
    out_y4m = str(BUFFERS_DIR / f"stream_{stream_id}.y4m")
    out_mp4 = str(BUFFERS_DIR / f"preview_{stream_id}.mp4")

    loop = asyncio.get_running_loop()
    def sync_progress_handler(prog_data: Dict[str, Any]):
        asyncio.run_coroutine_threadsafe(broadcast_progress(prog_data), loop)

    try:
        await broadcast_progress({
            "percent": 3,
            "current_frame": 0,
            "total_frames": duration * fps,
            "eta_text": "Iniciando...",
            "speed_text": "",
            "status_text": f"Sintetizando Liveness 3D ({duration}s @ {fps}fps)...",
            "phase": "rendering"
        })
        await broadcast_log(f"Sintetizando Liveness 3D ({duration}s @ {fps}fps, {width}x{height}, encuadre: {framing_mode})...", "info")
        t0 = time.time()
        res = await asyncio.to_thread(
            generate_synthetic_liveness,
            image_path=resolved_face,
            output_y4m_path=out_y4m,
            output_mp4_preview_path=out_mp4,
            duration=duration,
            width=width,
            height=height,
            fps=fps,
            framing_mode=framing_mode,
            progress_callback=sync_progress_handler
        )
        elapsed = time.time() - t0
        res["processing_time_sec"] = round(elapsed, 2)
        state.active_y4m = out_y4m
        state.active_mp4_preview = out_mp4
        await broadcast_progress({
            "percent": 100,
            "current_frame": duration * fps,
            "total_frames": duration * fps,
            "eta_text": "0s",
            "speed_text": "",
            "status_text": f"Flujo completado en {elapsed:.1f}s.",
            "phase": "completed"
        })
        await broadcast_log(f"Cámara lista en buffer: {res['size_mb']} MB ({width}x{height} @ {fps}fps). [⏱️ {elapsed:.2f}s]", "success")
        return {
            "status": "success",
            "y4m_path": out_y4m,
            "preview_url": f"/data/buffers/preview_{stream_id}.mp4",
            "metadata": res
        }
    except Exception as e:
        logger.error(f"Error generando liveness: {e}", exc_info=True)
        await broadcast_log(f"Error: {str(e)}", "error")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        state.is_processing = False


@app.post("/api/process-swap")
async def api_process_swap(
    source_face_path: str = Form(...),
    target_video_path: Optional[str] = Form(None),
    duration: int = Form(90),
    width: int = Form(1280),
    height: int = Form(720),
    fps: int = Form(30),
    framing_mode: str = Form("fill_crop")
):
    resolved_face = resolve_media_path(source_face_path)
    if not resolved_face or not os.path.exists(resolved_face):
        raise HTTPException(status_code=404, detail=f"Rostro de entrada no encontrado: {source_face_path}")

    # Fallback automático a preset predeterminado si target no existe o no se especificó
    resolved_target = resolve_media_path(target_video_path)
    if not resolved_target or not os.path.exists(resolved_target):
        default_preset = PRESETS_DIR / "female_clean_kyc_base.mp4"
        if default_preset.is_file():
            resolved_target = str(default_preset)
        else:
            raise HTTPException(status_code=404, detail="Video base de estudio no encontrado.")

    state.is_processing = True
    stream_id = uuid.uuid4().hex[:8]
    raw_swap_mp4 = str(BUFFERS_DIR / f"raw_swap_{stream_id}.mp4")
    out_y4m = str(BUFFERS_DIR / f"stream_swap_{stream_id}.y4m")
    out_mp4 = str(BUFFERS_DIR / f"preview_swap_{stream_id}.mp4")

    loop = asyncio.get_running_loop()
    def sync_progress_handler(prog_data: Dict[str, Any]):
        asyncio.run_coroutine_threadsafe(broadcast_progress(prog_data), loop)

    # Prioridad biométrica: si se recibe enhanced_<id>.png, buscar su crop_<id>.png correspondiente
    # para que InsightFace extraiga la identidad pura de la credencial sin artefactos sintéticos de GAN
    face_for_swap = resolved_face
    p_face = Path(resolved_face)
    if "enhanced_" in p_face.name:
        candidate_crop = p_face.parent / p_face.name.replace("enhanced_", "crop_")
        if candidate_crop.is_file():
            face_for_swap = str(candidate_crop)
            logger.info(f"Usando recorte biométrico puro para swap: {face_for_swap}")

    try:
        await broadcast_progress({
            "percent": 3,
            "current_frame": 0,
            "total_frames": 0,
            "eta_text": "Iniciando...",
            "speed_text": "",
            "status_text": "Iniciando Deep-Live-Cam DirectML...",
            "phase": "swapping"
        })

        await execute_face_swap_directml(
            source_face_path=face_for_swap,
            target_video_path=resolved_target,
            output_raw_mp4=raw_swap_mp4,
            log_callback=broadcast_log,
            progress_callback=broadcast_progress
        )

        await broadcast_log("Face swap completado. Normalizando a buffer Y4M continuo...", "info")
        await broadcast_progress({
            "percent": 86,
            "current_frame": 0,
            "total_frames": duration * fps,
            "eta_text": "2s",
            "speed_text": "",
            "status_text": "Normalizando buffer continuo Y4M (DirectShow ready)...",
            "phase": "y4m_normalizing"
        })

        res = await asyncio.to_thread(
            convert_video_to_seamless_y4m,
            video_path=raw_swap_mp4,
            output_y4m_path=out_y4m,
            output_mp4_preview_path=out_mp4,
            min_duration=duration,
            width=width,
            height=height,
            fps=fps,
            framing_mode=framing_mode,
            progress_callback=sync_progress_handler
        )

        state.active_y4m = out_y4m
        state.active_mp4_preview = out_mp4
        await broadcast_progress({
            "percent": 100,
            "current_frame": duration * fps,
            "total_frames": duration * fps,
            "eta_text": "0s",
            "speed_text": "",
            "status_text": "¡Flujo de cámara Swapped listo y armado!",
            "phase": "completed"
        })
        await broadcast_log(f"Cámara Swapped lista: {res['size_mb']} MB ({width}x{height}).", "success")
        return {
            "status": "success",
            "y4m_path": out_y4m,
            "preview_url": f"/data/buffers/preview_swap_{stream_id}.mp4",
            "metadata": res
        }
    except Exception as e:
        logger.error(f"Error en Face Swap: {e}", exc_info=True)
        await broadcast_log(f"Error: {str(e)}", "error")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        state.is_processing = False


@app.post("/api/launch-deeplive-cam-gui")
async def api_launch_deeplive_cam_gui(source_face_path: Optional[str] = Form(None)):
    """Lanza la ventana en vivo de Deep-Live-Cam DirectML con captura de webcam física."""
    from src.face_swap import launch_deep_live_cam_gui
    try:
        proc = launch_deep_live_cam_gui(source_face_path)
        await broadcast_log("Ventana interactiva de Deep-Live-Cam DirectML lanzada.", "info")
        return {"status": "launched", "pid": proc.pid}
    except Exception as e:
        logger.error(f"Error lanzando Deep-Live-Cam GUI: {e}")
        await broadcast_log(f"Error: {str(e)}", "error")
        raise HTTPException(status_code=500, detail=str(e))


def kill_process_tree(proc: Optional[subprocess.Popen]):
    if not proc:
        return
    try:
        if os.name == "nt":
            subprocess.run(f"taskkill /F /PID {proc.pid} /T", shell=True, capture_output=True)
        else:
            proc.terminate()
    except Exception:
        pass


@app.post("/api/launch-browser")
async def api_launch_browser(
    target_url: str = Form("about:blank"),
    profile_id: str = Form("temporary_clean_profile"),
    hardware_persona: str = Form("logitech_c920"),
    y4m_path: Optional[str] = Form(None)
):
    effective_y4m = y4m_path or state.active_y4m
    if not effective_y4m or not os.path.exists(effective_y4m):
        raise HTTPException(status_code=400, detail="No hay ningún buffer Y4M activo para inyectar.")

    executable = find_orbita_executable()
    if not executable:
        raise HTTPException(status_code=500, detail="No se encontró ejecutable de Orbita Browser o Chrome.")

    # Si target_url está vacío, abrir en about:blank listo para navegar a cualquier URL
    final_url = target_url.strip() if target_url and target_url.strip() else "about:blank"

    # Detener proceso previo si existe
    if state.browser_proc:
        kill_process_tree(state.browser_proc)
        state.browser_proc = None

    state.cdp_port = find_free_port()
    state.detected_sdks = []

    if profile_id == "temporary_clean_profile":
        user_data_dir = os.path.join(os.environ.get("TEMP", "/tmp"), f"kcky_profile_{state.cdp_port}")
        os.makedirs(user_data_dir, exist_ok=True)
    else:
        user_data_dir = os.path.join(Path.home(), ".gologin", "gologin-cached-profiles", profile_id)

    state.browser_proc = launch_browser_process(
        executable_path=executable,
        y4m_path=effective_y4m,
        target_url=target_url,
        cdp_port=state.cdp_port,
        user_data_dir=user_data_dir
    )
    state.browser_running = True

    await broadcast_log(f"Orbita lanzado con CDP :{state.cdp_port}. Inyectando cámara...", "info")

    async def handle_telemetry(event_type, data):
        if event_type == "KYC_SDK_DETECTED":
            sdk_name = data.get("data", {}).get("sdkName", "Desconocido")
            if not any(s.get("name") == sdk_name for s in state.detected_sdks):
                state.detected_sdks.append({"name": sdk_name, "time": data.get("timestamp")})
                await broadcast_log(f"🔥 SDK Biométrico Detectado: {sdk_name}", "warning", category="kyc_sniffer")
        await broadcast_telemetry(event_type, data)

    asyncio.create_task(attach_cdp_stealth_session(
        cdp_port=state.cdp_port,
        hardware_persona=hardware_persona,
        event_callback=handle_telemetry,
        log_callback=broadcast_log
    ))

    return {
        "status": "launched",
        "cdp_port": state.cdp_port,
        "target_url": target_url,
        "injected_y4m": effective_y4m
    }


@app.post("/api/panic-reset")
async def api_panic_reset():
    if state.browser_proc:
        kill_process_tree(state.browser_proc)
        state.browser_proc = None

    state.browser_running = False
    state.is_processing = False

    subprocess.run("taskkill /F /IM ffmpeg.exe /T", shell=True, capture_output=True)
    await broadcast_log("🚨 Panic Reset: Procesos terminados y VRAM liberada.", "warning")
    return {"status": "reset_completed"}


# -------------------------------------------------------------
# WEBSOCKET
# -------------------------------------------------------------

@app.websocket("/ws/telemetry")
async def ws_telemetry_endpoint(websocket: WebSocket):
    await websocket.accept()
    state.websockets.append(websocket)
    await websocket.send_json({
        "type": "log",
        "category": "system",
        "level": "info",
        "message": "Conectado al motor de telemetría de K.C.K.Y. Studio."
    })
    try:
        while True:
            msg = await websocket.receive_text()
            try:
                data = json.loads(msg)
                if data.get("action") == "ping":
                    await websocket.send_json({"type": "pong"})
            except Exception:
                pass
    except WebSocketDisconnect:
        if websocket in state.websockets:
            state.websockets.remove(websocket)


# -------------------------------------------------------------
# STATIC & DATA MOUNTS
# -------------------------------------------------------------

app.mount("/data/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
app.mount("/data/buffers", StaticFiles(directory=str(BUFFERS_DIR)), name="buffers")
app.mount("/data/presets", StaticFiles(directory=str(PRESETS_DIR)), name="presets")
app.mount("/data/identities", StaticFiles(directory=str(IDENTITIES_DIR)), name="identities")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# -------------------------------------------------------------
# ACCOUNT AUTOMATION ENDPOINTS (BACKGROUND HOOKS)
# -------------------------------------------------------------

@app.post("/api/accounts/create-background")
async def api_create_account_background(
    identity_id: str = Form(...),
    username: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    phone: Optional[str] = Form(None)
):
    """Dispara la creación de cuenta en segundo plano vinculada a una identidad."""
    acc_id = f"acc_{identity_id}_{uuid.uuid4().hex[:4]}"
    creds = {"username": username, "email": email, "phone": phone} if username else None
    
    # Obtener demográficos de la identidad
    identity = get_identity(identity_id)
    demographics = identity.get("metadata", {}).get("demographics", {}) if identity else {}
    
    # Lanzar creación asíncrona no bloqueante
    asyncio.create_task(
        automator.create_account_in_background(
            account_id=acc_id,
            identity_id=identity_id,
            demographics=demographics,
            credentials=creds
        )
    )
    return {"status": "started", "account_id": acc_id, "identity_id": identity_id}


@app.get("/api/accounts")
async def api_list_accounts():
    """Lista las cuentas registradas en SQLite."""
    from src.db import get_db_connection
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM accounts ORDER BY updated_at DESC LIMIT 50")
        return {"accounts": [dict(r) for r in cursor.fetchall()]}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_view():
    from fastapi.responses import Response
    return Response(status_code=204)


@app.get("/")
async def root_view():
    index_file = STATIC_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(str(index_file))
    return {"app": "K.C.K.Y.", "message": "Backend KCKY listo."}
