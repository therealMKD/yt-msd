# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.sync.startup).
import sys
from yt_msd.deps import winreg
from yt_msd.paths import program_file



def is_run_on_startup_enabled() -> bool:
    """Checks whether yt-msd is configured in the Windows HKCU Run startup registry key."""
    if sys.platform != 'win32':
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
        try:
            val, _ = winreg.QueryValueEx(key, "yt-msd")
            winreg.CloseKey(key)
            return bool(val)
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False
    except Exception:
        return False



def set_run_on_startup(enable: bool) -> bool:
    """Enables or disables running yt-msd on Windows startup via HKCU Run registry key."""
    if sys.platform != 'win32':
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
        app_name = "yt-msd"
        if enable:
            if getattr(sys, 'frozen', False):
                cmd = f'"{sys.executable}"'
            else:
                # The program's own file rather than this module's: a startup entry pointing at
                # yt_msd/sync/startup.py would run a module that starts nothing at all.
                script_path = program_file()
                pythonw = sys.executable
                idx = pythonw.lower().rfind("python.exe")
                if idx != -1:
                    pythonw = pythonw[:idx] + "pythonw.exe"
                cmd = f'"{pythonw}" "{script_path}"'
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False
