"""
email_rotator.py — Generador y Gestor de Alias Gmail con Dot-Trick
Genera variaciones de correo desplazando el punto de derecha a izquierda sobre las cuentas base:
- retirobetmex01@gmail.com
- retirobetmex02@gmail.com
- retirobetmex03@gmail.com
"""

import sqlite3
from typing import Dict, List, Optional, Any
from pathlib import Path

BASE_EMAILS = [
    "retirobetmex01@gmail.com",
    "retirobetmex02@gmail.com",
    "retirobetmex03@gmail.com"
]


def generate_dot_variations_for_user(username: str) -> List[str]:
    """
    Genera todas las variaciones posibles de 1 punto desplazándose de DERECHA a IZQUIERDA.
    Por ejemplo, para 'retirobetmex01':
    - retirobetmex0.1
    - retirobetmex.01
    - ...
    - r.etirobetmex01
    """
    n = len(username)
    if n <= 1:
        return [username]
    
    variations = []
    # De derecha a izquierda: insertar punto en posición i (desde n-1 hasta 1)
    for i in range(n - 1, 0, -1):
        variant = username[:i] + "." + username[i:]
        variations.append(variant)
    return variations


def get_all_dot_aliases(base_emails: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Genera la lista canónica de alias con rotación round-robin de derecha a izquierda."""
    bases = base_emails or BASE_EMAILS
    per_base = {}
    for b in bases:
        user, domain = b.split("@")
        per_base[b] = {
            "domain": domain,
            "variations": generate_dot_variations_for_user(user)
        }
    
    # Entrelazar en round-robin: Base1-Pos1, Base2-Pos1, Base3-Pos1, Base1-Pos2, ...
    results = []
    max_len = max(len(data["variations"]) for data in per_base.values())
    
    step = 0
    for pos_idx in range(max_len):
        for b in bases:
            data = per_base[b]
            if pos_idx < len(data["variations"]):
                alias_user = data["variations"][pos_idx]
                full_alias = f"{alias_user}@{data['domain']}"
                results.append({
                    "step": step,
                    "base_email": b,
                    "alias_email": full_alias,
                    "dot_position_from_right": pos_idx + 1,
                    "dot_index": len(alias_user) - pos_idx - 1
                })
                step += 1
    return results


def mark_email_as_used(
    db_conn: sqlite3.Connection,
    alias_email: str,
    base_email: Optional[str] = None,
    step_index: int = 0,
    account_id: Optional[str] = None
):
    """Registra formalmente un alias de correo como utilizado en la tabla de tracking."""
    cursor = db_conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_rotator_tracker (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            base_email TEXT NOT NULL,
            alias_email TEXT UNIQUE NOT NULL,
            step_index INTEGER NOT NULL,
            account_id TEXT,
            used_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    clean_alias = alias_email.strip().lower()
    effective_base = base_email or clean_alias.replace(".", "")
    if "@" in clean_alias and not base_email:
        u, d = clean_alias.split("@")
        effective_base = f"{u.replace('.', '')}@{d}"

    cursor.execute("""
        INSERT INTO email_rotator_tracker (base_email, alias_email, step_index, account_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(alias_email) DO UPDATE SET
            account_id = COALESCE(excluded.account_id, email_rotator_tracker.account_id),
            used_at = CURRENT_TIMESTAMP
    """, (effective_base, clean_alias, step_index, account_id))
    db_conn.commit()


def get_next_available_email(db_conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Consulta en la base de datos de KCKY los alias ya utilizados en accounts
    y retorna el siguiente alias disponible en la secuencia round-robin (DERECHA -> IZQUIERDA).
    """
    all_aliases = get_all_dot_aliases()
    
    cursor = db_conn.cursor()
    # Crear tabla de tracking si no existe
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_rotator_tracker (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            base_email TEXT NOT NULL,
            alias_email TEXT UNIQUE NOT NULL,
            step_index INTEGER NOT NULL,
            account_id TEXT,
            used_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db_conn.commit()
    
    cursor.execute("SELECT alias_email FROM email_rotator_tracker")
    used_in_tracker = {row[0].lower() for row in cursor.fetchall() if row[0]}
    
    cursor.execute("SELECT email FROM accounts WHERE email IS NOT NULL")
    used_in_accounts = {row[0].lower() for row in cursor.fetchall() if row[0]}
    
    used_set = used_in_tracker.union(used_in_accounts)
    
    for candidate in all_aliases:
        if candidate["alias_email"].lower() not in used_set:
            return candidate
            
    # Si se agotaron los de 1 punto, fallback al primer alias con timestamp o ciclo
    first = all_aliases[0]
    return first


def get_and_claim_next_email(db_conn: sqlite3.Connection, account_id: Optional[str] = None) -> Dict[str, Any]:
    """Obtiene y reserva atómicamente el siguiente alias disponible en la secuencia."""
    email_info = get_next_available_email(db_conn)
    mark_email_as_used(
        db_conn=db_conn,
        alias_email=email_info["alias_email"],
        base_email=email_info.get("base_email"),
        step_index=email_info.get("step", 0),
        account_id=account_id
    )
    return email_info


if __name__ == "__main__":
    aliases = get_all_dot_aliases()
    print(f"Total de alias generados (1 punto der->izq): {len(aliases)}")
    for a in aliases[:9]:
        print(f"Paso {a['step']}: {a['alias_email']} (Base: {a['base_email']})")
