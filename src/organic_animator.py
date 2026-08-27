"""
organic_animator.py — Motor de Animación Facial Orgánica & Liveness 3D desde Foto Estática
Inyecta parpadeo natural, micro-saccades oculares, respiración senoidal, micro-rotaciones 3D
y ruido de sensor CMOS para transformar una foto plana de INE en un flujo de cámara en vivo hiperrealista.
"""

import math
import os
import random
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

import cv2
import numpy as np
from scipy.spatial import Delaunay


def _warp_triangle(img1: np.ndarray, img2: np.ndarray, t1: np.ndarray, t2: np.ndarray):
    """Deforma un triángulo de img1 a img2 usando transformación afín."""
    r1 = cv2.boundingRect(np.float32([t1]))
    r2 = cv2.boundingRect(np.float32([t2]))

    # Puntos compensados al bounding box
    t1_rect = []
    t2_rect = []
    t2_rect_int = []

    for i in range(3):
        t1_rect.append(((t1[i][0] - r1[0]), (t1[i][1] - r1[1])))
        t2_rect.append(((t2[i][0] - r2[0]), (t2[i][1] - r2[1])))
        t2_rect_int.append(((t2[i][0] - r2[0]), (t2[i][1] - r2[1])))

    # Obtener máscara para el triángulo destino
    mask = np.zeros((r2[3], r2[2], 3), dtype=np.float32)
    cv2.fillConvexPoly(mask, np.int32(t2_rect_int), (1.0, 1.0, 1.0), 16, 0)

    # Recortar región origen
    img1_rect = img1[r1[1]:r1[1] + r1[3], r1[0]:r1[0] + r1[2]]
    if img1_rect.shape[0] == 0 or img1_rect.shape[1] == 0:
        return

    # Matriz de transformación afín
    warp_mat = cv2.getAffineTransform(np.float32(t1_rect), np.float32(t2_rect))
    
    # Aplicar transformación
    img2_rect = cv2.warpAffine(
        img1_rect,
        warp_mat,
        (r2[2], r2[3]),
        None,
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101
    )

    # Pegar en la imagen de salida con máscara
    y1, y2 = r2[1], r2[1] + r2[3]
    x1, x2 = r2[0], r2[0] + r2[2]
    
    # Asegurar límites válidos
    h, w = img2.shape[:2]
    if y1 < 0 or y2 > h or x1 < 0 or x2 > w:
        return

    img2[y1:y2, x1:x2] = img2[y1:y2, x1:x2] * (1.0 - mask) + img2_rect * mask


class OrganicFaceAnimator:
    def __init__(self, target_width: int = 1280, target_height: int = 720, fps: int = 30):
        self.target_width = target_width
        self.target_height = target_height
        self.fps = fps
        self._app = None

    def _get_insightface_app(self):
        if self._app is None:
            import insightface
            self._app = insightface.app.FaceAnalysis(
                name='buffalo_l',
                providers=['DmlExecutionProvider', 'CPUExecutionProvider']
            )
            self._app.prepare(ctx_id=0, det_size=(640, 640), det_thresh=0.2)
        return self._app

    def prepare_base_canvas(self, input_image_path: str) -> Tuple[np.ndarray, np.ndarray, Delaunay]:
        """
        Lee la imagen, realiza auto-encuadre de estudio biométrico en 1280x720 con flancos
        ambientales y detecta los landmarks faciales + puntos de anclaje periféricos.
        """
        src_img = cv2.imread(input_image_path)
        if src_img is None:
            raise FileNotFoundError(f"No se pudo cargar la imagen: {input_image_path}")

        h_src, w_src = src_img.shape[:2]
        
        # 1. Crear canvas de estudio 1280x720
        canvas_w, canvas_h = self.target_width, self.target_height
        
        # Escalar imagen principal de manera que ocupe el ~75% del alto (óvalo KYC óptimo)
        target_face_h = int(canvas_h * 0.88)
        scale_factor = target_face_h / float(h_src)
        scaled_w = int(w_src * scale_factor)
        scaled_h = int(h_src * scale_factor)
        
        scaled_face = cv2.resize(src_img, (scaled_w, scaled_h), interpolation=cv2.INTER_LANCZOS4)
        
        # Fondo ambiental suave (bokeh)
        bg_blur = cv2.resize(src_img, (canvas_w, canvas_h), interpolation=cv2.INTER_LINEAR)
        bg_blur = cv2.GaussianBlur(bg_blur, (51, 51), 30)
        bg_blur = (bg_blur * 0.45).astype(np.uint8) # oscurecer suavemente fondo
        
        # Centrar rostro en canvas
        x_offset = max(0, (canvas_w - scaled_w) // 2)
        y_offset = max(0, (canvas_h - scaled_h) // 2)
        
        # Superponer rostro centrado
        canvas = bg_blur.copy()
        
        # Si el rostro tiene ancho menor al canvas, colocar centrado con gradiente en bordes laterales
        paste_w = min(scaled_w, canvas_w)
        paste_h = min(scaled_h, canvas_h)
        face_crop = scaled_face[:paste_h, :paste_w]
        
        # Máscara suave para integrar con el fondo
        mask = np.ones((paste_h, paste_w), dtype=np.float32)
        edge_feather = int(paste_w * 0.08)
        if edge_feather > 4 and paste_w < canvas_w:
            for i in range(edge_feather):
                val = i / float(edge_feather)
                mask[:, i] = val
                mask[:, paste_w - 1 - i] = val
        mask = np.expand_dims(mask, axis=2)
        
        canvas_roi = canvas[y_offset:y_offset+paste_h, x_offset:x_offset+paste_w]
        blended = (face_crop * mask + canvas_roi * (1.0 - mask)).astype(np.uint8)
        canvas[y_offset:y_offset+paste_h, x_offset:x_offset+paste_w] = blended

        # 2. Detectar Landmarks en el Canvas
        app = self._get_insightface_app()
        faces = app.get(canvas)
        
        if not faces:
            # Intentar detectando directamente en scaled_face con offset
            faces_src = app.get(scaled_face)
            if faces_src:
                base_lmks = faces_src[0].landmark_2d_106.copy()
                base_lmks[:, 0] += x_offset
                base_lmks[:, 1] += y_offset
            else:
                # Generar malla elástica sintética proporcional
                base_lmks = self._generate_synthetic_grid(canvas_w, canvas_h)
        else:
            base_lmks = faces[0].landmark_2d_106.copy()

        # 3. Agregar puntos de frontera perimetral para evitar distorsiones en los bordes
        boundary_pts = [
            [0, 0], [canvas_w // 2, 0], [canvas_w - 1, 0],
            [0, canvas_h // 2], [canvas_w - 1, canvas_h // 2],
            [0, canvas_h - 1], [canvas_w // 2, canvas_h - 1], [canvas_w - 1, canvas_h - 1],
            # Puntos intermedios hombros / torso
            [canvas_w * 0.2, canvas_h - 1], [canvas_w * 0.8, canvas_h - 1],
            [canvas_w * 0.1, canvas_h * 0.75], [canvas_w * 0.9, canvas_h * 0.75]
        ]
        all_base_pts = np.vstack([base_lmks, np.array(boundary_pts, dtype=np.float32)])
        
        # 4. Triangulación de Delaunay sobre los puntos base
        delaunay = Delaunay(all_base_pts)
        
        return canvas, all_base_pts, delaunay

    def _generate_synthetic_grid(self, w: int, h: int) -> np.ndarray:
        cx, cy = w / 2.0, h / 2.0
        pts = []
        for r in np.linspace(0.15, 0.45, 5):
            for a in np.linspace(0, 2 * math.pi, 20, endpoint=False):
                pts.append([cx + r * w * math.cos(a), cy + r * h * math.sin(a)])
        return np.array(pts, dtype=np.float32)

    def generate_animated_video(
        self,
        input_image_path: str,
        output_y4m_path: str,
        output_mp4_path: Optional[str] = None,
        duration: int = 45,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Renderiza el flujo de video orgánico continuo con parpadeo, respiración, micro-movimientos
        y ruido de sensor CMOS hacia un archivo .y4m y preview .mp4.
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_y4m_path)), exist_ok=True)
        if output_mp4_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_mp4_path)), exist_ok=True)

        canvas, base_pts, delaunay = self.prepare_base_canvas(input_image_path)
        num_pts = len(base_pts)
        triangles = delaunay.simplices # (N, 3)

        total_frames = duration * self.fps

        # Configurar generador de parpadeos aleatorios naturales (Poisson-like)
        blink_events = []
        t_cursor = random.uniform(1.8, 3.5)
        while t_cursor < duration:
            blink_events.append({
                "start_time": t_cursor,
                "duration": random.uniform(0.22, 0.32), # 250ms aprox
                "double_blink": random.random() < 0.15  # 15% de doble parpadeo
            })
            t_cursor += random.uniform(2.5, 4.8)

        # Configurar micro-saccades oculares
        saccade_events = []
        t_sacc = random.uniform(1.0, 2.5)
        while t_sacc < duration:
            saccade_events.append({
                "time": t_sacc,
                "dx": random.uniform(-2.5, 2.5),
                "dy": random.uniform(-1.5, 1.5),
                "duration": random.uniform(0.1, 0.2)
            })
            t_sacc += random.uniform(1.8, 3.8)

        # Configurar FFmpeg pipe para escribir Y4M directamente sin almacenar miles de imágenes
        cmd_y4m = [
            "ffmpeg",
            "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{self.target_width}x{self.target_height}",
            "-pix_fmt", "bgr24",
            "-r", str(self.fps),
            "-i", "-",
            "-pix_fmt", "yuv420p",
            output_y4m_path
        ]
        
        proc_y4m = subprocess.Popen(cmd_y4m, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

        # Identificar índices de ojos en base_pts
        # Centroide de ojo izquierdo (X menor) y ojo derecho (X mayor)
        left_eye_indices = [i for i in range(min(106, num_pts)) if 68 <= i <= 79 or 35 <= i <= 51]
        right_eye_indices = [i for i in range(min(106, num_pts)) if 80 <= i <= 91 or 85 <= i <= 102]
        
        # Puntos del párpado superior que deben descender al parpadear
        # En 106 lmk: párpados superiores son puntos clave
        if len(base_pts) >= 106:
            # Índices de párpado superior
            left_upper_lid = [68, 69, 70, 71, 35, 36, 37]
            left_lower_lid = [72, 73, 74, 75, 41, 42, 40]
            right_upper_lid = [80, 81, 82, 83, 89, 90, 91]
            right_lower_lid = [84, 85, 86, 87, 95, 96, 94]
        else:
            left_upper_lid = []
            left_lower_lid = []
            right_upper_lid = []
            right_lower_lid = []

        start_time = time.time()
        canvas_f = canvas.astype(np.float32)

        for frame_idx in range(total_frames):
            current_time = frame_idx / float(self.fps)

            # 1. Calcular ciclo de respiración (0.22 Hz = ~13 respiraciones por minuto)
            resp_phase = 2 * math.pi * 0.22 * current_time
            resp_dy = 1.8 * math.sin(resp_phase)       # movimiento vertical suave
            resp_scale = 1.0 + 0.003 * math.sin(resp_phase) # ligera expansión de torso/pecho

            # 2. Micro-rotación y sway postural de cabeza 3D (Perlin-like con superposición armónica)
            head_yaw_dx = (
                2.2 * math.sin(2 * math.pi * 0.12 * current_time) +
                0.8 * math.sin(2 * math.pi * 0.31 * current_time + 1.2)
            )
            head_pitch_dy = (
                1.4 * math.cos(2 * math.pi * 0.15 * current_time + 0.5) +
                resp_dy
            )
            head_roll_angle = 0.008 * math.sin(2 * math.pi * 0.09 * current_time)

            # 3. Calcular estado de parpadeo (Blink State: 0.0 abierto -> 1.0 cerrado)
            blink_factor = 0.0
            for b in blink_events:
                b_start = b["start_time"]
                b_dur = b["duration"]
                if b_start <= current_time <= b_start + b_dur:
                    progress = (current_time - b_start) / b_dur
                    # Curva de párpado: cierra rápido en 35% del tiempo y abre suavemente
                    if progress < 0.38:
                        blink_factor = math.sin((progress / 0.38) * (math.pi / 2.0))
                    else:
                        blink_factor = math.cos(((progress - 0.38) / 0.62) * (math.pi / 2.0))
                    break

            # 4. Calcular micro-saccades de pupilas
            gaze_dx = 0.0
            gaze_dy = 0.0
            for s in saccade_events:
                if s["time"] <= current_time <= s["time"] + s["duration"]:
                    p = (current_time - s["time"]) / s["duration"]
                    gaze_dx = s["dx"] * math.sin(p * math.pi)
                    gaze_dy = s["dy"] * math.sin(p * math.pi)
                    break

            # 5. Generar nuevos puntos deformados
            deformed_pts = base_pts.copy()
            cx, cy = self.target_width / 2.0, self.target_height / 2.0

            # Aplicar traslación y rotación sutil a la cabeza
            for i in range(min(106, num_pts)):
                px, py = deformed_pts[i]
                # Rotación en torno al centro de masa
                rx = (px - cx) * math.cos(head_roll_angle) - (py - cy) * math.sin(head_roll_angle) + cx
                ry = (px - cx) * math.sin(head_roll_angle) + (py - cy) * math.cos(head_roll_angle) + cy
                
                deformed_pts[i][0] = rx + head_yaw_dx
                deformed_pts[i][1] = ry + head_pitch_dy

            # Aplicar parpadeo en los párpados
            if blink_factor > 0.001 and len(left_upper_lid) > 0:
                # Ojo izquierdo: bajar párpado superior hacia el inferior
                for u_idx, l_idx in zip(left_upper_lid, left_lower_lid):
                    if u_idx < num_pts and l_idx < num_pts:
                        target_y = deformed_pts[l_idx][1]
                        deformed_pts[u_idx][1] += (target_y - deformed_pts[u_idx][1]) * (blink_factor * 0.92)
                
                # Ojo derecho: bajar párpado superior hacia el inferior
                for u_idx, l_idx in zip(right_upper_lid, right_lower_lid):
                    if u_idx < num_pts and l_idx < num_pts:
                        target_y = deformed_pts[l_idx][1]
                        deformed_pts[u_idx][1] += (target_y - deformed_pts[u_idx][1]) * (blink_factor * 0.92)

            # Aplicar micro-saccades en la región ocular
            if abs(gaze_dx) > 0.01 or abs(gaze_dy) > 0.01:
                for idx in left_eye_indices + right_eye_indices:
                    if idx < num_pts:
                        deformed_pts[idx][0] += gaze_dx
                        deformed_pts[idx][1] += gaze_dy

            # 6. Renderizar frame con deformación afín por triángulos (Piecewise Affine Warp)
            frame_warped = np.zeros_like(canvas_f)
            for tri in triangles:
                t_src = base_pts[tri]
                t_dst = deformed_pts[tri]
                _warp_triangle(canvas_f, frame_warped, t_src, t_dst)

            # 7. Inyectar ruido de sensor CMOS dinámico y micro-variaciones de fotometría
            frame_u8 = np.clip(frame_warped, 0, 255).astype(np.uint8)
            
            # Ruido CMOS gaussiano sutil (sigma = 2.0)
            noise = np.random.normal(0, 2.2, (self.target_height, self.target_width, 3)).astype(np.float32)
            # Micro-fluctuación de exposición ambiental (luz ambiente natural)
            lum_drift = 1.0 + 0.004 * math.sin(2 * math.pi * 0.35 * current_time)
            
            final_frame = np.clip(frame_u8.astype(np.float32) * lum_drift + noise, 0, 255).astype(np.uint8)

            # Escribir frame en el pipe Y4M
            proc_y4m.stdin.write(final_frame.tobytes())

            if progress_callback and frame_idx % 30 == 0:
                progress_callback(frame_idx, total_frames)

        proc_y4m.stdin.close()
        proc_y4m.wait()

        # Generar vista previa .mp4 para la interfaz de usuario si se solicitó
        if output_mp4_path:
            cmd_mp4 = [
                "ffmpeg",
                "-y",
                "-i", output_y4m_path,
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "22",
                "-pix_fmt", "yuv420p",
                output_mp4_path
            ]
            subprocess.run(cmd_mp4, capture_output=True)

        size_mb = os.path.getsize(output_y4m_path) / (1024 * 1024)
        elapsed = time.time() - start_time

        return {
            "status": "success",
            "y4m_path": output_y4m_path,
            "mp4_preview_path": output_mp4_path,
            "duration": duration,
            "resolution": f"{self.target_width}x{self.target_height}",
            "fps": self.fps,
            "size_mb": round(size_mb, 2),
            "render_time_sec": round(elapsed, 2)
        }


def generate_organic_liveness(
    image_path: str,
    output_y4m_path: str,
    output_mp4_path: Optional[str] = None,
    duration: int = 45,
    width: int = 1280,
    height: int = 720,
    fps: int = 30
) -> Dict[str, Any]:
    """Punto de entrada unificado para sintetizar liveness orgánico."""
    animator = OrganicFaceAnimator(target_width=width, target_height=height, fps=fps)
    return animator.generate_animated_video(
        input_image_path=image_path,
        output_y4m_path=output_y4m_path,
        output_mp4_path=output_mp4_path,
        duration=duration
    )


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Organic Face Animator CLI")
    parser.add_argument("--image", required=True, help="Ruta de la imagen de entrada")
    parser.add_argument("--output-y4m", required=True, help="Ruta de salida del archivo Y4M")
    parser.add_argument("--output-mp4", help="Ruta de salida del archivo preview MP4")
    parser.add_argument("--duration", type=int, default=45, help="Duración en segundos")
    parser.add_argument("--width", type=int, default=1280, help="Ancho de video")
    parser.add_argument("--height", type=int, default=720, help="Alto de video")
    parser.add_argument("--fps", type=int, default=30, help="FPS")

    args = parser.parse_args()

    result = generate_organic_liveness(
        image_path=args.image,
        output_y4m_path=args.output_y4m,
        output_mp4_path=args.output_mp4,
        duration=args.duration,
        width=args.width,
        height=args.height,
        fps=args.fps
    )

    print(json.dumps(result))
