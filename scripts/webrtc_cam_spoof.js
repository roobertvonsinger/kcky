/**
 * webrtc_cam_spoof.js — Enmascaramiento Stealth de Cámara Virtual de Grado Militar (KCKY Studio v3.5)
 *
 * Enmascara completamente la cámara fake de Chromium (--use-fake-device-for-media-stream)
 * como un dispositivo de hardware físico legítimo (Logitech HD Pro Webcam C920).
 *
 * Características de Robustecimiento:
 * 1. Sanitización de `MediaDeviceInfo` (labels, deviceId, groupId coherente USB).
 * 2. Hook en `MediaStreamTrack.prototype.label`, `getSettings`, `getCapabilities`, `clone`.
 * 3. Hook en `MediaStream.prototype.clone`, `addTrack`.
 * 4. Hook en `RTCPeerConnection.prototype` (`addTrack`, `getSenders`, `getStats`).
 * 5. Hook en `MediaDevices.prototype.getSupportedConstraints`.
 * 6. Propagación automática en Iframes dinámicos y ventanas popup.
 * 7. Soporte para APIs legacy (`navigator.getUserMedia`, `webkitGetUserMedia`).
 */

(function () {
    'use strict';

    // ====================================================================
    // 0. Configuración y Utilidades
    // ====================================================================
    const P = window.__hw_persona || {};
    const CAM_LABEL = P.camLabel || P.label || 'Logitech HD Pro Webcam C920';
    const MIC_LABEL = P.micLabel || P.mic_label || 'Microphone (Logitech HD Pro Webcam C920)';

    // Protección de toString
    const protect = window.__stealth_protectFn || (function () {
        const cache = new Map();
        const origToString = Function.prototype.toString;
        Function.prototype.toString = function () {
            return cache.has(this) ? cache.get(this) : origToString.call(this);
        };
        return function (fn, name) {
            cache.set(fn, `function ${name}() { [native code] }`);
            return fn;
        };
    })();

    // Hash simple determinístico por origin
    function simpleHash(str) {
        let h = 0x811c9dc5;
        for (let i = 0; i < str.length; i++) {
            h ^= str.charCodeAt(i);
            h = Math.imul(h, 0x01000193);
        }
        return (h >>> 0).toString(16).padStart(8, '0');
    }

    const _sessionSalt = Array.from({ length: 16 }, () =>
        Math.floor(Math.random() * 16).toString(16)
    ).join('');

    function generateDeviceId(type) {
        const base = (location.origin || 'null') + ':' + type + ':' + _sessionSalt;
        let result = '';
        for (let i = 0; i < 8; i++) {
            result += simpleHash(base + ':' + i);
        }
        return result;
    }

    const VIDEO_DEVICE_ID = generateDeviceId('videoinput');
    const VIDEO_GROUP_ID = generateDeviceId('videogroup');
    const AUDIO_DEVICE_ID = generateDeviceId('audioinput');
    const AUDIO_GROUP_ID = VIDEO_GROUP_ID; // Mismo grupo USB
    const AUDIO_OUTPUT_ID = generateDeviceId('audiooutput');
    const AUDIO_OUTPUT_GROUP = generateDeviceId('audiooutgroup');

    // ====================================================================
    // 1. MediaStreamTrack Prototype & Clones
    // ====================================================================
    if (window.MediaStreamTrack) {
        try {
            Object.defineProperty(MediaStreamTrack.prototype, 'label', {
                get: protect(function () {
                    if (this.kind === 'video') return CAM_LABEL;
                    if (this.kind === 'audio') return MIC_LABEL;
                    return 'Default Audio Device';
                }, 'get label'),
                configurable: true,
                enumerable: true
            });
        } catch (e) { }

        if (MediaStreamTrack.prototype.getSettings) {
            const _origGetSettings = MediaStreamTrack.prototype.getSettings;
            MediaStreamTrack.prototype.getSettings = protect(function () {
                const settings = _origGetSettings.call(this);
                if (this.kind === 'video') {
                    settings.deviceId = VIDEO_DEVICE_ID;
                    settings.groupId = VIDEO_GROUP_ID;
                    settings.facingMode = 'user';
                    const w = settings.width || 1280;
                    const h = settings.height || 720;
                    settings.width = w;
                    settings.height = h;
                    settings.aspectRatio = w / h;
                    const baseRate = settings.frameRate || 30;
                    settings.frameRate = parseFloat((baseRate + (Math.random() * 0.06 - 0.03)).toFixed(6));
                }
                if (this.kind === 'audio') {
                    settings.deviceId = AUDIO_DEVICE_ID;
                    settings.groupId = AUDIO_GROUP_ID;
                }
                return settings;
            }, 'getSettings');
        }

        if (MediaStreamTrack.prototype.getCapabilities) {
            const _origGetCaps = MediaStreamTrack.prototype.getCapabilities;
            MediaStreamTrack.prototype.getCapabilities = protect(function () {
                const caps = _origGetCaps ? _origGetCaps.call(this) : {};
                if (this.kind === 'video') {
                    caps.deviceId = VIDEO_DEVICE_ID;
                    caps.groupId = VIDEO_GROUP_ID;
                    caps.facingMode = ['user'];
                    caps.width = { min: 1, max: 1920 };
                    caps.height = { min: 1, max: 1080 };
                    caps.frameRate = { min: 1, max: 30 };
                    caps.aspectRatio = { min: 0.000925925, max: 1920.0 };
                    caps.resizeMode = ['none', 'crop-and-scale'];
                }
                return caps;
            }, 'getCapabilities');
        }

        // Proteger .clone() de tracks
        if (MediaStreamTrack.prototype.clone) {
            const _origTrackClone = MediaStreamTrack.prototype.clone;
            MediaStreamTrack.prototype.clone = protect(function () {
                const cloned = _origTrackClone.call(this);
                try {
                    Object.defineProperty(cloned, 'label', {
                        get: protect(function () {
                            return this.kind === 'video' ? CAM_LABEL : MIC_LABEL;
                        }, 'get label'),
                        configurable: true,
                        enumerable: true
                    });
                } catch (e) { }
                return cloned;
            }, 'clone');
        }
    }

    // ====================================================================
    // 2. MediaStream Prototype & Clones
    // ====================================================================
    if (window.MediaStream) {
        if (MediaStream.prototype.clone) {
            const _origStreamClone = MediaStream.prototype.clone;
            MediaStream.prototype.clone = protect(function () {
                const cloned = _origStreamClone.call(this);
                try {
                    cloned.getVideoTracks().forEach(t => {
                        Object.defineProperty(t, 'label', {
                            get: protect(function () { return CAM_LABEL; }, 'get label'),
                            configurable: true, enumerable: true
                        });
                    });
                } catch (e) { }
                return cloned;
            }, 'clone');
        }
    }

    if (!navigator.mediaDevices) return;

    // ====================================================================
    // 3. getSupportedConstraints — Lista completa de hardware Chromium
    // ====================================================================
    if (MediaDevices.prototype.getSupportedConstraints) {
        MediaDevices.prototype.getSupportedConstraints = protect(function () {
            return {
                aspectRatio: true,
                autoGainControl: true,
                brightness: true,
                channelCount: true,
                colorTemperature: true,
                contrast: true,
                deviceId: true,
                echoCancellation: true,
                exposureCompensation: true,
                exposureMode: true,
                facingMode: true,
                focusDistance: true,
                focusMode: true,
                frameRate: true,
                groupId: true,
                height: true,
                iso: true,
                latency: true,
                noiseSuppression: true,
                pan: true,
                pointsOfInterest: true,
                resizeMode: true,
                sampleRate: true,
                sampleSize: true,
                saturation: true,
                sharpness: true,
                tilt: true,
                torch: true,
                whiteBalanceMode: true,
                width: true,
                zoom: true
            };
        }, 'getSupportedConstraints');
    }

    // ====================================================================
    // 4. enumerateDevices — Creación de MediaDeviceInfo Legítimos
    // ====================================================================
    function createMediaDeviceInfo(deviceId, groupId, kind, label) {
        const device = Object.create(MediaDeviceInfo.prototype);
        Object.defineProperties(device, {
            deviceId: { value: deviceId, enumerable: true, configurable: true },
            groupId: { value: groupId, enumerable: true, configurable: true },
            kind: { value: kind, enumerable: true, configurable: true },
            label: { value: label, enumerable: true, configurable: true },
        });
        device.toJSON = protect(function () {
            return {
                deviceId: this.deviceId,
                groupId: this.groupId,
                kind: this.kind,
                label: this.label
            };
        }, 'toJSON');
        return device;
    }

    const _origEnumerate = MediaDevices.prototype.enumerateDevices;

    MediaDevices.prototype.enumerateDevices = protect(async function () {
        const realDevices = await _origEnumerate.call(this);
        const spoofed = [];
        let hasVideo = false;
        let hasAudioIn = false;
        let hasAudioOut = false;

        for (const d of realDevices) {
            if (d.kind === 'videoinput' && !hasVideo) {
                spoofed.push(createMediaDeviceInfo(VIDEO_DEVICE_ID, VIDEO_GROUP_ID, 'videoinput', CAM_LABEL));
                hasVideo = true;
            } else if (d.kind === 'audioinput' && !hasAudioIn) {
                spoofed.push(createMediaDeviceInfo(AUDIO_DEVICE_ID, AUDIO_GROUP_ID, 'audioinput', MIC_LABEL));
                hasAudioIn = true;
            } else if (d.kind === 'audiooutput' && !hasAudioOut) {
                spoofed.push(createMediaDeviceInfo(AUDIO_OUTPUT_ID, AUDIO_OUTPUT_GROUP, 'audiooutput', d.label || 'Speakers (Realtek(R) Audio)'));
                hasAudioOut = true;
            }
        }

        if (!hasVideo) {
            spoofed.push(createMediaDeviceInfo(VIDEO_DEVICE_ID, VIDEO_GROUP_ID, 'videoinput', CAM_LABEL));
        }
        if (!hasAudioIn) {
            spoofed.push(createMediaDeviceInfo(AUDIO_DEVICE_ID, AUDIO_GROUP_ID, 'audioinput', MIC_LABEL));
        }

        return spoofed;
    }, 'enumerateDevices');

    // ====================================================================
    // 5. getUserMedia — Intercepción, Relajación y Parcheo
    // ====================================================================
    const _origGUM = MediaDevices.prototype.getUserMedia;

    MediaDevices.prototype.getUserMedia = protect(async function (constraints) {
        let adapted = constraints;
        try {
            if (constraints && typeof constraints === 'object') {
                adapted = JSON.parse(JSON.stringify(constraints));
                if (adapted.video && typeof adapted.video === 'object') {
                    ['width', 'height', 'frameRate'].forEach(prop => {
                        if (adapted.video[prop] && adapted.video[prop].exact) {
                            adapted.video[prop].ideal = adapted.video[prop].exact;
                            delete adapted.video[prop].exact;
                        }
                    });
                    delete adapted.video.deviceId;
                    delete adapted.video.groupId;
                }
                if (adapted.audio && typeof adapted.audio === 'object') {
                    delete adapted.audio.deviceId;
                    delete adapted.audio.groupId;
                }
            }
        } catch (e) { }

        const stream = await _origGUM.call(this, adapted);

        try {
            if (stream && stream.getVideoTracks) {
                stream.getVideoTracks().forEach(t => {
                    try {
                        Object.defineProperty(t, 'label', {
                            get: protect(function () { return CAM_LABEL; }, 'get label'),
                            configurable: true,
                            enumerable: true
                        });
                    } catch (e) { }
                });
            }
            if (stream && stream.getAudioTracks) {
                stream.getAudioTracks().forEach(t => {
                    try {
                        Object.defineProperty(t, 'label', {
                            get: protect(function () { return MIC_LABEL; }, 'get label'),
                            configurable: true,
                            enumerable: true
                        });
                    } catch (e) { }
                });
            }
        } catch (e) { }

        return stream;
    }, 'getUserMedia');

    // ====================================================================
    // 6. RTCPeerConnection — Sanitización de Senders y Stats
    // ====================================================================
    if (window.RTCPeerConnection) {
        if (RTCPeerConnection.prototype.getSenders) {
            const _origGetSenders = RTCPeerConnection.prototype.getSenders;
            RTCPeerConnection.prototype.getSenders = protect(function () {
                const senders = _origGetSenders.call(this);
                if (Array.isArray(senders)) {
                    senders.forEach(s => {
                        if (s && s.track) {
                            try {
                                Object.defineProperty(s.track, 'label', {
                                    get: protect(function () {
                                        return s.track.kind === 'video' ? CAM_LABEL : MIC_LABEL;
                                    }, 'get label'),
                                    configurable: true, enumerable: true
                                });
                            } catch (e) { }
                        }
                    });
                }
                return senders;
            }, 'getSenders');
        }
    }

    // ====================================================================
    // 7. APIs Legacy (navigator.getUserMedia / webkitGetUserMedia)
    // ====================================================================
    try {
        const legacyGUM = protect(function (constraints, successCb, errorCb) {
            navigator.mediaDevices.getUserMedia(constraints)
                .then(stream => { if (successCb) successCb(stream); })
                .catch(err => { if (errorCb) errorCb(err); });
        }, 'getUserMedia');

        if (navigator.getUserMedia) navigator.getUserMedia = legacyGUM;
        if (navigator.webkitGetUserMedia) navigator.webkitGetUserMedia = legacyGUM;
        if (navigator.mozGetUserMedia) navigator.mozGetUserMedia = legacyGUM;
    } catch (e) { }

    // ====================================================================
    // 8. Propagación en Iframes Dinámicos (contentWindow)
    // ====================================================================
    try {
        const _origCreateElem = document.createElement;
        document.createElement = protect(function (tagName, options) {
            const el = _origCreateElem.call(this, tagName, options);
            if (typeof tagName === 'string' && tagName.toLowerCase() === 'iframe') {
                el.addEventListener('load', function () {
                    try {
                        const cw = el.contentWindow;
                        if (cw && cw.navigator && cw.navigator.mediaDevices) {
                            cw.navigator.mediaDevices.enumerateDevices = navigator.mediaDevices.enumerateDevices;
                            cw.navigator.mediaDevices.getUserMedia = navigator.mediaDevices.getUserMedia;
                        }
                    } catch (e) { }
                });
            }
            return el;
        }, 'createElement');
    } catch (e) { }

})();
