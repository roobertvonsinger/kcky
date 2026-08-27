"""
launch_app_window.py — Lanzador Empírico de ventana KCKY al monitor físico
Usa Windows Task Scheduler para bypassear el aislamiento de desktop virtual (exebox).
Chromium (Edge/Chrome) no respeta lpDesktop en CreateProcessW (spawna subprocesos que heredan
el desktop del session, no del STARTUPINFO). Task Scheduler ejecuta en la sesión interactiva real.
"""
import sys
import os
import subprocess
import time

def find_browser():
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    ]
    for b in candidates:
        if os.path.isfile(b):
            return b
    return None

def launch_kcky_window(url="http://127.0.0.1:8765", width=1420, height=920):
    browser = find_browser()
    if not browser:
        print("[!] No se encontró Edge ni Chrome")
        return False

    user_data = os.path.join(os.environ.get("TEMP", r"C:\Temp"), "kcky_studio_app")
    os.makedirs(user_data, exist_ok=True)

    args = f'--app={url} --window-size={width},{height} --new-window --no-first-run --user-data-dir="{user_data}"'
    task_name = "KCKY_Launch"

    # Registrar y ejecutar via Task Scheduler (sesión interactiva real)
    ps_script = f'''
$action = New-ScheduledTaskAction -Execute "{browser}" -Argument '{args}'
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(1)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "{task_name}" -Action $action -Trigger $trigger -Settings $settings -User "{os.environ.get('USERNAME', 'rober')}" -Force | Out-Null
Start-ScheduledTask -TaskName "{task_name}"
'''
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True, text=True, timeout=10
    )

    if result.returncode != 0:
        print(f"[!] Error creando tarea: {result.stderr}")
        return False

    print(f"[+] Ventana KCKY despachada al monitor físico via Task Scheduler")
    print(f"    Browser: {browser}")
    print(f"    URL: {url}")
    print(f"    Tamaño: {width}x{height}")

    # Limpiar tarea después de lanzar
    time.sleep(3)
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", f'Unregister-ScheduledTask -TaskName "{task_name}" -Confirm:$false'],
        capture_output=True, text=True, timeout=5
    )

    return True


if __name__ == "__main__":
    ok = launch_kcky_window()
    sys.exit(0 if ok else 1)
