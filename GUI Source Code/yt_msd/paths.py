# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.paths).
import os
import sys
from PySide6.QtGui import QIcon


# ============================================================
# APPLICATION ICON (title bar, taskbar, system tray)
# icon-256x256.ico sits next to the program in the source tree and is bundled into
# the compiled exe, which unpacks it into its own application folder at startup.
# ============================================================

def program_file():
    """The file this program was started as: the .pyw in the source tree, the exe once installed.

    Deliberately not `__file__`. Since the split, the code that asks lives under yt_msd/, and its
    own `__file__` is a module inside the package rather than the program - which is what made the
    startup registry entry point at yt_msd/sync/startup.py, a file that starts nothing.

    Returns "" when the process has no file it was started from at all.
    """
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    entry = getattr(sys.modules.get("__main__"), "__file__", None)
    if not entry and sys.argv:
        entry = sys.argv[0]
    if not entry:
        return ""
    return os.path.abspath(entry)



def program_folder():
    """The folder the program itself was started from.

    gui_config.json, icon-256x256.ico, a bundled yt-dlp.exe and yt-msd-crash.log all live beside
    the file the program was started as - the .pyw in the source tree, the exe once installed. It
    is the folder of `program_file()`, for the same reason: a folder taken from the asking
    module's own `__file__` names a folder inside the package instead of the one the program sits
    in.

    Returns "" when the process has no file it was started from at all.
    """
    started_as = program_file()
    return os.path.dirname(started_as) if started_as else ""



def _app_icon_path():
    """Absolute path to icon-256x256.ico: inside the packaged app when frozen, next to the program otherwise."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    else:
        base = program_folder()
    return os.path.join(base, "icon-256x256.ico")



def app_icon():
    """The application icon, or None when icon-256x256.ico is missing or unreadable."""
    path = _app_icon_path()
    if os.path.isfile(path):
        icon = QIcon(path)
        if not icon.isNull():
            return icon
    return None



def is_packaged_build():
    """True when yt-msd is running as the packaged exe, False when it is running the source file."""
    return bool(getattr(sys, 'frozen', False))
