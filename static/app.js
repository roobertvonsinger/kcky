/**
 * ONBOARDED — Frontend Application Controller
 */

const StudioApp = {
    currentStep: 1,
    generationMode: 'synthetic',
    uploadedFacePath: null,
    uploadedFaceFilename: null,
    uploadedTargetPath: null,
    uploadedTargetFilename: null,
    activeY4mPath: null,
    activeMp4PreviewUrl: null,
    selectedHardwarePersona: 'logitech_c920',
    wsConnection: null,
    browserRunning: false
};

document.addEventListener('DOMContentLoaded', () => {
    initWebSocket();
    initDropzones();
    loadSystemStatus();
    loadProfiles();
    setupPanicButton();
});

function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

    StudioApp.wsConnection = new WebSocket(wsUrl);

    StudioApp.wsConnection.onopen = () => {
        appendLogLine("Conexión WebSocket establecida con Onboarded Engine.", "system");
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
    const telemetryList = document.getElementById('telemetry-events-list');
    if (!telemetryList) return;

    const emptyHint = telemetryList.querySelector('.empty-event-hint');
    if (emptyHint) emptyHint.remove();

    const timeStr = new Date().toLocaleTimeString();
    const row = document.createElement('div');
    row.className = 'telemetry-event-row';

    if (eventType === 'KYC_SDK_DETECTED') {
        const sdkName = eventData.data?.sdkName || eventData.sdkName || 'Desconocido';
        row.innerHTML = `<span class="ev-time">[${timeStr}]</span> <span class="ev-type sdk">[SDK DETECTADO]</span> <span class="ev-detail">Proveedor KYC activo: <strong>${sdkName}</strong></span>`;
        highlightSdkBadge(sdkName);
    } else if (eventType === 'GET_USER_MEDIA_REQUESTED') {
        const constraints = JSON.stringify(eventData.data?.constraints || {});
        row.innerHTML = `<span class="ev-time">[${timeStr}]</span> <span class="ev-type gum">[GUM SOLICITADO]</span> <span class="ev-detail">Constraints: ${constraints}</span>`;
    } else if (eventType === 'GET_USER_MEDIA_GRANTED') {
        row.innerHTML = `<span class="ev-time">[${timeStr}]</span> <span class="ev-type gum">[GUM CONCEDIDO]</span> <span class="ev-detail">Stream WebRTC inyectado y activo.</span>`;
    } else if (eventType === 'CANVAS_SNAPSHOT_CAPTURED') {
        const dim = `${eventData.data?.canvasWidth || 0}x${eventData.data?.canvasHeight || 0}`;
        row.innerHTML = `<span class="ev-time">[${timeStr}]</span> <span class="ev-type canvas">[SNAP CANVAS]</span> <span class="ev-detail">Instantánea de rostro tomada por el SDK (${dim})</span>`;
    } else {
        row.innerHTML = `<span class="ev-time">[${timeStr}]</span> <span class="ev-type">[${eventType}]</span> <span class="ev-detail">${JSON.stringify(eventData.data || {})}</span>`;
    }

    telemetryList.insertBefore(row, telemetryList.firstChild);
}

function highlightSdkBadge(sdkName) {
    const normalized = sdkName.toLowerCase();
    let badgeId = null;

    if (normalized.includes('incode')) badgeId = 'sdk-incode';
    else if (normalized.includes('veriff')) badgeId = 'sdk-veriff';
    else if (normalized.includes('truora')) badgeId = 'sdk-truora';
    else if (normalized.includes('metamap') || normalized.includes('mati')) badgeId = 'sdk-metamap';
    else if (normalized.includes('jumio')) badgeId = 'sdk-jumio';
    else if (normalized.includes('sumsub')) badgeId = 'sdk-sumsub';
    else if (normalized.includes('onfido')) badgeId = 'sdk-onfido';

    if (badgeId) {
        const badge = document.getElementById(badgeId);
        if (badge) {
            badge.classList.add('detected');
            badge.querySelector('.sdk-icon').textContent = '🔥';
        }
    }
}

function switchStep(stepNum) {
    if (stepNum === 2 && !StudioApp.activeY4mPath) {
        alert("Primero debes generar un buffer de cámara en el Paso 1.");
        return;
    }
    if (stepNum === 3 && !StudioApp.activeY4mPath) {
        alert("Se requiere un buffer de cámara antes de proceder a la inyección.");
        return;
    }

    StudioApp.currentStep = stepNum;

    document.querySelectorAll('.step-item').forEach((btn, idx) => {
        btn.classList.toggle('active', idx + 1 === stepNum);
    });

    document.querySelectorAll('.step-panel').forEach((panel, idx) => {
        panel.classList.toggle('active', idx + 1 === stepNum);
    });
}

function toggleGenMode(mode) {
    StudioApp.generationMode = mode;
    document.getElementById('mode-opt-synthetic').classList.toggle('active', mode === 'synthetic');
    document.getElementById('mode-opt-swap').classList.toggle('active', mode === 'swap');

    const targetBox = document.getElementById('target-video-box');
    if (targetBox) {
        targetBox.style.display = mode === 'swap' ? 'block' : 'none';
    }
}

function selectHardwarePersona(persona) {
    StudioApp.selectedHardwarePersona = persona;
    document.querySelectorAll('.hw-persona-card').forEach(c => c.classList.remove('active'));
    
    if (persona === 'logitech_c920') document.getElementById('hw-opt-c920').classList.add('active');
    else if (persona === 'integrated') document.getElementById('hw-opt-integrated').classList.add('active');
    else if (persona === 'hp_wide') document.getElementById('hw-opt-hpwide').classList.add('active');
}

function initDropzones() {
    const faceDrop = document.getElementById('face-dropzone');
    const faceInput = document.getElementById('face-file-input');

    if (faceDrop && faceInput) {
        faceDrop.addEventListener('click', () => {
            if (!StudioApp.uploadedFacePath) faceInput.click();
        });

        faceDrop.addEventListener('dragover', (e) => {
            e.preventDefault();
            faceDrop.classList.add('drag-over');
        });

        faceDrop.addEventListener('dragleave', () => {
            faceDrop.classList.remove('drag-over');
        });

        faceDrop.addEventListener('drop', (e) => {
            e.preventDefault();
            faceDrop.classList.remove('drag-over');
            if (e.dataTransfer.files.length > 0) {
                handleFaceUpload(e.dataTransfer.files[0]);
            }
        });

        faceInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                handleFaceUpload(e.target.files[0]);
            }
        });
    }

    const targetInput = document.getElementById('target-file-input');
    if (targetInput) {
        targetInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                handleTargetUpload(e.target.files[0]);
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

async function handleFaceUpload(file) {
    const formData = new FormData();
    formData.append('file', file);

    appendLogLine(`Subiendo imagen de rostro: ${file.name}...`, 'info');

    try {
        const resp = await fetch('/api/upload-face', { method: 'POST', body: formData });
        const res = await resp.json();
        if (resp.ok) {
            StudioApp.uploadedFacePath = res.file_path;
            StudioApp.uploadedFaceFilename = res.filename;
            // Reset buffer activo previo para obligar a nueva generación
            StudioApp.activeY4mPath = null;
            StudioApp.activeMp4PreviewUrl = null;

            document.getElementById('dropzone-idle').style.display = 'none';
            const previewCont = document.getElementById('face-preview-container');
            const previewImg = document.getElementById('face-preview-img');
            const fileNameTag = document.getElementById('face-file-name');

            previewImg.src = res.preview_url;
            fileNameTag.textContent = file.name;
            previewCont.style.display = 'block';

            appendLogLine(`Rostro cargado exitosamente: ${res.filename}`, 'success');
        } else {
            alert(`Error subiendo rostro: ${res.detail}`);
        }
    } catch (e) {
        console.error(e);
        appendLogLine(`Error subiendo rostro: ${e.message}`, 'error');
    }
}

async function handleTargetUpload(file) {
    const formData = new FormData();
    formData.append('file', file);

    appendLogLine(`Subiendo video base: ${file.name}...`, 'info');

    try {
        const resp = await fetch('/api/upload-target', { method: 'POST', body: formData });
        const res = await resp.json();
        if (resp.ok) {
            StudioApp.uploadedTargetPath = res.file_path;
            StudioApp.uploadedTargetFilename = res.filename;

            document.getElementById('target-file-name').textContent = `Video Cargado: ${file.name}`;
            appendLogLine(`Video base listo: ${res.filename}`, 'success');
        } else {
            alert(`Error: ${res.detail}`);
        }
    } catch (e) {
        console.error(e);
    }
}

async function processStage1() {
    if (!StudioApp.uploadedFacePath) {
        alert("Por favor sube primero la foto del rostro (INE / Selfie).");
        return;
    }

    if (StudioApp.generationMode === 'swap' && !StudioApp.uploadedTargetPath) {
        alert("En modo Face Swap debes seleccionar un video base objetivo.");
        return;
    }

    const btn = document.getElementById('btn-process-stage1');
    const progress = document.getElementById('stage1-progress');
    const statusText = document.getElementById('stage1-status-text');

    btn.disabled = true;
    progress.style.display = 'flex';

    const resolution = document.getElementById('setting-resolution').value.split('x');
    const width = parseInt(resolution[0], 10);
    const height = parseInt(resolution[1], 10);
    const duration = parseInt(document.getElementById('setting-duration').value, 10);
    const fps = parseInt(document.getElementById('setting-fps').value, 10);
    const framingMode = document.getElementById('setting-framing') ? document.getElementById('setting-framing').value : 'fill_crop';

    const formData = new FormData();
    formData.append('duration', duration);
    formData.append('width', width);
    formData.append('height', height);
    formData.append('fps', fps);
    formData.append('framing_mode', framingMode);

    try {
        let endpoint = '/api/generate-liveness';
        if (StudioApp.generationMode === 'synthetic') {
            formData.append('face_path', StudioApp.uploadedFacePath);
            statusText.textContent = "Sintetizando Liveness 3D, micro-movimiento y ruido CMOS...";
        } else {
            endpoint = '/api/process-swap';
            formData.append('source_face_path', StudioApp.uploadedFacePath);
            formData.append('target_video_path', StudioApp.uploadedTargetPath);
            statusText.textContent = "Procesando Face Swap con DirectML (AMD RX 580)...";
        }

        const resp = await fetch(endpoint, { method: 'POST', body: formData });
        const res = await resp.json();

        if (resp.ok) {
            StudioApp.activeY4mPath = res.y4m_path;
            StudioApp.activeMp4PreviewUrl = res.preview_url;

            appendLogLine(`Cámara armada y lista (${res.metadata.size_mb} MB, ${width}x${height}).`, 'success');

            const player = document.getElementById('buffer-video-player');
            const source = document.getElementById('buffer-video-source');
            source.src = res.preview_url;
            player.load();
            player.play();

            document.getElementById('hud-specs').textContent = `${width}x${height} @ ${fps}fps`;
            document.getElementById('hud-buffer-name').textContent = res.y4m_path.split(/[\\/]/).pop();
            document.getElementById('hud-duration').textContent = `${duration}s Loop Ready`;
            
            const framingTag = document.getElementById('metric-framing-val');
            if (framingTag) {
                framingTag.textContent = framingMode === 'fill_crop' ? 'Sensor Real (Fill Crop)' : 'Padding Centrado';
            }

            switchStep(2);
        } else {
            alert(`Error generando buffer: ${res.detail}`);
            appendLogLine(`Error: ${res.detail}`, 'error');
        }
    } catch (e) {
        console.error(e);
        appendLogLine(`Error en generación: ${e.message}`, 'error');
    } finally {
        btn.disabled = false;
        progress.style.display = 'none';
    }
}

async function launchBrowserInjection() {
    if (!StudioApp.activeY4mPath) {
        alert("No hay ningún buffer Y4M activo para inyectar.");
        return;
    }

    const profileId = document.getElementById('select-profile').value;
    const rawTargetUrl = document.getElementById('target-url-input').value.trim();
    const targetUrl = rawTargetUrl || 'about:blank';
    const btn = document.getElementById('btn-launch-browser');

    btn.disabled = true;
    appendLogLine(`Abriendo navegador con cámara armada hacia ${targetUrl}...`, 'info');

    const formData = new FormData();
    formData.append('target_url', targetUrl);
    formData.append('profile_id', profileId);
    formData.append('hardware_persona', StudioApp.selectedHardwarePersona);
    formData.append('y4m_path', StudioApp.activeY4mPath);

    try {
        const resp = await fetch('/api/launch-browser', { method: 'POST', body: formData });
        const res = await resp.json();

        if (resp.ok) {
            StudioApp.browserRunning = true;
            updateSessionPill(true, res.cdp_port);
            appendLogLine(`Navegador lanzado exitosamente (CDP :${res.cdp_port}).`, 'success');
        } else {
            alert(`Error lanzando navegador: ${res.detail}`);
            appendLogLine(`Error: ${res.detail}`, 'error');
        }
    } catch (e) {
        console.error(e);
        appendLogLine(`Error de red: ${e.message}`, 'error');
    } finally {
        btn.disabled = false;
    }
}

function setUrlPreset(url) {
    const input = document.getElementById('target-url-input');
    if (input) input.value = url;
}

async function loadSystemStatus() {
    try {
        const resp = await fetch('/api/status');
        const data = await resp.json();

        if (data.gpu_vendor) {
            document.getElementById('gpu-value').textContent = 'AMD RX 580 (DirectML)';
        }

        if (data.orbita_installed) {
            document.getElementById('orbita-value').textContent = 'Listo (Orbita)';
        } else {
            document.getElementById('orbita-value').textContent = 'Chrome Estándar';
        }

        if (data.active_buffer && data.active_buffer.preview_mp4) {
            StudioApp.activeY4mPath = data.active_buffer.y4m;
            StudioApp.activeMp4PreviewUrl = data.active_buffer.preview_mp4;
        }

        if (data.browser_running) {
            updateSessionPill(true, data.cdp_port);
        }
    } catch (e) {
        console.error("Error cargando estado:", e);
    }
}

async function loadProfiles() {
    try {
        const resp = await fetch('/api/profiles');
        const data = await resp.json();
        const select = document.getElementById('select-profile');
        if (!select) return;

        select.innerHTML = '';
        data.profiles.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = p.name;
            select.appendChild(opt);
        });
    } catch (e) {
        console.error("Error cargando perfiles:", e);
    }
}

function updateSessionPill(isActive, cdpPort) {
    const dot = document.getElementById('session-dot');
    const val = document.getElementById('session-value');
    if (isActive) {
        dot.className = 'dot-indicator green';
        val.textContent = `Activa (CDP :${cdpPort})`;
    } else {
        dot.className = 'dot-indicator gray';
        val.textContent = 'Inactiva';
    }
}

function setupPanicButton() {
    const btn = document.getElementById('btn-panic-reset');
    if (btn) {
        btn.addEventListener('click', async () => {
            if (confirm("¿Deseas detener de inmediato todos los procesos de prueba y liberar VRAM?")) {
                try {
                    const resp = await fetch('/api/panic-reset', { method: 'POST' });
                    const res = await resp.json();
                    updateSessionPill(false);
                    appendLogLine("Panic Reset ejecutado exitosamente.", "warning");
                } catch (e) {
                    console.error(e);
                }
            }
        });
    }
}

function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}
