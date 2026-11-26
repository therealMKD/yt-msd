# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.util.version).
import os
import re

from yt_msd.constants import UPDATE_REPO


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


# How a release on GitHub is named in this repository: the version the app carries, with
# "RELEASE-" in front of it ("RELEASE-3.4", "RELEASE-3.2"). A release page is the changelog
# for a version of yt-msd, and the box that tells someone they are now on a new version has to
# reach that page without asking the network what the tag is called - which is what this prefix
# is for.
RELEASE_TAG_PREFIX = "RELEASE-"


def release_notes_url(version):
    """The release page holding the notes for a version of yt-msd.

    "3.5" becomes the tag page for RELEASE-3.5, because that is how every release in this repository
    is named - RELEASE-3.0 through RELEASE-3.4, each one the version the app carries with "RELEASE-"
    in front of it - and a version already written as "RELEASE-3.5" arrives at the same page. A
    version padded out with a zero nobody released, "3.6.0" written where the release is 3.6, is
    named by the parts a release is named by; a third part that is not zero is a patch release, and a
    patch release is tagged with it. A version with no numbers in it - a build carrying no
    APP_VERSION at all - gets the general releases page rather than a tag page that cannot exist.
    """
    base = f"https://github.com/{UPDATE_REPO}/releases"
    tokens = re.findall(r"\d+(?:\.\d+)*", str(version or ""))
    if not tokens:
        return base
    number = max(tokens, key=lambda s: (s.count("."), len(s)))
    parts = number.split(".")
    if len(parts) > 2 and parts[-1] == "0":
        number = ".".join(parts[:-1])
    return f"{base}/tag/{RELEASE_TAG_PREFIX}{number}"


def version_notes_are_due(current_version, seen_version):
    """Whether a copy running 'current_version' should say out loud that it is now on that version.

    The answer is kept in this copy's own settings file rather than worked out from the network,
    because the thing being noticed is that this machine has changed - and that happens just as
    truly when somebody runs the setup program by hand as when the app downloads the update
    itself. A version older than the one already recorded is answered with nothing: a copy moved
    back to an older build has not gained anything worth a box, and nagging about it would be
    nagging about a downgrade nobody asked about.

    No recorded version at all is a yes. That is the case that matters most - a copy updated from
    a version that predates this box has no marker to compare against, and the upgrade would go
    unmentioned if an empty marker meant "nothing to report" - and a brand-new install gets the
    same box once, which is the honest reading of "you are now on version X".
    """
    current = _extract_version_number(current_version)
    if not re.search(r"\d", str(current_version or "")):
        # Nothing to announce, and nothing worth recording as announced.
        return False
    seen_text = str(seen_version or "").strip()
    if not seen_text:
        return True
    return _version_is_newer(current, _extract_version_number(seen_text))

