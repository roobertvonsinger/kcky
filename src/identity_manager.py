"""
identity_manager.py — Gestor Canónico de Jerarquía de Identidades & Extracción de Datos
Organiza archivos en data/identities/<NOMBRE_COMPLETO>/ (inputs, assets, outputs) y sincroniza con SQLite.
"""

import os
import re
import json
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import cv2
import numpy as np

from src.config import IDENTITIES_DIR, UPLOADS_DIR
from src.db import upsert_identity, get_identity

logger = logging.getLogger("IdentityManager")


def sanitize_identity_name(raw_name: Optional[str]) -> str:
    """Convierte cualquier nombre a formato canónico en mayúsculas separado por guiones bajos."""
    if not raw_name or not raw_name.strip():
        import uuid
        return f"IDENTIDAD_{uuid.uuid4().hex[:8].upper()}"
        
    # Reemplazar acentos y caracteres especiales
    name = raw_name.strip().upper()
    replacements = {
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U', 'Ü': 'U', 'Ñ': 'N'
    }
    for k, v in replacements.items():
        name = name.replace(k, v)
        
    # Eliminar cualquier carácter que no sea alfanumérico o espacio
    name = re.sub(r'[^A-Z0-9\s_]', '', name)
    # Colapsar múltiples espacios y guiones en un solo guión bajo
    name = re.sub(r'[\s_]+', '_', name)
    return name.strip('_')


def infer_name_from_path(file_path: str) -> Optional[str]:
    """Infiere el nombre del titular a partir de la estructura de carpetas o nombre de archivo si existe."""
    p = Path(file_path)
    # 1. Si está en una carpeta como "BLANCA ESTRELLA QUINTERO FRIAS"
    parent_name = p.parent.name
    if len(parent_name.split()) >= 2 and not parent_name.startswith("data") and not parent_name.startswith("identities"):
        return parent_name
        
    # 2. Si el archivo mismo contiene el nombre
    stem = p.stem
    if len(stem.split()) >= 2 or "_" in stem:
        if not stem.startswith("id_card_") and not stem.startswith("crop_") and not stem.startswith("face_"):
            return stem
    return None


def extract_ine_demographics(img_path: str) -> Dict[str, Any]:
    """
    Extrae datos demográficos del frente o reverso de la credencial INE
    (CURP, Nombre, Fecha de Nacimiento, Sexo, Clave de Elector).
    """
    demographics = {
        "full_name": None,
        "curp": None,
        "birth_date": None,
        "gender": None,
        "address": None
    }
    
    # 1. Inferir nombre por ruta
    inferred_name = infer_name_from_path(img_path)
    if inferred_name:
        demographics["full_name"] = inferred_name.replace("_", " ").title()

    # 2. Extracción mediante OCR y Regex si Tesseract o EasyOCR están disponibles
    try:
        # Búsqueda de CURP por patrón regex en imagen
        import pytesseract
        img = cv2.imread(img_path)
        if img is not None:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # Denoise y threshold adaptativo para OCR
            thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            text = pytesseract.image_to_string(thresh, lang='spa')
            
            # Buscar CURP (18 caracteres alfanuméricos estándar)
            curp_match = re.search(r'[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d', text)
            if curp_match:
                demographics["curp"] = curp_match.group(0)
                
            # Buscar género
            if "SEXO M" in text or "SEXO H" in text:
                demographics["gender"] = "Hombre" if "SEXO H" in text else "Mujer"
    except Exception:
        pass

    return demographics


class IdentitySession:
    """Representa y gestiona la carpeta canónica de un titular en el sistema."""
    
    def __init__(self, canonical_name: str):
        self.canonical_name = sanitize_identity_name(canonical_name)
        self.root_dir = IDENTITIES_DIR / self.canonical_name
        self.inputs_dir = self.root_dir / "inputs"
        self.assets_dir = self.root_dir / "assets"
        self.outputs_dir = self.root_dir / "outputs"
        self._ensure_directories()
        
    def _ensure_directories(self):
        for d in [self.root_dir, self.inputs_dir, self.assets_dir, self.outputs_dir]:
            d.mkdir(parents=True, exist_ok=True)
            
    def save_front_id(self, src_path: str) -> str:
        """Copia el documento frontal al directorio inputs/front.jpg."""
        ext = os.path.splitext(src_path)[1].lower() or ".jpg"
        dest = self.inputs_dir / f"front{ext}"
        shutil.copy2(src_path, dest)
        return str(dest)

    def save_back_id(self, src_path: str) -> str:
        """Copia el documento reverso al directorio inputs/back.jpg."""
        ext = os.path.splitext(src_path)[1].lower() or ".jpg"
        dest = self.inputs_dir / f"back{ext}"
        shutil.copy2(src_path, dest)
        return str(dest)

    def save_domicilio(self, src_path: str) -> str:
        """Copia el comprobante de domicilio al directorio inputs/domicilio.jpg."""
        ext = os.path.splitext(src_path)[1].lower() or ".jpg"
        dest = self.inputs_dir / f"domicilio{ext}"
        shutil.copy2(src_path, dest)
        return str(dest)

    def save_facial_assets(self, crop_path: str, enhanced_path: str, arcface_score: float = 0.0) -> Tuple[str, str]:
        """Copia el recorte puro y el rostro mejorado a assets/."""
        dest_crop = self.assets_dir / "crop.png"
        dest_enh = self.assets_dir / "enhanced.png"
        shutil.copy2(crop_path, dest_crop)
        shutil.copy2(enhanced_path, dest_enh)
        return str(dest_crop), str(dest_enh)

    def save_output_videos(self, preview_mp4: Optional[str] = None, stream_y4m: Optional[str] = None) -> Dict[str, str]:
        """Almacena o enlaza los videos generados en outputs/."""
        res = {}
        if preview_mp4 and os.path.exists(preview_mp4):
            dest_mp4 = self.outputs_dir / "preview_swap.mp4"
            shutil.copy2(preview_mp4, dest_mp4)
            res["preview_mp4"] = str(dest_mp4)
            
        if stream_y4m and os.path.exists(stream_y4m):
            dest_y4m = self.outputs_dir / "stream_swap.y4m"
            shutil.copy2(stream_y4m, dest_y4m)
            res["stream_y4m"] = str(dest_y4m)
        return res

    def commit_to_database(
        self,
        full_name: str,
        demographics: Optional[Dict[str, Any]] = None,
        arcface_score: float = 0.0,
        front_path: Optional[str] = None,
        back_path: Optional[str] = None,
        crop_path: Optional[str] = None,
        enhanced_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Guarda la identidad completa en SQLite."""
        demographics = demographics or {}
        meta_file = self.root_dir / "identity.json"
        
        id_data = {
            "canonical_name": self.canonical_name,
            "full_name": full_name,
            "demographics": demographics,
            "arcface_score": arcface_score,
            "folder_path": str(self.root_dir)
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(id_data, f, ensure_ascii=False, indent=2)

        return upsert_identity(
            identity_id=self.canonical_name,
            full_name=full_name,
            folder_path=str(self.root_dir),
            curp=demographics.get("curp"),
            birth_date=demographics.get("birth_date"),
            gender=demographics.get("gender"),
            address=demographics.get("address"),
            front_path=front_path,
            back_path=back_path,
            crop_path=crop_path,
            enhanced_path=enhanced_path,
            arcface_score=arcface_score,
            metadata=id_data
        )


def create_or_get_identity_session(raw_name: Optional[str] = None) -> IdentitySession:
    """Crea o recupera una sesión de identidad jerárquica."""
    c_name = sanitize_identity_name(raw_name)
    return IdentitySession(c_name)
