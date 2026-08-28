/**
 * kyc_sniffer.js
 * 
 * In-browser diagnostic and telemetry sniffer for biometric & KYC verification flows.
 * Detects active KYC SDKs (Incode, Veriff, Truora, Metamap, Jumio, Sumsub, Onfido),
 * intercepts getUserMedia constraints, and traces canvas biometric snapshot captures.
 */

(function () {
    'use strict';

    console.log("%c[KYC Sniffer Active]%c Initializing biometric & media pipeline auditor...", "background: #00ff88; color: #000; font-weight: bold; padding: 2px 6px; border-radius: 3px;", "");

    function emitEvent(eventType, detail) {
        const payload = {
            timestamp: new Date().toISOString(),
            type: eventType,
            data: detail,
            url: window.location.href
        };
        
        console.info("[KYC_SNIFFER_EVENT]", JSON.stringify(payload));

        try {
            window.dispatchEvent(new CustomEvent('KYC_Telemetry', { detail: payload }));
        } catch (e) { }

        if (window.__KYC_STUDIO_WS__ && window.__KYC_STUDIO_WS__.readyState === 1) {
            try {
                window.__KYC_STUDIO_WS__.send(JSON.stringify(payload));
            } catch (e) { }
        }
    }

    // 1. Interceptar getUserMedia
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        const origGUM = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
        navigator.mediaDevices.getUserMedia = async function (constraints) {
            emitEvent("GET_USER_MEDIA_REQUESTED", {
                constraints: constraints
            });
            try {
                const stream = await origGUM(constraints);
                const tracks = stream.getVideoTracks();
                const trackInfo = tracks.map(t => ({
                    id: t.id,
                    label: t.label,
                    settings: t.getSettings ? t.getSettings() : {},
                    capabilities: t.getCapabilities ? t.getCapabilities() : {}
                }));
                emitEvent("GET_USER_MEDIA_GRANTED", {
                    tracks: trackInfo
                });
                return stream;
            } catch (err) {
                emitEvent("GET_USER_MEDIA_ERROR", {
                    name: err.name,
                    message: err.message
                });
                throw err;
            }
        };
    }

    // 2. Interceptar capturas de instantáneas biométricas sobre Canvas
    if (HTMLCanvasElement && HTMLCanvasElement.prototype) {
        const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function (...args) {
            emitEvent("CANVAS_SNAPSHOT_CAPTURED", {
                method: "toDataURL",
                mimeType: args[0] || "image/png",
                canvasWidth: this.width,
                canvasHeight: this.height
            });
            return origToDataURL.apply(this, args);
        };

        const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
        CanvasRenderingContext2D.prototype.getImageData = function (...args) {
            if (!this._lastKycLogged || Date.now() - this._lastKycLogged > 1500) {
                this._lastKycLogged = Date.now();
                emitEvent("CANVAS_FRAME_INSPECTED", {
                    method: "getImageData",
                    rect: { sx: args[0], sy: args[1], sw: args[2], sh: args[3] },
                    canvasWidth: this.canvas.width,
                    canvasHeight: this.canvas.height
                });
            }
            return origGetImageData.apply(this, args);
        };
    }

    // 3. Scanner continuo de firmas de SDKs KYC
    const KYC_SIGNATURES = [
        { name: "Incode", detect: () => !!(window.Incode || window.incodeSDK || document.querySelector('[class*="incode"], [id*="incode"]')) },
        { name: "Veriff", detect: () => !!(window.veriff || window.Veriff || document.querySelector('[id*="veriff"], [class*="veriff"]')) },
        { name: "Truora", detect: () => !!(window.Truora || document.querySelector('[class*="truora"], script[src*="truora"]')) },
        { name: "MetaMap / Mati", detect: () => !!(window.Mati || window.MetaMap || document.querySelector('mati-button, metamap-button, [class*="metamap"]')) },
        { name: "Jumio", detect: () => !!(window.Jumio || document.querySelector('[class*="jumio"], [id*="jumio"]')) },
        { name: "Sumsub", detect: () => !!(window.snsWebSdk || window.idCheck || document.querySelector('[id*="sumsub"], [id*="idensic"]')) },
        { name: "Onfido", detect: () => !!(window.Onfido || document.querySelector('[class*="onfido"]')) },
        { name: "Microblink", detect: () => !!(window.BlinkID || window.Microblink) }
    ];

    const detectedSDKs = new Set();

    function scanForSDKs() {
        for (const sdk of KYC_SIGNATURES) {
            if (!detectedSDKs.has(sdk.name) && sdk.detect()) {
                detectedSDKs.add(sdk.name);
                emitEvent("KYC_SDK_DETECTED", {
                    sdkName: sdk.name,
                    detectedAt: new Date().toISOString()
                });
                console.log(`%c[KYC Sniffer Alert]%c Detected ${sdk.name} SDK operating on page!`, "background: #ff0055; color: #fff; font-weight: bold; padding: 2px 6px; border-radius: 3px;", "");
            }
        }
    }

    // 4. Scanner de inputs de archivo y solicitudes documentales (Frente, Reverso, Domicilio)
    let lastFileInputCount = 0;
    function scanForFileInputs() {
        const fileInputs = document.querySelectorAll('input[type="file"]');
        if (fileInputs.length > 0 && fileInputs.length !== lastFileInputCount) {
            lastFileInputCount = fileInputs.length;
            const inputDetails = Array.from(fileInputs).map(inp => ({
                id: inp.id || "",
                name: inp.name || "",
                accept: inp.accept || "",
                ariaLabel: inp.getAttribute('aria-label') || ""
            }));
            emitEvent("KYC_FILE_INPUT_DETECTED", {
                count: fileInputs.length,
                inputs: inputDetails,
                detectedAt: new Date().toISOString()
            });
            console.log(`%c[KYC Sniffer Alert]%c Detected ${fileInputs.length} file input elements for document upload!`, "background: #00ccff; color: #000; font-weight: bold; padding: 2px 6px; border-radius: 3px;", "");
        }
    }

    function runAllAudits() {
        scanForSDKs();
        scanForFileInputs();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', runAllAudits);
    } else {
        runAllAudits();
    }

    const observer = new MutationObserver(() => {
        runAllAudits();
    });

    try {
        observer.observe(document.documentElement, {
            childList: true,
            subtree: true
        });
    } catch (e) { }

    setInterval(runAllAudits, 2000);
})();
