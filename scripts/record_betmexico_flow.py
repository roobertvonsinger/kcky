"""
record_betmexico_flow.py — Grabador y Sniffer en Tiempo Real del Registro BetMexico
Lanza Chrome en WinSta0\\Default, se conecta vía CDP/Playwright y mapea:
1. Selectores DOM de cada campo y botón.
2. Endpoints HTTP/REST, Headers, Payloads JSON de registro y respuestas.
3. Llamadas a WebRTC/getUserMedia (cámara/selfie) e iframes de KYC.
4. Generación y asignación automática del correo alias con dot-trick.
"""

import os
import sys
import json
import time
import socket
import asyncio
import tempfile
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

# Fix encoding Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import ctypes
from ctypes import wintypes
from playwright.async_api import async_playwright

from src.email_rotator import get_all_dot_aliases, get_next_available_email
from src.db import get_db_connection
from src.browser import find_orbita_executable

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("KCKY_Recorder")

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CAPTURE_JSON = OUTPUT_DIR / "betmexico_flow_capture.json"
SUMMARY_MD = OUTPUT_DIR / "betmexico_flow_summary.md"

# Win32 Launch en Pantalla Física
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
GENERIC_ALL = 0x10000000

class STARTUPINFO(ctypes.Structure):
    _fields_ = [
        ('cb', wintypes.DWORD),
        ('lpReserved', wintypes.LPWSTR),
        ('lpDesktop', wintypes.LPWSTR),
        ('lpTitle', wintypes.LPWSTR),
        ('dwX', wintypes.DWORD),
        ('dwY', wintypes.DWORD),
        ('dwXSize', wintypes.DWORD),
        ('dwYSize', wintypes.DWORD),
        ('dwXCountChars', wintypes.DWORD),
        ('dwYCountChars', wintypes.DWORD),
        ('dwFillAttribute', wintypes.DWORD),
        ('dwFlags', wintypes.DWORD),
        ('wShowWindow', wintypes.WORD),
        ('cbReserved2', wintypes.WORD),
        ('lpReserved2', ctypes.c_void_p),
        ('hStdInput', wintypes.HANDLE),
        ('hStdOutput', wintypes.HANDLE),
        ('hStdError', wintypes.HANDLE),
    ]

class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('hProcess', wintypes.HANDLE),
        ('hThread', wintypes.HANDLE),
        ('dwProcessId', wintypes.DWORD),
        ('dwThreadId', wintypes.DWORD),
    ]

def launch_chrome_on_physical_desktop(chrome_path: str, cdp_port: int, user_data_dir: str, target_url: str) -> Optional[int]:
    """Lanza Chrome en WinSta0\\Default con Remote Debugging habilitado."""
    hDesk = user32.OpenDesktopW("Default", 0, False, GENERIC_ALL)
    if not hDesk:
        hDesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
    if hDesk:
        user32.SetThreadDesktop(hDesk)

    cmd = (
        f'"{chrome_path}" '
        f'--remote-debugging-port={cdp_port} '
        f'--user-data-dir="{user_data_dir}" '
        f'--no-first-run '
        f'--no-default-browser-check '
        f'--start-maximized '
        f'"{target_url}"'
    )

    si = STARTUPINFO()
    si.cb = ctypes.sizeof(STARTUPINFO)
    si.lpDesktop = "WinSta0\\Default"
    si.dwFlags = 0x00000001
    si.wShowWindow = 3 # SW_SHOWMAXIMIZED

    pi = PROCESS_INFORMATION()
    success = kernel32.CreateProcessW(
        None, cmd, None, None, False, 0x00000010, None, None, ctypes.byref(si), ctypes.byref(pi)
    )
    if success:
        pid = pi.dwProcessId
        kernel32.CloseHandle(pi.hProcess)
        kernel32.CloseHandle(pi.hThread)
        return pid
    return None


class FlowRecorder:
    def __init__(self, target_email_info: Dict[str, Any]):
        self.target_email_info = target_email_info
        self.events: List[Dict[str, Any]] = []
        self.requests: List[Dict[str, Any]] = []
        self.inputs_map: Dict[str, Any] = {}
        self.camera_hooks: List[Dict[str, Any]] = []
        self.is_running = True

    def record_dom_event(self, event_data: Dict[str, Any]):
        event_data["timestamp"] = time.time()
        self.events.append(event_data)
        
        etype = event_data.get("type")
        if etype in ("input", "change", "focus", "blur"):
            selector = event_data.get("selector")
            field_name = event_data.get("name") or event_data.get("id") or selector
            self.inputs_map[field_name] = {
                "selector": selector,
                "tag": event_data.get("tag"),
                "type": event_data.get("inputType"),
                "name": event_data.get("name"),
                "id": event_data.get("id"),
                "placeholder": event_data.get("placeholder"),
                "sample_val": event_data.get("value_masked"),
                "last_seen": event_data["timestamp"]
            }
            logger.info(f"📝 [DOM INPUT] {field_name} (Sel: {selector}) -> val: '{event_data.get('value_masked')}'")
        elif etype == "click":
            logger.info(f"🖱️ [CLICK] '{event_data.get('text')}' (Sel: {event_data.get('selector')})")
        elif etype == "get_user_media":
            self.camera_hooks.append(event_data)
            logger.info(f"📷 [CÁMARA / KYC DETECTADO] Solicitud getUserMedia: {json.dumps(event_data.get('constraints', {}))}")

        self._save_state()

    def record_network(self, req_data: Dict[str, Any]):
        req_data["timestamp"] = time.time()
        self.requests.append(req_data)
        url = req_data.get("url", "")
        method = req_data.get("method", "")
        
        # Loggear solo llamadas relevantes a API/auth/register/kyc
        if any(k in url.lower() for k in ["api", "register", "login", "user", "kyc", "document", "session", "captcha"]):
            body_preview = str(req_data.get("post_data", ""))[:120]
            logger.info(f"🌐 [{method}] {url} | Body: {body_preview}")

        self._save_state()

    def _save_state(self):
        data = {
            "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "target_email": self.target_email_info,
            "inputs_detected": list(self.inputs_map.values()),
            "camera_kyc_events": self.camera_hooks,
            "events_count": len(self.events),
            "requests_count": len(self.requests),
            "events": self.events[-100:],  # Últimos 100 eventos
            "requests": self.requests[-100:]
        }
        with open(CAPTURE_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self._generate_summary_md()

    def _generate_summary_md(self):
        lines = [
            "# 📋 Mapeo de Flujo de Registro BetMexico & KYC",
            f"**Fecha:** {time.strftime('%Y-%m-%d %H:%M:%S')}  ",
            f"**Correo Asignado:** `{self.target_email_info.get('alias_email')}` (Base: `{self.target_email_info.get('base_email')}`)  ",
            f"**Paso de Rotación:** #{self.target_email_info.get('step')} (Punto pos {self.target_email_info.get('dot_position_from_right')} desde la derecha)  ",
            "",
            "## 📝 1. Campos de Formulario Detectados",
            "| Campo / ID | Selector CSS Sugerido | Tipo | Placeholder |",
            "|---|---|---|---|"
        ]
        for name, inp in self.inputs_map.items():
            lines.append(f"| `{inp.get('name') or inp.get('id') or name}` | `{inp.get('selector')}` | `{inp.get('type')}` | `{inp.get('placeholder') or '-'}` |")

        lines.extend([
            "",
            "## 🌐 2. Endpoints & Tráfico de Red Relevante",
            "| Método | URL Endpoint | Status | Payload Preview |",
            "|---|---|---|---|"
        ])
        for r in self.requests:
            url = r.get("url", "")
            if any(k in url.lower() for k in ["api", "register", "login", "user", "kyc", "document", "session"]):
                method = r.get("method", "GET")
                status = r.get("status", "pending")
                body = str(r.get("post_data") or "-").replace("\n", " ")[:60]
                lines.append(f"| `{method}` | `{url}` | `{status}` | `{body}` |")

        if self.camera_hooks:
            lines.extend([
                "",
                "## 📷 3. Detección de Cámara & KYC (Selfie)",
                "| Timestamp | Constraints / Resolución | URL Origen |",
                "|---|---|---|"
            ])
            for c in self.camera_hooks:
                lines.append(f"| `{c.get('timestamp')}` | `{json.dumps(c.get('constraints'))}` | `{c.get('url')}` |")

        with open(SUMMARY_MD, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


SNIFFER_INJECTION_JS = """
(() => {
    if (window.__KCKY_SNIFFER_INITIALIZED__) return;
    window.__KCKY_SNIFFER_INITIALIZED__ = true;

    console.log("%c[KCKY] Sniffer Activo en Página", "color: #10b981; font-weight: bold; font-size: 14px;");

    // Función auxiliar para selector CSS robusto
    function getCssSelector(el) {
        if (!el || el.nodeType !== Node.ELEMENT_NODE) return '';
        if (el.id) return `#${CSS.escape(el.id)}`;
        if (el.name) return `${el.tagName.toLowerCase()}[name="${CSS.escape(el.name)}"]`;
        if (el.placeholder) return `${el.tagName.toLowerCase()}[placeholder*="${CSS.escape(el.placeholder.slice(0, 15))}"]`;
        
        let path = [];
        while (el && el.nodeType === Node.ELEMENT_NODE) {
            let selector = el.nodeName.toLowerCase();
            if (el.id) {
                selector += '#' + CSS.escape(el.id);
                path.unshift(selector);
                break;
            } else {
                let sib = el, nth = 1;
                while (sib = sib.previousElementSibling) {
                    if (sib.nodeName.toLowerCase() === selector) nth++;
                }
                if (nth !== 1) selector += `:nth-of-type(${nth})`;
            }
            path.unshift(selector);
            el = el.parentElement;
        }
        return path.join(' > ');
    }

    // Badge visual flotante
    const badge = document.createElement('div');
    badge.id = 'kcky-live-badge';
    badge.innerHTML = `
        <div style="position: fixed; top: 12px; right: 12px; z-index: 9999999; background: rgba(15, 23, 42, 0.95); color: #fff; padding: 8px 14px; border-radius: 8px; font-family: system-ui, sans-serif; font-size: 12px; border: 1px solid #10b981; box-shadow: 0 4px 15px rgba(0,0,0,0.5); display: flex; align-items: center; gap: 8px; pointer-events: none;">
            <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#10b981; animation: pulse 1.5s infinite;"></span>
            <strong>KCKY Sniffer</strong> | Mapeando en Vivo
        </div>
    `;
    document.body.appendChild(badge);

    // 1. Escuchar eventos de inputs y formularios
    ['input', 'change', 'blur'].forEach(evtType => {
        document.addEventListener(evtType, (e) => {
            const t = e.target;
            if (!t || !['INPUT', 'SELECT', 'TEXTAREA'].includes(t.tagName)) return;
            
            let val = t.value || '';
            let masked = (t.type === 'password') ? '••••••••' : (val.length > 30 ? val.slice(0, 30) + '...' : val);

            const payload = {
                type: evtType,
                tag: t.tagName.toLowerCase(),
                inputType: t.type || 'text',
                id: t.id || '',
                name: t.name || '',
                placeholder: t.placeholder || '',
                selector: getCssSelector(t),
                value_masked: masked,
                url: window.location.href
            };

            if (window.__kcky_bridge) {
                window.__kcky_bridge(JSON.stringify(payload));
            }
        }, true);
    });

    // 2. Escuchar clicks en botones o links
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('button, a, input[type="submit"], div[role="button"]');
        if (!btn) return;

        const payload = {
            type: 'click',
            tag: btn.tagName.toLowerCase(),
            text: (btn.innerText || btn.value || '').trim().slice(0, 40),
            selector: getCssSelector(btn),
            url: window.location.href
        };

        if (window.__kcky_bridge) {
            window.__kcky_bridge(JSON.stringify(payload));
        }
    }, true);

    // 3. Interceptar getUserMedia (Detección de Selfie / KYC)
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        const origGetUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
        navigator.mediaDevices.getUserMedia = async function(constraints) {
            console.log("%c[KCKY] getUserMedia llamado con constraints:", "color: #3b82f6;", constraints);
            const payload = {
                type: 'get_user_media',
                constraints: constraints,
                url: window.location.href,
                stack: new Error().stack
            };
            if (window.__kcky_bridge) {
                window.__kcky_bridge(JSON.stringify(payload));
            }
            return origGetUserMedia(constraints);
        };
    }
})();
"""


async def main():
    print("\n" + "="*70)
    print(" 👑 KCKY STUDIO — RECORDER & MAPPER DE REGISTRO BETMEXICO (CDP LIVE)")
    print("="*70)

    # 1. Asignar correo alias dot-trick
    conn = get_db_connection()
    next_email_info = get_next_available_email(conn)
    conn.close()

    print(f"\n📧 [CORREO SUGERIDO PARA ESTE REGISTRO]:")
    print(f"   ► Alias Exacto:   {next_email_info['alias_email']}")
    print(f"   ► Cuenta Base:    {next_email_info['base_email']}")
    print(f"   ► Posición Punto: #{next_email_info['dot_position_from_right']} (Paso {next_email_info['step']})")
    print(f"\n💡 Copia este correo al formulario de registro cuando te lo pida.\n")

    # 2. Localizar Chrome
    chrome_path = find_orbita_executable()
    if not chrome_path or not os.path.isfile(chrome_path):
        print(f"[!] No se encontró Chrome o navegador compatible.")
        return

    cdp_port = 9222
    temp_profile = tempfile.mkdtemp(prefix="kcky_mapper_profile_")
    target_url = "https://betmexico.mx/registro"

    print(f"[*] Lanzando navegador en tu pantalla física real (WinSta0\\Default)...")
    pid = launch_chrome_on_physical_desktop(chrome_path, cdp_port, temp_profile, target_url)
    if not pid:
        print(f"[!] Error iniciando Chrome en WinSta0\\Default.")
        return

    print(f"[+] Navegador activo (PID: {pid}). Conectando puente CDP en puerto {cdp_port}...")
    await asyncio.sleep(2.5)

    recorder = FlowRecorder(next_email_info)

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
            contexts = browser.contexts
            context = contexts[0] if contexts else await browser.new_context()

            # Configurar listeners para todas las páginas presentes y futuras
            async def setup_page_monitoring(page):
                logger.info(f"📄 Monitoreando página/pestaña: {page.url}")

                # Exponer función de puente JS -> Python
                await page.expose_function("__kcky_bridge", lambda data_str: recorder.record_dom_event(json.loads(data_str)))

                # Inyectar sniffer al cargar cualquier frame
                await page.add_init_script(SNIFFER_INJECTION_JS)

                # Monitorear requests
                page.on("request", lambda req: recorder.record_network({
                    "type": "request",
                    "method": req.method,
                    "url": req.url,
                    "post_data": req.post_data,
                    "headers": req.headers
                }))

                # Monitorear responses
                async def handle_response(resp):
                    url = resp.url
                    if any(k in url.lower() for k in ["api", "register", "login", "user", "kyc", "document", "session"]):
                        try:
                            body_text = await resp.text()
                        except Exception:
                            body_text = None

                        recorder.record_network({
                            "type": "response",
                            "status": resp.status,
                            "url": url,
                            "headers": resp.headers,
                            "response_body": body_text[:2000] if body_text else None
                        })

                page.on("response", handle_response)

                # Inyectar inmediatamente si ya cargó
                try:
                    await page.evaluate(SNIFFER_INJECTION_JS)
                except Exception:
                    pass

            for page in context.pages:
                await setup_page_monitoring(page)

            context.on("page", setup_page_monitoring)

            print("\n" + "="*70)
            print(" 🚀 SNIFFER ACTIVO — REALIZA EL REGISTRO MANUAL EN EL NAVEGADOR")
            print("="*70)
            print(" ► La consola mostrará en vivo cada campo, click y endpoint.")
            print(f" ► Resumen en tiempo real en: {SUMMARY_MD}")
            print(f" ► Datos crudos en: {CAPTURE_JSON}")
            print(" ► Cuando termines o pases a la selfie KYC, simplemente deja la ventana abierta o presiona Ctrl+C.")
            print("="*70 + "\n")

            # Loop de escucha activo
            while recorder.is_running:
                # Comprobar si todas las páginas se cerraron
                if not context.pages:
                    logger.info("Navegador cerrado por el usuario.")
                    break
                await asyncio.sleep(1.0)

        except KeyboardInterrupt:
            print("\n[*] Deteniendo sniffer por usuario...")
        except Exception as e:
            logger.error(f"Error en sesión CDP: {e}")
        finally:
            print(f"\n[+] Sesión finalizada. Archivo de resumen guardado en: {SUMMARY_MD}")


if __name__ == "__main__":
    asyncio.run(main())
