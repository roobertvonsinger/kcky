@echo off
setlocal
echo ===================================================
echo   LANZANDO PRUEBA DE CAMARA VIRTUAL EN NAVEGADOR
echo ===================================================

set Y4M_FILE=%~dp0data\buffers\live_audit_stream.y4m
set TEMP_DIR=%TEMP%\onboarded_cam_live_%RANDOM%

mkdir "%TEMP_DIR%" 2>nul

set BROWSER_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe
if not exist "%BROWSER_EXE%" (
    set BROWSER_EXE=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe
)

echo Usando Navegador: "%BROWSER_EXE%"
echo Usando Video: "%Y4M_FILE%"
echo Abriendo https://webcamtests.com/ ...

start "" "%BROWSER_EXE%" --user-data-dir="%TEMP_DIR%" --no-first-run --no-default-browser-check --use-fake-ui-for-media-stream --use-fake-device-for-media-stream --use-file-for-fake-video-capture="%Y4M_FILE%" "https://webcamtests.com/"

echo.
echo [OK] Ventana lanzada en primer plano.
pause
