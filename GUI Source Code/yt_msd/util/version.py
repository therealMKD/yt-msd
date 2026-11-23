# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.util.version).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
import os
import re



def _release_asset_file(asset):
    """(file name, download url) of one GitHub release asset, or ("", "") if it is unusable."""
    if not isinstance(asset, dict):
        return "", ""
    name = (asset.get("name") or "").strip()
    url = (asset.get("browser_download_url") or "").strip()
    return name, url



def select_release_asset(assets, wanted_name):
    """Choose which file of a release this build should download.

    A release page lists its files in whatever order the uploads happened to land
    in, so the first asset is not necessarily the one worth downloading. The wanted
    file is looked up by name instead: an exact match wins, then (for the setup
    program) any .exe named like a setup program, then any asset that simply shares
    the wanted extension. Returns (file name, download url), or ("", "") when the
    release carries nothing this kind of yt-msd can install.
    """
    wanted_name = (wanted_name or "").strip().lower()
    wanted_ext = os.path.splitext(wanted_name)[1]
    setup_like = None
    same_ext = None
    for asset in assets or []:
        name, url = _release_asset_file(asset)
        if not name or not url:
            continue
        lowered = name.lower()
        if lowered == wanted_name:
            return name, url
        if not lowered.endswith(wanted_ext):
            continue
        if same_ext is None:
            same_ext = (name, url)
        if wanted_ext == ".exe" and "setup" in lowered and setup_like is None:
            setup_like = (name, url)
    return setup_like or same_ext or ("", "")



# The packaged GUI has no console of its own, so the renamer is run by starting
# a second copy of the same exe with --renamer (see run_mp3_renamer). The
# launcher build_gui_exe.py puts inside the exe answers that flag by allocating a
# console window for that copy before it runs the renamer CLI, which prints a
# banner, uses colours and asks questions with input().


def _extract_version_number(text):
    """Isolate the full numeric version (including decimals) from a tag like 'RELEASE-3.0' -> (3, 0)."""
    tokens = re.findall(r"\d+(?:\.\d+)*", text or "")
    if not tokens:
        return (0,)
    # Prefer the token that looks most like a complete version (most dots, then longest).
    token = max(tokens, key=lambda s: (s.count("."), len(s)))
    parts = [int(p) for p in token.split(".") if p.isdigit()]
    return tuple(parts) if parts else (0,)



def _version_is_newer(latest, current):
    """Return True if 'latest' is a greater version than 'current' (shorter tuple zero-padded)."""
    n = max(len(latest), len(current))
    latest = tuple(list(latest) + [0] * (n - len(latest)))
    current = tuple(list(current) + [0] * (n - len(current)))
    return latest > current
