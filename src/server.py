"""
server.py — Backend FastAPI + WebSockets + REST API para Onboarded
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
    UPLOADS_DIR, BUFFERS_DIR, SESSIONS_DIR, STATIC_DIR,
    DEFAULT_HOST, DEFAULT_PORT, HARDWARE_PERSONAS
)
from src.liveness import generate_synthetic_liveness, convert_video_to_seamless_y4m
from src.face_swap import execute_face_swap_directml, get_deep_live_cam_python
from src.browser import (
    find_orbita_executable, get_cached_gologin_profiles,
    find_free_port, launch_browser_process, attach_cdp_stealth_session
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Onboarded_Server")

app = FastAPI(title="Onboarded — Suite de Inyección Biometríca & KYC", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AppState:
    def __init__(self):
        self.websockets: List[WebSocket] = []
        self.active_y4m: Optional[str] = None
        self.active_mp4_preview: Optional[str] = None
        self.browser_proc: Optional[subprocess.Popen] = None
        self.cdp_port: Optional[int] = None
        self.browser_running: bool = False
        self.is_processing: bool = False
        self.detected_sdks: List[Dict[str, Any]] = []

state = AppState()


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


# -------------------------------------------------------------
# REST ENDPOINTS
# -------------------------------------------------------------

@app.get("/api/status")
async def get_status():
    orbita_path = find_orbita_executable()
    deep_cam_py = get_deep_live_cam_python()
    preview_url = None
    if state.active_mp4_preview and os.path.exists(state.active_mp4_preview):
        preview_url = f"/data/buffers/{os.path.basename(state.active_mp4_preview)}"

    return {
        "app": "Onboarded",
        "status": "ready",
        "orbita_installed": orbita_path is not None,
        "orbita_path": orbita_path,
        "deep_live_cam_installed": deep_cam_py is not None,
        "directml_acceleration": True,
        "gpu_vendor": "AMD Radeon RX 580 (DirectML Enabled)",
        "active_buffer": {
            "y4m": state.active_y4m,
            "preview_mp4": preview_url
        },
        "browser_running": state.browser_running,
        "cdp_port": state.cdp_port,
        "detected_sdks": state.detected_sdks
    }


@app.get("/api/profiles")
async def list_profiles():
    profiles = get_cached_gologin_profiles()
    return {"profiles": profiles}


@app.get("/api/hardware-personas")
async def list_hardware_personas():
    return {"personas": HARDWARE_PERSONAS}


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
    fps: int = Form(30)
):
    if not os.path.exists(face_path):
        raise HTTPException(status_code=404, detail="Archivo de rostro no encontrado.")

    state.is_processing = True
    stream_id = uuid.uuid4().hex[:8]
    out_y4m = str(BUFFERS_DIR / f"stream_{stream_id}.y4m")
    out_mp4 = str(BUFFERS_DIR / f"preview_{stream_id}.mp4")

    try:
        await broadcast_log(f"Sintetizando Liveness 3D ({duration}s @ {fps}fps, {width}x{height})...", "info")
        res = await asyncio.to_thread(
            generate_synthetic_liveness,
            image_path=face_path,
            output_y4m_path=out_y4m,
            output_mp4_preview_path=out_mp4,
            duration=duration,
            width=width,
            height=height,
            fps=fps
        )
        state.active_y4m = out_y4m
        state.active_mp4_preview = out_mp4
        await broadcast_log(f"Buffer Y4M generado: {res['size_mb']} MB. Listo para inyección.", "success")
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
    target_video_path: str = Form(...),
    duration: int = Form(90),
    width: int = Form(1280),
    height: int = Form(720),
    fps: int = Form(30)
):
    if not os.path.exists(source_face_path) or not os.path.exists(target_video_path):
        raise HTTPException(status_code=404, detail="Archivos de entrada no encontrados.")

    state.is_processing = True
    stream_id = uuid.uuid4().hex[:8]
    raw_swap_mp4 = str(BUFFERS_DIR / f"raw_swap_{stream_id}.mp4")
    out_y4m = str(BUFFERS_DIR / f"stream_swap_{stream_id}.y4m")
    out_mp4 = str(BUFFERS_DIR / f"preview_swap_{stream_id}.mp4")

    try:
        await execute_face_swap_directml(
            source_face_path=source_face_path,
            target_video_path=target_video_path,
            output_raw_mp4=raw_swap_mp4,
            log_callback=broadcast_log
        )

        await broadcast_log("Face swap completado. Normalizando a buffer Y4M...", "info")
        res = await asyncio.to_thread(
            convert_video_to_seamless_y4m,
            video_path=raw_swap_mp4,
            output_y4m_path=out_y4m,
            output_mp4_preview_path=out_mp4,
            min_duration=duration,
            width=width,
            height=height,
            fps=fps
        )

        state.active_y4m = out_y4m
        state.active_mp4_preview = out_mp4
        await broadcast_log(f"Buffer Swapped Y4M listo: {res['size_mb']} MB.", "success")
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
    target_url: str = Form("https://webcamtests.com/"),
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

    # Detener proceso previo si existe
    if state.browser_proc:
        kill_process_tree(state.browser_proc)
        state.browser_proc = None

    state.cdp_port = find_free_port()
    state.detected_sdks = []

    if profile_id == "temporary_clean_profile":
        user_data_dir = os.path.join(os.environ.get("TEMP", "/tmp"), f"onboarded_profile_{state.cdp_port}")
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
        "message": "Conectado al motor de telemetría de Onboarded."
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
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def root_view():
    index_file = STATIC_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(str(index_file))
    return {"app": "Onboarded", "message": "Backend listo."}
