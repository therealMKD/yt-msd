# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.deps).
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
    # Bound either way: the entry point re-exports these names, and HostFolderWatcher decides
    # whether to use them by reading _WATCHDOG_AVAILABLE. Leaving them undefined here makes the
    # re-export itself fail on a machine with no watchdog, which stops the program starting.
    Observer = None
    FileSystemEventHandler = None
    _WATCHDOG_AVAILABLE = False
