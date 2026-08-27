"""Lanza launch_window.py de kcky en el desktop físico (WinSta0\\Default)"""
import sys, os
sys.path.insert(0, r"c:\Users\rober\Dropbox\TESTING DEV")
from tools.launch_desktop_window import launch_on_physical_desktop

python_exe = sys.executable
script = r"c:\Users\rober\Dropbox\TESTING DEV\repos\kcky\launch_window.py"
work_dir = r"c:\Users\rober\Dropbox\TESTING DEV\repos\kcky"

cmd = f'"{python_exe}" "{script}"'
print(f"[*] Lanzando: {cmd}")
print(f"[*] WorkDir: {work_dir}")

pid = launch_on_physical_desktop(cmd, work_dir)
if pid:
    print(f"[+] Ventana KCKY despachada en WinSta0\\Default con PID: {pid}")
else:
    import ctypes
    err = ctypes.windll.kernel32.GetLastError()
    print(f"[!] Fallo CreateProcessW. LastError: {err}")
