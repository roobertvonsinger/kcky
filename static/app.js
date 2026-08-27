/**
 * ONBOARDED — Frontend Application Controller (v2.0 Zero-Friction Engine)
 */

const StudioApp = {
    generationMode: 'swap',
    uploadedFacePath: null,
    uploadedFaceFilename: null,
    uploadedTargetPath: 'data/presets/female_clean_kyc_base.mp4',
    uploadedTargetFilename: 'female_clean_kyc_base.mp4',
    activeY4mPath: null,
    activeMp4PreviewUrl: null,
    selectedHardwarePersona: 'logitech_c920',
    wsConnection: null,
    browserRunning: false,
    vcamRunning: false
};

document.addEventListener('DOMContentLoaded', () => {
    initWebSocket();
    initUniversalDropzone();
    loadSystemStatus();
    loadProfiles();
    setupPanicButton();
    checkExistingDefaults();
});

function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

    StudioApp.wsConnection = new WebSocket(wsUrl);

    StudioApp.wsConnection.onopen = () => {
        appendLogLine("Conexión activa con el motor de telemetría y sniffer.", "system");
    };

    StudioApp.wsConnection.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'log') {
                appendLogLine(data.message, data.level || 'info');
            } else if (data.type === 'telemetry') {
                handleTelemetryEvent(data.event_type, data.data);
            }
        } catch (e) {
            console.error("Error procesando WebSocket:", e);
        }
    };

    StudioApp.wsConnection.onclose = () => {
        setTimeout(initWebSocket, 3000);
    };
}

function appendLogLine(message, level = 'info') {
    const terminalBody = document.getElementById('terminal-body');
    if (!terminalBody) return;

    const timeStr = new Date().toLocaleTimeString();
    const line = document.createElement('div');
    line.className = `term-line ${level}`;
    line.innerHTML = `<span class="term-time">[${timeStr}]</span> ${escapeHtml(message)}`;

    terminalBody.appendChild(line);
    terminalBody.scrollTop = terminalBody.scrollHeight;
}

function clearTerminalLogs() {
    const terminalBody = document.getElementById('terminal-body');
    if (terminalBody) {
        terminalBody.innerHTML = '';
        appendLogLine("Terminal reiniciada.", "system");
    }
}

function handleTelemetryEvent(eventType, eventData) {
    const timeStr = new Date().toLocaleTimeString();
    if (eventType === 'KYC_SDK_DETECTED') {
        const sdkName = eventData.data?.sdkName || eventData.sdkName || 'Desconocido';
        appendLogLine(`🔥 SDK KYC Detectado en el sitio: ${sdkName}`, 'warning');
        highlightSdkBadge(sdkName);
    } else if (eventType === 'GET_USER_MEDIA_REQUESTED') {
        appendLogLine(`📹 WebRTC getUserMedia solicitado por el sitio web.`, 'info');
    } else if (eventType === 'GET_USER_MEDIA_GRANTED') {
        appendLogLine(`✔️ Stream WebRTC inyectado y aceptado bajo identidad Logitech C920.`, 'success');
    }
}

function highlightSdkBadge(sdkName) {
    const normalized = sdkName.toLowerCase();
    let badgeId = null;

    if (normalized.includes('incode')) badgeId = 'sdk-incode';
    else if (normalized.includes('veriff')) badgeId = 'sdk-veriff';
    else if (normalized.includes('metamap') || normalized.includes('mati')) badgeId = 'sdk-metamap';
    else if (normalized.includes('sumsub')) badgeId = 'sdk-sumsub';
    else if (normalized.includes('onfido')) badgeId = 'sdk-onfido';

    if (badgeId) {
        const badge = document.getElementById(badgeId);
        if (badge) {
            badge.classList.add('detected');
        }
    }
}

function initUniversalDropzone() {
    const dropzone = document.getElementById('universal-dropzone');
    const fileInput = document.getElementById('universal-file-input');

    if (dropzone && fileInput) {
        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.classList.add('drag-over');
        });

        dropzone.addEventListener('dragleave', () => {
            dropzone.classList.remove('drag-over');
        });

        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('drag-over');
            if (e.dataTransfer.files.length > 0) {
                handleUniversalUpload(e.dataTransfer.files[0]);
            }
        });

        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                handleUniversalUpload(e.target.files[0]);
            }
        });
    }
}

function triggerFileInput(id, event) {
    if (event) {
        event.stopPropagation();
        event.preventDefault();
    }
    const el = document.getElementById(id);
    if (el) el.click();
}

async function handleUniversalUpload(file) {
    const formData = new FormData();
    formData.append('file', file);

    appendLogLine(`Cargando archivo: ${file.name}...`, 'info');

    // Intentar primero como credencial para auto-crop + GFPGAN
    try {
        const resp = await fetch('/api/extract-id-face', { method: 'POST', body: formData });
        const res = await resp.json();

        if (resp.ok && res.status === 'success') {
            StudioApp.uploadedFacePath = res.enhanced_file_path;
            StudioApp.uploadedFaceFilename = file.name;

            document.getElementById('universal-dropzone').style.display = 'none';
            const previewBox = document.getElementById('identity-preview-box');
            document.getElementById('id-crop-preview').src = res.crop_url;
            document.getElementById('id-enhanced-preview').src = res.enhanced_url;
            document.getElementById('identity-status-label').textContent = `✔️ INE Detectada · Rostro restaurado en HD (${res.metadata.enhanced_size || '1024x1024'})`;
            previewBox.style.display = 'block';

            appendLogLine(`Credencial INE procesada exitosamente con GFPGAN Super-Resolución.`, 'success');
            return;
        }
    } catch (e) {
        // Fallback a carga directa de foto
    }

    // Carga directa de selfie normal
    try {
        const respDirect = await fetch('/api/upload-face', { method: 'POST', body: formData });
        const resDirect = await respDirect.json();

        if (respDirect.ok) {
            StudioApp.uploadedFacePath = resDirect.file_path;
            StudioApp.uploadedFaceFilename = resDirect.filename;

            document.getElementById('universal-dropzone').style.display = 'none';
            const previewBox = document.getElementById('identity-preview-box');
            document.getElementById('id-crop-preview').src = resDirect.preview_url;
            document.getElementById('id-enhanced-preview').src = resDirect.preview_url;
            document.getElementById('identity-status-label').textContent = `✔️ Foto de rostro cargada (${file.name})`;
            previewBox.style.display = 'block';

            appendLogLine(`Rostro cargado: ${resDirect.filename}`, 'success');
        } else {
            alert(`Error cargando imagen: ${resDirect.detail}`);
        }
    } catch (e) {
        console.error(e);
        appendLogLine(`Error subiendo imagen: ${e.message}`, 'error');
    }
}

function toggleGenMode(mode) {
    StudioApp.generationMode = mode;
    document.getElementById('mode-opt-swap').classList.toggle('active', mode === 'swap');
    document.getElementById('mode-opt-synthetic').classList.toggle('active', mode === 'synthetic');

    const presetsContainer = document.getElementById('swap-presets-container');
    if (presetsContainer) {
        presetsContainer.style.display = mode === 'swap' ? 'block' : 'none';
    }

    const subTitle = document.getElementById('btn-master-sub');
    if (subTitle) {
        subTitle.textContent = mode === 'swap' 
            ? 'DirectML Face Swap + Logitech C920 Spoofing' 
            : 'Liveness Orgánico 3D (Parpadeo/Respiración) + Spoofing';
    }
}

function selectPresetVideo(presetId, relativePath) {
    StudioApp.uploadedTargetPath = relativePath;
    StudioApp.uploadedTargetFilename = presetId;

    document.querySelectorAll('.preset-chip-btn').forEach(b => b.classList.remove('active'));
    if (presetId.includes('clean')) {
        const b = document.getElementById('preset-btn-clean');
        if (b) b.classList.add('active');
    } else {
        const b = document.getElementById('preset-btn-alt');
        if (b) b.classList.add('active');
    }

    appendLogLine(`Preset de video base seleccionado: ${presetId}`, 'info');
}

function setQuickUrl(url) {
    const input = document.getElementById('target-url-input');
    if (input) {
        input.value = url;
        appendLogLine(`URL destino establecida: ${url}`, 'info');
    }
}

function selectHardwarePersona(persona) {
    StudioApp.selectedHardwarePersona = persona;
    const personaSelect = document.getElementById('select-hw-persona');
    if (personaSelect && personaSelect.value !== persona) {
        personaSelect.value = persona;
    }
    const label = persona === 'logitech_c920' ? 'Logitech C920' : (persona === 'integrated' ? 'Integrated Cam' : 'HP Wide Vision');
    document.getElementById('orbita-value').textContent = label;
}

/**
 * EL DISPARO MAESTRO DE 1 CLIC (Zero-Friction Auto-Pipeline)
 */
async function executeFullPipeline() {
    if (!StudioApp.uploadedFacePath) {
        alert("Por favor arrastra primero la credencial INE o foto del rostro.");
        return;
    }

    const btn = document.getElementById('btn-master-launch');
    const progress = document.getElementById('master-progress');
    const statusText = document.getElementById('master-progress-status');

    btn.disabled = true;
    progress.style.display = 'flex';

    const resolution = (document.getElementById('setting-resolution')?.value || '1280x720').split('x');
    const width = parseInt(resolution[0], 10);
    const height = parseInt(resolution[1], 10);
    const duration = parseInt(document.getElementById('setting-duration')?.value || '90', 10);
    const targetUrl = document.getElementById('target-url-input')?.value.trim() || 'https://webcamtests.com/';
    const profileId = document.getElementById('select-profile')?.value || 'temporary_clean_profile';

    try {
        // 1. Generar Buffer
        const formData = new FormData();
        formData.append('duration', duration);
        formData.append('width', width);
        formData.append('height', height);
        formData.append('fps', 30);
        formData.append('framing_mode', 'fill_crop');

        let endpoint = '/api/process-swap';
        if (StudioApp.generationMode === 'synthetic') {
            endpoint = '/api/generate-liveness';
            formData.append('face_path', StudioApp.uploadedFacePath);
            statusText.textContent = "1/2 Sintetizando Liveness 3D Orgánico (Parpadeo / Respiración / 3D Sway)...";
            appendLogLine("Generando Liveness Orgánico 3D...", "info");
        } else {
            formData.append('source_face_path', StudioApp.uploadedFacePath);
            formData.append('target_video_path', StudioApp.uploadedTargetPath);
            statusText.textContent = "1/2 Procesando Face Swap en GPU (AMD Radeon DirectML + GFPGAN-1024)...";
            appendLogLine("Procesando Face Swap con DirectML y GFPGAN-1024...", "info");
        }

        const resp = await fetch(endpoint, { method: 'POST', body: formData });
        const res = await resp.json();

        if (!resp.ok) {
            throw new Error(res.detail || "Error en generación de buffer");
        }

        StudioApp.activeY4mPath = res.y4m_path;
        StudioApp.activeMp4PreviewUrl = res.preview_url;

        // Actualizar video monitor en vivo
        const player = document.getElementById('buffer-video-player');
        const source = document.getElementById('buffer-video-source');
        source.src = res.preview_url;
        player.load();
        player.play();

        document.getElementById('hud-status-text').textContent = 'TRANSMITIENDO EN VIVO';
        document.getElementById('hud-specs').textContent = `${width}x${height} @ 30fps`;
        document.getElementById('hud-buffer-name').textContent = res.y4m_path.split(/[\\/]/).pop();
        document.getElementById('session-value').textContent = 'Activa';
        document.getElementById('session-dot').className = 'dot-indicator green';

        appendLogLine(`Buffer de cámara armado exitosamente (${res.metadata?.size_mb || 'OK'} MB).`, "success");

        // 2. Lanzar Navegador con inyección WebRTC
        statusText.textContent = `2/2 Lanzando Navegador con cámara armada hacia ${targetUrl}...`;
        appendLogLine(`Abriendo navegador con identidad ${StudioApp.selectedHardwarePersona}...`, "info");

        const launchData = new FormData();
        launchData.append('target_url', targetUrl);
        launchData.append('profile_id', profileId);
        launchData.append('hardware_persona', StudioApp.selectedHardwarePersona);
        launchData.append('y4m_path', res.y4m_path);

        const respLaunch = await fetch('/api/launch-browser', { method: 'POST', body: launchData });
        const resLaunch = await respLaunch.json();

        if (!respLaunch.ok) {
            throw new Error(resLaunch.detail || "Error al lanzar navegador");
        }

        appendLogLine(`🚀 ¡Navegador abierto exitosamente en ${targetUrl}! WebRTC activo y protegido.`, "success");
        statusText.textContent = "✔️ ¡Cámara y Navegador 100% Operativos!";

    } catch (e) {
        console.error(e);
        alert(`Error en el pipeline: ${e.message}`);
        appendLogLine(`Error: ${e.message}`, "error");
    } finally {
        btn.disabled = false;
        setTimeout(() => {
            progress.style.display = 'none';
        }, 3000);
    }
}

async function toggleSystemVirtualCam() {
    const btn = document.getElementById('btn-toggle-vcam');
    const badge = document.getElementById('vcam-status-badge');

    if (!StudioApp.vcamRunning) {
        try {
            const resp = await fetch('/api/virtual-cam/start', { method: 'POST' });
            const res = await resp.json();
            if (resp.ok) {
                StudioApp.vcamRunning = true;
                badge.textContent = 'ACTIVO (OBS/SYS)';
                badge.style.background = 'rgba(0, 240, 144, 0.2)';
                badge.style.color = '#00f090';
                btn.textContent = 'DETENER';
                btn.style.background = '#ff2a70';
                btn.style.color = '#fff';
                appendLogLine(`Cámara Virtual DirectShow activa en el sistema operativo.`, 'success');
            } else {
                alert(`Error: ${res.detail}`);
            }
        } catch (e) {
            console.error(e);
        }
    } else {
        try {
            const resp = await fetch('/api/virtual-cam/stop', { method: 'POST' });
            if (resp.ok) {
                StudioApp.vcamRunning = false;
                badge.textContent = 'INACTIVO';
                badge.style.background = 'rgba(255,255,255,0.08)';
                badge.style.color = '#8b949e';
                btn.textContent = 'TRANSMITIR';
                btn.style.background = '#00f090';
                btn.style.color = '#06090e';
                appendLogLine(`Cámara Virtual DirectShow detenida.`, 'info');
            }
        } catch (e) {
            console.error(e);
        }
    }
}

async function loadSystemStatus() {
    try {
        const resp = await fetch('/api/status');
        const res = await resp.json();
        if (resp.ok) {
            if (res.active_buffer?.preview_mp4) {
                StudioApp.activeMp4PreviewUrl = res.active_buffer.preview_mp4;
                const player = document.getElementById('buffer-video-player');
                const source = document.getElementById('buffer-video-source');
                source.src = res.active_buffer.preview_mp4;
                player.load();
                player.play();
                document.getElementById('hud-status-text').textContent = 'BUFFER PREVIO LISTO';
            }
            if (res.gpu_vendor) {
                document.getElementById('gpu-value').textContent = 'AMD RX 580 (DirectML)';
            }
        }
    } catch (e) { }
}

async function loadProfiles() {
    try {
        const resp = await fetch('/api/profiles');
        const res = await resp.json();
        const select = document.getElementById('select-profile');
        if (resp.ok && res.profiles && select) {
            select.innerHTML = '<option value="temporary_clean_profile" selected>Perfil Limpio Temporal (Recomendado)</option>';
            res.profiles.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = `${p.name} (GoLogin)`;
                select.appendChild(opt);
            });
        }
    } catch (e) { }
}

function setupPanicButton() {
    const btn = document.getElementById('btn-panic-reset');
    if (btn) {
        btn.addEventListener('click', async () => {
            if (confirm("¿Deseas realizar un Panic Reset? Cerrará procesos de Chromium, detendrá ffmpeg y liberará VRAM.")) {
                try {
                    await fetch('/api/panic-reset', { method: 'POST' });
                    appendLogLine("🚨 Panic Reset ejecutado exitosamente.", "warning");
                    document.getElementById('session-value').textContent = 'Reset';
                    document.getElementById('session-dot').className = 'dot-indicator gray';
                } catch (e) { }
            }
        });
    }
}

function checkExistingDefaults() {
    // Si hay una imagen previa guardada, cargarla para conveniencia
    StudioApp.uploadedTargetPath = 'data/presets/female_clean_kyc_base.mp4';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
