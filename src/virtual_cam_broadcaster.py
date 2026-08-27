"""
virtual_cam_broadcaster.py — Emisor de Cámara Virtual DirectShow (OBS Virtual Camera / Windows)
Transmite video en bucle o fotogramas en tiempo real a nivel de sistema operativo para que
CUALQUIER aplicación (navegador normal, AlterCam, OBS, Telegram, etc.) reciba el video sin pantalla negra.
"""

import os
import time
import threading
import logging
import cv2
import numpy as np
from typing import Optional

logger = logging.getLogger("KCKY_VirtualCam")

_active_broadcaster: Optional["VirtualCamBroadcaster"] = None
_broadcaster_lock = threading.Lock()


class VirtualCamBroadcaster:
    def __init__(self, media_path: str, width: int = 1280, height: int = 720, fps: int = 30):
        self.media_path = os.path.abspath(media_path)
        self.width = width
        self.height = height
        self.fps = fps
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self.device_name = "Unknown"

    def start(self) -> bool:
        if not os.path.exists(self.media_path):
            logger.error(f"Archivo de medios no encontrado: {self.media_path}")
            return False

        if self.running:
            self.stop()

        self.running = True
        self._thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self._thread.start()
        return True

    def _broadcast_loop(self):
        try:
            import pyvirtualcam
            logger.info(f"Iniciando VirtualCamBroadcaster ({self.width}x{self.height} @ {self.fps}fps) con {self.media_path}")
            
            with pyvirtualcam.Camera(width=self.width, height=self.height, fps=self.fps, fmt=pyvirtualcam.PixelFormat.BGR) as cam:
                self.device_name = cam.device
                logger.info(f"Cámara virtual conectada al dispositivo: {cam.device}")
                
                frame_delay = 1.0 / self.fps

                while self.running:
                    cap = cv2.VideoCapture(self.media_path)
                    if not cap.isOpened():
                        img = cv2.imread(self.media_path)
                        if img is not None:
                            resized = cv2.resize(img, (self.width, self.height))
                            while self.running:
                                cam.send(resized)
                                cam.sleep_until_next_frame()
                        break

                    while self.running:
                        ret, frame = cap.read()
                        if not ret:
                            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            ret, frame = cap.read()
                            if not ret:
                                break

                        if frame.shape[1] != self.width or frame.shape[0] != self.height:
                            frame = cv2.resize(frame, (self.width, self.height))

                        cam.send(frame)
                        cam.sleep_until_next_frame()

                    cap.release()
                    time.sleep(0.01)

        except Exception as e:
            logger.error(f"Error en VirtualCamBroadcaster: {e}", exc_info=True)
        finally:
            self.running = False
            logger.info("VirtualCamBroadcaster detenido.")

    def stop(self):
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None


def start_system_virtual_cam(media_path: str, width: int = 1280, height: int = 720, fps: int = 30) -> bool:
    global _active_broadcaster
    with _broadcaster_lock:
        if _active_broadcaster:
            _active_broadcaster.stop()
        
        _active_broadcaster = VirtualCamBroadcaster(media_path, width, height, fps)
        return _active_broadcaster.start()


def stop_system_virtual_cam():
    global _active_broadcaster
    with _broadcaster_lock:
        if _active_broadcaster:
            _active_broadcaster.stop()
            _active_broadcaster = None


def get_virtual_cam_status() -> dict:
    global _active_broadcaster
    with _broadcaster_lock:
        if _active_broadcaster and _active_broadcaster.running:
            return {
                "active": True,
                "device": _active_broadcaster.device_name,
                "media_path": _active_broadcaster.media_path,
                "resolution": f"{_active_broadcaster.width}x{_active_broadcaster.height}",
                "fps": _active_broadcaster.fps
            }
        return {"active": False, "device": None}
