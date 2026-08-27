@echo off
title ONBOARDED - Media Injector and KYC Auditor
pushd "%~dp0"

echo ======================================================================
echo  ONBOARDED - SUITE DE INYECCION BIOMETRICA Y AUDITORIA KYC
echo  DirectML AMD RX 580 + WebRTC Stealth Spoofing + Sniffer en Vivo
echo ======================================================================
echo.
echo [*] Iniciando Onboarded Studio en http://127.0.0.1:8765...

python run.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Se detecto un error al ejecutar Onboarded.
    pause
)

popd
