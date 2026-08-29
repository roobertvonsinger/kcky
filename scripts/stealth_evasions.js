/**
 * stealth_evasions.js — Evasiones Anti-Detección de Navegador de Grado Avanzado
 * 
 * Script inyectado via context.add_init_script() ANTES de cualquier carga de página.
 * Normaliza el fingerprint del navegador para que coincida 1:1 con un usuario real de Chrome en Windows 10/11.
 * 
 * Configuración dinámica via window.__hw_persona (inyectado por Python antes de este script).
 */

(function () {
    'use strict';

    // ====================================================================
    // 0. Configuración de Hardware Persona (inyectada por Python o defaults)
    // ====================================================================
    const P = window.__hw_persona || {};
    const GPU_VENDOR = P.gpu_vendor || 'Google Inc. (AMD)';
    const GPU_RENDERER = P.gpu_renderer || 'ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)';
    const HW_CONCURRENCY = P.hardware_concurrency || 8;
    const DEV_MEMORY = P.device_memory || 8;
    const MAX_TOUCH = P.max_touch_points || 0;
    const PLATFORM = P.platform || 'Win32';

    // ====================================================================
    // 1. Utilidad: Protección de Function.prototype.toString
    // ====================================================================
    const _fnCache = new Map();

    function protectFunction(fn, nativeName) {
        _fnCache.set(fn, `function ${nativeName}() { [native code] }`);
        return fn;
    }

    // Proxy global de toString para todas las funciones protegidas
    const _origToString = Function.prototype.toString;
    const _boundToString = Function.prototype.call.bind(_origToString);

    Function.prototype.toString = function () {
        if (_fnCache.has(this)) {
            return _fnCache.get(this);
        }
        return _boundToString(this);
    };
    // Proteger el propio toString
    _fnCache.set(Function.prototype.toString, 'function toString() { [native code] }');

    // Exportar para uso de otros módulos stealth
    window.__stealth_protectFn = protectFunction;

    // ====================================================================
    // 2. navigator.webdriver → undefined
    // ====================================================================
    try {
        Object.defineProperty(navigator, 'webdriver', {
            get: protectFunction(function () { return undefined; }, 'get webdriver'),
            configurable: true,
            enumerable: true
        });
    } catch (e) { }

    try {
        const proto = Object.getPrototypeOf(navigator);
        if (proto) {
            const desc = Object.getOwnPropertyDescriptor(proto, 'webdriver');
            if (desc) {
                Object.defineProperty(proto, 'webdriver', {
                    get: protectFunction(function () { return undefined; }, 'get webdriver'),
                    configurable: true,
                    enumerable: true
                });
            }
        }
    } catch (e) { }

    // ====================================================================
    // 3. window.chrome — Objeto nativo completo de Google Chrome
    // ====================================================================
    if (!window.chrome) {
        window.chrome = {};
    }
    if (!window.chrome.runtime) {
        window.chrome.runtime = {
            id: undefined,
            connect: protectFunction(function () { }, 'connect'),
            sendMessage: protectFunction(function () { }, 'sendMessage'),
            onMessage: { addListener: protectFunction(function () { }, 'addListener') },
            onConnect: { addListener: protectFunction(function () { }, 'addListener') }
        };
    }
    if (!window.chrome.app) {
        window.chrome.app = {
            isInstalled: false,
            InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
            RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
            getDetails: protectFunction(function () { return null; }, 'getDetails'),
            getIsInstalled: protectFunction(function () { return false; }, 'getIsInstalled'),
        };
    }
    if (!window.chrome.csi) {
        window.chrome.csi = protectFunction(function () {
            return {
                onloadT: Date.now() - Math.floor(Math.random() * 2000 + 500),
                pageT: performance.now(),
                startE: Date.now() - Math.floor(Math.random() * 3000 + 1000),
                tran: 15
            };
        }, 'csi');
    }
    if (!window.chrome.loadTimes) {
        window.chrome.loadTimes = protectFunction(function () {
            return {
                commitLoadTime: Date.now() / 1000 - Math.random() * 2,
                connectionInfo: 'h2',
                finishDocumentLoadTime: Date.now() / 1000 - Math.random(),
                finishLoadTime: Date.now() / 1000 - Math.random() * 0.5,
                firstPaintAfterLoadTime: 0,
                firstPaintTime: Date.now() / 1000 - Math.random() * 1.5,
                navigationType: 'Other',
                npnNegotiatedProtocol: 'h2',
                requestTime: Date.now() / 1000 - Math.random() * 3,
                startLoadTime: Date.now() / 1000 - Math.random() * 2.5,
                wasAlternateProtocolAvailable: false,
                wasFetchedViaSpdy: true,
                wasNpnNegotiated: true
            };
        }, 'loadTimes');
    }

    // ====================================================================
    // 4. Plugins y MimeTypes — Chrome estándar
    // ====================================================================
    try {
        const PLUGIN_DATA = [
            { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        ];

        const mimeType = {
            type: 'application/pdf',
            suffixes: 'pdf',
            description: 'Portable Document Format',
            __proto__: MimeType.prototype
        };

        const plugins = PLUGIN_DATA.map((pd, i) => {
            const p = Object.create(Plugin.prototype);
            Object.defineProperties(p, {
                name: { value: pd.name, enumerable: true },
                filename: { value: pd.filename, enumerable: true },
                description: { value: pd.description, enumerable: true },
                length: { value: 1, enumerable: true },
                0: { value: mimeType },
            });
            p.item = protectFunction(function (index) { return index === 0 ? mimeType : null; }, 'item');
            p.namedItem = protectFunction(function (name) { return name === 'application/pdf' ? mimeType : null; }, 'namedItem');
            return p;
        });

        const pluginArrayProto = Object.create(PluginArray.prototype);
        Object.defineProperty(pluginArrayProto, 'length', { value: plugins.length, enumerable: true });
        plugins.forEach((p, i) => {
            Object.defineProperty(pluginArrayProto, i, { value: p, enumerable: false });
        });
        pluginArrayProto.item = protectFunction(function (i) { return plugins[i] || null; }, 'item');
        pluginArrayProto.namedItem = protectFunction(function (name) { return plugins.find(p => p.name === name) || null; }, 'namedItem');
        pluginArrayProto.refresh = protectFunction(function () { }, 'refresh');

        Object.defineProperty(navigator, 'plugins', {
            get: protectFunction(function () { return pluginArrayProto; }, 'get plugins'),
            configurable: true, enumerable: true
        });

        const mimeArrayProto = Object.create(MimeTypeArray.prototype);
        Object.defineProperty(mimeArrayProto, 'length', { value: 1, enumerable: true });
        Object.defineProperty(mimeArrayProto, 0, { value: mimeType });
        mimeArrayProto.item = protectFunction(function (i) { return i === 0 ? mimeType : null; }, 'item');
        mimeArrayProto.namedItem = protectFunction(function (name) { return name === 'application/pdf' ? mimeType : null; }, 'namedItem');

        Object.defineProperty(navigator, 'mimeTypes', {
            get: protectFunction(function () { return mimeArrayProto; }, 'get mimeTypes'),
            configurable: true, enumerable: true
        });
    } catch (e) { }

    // ====================================================================
    // 5. navigator.userAgentData — High Entropy Values
    // ====================================================================
    if (navigator.userAgentData) {
        try {
            const _origGetValues = navigator.userAgentData.getHighEntropyValues;
            navigator.userAgentData.getHighEntropyValues = protectFunction(function (hints) {
                return _origGetValues.call(this, hints).then(values => {
                    return Object.assign({}, values, {
                        architecture: 'x86',
                        bitness: '64',
                        model: '',
                        platform: 'Windows',
                        platformVersion: '15.0.0',
                        wow64: false
                    });
                });
            }, 'getHighEntropyValues');
        } catch (e) { }
    }

    // ====================================================================
    // 6. Permissions.query — Estado consistente de permisos
    // ====================================================================
    if (navigator.permissions && navigator.permissions.query) {
        const origQuery = navigator.permissions.query.bind(navigator.permissions);
        navigator.permissions.query = protectFunction(function (descriptor) {
            if (descriptor && (descriptor.name === 'camera' || descriptor.name === 'microphone')) {
                return Promise.resolve({
                    state: 'granted',
                    name: descriptor.name,
                    onchange: null,
                    addEventListener: function () { },
                    removeEventListener: function () { },
                    dispatchEvent: function () { return true; }
                });
            }
            if (descriptor && descriptor.name === 'notifications') {
                return Promise.resolve({
                    state: 'prompt',
                    name: 'notifications',
                    onchange: null,
                    addEventListener: function () { },
                    removeEventListener: function () { },
                    dispatchEvent: function () { return true; }
                });
            }
            return origQuery(descriptor);
        }, 'query');
        window.__permissions_patched = true;
    }

    // ====================================================================
    // 7. WebGL — Spoof GPU Vendor & Renderer
    // ====================================================================
    try {
        function patchWebGL(proto) {
            const origGetParameter = proto.getParameter;
            proto.getParameter = protectFunction(function (param) {
                try {
                    const ext = this.getExtension('WEBGL_debug_renderer_info');
                    if (ext) {
                        if (param === ext.UNMASKED_VENDOR_WEBGL) return GPU_VENDOR;
                        if (param === ext.UNMASKED_RENDERER_WEBGL) return GPU_RENDERER;
                    }
                    if (param === 0x9245) return GPU_VENDOR;
                    if (param === 0x9246) return GPU_RENDERER;
                } catch (e) { }
                return origGetParameter.call(this, param);
            }, 'getParameter');
        }

        if (window.WebGLRenderingContext) patchWebGL(WebGLRenderingContext.prototype);
        if (window.WebGL2RenderingContext) patchWebGL(WebGL2RenderingContext.prototype);
    } catch (e) { }

    // ====================================================================
    // 8. Navigator Properties — Hardware consistency
    // ====================================================================
    try {
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: protectFunction(function () { return HW_CONCURRENCY; }, 'get hardwareConcurrency'),
            configurable: true, enumerable: true
        });
        Object.defineProperty(navigator, 'deviceMemory', {
            get: protectFunction(function () { return DEV_MEMORY; }, 'get deviceMemory'),
            configurable: true, enumerable: true
        });
        Object.defineProperty(navigator, 'maxTouchPoints', {
            get: protectFunction(function () { return MAX_TOUCH; }, 'get maxTouchPoints'),
            configurable: true, enumerable: true
        });
        Object.defineProperty(navigator, 'platform', {
            get: protectFunction(function () { return PLATFORM; }, 'get platform'),
            configurable: true, enumerable: true
        });
    } catch (e) { }

    // ====================================================================
    // 9. Document Focus & Visibility
    // ====================================================================
    try {
        Document.prototype.hasFocus = protectFunction(function () { return true; }, 'hasFocus');
        Object.defineProperty(document, 'hidden', {
            get: protectFunction(function () { return false; }, 'get hidden'),
            configurable: true, enumerable: true
        });
        Object.defineProperty(document, 'visibilityState', {
            get: protectFunction(function () { return 'visible'; }, 'get visibilityState'),
            configurable: true, enumerable: true
        });
    } catch (e) { }

    // ====================================================================
    // 10. Iframes Dinámicos — Auto-propagación inmediata de parches
    // ====================================================================
    try {
        const _origContentWindow = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
        if (_origContentWindow && _origContentWindow.get) {
            Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
                get: protectFunction(function () {
                    const w = _origContentWindow.get.call(this);
                    if (w) {
                        try {
                            if (!w.__stealth_applied) {
                                Object.defineProperty(w.navigator, 'webdriver', {
                                    get: function () { return undefined; },
                                    configurable: true
                                });
                                Object.defineProperty(w.navigator, 'hardwareConcurrency', {
                                    get: function () { return HW_CONCURRENCY; },
                                    configurable: true
                                });
                                Object.defineProperty(w.navigator, 'deviceMemory', {
                                    get: function () { return DEV_MEMORY; },
                                    configurable: true
                                });
                                w.__stealth_applied = true;
                            }
                        } catch (e) { }
                    }
                    return w;
                }, 'get contentWindow'),
                configurable: true, enumerable: true
            });
        }
    } catch (e) { }

    // ====================================================================
    // 11. Limpiar artefactos de automatización conocidos
    // ====================================================================
    try {
        delete window.__playwright;
        delete window.__pw_manual;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
        for (const key of Object.keys(window)) {
            if (key.startsWith('cdc_') || key.startsWith('__webdriver')) {
                try { delete window[key]; } catch (e) { }
            }
        }
    } catch (e) { }

})();
