# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.ytdlp.install).
#
# Finding the yt-dlp this system already has, driving winget to install or update
# it, and asking GitHub what the newest release is. Nothing here runs yt-dlp to
# answer a question about a video - that is yt_msd.ytdlp.runner.
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
import os
import sys
import json
import subprocess
import shutil
from pathlib import Path
import urllib.request
import urllib.parse
from yt_msd.subproc import _hidden_window_kwargs
from yt_msd.paths import program_folder


# ============================================================
# SYSTEM yt-dlp: installed and updated with winget, never bundled in the exe
# ============================================================
# yt-dlp is updated almost weekly, so the packaged build does not carry its own
# copy inside the executable. yt-dlp is a normal Windows program (winget id
# "yt-dlp.yt-dlp") and yt-msd drives it through its command line instead of the
# Python API. Whether a newer yt-dlp exists is answered by GitHub; installing and
# updating it is done by winget, which is already part of Windows 10/11. No pip,
# no bundled copy that goes stale, and nothing to rebuild when yt-dlp ships a fix.
YTDLP_WINGET_ID = "yt-dlp.yt-dlp"

YTDLP_GITHUB_REPO = "yt-dlp/yt-dlp"

YTDLP_UPDATE_CHECK_INTERVAL = 7 * 24 * 60 * 60  # seconds between "is yt-dlp current?" checks

YTDLP_INSTALL_TIMEOUT = 1200  # winget installs can be slow

YTDLP_EXTRACT_TIMEOUT = 300  # search / stream-info extraction



class YtDlpMissingError(RuntimeError):
    """Raised when yt-dlp is needed but no yt-dlp exists on this system."""



def _yt_dlp_lookup_paths():
    """Places to look for yt-dlp.exe before falling back to PATH.

    The winget copy comes first on purpose: it is the copy yt-msd can keep up
    to date. A copy placed next to the program, or one only reachable through
    PATH, is still used when there is no winget copy.
    """
    candidates = []
    local = os.environ.get("LOCALAPPDATA") or ""
    if local:
        candidates.append(os.path.join(local, "Microsoft", "WinGet", "Links", "yt-dlp.exe"))
        packages = os.path.join(local, "Microsoft", "WinGet", "Packages")
        if os.path.isdir(packages):
            try:
                for unpacked in Path(packages).glob("yt-dlp.yt-dlp*"):
                    candidates.append(str(unpacked / "yt-dlp.exe"))
            except Exception:
                pass
    try:
        if getattr(sys, 'frozen', False):
            base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.executable)))
        else:
            base_dir = program_folder()
        candidates.append(os.path.join(base_dir, "yt-dlp.exe"))
    except Exception:
        pass
    return candidates


def find_winget_executable():
    """winget.exe, the package manager that ships with Windows. None if absent."""
    found = shutil.which("winget")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA") or ""
    if local:
        candidate = os.path.join(local, "Microsoft", "WindowsApps", "winget.exe")
        if os.path.isfile(candidate):
            return candidate
    return None



def run_winget(args, timeout=YTDLP_INSTALL_TIMEOUT):
    """Run winget with these arguments. Returns (returncode, output, error)."""
    winget = find_winget_executable()
    if not winget:
        return None, "", "winget was not found on this system."
    try:
        result = subprocess.run([winget] + list(args), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
                                timeout=timeout, **_hidden_window_kwargs())
        return result.returncode, (result.stdout or ""), ""
    except Exception as e:
        return None, "", str(e)



def latest_yt_dlp_release():
    """Newest published yt-dlp release tag from GitHub ('' if it cannot be read)."""
    try:
        api_url = f"https://api.github.com/repos/{YTDLP_GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(api_url, headers={"User-Agent": "yt-msd-updater"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return (data.get("tag_name") or "").strip()
    except Exception:
        return ""
