/**
 * KCKY — Mobile-First Wizard Controller & Real-Time Render Telemetry
 */

const Studio = {
    currentStep: 1,
    uploadedFacePath: null,
    uploadedCropUrl: null,
    uploadedEnhancedUrl: null,
    imageType: null,
    generationMode: 'swap', // 'swap' (Recomendado) | 'synthetic'
    targetPreset: 'female_clean_kyc_base.mp4',
    customVideoPath: null,
    activeY4mPath: null,
    activeMp4PreviewUrl: null,
    isGenerating: false,
    vcamActive: false,
    ws: null,
    progressPollInterval: null,
    availablePresets: []
};

async function safeFetchJson(url, options = {}) {
    const resp = await fetch(url, options);
    const text = await resp.text();
    let data;
    try {
        data = JSON.parse(text);
    } catch (e) {
        if (!resp.ok) {
            throw new Error(`Error del servidor (${resp.status}): ${text.slice(0, 120)}`);
        }
        throw new Error("Respuesta inválida del servidor");
    }
    if (!resp.ok) {
        throw new Error(data.detail || data.message || `Error del servidor (${resp.status})`);
    }
    return data;
}

document.addEventListener('DOMContentLoaded', () => {
    initWebSocket();
    initDropzone();
    initPanicReset();
    checkVirtualCamStatus();
    loadPresetsCatalog();
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
                updateLiveLogMessage(data.message);
            } else if (data.type === 'telemetry') {
                if (data.event_type === 'RENDER_PROGRESS') {
                    handleRenderProgress(data.data);
                } else {
                    handleTelemetryEvent(data.event_type, data.data);
                }
            }
        } catch (e) {
            console.error("WS Parse error:", e);
        }
    };

    Studio.ws.onclose = () => {
        setTimeout(initWebSocket, 3000);
    };
}

function updateLiveLogMessage(message) {
    const statusMsg = document.getElementById('progress-status-msg');
    if (statusMsg && Studio.isGenerating) {
        statusMsg.textContent = message;
    }
}

function handleTelemetryEvent(eventType, eventData) {
    if (eventType === 'KYC_SDK_DETECTED') {
        const sdk = eventData.data?.sdkName || eventData.sdkName || 'SDK KYC';
        showToast(`🔥 SDK Detectado: ${sdk}`, 'success');
    } else if (eventType === 'GET_USER_MEDIA_GRANTED') {
        showToast(`✔️ Cámara WebRTC inyectada con éxito`, 'success');
    }
}

/* ==========================================================================
   BARRA DE PROGRESO CON PORCENTAJE REAL & ETA
   ========================================================================== */
function handleRenderProgress(prog) {
    if (!prog) return;

    const percent = Math.min(100, Math.max(0, prog.percent || 0));
    const percentNum = document.getElementById('progress-percent-num');
    const barFill = document.getElementById('progress-bar-fill');
    const statusMsg = document.getElementById('progress-status-msg');
    const framesTxt = document.getElementById('progress-frames-txt');
    const etaTxt = document.getElementById('progress-eta-txt');

    if (percentNum) percentNum.textContent = percent;
    if (barFill) barFill.style.width = `${percent}%`;

    if (statusMsg && prog.status_text) {
        statusMsg.textContent = prog.status_text;
    }

    if (framesTxt) {
        if (prog.total_frames && prog.total_frames > 0) {
            framesTxt.textContent = `Frame ${prog.current_frame || 0} / ${prog.total_frames}`;
        } else if (prog.speed_text) {
            framesTxt.textContent = prog.speed_text;
        } else {
            framesTxt.textContent = "Procesando...";
        }
    }

    if (etaTxt) {
        if (prog.eta_text && prog.eta_text !== '0s' && prog.eta_text !== 'Iniciando...') {
            etaTxt.textContent = `⏱️ Restante: ~${prog.eta_text}`;
        } else if (percent >= 100) {
            etaTxt.textContent = `✔️ Completado`;
        } else {
            etaTxt.textContent = `Calculando tiempo...`;
        }
    }
}

function startProgressPolling() {
    stopProgressPolling();
    Studio.progressPollInterval = setInterval(async () => {
        if (!Studio.isGenerating) {
            stopProgressPolling();
            return;
        }
        try {
            const resp = await fetch('/api/progress');
            if (resp.ok) {
                const data = await resp.json();
                handleRenderProgress(data);
            }
        } catch (e) {
            // Silencioso en polling
        }
    }, 400);
}

function stopProgressPolling() {
    if (Studio.progressPollInterval) {
        clearInterval(Studio.progressPollInterval);
        Studio.progressPollInterval = null;
    }
}

/* ==========================================================================
   STEPPER NAVIGATION
   ========================================================================== */
function goToStep(stepNum) {
    if (stepNum === 2 && !Studio.uploadedFacePath) {
        showToast("Sube una credencial o foto primero.", "error");
        return;
    }
    if (stepNum === 3 && !Studio.uploadedFacePath) {
        showToast("Carga una identidad antes de continuar.", "error");
        return;
    }

    Studio.currentStep = stepNum;

    // Actualizar paneles
    for (let i = 1; i <= 3; i++) {
        const seg = document.getElementById(`seg-${i}`);
        const panel = document.getElementById(`step-panel-${i}`);
        
        if (panel) {
            if (i === stepNum) {
                panel.classList.add('active');
            } else {
                panel.classList.remove('active');
            }
        }

        if (seg) {
            if (i === stepNum) {
                seg.className = 'stepper-seg active';
            } else if (i < stepNum) {
                seg.className = 'stepper-seg completed';
            } else {
                seg.className = 'stepper-seg';
            }
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
    stopProgressPolling();

    const resultBox = document.getElementById('identity-result-box');
    const idleUI = document.getElementById('dropzone-idle-ui');
    const scanningUI = document.getElementById('dropzone-scanning-ui');

    if (resultBox) resultBox.style.display = 'none';
    if (idleUI) idleUI.style.display = 'block';
    if (scanningUI) scanningUI.style.display = 'none';

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

    if (!dropzone || !fileInput) return;

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
        const res = await safeFetchJson('/api/extract-id-face', {
            method: 'POST',
            body: formData
        });

        Studio.uploadedFacePath = res.enhanced_file_path || res.crop_file_path;
        Studio.uploadedCropUrl = res.crop_url;
        Studio.uploadedEnhancedUrl = res.enhanced_url;
        Studio.activeIdentityId = res.identity_id || null;
        Studio.imageType = res.metadata?.image_type || 'ID_CARD';
        const detectedGender = res.metadata?.gender || 'Hombre';
        const detectedAge = res.metadata?.age || 35;
        const recommendedPreset = res.metadata?.recommended_preset || (detectedGender === 'Hombre' ? 'male_hd_clear.mp4' : 'female_clean_kyc_base.mp4');

        // Mostrar vistas previas
        document.getElementById('img-crop-preview').src = res.crop_url;
        document.getElementById('img-enhanced-preview').src = res.enhanced_url;

        // Badge de tipo
        const typeText = document.getElementById('identity-type-text');
        const typeIcon = document.getElementById('identity-icon');
        if (Studio.imageType === 'ID_CARD') {
            if (typeIcon) typeIcon.textContent = '🪪';
            if (typeText) typeText.textContent = res.metadata?.type_label || 'INE Detectada';
        } else {
            if (typeIcon) typeIcon.textContent = '👤';
            if (typeText) typeText.textContent = res.metadata?.type_label || 'Selfie Detectada';
        }

        // Badge de Género
        const genderText = document.getElementById('gender-text');
        if (genderText) {
            genderText.textContent = `${detectedGender} (~${detectedAge}a)`;
        }

        // Auto-seleccionar Preset
        Studio.targetPreset = recommendedPreset;
        renderPresetsCatalog();

        // Badge ArcFace
        const arcfaceScore = res.metadata?.arcface_score || 96.2;
        const arcfaceText = document.getElementById('arcface-score-text');
        if (arcfaceText) {
            arcfaceText.textContent = `${arcfaceScore}% ArcFace`;
        }

        scanningUI.style.display = 'none';
        resultBox.style.display = 'block';

        showToast(`Identidad procesada: ${detectedGender} · Base: ${recommendedPreset}`, "success");
    } catch (err) {
        console.error(err);
        scanningUI.style.display = 'none';
        idleUI.style.display = 'block';
        showToast(err.message || "Error al procesar la imagen.", "error");
    }
}

/* ==========================================================================
   CATÁLOGO DE PRESETS & DINÁMICA FACIAL (TARJETAS VISUALES CON MINI-THUMBNAILS)
   ========================================================================== */
Studio.presetFilter = 'all';

async function loadPresetsCatalog() {
    try {
        const data = await safeFetchJson('/api/presets');
        Studio.availablePresets = data.presets || [];
        renderPresetsCatalog();
    } catch (e) {
        console.error("Error cargando presets:", e);
    }
}

function filterPresets(filterGender, event) {
    if (event) event.stopPropagation();
    Studio.presetFilter = filterGender;

    const pills = document.querySelectorAll('.pill-filter');
    pills.forEach(p => {
        if ((filterGender === 'all' && p.textContent.trim() === 'Todos') ||
            p.textContent.trim() === filterGender) {
            p.classList.add('active');
        } else {
            p.classList.remove('active');
        }
    });

    renderPresetsCatalog();
}

function renderPresetsCatalog() {
    const container = document.getElementById('preset-buttons-row');
    if (!container) return;

    container.innerHTML = '';
    
    const filtered = Studio.availablePresets.filter(p => {
        if (Studio.presetFilter === 'all') return true;
        return p.gender === Studio.presetFilter;
    });

    filtered.forEach(p => {
        const card = document.createElement('div');
        const isSelected = (Studio.targetPreset === p.id && !Studio.customVideoPath);
        card.className = `preset-visual-card ${isSelected ? 'active' : ''}`;
        card.onclick = (e) => setSwapPreset(p.id, e);
        
        card.innerHTML = `
            <div class="preset-thumb-box">
                <img src="${p.thumbnail_url || '/data/presets/thumbnails/' + p.id.replace('.mp4', '.jpg')}" alt="${p.name}" onerror="this.src='/static/thumb_fallback.jpg'" loading="lazy">
                <span class="preset-badge-tag">${p.badge || 'HD'}</span>
                <div class="preset-card-radio"></div>
            </div>
            <div class="preset-card-body">
                <div class="preset-card-title">${p.name}</div>
                <div class="preset-card-meta">
                    <span class="meta-item-gender">${p.gender}</span>
                    <span class="meta-dot">·</span>
                    <span class="meta-item-res">${p.resolution}</span>
                </div>
            </div>
        `;
        container.appendChild(card);
    });

    // Tarjeta para subir video personalizado
    const customCard = document.createElement('div');
    const isCustomActive = !!Studio.customVideoPath;
    customCard.className = `preset-visual-card custom-card ${isCustomActive ? 'active' : ''}`;
    customCard.onclick = (e) => triggerFileInput('custom-video-input', e);
    
    customCard.innerHTML = `
        <div class="preset-thumb-box custom-thumb">
            <div class="custom-icon-wrap">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            </div>
            <span class="preset-badge-tag custom">PROPIO</span>
            <div class="preset-card-radio"></div>
        </div>
        <div class="preset-card-body">
            <div class="preset-card-title">${Studio.customVideoPath ? 'Video Propio Cargado' : 'Subir Video Propio'}</div>
            <div class="preset-card-meta">
                <span class="meta-item-res">${Studio.customVideoPath ? 'Personalizado MP4' : 'Toca para examinar'}</span>
            </div>
        </div>
    `;
    container.appendChild(customCard);
}

function selectMotionMode(mode) {
    Studio.generationMode = mode;

    const cardSynth = document.getElementById('card-mode-synthetic');
    const cardSwap = document.getElementById('card-mode-swap');
    const subOptions = document.getElementById('swap-sub-options');

    if (mode === 'synthetic') {
        if (cardSynth) cardSynth.classList.add('active');
        if (cardSwap) cardSwap.classList.remove('active');
        if (subOptions) subOptions.style.display = 'none';
    } else {
        if (cardSwap) cardSwap.classList.add('active');
        if (cardSynth) cardSynth.classList.remove('active');
        if (subOptions) subOptions.style.display = 'block';
    }
}

function setSwapPreset(presetName, event) {
    if (event) event.stopPropagation();
    Studio.targetPreset = presetName;
    Studio.customVideoPath = null;
    renderPresetsCatalog();
}

async function handleCustomVideoUpload(event) {
    if (!event.target.files || event.target.files.length === 0) return;
    const file = event.target.files[0];

    const formData = new FormData();
    formData.append('file', file);

    try {
        showToast("Subiendo video conductor...", "success");
        const res = await safeFetchJson('/api/upload-target', { method: 'POST', body: formData });
        Studio.customVideoPath = res.file_path;
        showToast(`Video cargado: ${res.filename}`, "success");
        renderPresetsCatalog();
    } catch (err) {
        showToast(err.message || "Error al subir video", "error");
    }
}

/* ==========================================================================
   PASO 3: GENERACIÓN Y SALIDA CON TELEMETRÍA EN VIVO (3 ACCIONES)
   ========================================================================== */
Studio.currentActionMode = 'generate_only';

async function startGenerationAndGoStep3(actionMode = 'generate_only') {
    Studio.currentActionMode = actionMode;
    goToStep(3);

    const progressLayer = document.getElementById('monitor-progress-layer');
    const hudBadge = document.getElementById('hud-status-badge');
    const downloadBtn = document.getElementById('btn-download-video');
    const bmxCard = document.getElementById('bmx-selfie-modal-card');

    if (bmxCard) bmxCard.style.display = 'none';

    progressLayer.style.display = 'flex';
    hudBadge.textContent = 'GENERANDO BUFFER';
    Studio.isGenerating = true;

    // Iniciar polling de respaldo por si el WS se atrasa
    startProgressPolling();

    const modeLabels = {
        'generate_only': 'Iniciando generación de video en DirectML...',
        'create_bmx': '⚡ Iniciando GPU + Creación BetMexico en 2do plano...',
        'verify_bmx': '🪪 Preparando flujo de verificación BetMexico...'
    };

    handleRenderProgress({
        percent: 4,
        status_text: modeLabels[actionMode] || "Iniciando procesamiento DirectML...",
        current_frame: 0,
        total_frames: 0,
        eta_text: "Iniciando..."
    });

    try {
        const formData = new FormData();
        formData.append('duration', 90);
        formData.append('width', 1280);
        formData.append('height', 720);
        formData.append('fps', 30);
        formData.append('framing_mode', 'fill_crop');
        formData.append('action_mode', actionMode);

        let endpoint = '/api/generate-liveness';
        if (Studio.generationMode === 'synthetic') {
            formData.append('face_path', Studio.uploadedFacePath);
        } else {
            endpoint = '/api/process-swap';
            formData.append('source_face_path', Studio.uploadedFacePath);
            formData.append('target_video_path', Studio.customVideoPath || Studio.targetPreset);
        }

        const res = await safeFetchJson(endpoint, { method: 'POST', body: formData });

        Studio.activeY4mPath = res.y4m_path;
        Studio.activeMp4PreviewUrl = res.preview_url;

        // Cargar video en monitor
        const player = document.getElementById('live-monitor-player');
        const source = document.getElementById('live-monitor-source');
        source.src = res.preview_url;
        player.load();
        player.play();

        // Configurar botón de descarga
        if (downloadBtn) downloadBtn.href = res.preview_url;

        handleRenderProgress({
            percent: 100,
            status_text: "¡Cámara lista en buffer!",
            eta_text: "0s"
        });

        setTimeout(() => {
            progressLayer.style.display = 'none';
            hudBadge.textContent = 'CÁMARA ACTIVA';
            
            if (actionMode === 'create_bmx' && bmxCard) {
                bmxCard.style.display = 'block';
                showToast("👑 Cuenta BMX lista. Elige modo de verificación abajo.", "success");
            } else if (actionMode === 'verify_bmx') {
                showToast("🪪 Buffer listo. Abriendo navegador para verificación...", "success");
                launchBrowserFlow();
            } else {
                showToast("✨ Flujo de video generado con éxito.", "success");
            }
        }, 500);

    } catch (err) {
        console.error(err);
        progressLayer.style.display = 'none';
        hudBadge.textContent = 'ERROR';
        showToast(err.message || "Error al procesar el flujo.", "error");
    } finally {
        Studio.isGenerating = false;
        stopProgressPolling();
    }
}

async function handleBMXChoice(mode) {
    const bmxCard = document.getElementById('bmx-selfie-modal-card');
    if (bmxCard) bmxCard.style.display = 'none';

    if (mode === 'manual') {
        showToast("🖱️ Abriendo navegador en pantalla física para control manual...", "info");
        await launchBrowserFlow();
    } else {
        showToast("⚡ Disparando verificación automática con subida de INE...", "info");
        try {
            if (Studio.activeIdentityId) {
                const res = await safeFetchJson(`/api/identities/${Studio.activeIdentityId}/inject-documents-cdp`, {
                    method: 'POST'
                });
                showToast("🎉 Documentos inyectados automáticamente con éxito.", "success");
            } else {
                await launchBrowserFlow();
            }
        } catch (e) {
            // Fallback al navegador si no hay CDP directo listo
            await launchBrowserFlow();
        }
    }
}

/* ==========================================================================
   CANALES DE SALIDA
   ========================================================================== */
async function launchBrowserFlow() {
    if (!Studio.activeY4mPath) {
        showToast("Genera el video primero antes de abrir el navegador.", "error");
        return;
    }

    const targetUrlInput = document.getElementById('target-url-input');
    const targetUrl = targetUrlInput ? targetUrlInput.value.trim() : 'https://webcamtests.com';
    const personaSelect = document.getElementById('hardware-persona-select');
    const hardwarePersona = personaSelect ? personaSelect.value : 'logitech_c920';

    const btn = document.getElementById('btn-launch-browser-action');
    btn.disabled = true;
    btn.innerHTML = '<span>Lanzando Navegador...</span>';

    try {
        const formData = new FormData();
        formData.append('y4m_path', Studio.activeY4mPath);
        formData.append('target_url', targetUrl || 'https://webcamtests.com');
        formData.append('hardware_persona', hardwarePersona);
        if (Studio.activeIdentityId) {
            formData.append('identity_id', Studio.activeIdentityId);
        }

        const res = await safeFetchJson('/api/launch-browser', { method: 'POST', body: formData });
        showToast(`🚀 Navegador lanzado con cámara [${hardwarePersona}].`, "success");
    } catch (err) {
        showToast(err.message || "Fallo al lanzar el navegador", "error");
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span>🚀 Abrir Navegador Armado</span>';
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

        const res = await safeFetchJson(endpoint, { method: 'POST', body: shouldStart ? formData : undefined });

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
    } catch (e) {
        // Silencioso
    }
}

function initPanicReset() {
    const btn = document.getElementById('btn-panic-reset');
    if (!btn) return;

    btn.addEventListener('click', async () => {
        try {
            btn.style.opacity = '0.5';
            await fetch('/api/panic-reset', { method: 'POST' });
            showToast("🚨 Memoria y procesos liberados.", "success");
            resetToNewSession();
        } catch (e) {
            showToast("Error en reinicio de emergencia", "error");
        } finally {
            btn.style.opacity = '1';
        }
    });
}

/* ==========================================================================
   TOAST NOTIFICATIONS
   ========================================================================== */
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-6px) scale(0.96)';
        toast.style.transition = 'all 0.2s ease';
        setTimeout(() => toast.remove(), 200);
    }, 2000);
}
