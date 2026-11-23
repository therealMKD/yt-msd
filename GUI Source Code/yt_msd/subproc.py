# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.subproc).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
import os
import sys
import subprocess



def _hidden_window_kwargs():
    """subprocess kwargs that stop helper programs from flashing a console window."""
    if sys.platform != "win32":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {"startupinfo": startupinfo, "creationflags": 0x08000000}



def _child_utf8_env():
    """Ask child programs for UTF-8 so titles and JSON survive non-ASCII text."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return env
