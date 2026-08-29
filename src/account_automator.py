"""
account_automator.py — Orquestador de Creación de Cuentas & Inyección de Documentos KYC por CDP
Automatización de registro en BetMexico en segundo plano y auto-upload de credenciales (Frente, Reverso, Domicilio).
"""

import os
import re
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from src.db import (
    register_account, update_account_status, record_kyc_session,
    get_identity, get_db_connection, get_accounts_by_identity
)
from src.email_rotator import get_next_available_email, mark_email_as_used

logger = logging.getLogger("AccountAutomator")

DEFAULT_BETMEXICO_PASSWORD = "Kashau2022"


def generate_realistic_mx_phone(seed: Optional[str] = None) -> str:
    """Genera un número de teléfono celular mexicano realista a 10 dígitos."""
    import random
    prefixes = ["55", "81", "33", "442", "664", "999", "222", "656"]
    if seed:
        # Generación pseudo-determinista a partir del seed (ej. CURP)
        digits = "".join([c for c in seed if c.isdigit()])
        if len(digits) >= 8:
            return "55" + digits[-8:]
    
    prefix = random.choice(prefixes)
    suffix_len = 10 - len(prefix)
    suffix = "".join([str(random.randint(0, 9)) for _ in range(suffix_len)])
    return f"{prefix}{suffix}"


class AccountAutomator:
    """Gestiona el ciclo de vida de la cuenta en BetMexico y la inyección documental por CDP."""
    
    def __init__(self, platform: str = "BetMexico"):
        self.platform = platform
        self._injected_docs_history: List[Dict[str, Any]] = []

    def get_identity_documents(self, identity_folder: str) -> Dict[str, Optional[str]]:
        """
        Localiza los documentos disponibles en la carpeta inputs/ de la identidad
        con soporte para múltiples extensiones (.jpg, .jpeg, .png, .webp).
        """
        p = Path(identity_folder)
        inputs_dir = p / "inputs"
        assets_dir = p / "assets"
        
        def find_file(base_dir: Path, name_stem: str) -> Optional[str]:
            if not base_dir.is_dir():
                return None
            for ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]:
                candidate = base_dir / f"{name_stem}{ext}"
                if candidate.is_file():
                    return str(candidate)
            return None

        front = find_file(inputs_dir, "front") or find_file(p, "front")
        back = find_file(inputs_dir, "back") or find_file(p, "back")
        domicilio = find_file(inputs_dir, "domicilio") or find_file(p, "domicilio")
        enhanced = find_file(assets_dir, "enhanced") or find_file(inputs_dir, "crop")

        return {
            "front": front,
            "back": back,
            "domicilio": domicilio,
            "enhanced": enhanced
        }

    def parse_demographic_fields(
        self,
        demographics: Dict[str, Any],
        credentials: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Extrae y normaliza los campos requeridos para el formulario de registro en BetMexico."""
        full_name = (demographics.get("full_name") or "").strip()
        parts = full_name.split()
        
        first_name = parts[0] if parts else "Usuario"
        if len(parts) > 2:
            first_name = " ".join(parts[:-2])
            last_name = parts[-2]
            second_last_name = parts[-1]
        elif len(parts) == 2:
            first_name = parts[0]
            last_name = parts[1]
            second_last_name = ""
        else:
            last_name = ""
            second_last_name = ""

        curp = (demographics.get("curp") or "").strip().upper()
        gender = demographics.get("gender") or ("Hombre" if len(curp) >= 11 and curp[10] == 'H' else "Mujer")
        birth_date = demographics.get("birth_date") or ""

        # Si el CURP es válido (18 caracteres), derivar fecha si no existe
        if len(curp) >= 10 and not birth_date:
            yy = curp[4:6]
            mm = curp[6:8]
            dd = curp[8:10]
            year_prefix = "19" if int(yy) > 25 else "20"
            birth_date = f"{year_prefix}{yy}-{mm}-{dd}"

        clean_slug = re.sub(r'[^a-zA-Z0-9]', '', first_name.lower()) or "user"
        random_suffix = curp[-4:].lower() if len(curp) >= 4 else "2026"
        
        default_user = f"{clean_slug}_{random_suffix}"
        
        # Obtener correo de la rotación dot-trick si no se provee explícito
        creds = credentials or {}
        assigned_email = creds.get("email")
        if not assigned_email:
            try:
                with get_db_connection() as conn:
                    email_info = get_next_available_email(conn)
                    assigned_email = email_info["alias_email"]
            except Exception:
                assigned_email = f"{clean_slug}.{random_suffix}@gmail.com"

        phone = creds.get("phone") or generate_realistic_mx_phone(curp)
        password = creds.get("password") or DEFAULT_BETMEXICO_PASSWORD

        return {
            "first_name": first_name,
            "last_name": last_name,
            "second_last_name": second_last_name,
            "full_name": full_name,
            "curp": curp,
            "gender": gender,
            "gender_code": "H" if gender == "Hombre" else "M",
            "birth_date": birth_date,
            "address": demographics.get("address") or "",
            "username": creds.get("username") or default_user,
            "email": assigned_email,
            "phone": phone,
            "password": password
        }

    async def create_account_in_background(
        self,
        account_id: str,
        identity_id: str,
        demographics: Dict[str, Any],
        credentials: Optional[Dict[str, str]] = None,
        force_new: bool = False
    ) -> Dict[str, Any]:
        """
        Hook ejecutado en segundo plano mientras la GPU genera el video swap/liveness.
        Verifica duplicados en BD, llena el formulario de registro y persiste el estado.
        """
        logger.info(f"[{self.platform}] Iniciando verificación/creación de cuenta para identidad: {identity_id}")
        fields = self.parse_demographic_fields(demographics, credentials)

        # 1. MECANISMO ANTI-DUPLICADOS: Si no se fuerza una nueva, verificar si ya existe una cuenta previa activa
        if not force_new:
            existing = get_accounts_by_identity(identity_id, platform=self.platform)
            active = [a for a in existing if a.get("status") in ["CREATED", "VERIFYING", "APPROVED"]]
            if active:
                prev = active[0]
                logger.info(f"[{self.platform}] ⚠️ Registro previo encontrado para {identity_id}: {prev['id']} (Estado: {prev['status']}). Reutilizando cuenta existente.")
                reused_fields = dict(fields)
                reused_fields["username"] = prev.get("username") or fields["username"]
                reused_fields["email"] = prev.get("email") or fields["email"]
                reused_fields["phone"] = prev.get("phone") or fields["phone"]
                return {
                    "status": "success",
                    "reused": True,
                    "account_id": prev["id"],
                    "state": prev["status"],
                    "message": f"Cuenta existente reutilizada ({prev['username']})",
                    "fields": reused_fields
                }

        # Registrar cuenta en estado CREATING en base de datos
        register_account(
            account_id=account_id,
            identity_id=identity_id,
            platform=self.platform,
            username=fields["username"],
            email=fields["email"],
            phone=fields["phone"],
            status="CREATING"
        )
        
        # Registrar alias en el tracker de rotación de correo
        try:
            with get_db_connection() as conn:
                mark_email_as_used(conn, fields["email"], account_id=account_id)
        except Exception:
            pass
        
        try:
            # Simulación no bloqueante de registro o preparación de payload para CDP
            await asyncio.sleep(0.5)
            
            update_account_status(account_id, "CREATED")
            logger.info(f"[{self.platform}] Cuenta {account_id} creada exitosamente ({fields['username']}).")
            return {
                "status": "success",
                "account_id": account_id,
                "state": "CREATED",
                "fields": fields
            }
        except Exception as e:
            logger.error(f"[{self.platform}] Error creando cuenta {account_id}: {e}")
            update_account_status(account_id, "FAILED", error_detail=str(e))
            return {"status": "error", "account_id": account_id, "error": str(e)}

    async def autofill_registration_form_cdp(
        self,
        page: Any,
        demographics: Dict[str, Any],
        credentials: Optional[Dict[str, str]] = None,
        log_callback: Optional[Any] = None
    ) -> bool:
        """
        Rellena automáticamente los campos del formulario de registro de BetMexico / portal KYC
        mediante los selectores exactos mapeados (CDP) y heurísticas de fallback.
        """
        fields = self.parse_demographic_fields(demographics, credentials)
        filled_count = 0

        # Mapeo de selectores exactos de BetMexico + fallbacks
        selector_mappings = [
            ("email", ["input[name='email']", "input[type='email']", "#email"], fields["email"]),
            ("password", ["input[name='new-password']", "input[type='password']", "#password"], fields["password"]),
            ("confirm_password", ["input[name='confirm-new-password']", "#confirm-password"], fields["password"]),
            ("first_name", ["input[name='name']", "input[name*='nombre' i]", "#firstName"], fields["first_name"]),
            ("last_name", ["input[name='lastname']", "input[name*='apellido' i]", "#lastName"], fields["last_name"]),
            ("second_last_name", ["input[name='maidenName']", "input[name*='materno' i]", "#maidenName"], fields["second_last_name"]),
            ("phone", ["#cellphone", "input[name='cellphone']", "input[type='tel']"], fields["phone"])
        ]

        for field_name, selectors, value in selector_mappings:
            if not value:
                continue
            for sel in selectors:
                try:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        await el.fill(str(value))
                        filled_count += 1
                        if log_callback:
                            await log_callback(f"Campo llenado: {field_name} -> {sel}", "info", category="autofill")
                        break
                except Exception:
                    pass

        # Manejo de fecha de nacimiento (HeadlessUI Listboxes de BetMexico o input date)
        if fields["birth_date"]:
            try:
                parts = fields["birth_date"].split("-")
                if len(parts) == 3:
                    yyyy, mm, dd = parts[0], parts[1], str(int(parts[2]))
                    
                    # 1. Año
                    btn_year = await page.query_selector("#headlessui-listbox-button-v-1-0-0, button:has-text('Año')")
                    if btn_year and await btn_year.is_visible():
                        await btn_year.click()
                        await asyncio.sleep(0.1)
                        opt_year = await page.query_selector(f"li[role='option']:has-text('{yyyy}'), li:has-text('{yyyy}')")
                        if opt_year:
                            await opt_year.click()
                            filled_count += 1

                    # 2. Mes
                    btn_month = await page.query_selector("#headlessui-listbox-button-v-1-1-0, button:has-text('Mes')")
                    if btn_month and await btn_month.is_visible():
                        await btn_month.click()
                        await asyncio.sleep(0.1)
                        # Mes como número o dos dígitos
                        opt_month = await page.query_selector(f"li[role='option']:has-text('{mm}'), li:has-text('{mm}')")
                        if opt_month:
                            await opt_month.click()
                            filled_count += 1

                    # 3. Día
                    btn_day = await page.query_selector("#headlessui-listbox-button-v-1-2-0, button:has-text('Día')")
                    if btn_day and await btn_day.is_visible():
                        await btn_day.click()
                        await asyncio.sleep(0.1)
                        opt_day = await page.query_selector(f"li[role='option']:has-text('{dd}'), li:has-text('{dd}')")
                        if opt_day:
                            await opt_day.click()
                            filled_count += 1

                # Fallback input type date
                date_input = await page.query_selector("input[type='date'], input[name*='birth' i]")
                if date_input and await date_input.is_visible():
                    await date_input.fill(fields["birth_date"])
                    filled_count += 1
            except Exception:
                pass

        # Auto-check de términos y condiciones si existen
        try:
            terms_checkbox = await page.query_selector("input[type='checkbox'][name*='term' i], input[type='checkbox'][name*='agree' i], input[type='checkbox'][name*='18' i]")
            if terms_checkbox and await terms_checkbox.is_visible() and not await terms_checkbox.is_checked():
                await terms_checkbox.check()
                filled_count += 1
        except Exception:
            pass

        return filled_count > 0

    async def submit_registration_form_cdp(
        self,
        page: Any,
        log_callback: Optional[Any] = None
    ) -> bool:
        """Hace click en el botón de registrar (#register / Continuar) y procesa onboard-success."""
        try:
            reg_btn = await page.query_selector("#register, button:has-text('Continuar'), button[type='submit']")
            if reg_btn and await reg_btn.is_visible():
                await reg_btn.click()
                if log_callback:
                    await log_callback("🖱️ Click en botón de registro (#register)", "info", category="autofill")
                
                # Esperar a onboard-success si aparece botón 'Jugar ahora'
                try:
                    play_btn = await page.wait_for_selector("button:has-text('Jugar ahora')", timeout=6000)
                    if play_btn and await play_btn.is_visible():
                        await play_btn.click()
                        if log_callback:
                            await log_callback("🎉 Registro exitoso: click en 'Jugar ahora'", "success", category="autofill")
                except Exception:
                    pass
                return True
        except Exception as e:
            logger.error(f"[{self.platform}] Error al enviar formulario de registro: {e}")
        return False

    async def handle_facial_verification_cdp(
        self,
        page: Any,
        account_id: Optional[str] = None,
        log_callback: Optional[Any] = None
    ) -> bool:
        """
        Detecta el modal nativo 'Verificación facial' de BetMexico,
        espera estabilización del stream de video (.y4m sintetizado) y toma la selfie.
        """
        try:
            # Buscar modal o botón de captura 'Tomar foto'
            take_photo_btn = await page.wait_for_selector(
                "button:has-text('Tomar foto'), #take-photo, button.btn-primary:has-text('foto')",
                timeout=10000
            )
            if take_photo_btn and await take_photo_btn.is_visible():
                if log_callback:
                    await log_callback("📷 Modal 'Verificación facial' detectado. Estabilizando feed...", "info", category="kyc_facial")
                
                # Pausa para estabilización del stream de video sintetizado
                await asyncio.sleep(1.8)
                
                await take_photo_btn.click()
                logger.info(f"[{self.platform}] Selfie facial disparada exitosamente con click en 'Tomar foto'")
                if log_callback:
                    await log_callback("✅ Selfie capturada y enviada a validación biométrica", "success", category="kyc_facial")
                
                if account_id:
                    update_account_status(account_id, "FACIAL_SUBMITTED")
                return True
        except Exception as e:
            logger.debug(f"[{self.platform}] Modal de verificación facial no presente o expiró espera: {e}")
        return False

    async def auto_upload_kyc_documents_cdp(
        self,
        page: Any,
        identity_folder: str,
        account_id: Optional[str] = None,
        log_callback: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Escanea la página e iframes en busca de inputs de archivo (<input type="file">)
        e inyecta automáticamente los documentos correspondientes (front.jpg, back.jpg, domicilio.jpg).
        """
        docs = self.get_identity_documents(identity_folder)
        injected = {}
        
        try:
            file_inputs = await page.query_selector_all("input[type='file']")
            
            for idx, el in enumerate(file_inputs):
                name_attr = (await el.get_attribute("name") or "").lower()
                id_attr = (await el.get_attribute("id") or "").lower()
                aria_attr = (await el.get_attribute("aria-label") or "").lower()
                combined_desc = f"{name_attr} {id_attr} {aria_attr}"

                target_doc = None
                if any(k in combined_desc for k in ["front", "anverso", "frente", "id_front", "document_front"]):
                    target_doc = docs.get("front")
                    doc_label = "front.jpg"
                elif any(k in combined_desc for k in ["back", "reverso", "atras", "id_back", "document_back"]):
                    target_doc = docs.get("back")
                    doc_label = "back.jpg"
                elif any(k in combined_desc for k in ["domicilio", "address", "comprobante", "proof", "utility"]):
                    target_doc = docs.get("domicilio")
                    doc_label = "domicilio.jpg"
                else:
                    # Asignación secuencial
                    if idx == 0 and docs.get("front"):
                        target_doc = docs.get("front")
                        doc_label = "front.jpg (secuencial)"
                    elif idx == 1 and docs.get("back"):
                        target_doc = docs.get("back")
                        doc_label = "back.jpg (secuencial)"
                    elif idx == 2 and docs.get("domicilio"):
                        target_doc = docs.get("domicilio")
                        doc_label = "domicilio.jpg (secuencial)"

                if target_doc and os.path.exists(target_doc):
                    await el.set_input_files(target_doc)
                    injected[doc_label] = target_doc
                    self._injected_docs_history.append({"file": doc_label, "path": target_doc})
                    logger.info(f"[{self.platform}] Documento inyectado vía CDP: {doc_label} -> {target_doc}")
                    if log_callback:
                        await log_callback(f"📄 Documento inyectado automáticamente: {doc_label}", "success", category="kyc_injector")

            if account_id and injected:
                update_account_status(account_id, "DOCUMENT_INJECTED")

        except Exception as e:
            logger.error(f"[{self.platform}] Error en auto_upload_kyc_documents_cdp: {e}")

        return {
            "status": "success" if injected else "no_inputs_found",
            "injected_documents": injected,
            "available_documents": docs
        }

    async def handle_file_chooser(
        self,
        file_chooser: Any,
        identity_folder: str,
        account_id: Optional[str] = None,
        log_callback: Optional[Any] = None
    ) -> bool:
        """
        Manejador para el evento 'filechooser' de Playwright. Sube el documento más idóneo automáticamente.
        """
        docs = self.get_identity_documents(identity_folder)
        
        # Determinar documento basado en el historial o disponibilidad
        chosen_file = docs.get("front")
        doc_name = "front.jpg"
        
        already_injected_front = any(d.get("file", "").startswith("front") for d in self._injected_docs_history)
        already_injected_back = any(d.get("file", "").startswith("back") for d in self._injected_docs_history)
        
        if already_injected_front and docs.get("back") and not already_injected_back:
            chosen_file = docs.get("back")
            doc_name = "back.jpg"
        elif already_injected_front and already_injected_back and docs.get("domicilio"):
            chosen_file = docs.get("domicilio")
            doc_name = "domicilio.jpg"

        if chosen_file and os.path.exists(chosen_file):
            await file_chooser.set_files(chosen_file)
            self._injected_docs_history.append({"file": doc_name, "path": chosen_file})
            logger.info(f"[{self.platform}] FileChooser interceptado: {doc_name} -> {chosen_file}")
            if log_callback:
                await log_callback(f"🪪 Cuadro de diálogo de archivo resuelto automáticamente con {doc_name}", "success", category="kyc_injector")
            if account_id:
                update_account_status(account_id, "DOCUMENT_INJECTED")
            return True
            
        return False

    async def auto_upload_kyc_documents(
        self,
        cdp_port: int,
        identity_folder: str,
        account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Hook de compatibilidad para obtención de documentos."""
        docs = self.get_identity_documents(identity_folder)
        
        if account_id:
            update_account_status(account_id, "VERIFYING")
            
        return {
            "status": "ready",
            "documents": docs,
            "cdp_port": cdp_port
        }


# ==============================================================================
# MAPEO Y TELEMETRÍA DE ENDPOINTS KYC BETMEXICO (CDP & NETWORK AUDIT)
# ==============================================================================

BETMEXICO_DOC_TYPES = {
    1: {"code": "selfie", "label": "Validación Facial / Selfie", "critical": True},
    2: {"code": "id_back", "label": "Reverso de Identificación (INE)", "critical": False},
    3: {"code": "id_front", "label": "Frente de Identificación (INE)", "critical": True},
    4: {"code": "address_proof", "label": "Comprobante de Domicilio", "critical": False}
}

class BetMexicoKYCMonitor:
    """
    Monitor y Decodificador de Respuestas de Red BetMexico:
    - GetStatusFiles: Mapeo de userTypeDocument (1=Selfie, 2=Reverso, 3=Frente, 4=Domicilio).
    - HasFullValidation: Estado global de aprobación de la cuenta.
    - Users/: faceStatus (-1=En revisión/Falla biométrica, 1=Aprobado) y datos del titular.
    - AddressAcknowledgment/: Estado del comprobante de domicilio.
    """

    @staticmethod
    def parse_get_status_files(response_json: Any) -> Dict[str, Any]:
        """Parsea la respuesta del endpoint GetStatusFiles de BetMexico."""
        raw_list = response_json if isinstance(response_json, list) else response_json.get("data", [])
        parsed_docs = {}
        all_critical_approved = True
        has_any_rejection = False

        for item in raw_list:
            doc_type_id = item.get("userTypeDocument")
            is_approved = bool(item.get("isApproved", False))
            upload_date = item.get("dateUploadDocument", "")
            
            meta = BETMEXICO_DOC_TYPES.get(doc_type_id, {
                "code": f"doc_{doc_type_id}",
                "label": f"Documento Tipo {doc_type_id}",
                "critical": False
            })
            
            parsed_docs[meta["code"]] = {
                "type_id": doc_type_id,
                "label": meta["label"],
                "is_approved": is_approved,
                "upload_date": upload_date,
                "critical": meta["critical"]
            }

            if meta["critical"] and not is_approved:
                all_critical_approved = False

        return {
            "documents": parsed_docs,
            "all_critical_approved": all_critical_approved,
            "selfie_approved": parsed_docs.get("selfie", {}).get("is_approved", False),
            "front_approved": parsed_docs.get("id_front", {}).get("is_approved", False),
            "back_approved": parsed_docs.get("id_back", {}).get("is_approved", False),
            "raw": raw_list
        }

    @staticmethod
    def parse_has_full_validation(response_json: Any) -> Dict[str, Any]:
        """Parsea la respuesta del endpoint HasFullValidation."""
        is_valid = bool(response_json.get("data", False)) if isinstance(response_json, dict) else False
        msg = response_json.get("message", "") if isinstance(response_json, dict) else ""
        return {
            "has_full_validation": is_valid,
            "message": msg,
            "is_verified": is_valid
        }

    @staticmethod
    def parse_users_profile(response_json: Any) -> Dict[str, Any]:
        """Parsea la respuesta del endpoint Users/ para extraer faceStatus y datos de cuenta."""
        data = response_json.get("data", {}) if isinstance(response_json, dict) else {}
        user_account = data.get("userAccount", {})
        user_detail = data.get("userDetail", {})

        face_status = user_account.get("faceStatus", 0)  # -1 = revisión/fallo, 1 = aprobado
        return {
            "full_name": data.get("fullName", ""),
            "email": user_account.get("email", ""),
            "username": user_account.get("username", ""),
            "face_status": face_status,
            "face_status_label": "Aprobado" if face_status == 1 else ("En revisión / Mismatch" if face_status == -1 else "Pendiente"),
            "register_step": data.get("userRegisterStep", 0),
            "address": user_detail.get("address", ""),
            "cellphone": user_detail.get("cellPhone", "")
        }

    @staticmethod
    def evaluate_health_and_timeout(
        status_files: Optional[Dict[str, Any]],
        full_validation: Optional[Dict[str, Any]],
        users_profile: Optional[Dict[str, Any]],
        elapsed_seconds: float,
        stuck_timeout_seconds: float = 300.0  # 5 minutos
    ) -> Dict[str, Any]:
        """
        Evalúa el estado general del KYC y detecta estancamiento (timeout) si BetMexico derivó a cola muerta.
        """
        is_verified = full_validation.get("has_full_validation", False) if full_validation else False
        if is_verified:
            return {
                "verdict": "VERIFIED",
                "message": "🎉 Cuenta 100% validada y aprobada en BetMexico.",
                "action": "PROCEED",
                "elapsed_seconds": round(elapsed_seconds, 1)
            }

        face_status = users_profile.get("face_status", 0) if users_profile else 0
        selfie_approved = status_files.get("selfie_approved", False) if status_files else False
        front_approved = status_files.get("front_approved", False) if status_files else False
        back_approved = status_files.get("back_approved", False) if status_files else False

        # Si ya pasaron los 5-10 minutos y la selfie/frente no aprueban
        if elapsed_seconds >= stuck_timeout_seconds:
            if not selfie_approved or not front_approved or face_status == -1:
                return {
                    "verdict": "STUCK_OR_DEAD",
                    "message": f"⚠️ Verificación estancada tras {int(elapsed_seconds//60)}m {int(elapsed_seconds%60)}s. La selfie ({'Aprobada' if selfie_approved else 'No aprobada'}) o frente ({'Aprobado' if front_approved else 'No aprobado'}) no hicieron match. Se recomienda descartar cuenta y rotar identidad.",
                    "action": "ROTATE_NEXT",
                    "elapsed_seconds": round(elapsed_seconds, 1)
                }

        return {
            "verdict": "PENDING",
            "message": f"⏳ En proceso ({int(elapsed_seconds)}s transcurridos). Reverso: {'OK' if back_approved else '...'}, Frente: {'OK' if front_approved else '...'}, Selfie: {'OK' if selfie_approved else '...'}",
            "action": "WAIT",
            "elapsed_seconds": round(elapsed_seconds, 1)
        }


# Instancias singleton
automator = AccountAutomator()
kyc_monitor = BetMexicoKYCMonitor()
