"""
db.py — Base de Datos Soberana SQLite para KCKY Studio & Automatización KYC
Maneja la persistencia de identidades, cuentas de plataforma y auditorías biométricas.
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from src.config import DB_PATH

logger = logging.getLogger("KCKY_DB")


def get_db_connection() -> sqlite3.Connection:
    """Retorna una conexión a SQLite optimizada para concurrencia (WAL mode)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db():
    """Inicializa el esquema de base de datos relacional de KCKY."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Tabla de Identidades Físicas / Documentales
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS identities (
                id TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                curp TEXT,
                birth_date TEXT,
                gender TEXT,
                address TEXT,
                folder_path TEXT NOT NULL,
                front_path TEXT,
                back_path TEXT,
                domicilio_path TEXT,
                crop_path TEXT,
                enhanced_path TEXT,
                arcface_score REAL DEFAULT 0.0,
                metadata_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_identities_name ON identities(full_name);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_identities_curp ON identities(curp);")

        # 2. Tabla de Cuentas de Plataforma (BetMexico / Otros)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                identity_id TEXT,
                platform TEXT DEFAULT 'BetMexico',
                username TEXT,
                email TEXT,
                phone TEXT,
                status TEXT DEFAULT 'CREATED',
                error_detail TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (identity_id) REFERENCES identities(id) ON DELETE SET NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_accounts_identity ON accounts(identity_id);")

        # 3. Tabla de Sesiones y Auditorías de Verificación KYC
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS kyc_sessions (
                id TEXT PRIMARY KEY,
                account_id TEXT,
                identity_id TEXT,
                preset_used TEXT,
                similarity_score REAL DEFAULT 0.0,
                outcome TEXT DEFAULT 'PENDING',
                failure_reason TEXT,
                output_video_path TEXT,
                output_y4m_path TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL,
                FOREIGN KEY (identity_id) REFERENCES identities(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_kyc_identity ON kyc_sessions(identity_id);")
        conn.commit()


# Inicializar automáticamente al importar
init_db()


# ==============================================================================
# OPERACIONES CRUD — IDENTIDADES
# ==============================================================================

def upsert_identity(
    identity_id: str,
    full_name: str,
    folder_path: str,
    curp: Optional[str] = None,
    birth_date: Optional[str] = None,
    gender: Optional[str] = None,
    address: Optional[str] = None,
    front_path: Optional[str] = None,
    back_path: Optional[str] = None,
    domicilio_path: Optional[str] = None,
    crop_path: Optional[str] = None,
    enhanced_path: Optional[str] = None,
    arcface_score: float = 0.0,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Crea o actualiza una identidad física en la base de datos."""
    meta_json = json.dumps(metadata or {}, ensure_ascii=False)
    now = datetime.now(timezone.utc).isoformat()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO identities (
                id, full_name, curp, birth_date, gender, address,
                folder_path, front_path, back_path, domicilio_path,
                crop_path, enhanced_path, arcface_score, metadata_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                full_name = excluded.full_name,
                curp = COALESCE(excluded.curp, identities.curp),
                birth_date = COALESCE(excluded.birth_date, identities.birth_date),
                gender = COALESCE(excluded.gender, identities.gender),
                address = COALESCE(excluded.address, identities.address),
                folder_path = excluded.folder_path,
                front_path = COALESCE(excluded.front_path, identities.front_path),
                back_path = COALESCE(excluded.back_path, identities.back_path),
                domicilio_path = COALESCE(excluded.domicilio_path, identities.domicilio_path),
                crop_path = COALESCE(excluded.crop_path, identities.crop_path),
                enhanced_path = COALESCE(excluded.enhanced_path, identities.enhanced_path),
                arcface_score = excluded.arcface_score,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
        """, (
            identity_id, full_name, curp, birth_date, gender, address,
            folder_path, front_path, back_path, domicilio_path,
            crop_path, enhanced_path, arcface_score, meta_json,
            now, now
        ))
        conn.commit()

    return get_identity(identity_id)


def get_identity(identity_id: str) -> Optional[Dict[str, Any]]:
    """Obtiene una identidad por ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM identities WHERE id = ?", (identity_id,))
        row = cursor.fetchone()
        if row:
            res = dict(row)
            if res.get("metadata_json"):
                try:
                    res["metadata"] = json.loads(res["metadata_json"])
                except Exception:
                    res["metadata"] = {}
            return res
    return None


def list_identities(limit: int = 50) -> List[Dict[str, Any]]:
    """Lista las identidades registradas más recientes."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM identities ORDER BY updated_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in cursor.fetchall()]


# ==============================================================================
# OPERACIONES CRUD — CUENTAS
# ==============================================================================

def register_account(
    account_id: str,
    identity_id: str,
    platform: str = "BetMexico",
    username: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    status: str = "CREATING"
) -> Dict[str, Any]:
    """Registra una cuenta de plataforma vinculada a una identidad."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO accounts (
                id, identity_id, platform, username, email, phone, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                updated_at = excluded.updated_at
        """, (account_id, identity_id, platform, username, email, phone, status, now, now))
        conn.commit()
    return {"id": account_id, "identity_id": identity_id, "status": status}


def update_account_status(account_id: str, status: str, error_detail: Optional[str] = None):
    """Actualiza el estado de una cuenta (CREATING, CREATED, VERIFYING, APPROVED, REJECTED, DEAD)."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE accounts
            SET status = ?, error_detail = ?, updated_at = ?
            WHERE id = ?
        """, (status, error_detail, now, account_id))
        conn.commit()


def get_accounts_by_identity(identity_id: str, platform: Optional[str] = None) -> List[Dict[str, Any]]:
    """Obtiene el historial de cuentas registradas para una identidad dada para prevenir duplicados."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if platform:
            cursor.execute(
                "SELECT * FROM accounts WHERE identity_id = ? AND platform = ? ORDER BY created_at DESC",
                (identity_id, platform)
            )
        else:
            cursor.execute(
                "SELECT * FROM accounts WHERE identity_id = ? ORDER BY created_at DESC",
                (identity_id,)
            )
        return [dict(r) for r in cursor.fetchall()]


# ==============================================================================
# OPERACIONES CRUD — SESIONES KYC
# ==============================================================================

def record_kyc_session(
    session_id: str,
    identity_id: str,
    preset_used: str,
    similarity_score: float,
    outcome: str,
    failure_reason: Optional[str] = None,
    output_video_path: Optional[str] = None,
    output_y4m_path: Optional[str] = None,
    account_id: Optional[str] = None
) -> Dict[str, Any]:
    """Registra o actualiza el resultado de una sesión de verificación KYC."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO kyc_sessions (
                id, account_id, identity_id, preset_used, similarity_score,
                outcome, failure_reason, output_video_path, output_y4m_path, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                similarity_score = excluded.similarity_score,
                outcome = excluded.outcome,
                failure_reason = excluded.failure_reason,
                output_video_path = excluded.output_video_path,
                output_y4m_path = excluded.output_y4m_path
        """, (
            session_id, account_id, identity_id, preset_used, similarity_score,
            outcome, failure_reason, output_video_path, output_y4m_path, now
        ))
        conn.commit()
    return {"session_id": session_id, "outcome": outcome, "similarity_score": similarity_score}
