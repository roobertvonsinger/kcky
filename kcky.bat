@echo off
title K.C.K.Y. - Media Injector & KYC Auditor
pushd "%~dp0"

echo ======================================================================
echo  K.C.K.Y. - SUITE DE INYECCION BIOMETRICA Y AUDITORIA KYC
echo  DirectML AMD RX 580 + WebRTC Stealth Spoofing + Sniffer en Vivo
echo ======================================================================
echo.
echo [*] Verificando dependencias y modelos de IA...
python run.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Se detecto un error al ejecutar K.C.K.Y.
    pause
)

popd
