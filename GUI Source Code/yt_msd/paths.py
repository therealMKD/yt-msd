# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.paths).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
import os
import sys
from PySide6.QtGui import QIcon


# ============================================================
# APPLICATION ICON (title bar, taskbar, system tray)
# icon-256x256.ico sits next to this file in the source tree and is bundled into
# the compiled exe, which unpacks it into its own application folder at startup.
# ============================================================

def _app_icon_path():
    """Absolute path to icon-256x256.ico: inside the packaged app when frozen, next to this file otherwise."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
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
