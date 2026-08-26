@echo off
title ONBOARDED — Media Injector & KYC Auditor
chcp 65001 >nul
cd /d "%~dp0"

echo ======================================================================
echo  👁️ ONBOARDED — SUITE DE INYECCIÓN BIOMÉTRICA & AUDITORÍA KYC
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
