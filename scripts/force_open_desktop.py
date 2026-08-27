import os
import sys
import time
import subprocess
import ctypes

def open_and_focus():
    url = "http://127.0.0.1:8765"
    # Lanzar explorer directamente
    subprocess.Popen(f'explorer.exe "{url}"', shell=True)
    
    time.sleep(1.5)
    
    # Forzar foco usando Win32 API
    user32 = ctypes.windll.user32
    
    def enum_windows_callback(hwnd, extra):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value
            if "KCKY" in title or "8765" in title or "Suite" in title or "Chrome" in title or "Edge" in title:
                # Traer al frente
                user32.ShowWindow(hwnd, 9) # SW_RESTORE
                user32.SetForegroundWindow(hwnd)
                user32.BringWindowToTop(hwnd)
                print(f"[+] Ventana enfocada en tu pantalla: {title}")
        return True

    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)(enum_windows_callback)
    user32.EnumWindows(cb, 0)

if __name__ == "__main__":
    open_and_focus()
