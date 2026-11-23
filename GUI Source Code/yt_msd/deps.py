# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.deps).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
try:
    import winreg
except ImportError:
    winreg = None

try:
    import vlc
    _VLC_MODULE_AVAILABLE = True
except Exception as e:
    vlc = None
    _VLC_MODULE_AVAILABLE = False
    _VLC_IMPORT_ERROR = str(e)


try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    _WATCHDOG_AVAILABLE = True
except ImportError:
    _WATCHDOG_AVAILABLE = False
