/**
 * K.C.K.Y. — Blackbox Wizard Controller (Caja Negra Ejecutable v2.0)
 */

const Studio = {
    currentStep: 1,
    uploadedFacePath: null,
    uploadedCropUrl: null,
    uploadedEnhancedUrl: null,
    imageType: null,
    generationMode: 'synthetic', // 'synthetic' | 'swap'
    targetPreset: 'female_clean_kyc_base.mp4',
    customVideoPath: null,
    activeY4mPath: null,
    activeMp4PreviewUrl: null,
    isGenerating: false,
    vcamActive: false,
    ws: null
};

document.addEventListener('DOMContentLoaded', () => {
    initWebSocket();
    initDropzone();
    initPanicReset();
    checkVirtualCamStatus();
});

/* ==========================================================================
   WEBSOCKET & TELEMETRY
   ========================================================================== */
function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

    Studio.ws = new WebSocket(wsUrl);

    Studio.ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'log') {
                updateLiveStatus(data.message);
            } else if (data.type === 'telemetry') {
                handleTelemetryEvent(data.event_type, data.data);
            }
        } catch (e) {
            console.error("WS Parse error:", e);
        }
    };

    Studio.ws.onclose = () => {
        setTimeout(initWebSocket, 3000);
    };
}

function updateLiveStatus(message) {
    const statusMsg = document.getElementById('progress-status-msg');
    if (statusMsg) {
        statusMsg.textContent = message;
    }
}

function handleTelemetryEvent(eventType, eventData) {
    if (eventType === 'KYC_SDK_DETECTED') {
        const sdk = eventData.data?.sdkName || eventData.sdkName || 'SDK KYC';
        showToast(`🔥 SDK Detectado en el sitio: ${sdk}`, 'success');
    } else if (eventType === 'GET_USER_MEDIA_GRANTED') {
        showToast(`✔️ Cámara WebRTC inyectada bajo identidad Logitech C920`, 'success');
    }
}

/* ==========================================================================
   STEPPER NAVIGATION
   ========================================================================== */
function goToStep(stepNum) {
    if (stepNum === 2 && !Studio.uploadedFacePath) {
        showToast("Primero sube una credencial o foto de rostro.", "error");
        return;
    }
    if (stepNum === 3 && !Studio.uploadedFacePath) {
        showToast("Debes cargar una identidad antes de continuar.", "error");
        return;
    }

    Studio.currentStep = stepNum;

    // Actualizar visual del stepper
    for (let i = 1; i <= 3; i++) {
        const nav = document.getElementById(`step-nav-i`.replace('i', i));
        const panel = document.getElementById(`step-panel-i`.replace('i', i));
        
        if (i === stepNum) {
            nav.className = 'step-indicator active';
            panel.className = 'step-panel active';
        } else if (i < stepNum) {
            nav.className = 'step-indicator completed';
            panel.className = 'step-panel';
        } else {
            nav.className = 'step-indicator disabled';
            panel.className = 'step-panel';
        }
    }
}

function resetToNewSession() {
    Studio.uploadedFacePath = null;
    Studio.uploadedCropUrl = null;
    Studio.uploadedEnhancedUrl = null;
    Studio.activeY4mPath = null;
    Studio.activeMp4PreviewUrl = null;
    Studio.isGenerating = false;

    document.getElementById('identity-result-box').style.display = 'none';
    document.getElementById('dropzone-idle-ui').style.display = 'block';
    document.getElementById('dropzone-scanning-ui').style.display = 'none';

    goToStep(1);
    showToast("Sesión reiniciada para nueva identidad.", "success");
}

/* ==========================================================================
   PASO 1: DROPZONE & EXTRACCIÓN FACIAL
   ========================================================================== */
function triggerFileInput(inputId, event) {
    if (event) event.stopPropagation();
    const input = document.getElementById(inputId);
    if (input) input.click();
}

function initDropzone() {
    const dropzone = document.getElementById('identity-dropzone');
    const fileInput = document.getElementById('identity-file-input');

    ['dragenter', 'dragover'].forEach(name => {
        dropzone.addEventListener(name, (e) => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        });
    });

    ['dragleave', 'drop'].forEach(name => {
        dropzone.addEventListener(name, (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
        });
    });

    dropzone.addEventListener('drop', (e) => {
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            handleImageUpload(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files.length > 0) {
            handleImageUpload(e.target.files[0]);
        }
    });
}

async function handleImageUpload(file) {
    const idleUI = document.getElementById('dropzone-idle-ui');
    const scanningUI = document.getElementById('dropzone-scanning-ui');
    const resultBox = document.getElementById('identity-result-box');

    idleUI.style.display = 'none';
    scanningUI.style.display = 'block';
    resultBox.style.display = 'none';

    const formData = new FormData();
    formData.append('file', file);

    try {
        const resp = await fetch('/api/extract-id-face', {
            method: 'POST',
            body: formData
        });

        const res = await resp.json();
        if (!resp.ok) {
            throw new Error(res.detail || "Fallo en la extracción de la imagen.");
        }

        Studio.uploadedFacePath = res.enhanced_file_path || res.crop_file_path;
        Studio.uploadedCropUrl = res.crop_url;
        Studio.uploadedEnhancedUrl = res.enhanced_url;
        Studio.imageType = res.metadata?.image_type || 'ID_CARD';

        // Mostrar vistas previas
        document.getElementById('img-crop-preview').src = res.crop_url;
        document.getElementById('img-enhanced-preview').src = res.enhanced_url;

        // Badge de tipo
        const typeBadge = document.getElementById('identity-detected-badge');
        const typeText = document.getElementById('identity-type-text');
        if (Studio.imageType === 'ID_CARD') {
            typeBadge.querySelector('.badge-icon').textContent = '🪪';
            typeText.textContent = res.metadata?.type_label || 'Credencial INE / ID Detectada';
        } else {
            typeBadge.querySelector('.badge-icon').textContent = '👤';
            typeText.textContent = res.metadata?.type_label || 'Selfie / Retrato Detectado';
        }

        scanningUI.style.display = 'none';
        resultBox.style.display = 'block';

        showToast("Rostro restaurado y calibrado a calidad HD.", "success");
    } catch (err) {
        console.error(err);
        scanningUI.style.display = 'none';
        idleUI.style.display = 'block';
        showToast(err.message || "Error al procesar la imagen.", "error");
    }
}

/* ==========================================================================
   PASO 2: DINÁMICA FACIAL & MODOS
   ========================================================================== */
function selectMotionMode(mode) {
    Studio.generationMode = mode;

    const cardSynth = document.getElementById('card-mode-synthetic');
    const cardSwap = document.getElementById('card-mode-swap');
    const subOptions = document.getElementById('swap-sub-options');

    if (mode === 'synthetic') {
        cardSynth.classList.add('active');
        cardSwap.classList.remove('active');
        subOptions.style.display = 'none';
    } else {
        cardSwap.classList.add('active');
        cardSynth.classList.remove('active');
        subOptions.style.display = 'block';
    }
}

function setSwapPreset(presetName, event) {
    if (event) event.stopPropagation();
    Studio.targetPreset = presetName;
    Studio.customVideoPath = null;

    document.querySelectorAll('.preset-btn').forEach(btn => btn.classList.remove('active'));
    if (event && event.target) {
        event.target.classList.add('active');
    }
    showToast(`Preset seleccionado: ${presetName}`, "success");
}

async function handleCustomVideoUpload(event) {
    if (!event.target.files || event.target.files.length === 0) return;
    const file = event.target.files[0];

    const formData = new FormData();
    formData.append('file', file);

    try {
        showToast("Subiendo video conductor...", "success");
        const resp = await fetch('/api/upload-target', { method: 'POST', body: formData });
        const res = await resp.json();
        if (!resp.ok) throw new Error(res.detail || "Error subiendo video");

        Studio.customVideoPath = res.file_path;
        showToast(`Video conductor cargado: ${res.filename}`, "success");
    } catch (err) {
        showToast(err.message || "Error al subir video", "error");
    }
}

/* ==========================================================================
   PASO 3: GENERACIÓN Y SALIDA
   ========================================================================== */
async function startGenerationAndGoStep3() {
    goToStep(3);

    const progressLayer = document.getElementById('monitor-progress-layer');
    const hudBadge = document.getElementById('hud-status-badge');
    const downloadBtn = document.getElementById('btn-download-video');

    progressLayer.style.display = 'flex';
    hudBadge.textContent = 'GENERANDO BUFFER...';
    Studio.isGenerating = true;

    try {
        const formData = new FormData();
        formData.append('duration', 90);
        formData.append('width', 1280);
        formData.append('height', 720);
        formData.append('fps', 30);
        formData.append('framing_mode', 'fill_crop');

        let endpoint = '/api/generate-liveness';
        if (Studio.generationMode === 'synthetic') {
            formData.append('face_path', Studio.uploadedFacePath);
        } else {
            endpoint = '/api/process-swap';
            formData.append('source_face_path', Studio.uploadedFacePath);
            formData.append('target_video_path', Studio.customVideoPath || Studio.targetPreset);
        }

        const resp = await fetch(endpoint, { method: 'POST', body: formData });
        const res = await resp.json();

        if (!resp.ok) {
            throw new Error(res.detail || "Error generando el flujo de video.");
        }

        Studio.activeY4mPath = res.y4m_path;
        Studio.activeMp4PreviewUrl = res.preview_url;

        // Cargar video en monitor
        const player = document.getElementById('live-monitor-player');
        const source = document.getElementById('live-monitor-source');
        source.src = res.preview_url;
        player.load();
        player.play();

        // Configurar botón de descarga
        downloadBtn.href = res.preview_url;

        progressLayer.style.display = 'none';
        hudBadge.textContent = 'STREAM ACTIVO EN BUFFER';
        showToast("✨ Flujo de cámara generado y armado con éxito.", "success");
    } catch (err) {
        console.error(err);
        progressLayer.style.display = 'none';
        hudBadge.textContent = 'ERROR EN PROCESO';
        showToast(err.message || "Error al procesar el flujo.", "error");
    } finally {
        Studio.isGenerating = false;
    }
}

/* ==========================================================================
   CANALES DE SALIDA
   ========================================================================= */
async function launchBrowserFlow() {
    if (!Studio.activeY4mPath) {
        showToast("El buffer aún se está generando. Por favor espera...", "error");
        return;
    }

    const targetUrl = document.getElementById('target-url-input').value.trim() || 'https://webcamtests.com';
    const btn = document.getElementById('btn-launch-browser-action');
    btn.disabled = true;
    btn.textContent = 'Abriendo Navegador Seguro...';

    try {
        const formData = new FormData();
        formData.append('y4m_path', Studio.activeY4mPath);
        formData.append('target_url', targetUrl);
        formData.append('hardware_persona', 'logitech_c920');

        const resp = await fetch('/api/launch-browser', { method: 'POST', body: formData });
        const res = await resp.json();

        if (!resp.ok) {
            throw new Error(res.detail || "Error al abrir el navegador");
        }

        showToast("🚀 Navegador lanzado con cámara Logitech C920 inyectada.", "success");
    } catch (err) {
        showToast(err.message || "Fallo al lanzar el navegador", "error");
    } finally {
        btn.disabled = false;
        btn.textContent = '🚀 Abrir Navegador con Cámara Armada';
    }
}

async function toggleSystemVirtualCam() {
    if (!Studio.activeMp4PreviewUrl && !Studio.activeY4mPath) {
        showToast("Genera el video primero antes de activar la cámara virtual.", "error");
        return;
    }

    const btn = document.getElementById('btn-toggle-vcam');
    const shouldStart = !Studio.vcamActive;

    try {
        let endpoint = '/api/virtual-cam/stop';
        const formData = new FormData();

        if (shouldStart) {
            endpoint = '/api/virtual-cam/start';
            formData.append('media_path', Studio.activeMp4PreviewUrl || Studio.activeY4mPath);
        }

        const resp = await fetch(endpoint, { method: 'POST', body: shouldStart ? formData : undefined });
        const res = await resp.json();

        if (shouldStart) {
            Studio.vcamActive = true;
            btn.classList.add('active');
            btn.textContent = 'Detener';
            showToast("🎥 Cámara virtual DirectShow transmitiendo en el sistema.", "success");
        } else {
            Studio.vcamActive = false;
            btn.classList.remove('active');
            btn.textContent = 'Activar';
            showToast("Cámara virtual detenida.", "success");
        }
    } catch (err) {
        showToast("Error controlando cámara virtual", "error");
    }
}

async function checkVirtualCamStatus() {
    try {
        const resp = await fetch('/api/virtual-cam/status');
        const res = await resp.json();
        const btn = document.getElementById('btn-toggle-vcam');
        if (res.active) {
            Studio.vcamActive = true;
            if (btn) {
                btn.classList.add('active');
                btn.textContent = 'Detener';
            }
        }
    } catch (e) {}
}

/* ==========================================================================
   PANIC RESET & TOASTS
   ========================================================================== */
function initPanicReset() {
    const btn = document.getElementById('btn-panic-reset');
    if (btn) {
        btn.addEventListener('click', async () => {
            try {
                await fetch('/api/panic-reset', { method: 'POST' });
                resetToNewSession();
                showToast("⚡ Memoria liberada y procesos detenidos.", "success");
            } catch (e) {
                showToast("Error en Panic Reset", "error");
            }
        });
    }
}

function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast-item ${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}
