@echo off
title K.C.K.Y. - Media Injector & KYC Auditor
pushd "%~dp0"

echo ======================================================================
echo  K.C.K.Y. - SUITE DE INYECCION BIOMETRICA Y AUDITORIA KYC
echo  DirectML AMD RX 580 + WebRTC Stealth Spoofing + Sniffer en Vivo
echo ======================================================================
echo.
set "PY_EXE=..\Deep-Live-Cam\venv\Scripts\python.exe"
if not exist "%PY_EXE%" set "PY_EXE=venv\Scripts\python.exe"
if not exist "%PY_EXE%" set "PY_EXE=python"

echo [*] Utilizando interprete Python: %PY_EXE%
"%PY_EXE%" run.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Se detecto un error al ejecutar K.C.K.Y.
    pause
)

popd
