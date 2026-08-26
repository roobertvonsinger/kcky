/**
 * webrtc_cam_spoof.js
 * 
 * Script de inyección sigilosa (stealth) para WebRTC / MediaDevices en Chromium/Playwright.
 * Enmascara la cámara virtual/fake inyectada por Chromium y la reporta como un dispositivo
 * de hardware físico legítimo para evadir detección de SDKs de onboarding / KYC (Incode, Veriff, etc.).
 */

(function () {
    'use strict';

    // Configuración de hardware emulado (sobrescrito dinámicamente por browser.py si se cambia persona)
    const FAKE_CAM_CONFIG = {
        label: "Integrated Camera (04f2:b614)",
        deviceId: "d7a4b89f3c2e1a5d6b8c9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b",
        groupId: "e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2",
        micLabel: "Microphone (Realtek(R) Audio)",
        micDeviceId: "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2",
        micGroupId: "f2e1d0c9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1"
    };

    if (!navigator.mediaDevices) {
        return;
    }

    const origEnumerateDevices = navigator.mediaDevices.enumerateDevices.bind(navigator.mediaDevices);
    const origGUM = navigator.mediaDevices.getUserMedia ? navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices) : null;

    // 0. Interceptar getUserMedia para relajar restricciones rígidas ('exact') y desviar deviceId hacia la cámara activa
    if (origGUM) {
        navigator.mediaDevices.getUserMedia = async function (constraints) {
            let adaptedConstraints = constraints;
            try {
                if (constraints && typeof constraints === 'object') {
                    adaptedConstraints = JSON.parse(JSON.stringify(constraints));
                    if (adaptedConstraints.video) {
                        if (typeof adaptedConstraints.video === 'object') {
                            // Relajar restricciones exactas de resolución y fps hacia 'ideal'
                            if (adaptedConstraints.video.width && adaptedConstraints.video.width.exact) {
                                adaptedConstraints.video.width.ideal = adaptedConstraints.video.width.exact;
                                delete adaptedConstraints.video.width.exact;
                            }
                            if (adaptedConstraints.video.height && adaptedConstraints.video.height.exact) {
                                adaptedConstraints.video.height.ideal = adaptedConstraints.video.height.exact;
                                delete adaptedConstraints.video.height.exact;
                            }
                            if (adaptedConstraints.video.frameRate && adaptedConstraints.video.frameRate.exact) {
                                adaptedConstraints.video.frameRate.ideal = adaptedConstraints.video.frameRate.exact;
                                delete adaptedConstraints.video.frameRate.exact;
                            }
                            // Eliminar deviceId o groupId restrictivos para que Chromium capture el stream falso sin error
                            delete adaptedConstraints.video.deviceId;
                            delete adaptedConstraints.video.groupId;
                        }
                    }
                    if (adaptedConstraints.audio && typeof adaptedConstraints.audio === 'object') {
                        delete adaptedConstraints.audio.deviceId;
                        delete adaptedConstraints.audio.groupId;
                    }
                }
            } catch (e) { }
            return origGUM(adaptedConstraints);
        };
    }

    // 1. Interceptar enumerateDevices
    navigator.mediaDevices.enumerateDevices = async function () {
        const devices = await origEnumerateDevices();
        return devices.map(d => {
            if (d.kind === 'videoinput') {
                return {
                    deviceId: d.deviceId || FAKE_CAM_CONFIG.deviceId,
                    groupId: d.groupId || FAKE_CAM_CONFIG.groupId,
                    kind: 'videoinput',
                    label: FAKE_CAM_CONFIG.label,
                    toJSON: function () {
                        return {
                            deviceId: this.deviceId,
                            groupId: this.groupId,
                            kind: this.kind,
                            label: this.label
                        };
                    }
                };
            }
            if (d.kind === 'audioinput') {
                return {
                    deviceId: d.deviceId || FAKE_CAM_CONFIG.micDeviceId,
                    groupId: d.groupId || FAKE_CAM_CONFIG.micGroupId,
                    kind: 'audioinput',
                    label: FAKE_CAM_CONFIG.micLabel,
                    toJSON: function () {
                        return {
                            deviceId: this.deviceId,
                            groupId: this.groupId,
                            kind: this.kind,
                            label: this.label
                        };
                    }
                };
            }
            return d;
        });
    };

    // 2. Interceptar MediaStreamTrack.prototype.getSettings y getCapabilities
    if (window.MediaStreamTrack) {
        const origGetSettings = MediaStreamTrack.prototype.getSettings;
        MediaStreamTrack.prototype.getSettings = function () {
            const settings = origGetSettings.apply(this);
            if (this.kind === 'video') {
                settings.deviceId = FAKE_CAM_CONFIG.deviceId;
                settings.groupId = FAKE_CAM_CONFIG.groupId;
                settings.facingMode = "user";
                const w = settings.width || 1280;
                const h = settings.height || 720;
                settings.width = w;
                settings.height = h;
                settings.aspectRatio = w / h;
                if (!settings.frameRate) settings.frameRate = 30;
            }
            return settings;
        };

        if (MediaStreamTrack.prototype.getCapabilities) {
            const origGetCapabilities = MediaStreamTrack.prototype.getCapabilities;
            MediaStreamTrack.prototype.getCapabilities = function () {
                const caps = origGetCapabilities ? origGetCapabilities.apply(this) : {};
                if (this.kind === 'video') {
                    const settings = this.getSettings ? this.getSettings() : {};
                    const w = settings.width || 1280;
                    const h = settings.height || 720;
                    caps.deviceId = FAKE_CAM_CONFIG.deviceId;
                    caps.groupId = FAKE_CAM_CONFIG.groupId;
                    caps.facingMode = ["user"];
                    caps.frameRate = { max: 30, min: 1 };
                    caps.height = { max: h, min: 1 };
                    caps.width = { max: w, min: 1 };
                    caps.aspectRatio = { max: w / h, min: 0.001 };
                    caps.resizeMode = ["none", "crop-and-scale"];
                }
                return caps;
            };
        }

        // Interceptar la propiedad 'label' del track de video
        const labelDescriptor = Object.getOwnPropertyDescriptor(MediaStreamTrack.prototype, 'label');
        if (labelDescriptor && labelDescriptor.get) {
            Object.defineProperty(MediaStreamTrack.prototype, 'label', {
                get: function () {
                    if (this.kind === 'video') {
                        return FAKE_CAM_CONFIG.label;
                    }
                    if (this.kind === 'audio') {
                        return FAKE_CAM_CONFIG.micLabel;
                    }
                    return labelDescriptor.get.apply(this);
                },
                configurable: true,
                enumerable: true
            });
        }
    }

    // 3. Silenciar auto-permisos para evitar discrepancias
    if (navigator.permissions && navigator.permissions.query) {
        const origQuery = navigator.permissions.query.bind(navigator.permissions);
        navigator.permissions.query = function (param) {
            if (param && (param.name === 'camera' || param.name === 'microphone')) {
                return Promise.resolve({
                    state: 'granted',
                    name: param.name,
                    onchange: null
                });
            }
            return origQuery(param);
        };
    }
})();
