"""
account_automator.py — Orquestador de Creación de Cuentas & Subida Automática de Documentos KYC
Enganche para la automatización en segundo plano (BetMexico) y subida de archivos (Frente, Reverso, Domicilio).
"""

import os
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from src.db import register_account, update_account_status, record_kyc_session

logger = logging.getLogger("AccountAutomator")


class AccountAutomator:
    """Gestiona el ciclo de vida de la cuenta en la casa de apuestas y la inyección documental."""
    
    def __init__(self, platform: str = "BetMexico"):
        self.platform = platform
        
    async def create_account_in_background(
        self,
        account_id: str,
        identity_id: str,
        demographics: Dict[str, Any],
        credentials: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Hook ejecutado en segundo plano mientras la GPU genera el video swap/liveness.
        Llena el formulario de registro de la plataforma y persiste el estado en SQLite.
        """
        logger.info(f"[{self.platform}] Iniciando creación de cuenta para identidad: {identity_id}")
        
        # Registrar cuenta en estado CREATING en base de datos
        register_account(
            account_id=account_id,
            identity_id=identity_id,
            platform=self.platform,
            username=credentials.get("username") if credentials else None,
            email=credentials.get("email") if credentials else None,
            phone=credentials.get("phone") if credentials else None,
            status="CREATING"
        )
        
        try:
            # Espacio reservado para el script de navegación / CDP / API de BetMexico
            # Simulación no bloqueante mientras se conecta el driver completo
            await asyncio.sleep(0.5)
            
            update_account_status(account_id, "CREATED")
            logger.info(f"[{self.platform}] Cuenta {account_id} creada exitosamente.")
            return {"status": "success", "account_id": account_id, "state": "CREATED"}
        except Exception as e:
            logger.error(f"[{self.platform}] Error creando cuenta {account_id}: {e}")
            update_account_status(account_id, "FAILED", error_detail=str(e))
            return {"status": "error", "account_id": account_id, "error": str(e)}

    async def auto_upload_kyc_documents(
        self,
        cdp_port: int,
        identity_folder: str,
        account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Hook para inyectar automáticamente los archivos de la credencial (Frente, Reverso, Domicilio)
        en el portal de verificación KYC tras validar la selfie por cámara virtual.
        """
        p = Path(identity_folder)
        inputs_dir = p / "inputs"
        
        front = inputs_dir / "front.jpg"
        back = inputs_dir / "back.jpg"
        domicilio = inputs_dir / "domicilio.jpg"
        
        found_docs = {
            "front": str(front) if front.is_file() else None,
            "back": str(back) if back.is_file() else None,
            "domicilio": str(domicilio) if domicilio.is_file() else None
        }
        
        logger.info(f"[{self.platform}] Documentos listos para inyección CDP: {found_docs}")
        
        if account_id:
            update_account_status(account_id, "VERIFYING")
            
        return {
            "status": "ready",
            "documents": found_docs,
            "cdp_port": cdp_port
        }


# Instancia singleton del automador
automator = AccountAutomator()
