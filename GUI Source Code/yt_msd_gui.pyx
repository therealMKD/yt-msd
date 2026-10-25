# Open Source Software under the Apache License, Version 2.0
# PySide6 version of yt-msd - Cython source for the compiled GUI build
#
# Everything after the END OF CYTHON HEADER line below is the text of
# "GUI Source Code/yt-msd-gui.pyw" copied byte-for-byte, so the compiled program behaves
# exactly like the script. Edit the .pyw, then run:
#     python build_gui_cython.py sync      (rewrites this file from the .pyw)
#     python build_gui_cython.py verify    (checks the two are still identical)
#
# The directives are all set to keep Python semantics unchanged:
#   language_level=3         Python 3 rules for division, print, str/bytes, comparisons.
#   annotation_typing=False  "def f(x: int) -> Optional[str]" hints stay documentation, so no
#                            argument or return value is type-checked or converted at call time.
#   infer_types=False        no variable is given a C int/float type, so large integers, None
#                            handling and error messages stay exactly Python's own.
#   binding=True             closures and nested functions capture names the way Python does.
# cython: language_level=3
# cython: annotation_typing=False
# cython: infer_types=False
# cython: binding=True
#
# ---- END OF CYTHON HEADER - the unchanged yt-msd-gui.pyw source follows ----
# Open Source Software under the Apache License, Version 2.0
# PySide6 version of yt-msd
# Programmed with Antigravity, if you don't like it, don't use it.

import os
import re
import sys
import json
import threading
import tempfile
import subprocess
import zipfile
import shutil
from pathlib import Path
# ThreadPoolExecutor is not defined in concurrent.futures - Python 3.15 hands it over with
# a "lazy from" (concurrent/futures/__init__.py: lazy from .thread import ThreadPoolExecutor),
# and that deferred binding is an object of its own called lazy_import, which is not callable.
# Running this file as a script never notices: Python resolves the binding the moment the name
# is used. The compiled build does notice, because it stores whatever the name held at import
# time, and in the installed exe that is the unresolved binding - which is the
# "TypeError: 'lazy_import' object is not callable" that fired on every local-library metadata
# pass. Importing from the module that really defines the class skips the lazy re-export.
from concurrent.futures.thread import ThreadPoolExecutor
from concurrent.futures import as_completed  # a plain re-export, already resolved at import
try:
    import winreg
except ImportError:
    winreg = None
import webbrowser
import urllib.request
import io
try:
    import vlc
    _VLC_MODULE_AVAILABLE = True
except Exception as e:
    vlc = None
    _VLC_MODULE_AVAILABLE = False
    _VLC_IMPORT_ERROR = str(e)
import shlex
import time
import random
import socket
import struct
import hashlib
import traceback
from typing import Dict, List, Optional, Tuple, Callable, Union
from PIL import Image

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    _WATCHDOG_AVAILABLE = True
except ImportError:
    _WATCHDOG_AVAILABLE = False

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QPushButton, QLineEdit, 
                               QComboBox, QCheckBox, QSlider, QScrollArea, 
                               QSplitter, QSplitterHandle, QFileDialog, QMessageBox, QDialog,
                               QSystemTrayIcon, QMenu, QFrame, QGridLayout,
                               QSizePolicy, QStyle, QToolTip, QStyleOption, QSpinBox, QProgressBar, QInputDialog)
from PySide6.QtCore import Qt, Signal, QTimer, Slot, QPoint, QRect, QMargins, QThread, QEvent, QObject, QByteArray
from PySide6.QtGui import QIcon, QPixmap, QImage, QAction, QColor, QPalette, QPainter, QPainterPath, QBrush, QFont, QDrag, QFontMetrics
from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtNetwork import QLocalServer, QLocalSocket

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

# ============================================================
# INTEGRATED MP3 RENAMER, TAGGER & LOUDNESS NORMALIZER
# (Ported from mp3renamer5000.py — interactive CLI mode & algorithms)
# ============================================================

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[90m'

_print_lock = threading.Lock()

def _safe_print(msg):
    with _print_lock:
        print(msg)

_available_threads = os.cpu_count() or 4
TARGET_LUFS = "-16"
TRUE_PEAK = "-1.5"
LOUDNESS_RANGE = "11"
BITRATE = "320k"
MAX_WORKERS = max(1, _available_threads // 2)
SILENCE_PAD_DUR = 2.0
SILENCE_TRIM = True  # Trim leading/trailing silence; independent of the loudnorm override
# Built-in silence trimming values. Used verbatim for both the front pass and the
# reversed back pass - a loudnorm override never changes them.
SILENCE_THRESHOLD = "-60dB"
SILENCE_DURATION = "0.5"
SILENCE_KEEP = "0.5"
CUSTOM_NORM_CMD = ""  # Optional override of ONLY the loudnorm part of the ffmpeg -af chain

# Internal version number - the numeric part of the latest GitHub release tag.
# (RELEASE-3.2 is tagged as "RELEASE-3.2" and read here as "3.2":
# _extract_version_number() reduces both sides to their numbers before comparing
# them, so a tag is still recognised as this version or as a newer one. The same
# numbers are what build_gui_exe.py puts in the installer and in the version
# resource of the exe, so the app, the setup program and the file's own
# Properties dialog all report one version.)
APP_VERSION = "3.2"

# GitHub repository whose releases page is polled for newer versions.
UPDATE_REPO = "therealMKD/yt-msd"

# Which file of a release this copy of yt-msd downloads depends on how it is being
# run: the packaged exe is updated with its setup program, a copy started from the
# source is updated with the new source file written over the one being run.
INSTALLER_ASSET = "yt-msd-setup.exe"   # what the packaged exe looks for on a release
SOURCE_ASSET = "yt-msd-gui.pyw"        # what a copy started from the source looks for

# How a downloaded update gets applied, reported to UpdateReadyDialog and used by
# _launch_swap_helper:
UPDATE_MODE_INSTALLER = "installer"  # run the downloaded setup program; this file is left alone
UPDATE_MODE_REPLACE = "replace"      # the download was written over the file being run
UPDATE_MODE_SWAP = "swap"            # keep both files, delete this one, launch the new one


def is_packaged_build():
    """True when yt-msd is running as the packaged exe, False when it is running the source file."""
    return bool(getattr(sys, 'frozen', False))


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

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, COMM, ID3NoHeaderError
from mutagen.easymp4 import EasyMP4
from mutagen import File as MutagenFile

def _print_renamer_banner():
    banner = rf"""{Colors.CYAN}{Colors.BOLD}                                                  
 _____ _____ ___    _____                           
|     |  _  |_  |  | __  |___ ___ ___ _____ ___ ___ 
| | | |   __|_  |  |    -| -_|   | .'|     | -_|  _|
|_|_|_|__|  |___|  |__|__|___|_|_|__,|_|_|_|___|_|  
{Colors.END}"""
    print(banner)
    print(f"{Colors.BOLD}Interactive MP3/M4A Renamer, Tagger & Loudness Normalizer{Colors.END}")
    print(f"{Colors.BOLD}Available CPU Threads: {_available_threads}{Colors.END}\n")
    print(f"{Colors.BOLD}Using {MAX_WORKERS} CPU Threads for Processing{Colors.END}\n")
    print(f"{Colors.GREEN}[✓] Mutagen library active. Automatic metadata tagging is enabled.{Colors.END}\n")

def _select_renamer_folder():
    print(f"{Colors.BLUE}Please select the folder containing your audio files...{Colors.END}")
    folder_path = ""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.focus_force()
        folder_path = filedialog.askdirectory(title="Select Audio Folder (MP3/M4A)")
        root.destroy()
    except Exception:
        pass
    if not folder_path:
        folder_path = input(f"{Colors.BOLD}Enter the folder path containing MP3/M4A files:{Colors.END}\n").strip()
    if not folder_path:
        print(f"{Colors.RED}No folder selected. Exiting.{Colors.END}")
        sys.exit(0)
    path = Path(folder_path)
    if not path.exists() or not path.is_dir():
        print(f"{Colors.RED}The folder '{folder_path}' does not exist or is not a directory.{Colors.END}")
        sys.exit(1)
    return path

def _is_romanized(text):
    return re.search(
        r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af\u0400-\u04ff\u0370-\u03ff\u0600-\u06ff]',
        text
    ) is None

def clean_youtube_title(filename):
    title = filename
    title = re.sub(r'[\u2010-\u2015—–‐‑‒―]+', '-', title)
    title = re.sub(r'-+', '-', title)
    title = re.sub(r'[｜│┃ǀ]+', '|', title)
    title = title.replace('：', ':')
    title = title.replace('’', "'").replace('‘', "'").replace('`', "'").replace('´', "'")
    title = title.replace('“', '"').replace('”', '"')

    MASK_HYPHEN = "\x00HYPHEN\x00"
    MASK_PIPE   = "\x00PIPE\x00"
    MASK_COLON  = "\x00COLON\x00"

    def mask_separators_in_brackets(text):
        result, depth, i = [], 0, 0
        while i < len(text):
            ch = text[i]
            if ch in '([{':
                depth += 1; result.append(ch); i += 1
            elif ch in ')]}':
                depth -= 1; result.append(ch); i += 1
            elif depth > 0:
                if text[i:i+3] == ' - ':
                    result.append(MASK_HYPHEN); i += 3
                elif text[i] == '|':
                    result.append(MASK_PIPE); i += 1
                elif text[i] == ':':
                    result.append(MASK_COLON); i += 1
                else:
                    result.append(ch); i += 1
            else:
                result.append(ch); i += 1
        return ''.join(result)

    title = mask_separators_in_brackets(title)
    title = re.sub(r'\s*:\s*', ' - ', title)

    if "|" in title:
        if "-" not in title:
            title = title.replace("|", " - ")
        else:
            title = title.split("|")[0].rstrip()

    title = re.sub(r'\s+-\s+', ' - ', title)

    parts = title.split(" - ")
    if len(parts) > 2:
        title = " - ".join(parts[:2])

    title = title.replace(MASK_HYPHEN, ' - ').replace(MASK_PIPE, '|').replace(MASK_COLON, ':')

    if " - " in title:
        parts = title.split(" - ", 1)
        artist_part, title_part = parts[0].strip(), parts[1].strip()
        if not _is_romanized(title_part):
            m = re.search(r'[\(\[\{]([^\)\}\]]+)[\)\]\}]', title_part)
            if m:
                inside = m.group(1).strip()
                if not _is_romanized(inside):
                    title_part = inside
        title = f"{artist_part} - {title_part}"
    else:
        if not _is_romanized(title):
            m = re.search(r'[\(\[\{]([^\)\}\]]+)[\)\]\}]', title)
            if m:
                inside = m.group(1).strip()
                if not _is_romanized(inside):
                    title = inside

    if " - " in title:
        parts = title.split(" - ", 1)
        artist_part = re.split(r'\s*&\s*|\s+[xX]\s+', parts[0].strip())[0].strip()
        title = f"{artist_part} - {parts[1].strip()}"

    def process_brackets(match):
        inside = match.group(2)
        if not _is_romanized(inside):
            return inside
        return ""

    bracket_pair_pattern = r'(\(|\[|\{)([^\(\)\[\]\{\}]*)(\)|\]|\})'
    old_title = ""
    while old_title != title:
        old_title = title
        title = re.sub(bracket_pair_pattern, process_brackets, title)

    title = re.sub(r'[\(\)\{\}\[\]]', '', title)
    title = re.sub(r'\b(hd|version|original|official|4k|uhd|upgraded|upscaled|remastered|lyrics)\b', '', title, flags=re.IGNORECASE)
    title = re.compile(r'\b(ft|feat|featuring)\b\.?', re.IGNORECASE).split(title)[0]
    title = re.sub(r'#\S+', '', title)

    # Quote handling:
    # 1. Double quotes are never part of a contraction, so every double-quote character is
    #    removed outright: ASCII " plus the unicode variants - curly U+201C/U+201D, low
    #    double U+201E, reversed-9 high U+201F, guillemets U+00AB/U+00BB and the double
    #    prime U+2033. No pairing and no adjacency rules are applied. This is what stops Bad
    #    Lip Reading style titles (which wrap words in quotes) from leaving floating double
    #    quotes behind in the filename.
    title = re.sub(r'["\u201c\u201d\u201e\u201f\u00ab\u00bb\u2033]', '', title)

    # 2. Mask interior word contractions (e.g. Don't, won't, it's, rock'n'roll)
    MASK = "\x00APOS\x00"
    title = re.sub(r"([a-zA-Z0-9])'([a-zA-Z0-9])", rf"\1{MASK}\2", title)

    # 2b. Quoted-title pattern with no explicit artist separator.
    #     When no " - " was detected anywhere but there is a balanced single-quote pair
    #     (opening quote preceded by whitespace), treat it as "<artist> '<title>' <junk>":
    #     everything before the quotes becomes the artist, the quoted text becomes the title,
    #     the quotes are dropped and everything after the closing quote is stripped.
    #     Common for Kpop uploads, e.g. "A2O Lite 'NEON' Official Video" -> "A2O Lite - NEON".
    if " - " not in title:
        m = re.match(r"^(.*?)\s+'([^']+)'.*$", title)
        if m:
            quoted_artist = m.group(1).strip()
            quoted_title  = m.group(2).strip()
            if quoted_artist and quoted_title:
                title = f"{quoted_artist} - {quoted_title}"

    # 3. Remove balanced single-quote pairs ('x')
    old = None
    while old != title:
        old = title
        title = re.sub(r"'([^']*)'", r'\1', title)

    # 4. Remove any UNATTACHED single quotes (not touching any letters/numbers on either side)
    title = re.sub(r"(?<![a-zA-Z0-9])'(?![a-zA-Z0-9])", "", title)

    # 5. Restore masked interior contractions (e.g. Don't stays as Don't)
    title = title.replace(MASK, "'")

    try:
        title = re.sub(r'[\U00010000-\U0010ffff\u2600-\u27bf]', '', title, flags=re.UNICODE)
    except re.error:
        pass

    title = re.sub(r'\s+', ' ', title).strip()

    if " - " in title:
        parts = title.split(" - ", 1)
        artist_part = parts[0].strip()
        title_part = parts[1].strip()
        if "," in artist_part:
            artist_part = artist_part.split(",")[0].strip()
        title = f"{artist_part} - {title_part}"
    else:
        title = re.sub(r'\s*-\s*$', '', title)
        title = re.sub(r'^\s*-\s*', '', title)
        title = title.strip()

    invalid_chars = r'[\\/:*?<>|]'
    title = re.sub(invalid_chars, '_', title)
    title = re.sub(r'\s+', ' ', title).strip()

    return title

def read_metadata_tags(filepath):
    suffix = filepath.suffix.lower()
    try:
        if suffix == ".mp3":
            try:
                tags = EasyID3(filepath)
                artist = tags.get("artist", [None])[0] or tags.get("albumartist", [None])[0] or tags.get("performer", [None])[0]
                title = tags.get("title", [None])[0]
                return (str(artist).strip() if artist else None), (str(title).strip() if title else None)
            except ID3NoHeaderError:
                return None, None
        elif suffix == ".m4a":
            try:
                tags = EasyMP4(filepath)
                artist = tags.get("artist", [None])[0] or tags.get("albumartist", [None])[0]
                title = tags.get("title", [None])[0]
                return (str(artist).strip() if artist else None), (str(title).strip() if title else None)
            except Exception:
                return None, None
    except Exception:
        pass
    return None, None

def write_metadata_tags(filepath, artist, title):
    suffix = filepath.suffix.lower()
    try:
        if suffix == ".mp3":
            try:
                tags = EasyID3(filepath)
            except ID3NoHeaderError:
                tags = EasyID3()
                tags.save(filepath)
                tags = EasyID3(filepath)
            tags["artist"] = artist
            tags["title"] = title
            tags.save()
            return True
        elif suffix == ".m4a":
            try:
                tags = EasyMP4(filepath)
            except Exception:
                tags = EasyMP4(filepath)
            tags["artist"] = artist
            tags["title"] = title
            tags.save()
            return True
    except Exception as e:
        print(f"{Colors.RED}Error writing tags to {filepath.name}: {e}{Colors.END}")
    return False

def _add_placeholder_tag(filepath):
    if not os.path.exists(filepath): return
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == ".mp3":
            try:
                audio = ID3(filepath)
            except ID3NoHeaderError:
                audio = ID3()
            audio.setall('COMM', [COMM(encoding=3, lang='eng', desc='ytmsd', text='YTMSD_PENDING_VERIFY')])
            audio.save(filepath)
        elif ext == ".m4a":
            try:
                tags = EasyMP4(filepath)
                tags['comment'] = ['YTMSD_PENDING_VERIFY']
                tags.save()
            except Exception:
                pass
    except Exception:
        pass

def _has_placeholder_tag(filepath):
    if not os.path.exists(filepath): return False
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == ".mp3":
            audio = ID3(filepath)
            return any('YTMSD_PENDING_VERIFY' in str(c.text) for c in audio.getall('COMM'))
        elif ext == ".m4a":
            tags = EasyMP4(filepath)
            return 'YTMSD_PENDING_VERIFY' in tags.get('comment', [])
    except Exception:
        return False
    return False

def _remove_placeholder_tag(filepath):
    if not os.path.exists(filepath): return
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == ".mp3":
            audio = ID3(filepath)
            comms = [c for c in audio.getall('COMM') if 'YTMSD_PENDING_VERIFY' not in str(c.text)]
            audio.setall('COMM', comms)
            audio.save(filepath)
        elif ext == ".m4a":
            tags = EasyMP4(filepath)
            if 'comment' in tags:
                tags['comment'] = [c for c in tags['comment'] if c != 'YTMSD_PENDING_VERIFY']
                tags.save()
    except Exception:
        pass


def clean_and_tag_files(folder_path, start_auto=False):
    extensions = TAGGABLE_EXTENSIONS
    files = sorted([f for f in folder_path.iterdir() if f.is_file() and f.suffix.lower() in extensions])
    
    if not files:
        print(f"{Colors.YELLOW}No MP3 or M4A files found in this folder.{Colors.END}")
        return 0, 0, 0, 0
        
    print(f"{Colors.GREEN}Found {len(files)} audio files for renaming.{Colors.END}\n")
    
    renamed_count = 0
    tagged_count = 0
    skipped_count = 0
    already_formatted_count = 0
    
    def run_renaming_pass(file_list, is_manual_skipped_pass=False):
        nonlocal renamed_count, tagged_count, skipped_count, already_formatted_count
        
        auto_mode = start_auto if not is_manual_skipped_pass else False
        skipped_files = []
        forced_redo_indices = set()
        
        idx = 1
        while idx <= len(file_list):
            file = file_list[idx - 1]
            stem = file.stem
            suffix = file.suffix.lower()
            
            current_suggestion = clean_youtube_title(stem)
            existing_artist, existing_title = read_metadata_tags(file)
            
            filename_is_correct = (current_suggestion == stem and " - " in stem)
            has_valid_tags = bool(existing_artist and existing_title)
            
            is_forced_redo = (idx in forced_redo_indices)
            if is_forced_redo:
                forced_redo_indices.remove(idx)
            
            # Skip renaming AND normalization if file already has both artist and title tags
            if not is_manual_skipped_pass and not is_forced_redo and has_valid_tags:
                print(f"{Colors.DIM}[{idx}/{len(file_list)}] {Colors.GREEN}✔ Already tagged (artist+title present), skipping: {Colors.END}{file.name}")
                already_formatted_count += 1
                idx += 1
                continue
            
            is_manually_inputted = False
            if auto_mode:
                has_artist_sep = " - " in current_suggestion
                artist_name = ""
                title_name = ""
                if has_artist_sep:
                    parts = current_suggestion.split(" - ", 1)
                    artist_name = parts[0].strip()
                    title_name = parts[1].strip()
                
                if not has_artist_sep or not artist_name or not title_name:
                    skipped_files.append(file)
                    skipped_count += 1
                    idx += 1
                    continue
                else:
                    final_name = current_suggestion
            else:
                final_name = None
                skip_file = False
                go_prev = False
                while True:
                    print(f"{Colors.DIM}─" * 60)
                    print(f"{Colors.BOLD}[{idx}/{len(file_list)}] File: {Colors.END}{file.name}")
                    print(f"  {Colors.YELLOW}Original  :{Colors.END} {stem}")
                    print(f"  {Colors.GREEN}Predicted :{Colors.END} {current_suggestion}")
                    
                    if has_valid_tags:
                        print(f"  {Colors.CYAN}Tags found:{Colors.END} Artist='{existing_artist}', Title='{existing_title}'")
                    else:
                        print(f"  {Colors.DIM}Tags found: [None/Missing]{Colors.END}")
                        
                    has_artist_sep = " - " in current_suggestion
                    artist_name = ""
                    title_name = ""
                    if has_artist_sep:
                        parts = current_suggestion.split(" - ", 1)
                        artist_name = parts[0].strip()
                        title_name = parts[1].strip()
                        
                    if not has_artist_sep or not artist_name or not title_name:
                        artist_prompt = (
                            f"\n  {Colors.CYAN}No artist found.{Colors.END} Predicted title: {Colors.BOLD}{current_suggestion}{Colors.END}\n"
                            f"  Type the {Colors.GREEN}artist name{Colors.END} to build '{Colors.BOLD}Artist - {current_suggestion}{Colors.END}',\n"
                            f"  {Colors.YELLOW}'n'{Colors.END} to enter a full name manually, {Colors.YELLOW}'s'{Colors.END} to skip, {Colors.YELLOW}'prev'{Colors.END} to redo previous, or type {Colors.YELLOW}'AUTO'{Colors.END} to switch to auto-mode:\n  > "
                        )
                        user_input = input(artist_prompt).strip()
                        
                        if user_input.upper() == 'AUTO':
                            auto_mode = True
                            break
                        elif user_input.lower() == 'prev':
                            if idx > 1:
                                go_prev = True
                                forced_redo_indices.add(idx - 1)
                            else:
                                print(f"  {Colors.YELLOW}Already at the first file.{Colors.END}")
                            break
                        elif user_input.lower() == 's':
                            print(f"  {Colors.YELLOW}Skipped.{Colors.END}\n")
                            skipped_count += 1
                            skipped_files.append(file)
                            skip_file = True
                            break
                        elif user_input.lower() == 'n' or not user_input:
                            prompt = f"\n  Type custom {Colors.BOLD}Artist - Title{Colors.END} name, or {Colors.YELLOW}'s'{Colors.END} to skip:\n  > "
                            custom_input = input(prompt).strip()
                            if custom_input.lower() == 's':
                                print(f"  {Colors.YELLOW}Skipped.{Colors.END}\n")
                                skipped_count += 1
                                skipped_files.append(file)
                                skip_file = True
                                break
                            elif custom_input.upper() == 'AUTO':
                                auto_mode = True
                                break
                            elif custom_input:
                                final_name = custom_input
                                is_manually_inputted = True
                                break
                            else:
                                print(f"  {Colors.YELLOW}Skipped.{Colors.END}\n")
                                skipped_count += 1
                                skipped_files.append(file)
                                skip_file = True
                                break
                        else:
                            final_name = f"{user_input} - {current_suggestion}"
                            is_manually_inputted = True
                            break
                    else:
                        prompt = f"\n  {Colors.BOLD}Accept predicted name?{Colors.END}\n  {Colors.CYAN}[ENTER]{Colors.END} to accept, type {Colors.GREEN}'f'{Colors.END} to flip Artist/Title, type a new {Colors.BOLD}Artist - Title{Colors.END}, {Colors.YELLOW}'s'{Colors.END} to skip, {Colors.YELLOW}'prev'{Colors.END} to redo previous, or {Colors.YELLOW}'AUTO'{Colors.END} to auto-process remaining:\n  > "
                        user_input = input(prompt).strip()
                        
                        if user_input.upper() == 'AUTO':
                            auto_mode = True
                            break
                        elif user_input.lower() == 'prev':
                            if idx > 1:
                                go_prev = True
                                forced_redo_indices.add(idx - 1)
                            else:
                                print(f"  {Colors.YELLOW}Already at the first file.{Colors.END}")
                            break
                        elif user_input.lower() == 's':
                            print(f"  {Colors.YELLOW}Skipped.{Colors.END}\n")
                            skipped_count += 1
                            skipped_files.append(file)
                            skip_file = True
                            break
                        elif user_input.lower() == 'f':
                            parts = current_suggestion.split(" - ", 1)
                            flipped_name = f"{parts[1]} - {parts[0]}"
                            current_suggestion = clean_youtube_title(flipped_name)
                            print(f"  {Colors.CYAN}Flipped Layout Prediction to:{Colors.END} {current_suggestion}")
                            continue
                        else:
                            if user_input:
                                final_name = user_input
                                is_manually_inputted = True
                            else:
                                final_name = current_suggestion
                                is_manually_inputted = False
                            break
                
                if auto_mode:
                    continue
                if go_prev:
                    idx -= 1
                    continue
                if skip_file:
                    idx += 1
                    continue
            
            if not is_manually_inputted:
                final_name = clean_youtube_title(final_name)
            if not final_name:
                print(f"  {Colors.RED}Invalid name. Skipped.{Colors.END}\n")
                skipped_count += 1
                skipped_files.append(file)
                idx += 1
                continue
                
            new_filename = f"{final_name}{suffix}"
            new_filepath = folder_path / new_filename
            
            renamed = False
            active_filepath = file
            
            if final_name != stem:
                if new_filepath.exists():
                    print(f"  {Colors.RED}Error: A file named '{new_filename}' already exists. Skipping rename.{Colors.END}\n")
                    skipped_count += 1
                    skipped_files.append(file)
                    idx += 1
                    continue
                try:
                    file.rename(new_filepath)
                    print(f"  {Colors.GREEN}Renamed to:{Colors.END} {new_filename}")
                    active_filepath = new_filepath
                    file_list[idx - 1] = new_filepath
                    renamed_count += 1
                    renamed = True
                except Exception as e:
                    print(f"  {Colors.RED}Rename failed: {e}{Colors.END}\n")
                    skipped_count += 1
                    skipped_files.append(file)
                    idx += 1
                    continue
            
            # If this file was recorded as skipped earlier in the pass (e.g. its rename
            # failed because of an illegal character in a manually entered name) but is
            # now being handled successfully - typically because the user went back to it
            # with 'prev' and gave it a valid name - drop it from the skipped list so it
            # is not presented again in the end-of-pass review of skipped files.
            while file in skipped_files:
                skipped_files.remove(file)
                skipped_count -= 1

            artist, title = None, None
            if " - " in final_name:
                parts = final_name.split(" - ", 1)
                artist = parts[0].strip()
                title = parts[1].strip()
                
            if artist and title:
                success = write_metadata_tags(active_filepath, artist, title)
                if success:
                    tagged_count += 1
                    tag_status = "Renamed & Tagged" if renamed else "Tagged"
                    print(f"  {Colors.GREEN}✔ {tag_status} successfully:{Colors.END} Artist='{artist}', Title='{title}'")
                else:
                    print(f"  {Colors.YELLOW}Renamed, but failed to write metadata tags.{Colors.END}")
            else:
                print(f"  {Colors.YELLOW}Could not parse 'Artist - Title' format. Skipping metadata tagging.{Colors.END}")
                
            print()
            idx += 1
            
        return skipped_files
    
    skipped_files = run_renaming_pass(files, is_manual_skipped_pass=False)
    
    if skipped_files:
        print(f"{Colors.DIM}─" * 60)
        print(f"\n{Colors.BOLD}Auto-mode / Renaming Pass Complete.{Colors.END}")
        print(f"There are {len(skipped_files)} files that were skipped or did not match the naming pattern.")
        try:
            choice = input(f"Do you want to manually go over the skipped ones? ({Colors.GREEN}y{Colors.END}/{Colors.RED}n{Colors.END}): ").strip().lower()
            if choice in ('y', 'yes'):
                skipped_count -= len(skipped_files)
                run_renaming_pass(skipped_files, is_manual_skipped_pass=True)
        except KeyboardInterrupt:
            print(f"\n\n{Colors.RED}Process interrupted by user. Exiting.{Colors.END}")
            sys.exit(0)
            
    return renamed_count, tagged_count, skipped_count, already_formatted_count

def check_ffmpeg_available():
    try:
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        subprocess.run([_ffmpeg_binary(), "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, check=True, startupinfo=startupinfo)
        return True
    except Exception:
        return False

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

# Playback reads ahead of the player. A stream URL takes a second or two to resolve
# with yt-dlp, and that time used to land between two tracks - the player sat on an
# empty media while the successor's URL was fetched, which looked like a skip or a
# laggy start. So the successor is resolved while the current track still has this
# many seconds left, on its own thread, and the resolved URL is held ready.
# PREFETCH_URL_MAX_AGE is the guard: a YouTube stream URL that has been sitting
# longer than that has expired and is resolved again.
PREFETCH_SECONDS_BEFORE_END = 30
PREFETCH_URL_MAX_AGE = 15 * 60  # seconds a prefetched stream URL is still trusted
PREFETCH_CACHE_LIMIT = 4        # resolved stream URLs held at most

# Keeping one track playing. A YouTube stream URL is a signed link with a lifetime rather
# than a file: partway through a long track - or after a track has been paused for an hour -
# it stops answering, and libVLC reports that as nothing useful. The media on the player
# either falls to vlc.State.Error or goes on claiming Playing with a position that has
# stopped moving, and in both cases scrubbing does nothing and Play does nothing, so the only
# way back was to pick the track again. STREAM_STALL_SECONDS is how long a reported position
# may stand still while the player claims Playing before the stream counts as dead; a dead
# stream the listener never asked to stop is re-resolved by itself, keeping its position, up
# to STREAM_REFETCH_LIMIT times per track. STREAM_URL_MAX_AGE is the backstop: a loaded URL
# that old is re-resolved the moment the user scrubs or presses Play, unless the player is
# measurably advancing on it - a stream that is working is left alone however old its URL is,
# and so is a stream that was only ever loaded and left sitting, which is the track the session
# restore preloads at start up. Age alone reloads a stream that has actually been heard and has
# then gone idle; reloading anything else is a restart rather than a recovery, and the two are
# told apart by _stream_listened.
# STREAM_END_SLACK_MS is how far short of its own reported length a media may "end" before
# that ending is read as a stream that gave up rather than a track that finished.
STREAM_STALL_SECONDS = 8
STREAM_URL_MAX_AGE = 30 * 60      # seconds the URL on the player may be before a scrub or Play re-resolves it
STREAM_REFETCH_LIMIT = 3          # self-healing re-resolutions per track before the player says so and waits
STREAM_RENEW_COOLDOWN = 10        # seconds between two re-resolutions of the same track
STREAM_END_SLACK_MS = 15000       # a stream that ended this far short of its length did not finish
STREAM_SEEK_RESTORE_TIMEOUT = 12  # seconds a scrub or a restored position stays queued for fresh media

# "Stop after current", cycled one state per click: off -> once -> always -> off.
STOP_AFTER_OFF = 0     # playback advances to the next track when one ends, as it always did
STOP_AFTER_ONCE = 1    # stop when the current track ends, then the state returns to off
STOP_AFTER_ALWAYS = 2  # stop after every track until the button is clicked again
STOP_AFTER_STATE_NAMES = {STOP_AFTER_OFF: "off", STOP_AFTER_ONCE: "once", STOP_AFTER_ALWAYS: "always"}
STOP_AFTER_LABELS = {STOP_AFTER_OFF: "Off", STOP_AFTER_ONCE: "Once", STOP_AFTER_ALWAYS: "Always"}
STOP_AFTER_TOOLTIPS = {
    STOP_AFTER_OFF: "Stop After Current: Off - playback advances to the next track.\n"
                    "Click once: stop after this track.",
    STOP_AFTER_ONCE: "Stop After Current: Once - this track is the last one, then the button returns to Off.\n"
                     "Click again: keep stopping after every track.",
    STOP_AFTER_ALWAYS: "Stop After Current: Always - every track stops when it ends.\n"
                       "Click once: turn it off.",
}

_ytdlp_exe_cache = None
_ytdlp_exe_cache_lock = threading.Lock()


class YtDlpMissingError(RuntimeError):
    """Raised when yt-dlp is needed but no yt-dlp exists on this system."""


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
            base_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(base_dir, "yt-dlp.exe"))
    except Exception:
        pass
    return candidates


def find_yt_dlp_executable(refresh=False):
    """Path of the yt-dlp to use, or None. Resolved once and cached."""
    global _ytdlp_exe_cache
    with _ytdlp_exe_cache_lock:
        cached = _ytdlp_exe_cache
        if cached and not refresh and os.path.isfile(cached):
            return cached
        found = None
        for candidate in _yt_dlp_lookup_paths():
            if candidate and os.path.isfile(candidate):
                found = candidate
                break
        if not found:
            for name in ("yt-dlp", "yt-dlp.exe"):
                candidate = shutil.which(name)
                if candidate:
                    found = candidate
                    break
        _ytdlp_exe_cache = found
        return found


def get_yt_dlp_version(exe_path=None):
    """The version yt-dlp reports (e.g. '2026.08.19'), or '' when unavailable."""
    exe = exe_path or find_yt_dlp_executable()
    if not exe:
        return ""
    try:
        result = subprocess.run([exe, "--version"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, encoding="utf-8", errors="replace",
                                timeout=30, env=_child_utf8_env(), **_hidden_window_kwargs())
        text = (result.stdout or "").strip()
        return text.splitlines()[0] if text else ""
    except Exception:
        return ""

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


def run_yt_dlp_json(args, timeout=YTDLP_EXTRACT_TIMEOUT):
    """Run yt-dlp with -J and return the info dictionary it prints."""
    exe = find_yt_dlp_executable()
    if not exe:
        raise YtDlpMissingError("yt-dlp is not installed on this system")
    result = subprocess.run([exe] + list(args), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, encoding="utf-8", errors="replace",
                            timeout=timeout, env=_child_utf8_env(), **_hidden_window_kwargs())
    if result.returncode != 0:
        tail = [line for line in (result.stderr or "").splitlines() if line.strip()]
        raise RuntimeError(tail[-1] if tail else f"yt-dlp exited with code {result.returncode}")
    return json.loads(result.stdout or "")


def stream_cli_args():
    """The yt-dlp arguments that turn one video id into a playable stream URL.

    Shared by the play path and by the prefetch thread so the two never resolve a
    track differently - the prefetched URL is the URL the player would have found.
    """
    cli_args = [
        "-J",
        "--format", "bestaudio/best",
        "--extractor-args", "youtube:player_client=android",
        "--no-playlist",
    ]
    if getattr(sys, 'frozen', False):
        cli_args.extend(["--ffmpeg-location", getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))])
    return cli_args


def resolve_stream_url(vid_id):
    """(stream url, user agent) for a video id, or raises when there is no stream."""
    info = run_yt_dlp_json(stream_cli_args() + [f"https://www.youtube.com/watch?v={vid_id}"])
    url = info.get('url') if info else None
    if not url and info and 'formats' in info:
        for f in reversed(info['formats']):
            if f.get('url') and (f.get('acodec') != 'none' or f.get('vcodec') == 'none'):
                url = f['url']
                break
        if not url and info['formats']:
            url = info['formats'][-1].get('url')
    if not url:
        raise RuntimeError("No playable audio stream URL found")
    headers = info.get('http_headers', {}) if info else {}
    user_agent = headers.get('User-Agent', 'com.google.android.youtube/19.29.37 (Linux; U; Android 11)')
    return url, user_agent


# The lines yt-dlp prints when it names the file it ended up with. Which of
# them appear, and whether the path is wrapped in quotes, depends on the
# yt-dlp version and on whether the audio needed converting: the "no conversion
# needed" message is quoted in some releases and bare in others, and newer
# releases dropped its [ExtractAudio] prefix. Every form is matched here and
# the quotes are taken off afterwards. Getting this wrong looked exactly like a
# song being skipped - the file was on disk, the GUI could not match it, and
# the track was quietly queued up again for the next pass.
_YTDLP_FINAL_PATH_PATTERNS = [
    re.compile(r'^\[ExtractAudio\] Destination:\s*(.+)$'),
    re.compile(r'^\[ExtractAudio\] Not converting audio\s+"(.+?)"\s*;'),
    re.compile(r'^Not converting audio\s+"(.+?)"\s*;'),
    re.compile(r'^\[ExtractAudio\] Not converting audio\s+(.+?);\s'),
    re.compile(r'^Not converting audio\s+(.+?);\s'),
    re.compile(r'^\[Merger\] Merging formats into "(.+?)"$'),
    re.compile(r'^\[download\] "(.+?)" has already been downloaded$'),
    re.compile(r'^\[download\] (.+?) has already been downloaded$'),
]
_YTDLP_STAGED_PATH_PATTERNS = [
    re.compile(r'^\[download\] Destination:\s*(.+)$'),
]


def _clean_reported_path(text):
    """Take off the quotes yt-dlp wraps around some of the paths it prints."""
    text = (text or '').strip()
    while len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1].strip()
    return text


def _match_reported_path(line):
    """('final'|'staged', path) for a yt-dlp line naming a file, else (None, '')."""
    for pattern in _YTDLP_FINAL_PATH_PATTERNS:
        match = pattern.match(line)
        if match:
            return 'final', _clean_reported_path(match.group(1))
    for pattern in _YTDLP_STAGED_PATH_PATTERNS:
        match = pattern.match(line)
        if match:
            return 'staged', _clean_reported_path(match.group(1))
    return None, ''


def _title_match_key(text):
    """A loose key for matching a queue title against the file it produced.

    yt-dlp rewrites every character a Windows filename cannot hold, so a title
    with a ':' or a '/' in it never matches the file it was downloaded to.
    Comparing only the letters and digits ignores those rewrites.
    """
    return re.sub(r'[^0-9a-z]+', '', (text or '').lower())


def _title_matches_filename(title, filename):
    """True when 'filename' is the file a download of 'title' would have written."""
    wanted = _title_match_key(title)
    on_disk = _title_match_key(os.path.splitext(os.path.basename(filename))[0])
    if not wanted or not on_disk:
        return False
    if wanted == on_disk:
        return True
    # yt-dlp shortens titles past its own filename limit, so a long enough
    # prefix of the right shape still counts.
    shorter, longer = (wanted, on_disk) if len(wanted) < len(on_disk) else (on_disk, wanted)
    return len(shorter) >= 12 and longer.startswith(shorter)


def run_yt_dlp_download(args, progress_cb=None, cancelled_cb=None):
    """Run a real yt-dlp download and report its progress while it runs.

    Returns the path of the finished file. Returning None does NOT mean the
    download failed - it means yt-dlp finished without naming a file this
    version recognises, and the caller has to look the file up itself.
    Raises when yt-dlp is missing, when the download failed, or when the user
    cancelled - the same contract the old progress hooks had.
    """
    exe = find_yt_dlp_executable()
    if not exe:
        raise YtDlpMissingError("yt-dlp is not installed on this system")
    # stderr is folded into stdout: two pipes would let ffmpeg's chatter fill a
    # full buffer and stall the download.
    proc = subprocess.Popen([exe] + list(args), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
                            bufsize=1, env=_child_utf8_env(), **_hidden_window_kwargs())
    final_path = None
    staged_path = None
    errors = []
    cancelled = False
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        kind, reported = _match_reported_path(line)
        if kind == 'final':
            final_path = reported
        elif kind == 'staged':
            staged_path = reported
        elif line.startswith("[download]"):
            match = re.search(r"\[download\]\s+([0-9.]+%|N/A)", line)
            if match and progress_cb:
                progress_cb(match.group(1))
        elif line.startswith("ERROR:"):
            errors.append(line)
        if cancelled_cb and cancelled_cb():
            cancelled = True
            proc.kill()
            break
    try:
        proc.stdout.close()
    except Exception:
        pass
    try:
        proc.wait(timeout=30)
    except Exception:
        pass
    if cancelled:
        raise RuntimeError("Download cancelled by user")
    if proc.returncode != 0:
        raise RuntimeError(errors[-1] if errors else f"yt-dlp exited with code {proc.returncode}")
    # Return whichever path is really there: the converted file when there is
    # one, the plain download when the conversion message was never printed.
    # A half-parsed path is worse than no path at all.
    for candidate in (final_path, staged_path):
        if candidate and os.path.isfile(candidate):
            return candidate
    return final_path or staged_path


# A single track gets a few tries of its own before it is handed back to the
# queue-wide re-check. Retrying one track is far cheaper than re-running the
# whole queue, and the short waits between tries are what let a throttled
# request recover. The queue-wide passes stay on top of this as the safety net.
DOWNLOAD_ITEM_ATTEMPTS = 3

# yt-dlp complaints another request cannot fix, so they are not retried.
_PERMANENT_DOWNLOAD_ERROR_MARKERS = (
    "video unavailable",
    "private video",
    "this video is not available",
    "unsupported url",
    "is not a valid url",
    "requested format is not available",
)


def _is_permanent_download_error(message):
    """True for a failure that a retry could never turn into a download."""
    text = (message or '').lower()
    return any(marker in text for marker in _PERMANENT_DOWNLOAD_ERROR_MARKERS)


def check_vlc_available():
    if not _VLC_MODULE_AVAILABLE or vlc is None:
        return False, getattr(sys.modules[__name__], '_VLC_IMPORT_ERROR', 'python-vlc not available')
    try:
        instance = vlc.Instance('--quiet', '--no-video')
        if instance is None:
            return False, "libvlc.dll not found. Please install VLC Media Player."
        player = instance.media_player_new()
        if player is None:
            return False, "Failed to create VLC media player instance."
        return True, "OK"
    except Exception as e:
        return False, str(e)


def measure_loudness(filepath):
    command = [
        _ffmpeg_binary(),
        "-nostdin",
        "-y",
        "-i", str(filepath),
        "-af", f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:print_format=json",
        "-f", "null",
        "-"
    ]
    try:
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='ignore',
            startupinfo=startupinfo
        )
        if result.returncode != 0:
            return None, None, f"FFmpeg exited with code {result.returncode}"
            
        stderr_output = result.stderr
        json_match = re.search(r'\{\s*"input_i".*?\}', stderr_output, re.DOTALL)
        if json_match:
            import json
            data = json.loads(json_match.group(0))
            input_i = float(data.get("input_i", TARGET_LUFS))
            input_tp = float(data.get("input_tp", TRUE_PEAK))
            return input_i, input_tp, None
        else:
            return None, None, "Could not find loudnorm JSON block in FFmpeg output"
    except Exception as e:
        return None, None, str(e)

def _ffprobe_binary():
    """The ffprobe to run: the one bundled with the frozen exe when this program is
    packaged, otherwise whatever is on PATH."""
    if getattr(sys, 'frozen', False):
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        bundled = os.path.join(base_dir, 'ffprobe.exe')
        if os.path.exists(bundled):
            return bundled
    return 'ffprobe'


def _ffmpeg_binary():
    """The ffmpeg to run: the one bundled with the frozen exe when this program is
    packaged, otherwise whatever is on PATH. yt-dlp is already pointed at that copy
    with --ffmpeg-location, but the loudness and silence-trim passes call ffmpeg
    directly and had no equivalent, so a packaged build that carries ffmpeg.exe and
    does not have it on PATH reported ffmpeg as unavailable and never normalized or
    trimmed anything."""
    if getattr(sys, 'frozen', False):
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        bundled = os.path.join(base_dir, 'ffmpeg.exe')
        if os.path.exists(bundled):
            return bundled
    return 'ffmpeg'


def _probe_format_block(filepath):
    """Run ffprobe over one file and return the "format" block of its JSON output,
    or None when ffprobe could not read it.

    '-nostdin' is deliberately not used: this build of ffprobe treats it as an option
    that takes a value, so every call that had it failed with "Failed to set value
    '-v' for option 'nostdin'" and no duration was ever returned. Closing stdin with
    DEVNULL, as this does, is what that switch was for."""
    try:
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        cmd = [_ffprobe_binary(), "-v", "quiet", "-print_format", "json", "-show_format", str(filepath)]
        result = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding='utf-8', errors='ignore',
                                startupinfo=startupinfo)
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            return data.get('format') or None
    except Exception:
        pass
    return None


def _get_audio_duration(filepath):
    """Return duration in seconds via ffprobe, or None on failure."""
    fmt = _probe_format_block(filepath)
    if not fmt:
        return None
    try:
        return float(fmt.get('duration'))
    except (TypeError, ValueError):
        return None

def _silence_trim_filters():
    """
    The built-in silence-trim filters, exactly as they have always been built:
    one pass for the front of the track, then the same filter over a reversed
    stream so the trailing silence is trimmed too, then reversed back.
    """
    single = (
        f"silenceremove=start_periods=1:start_duration={SILENCE_DURATION}:"
        f"start_threshold={SILENCE_THRESHOLD}:start_silence={SILENCE_KEEP}:stop_silence={SILENCE_KEEP}"
    )
    return f"{single},areverse,{single},areverse"


def build_af_chain(loudnorm_filter=None, include_silence_trim=None, include_pad=True):
    """
    Assemble the ffmpeg -af chain from its three independent parts:

      1. silence trim    - _silence_trim_filters(), gated by the SILENCE_TRIM setting
      2. loudnorm        - the built-in whole-track gain, or the loudnorm/EQ override
      3. end-of-file pad - apad, gated by SILENCE_PAD_DUR

    A loudnorm override only replaces part 2. Silence trimming is never overridden
    by it, and turning silence trimming off never touches the loudnorm part.
    """
    trim_on = SILENCE_TRIM if include_silence_trim is None else include_silence_trim
    parts = []
    if trim_on:
        parts.append(_silence_trim_filters())
    if loudnorm_filter:
        parts.append(loudnorm_filter)
    if include_pad and SILENCE_PAD_DUR > 0:
        parts.append(f"apad=pad_dur={SILENCE_PAD_DUR}")
    return ",".join(parts)


def normalize_file(index, total, filepath, custom_norm_cmd=None):
    suffix = filepath.suffix.lower()
    artist, title = read_metadata_tags(filepath)

    # Measure original duration before processing
    orig_duration = _get_audio_duration(filepath)
    
    input_i, input_tp, err = measure_loudness(filepath)
    if err:
        return False, filepath.name, f"Loudness measurement failed: {err}"
        
    target_lufs = float(TARGET_LUFS)
    true_peak_limit = float(TRUE_PEAK)
    
    gain = target_lufs - input_i
    max_gain = true_peak_limit - input_tp
    final_gain = min(gain, max_gain)
    
    limit_str = " (Peak Limited)" if final_gain < gain else ""
    _effective_norm_cmd = (custom_norm_cmd or CUSTOM_NORM_CMD or "").strip()
    gain_line = (
        f"  └─ Loudnorm/EQ override: {_effective_norm_cmd}" if _effective_norm_cmd
        else f"  └─ Applying Whole-Track Gain: {final_gain:+.2f} dB{limit_str} (Target: {target_lufs} LUFS)"
    )
    _safe_print(
        f"[{index}/{total}] {Colors.CYAN}Processing:{Colors.END} {filepath.name}...\n"
        f"  ├─ Measured: {input_i:+.2f} LUFS | True Peak: {input_tp:+.2f} dB\n"
        f"{gain_line}"
    )
    
    try:
        temp_fd, temp_path = tempfile.mkstemp(suffix=suffix)
        os.close(temp_fd)
    except Exception as e:
        return False, filepath.name, f"Failed to create temp file: {e}"
        
    # The three parts of the chain are independent: silence trimming, the loudnorm
    # filter and the end-of-file pad. A loudnorm override replaces ONLY the loudnorm
    # filter and can never replace the silence trimming command.
    loudnorm_filter = _effective_norm_cmd or f"volume={final_gain:.2f}dB"
    af_chain = build_af_chain(loudnorm_filter)

    command = [_ffmpeg_binary(), "-nostdin", "-y", "-i", str(filepath), "-af", af_chain]
    
    if suffix == ".mp3":
        command += ["-codec:a", "libmp3lame", "-b:a", BITRATE]
    elif suffix == ".m4a":
        command += ["-codec:a", "aac", "-b:a", BITRATE]
    else:
        command += ["-b:a", BITRATE]
        
    command += ["-map_metadata", "0"]
    if suffix == ".m4a":
        command += ["-movflags", "+faststart"]
        
    command.append(temp_path)
    
    try:
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            startupinfo=startupinfo
        )
    except Exception as e:
        try: os.remove(temp_path)
        except: pass
        return False, filepath.name, f"FFmpeg execution failed: {e}"
        
    if result.returncode != 0:
        try: os.remove(temp_path)
        except: pass
        return False, filepath.name, result.stderr
        
    try:
        os.replace(temp_path, str(filepath))
    except Exception as e:
        return False, filepath.name, f"Failed to replace original file with temp: {e}"
    
    # Report silence removal stats (only meaningful when the trim filters ran)
    new_duration = _get_audio_duration(filepath)
    if SILENCE_TRIM and orig_duration is not None and new_duration is not None:
        total_removed = orig_duration - new_duration
        pad_added = SILENCE_PAD_DUR if SILENCE_PAD_DUR > 0 else 0.0
        net_removed = total_removed + pad_added  # silence removed before pad was added
        front_est = net_removed / 2.0
        back_est = net_removed / 2.0
        _safe_print(
            f"  {Colors.DIM}├─ Original duration: {orig_duration:.2f}s  →  New: {new_duration:.2f}s{Colors.END}\n"
            f"  {Colors.DIM}└─ Silence removed: ~{front_est:.2f}s front, ~{back_est:.2f}s back (total: {net_removed:.2f}s){Colors.END}"
        )
        
    if (artist or title):
        write_metadata_tags(filepath, artist, title)
        
    return True, filepath.name, None


def run_loudness_normalization(folder_path, skip_files=None):
    print(f"\n{Colors.CYAN}{Colors.BOLD}========================================{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}=== TWO-PASS VOLUME ADJUSTMENT PASS ===={Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}========================================{Colors.END}\n")
    
    if not check_ffmpeg_available():
        print(f"{Colors.YELLOW}[!] FFmpeg was not found in your system's PATH.{Colors.END}")
        print(f"{Colors.DIM}    Loudness normalization requires FFmpeg to process files.{Colors.END}")
        print(f"{Colors.DIM}    Skipping volume adjustment pass.{Colors.END}\n")
        return 0, 0
        
    extensions = TAGGABLE_EXTENSIONS
    files = sorted([f for f in folder_path.iterdir() if f.is_file() and f.suffix.lower() in extensions])

    # Filter out files that were already tagged before the renaming pass started
    if skip_files:
        pre_skip_count = len([f for f in files if f in skip_files])
        files = [f for f in files if f not in skip_files]
        if pre_skip_count:
            print(f"{Colors.DIM}Skipping {pre_skip_count} already-tagged file(s) from normalization.{Colors.END}")

    if not files:
        print(f"{Colors.YELLOW}No MP3 or M4A files found to adjust.{Colors.END}\n")
        return 0, 0
        
    print(f"{Colors.GREEN}Starting static volume adjustment on {len(files)} files with {MAX_WORKERS} worker threads...{Colors.END}")
    print(f"{Colors.DIM}Settings: Target Loudness={TARGET_LUFS} LUFS | Max Peak={TRUE_PEAK} dB | Output Bitrate={BITRATE}{Colors.END}")
    print(f"{Colors.DIM}Silence trim: {'ON' if SILENCE_TRIM else 'OFF'} | End pad: {SILENCE_PAD_DUR}s | Loudnorm: {CUSTOM_NORM_CMD or 'built-in whole-track gain'}{Colors.END}\n")
    
    completed = 0
    failed = 0
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for idx, file in enumerate(files, 1):
            futures.append(executor.submit(normalize_file, idx, len(files), file))
            
        for future in as_completed(futures):
            success, filename, error = future.result()
            if success:
                completed += 1
                _safe_print(f"  {Colors.GREEN}✔ Adjusted Volume:{Colors.END} {filename}\n")
            else:
                failed += 1
                _safe_print(f"\n  {Colors.RED}✘ Failed to adjust volume {filename}:{Colors.END}")
                _safe_print(f"{Colors.DIM}{error}{Colors.END}\n")
                
    print(f"\n{Colors.CYAN}{Colors.BOLD}Volume Adjustment Complete!{Colors.END}")
    print(f"  {Colors.GREEN}Success: {completed}{Colors.END} | {Colors.RED}Failed: {failed}{Colors.END}\n")
    return completed, failed

def trim_silence_file(index, total, filepath):
    _safe_print(f"[{index}/{total}] {Colors.CYAN}Trimming silence:{Colors.END} {filepath.name}...")
    suffix = filepath.suffix.lower()
    artist, title = read_metadata_tags(filepath)

    try:
        temp_fd, temp_path = tempfile.mkstemp(suffix=suffix)
        os.close(temp_fd)
    except Exception as e:
        return False, filepath.name, f"Failed to create temp file: {e}"
    
    # Silence trimming only. The loudnorm/EQ override is never applied to this pass.
    af_chain = build_af_chain(include_pad=False)
    command = [_ffmpeg_binary(), "-nostdin", "-y", "-i", str(filepath), "-af", af_chain]
    
    if suffix == ".mp3":
        command += ["-codec:a", "libmp3lame", "-b:a", BITRATE]
    elif suffix == ".m4a":
        command += ["-codec:a", "aac", "-b:a", BITRATE]
    else:
        command += ["-b:a", BITRATE]
    
    command += ["-map_metadata", "0"]
    if suffix == ".m4a":
        command += ["-movflags", "+faststart"]
    command.append(temp_path)
    
    try:
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            startupinfo=startupinfo
        )
    except Exception as e:
        try: os.remove(temp_path)
        except: pass
        return False, filepath.name, f"FFmpeg execution failed: {e}"
    
    if result.returncode != 0:
        try: os.remove(temp_path)
        except: pass
        return False, filepath.name, result.stderr
    
    try:
        os.replace(temp_path, str(filepath))
    except Exception as e:
        return False, filepath.name, f"Failed to replace original file with temp: {e}"
    
    if (artist or title):
        write_metadata_tags(filepath, artist or "", title or "")
    
    return True, filepath.name, None

def run_silence_trim(folder_path, skip_files=None):
    print(f"\n{Colors.CYAN}{Colors.BOLD}====================================={Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}=== SILENCE TRIM PASS ==============={Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}====================================={Colors.END}\n")
    
    if not SILENCE_TRIM:
        print(f"{Colors.YELLOW}[!] Silence trimming is disabled in settings.{Colors.END}")
        print(f"{Colors.DIM}    Skipping silence trim pass.{Colors.END}\n")
        return 0, 0

    if not check_ffmpeg_available():
        print(f"{Colors.YELLOW}[!] FFmpeg was not found in your system's PATH.{Colors.END}")
        print(f"{Colors.DIM}    Skipping silence trim pass.{Colors.END}\n")
        return 0, 0
    
    extensions = TAGGABLE_EXTENSIONS
    files = sorted([f for f in folder_path.iterdir() if f.is_file() and f.suffix.lower() in extensions])

    # Filter out files that were already tagged before the renaming pass started
    if skip_files:
        pre_skip_count = len([f for f in files if f in skip_files])
        files = [f for f in files if f not in skip_files]
        if pre_skip_count:
            print(f"{Colors.DIM}Skipping {pre_skip_count} already-tagged file(s) from silence trim.{Colors.END}")

    if not files:
        print(f"{Colors.YELLOW}No MP3 or M4A files found to trim.{Colors.END}\n")
        return 0, 0

    print(f"{Colors.GREEN}Trimming silence on {len(files)} files with {MAX_WORKERS} worker threads...{Colors.END}")
    print(f"{Colors.DIM}Threshold: {SILENCE_THRESHOLD} | Min silence duration: {SILENCE_DURATION}s | Silence kept: {SILENCE_KEEP}s{Colors.END}\n")
    
    completed = 0
    failed = 0
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(trim_silence_file, idx, len(files), file)
                   for idx, file in enumerate(files, 1)]
        for future in as_completed(futures):
            success, filename, error = future.result()
            if success:
                completed += 1
                _safe_print(f"  {Colors.GREEN}✔ Trimmed:{Colors.END} {filename}")
            else:
                failed += 1
                _safe_print(f"\n  {Colors.RED}✘ Failed to trim {filename}:{Colors.END}")
                _safe_print(f"{Colors.DIM}{error}{Colors.END}\n")
    
    print(f"\n{Colors.CYAN}{Colors.BOLD}Silence Trim Complete!{Colors.END}")
    print(f"  {Colors.GREEN}Success: {completed}{Colors.END} | {Colors.RED}Failed: {failed}{Colors.END}\n")
    return completed, failed

def run_integrated_renamer_cli():
    if sys.platform == "win32":
        os.system("")
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            hStdin = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(hStdin, ctypes.byref(mode)):
                new_mode = (mode.value & ~0x0040) | 0x0080  # Disable ENABLE_QUICK_EDIT_MODE, set ENABLE_EXTENDED_FLAGS
                kernel32.SetConsoleMode(hStdin, new_mode)
        except Exception:
            pass
        
    import argparse
    parser = argparse.ArgumentParser(description="Integrated MP3 Renamer 5000", add_help=False)
    parser.add_argument('folder', nargs='?', default=None,
                        help="Target folder path. If omitted or invalid, a prompt will appear.")
    parser.add_argument('--norm', choices=['on', 'off', 'ask'], default='ask',
                        help="Normalization: on=always run, off=always skip, ask=prompt (default)")
    parser.add_argument('--auto', action='store_true',
                        help="Auto-accept all rename predictions without user prompts")
    parser.add_argument('--silence-pad', type=float, default=None,
                        help="Seconds of silence to append at end of each normalized file")
    parser.add_argument('--norm-threads', type=int, default=None,
                        help="Worker threads for normalization pass")
    parser.add_argument('--silence-trim', choices=['on', 'off'], default='on',
                        help="Silence trimming: on=trim front and back (default), off=leave silence alone")
    parser.add_argument('--custom-norm-cmd', default=None,
                        help="Replace ONLY the loudnorm part of the ffmpeg -af chain (silence trim unaffected)")
    args, _ = parser.parse_known_args()

    global SILENCE_PAD_DUR, SILENCE_TRIM, MAX_WORKERS, CUSTOM_NORM_CMD
    if args.silence_pad is not None:
        SILENCE_PAD_DUR = args.silence_pad
    SILENCE_TRIM = (args.silence_trim == 'on')
    if args.custom_norm_cmd:
        CUSTOM_NORM_CMD = args.custom_norm_cmd
    if args.norm_threads is not None and args.norm_threads > 0:
        MAX_WORKERS = args.norm_threads

    norm_mode = args.norm
    start_auto = args.auto

    _print_renamer_banner()

    if args.folder and Path(args.folder).is_dir():
        folder = Path(args.folder)
        print(f"{Colors.GREEN}[✓] Using folder: {folder}{Colors.END}\n")
    else:
        folder = _select_renamer_folder()

    # Snapshot which files already have both artist+title tags BEFORE renaming writes new tags
    _ext = TAGGABLE_EXTENSIONS
    _pre_tagged = frozenset(
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in _ext
        and all(read_metadata_tags(f))
    )
    if _pre_tagged:
        print(f"{Colors.DIM}Found {len(_pre_tagged)} already-tagged file(s) — will skip them in normalization/trim.{Colors.END}\n")

    renamed_count, tagged_count, skipped_count, already_formatted_count = clean_and_tag_files(folder, start_auto=start_auto)

    norm_completed, norm_failed = 0, 0
    trim_completed, trim_failed = 0, 0

    try:
        if norm_mode == 'on':
            norm_completed, norm_failed = run_loudness_normalization(folder, skip_files=_pre_tagged)
        elif norm_mode == 'off':
            print(f"\n{Colors.YELLOW}Skipping volume adjustment (disabled in settings).{Colors.END}\n")
        else:
            print(f"{Colors.BOLD}Normalization and Silence Trimming{Colors.END}")
            choice = input(f"Do you want to run normalization and silence trimming? ({Colors.GREEN}y{Colors.END}/{Colors.RED}n{Colors.END}): ").strip().lower()
            if choice in ('y', 'yes'):
                norm_completed, norm_failed = run_loudness_normalization(folder, skip_files=_pre_tagged)
            else:
                print(f"\n{Colors.YELLOW}Skipping normalization and silence trim pass.{Colors.END}\n")
    except KeyboardInterrupt:
        print(f"\n\n{Colors.RED}Process interrupted by user. Exiting.{Colors.END}")
        sys.exit(0)

    print(f"\n{Colors.CYAN}{Colors.BOLD}{'═' * 50}{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}  SESSION SUMMARY{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'═' * 50}{Colors.END}")
    print(f"  {Colors.GREEN}Already formatted / skipped:{Colors.END} {already_formatted_count}")
    print(f"  {Colors.GREEN}Renamed:                    {Colors.END} {renamed_count}")
    print(f"  {Colors.GREEN}Tagged:                     {Colors.END} {tagged_count}")
    print(f"  {Colors.YELLOW}Skipped (user / no artist): {Colors.END} {skipped_count}")
    if norm_completed or norm_failed:
        print(f"  {Colors.GREEN}Volume-equalized:           {Colors.END} {norm_completed}  "
              f"{Colors.RED}(failed: {norm_failed}){Colors.END}")
    if trim_completed or trim_failed:
        print(f"  {Colors.GREEN}Silence-trimmed:            {Colors.END} {trim_completed}  "
              f"{Colors.RED}(failed: {trim_failed}){Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'═' * 50}{Colors.END}")
    print(f"\n{Colors.CYAN}{Colors.BOLD}All processes complete.{Colors.END}")

    try:
        input(f"\n{Colors.DIM}Press ENTER to exit...{Colors.END}")
    except (KeyboardInterrupt, EOFError):
        pass

# ============================================================
# Theme Mapping for custom colors
THEME_COLORS = {
    "Blue": ("#3B8ED0", "#1F6AA5"),
    "Green": ("#1abd33", "#148024"),
    "Red": ("#E31E24", "#C42B1C"),
    "Purple": ("#9146FF", "#6441A5"),
    "Pink": ("#FF4B8B", "#D12D69"),
    "Yellow": ("#FFD700", "#FFC800"),
    "Orange": ("#FF8C00", "#FF7B00"),
    "Grey": ("#808080", "#555555"),
    "White": ("#FFFFFF", "#E5E5E5")
}

# The formats the Format dropdown offers, and therefore the formats a download can
# be saved as. The rule for this list is strict: a format is only allowed if the
# tagger can write artist/title into it and read them back, because the player gets
# everything it displays out of those two tags. Three formats used to be on this
# list and are off it on purpose, each verified against mutagen:
#   .aac  - a raw ADTS bitstream with no tag container of any kind.
#   .wav  - RIFF/PCM. mutagen opens it but gives it no tag API at all, so the
#           tagger has nowhere to put an artist or a title.
#   .flac - taggable, but only through Vorbis comments, which is a different tag
#           system from the ID3/MP4 path this tagger uses.
# All three are still in AUDIO_EXTENSIONS below, so a file someone already downloaded
# in one of them stays visible and playable - it can just no longer be produced. The
# two that are left are the two the whole pipeline actually supports: MP3 (ID3v2) and
# M4A (MP4 atoms). M4A is the same AAC codec, so no codec was ever lost, only the
# containers that could not carry a tag.
DOWNLOAD_FORMATS = ("mp3", "m4a")
DEFAULT_DOWNLOAD_FORMAT = "mp3"

# The same list as file suffixes, for the passes that walk a folder. Derived from
# DOWNLOAD_FORMATS so that a format cannot be offered in the dropdown without also
# being handled by the rename/tag/normalize/silence-trim passes, which is how aac,
# flac and wav ended up downloadable-but-never-taggable in the first place.
TAGGABLE_EXTENSIONS = {f".{fmt}" for fmt in DOWNLOAD_FORMATS}

# Audio extensions the local file browser and the sync scan accept. This is wider
# than DOWNLOAD_FORMATS on purpose: it also covers files that are already sitting in
# someone's library, including .aac files downloaded by older versions of the app,
# which should stay visible and playable even though they can no longer be produced.
AUDIO_EXTENSIONS = {'.mp3', '.flac', '.wav', '.m4a', '.ogg', '.opus', '.aac', '.wma', '.mka', '.aiff', '.alac', '.ape', '.wv'}

# The containers mutagen can read artist/title out of, measured against mutagen 1.48.1.
# Everything else on AUDIO_EXTENSIONS is outside this set for a reason: .aac is a raw
# ADTS bitstream with no tag container, .wav and .aiff open fine but mutagen gives them
# no tag API, and .mka and .ape are formats mutagen will not open at all. Those keep
# going to ffprobe for their tags, exactly as they did before.
MUTAGEN_TAGGABLE_EXTENSIONS = {'.mp3', '.m4a', '.alac', '.flac', '.ogg', '.opus', '.wma', '.wv'}

# Duration and tags for the local file list, cached for the whole session under a key
# that describes what the file IS - (path, mtime_ns, size) - rather than what it is
# called. A file that is edited, re-downloaded or replaced simply misses, and the
# entries nobody is looking at any more are dropped once the cache reaches its cap.
_LOCAL_META_CACHE_CAP = 6000
_local_meta_cache = {}

# The rows of a folder are filled in chunks, and every chunk hands the event loop back a
# chance to lay the new rows out and paint them. The first chunk is deliberately about
# what fits in the pane, because those are the rows the user switched folders to look at:
# a folder of thirty files is filled by that chunk alone, and a folder of a thousand is
# on screen and readable while the rest of it is still arriving.
LOCAL_RENDER_FIRST_CHUNK_ROWS = 32

# How tall a row is assumed to be until the pane has measured its own, which is what
# decides how many rows a screenful is.
LOCAL_RENDER_ROW_HEIGHT_GUESS = 24.0

# After the first chunk the size is worked out from what a row actually costs this machine -
# building it, laying it out and painting it - so that a chunk is as big as it can be and still
# keep the GUI thread away for no more than about a frame. A fast machine fills a thousand files
# in a few larger chunks, a slow one in many smaller ones, and neither stops answering the user.
LOCAL_RENDER_CHUNK_MIN_ROWS = 32
LOCAL_RENDER_CHUNK_MAX_ROWS = 1024
LOCAL_RENDER_CHUNK_BUDGET_S = 0.020

# The pane is handed the height the finished folder is going to occupy as soon as its listing is
# known, and it keeps that height until the fill is done. A row that has already been drawn is
# therefore never moved while the rest of the folder is being built: the folder appears at the
# size it is going to be, its scrollbar is right from the first frame, and every chunk after the
# first lands in room that is already reserved instead of stretching the list under the user and
# forcing everything already on screen to be laid out and painted over again. Chunked filling
# without it is what makes a big folder look like it is inflating rather than arriving.


def _format_audio_duration(seconds):
    """The duration text a local row shows: H:MM:SS at an hour or more, M:SS under it."""
    try:
        d = float(seconds)
    except (TypeError, ValueError):
        return ""
    if d <= 0:
        return ""
    if d >= 3600:
        return f"{int(d // 3600)}:{int((d % 3600) // 60):02d}:{int(d % 60):02d}"
    return f"{int(d // 60)}:{int(d % 60):02d}"


def _local_display_name(filename, title, artist):
    """The name a local row shows when "Show artist/title" is switched on: "Artist -
    Title", the title on its own when there is no artist, and the filename when the
    file is not tagged."""
    if title:
        return f"{artist} - {title}" if artist else title
    return filename


def _local_meta_cache_put(key, title, artist, duration, tags_resolved):
    """Remember what was read for one file. Insertion order is the age order, so
    trimming drops the oldest half rather than a random half."""
    if len(_local_meta_cache) >= _LOCAL_META_CACHE_CAP:
        for stale in list(_local_meta_cache)[:_LOCAL_META_CACHE_CAP // 2]:
            del _local_meta_cache[stale]
    _local_meta_cache[key] = (title, artist, duration, tags_resolved)


def _read_local_audio_meta(path):
    """Duration, and artist/title when the file has them, read in-process by mutagen.
    Returns (title, artist, duration_seconds), or None when mutagen cannot open the
    format at all - which is the signal to fall back to ffprobe for that file.

    mutagen is already a dependency (it is the tagger) and it answers both questions
    off the file header without starting a process: measured over 120 files it read
    them in 0.04s against 7.66s for one ffprobe call each."""
    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        return None
    if audio is None:
        return None

    duration = None
    info = getattr(audio, 'info', None)
    if info is not None:
        try:
            length = float(getattr(info, 'length', 0.0) or 0.0)
            if length > 0:
                duration = length
        except (TypeError, ValueError):
            duration = None

    title = artist = None
    tags = getattr(audio, 'tags', None)
    if tags:
        def _tag_value(*names):
            # The key a title lives under depends on the tag system behind the
            # container: the easy interface normalises ID3 and MP4 to 'title' and
            # 'artist', Vorbis comments (flac, ogg, opus) already use those names,
            # and ASF (wma) uses its own.
            for name in names:
                try:
                    value = tags[name]
                except Exception:
                    continue
                if isinstance(value, (list, tuple)):
                    value = value[0] if len(value) else None
                if value is None:
                    continue
                text = str(value).strip()
                if text:
                    return text
            return None
        title = _tag_value('title', 'Title', 'TITLE')
        artist = _tag_value('artist', 'Artist', 'ARTIST', 'albumartist', 'Author', 'Writer')
    return title, artist, duration


def _ffprobe_audio_meta(path):
    """The fallback for a file mutagen cannot open or measure: one ffprobe call,
    giving back (title, artist, duration_seconds) with anything unreadable as None."""
    fmt = _probe_format_block(path)
    if not fmt:
        return None, None, None
    tags = fmt.get('tags') or {}
    title = tags.get('title') or tags.get('TITLE')
    artist = tags.get('artist') or tags.get('ARTIST')
    try:
        duration = float(fmt.get('duration'))
    except (TypeError, ValueError):
        duration = None
    return title or None, artist or None, duration or None

def get_system_accent_color():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM")
        val, _ = winreg.QueryValueEx(key, "AccentColor")
        winreg.CloseKey(key)
        b = (val >> 16) & 0xFF
        g = (val >> 8) & 0xFF
        r = val & 0xFF
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return "#0067c0"

def get_system_appearance_mode():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return "Light" if val == 1 else "Dark"
    except Exception:
        return "Dark"

def get_accent_color(color_name):
    if color_name == "System": return get_system_accent_color()
    return THEME_COLORS.get(color_name, THEME_COLORS["Blue"])[0]

def pil_to_qpixmap(pil_image):
    if pil_image is None: return QPixmap()
    img = pil_image.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg)


class ClickableSlider(QSlider):
    """A QSlider that seeks immediately on mouse press (click-to-seek), not just drag."""
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._seeking = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Compute value from click position
            val = QStyle.sliderValueFromPosition(
                self.minimum(), self.maximum(),
                event.position().toPoint().x(), self.width()
            )
            self._seeking = True
            self.setValue(val)
            self._seeking = False
            # Emit sliderMoved so on_seek fires
            self.sliderMoved.emit(val)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            val = QStyle.sliderValueFromPosition(
                self.minimum(), self.maximum(),
                event.position().toPoint().x(), self.width()
            )
            self.setValue(val)
            self.sliderMoved.emit(val)
        super().mouseMoveEvent(event)


class DoubleClickButton(QPushButton):
    """QPushButton that only triggers its primary action on double-click.

    A single left-click is reported through `singleClicked` instead of the
    standard `clicked` signal, so callers can use single clicks for selection
    (the way File Explorer does) while double clicks open or play the item."""
    doubleClicked = Signal()
    singleClicked = Signal()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        # Absorb single click so it doesn't trigger clicked signal for playback
        # (still allow default visual press styling)
        if event.button() == Qt.LeftButton:
            self.setFocus()
            self.singleClicked.emit()
        event.accept()


class _ElideTextFilter(QObject):
    """Event filter that lets a title widget shrink so sibling badge widgets
    (duration / channel labels) always keep their full width. The title text is
    elided with an ellipsis to whatever width the layout actually gives it."""

    def __init__(self, full_text, reserve=12):
        super().__init__()
        self._full = full_text
        self._reserve = reserve
        self._widget = None

    def attach(self, widget):
        self._widget = widget
        widget.installEventFilter(self)
        sp = widget.sizePolicy()
        sp.setHorizontalPolicy(QSizePolicy.Ignored)
        sp.setHorizontalStretch(1)
        widget.setSizePolicy(sp)
        widget.setMinimumWidth(0)
        self._relayout(widget)
        return self

    def set_full_text(self, text):
        self._full = text
        if self._widget is not None:
            self._relayout(self._widget)

    def eventFilter(self, obj, event):
        if obj is self._widget and event.type() in (QEvent.Resize, QEvent.Show):
            self._relayout(obj)
        return False

    def _relayout(self, widget):
        avail = widget.width() - self._reserve
        if avail <= 0:
            return
        fm = QFontMetrics(widget.font())
        full = self._full
        new_text = full if fm.horizontalAdvance(full) <= avail else fm.elidedText(full, Qt.ElideRight, avail)
        if new_text != widget.text():
            widget.setText(new_text)


class DraggableQueueWidget(QWidget):
    """Queue container widget that supports drag-and-drop reordering of pending items."""
    order_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAcceptDrops(True)
        self._drag_start_pos = None
        self._drag_source_widget = None

    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, p, self)

    def get_item_at(self, pos):
        for i in range(self.layout().count()):
            w = self.layout().itemAt(i).widget()
            if w and w.geometry().contains(pos):
                return i, w
        return None, None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            idx, w = self.get_item_at(event.position().toPoint())
            if w is not None:
                q = w.property("queue_item")
                if q and q.get('status') == 'Pending':
                    self._drag_start_pos = event.position().toPoint()
                    self._drag_source_widget = w
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._drag_source_widget and self._drag_start_pos and
                event.buttons() & Qt.LeftButton):
            dist = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            if dist > 6:
                drag = QDrag(self)
                mime = QMimeData()
                lay = self.layout()
                src_idx = -1
                for i in range(lay.count()):
                    if lay.itemAt(i).widget() == self._drag_source_widget:
                        src_idx = i
                        break
                mime.setText(str(src_idx))
                drag.setMimeData(mime)
                drag.exec(Qt.MoveAction)
        super().mouseMoveEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        src_idx = int(event.mimeData().text())
        drop_pos = event.position().toPoint()
        dst_idx, _ = self.get_item_at(drop_pos)
        if dst_idx is None:
            dst_idx = self.layout().count() - 1
        if src_idx != dst_idx and dst_idx >= 0:
            self.order_changed.emit()
            # Emit signal with indices – parent will do the actual reorder
            self._pending_reorder = (src_idx, dst_idx)
            self.order_changed.emit()
        event.acceptProposedAction()
        self._drag_start_pos = None
        self._drag_source_widget = None


# The box a result thumbnail sits in, and the colour that box wears when the track
# it belongs to is the one the player is holding. See _refresh_playback_highlights.
# The tile is the outside of the box and it does not move: how much of the box shows
# around the picture is set by growing the picture until it covers the tile down to
# THUMB_BOX_INSET on every side (cover_thumbnail). Growing the picture is the only way
# to thin the band, because the band IS the leftover - scaling to fit inside the tile
# kept the aspect ratio and spent the leftover on the box, which is why it read as far
# thicker than the inset it was built with: a 16:9 thumbnail fitted into this 1.8:1 tile
# showed 6 px of colour down each side and 3 top and bottom, and a legacy 4:3 thumbnail
# showed 16 at the sides.
# The other thing that eats the box is the app stylesheet: QLabel is a QFrame, and the
# stylesheet pads every QFrame by 5 px ("QFrame { ... padding: 5px; }"). A padded label
# draws a frame of its own around the picture - it even scales the picture down into the
# padded rect - so 5 px of frame shows whatever the inset is, and an inset change is
# invisible. So the tile behind wears the colour, and the label is the size of the picture
# and carries no padding of its own.
THUMB_TILE_W = 90
THUMB_TILE_H = 50
# Two pixels, not one: at one pixel the frame vanished into the anti-aliasing on a light
# theme and the play state was impossible to read. The tile never changes size, so a wider
# inset just means the picture is cut back further.
THUMB_BOX_INSET = 2
THUMB_BOX_W = THUMB_TILE_W - 2 * THUMB_BOX_INSET
THUMB_BOX_H = THUMB_TILE_H - 2 * THUMB_BOX_INSET
# The curve of the box's corners, and the curve the picture inside it is cut to so the
# two follow the same circle instead of a square-cornered picture inside a round frame.
# The box is always the inset wider than the picture at every point of that circle, which
# is what keeps the frame an even thickness into the corners as well as down the sides.
THUMB_BOX_RADIUS = 4
THUMB_IMG_RADIUS = THUMB_BOX_RADIUS - THUMB_BOX_INSET

THUMB_BOX_PLAIN = "#2b2b2b"     # the box of every row that is not the loaded track
THUMB_BOX_PLAYING = "#1abd33"   # the box of the track the player is running
THUMB_BOX_PAUSED = "#FF8C00"    # the box of the loaded track, held where it stopped

# What a row is told about the player - "playing" or "paused", the same tokens the local
# rows carry as their play_state property - and the colour the thumbnail box wears for it.
THUMB_BOX_COLORS = {"playing": THUMB_BOX_PLAYING, "paused": THUMB_BOX_PAUSED}


def cover_thumbnail(pixmap, width=THUMB_BOX_W, height=THUMB_BOX_H, radius=THUMB_IMG_RADIUS):
    """Scale a thumbnail until it covers width x height, cut back to that size keeping the
    middle, and round its corners to sit inside the box's own curve. Covering rather than
    fitting is what makes the box the same thickness on all four sides: the box colour is
    what is left over after the picture is placed, and a fitted 16:9 picture leaves its
    spare width as a wide band of colour down each side."""
    if pixmap.isNull():
        return pixmap
    scaled = pixmap.scaled(width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    w, h = min(width, scaled.width()), min(height, scaled.height())
    cropped = scaled.copy((scaled.width() - w) // 2, (scaled.height() - h) // 2, w, h)
    if radius <= 0:
        return cropped
    masked = QPixmap(w, h)
    masked.fill(Qt.transparent)
    painter = QPainter(masked)
    painter.setRenderHint(QPainter.Antialiasing)
    corners = QPainterPath()
    corners.addRoundedRect(0, 0, w, h, radius, radius)
    painter.setClipPath(corners)
    painter.drawPixmap(0, 0, cropped)
    painter.end()
    return masked


class ThumbnailWidget(QWidget):

    def __init__(self, video, parent_app, parent=None):
        super().__init__(parent)
        self.setFixedSize(THUMB_TILE_W, THUMB_TILE_H)
        self.video = video
        self.parent_app = parent_app
        
        self.box_color = THUMB_BOX_PLAIN
        # Without this attribute the tile's background is painted from the palette, which is a
        # flat rectangle and ignores the rounded corners the stylesheet asks for - the picture
        # inside would be cut round inside a box with square ones.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._box_style(f"background-color: {THUMB_BOX_PLAIN}; border-radius: {THUMB_BOX_RADIUS}px;")

        self.thumb_label = QLabel(self)
        self.thumb_label.setFixedSize(THUMB_BOX_W, THUMB_BOX_H)
        self.thumb_label.move(THUMB_BOX_INSET, THUMB_BOX_INSET)
        # Its own stylesheet is what keeps the picture the size it was made: without it the
        # app's QFrame padding takes 5 px off every side and the label scales the picture
        # down to fit, which is a frame nobody asked for.
        self.thumb_label.setStyleSheet("background: transparent; border: none; padding: 0px;")
        self.thumb_label.setAlignment(Qt.AlignCenter)
        
        accent = get_accent_color(parent_app.accent_color_name)
        self.play_btn = QPushButton("\uE768", self)
        self.play_btn.setToolTip("Play this track")
        self.play_btn.setFixedSize(30, 30)
        self.play_btn.move(30, 10)
        self.play_btn.setStyleSheet(f"background: rgba(0,0,0,180); color: {accent}; border-radius: 15px; font-weight: bold; font-family: 'Segoe MDL2 Assets'; font-size: 14px; padding: 0px;")
        self.play_btn.clicked.connect(self.on_play)
        self.play_btn.hide()
        
    def on_play(self, checked=False):
        self.parent_app.play_result(self.video)
        
    def enterEvent(self, event):
        self.play_btn.show()
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        self.play_btn.hide()
        super().leaveEvent(event)

    def _box_style(self, style):
        """Put the colour of the box on the tile rather than on the label. The label is a
        QFrame, and the app stylesheet pads every QFrame by 5 px, so a coloured label paints
        a 5 px frame of its own around the picture however thin the inset is. The tile is a
        plain QWidget, which that rule does not pad, and so it shows the inset exactly as
        written."""
        self.setStyleSheet(style)

    def set_highlight(self, play_state):
        """Wear the colour of what the player is doing with this track: green while it
        runs, orange while it is held where it stopped, and the plain grey the row started
        with for everything else - including a row whose state is not known any more."""
        color = THUMB_BOX_COLORS.get(play_state, THUMB_BOX_PLAIN)
        if self.box_color == color:
            return
        self.box_color = color
        self._box_style(f"background-color: {color}; border-radius: {THUMB_BOX_RADIUS}px;")

# ============================================================
# LOCAL NETWORK PLAYLIST & AUDIO FILE SYNC ("SYNC CHAINS")
# ============================================================

SYNC_PORT_START = 63350
SYNC_PORT_END = 63370
UDP_BEACON_PORT = 63350
SYNC_SOCKET_TIMEOUT = 12.0
SYNC_CHUNK_SIZE = 1024 * 1024


def get_current_wifi_ssid() -> Optional[str]:
    """Returns the current connected Wi-Fi SSID on Windows, or None if not connected to Wi-Fi."""
    if sys.platform != 'win32':
        return None
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        res = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='ignore',
            startupinfo=startupinfo
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                line = line.strip()
                if line.startswith("SSID") and not line.startswith("SSID name") and not line.startswith("BSSID"):
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        ssid = parts[1].strip()
                        if ssid:
                            return ssid
    except Exception:
        pass
    return None


def is_run_on_startup_enabled() -> bool:
    """Checks whether yt-msd is configured in the Windows HKCU Run startup registry key."""
    if sys.platform != 'win32':
        return False
    try:
        import winreg
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
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
        app_name = "yt-msd"
        if enable:
            if getattr(sys, 'frozen', False):
                cmd = f'"{sys.executable}"'
            else:
                script_path = os.path.abspath(__file__)
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


def is_client_chain_paused(cc: dict) -> tuple[bool, int]:
    """Returns (is_paused, pause_until) for the client sync chain."""
    paused_until = cc.get('paused_until', 0)

    if paused_until == -1:
        return True, -1

    if paused_until > 0:
        if paused_until > time.time():
            return True, paused_until
        else:
            cc['paused_until'] = 0

    return False, 0


_CACHED_LOCAL_IP = None
_CACHED_LOCAL_IP_TIME = 0


def get_local_ip() -> str:
    """Returns the primary local IPv4 address on the LAN interface with fast memory caching."""
    global _CACHED_LOCAL_IP, _CACHED_LOCAL_IP_TIME
    now = time.time()
    if _CACHED_LOCAL_IP and (now - _CACHED_LOCAL_IP_TIME < 60.0):
        return _CACHED_LOCAL_IP

    # 1. First attempt: UDP routing table query (instant 0ms kernel lookup, no packets sent)
    ip = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        cand = s.getsockname()[0]
        s.close()
        if cand and not cand.startswith('127.'):
            ip = cand
    except Exception:
        pass

    # 2. Fallback: Hostname adapter resolution with LAN subnet priority (prefer 192.168.x.x / 10.x.x.x)
    if not ip or ip.startswith('127.'):
        try:
            hostname = socket.gethostname()
            candidates = socket.gethostbyname_ex(hostname)[2]
            for c in candidates:
                if c.startswith('192.168.'):
                    ip = c
                    break
            if not ip:
                for c in candidates:
                    if c.startswith('10.'):
                        ip = c
                        break
            if not ip:
                for c in candidates:
                    if not c.startswith('127.') and not c.startswith('172.17.') and not c.startswith('172.18.') and not c.startswith('172.21.'):
                        ip = c
                        break
        except Exception:
            pass

    if not ip:
        ip = '127.0.0.1'

    _CACHED_LOCAL_IP = ip
    _CACHED_LOCAL_IP_TIME = now
    return ip


def get_broadcast_addresses() -> list:
    """Returns a list of broadcast addresses: subnet-directed (e.g. 192.168.1.255) across all network adapters and global."""
    addrs = set()
    addrs.add('255.255.255.255')
    try:
        local_ip = get_local_ip()
        if local_ip and not local_ip.startswith('127.'):
            parts = local_ip.split('.')
            if len(parts) == 4:
                addrs.add(f"{parts[0]}.{parts[1]}.{parts[2]}.255")
        hostname = socket.gethostname()
        for cand in socket.gethostbyname_ex(hostname)[2]:
            if cand and not cand.startswith('127.'):
                parts = cand.split('.')
                if len(parts) == 4:
                    addrs.add(f"{parts[0]}.{parts[1]}.{parts[2]}.255")
    except Exception:
        pass
    return list(addrs)


def compute_file_sha256(filepath: Path) -> str:
    """Computes SHA-256 hash of a file in streaming chunks."""
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(SYNC_CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def filter_audio_files(folder_path: Path) -> List[Path]:
    """Scans folder non-recursively, filtering ONLY audio files (ignoring dirs, zips, etc.)."""
    if not folder_path.is_dir():
        return []
    files = []
    try:
        for entry in folder_path.iterdir():
            if entry.is_file() and entry.suffix.lower() in AUDIO_EXTENSIONS:
                files.append(entry)
    except Exception:
        pass
    return sorted(files, key=lambda p: p.name.lower())


# ---------------------------------------------------------------------------
# Slow-device helpers
#
# A sluggish USB stick or MP3 player can stall a single directory call for
# several seconds while it is busy. Anything running on the GUI thread must
# therefore never touch one of those devices directly - it reads the cached
# results produced by the background probe instead, and every real file
# operation happens inside a worker thread.
# ---------------------------------------------------------------------------

_DRIVE_IO_LOCKS: Dict[str, threading.RLock] = {}
_DRIVE_IO_LOCKS_GUARD = threading.Lock()


def get_drive_io_lock(path: Union[str, Path]) -> threading.RLock:
    """Per-drive lock so only one sync ever hammers a given device at a time.

    Reentrant: a removable chain may sync a client folder that lives on the
    very same device, and nested acquisition must not deadlock.
    """
    try:
        anchor = str(Path(path).anchor) or str(path)
    except Exception:
        anchor = str(path)
    with _DRIVE_IO_LOCKS_GUARD:
        lock = _DRIVE_IO_LOCKS.get(anchor)
        if lock is None:
            lock = threading.RLock()
            _DRIVE_IO_LOCKS[anchor] = lock
        return lock


def make_throttled_progress_cb(progress_cb: Optional[Callable[[int, int, str, int, int], None]],
                              min_interval: float = 0.15):
    """Coalesce progress callbacks so a long sync cannot flood the GUI queue."""
    if progress_cb is None:
        return None
    last = [0.0]

    def _emit(done, total, name, idx, total_items):
        now = time.monotonic()
        is_final = total > 0 and done >= total
        if is_final or (now - last[0]) >= min_interval:
            last[0] = now
            progress_cb(done, total, name, idx, total_items)

    return _emit


def send_json_msg(sock: socket.socket, data: dict) -> None:
    raw = json.dumps(data).encode('utf-8')
    header = struct.pack('!I', len(raw))
    sock.sendall(header + raw)


def recv_json_msg(sock: socket.socket, timeout: float = SYNC_SOCKET_TIMEOUT) -> Optional[dict]:
    sock.settimeout(timeout)
    header = _recv_all(sock, 4)
    if not header:
        return None
    length = struct.unpack('!I', header)[0]
    payload = _recv_all(sock, length)
    if not payload:
        return None
    return json.loads(payload.decode('utf-8'))


def _recv_all(sock: socket.socket, n: int) -> Optional[bytes]:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def stream_file_to_socket(sock: socket.socket, filepath: Path, progress_cb: Optional[Callable[[int, int], None]] = None) -> str:
    total_size = filepath.stat().st_size
    h = hashlib.sha256()
    sent_bytes = 0
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(SYNC_CHUNK_SIZE)
            if not chunk:
                break
            sock.sendall(chunk)
            h.update(chunk)
            sent_bytes += len(chunk)
            if progress_cb:
                progress_cb(sent_bytes, total_size)
    return h.hexdigest()


def recv_file_from_socket(sock: socket.socket, target_path: Path, expected_size: int, expected_sha256: str,
                          progress_cb: Optional[Callable[[int, int], None]] = None) -> bool:
    tmp_path = target_path.with_suffix(target_path.suffix + '.tmp_sync')
    h = hashlib.sha256()
    received_bytes = 0
    try:
        with open(tmp_path, 'wb') as f:
            while received_bytes < expected_size:
                to_read = min(SYNC_CHUNK_SIZE, expected_size - received_bytes)
                chunk = sock.recv(to_read)
                if not chunk:
                    raise ConnectionError("Socket closed prematurely while receiving file")
                f.write(chunk)
                h.update(chunk)
                received_bytes += len(chunk)
                if progress_cb:
                    progress_cb(received_bytes, expected_size)

        actual_sha256 = h.hexdigest()
        if actual_sha256.lower() != expected_sha256.lower():
            if tmp_path.exists():
                tmp_path.unlink()
            return False

        if target_path.exists():
            target_path.unlink()
        tmp_path.replace(target_path)
        return True
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        return False


class UDPBeaconBroadcaster:
    """Broadcaster & Listener for LAN host discovery and dynamic IP updates (runs in dedicated daemon thread)."""
    def __init__(self, get_hosted_chains_cb: Callable[[], List[dict]], get_tcp_port_cb: Callable[[], int],
                 on_chain_updated_cb: Optional[Callable[[str], None]] = None):
        self.get_hosted_chains_cb = get_hosted_chains_cb
        self.get_tcp_port_cb = get_tcp_port_cb
        self.on_chain_updated_cb = on_chain_updated_cb
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if hasattr(self, '_sock') and self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def _run_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock = sock
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        if sys.platform == 'win32':
            try:
                sock.ioctl(0x9800000C, False)
            except Exception:
                pass

        is_bound = False
        try:
            sock.bind(('', UDP_BEACON_PORT))
            is_bound = True
        except Exception:
            is_bound = False
        sock.settimeout(1.0)

        last_beacon_time = 0
        while self._running:
            now = time.time()
            if now - last_beacon_time >= 4.0:
                last_beacon_time = now
                try:
                    chains = self.get_hosted_chains_cb()
                    tcp_port = self.get_tcp_port_cb()
                    if chains and tcp_port > 0:
                        codes = [c.get('sync_code') for c in chains if c.get('sync_code')]
                        beacon_data = {
                            'type': 'BEACON',
                            'sync_codes': codes,
                            'tcp_port': tcp_port,
                            'host_ip': get_local_ip()
                        }
                        raw = json.dumps(beacon_data).encode('utf-8')
                        for _bcast_addr in get_broadcast_addresses():
                            try:
                                sock.sendto(raw, (_bcast_addr, UDP_BEACON_PORT))
                            except Exception:
                                pass
                except Exception:
                    pass

            if is_bound:
                try:
                    msg, addr = sock.recvfrom(2048)
                    data = json.loads(msg.decode('utf-8'))
                    msg_type = data.get('type')
                    if msg_type in ('PROBE', 'PROBE_ALL'):
                        target_code = str(data.get('sync_code', '')).strip()
                        chains = self.get_hosted_chains_cb()
                        tcp_port = self.get_tcp_port_cb()
                        if chains and tcp_port > 0:
                            for c in chains:
                                c_code = str(c.get('sync_code', ''))
                                if not target_code or target_code == c_code or msg_type == 'PROBE_ALL':
                                    reply = {
                                        'type': 'PROBE_REPLY',
                                        'sync_code': c_code,
                                        'chain_name': c.get('name', 'Audio Playlist'),
                                        'tcp_port': tcp_port,
                                        'host_ip': get_local_ip()
                                    }
                                    try:
                                        sock.sendto(json.dumps(reply).encode('utf-8'), addr)
                                    except Exception:
                                        pass
                    elif msg_type == 'CHAIN_UPDATED':
                        target_code = str(data.get('sync_code', '')).strip()
                        if target_code and self.on_chain_updated_cb:
                            self.on_chain_updated_cb(target_code)
                except socket.timeout:
                    pass
                except Exception:
                    time.sleep(0.5)
            else:
                time.sleep(1.0)

        try:
            sock.close()
        except Exception:
            pass


def discover_hosts_on_lan(sync_code: Optional[str] = None, timeout: float = 2.5) -> List[Tuple[str, int, str, str]]:
    """Broadcasts a UDP discovery probe; returns list of (host_ip, tcp_port, sync_code, chain_name)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    if sys.platform == 'win32':
        try:
            sock.ioctl(0x9800000C, False)
        except Exception:
            pass
    sock.settimeout(0.3)

    probe_type = 'PROBE' if sync_code else 'PROBE_ALL'
    probe = json.dumps({'type': probe_type, 'sync_code': str(sync_code or '')}).encode('utf-8')
    start_time = time.time()
    results = []
    seen = set()

    try:
        for _bcast_addr in get_broadcast_addresses():
            try:
                sock.sendto(probe, (_bcast_addr, UDP_BEACON_PORT))
            except Exception:
                pass
        while time.time() - start_time < timeout:
            try:
                msg, (sender_ip, _) = sock.recvfrom(2048)
                data = json.loads(msg.decode('utf-8'))
                if data.get('type') in ('PROBE_REPLY', 'BEACON'):
                    rep_code = str(data.get('sync_code') or '')
                    codes = data.get('sync_codes', [rep_code] if rep_code else [])
                    port = int(data.get('tcp_port', 63350))
                    name = data.get('chain_name', 'Audio Playlist')
                    ip = data.get('host_ip') or sender_ip
                    for c in codes:
                        c_str = str(c)
                        if sync_code and c_str != str(sync_code):
                            continue
                        key = (ip, port, c_str)
                        if key not in seen:
                            seen.add(key)
                            results.append((ip, port, c_str, name))
                            if sync_code and c_str == str(sync_code):
                                return results
            except socket.timeout:
                try:
                    for _bcast_addr in get_broadcast_addresses():
                        try:
                            sock.sendto(probe, (_bcast_addr, UDP_BEACON_PORT))
                        except Exception:
                            pass
                except Exception:
                    pass
            except Exception:
                pass
    finally:
        try:
            sock.close()
        except Exception:
            pass
    return results


def discover_host_on_lan(sync_code: str, timeout: float = 2.5) -> Optional[Tuple[str, int, str]]:
    """Broadcasts a UDP discovery probe for a 4-digit sync code; returns (host_ip, tcp_port, chain_name) or None."""
    res = discover_hosts_on_lan(sync_code=str(sync_code), timeout=timeout)
    if res:
        ip, port, _, name = res[0]
        return (ip, port, name)
    return None


def send_lan_update_notification(sync_code: str, host_port: int):
    """Sends a UDP broadcast notification to LAN that a hosted chain's files have been modified."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    if sys.platform == 'win32':
        try:
            sock.ioctl(0x9800000C, False)
        except Exception:
            pass
    try:
        payload = json.dumps({
            'type': 'CHAIN_UPDATED',
            'sync_code': str(sync_code),
            'host_ip': get_local_ip(),
            'tcp_port': host_port
        }).encode('utf-8')
        for _bcast_addr in get_broadcast_addresses():
            try:
                sock.sendto(payload, (_bcast_addr, UDP_BEACON_PORT))
            except Exception:
                pass
    except Exception:
        pass
    finally:
        try:
            sock.close()
        except Exception:
            pass


class HostFolderWatcher:
    """Monitors hosted sync chain folders and debounces notifications to avoid spamming."""
    def __init__(self, on_change_callback: Callable[[str], None]):
        self.on_change_callback = on_change_callback
        self.watched_chains: Dict[str, dict] = {}
        # RLock, not Lock: add_or_update_chain() takes this lock and then calls remove_chain(),
        # which takes it again on the same thread. A plain threading.Lock deadlocks that thread
        # where it stands, holding the lock for good - so the first hosted chain ever created
        # silently killed the watcher (no folder change was ever noticed, so clients were never
        # notified), and every later refresh_sync_watchers() call leaked another stuck thread
        # because stop_all(), remove_chain() and add_or_update_chain() all queue on a lock that
        # nobody will ever release again.
        self.lock = threading.RLock()

    def add_or_update_chain(self, chain_id: str, folder_path: str, sync_code: str, delay_mins: int = 5):
        with self.lock:
            self.remove_chain(chain_id)
            if not _WATCHDOG_AVAILABLE:
                return
            p = Path(folder_path)
            if not p.is_dir():
                return

            delay_sec = max(5, delay_mins * 60)

            class Handler(FileSystemEventHandler):
                def __init__(self, watcher_ref, cid):
                    self.watcher_ref = watcher_ref
                    self.cid = cid
                def on_any_event(self, event):
                    src = getattr(event, 'src_path', '')
                    dest = getattr(event, 'dest_path', '')
                    ext1 = os.path.splitext(src)[1].lower() if src else ''
                    ext2 = os.path.splitext(dest)[1].lower() if dest else ''
                    if ext1 in AUDIO_EXTENSIONS or ext2 in AUDIO_EXTENSIONS:
                        self.watcher_ref._trigger_debounce(self.cid)

            observer = Observer()
            observer.daemon = True
            handler = Handler(self, chain_id)
            observer.schedule(handler, str(p), recursive=False)
            observer.start()

            self.watched_chains[chain_id] = {
                'folder_path': folder_path,
                'sync_code': sync_code,
                'delay_sec': delay_sec,
                'timer': None,
                'observer': observer
            }

    def remove_chain(self, chain_id: str):
        obs = None
        timer = None
        with self.lock:
            info = self.watched_chains.pop(chain_id, None)
            if info:
                timer = info.get('timer')
                obs = info.get('observer')
        if timer and timer.is_alive():
            timer.cancel()
        if obs:
            try:
                obs.stop()
                obs.join(timeout=0.3)
            except Exception:
                pass

    def stop_all(self):
        with self.lock:
            chain_ids = list(self.watched_chains.keys())
        for cid in chain_ids:
            self.remove_chain(cid)

    def _trigger_debounce(self, chain_id: str):
        with self.lock:
            info = self.watched_chains.get(chain_id)
            if not info:
                return
            timer = info.get('timer')
            if timer and timer.is_alive():
                timer.cancel()

            sync_code = info['sync_code']
            delay_sec = info['delay_sec']

            def _fire():
                self.on_change_callback(sync_code)

            new_timer = threading.Timer(delay_sec, _fire)
            new_timer.daemon = True
            info['timer'] = new_timer
            new_timer.start()


class SyncHostServer:
    """TCP Server serving hosted sync chains to connected clients."""
    def __init__(self, get_hosted_chains_cb: Callable[[], List[dict]],
                 on_client_activity_cb: Optional[Callable[[str, str, str], None]] = None):
        self.get_hosted_chains_cb = get_hosted_chains_cb
        self.on_client_activity_cb = on_client_activity_cb
        self.server_sock: Optional[socket.socket] = None
        self.active_port: int = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> int:
        if self._running:
            return self.active_port

        for port in range(SYNC_PORT_START, SYNC_PORT_END + 1):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('', port))
                s.listen(10)
                self.server_sock = s
                self.active_port = port
                self._running = True
                self._thread = threading.Thread(target=self._accept_loop, daemon=True)
                self._thread.start()
                return port
            except OSError:
                continue
        return 0

    def stop(self):
        self._running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
            self.server_sock = None
        self.active_port = 0

    def _accept_loop(self):
        while self._running and self.server_sock:
            try:
                client_sock, (client_ip, client_port) = self.server_sock.accept()
                threading.Thread(target=self._handle_client, args=(client_sock, client_ip), daemon=True).start()
            except OSError:
                break

    def _handle_client(self, sock: socket.socket, client_ip: str):
        try:
            sock.settimeout(SYNC_SOCKET_TIMEOUT)
            auth_msg = recv_json_msg(sock)
            if not auth_msg or auth_msg.get('cmd') != 'AUTH':
                send_json_msg(sock, {'status': 'ERROR', 'reason': 'Expected AUTH command'})
                return

            sync_code = str(auth_msg.get('sync_code', ''))
            chains = self.get_hosted_chains_cb()
            matching_chain = None
            for c in chains:
                if str(c.get('sync_code')) == sync_code:
                    matching_chain = c
                    break

            if not matching_chain:
                send_json_msg(sock, {'status': 'ERROR', 'reason': f'Sync code {sync_code} not found on host'})
                return

            folder_path = Path(matching_chain.get('folder_path', ''))
            if not folder_path.is_dir():
                send_json_msg(sock, {'status': 'ERROR', 'reason': 'Hosted folder path does not exist on disk'})
                return

            audio_files = filter_audio_files(folder_path)
            send_json_msg(sock, {
                'status': 'OK',
                'chain_name': matching_chain.get('name', 'Audio Playlist'),
                'files_count': len(audio_files)
            })

            if self.on_client_activity_cb:
                self.on_client_activity_cb(sync_code, client_ip, 'Connected')

            while self._running:
                req = recv_json_msg(sock, timeout=30.0)
                if not req:
                    break
                cmd = req.get('cmd')
                if cmd == 'GET_INDEX':
                    index = []
                    for f in filter_audio_files(folder_path):
                        try:
                            stat = f.stat()
                            art, tit = read_metadata_tags(f)
                            sha = compute_file_sha256(f)
                            index.append({
                                'name': f.name,
                                'size': stat.st_size,
                                'mtime': stat.st_mtime,
                                'sha256': sha,
                                'artist': art,
                                'title': tit
                            })
                        except Exception:
                            pass
                    send_json_msg(sock, {'status': 'OK', 'files': index})

                elif cmd == 'PULL_FILE':
                    filename = req.get('filename', '')
                    target_file = folder_path / filename
                    if not target_file.is_file() or target_file.suffix.lower() not in AUDIO_EXTENSIONS:
                        send_json_msg(sock, {'status': 'ERROR', 'reason': 'File not found or not an audio file'})
                    else:
                        size = target_file.stat().st_size
                        sha = compute_file_sha256(target_file)
                        send_json_msg(sock, {
                            'status': 'SENDING',
                            'filename': filename,
                            'filesize': size,
                            'sha256': sha
                        })
                        if self.on_client_activity_cb:
                            self.on_client_activity_cb(sync_code, client_ip, f'Sending {filename}')
                        stream_file_to_socket(sock, target_file)

                elif cmd == 'PING':
                    send_json_msg(sock, {'status': 'PONG'})
                else:
                    send_json_msg(sock, {'status': 'ERROR', 'reason': f'Unknown command: {cmd}'})
        except Exception:
            pass
        finally:
            try:
                sock.close()
            except Exception:
                pass


class SyncClientWorker:
    """Executes client synchronization against a remote host."""
    @staticmethod
    def sync_chain(chain_config: dict,
                   status_cb: Optional[Callable[[str], None]] = None,
                   progress_cb: Optional[Callable[[int, int, str, int, int], None]] = None) -> Tuple[bool, str, int, int]:
        sync_code = str(chain_config.get('sync_code', ''))
        folder_str = chain_config.get('folder_path', '')
        dest_folder = Path(folder_str)
        dest_folder.mkdir(parents=True, exist_ok=True)

        host_ip = chain_config.get('last_known_host_ip', '')
        host_port = int(chain_config.get('host_port', 63350))
        deletion_mode = chain_config.get('deletion_mode', 'mirror')

        # Progress is reported at a bounded rate no matter how fast the device
        # is, so a sync can never starve the UI event loop.
        progress_cb = make_throttled_progress_cb(progress_cb)

        if status_cb:
            status_cb(f"Connecting to host for Sync Code {sync_code}...")

        sock = None
        if host_ip and host_port > 0:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3.0)
                sock.connect((host_ip, host_port))
            except Exception:
                sock = None

        if not sock:
            if status_cb:
                status_cb(f"Host unreachable at {host_ip}. Broadcasting LAN discovery...")
            found = discover_host_on_lan(sync_code, timeout=3.0)
            if not found:
                return False, f"Could not find active host for Sync Code {sync_code} on local network.", 0, 0
            host_ip, host_port, _ = found
            chain_config['last_known_host_ip'] = host_ip
            chain_config['host_port'] = host_port
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(SYNC_SOCKET_TIMEOUT)
                sock.connect((host_ip, host_port))
            except Exception as e:
                return False, f"Failed to connect to host at {host_ip}:{host_port}: {e}", 0, 0

        transferred = 0
        deleted = 0
        # Everything below reads and writes dest_folder, which may be a slow
        # device: hold the per-drive lock so only one sync works it over.
        drive_lock = get_drive_io_lock(dest_folder)
        drive_lock.acquire()
        try:
            sock.settimeout(SYNC_SOCKET_TIMEOUT)
            send_json_msg(sock, {'cmd': 'AUTH', 'sync_code': sync_code, 'client_ip': get_local_ip()})
            auth_resp = recv_json_msg(sock)
            if not auth_resp or auth_resp.get('status') != 'OK':
                err = auth_resp.get('reason', 'Authentication rejected by host') if auth_resp else 'No auth response'
                return False, err, 0, 0

            if status_cb:
                status_cb("Fetching file index from host...")
            send_json_msg(sock, {'cmd': 'GET_INDEX'})
            index_resp = recv_json_msg(sock, timeout=25.0)
            if not index_resp or index_resp.get('status') != 'OK':
                return False, "Failed to retrieve file index from host.", 0, 0

            host_files: List[dict] = index_resp.get('files', [])
            host_files_map = {f['name']: f for f in host_files}

            local_files = filter_audio_files(dest_folder)
            local_files_map = {f.name: f for f in local_files}

            if deletion_mode == 'mirror':
                for local_name, local_path in list(local_files_map.items()):
                    if local_name not in host_files_map:
                        try:
                            local_path.unlink()
                            deleted += 1
                            if status_cb:
                                status_cb(f"Removed deleted track: {local_name}")
                        except Exception:
                            pass

            total_items = len(host_files)
            for idx, hf in enumerate(host_files, 1):
                name = hf['name']
                h_size = hf['size']
                h_sha256 = hf['sha256']
                h_mtime = hf.get('mtime', 0)
                h_artist = hf.get('artist')
                h_title = hf.get('title')

                target_path = dest_folder / name
                needs_download = False
                needs_tag_update = False

                if not target_path.exists():
                    needs_download = True
                else:
                    l_size = target_path.stat().st_size
                    l_mtime = target_path.stat().st_mtime
                    if l_size != h_size or h_mtime > l_mtime + 1.0:
                        l_sha256 = compute_file_sha256(target_path)
                        if l_sha256.lower() != h_sha256.lower():
                            l_art, l_tit = read_metadata_tags(target_path)
                            if (l_art != h_artist or l_tit != h_title) and abs(l_size - h_size) < 4096:
                                write_metadata_tags(target_path, h_artist or "", h_title or "")
                                if compute_file_sha256(target_path).lower() == h_sha256.lower():
                                    needs_tag_update = True
                                else:
                                    needs_download = True
                            else:
                                needs_download = True

                if needs_download:
                    if status_cb:
                        status_cb(f"Downloading [{idx}/{total_items}]: {name}")
                    send_json_msg(sock, {'cmd': 'PULL_FILE', 'filename': name})
                    pull_resp = recv_json_msg(sock)
                    if not pull_resp or pull_resp.get('status') != 'SENDING':
                        continue

                    def _progress(bytes_done, bytes_total, _name=name, _idx=idx, _tot=total_items):
                        if progress_cb:
                            progress_cb(bytes_done, bytes_total, _name, _idx, _tot)

                    ok = recv_file_from_socket(sock, target_path, h_size, h_sha256, _progress)
                    if ok:
                        transferred += 1
                        try:
                            os.utime(target_path, (time.time(), h_mtime))
                        except Exception:
                            pass
                elif needs_tag_update:
                    if status_cb:
                        status_cb(f"Updated metadata [{idx}/{total_items}]: {name}")
                    transferred += 1

            return True, f"Synced successfully ({transferred} updated, {deleted} removed).", transferred, deleted
        except Exception as e:
            return False, f"Sync error: {e}", transferred, deleted
        finally:
            drive_lock.release()
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass


# Placeholder tag file placed in removable media / USB drive folders
SYNC_TAG_FILENAME = "TAG.yaml"

def write_sync_tag_file(folder_path: Union[str, Path], sync_code: str, chain_name: str = '',
                        sync_style: str = 'Mirror', last_synced_by: str = 'Host',
                        parent_sync_folder: str = '') -> bool:
    try:
        p = Path(folder_path)
        p.mkdir(parents=True, exist_ok=True)
        tag_file = p / SYNC_TAG_FILENAME
        now_str = time.strftime("%m-%d-%Y %H:%M:%S")
        content = (
            "# This is a marker file for yt-msd syncing. DO NOT DELETE!\n"
            "# This file is automatically created by yt-msd, when syncing a playlist onto removable media (Like an SD card)\n"
            "# Modifying or deleting this file will break the sync process. If you no longer want to sync, delete the sync chain inside of yt-msd.\n\n"
            f"sync_code: {sync_code}\n\n"
            "# Human-readable name for this sync chain\n"
            f"chain_name: {chain_name}\n\n"
            "# Either Mirror, or Additive\n"
            f"sync_style: {sync_style}\n\n"
            f"last_synced: {now_str}\n\n"
            "# Either Host (this machine hosts the chain) or Client (subscribed to a remote host).\n"
            f"last_synced_by: {last_synced_by}\n\n"
            "# Filepath of master folder on host\n"
            f"parent_sync_folder: {parent_sync_folder}\n"
        )
        with open(tag_file, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"Error writing sync tag file to {folder_path}: {e}")
        return False

def read_sync_tag_file(folder_path: Union[str, Path]) -> Optional[dict]:
    p = Path(folder_path)
    for fname in (SYNC_TAG_FILENAME, "TAG.yaml", "tag.yaml", "TAG.yml", "tag.yml", ".ytmsd_sync_tag"):
        tag_file = p / fname
        if tag_file.is_file():
            try:
                res = {}
                with open(tag_file, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if ':' in line:
                            parts = line.split(':', 1)
                            k = parts[0].strip().lower()
                            v = parts[1].strip().strip("'\"")
                            res[k] = v
                sync_code = (res.get('sync_code') or res.get('sync code') or res.get('code') or '').strip()
                if sync_code and sync_code.upper() != 'XXXX':
                    res['sync_code'] = sync_code
                    style = (res.get('sync_style') or res.get('sync style') or res.get('style') or 'Mirror').strip()
                    res['sync_style'] = style
                    res['deletion_mode'] = 'mirror' if style.lower() == 'mirror' else 'additive'
                    res['chain_name'] = res.get('chain_name') or res.get('chain name') or res.get('name') or p.name
                    res['last_synced'] = res.get('last_synced') or res.get('last synced') or ''
                    return res
            except Exception as e:
                print(f"Error reading sync tag from {tag_file}: {e}")
    return None

# A TAG.yaml records last_synced as a local wall-clock string, while the chain
# dicts in sync-chains.json keep it as an epoch number. Both forms have to be
# comparable before a removable drive is written to, otherwise a client that has
# not spoken to its host in a while can roll a drive that is still current back
# to an older version of the chain.
SYNC_TAG_TIME_FORMATS = ("%m-%d-%Y %H:%M:%S", "%m-%d-%Y %H:%M",
                         "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")
# Two machines' clocks are never perfectly in step. A drive that only looks a
# minute ahead is clock drift, not a newer version of the chain.
SYNC_RETROGRADE_GRACE_SECONDS = 60


def parse_sync_timestamp(value) -> Optional[float]:
    """Normalize a last_synced value - epoch number or TAG.yaml date string - to epoch seconds."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        return ts if ts > 0 else None
    text = str(value).strip()
    if not text:
        return None
    try:  # An epoch stored as text (older configs did this)
        ts = float(text)
        return ts if ts > 0 else None
    except ValueError:
        pass
    for fmt in SYNC_TAG_TIME_FORMATS:
        try:
            return time.mktime(time.strptime(text, fmt))
        except (ValueError, TypeError):
            continue
    return None


def format_sync_timestamp(ts: Optional[float]) -> str:
    """The readable form of a parsed last_synced, for status lines and prompts."""
    if not ts:
        return "never"
    try:
        return time.strftime("%m-%d-%Y %H:%M:%S", time.localtime(ts))
    except (ValueError, OSError, OverflowError):
        return "an unknown time"


def drive_last_synced_timestamp(folder_path: Union[str, Path]) -> Optional[float]:
    """The last_synced recorded in the TAG.yaml sitting on a drive, if it has one."""
    tag = read_sync_tag_file(folder_path)
    if not tag:
        return None
    return parse_sync_timestamp(tag.get('last_synced'))


def find_tagged_sync_folders_on_drive(drive_root: str) -> List[Tuple[Path, dict]]:
    """Scans drive root and one level of subdirectories for yt-msd TAG.yaml files.
    Playlists are always placed as a direct subfolder on the drive root."""
    results = []
    root = Path(drive_root)
    if not root.exists():
        return results

    # 1. Check drive root itself
    tag = read_sync_tag_file(root)
    if tag and tag.get('sync_code'):
        results.append((root, tag))

    # 2. Check direct subdirectories only (depth 1)
    skip_names = {'$recycle.bin', 'system volume information', 'windows',
                  'program files', 'program files (x86)', 'appdata', '.git', '.gemini'}
    try:
        for entry in root.iterdir():
            if entry.is_dir() and entry.name.lower() not in skip_names and not entry.name.startswith('.'):
                tag_data = read_sync_tag_file(entry)
                if tag_data and tag_data.get('sync_code'):
                    results.append((entry, tag_data))
    except (PermissionError, OSError):
        pass

    return results


def make_removable_chain_id(sync_code: str, folder_path: str) -> str:
    """Stable, collision-resistant id for a runtime removable-media chain."""
    digest = hashlib.md5(str(folder_path).encode('utf-8')).hexdigest()[:8]
    return f"rc_{sync_code}_{digest}"


# Shared lock so the two writers of gui_config.json (MainApp.save_config and
# SyncConfigManager.save) never interleave partial reads/writes and clobber each other.
_CONFIG_WRITE_LOCK = threading.Lock()

# The sync settings a fresh install gets. Named here rather than written inline so that
# MainApp.reset_to_defaults() can hand back exactly these defaults instead of guessing at
# a copy of the literal.
DEFAULT_SYNC_SETTINGS = {"auto_sync_interval_mins": 30, "firewall_prompted": False}


class SyncConfigManager:
    """Manages persistence of sync configuration within the unified gui_config.json."""
    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        self.config_file = os.path.join(config_dir, "gui_config.json")
        self.legacy_file = os.path.join(config_dir, "sync_config.json")
        self.settings: dict = dict(DEFAULT_SYNC_SETTINGS)
        self.hosted_chains: List[dict] = []
        self.client_chains: List[dict] = []
        self.load()

    def load(self):
        migrated = False
        # Migrate legacy sync_config.json if present
        if os.path.exists(self.legacy_file):
            try:
                with open(self.legacy_file, 'r', encoding='utf-8') as f:
                    legacy_data = json.load(f)
                    self.settings = legacy_data.get('settings', self.settings)
                    self.hosted_chains = legacy_data.get('hosted_chains', [])
                    self.client_chains = legacy_data.get('client_chains', [])
                migrated = True
            except Exception:
                pass
            try:
                os.remove(self.legacy_file)
            except Exception:
                pass

        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if not migrated or 'hosted_chains' in data:
                        self.settings = data.get('sync_settings', self.settings)
                        self.hosted_chains = data.get('hosted_chains', self.hosted_chains)
                        self.client_chains = data.get('client_chains', self.client_chains)
            except Exception:
                pass

        # bind_client_wifi() used to write the Wi-Fi binding as 'bound_wifi_ssid' while every
        # reader - the chain card label, the auto-sync gate, the LAN-notification path and the
        # removable-drive path - asks for 'wifi_ssid'. A chain that was bound to a network in an
        # earlier build therefore reads back as unbound, and the sync quietly reverts to running on
        # any network. Fold the stray key back onto the name the readers use so an existing binding
        # survives the upgrade instead of silently disappearing.
        for chain in self.client_chains:
            stray_ssid = chain.pop('bound_wifi_ssid', None)
            if stray_ssid is not None and not str(chain.get('wifi_ssid') or '').strip():
                chain['wifi_ssid'] = str(stray_ssid).strip()
                migrated = True

        if migrated:
            self.save()

    def save(self):
        with _CONFIG_WRITE_LOCK:
            data = {}
            if os.path.exists(self.config_file):
                try:
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except Exception:
                    data = {}

            data['sync_settings'] = self.settings
            data['hosted_chains'] = self.hosted_chains
            data['client_chains'] = self.client_chains

            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
            except Exception:
                pass

    def generate_unique_sync_code(self) -> str:
        used = {str(c.get('sync_code')) for c in self.hosted_chains}
        for _ in range(1000):
            code = str(random.randint(1000, 9999))
            if code not in used:
                return code
        return "1000"

    def add_hosted_chain(self, name: str, folder_path: str, sync_code: Optional[str] = None, notify_delay_mins: int = 5) -> dict:
        code = sync_code or self.generate_unique_sync_code()
        chain = {
            'id': f'hc_{code}',
            'sync_code': code,
            'name': name,
            'folder_path': folder_path,
            'notify_delay_mins': notify_delay_mins,
            'created_at': time.time(),
            'last_synced': 0,
            'status': 'Active'
        }
        self.hosted_chains.append(chain)
        self.save()
        return chain

    def add_client_chain(self, name: str, folder_path: str, sync_code: str, host_ip: str,
                         host_port: int = 63350, deletion_mode: str = 'mirror', bound_wifi_ssid: str = '') -> dict:
        chain = {
            'id': f'cc_{sync_code}',
            'sync_code': sync_code,
            'name': name,
            'folder_path': folder_path,
            'last_known_host_ip': host_ip,
            'host_port': host_port,
            'deletion_mode': deletion_mode,
            'paused_until': 0,
            'wifi_ssid': bound_wifi_ssid,
            'created_at': time.time(),
            'last_synced': 0,
            'status': 'Pending Sync'
        }
        self.client_chains.append(chain)
        self.save()
        return chain

    def pause_client_chain(self, chain_id: str, duration_sec: int):
        paused_until = -1 if duration_sec == -1 else int(time.time() + duration_sec)
        for c in self.client_chains:
            if c.get('id') == chain_id:
                c['paused_until'] = paused_until
                break
        self.save()

    def resume_client_chain(self, chain_id: str):
        for c in self.client_chains:
            if c.get('id') == chain_id:
                c['paused_until'] = 0
                break
        self.save()

    def bind_client_wifi(self, chain_id: str, ssid: str):
        for c in self.client_chains:
            if c.get('id') == chain_id:
                # Must be written under exactly 'wifi_ssid'. add_client_chain() stores it under
                # that name and every reader asks for it by that name, so writing it anywhere else
                # made "Bind Wi-Fi" / "Unbind Wi-Fi" on a live chain look like a no-op: the card
                # kept its old label and the auto-sync gate kept the SSID the chain was created with.
                c['wifi_ssid'] = ssid.strip()
                break
        self.save()

    def remove_chain(self, chain_id: str):
        self.hosted_chains = [c for c in self.hosted_chains if c.get('id') != chain_id]
        self.client_chains = [c for c in self.client_chains if c.get('id') != chain_id]
        self.save()


class ClientSyncThread(QThread):
    status_signal = Signal(str)
    progress_signal = Signal(int, int, str, int, int)
    finished_signal = Signal(bool, str, int, int)

    def __init__(self, chain_config: dict):
        super().__init__()
        self.chain_config = chain_config

    def run(self):
        def _status(txt):
            self.status_signal.emit(txt)

        def _progress(done, total, filename, idx, total_items):
            self.progress_signal.emit(done, total, filename, idx, total_items)

        ok, msg, transferred, deleted = SyncClientWorker.sync_chain(
            self.chain_config,
            status_cb=_status,
            progress_cb=_progress
        )
        self.finished_signal.emit(ok, msg, transferred, deleted)


class SyncRemovableWorker:
    """Synchronizes audio files between local master folders and removable storage devices."""
    @staticmethod
    def sync_local_folders(src_dir: Path, dest_dir: Path, deletion_mode: str = 'mirror',
                           status_cb: Optional[Callable[[str], None]] = None,
                           progress_cb: Optional[Callable[[int, int, str, int, int], None]] = None) -> Tuple[bool, str, int, int]:
        import shutil
        progress_cb = make_throttled_progress_cb(progress_cb)
        if not src_dir.is_dir():
            return False, f"Source directory '{src_dir}' does not exist.", 0, 0
        dest_dir.mkdir(parents=True, exist_ok=True)

        src_files = filter_audio_files(src_dir)
        src_map = {f.name: f for f in src_files}
        dest_files = filter_audio_files(dest_dir)
        dest_map = {f.name: f for f in dest_files}

        transferred = 0
        deleted = 0

        # Mirror deletion
        if deletion_mode == 'mirror':
            for local_name, local_path in list(dest_map.items()):
                if local_name not in src_map:
                    try:
                        local_path.unlink()
                        deleted += 1
                        if status_cb:
                            status_cb(f"Removed deleted track: {local_name}")
                    except Exception:
                        pass

        total_items = len(src_files)
        for idx, (name, src_file) in enumerate(src_map.items(), 1):
            dest_file = dest_dir / name
            needs_copy = False

            if not dest_file.exists():
                needs_copy = True
            else:
                try:
                    s_stat = src_file.stat()
                    d_stat = dest_file.stat()
                    # If size differs or source is newer by > 2s, copy
                    if s_stat.st_size != d_stat.st_size or s_stat.st_mtime > d_stat.st_mtime + 2.0:
                        needs_copy = True
                except Exception:
                    needs_copy = True

            if needs_copy:
                if status_cb:
                    status_cb(f"Copying [{idx}/{total_items}]: {name}")
                try:
                    # High-speed unthrottled copy using 4MB streaming buffer
                    BUF_SIZE = 4 * 1024 * 1024
                    file_size = max(1, src_file.stat().st_size)
                    copied_bytes = 0
                    if progress_cb:
                        progress_cb(0, file_size, name, idx, total_items)
                    with open(src_file, 'rb') as sf, open(dest_file, 'wb') as df:
                        while True:
                            buf = sf.read(BUF_SIZE)
                            if not buf:
                                break
                            df.write(buf)
                            copied_bytes += len(buf)
                            if progress_cb:
                                progress_cb(copied_bytes, file_size, name, idx, total_items)
                    shutil.copystat(src_file, dest_file)
                    transferred += 1
                    if progress_cb:
                        progress_cb(file_size, file_size, name, idx, total_items)
                except Exception as e:
                    print(f"Error copying {name} to {dest_file}: {e}")

        return True, f"Synced {transferred} files ({deleted} removed).", transferred, deleted

    @staticmethod
    def sync_removable_chain(removable_chain: dict, config_manager: SyncConfigManager,
                             status_cb: Optional[Callable[[str], None]] = None,
                             progress_cb: Optional[Callable[[int, int, str, int, int], None]] = None,
                             confirm_cb: Optional[Callable[[str], bool]] = None) -> Tuple[bool, str, int, int]:
        sync_code = str(removable_chain.get('sync_code', ''))
        dest_path = Path(removable_chain.get('folder_path', ''))
        del_mode = removable_chain.get('deletion_mode', 'mirror')
        chain_name = removable_chain.get('name', 'Removable Media')

        # Find the chain that supplies the source files. Its folder lives on a
        # second drive that also gets worked over, so take every drive lock this
        # chain may touch in a fixed (sorted) order - that way two chains that
        # point at each other's drives cannot deadlock. The inner worker
        # re-acquires the same locks reentrantly.
        matching_hc = next((hc for hc in config_manager.hosted_chains if str(hc.get('sync_code')) == sync_code), None)
        matching_cc = next((cc for cc in config_manager.client_chains if str(cc.get('sync_code')) == sync_code), None)
        src_chain = matching_hc or matching_cc or {}
        anchors = set()
        for p in (dest_path, Path(src_chain.get('folder_path', ''))):
            try:
                anchor = str(p.anchor)
            except Exception:
                anchor = ''
            if anchor:
                anchors.add(anchor)
        drive_locks = [get_drive_io_lock(a) for a in sorted(anchors)]
        for lock in drive_locks:
            lock.acquire()
        try:
            return SyncRemovableWorker._sync_removable_chain_locked(
                sync_code, dest_path, del_mode, chain_name, config_manager, status_cb, progress_cb,
                matching_hc, matching_cc, confirm_cb)
        finally:
            for lock in reversed(drive_locks):
                lock.release()

    @staticmethod
    def _sync_removable_chain_locked(sync_code: str, dest_path: Path, del_mode: str,
                                     chain_name: str, config_manager: SyncConfigManager,
                                     status_cb: Optional[Callable[[str], None]],
                                     progress_cb: Optional[Callable[[int, int, str, int, int], None]],
                                     matching_hc: Optional[dict] = None,
                                     matching_cc: Optional[dict] = None,
                                     confirm_cb: Optional[Callable[[str], bool]] = None) -> Tuple[bool, str, int, int]:
        # Find matching hosted chain or client chain (the wrapper normally passes
        # these in already; the lookup is only a fallback for direct callers)
        if matching_hc is None and matching_cc is None:
            matching_hc = next((hc for hc in config_manager.hosted_chains if str(hc.get('sync_code')) == sync_code), None)
            matching_cc = next((cc for cc in config_manager.client_chains if str(cc.get('sync_code')) == sync_code), None)

        if matching_hc:
            src_dir = Path(matching_hc.get('folder_path', ''))
            if status_cb:
                status_cb(f"[USB Sync: {chain_name}] Syncing from hosted master folder '{src_dir.name}'...")
            ok, msg, transferred, deleted = SyncRemovableWorker.sync_local_folders(src_dir, dest_path, del_mode, status_cb, progress_cb)
            if ok:
                write_sync_tag_file(
                    dest_path,
                    sync_code=sync_code,
                    chain_name=chain_name,
                    sync_style='Mirror' if del_mode == 'mirror' else 'Additive',
                    last_synced_by='Host',
                    parent_sync_folder=str(src_dir)
                )
            return ok, msg, transferred, deleted

        elif matching_cc:
            src_dir = Path(matching_cc.get('folder_path', ''))

            # Retrograde failsafe. The drive carries its own last_synced in its
            # TAG.yaml. If this PC's client copy has not been refreshed since that,
            # writing it to the drive rolls the drive back to an older version of
            # the chain - and in Mirror mode deletes tracks the drive still has.
            # Such a client has to hear from its host first.
            drive_ts = drive_last_synced_timestamp(dest_path)
            client_ts = parse_sync_timestamp(matching_cc.get('last_synced'))
            try:
                drive_tracks = filter_audio_files(dest_path)
            except Exception:
                drive_tracks = []
            # A drive with nothing on it has nothing to lose, and a client with no
            # recorded sync is assumed stale rather than trusted.
            is_retrograde = bool(drive_tracks) and drive_ts is not None and (
                client_ts is None or client_ts < drive_ts - SYNC_RETROGRADE_GRACE_SECONDS)

            # 1. Sync client from host first over network
            if status_cb:
                if is_retrograde:
                    status_cb(f"[USB Sync: {chain_name}] This PC's copy is older than the drive's; "
                              f"refreshing from host before writing...")
                status_cb(f"[USB Sync: {chain_name}] Step 1/2: Updating client chain from host...")
            ok, msg, t, d = SyncClientWorker.sync_chain(matching_cc, status_cb=status_cb, progress_cb=progress_cb)
            if ok:
                # This copy genuinely did just come off the host, so say so. Without
                # the stamp the drive would look newer than this PC after every
                # successful USB sync, and the question would come back on the next
                # plug-in.
                matching_cc['last_synced'] = time.time()
                try:
                    config_manager.save()
                except Exception:
                    pass
            if not ok:
                if is_retrograde:
                    # The host is out of reach, so the only copy this PC can offer
                    # is older than what the drive already holds. Rolling a newer
                    # drive back is the user's call, not the sync's.
                    if status_cb:
                        status_cb(f"[USB Sync: {chain_name}] Drive holds a newer version and the host is "
                                  f"unreachable - asking before overwriting...")
                    question = (
                        f"Syncing '{chain_name}' would replace the copy on '{dest_path}' with an older one.\n\n"
                        f"Drive last synced: {format_sync_timestamp(drive_ts)} "
                        f"({len(drive_tracks)} track(s) on it)\n"
                        f"This PC last synced: {format_sync_timestamp(client_ts)}\n\n"
                        f"The host for Sync Code {sync_code} could not be reached:\n{msg}\n\n"
                        "Sync an older version of the chain onto the drive anyway?"
                    )
                    if confirm_cb is None or not confirm_cb(question):
                        return False, ("Sync skipped: the drive holds a newer version of this chain and the host "
                                       "could not be reached, so this PC's older copy was not written to the drive."), 0, 0
                if status_cb:
                    status_cb(f"[USB Sync: {chain_name}] Host offline, syncing with local client cache...")

            if status_cb:
                status_cb(f"[USB Sync: {chain_name}] Step 2/2: Syncing local files to removable device...")
            ok2, msg2, transferred, deleted = SyncRemovableWorker.sync_local_folders(src_dir, dest_path, del_mode, status_cb, progress_cb)
            if ok2:
                write_sync_tag_file(
                    dest_path,
                    sync_code=sync_code,
                    chain_name=chain_name,
                    sync_style='Mirror' if del_mode == 'mirror' else 'Additive',
                    last_synced_by='Client',
                    parent_sync_folder=str(matching_cc.get('folder_path', ''))
                )
            return ok2, msg2, transferred, deleted

        else:
            return False, f"No hosted or client sync chain with Sync Code {sync_code} found on this PC.", 0, 0


class RemovableSyncThread(QThread):
    status_signal = Signal(str)
    progress_signal = Signal(int, int, str, int, int)
    finished_signal = Signal(bool, str, int, int)
    confirm_signal = Signal(str, str)  # (chain id, question) - parked until answer_confirm()

    def __init__(self, removable_config: dict, config_manager: SyncConfigManager):
        super().__init__()
        self.removable_config = removable_config
        self.config_manager = config_manager
        # Only MainApp turns this on, and only because it can put the question on
        # screen. Left off, a sync that needs asking simply proceeds.
        self.confirm_enabled = False
        self._confirm_event = threading.Event()
        self._confirm_answer = True

    def answer_confirm(self, proceed: bool):
        """The GUI thread's reply to a confirm_signal this thread emitted."""
        self._confirm_answer = bool(proceed)
        self._confirm_event.set()

    def run(self):
        chain_id = str(self.removable_config.get('id', ''))

        def _status(txt):
            self.status_signal.emit(txt)

        def _progress(done, total, filename, idx, total_items):
            self.progress_signal.emit(done, total, filename, idx, total_items)

        def _confirm(message: str) -> bool:
            """Ask the user on the GUI thread and wait here for the answer."""
            if not self.confirm_enabled:
                return True
            self._confirm_event.clear()
            self._confirm_answer = True
            self.confirm_signal.emit(chain_id, message)
            while not self._confirm_event.wait(timeout=0.5):
                if self.isInterruptionRequested():
                    return False
            return bool(self._confirm_answer)

        ok, msg, transferred, deleted = SyncRemovableWorker.sync_removable_chain(
            self.removable_config,
            self.config_manager,
            status_cb=_status,
            progress_cb=_progress,
            confirm_cb=_confirm
        )
        self.finished_signal.emit(ok, msg, transferred, deleted)


class CreateHostChainDialog(QDialog):
    """Dialog to create a new hosted Sync Chain."""
    def __init__(self, parent_window, config_manager: SyncConfigManager):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.config_manager = config_manager
        self.setWindowTitle("Create Sync Chain (Host)")
        self.setFixedSize(520, 360)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title_lbl = QLabel("CREATE A NEW SYNC CHAIN (HOST)")
        title_lbl.setFont(QFont("Segoe UI Semibold", 11))
        layout.addWidget(title_lbl)

        desc = QLabel("You will host this folder on your local network. Other yt-msd clients with your sync code can connect and sync audio files.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(desc)

        layout.addWidget(QLabel("Playlist / Sync Chain Name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Rock Classics")
        layout.addWidget(self.name_edit)

        layout.addWidget(QLabel("Master Audio Folder to Sync:"))
        folder_h = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Select folder...")
        self.folder_edit.textChanged.connect(self._update_file_count)
        folder_h.addWidget(self.folder_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.setToolTip("Browse for the master audio folder to sync")
        browse_btn.clicked.connect(self._browse_folder)
        folder_h.addWidget(browse_btn)
        layout.addLayout(folder_h)

        self.count_lbl = QLabel("0 audio files detected (subfolders/zips ignored)")
        self.count_lbl.setStyleSheet("color: #3B8ED0; font-size: 11px;")
        layout.addWidget(self.count_lbl)

        options_h = QHBoxLayout()
        options_h.addWidget(QLabel("Sync Code (4-digit):"))
        self.code_edit = QLineEdit(self.config_manager.generate_unique_sync_code())
        self.code_edit.setFixedWidth(70)
        options_h.addWidget(self.code_edit)

        options_h.addSpacing(20)
        options_h.addWidget(QLabel("Change Notify Delay:"))
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(1, 60)
        self.delay_spin.setValue(5)
        self.delay_spin.setSuffix(" min")
        options_h.addWidget(self.delay_spin)
        options_h.addStretch()
        layout.addLayout(options_h)

        layout.addStretch()

        btn_h = QHBoxLayout()
        btn_h.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_h.addWidget(cancel_btn)

        create_btn = QPushButton("Create Chain")
        create_btn.setToolTip("Create the sync chain and start hosting")
        create_btn.clicked.connect(self._create_chain)
        btn_h.addWidget(create_btn)
        layout.addLayout(btn_h)

    def _browse_folder(self):
        f = QFileDialog.getExistingDirectory(self, "Select Master Audio Folder", self.folder_edit.text() or "")
        if f:
            self.folder_edit.setText(f)
            if not self.name_edit.text().strip():
                self.name_edit.setText(Path(f).name)

    def _update_file_count(self, path_str: str):
        p = Path(path_str)
        if p.is_dir():
            files = filter_audio_files(p)
            self.count_lbl.setText(f"✔ {len(files)} audio files detected (non-audio & subfolders ignored)")
            self.count_lbl.setStyleSheet("color: #1abd33; font-size: 11px;")
        else:
            self.count_lbl.setText("Folder does not exist or is invalid")
            self.count_lbl.setStyleSheet("color: #E31E24; font-size: 11px;")

    def _create_chain(self):
        name = self.name_edit.text().strip()
        folder = self.folder_edit.text().strip()
        code = self.code_edit.text().strip()
        delay = self.delay_spin.value()

        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a name for this sync chain.")
            return
        if not folder or not Path(folder).is_dir():
            QMessageBox.warning(self, "Invalid Folder", "Please select a valid folder containing your audio files.")
            return
        if not code.isdigit() or len(code) != 4:
            QMessageBox.warning(self, "Invalid Code", "Sync code must be a 4-digit number (e.g. 1002).")
            return

        self.config_manager.add_hosted_chain(name, folder, code, notify_delay_mins=delay)
        self.accept()


class ConnectClientChainDialog(QDialog):
    """Dialog to connect to a remote Host's Sync Chain."""
    def __init__(self, parent_window, config_manager: SyncConfigManager):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.config_manager = config_manager
        self.setWindowTitle("Connect to Sync Chain (Client)")
        self.setFixedSize(520, 390)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title_lbl = QLabel("CONNECT TO A REMOTE SYNC CHAIN")
        title_lbl.setFont(QFont("Segoe UI Semibold", 11))
        layout.addWidget(title_lbl)

        desc = QLabel("Enter the Host PC's IP address and 4-digit Sync Code to subscribe to their sync chain.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(desc)

        layout.addWidget(QLabel("Host Computer IP Address:"))
        self.ip_edit = QLineEdit()
        self.ip_edit.setPlaceholderText("e.g. 192.168.1.50")
        layout.addWidget(self.ip_edit)

        layout.addWidget(QLabel("4-Digit Sync Code:"))
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("e.g. 1002")
        self.code_edit.setFixedWidth(100)
        layout.addWidget(self.code_edit)

        layout.addWidget(QLabel("Local Base Folder where files should be synced:"))
        folder_h = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Base folder (e.g. C:\\Music)...")
        folder_h.addWidget(self.folder_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.setToolTip("Browse for the local folder to sync into")
        browse_btn.clicked.connect(self._browse_base_folder)
        folder_h.addWidget(browse_btn)
        layout.addLayout(folder_h)

        layout.addWidget(QLabel("Playlist / Subfolder Name:"))
        self.playlist_name_edit = QLineEdit()
        self.playlist_name_edit.setPlaceholderText("e.g. Rock Classics")
        layout.addWidget(self.playlist_name_edit)

        layout.addWidget(QLabel("Sync / Deletion Mode:"))
        self.del_mode_combo = QComboBox()
        self.del_mode_combo.addItem("Mirror Mode (Default: Sync all files, update edits & delete removed files)", "mirror")
        self.del_mode_combo.addItem("Additive Mode (Only download new/updated files, keep local files)", "additive")
        layout.addWidget(self.del_mode_combo)

        layout.addStretch()

        btn_h = QHBoxLayout()
        btn_h.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_h.addWidget(cancel_btn)

        connect_btn = QPushButton("Connect & Join")
        connect_btn.setToolTip("Connect to the remote sync chain")
        connect_btn.clicked.connect(self._connect_chain)
        btn_h.addWidget(connect_btn)
        layout.addLayout(btn_h)

    def _browse_base_folder(self):
        f = QFileDialog.getExistingDirectory(self, "Select Base Music Directory", self.folder_edit.text() or "")
        if f:
            self.folder_edit.setText(f)

    def _connect_chain(self):
        ip = self.ip_edit.text().strip()
        code = self.code_edit.text().strip()
        base_folder = self.folder_edit.text().strip()
        subfolder = self.playlist_name_edit.text().strip()
        del_mode = self.del_mode_combo.currentData()

        if not ip:
            QMessageBox.warning(self, "Missing IP", "Please enter the Host computer IP address.")
            return
        if not code.isdigit() or len(code) != 4:
            QMessageBox.warning(self, "Invalid Code", "Sync code must be a 4-digit number (e.g. 1002).")
            return
        if not base_folder or not Path(base_folder).exists():
            QMessageBox.warning(self, "Invalid Folder", "Please select a valid base folder on your computer.")
            return
        if not subfolder:
            QMessageBox.warning(self, "Missing Name", "Please enter a name for the playlist folder.")
            return

        full_dest_path = str(Path(base_folder) / subfolder)
        self.config_manager.add_client_chain(
            name=subfolder,
            folder_path=full_dest_path,
            sync_code=code,
            host_ip=ip,
            deletion_mode=del_mode
        )
        self.accept()


class RemovableInitThread(QThread):
    """Creates the target folder and writes the initial TAG.yaml off the GUI thread."""
    done_signal = Signal(bool, str, str)  # ok, error message, folder path

    def __init__(self, dest_path: Path, sync_code: str, chain_name: str,
                 del_mode: str, last_synced_by: str, parent_folder: str):
        super().__init__()
        self.dest_path = dest_path
        self.sync_code = sync_code
        self.chain_name = chain_name
        self.del_mode = del_mode
        self.last_synced_by = last_synced_by
        self.parent_folder = parent_folder

    def run(self):
        drive_lock = get_drive_io_lock(self.dest_path)
        drive_lock.acquire()
        try:
            try:
                self.dest_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                self.done_signal.emit(False, f"Could not create folder on drive:\n{e}", "")
                return

            # Write the initial TAG.yaml (all config lives here, not in local config)
            ok = write_sync_tag_file(
                self.dest_path,
                sync_code=self.sync_code,
                chain_name=self.chain_name,
                sync_style='Mirror' if self.del_mode == 'mirror' else 'Additive',
                last_synced_by=self.last_synced_by,
                parent_sync_folder=self.parent_folder
            )
            if ok:
                self.done_signal.emit(True, "", str(self.dest_path))
            else:
                self.done_signal.emit(False, f"Failed to write TAG.yaml file to {self.dest_path}.", "")
        finally:
            drive_lock.release()


class ConnectRemovableMediaDialog(QDialog):
    """Dialog to configure and sync a chain onto a Removable Storage Drive (USB/SD Card/MP3 Player)."""
    def __init__(self, parent_window, config_manager: SyncConfigManager):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.config_manager = config_manager
        self.setWindowTitle("Connect Removable Media (USB / SD Card / MP3 Player)")
        self.setFixedSize(540, 440)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title_lbl = QLabel("CONNECT REMOVABLE MEDIA SYNC")
        title_lbl.setFont(QFont("Segoe UI Semibold", 11))
        layout.addWidget(title_lbl)

        desc = QLabel("Tag and synchronize a playlist to a removable USB flash drive, SD card, or portable MP3 player. A TAG.yaml file will be placed in the folder to identify it.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(desc)

        # 1. Select Sync Chain
        layout.addWidget(QLabel("Select Sync Chain to Mirror:"))
        self.chain_combo = QComboBox()
        
        all_chains = []
        for hc in self.config_manager.hosted_chains:
            all_chains.append(("Host", hc))
        for cc in self.config_manager.client_chains:
            all_chains.append(("Client", cc))

        if not all_chains:
            self.chain_combo.addItem("No active chains (Create or join a chain first)", None)
            self.chain_combo.setEnabled(False)
        else:
            for c_type, c in all_chains:
                label = f"[{c_type}] {c.get('name', 'Chain')} (Sync Code: {c.get('sync_code')})"
                self.chain_combo.addItem(label, (c_type, c))

        layout.addWidget(self.chain_combo)

        # 2. Target Removable Drive / Folder
        layout.addWidget(QLabel("Target Removable Drive or Folder:"))
        folder_h = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Select drive or folder on USB/SD card (e.g. E:\\Music)...")
        folder_h.addWidget(self.folder_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.setToolTip("Browse for the removable drive or folder")
        browse_btn.clicked.connect(self._browse_folder)
        folder_h.addWidget(browse_btn)
        layout.addLayout(folder_h)

        # Detected removable drives quick buttons. The list comes from the
        # background drive probe's cache: probing all 26 letters here would stat
        # every root on the GUI thread, and a busy MP3 player can sit on one of
        # those calls for seconds.
        detected_drives = []
        app = getattr(self.parent_window, 'parent_app', None)
        cached_drives = getattr(app, 'known_connected_drives', None) if app is not None else None
        if cached_drives:
            detected_drives = sorted(d for d in cached_drives if d.upper() != "C:\\")
        elif sys.platform == 'win32':
            import string
            for letter in string.ascii_uppercase:
                d = f"{letter}:\\"
                if d.upper() != "C:\\" and os.path.exists(d):
                    detected_drives.append(d)

        if detected_drives:
            quick_h = QHBoxLayout()
            quick_lbl = QLabel("Detected Drives:")
            quick_lbl.setStyleSheet("color: #888; font-size: 11px;")
            quick_h.addWidget(quick_lbl)
            for d in detected_drives:
                d_btn = QPushButton(d)
                d_btn.setFixedHeight(22)
                d_btn.setToolTip(f"Use drive {d}")
                d_btn.setStyleSheet("font-size: 11px; padding: 2px 6px;")
                d_btn.clicked.connect(lambda chk=False, drv=d: self._set_drive(drv))
                quick_h.addWidget(d_btn)
            quick_h.addStretch()
            layout.addLayout(quick_h)

        # Subfolder name
        layout.addWidget(QLabel("Playlist / Subfolder Name on Drive:"))
        self.subfolder_edit = QLineEdit()
        self._update_subfolder_placeholder()
        self.chain_combo.currentIndexChanged.connect(self._update_subfolder_placeholder)
        layout.addWidget(self.subfolder_edit)

        # Deletion mode
        layout.addWidget(QLabel("Sync Style:"))
        self.del_mode_combo = QComboBox()
        self.del_mode_combo.addItem("Mirror (Sync all files, delete removed files)", "mirror")
        self.del_mode_combo.addItem("Additive (Only download new/updated, keep existing files)", "additive")
        layout.addWidget(self.del_mode_combo)

        layout.addStretch()

        btn_h = QHBoxLayout()
        btn_h.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_h.addWidget(cancel_btn)

        self.connect_btn = QPushButton("Connect & Initialize Drive")
        self.connect_btn.setToolTip("Connect and initialize the removable drive")
        self.connect_btn.clicked.connect(self._connect_removable)
        btn_h.addWidget(self.connect_btn)
        layout.addLayout(btn_h)

    def _set_drive(self, drive_str: str):
        self.folder_edit.setText(drive_str)

    def _update_subfolder_placeholder(self):
        data = self.chain_combo.currentData()
        if data:
            _, chain = data
            self.subfolder_edit.setText(chain.get('name', ''))

    def _browse_folder(self):
        f = QFileDialog.getExistingDirectory(self, "Select Removable Folder / Drive", self.folder_edit.text() or "")
        if f:
            self.folder_edit.setText(f)

    def _connect_removable(self):
        data = self.chain_combo.currentData()
        if not data:
            QMessageBox.warning(self, "No Chain Selected", "Please create or connect to a sync chain before adding removable media.")
            return

        c_type, chain = data
        base_dir = self.folder_edit.text().strip()
        subfolder = self.subfolder_edit.text().strip()
        del_mode = self.del_mode_combo.currentData()
        sync_code = str(chain.get('sync_code', ''))

        if not base_dir:
            QMessageBox.warning(self, "Missing Folder", "Please select a target folder or drive on the removable device.")
            return

        dest_path = Path(base_dir)
        if subfolder:
            dest_path = dest_path / subfolder

        name = subfolder or chain.get('name', 'Removable Drive')
        parent_folder = chain.get('folder_path', '')
        sync_code = str(chain.get('sync_code', ''))
        chain_name = chain.get('name', name)

        app = getattr(self.parent_window, 'parent_app', None)
        if app is None:
            app = self.parent_window  # SyncManagerDialog -> parent_app

        rc = {
            'id': make_removable_chain_id(sync_code, str(dest_path)),
            'sync_code': sync_code,
            'name': chain_name,
            'folder_path': str(dest_path),
            'deletion_mode': del_mode,
            'last_synced': '',
            'status': 'Ready',
            'drive_root': str(Path(base_dir).anchor),
        }

        # Creating the folder and writing TAG.yaml means talking to the drive.
        # That happens on a worker thread so a slow player cannot freeze this
        # dialog - or the rest of the app - while it thinks about it.
        self._pending_rc = rc
        self._pending_app = app
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("Initializing drive...")

        thread = RemovableInitThread(dest_path, sync_code, chain_name, del_mode, c_type, parent_folder)
        self._init_thread = thread
        thread.done_signal.connect(self._on_drive_initialized)
        thread.start()

    def _on_drive_initialized(self, ok: bool, msg: str, dest_path: str):
        if not ok:
            self.connect_btn.setEnabled(True)
            self.connect_btn.setText("Connect & Initialize Drive")
            QMessageBox.warning(self, "Invalid Path", msg)
            return

        rc = self._pending_rc
        app = self._pending_app
        # Register in the runtime active drives dict and immediately sync
        with app._runtime_state_lock:
            app.active_removable_drives[str(rc['folder_path'])] = rc
            if hasattr(app, 'mount_state'):
                app.mount_state[str(rc['folder_path'])] = True
        self.accept()
        if hasattr(app, '_auto_sync_removable_chain'):
            QTimer.singleShot(50, lambda r=rc: app._auto_sync_removable_chain(r))


class SyncManagerDialog(QDialog):
    """Main Sync Chains Management Dialog with Host, Client, and Removable Drive cards and live transfer tracking."""
    def __init__(self, parent_app):
        super().__init__(parent_app)
        self.parent_app = parent_app
        self.config_manager: SyncConfigManager = parent_app.sync_config_manager
        self.setWindowTitle("Sync Chains Manager - Local Network Playlist Sync")
        self.resize(920, 620)

        # Check Windows Firewall rule every time the sync window opens
        self._check_firewall_rule()

        # Reference the app-level sync_threads dict (persists across dialog open/close)
        self.sync_threads = parent_app.sync_threads

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(12)

        top_bar = QHBoxLayout()
        local_ip = get_local_ip()
        self.ip_badge = QLabel(f"Your Local IP: <b>{local_ip}</b>")
        self.ip_badge.setStyleSheet("background: rgba(59, 142, 208, 0.15); border: 1px solid #3B8ED0; padding: 6px 12px; border-radius: 4px; font-size: 12px;")
        top_bar.addWidget(self.ip_badge)

        copy_ip_btn = QPushButton("Copy IP")
        copy_ip_btn.setFixedWidth(75)
        copy_ip_btn.setToolTip("Copy your local IP address")
        copy_ip_btn.clicked.connect(lambda: QApplication.clipboard().setText(local_ip))
        top_bar.addWidget(copy_ip_btn)

        top_bar.addStretch()

        create_btn = QPushButton("Create Chain (Host)")
        create_btn.setToolTip("Host a folder as a sync chain")
        create_btn.clicked.connect(self._open_create_dialog)
        top_bar.addWidget(create_btn)

        connect_btn = QPushButton("Connect Chain (Client)")
        connect_btn.setToolTip("Connect to an existing sync chain")
        connect_btn.clicked.connect(self._open_connect_dialog)
        top_bar.addWidget(connect_btn)

        removable_btn = QPushButton("Connect Removable Drive (USB)")
        removable_btn.setToolTip("Sync a playlist to a USB / SD drive")
        removable_btn.clicked.connect(self._open_removable_dialog)
        top_bar.addWidget(removable_btn)

        sync_all_btn = QPushButton("Force Sync All")
        sync_all_btn.setToolTip("Force a sync of all chains now")
        sync_all_btn.clicked.connect(self._force_sync_all)
        top_bar.addWidget(sync_all_btn)

        main_layout.addLayout(top_bar)

        settings_bar = QHBoxLayout()
        settings_bar.addWidget(QLabel("Client Auto-Sync Frequency (minutes):"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 1440)
        self.interval_spin.setValue(self.config_manager.settings.get('auto_sync_interval_mins', 30))
        self.interval_spin.setSuffix(" min")
        self.interval_spin.valueChanged.connect(self._update_interval)
        settings_bar.addWidget(self.interval_spin)

        settings_bar.addSpacing(20)
        self.host_port_lbl = QLabel(f"Host Server: Port {getattr(parent_app.sync_host_server, 'active_port', 'Offline')}")
        self.host_port_lbl.setStyleSheet("color: #888; font-size: 11px;")
        settings_bar.addWidget(self.host_port_lbl)

        settings_bar.addStretch()
        main_layout.addLayout(settings_bar)

        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setObjectName("scrollContent")
        self.cards_scroll.setAttribute(Qt.WA_StyledBackground, True)

        self.cards_container = QWidget()
        self.cards_container.setObjectName("scrollContent")
        self.cards_container.setAttribute(Qt.WA_StyledBackground, True)
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(6, 6, 6, 6)
        self.cards_layout.setSpacing(10)
        self.cards_scroll.setWidget(self.cards_container)
        main_layout.addWidget(self.cards_scroll, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(100)
        close_btn.setToolTip("Close this window")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        main_layout.addLayout(footer)

        self.refresh_cards()

    def _check_firewall_rule(self):
        """Binds to sync ports and triggers the Windows Firewall permission alert if no rule exists yet."""
        if sys.platform != 'win32':
            return
        def _bg_firewall():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('0.0.0.0', 0))
                s.listen(1)
                port = s.getsockname()[1]
                try:
                    c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    c.settimeout(0.2)
                    c.connect(('127.0.0.1', port))
                    c.close()
                except Exception:
                    pass
                s.close()

                s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s2.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s2.bind(('0.0.0.0', 0))
                port2 = s2.getsockname()[1]
                try:
                    s2.sendto(b'probe', ('127.0.0.1', port2))
                except Exception:
                    pass
                s2.close()
            except Exception:
                pass
        threading.Thread(target=_bg_firewall, daemon=True).start()

    def showEvent(self, event):
        super().showEvent(event)
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        # Hide instead of closing so thread references and state survive across open/close cycles
        event.ignore()
        self.hide()
        if self.parent_app:
            self.parent_app.raise_()
            self.parent_app.activateWindow()

    def accept(self):
        # Hide instead of accepting (would destroy the dialog with exec())
        self.hide()
        if self.parent_app:
            self.parent_app.raise_()
            self.parent_app.activateWindow()

    def reject(self):
        # Hide instead of rejecting
        self.hide()
        if self.parent_app:
            self.parent_app.raise_()
            self.parent_app.activateWindow()

    def _update_interval(self, val: int):
        self.config_manager.settings['auto_sync_interval_mins'] = val
        self.config_manager.save()
        if hasattr(self.parent_app, '_update_sync_timer'):
            self.parent_app._update_sync_timer()

    def _open_create_dialog(self):
        dlg = CreateHostChainDialog(self, self.config_manager)
        if dlg.exec():
            self.config_manager.save()
            self.parent_app.refresh_sync_watchers()
            self.refresh_cards()

    def _open_connect_dialog(self):
        dlg = ConnectClientChainDialog(self, self.config_manager)
        if dlg.exec():
            self.config_manager.save()
            self.refresh_cards()
            if self.config_manager.client_chains:
                self._sync_single_client_chain(self.config_manager.client_chains[-1])

    def showEvent(self, event):
        super().showEvent(event)
        # Immediately scan drives so cards appear as soon as the dialog opens
        if hasattr(self.parent_app, '_check_removable_drives_change'):
            self.parent_app._check_removable_drives_change()
        QTimer.singleShot(300, self.refresh_cards)

    def _open_removable_dialog(self):
        dlg = ConnectRemovableMediaDialog(self, self.config_manager)
        if dlg.exec():
            # Defer refresh to ensure dialog destruction is completed
            QTimer.singleShot(50, self.refresh_cards)

    def _cards_signature(self) -> tuple:
        """Cheap, I/O-free description of everything the cards currently show."""
        mount_state = getattr(self.parent_app, 'mount_state', {})
        counts = getattr(self.parent_app, 'chain_track_counts', {}) or {}
        hosted = tuple(
            (hc.get('id'), hc.get('name'), str(hc.get('sync_code', '')), hc.get('folder_path'),
             counts.get(hc.get('id')))
            for hc in self.config_manager.hosted_chains
        )
        clients = tuple(
            (cc.get('id'), cc.get('name'), str(cc.get('sync_code', '')), cc.get('last_known_host_ip', ''),
             bool(is_client_chain_paused(cc)[0]), cc.get('wifi_ssid', ''), cc.get('status', ''))
            for cc in self.config_manager.client_chains
        )
        removables = tuple(
            (rc.get('id'), rc.get('name'), rc.get('folder_path'), rc.get('status', ''),
             str(rc.get('last_synced', '')), bool(mount_state.get(rc.get('folder_path'), True)))
            for rc in getattr(self.parent_app, 'active_removable_drives', {}).values()
        )
        return (hosted, clients, removables)

    def _open_folder(self, folder_str: str):
        """Hand the path straight to the shell instead of stat()ing a drive that
        may be busy with a sync right now."""
        if not folder_str:
            return
        try:
            os.startfile(folder_str)
        except Exception:
            pass

    def refresh_cards(self, force: bool = False):
        # The background drive probe runs every few seconds. Tearing down and
        # rebuilding every card on each pass is pure churn, so skip the rebuild
        # whenever nothing about the chains has actually changed.
        signature = self._cards_signature()
        if (not force and self.cards_layout.count()
                and signature == getattr(self, '_cards_signature_state', None)):
            self._restore_in_progress_labels()
            return
        self._cards_signature_state = signature

        # Preserve scroll position so rescans don't jump back to the top
        scroll_bar = self.cards_scroll.verticalScrollBar()
        saved_scroll = scroll_bar.value() if scroll_bar else 0

        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                w = item.widget()
                w.setParent(None)
                w.deleteLater()

        hosted = self.config_manager.hosted_chains
        clients = self.config_manager.client_chains
        removables = list(getattr(self.parent_app, 'active_removable_drives', {}).values())

        if not hosted and not clients and not removables:
            empty_lbl = QLabel("No active Sync Chains. Click 'Create Chain' to host a folder, 'Connect Chain' to join an existing one, or plug in a USB drive tagged with TAG.yaml.")
            empty_lbl.setAlignment(Qt.AlignCenter)
            empty_lbl.setStyleSheet("color: #888; padding: 40px; font-size: 13px;")
            self.cards_layout.addWidget(empty_lbl)
            self.cards_layout.addStretch()
            self.cards_container.adjustSize()
            self.cards_container.update()
            return

        if hosted:
            sec_lbl = QLabel("HOSTED SYNC CHAINS (This computer is sharing)")
            sec_lbl.setFont(QFont("Segoe UI Semibold", 10))
            sec_lbl.setStyleSheet("color: #3B8ED0; margin-top: 6px;")
            self.cards_layout.addWidget(sec_lbl)

            for hc in hosted:
                card = self._build_host_card(hc)
                self.cards_layout.addWidget(card)

        if clients:
            sec_lbl2 = QLabel("CLIENT SYNC CHAINS (Subscribed to remote hosts)")
            sec_lbl2.setFont(QFont("Segoe UI Semibold", 10))
            sec_lbl2.setStyleSheet("color: #1abd33; margin-top: 14px;")
            self.cards_layout.addWidget(sec_lbl2)

            for cc in clients:
                card = self._build_client_card(cc)
                self.cards_layout.addWidget(card)

        if removables:
            sec_lbl3 = QLabel("REMOVABLE MEDIA SYNC (USB Flash Drives / SD Cards / MP3 Players)")
            sec_lbl3.setFont(QFont("Segoe UI Semibold", 10))
            sec_lbl3.setStyleSheet("color: #9B59B6; margin-top: 14px;")
            self.cards_layout.addWidget(sec_lbl3)

            for rc in removables:
                card = self._build_removable_card(rc)
                self.cards_layout.addWidget(card)

        self.cards_layout.addStretch()
        # Immediately restore live status/progress for any in-progress syncs
        self._restore_in_progress_labels()
        self.cards_container.adjustSize()
        self.cards_container.update()
        # Restore scroll position after layout rebuild
        QTimer.singleShot(0, lambda: self.cards_scroll.verticalScrollBar().setValue(saved_scroll))

    def _build_host_card(self, hc: dict) -> QWidget:
        card = QFrame()
        card.setProperty("chain_id", hc.get('id'))
        card.setProperty("sync_code", str(hc.get('sync_code', '')))
        card.setStyleSheet("background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; padding: 8px;")
        l = QVBoxLayout(card)
        l.setContentsMargins(10, 8, 10, 8)
        l.setSpacing(6)

        header = QHBoxLayout()
        badge = QLabel("HOST")
        badge.setStyleSheet("background: #3B8ED0; color: white; padding: 2px 6px; border-radius: 3px; font-weight: bold; font-size: 10px;")
        header.addWidget(badge)

        name_lbl = QLabel(f"<b>{hc.get('name', 'Audio Playlist')}</b>")
        name_lbl.setFont(QFont("Segoe UI", 12))
        header.addWidget(name_lbl)

        header.addSpacing(10)
        code_lbl = QLabel(f"Sync Code: <b style='color: #FF8C00;'>{hc.get('sync_code')}</b>")
        header.addWidget(code_lbl)

        header.addStretch()

        copy_code_btn = QPushButton("Copy Code")
        copy_code_btn.setFixedWidth(105)
        copy_code_btn.setToolTip("Copy the sync code")
        code_val = str(hc.get('sync_code', ''))
        copy_code_btn.clicked.connect(lambda chk=False, c=code_val: QApplication.clipboard().setText(c))
        header.addWidget(copy_code_btn)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(26, 26)
        del_btn.setToolTip("Delete this hosted sync chain")
        del_btn.setStyleSheet("background: #E31E24; color: white; border: none; border-radius: 3px; font-weight: bold;")
        cid_val = hc.get('id')
        del_btn.clicked.connect(lambda chk=False, cid=cid_val: self._delete_chain(cid))
        header.addWidget(del_btn)

        l.addLayout(header)

        folder_str = hc.get('folder_path', '')
        # Track counts come from the background probe's cache: counting files
        # here would scan the folder on the GUI thread.
        counts = getattr(self.parent_app, 'chain_track_counts', {}) or {}
        audio_cnt = counts.get(hc.get('id'))
        cnt_str = f" ({audio_cnt} tracks)" if audio_cnt is not None else ""

        host_activity_lbl = QLabel("Status: Ready (Serving clients)")
        host_activity_lbl.setStyleSheet("color: #888; font-size: 11px;")
        card.setProperty("host_activity_lbl", host_activity_lbl)
        l.addWidget(host_activity_lbl)

        info_h = QHBoxLayout()
        path_lbl = QLabel(f"Path: {folder_str}{cnt_str}")
        path_lbl.setStyleSheet("color: #888; font-size: 11px;")
        info_h.addWidget(path_lbl, 1)

        open_btn = QPushButton("Open Folder")
        open_btn.setToolTip("Open this folder in File Explorer")
        open_btn.setFixedWidth(115)
        open_btn.clicked.connect(lambda chk=False, f=folder_str: self._open_folder(f))
        info_h.addWidget(open_btn)

        l.addLayout(info_h)
        return card

    def _on_host_activity_received(self, sync_code: str, client_ip: str, activity: str):
        """Updates host card in UI when a client connects or downloads files."""
        for i in range(self.cards_layout.count()):
            item = self.cards_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if w.property("sync_code") == str(sync_code):
                    lbl = w.property("host_activity_lbl")
                    if lbl:
                        lbl.setText(f"Active Sync Event: {activity} ({client_ip})")
                        lbl.setStyleSheet("color: #1abd33; font-size: 11px; font-weight: bold;")
                        def _reset(_l=lbl):
                            try:
                                _l.setText("Status: Ready (Serving clients)")
                                _l.setStyleSheet("color: #888; font-size: 11px;")
                            except Exception:
                                pass
                        QTimer.singleShot(4000, _reset)

    def _build_client_card(self, cc: dict) -> QWidget:
        card = QFrame()
        cid_val = cc.get('id')
        card.setProperty("chain_id", cid_val)
        card.setStyleSheet("background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; padding: 8px;")
        l = QVBoxLayout(card)
        l.setContentsMargins(10, 8, 10, 8)
        l.setSpacing(6)

        header = QHBoxLayout()
        badge = QLabel("CLIENT")
        badge.setStyleSheet("background: #1abd33; color: white; padding: 2px 6px; border-radius: 3px; font-weight: bold; font-size: 10px;")
        header.addWidget(badge)

        name_lbl = QLabel(f"<b>{cc.get('name', 'Audio Playlist')}</b>")
        name_lbl.setFont(QFont("Segoe UI", 12))
        header.addWidget(name_lbl)

        header.addSpacing(10)
        code_lbl = QLabel(f"Code: <b style='color: #FF8C00;'>{cc.get('sync_code')}</b> | Host: {cc.get('last_known_host_ip', 'Unknown')}")
        code_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
        header.addWidget(code_lbl)

        header.addStretch()

        # Pause / Resume Sync Controls
        is_paused, pause_until = is_client_chain_paused(cc)
        if is_paused:
            resume_btn = QPushButton("Resume Sync")
            resume_btn.setToolTip("Resume syncing for this chain")
            resume_btn.setStyleSheet("background: #3B8ED0; color: white; font-size: 11px; padding: 3px 8px; border-radius: 4px;")
            resume_btn.clicked.connect(lambda chk=False, cid=cid_val: self._resume_chain_sync(cid))
            header.addWidget(resume_btn)
        else:
            pause_btn = QPushButton("Pause Sync ▾")
            pause_btn.setToolTip("Pause syncing for this chain")
            pause_btn.setStyleSheet("font-size: 11px; padding: 3px 8px;")
            pause_menu = QMenu(self)
            durations = [
                ("30 Minutes", 30 * 60),
                ("1 Hour", 1 * 3600),
                ("2 Hours", 2 * 3600),
                ("5 Hours", 5 * 3600),
                ("12 Hours", 12 * 3600),
                ("24 Hours", 24 * 3600),
                ("1 Week", 7 * 86400),
                # -1 and not 0. pause_client_chain() turns any other duration into
                # "now + duration_seconds", so 0 asked for a pause that had already expired by the
                # time the card was rebuilt: the chain carried on syncing and the card flipped
                # straight back to "Pause Sync". -1 is the sentinel both pause_client_chain() and
                # is_client_chain_paused() already treat as "paused until the user resumes it",
                # which is what this menu entry promises.
                ("Forever (Until Re-enabled)", -1)
            ]
            for label, secs in durations:
                act = pause_menu.addAction(label)
                act.triggered.connect(lambda chk=False, cid=cid_val, s=secs: self._pause_chain_sync(cid, s))
            pause_btn.setMenu(pause_menu)
            header.addWidget(pause_btn)

        # Wi-Fi SSID Auto-Sync Binding Control
        wifi_ssid = cc.get('wifi_ssid', '')
        wifi_btn = QPushButton(f"Wi-Fi: {wifi_ssid}" if wifi_ssid else "Bind Wi-Fi ▾")
        wifi_btn.setToolTip("Bind this chain to a Wi-Fi network")
        wifi_btn.setStyleSheet("font-size: 11px; padding: 3px 8px;" + (" background: rgba(59, 142, 208, 0.25);" if wifi_ssid else ""))
        wifi_menu = QMenu(self)
        # Reuse the Wi-Fi monitor's cached SSID: shelling out to netsh for every
        # card built would make the sync window crawl.
        curr_ssid = getattr(self.parent_app, 'last_wifi_ssid', None)
        if curr_ssid is None:
            curr_ssid = get_current_wifi_ssid()
        if curr_ssid:
            act_cur = wifi_menu.addAction(f"Bind to current network: '{curr_ssid}'")
            act_cur.triggered.connect(lambda chk=False, cid=cid_val, s=curr_ssid: self._bind_chain_wifi(cid, s))
        act_custom = wifi_menu.addAction("Enter Wi-Fi SSID manually...")
        act_custom.triggered.connect(lambda chk=False, cid=cid_val: self._prompt_custom_wifi(cid))
        if wifi_ssid:
            wifi_menu.addSeparator()
            act_clear = wifi_menu.addAction("Unbind Wi-Fi (Sync on any network)")
            act_clear.triggered.connect(lambda chk=False, cid=cid_val: self._bind_chain_wifi(cid, ""))
        wifi_btn.setMenu(wifi_menu)
        header.addWidget(wifi_btn)

        sync_btn = QPushButton("Sync Now")
        sync_btn.setToolTip("Sync this chain now")
        sync_btn.clicked.connect(lambda chk=False, c=cc: self._sync_single_client_chain(c))
        header.addWidget(sync_btn)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(26, 26)
        del_btn.setToolTip("Remove this client sync chain")
        del_btn.setStyleSheet("background: #E31E24; color: white; border: none; border-radius: 3px; font-weight: bold;")
        del_btn.clicked.connect(lambda chk=False, cid=cid_val: self._delete_chain(cid))
        header.addWidget(del_btn)

        l.addLayout(header)

        folder_str = cc.get('folder_path', '')
        last_sync = cc.get('last_synced', 0)
        if isinstance(last_sync, (int, float)) and last_sync > 0:
            last_sync_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_sync))
        elif isinstance(last_sync, str) and last_sync.strip():
            last_sync_str = last_sync.strip()
        else:
            last_sync_str = "Never"
        del_mode = cc.get('deletion_mode', 'mirror').capitalize()

        pause_info = ""
        if is_paused:
            if pause_until > 0:
                p_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(pause_until))
                pause_info = f"  |  <span style='color: #FF8C00; font-weight: bold;'>Paused until {p_time_str}</span>"
            else:
                pause_info = "  |  <span style='color: #FF8C00; font-weight: bold;'>Paused Forever</span>"

        wifi_info = f"  |  <span style='color: #3B8ED0;'>Wi-Fi: {wifi_ssid}</span>" if wifi_ssid else ""

        status_lbl = QLabel(f"Status: {cc.get('status', 'Idle')}  |  Last Synced: {last_sync_str}  |  Mode: {del_mode}{pause_info}{wifi_info}")
        status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        card.setProperty("status_lbl", status_lbl)
        l.addWidget(status_lbl)

        progress_lbl = QLabel("")
        progress_lbl.setStyleSheet("color: #3B8ED0; font-size: 11px;")
        card.setProperty("progress_lbl", progress_lbl)
        l.addWidget(progress_lbl)

        info_h = QHBoxLayout()
        path_lbl = QLabel(f"Path: {folder_str}")
        path_lbl.setStyleSheet("color: #888; font-size: 11px;")
        info_h.addWidget(path_lbl, 1)

        open_btn = QPushButton("Open Folder")
        open_btn.setToolTip("Open this folder in File Explorer")
        open_btn.setFixedWidth(115)
        open_btn.clicked.connect(lambda chk=False, f=folder_str: self._open_folder(f))
        info_h.addWidget(open_btn)

        l.addLayout(info_h)
        return card

    def _build_removable_card(self, rc: dict) -> QWidget:
        card = QFrame()
        cid_val = rc.get('id')
        card.setProperty("chain_id", cid_val)
        card.setStyleSheet("background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; padding: 8px;")
        l = QVBoxLayout(card)
        l.setContentsMargins(10, 8, 10, 8)
        l.setSpacing(6)

        header = QHBoxLayout()
        badge = QLabel("REMOVABLE")
        badge.setStyleSheet("background: #9B59B6; color: white; padding: 2px 6px; border-radius: 3px; font-weight: bold; font-size: 10px;")
        header.addWidget(badge)

        name_lbl = QLabel(f"<b>{rc.get('name', 'Removable Drive')}</b>")
        name_lbl.setFont(QFont("Segoe UI", 12))
        header.addWidget(name_lbl)

        header.addSpacing(10)
        code_lbl = QLabel(f"Code: <b style='color: #FF8C00;'>{rc.get('sync_code')}</b> | Style: {rc.get('deletion_mode', 'mirror').capitalize()}")
        code_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
        header.addWidget(code_lbl)

        header.addStretch()

        sync_btn = QPushButton("Sync Now")
        sync_btn.setToolTip("Sync this chain now")
        sync_btn.clicked.connect(lambda chk=False, r=rc: self._sync_single_removable_chain(r))
        header.addWidget(sync_btn)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(26, 26)
        del_btn.setToolTip("Remove this removable sync chain")
        del_btn.setStyleSheet("background: #E31E24; color: white; border: none; border-radius: 3px; font-weight: bold;")
        del_btn.clicked.connect(lambda chk=False, cid=cid_val: self._delete_chain(cid))
        header.addWidget(del_btn)

        l.addLayout(header)

        folder_str = rc.get('folder_path', '')
        last_sync = rc.get('last_synced', 0)
        if isinstance(last_sync, (int, float)) and last_sync > 0:
            last_sync_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_sync))
        elif isinstance(last_sync, str) and last_sync.strip():
            last_sync_str = last_sync.strip()
        else:
            last_sync_str = "Never"
        # Mount state comes from the background probe's cache. Calling
        # exists() here would block this thread on a drive that is busy
        # syncing somewhere else.
        is_mounted = getattr(self.parent_app, 'mount_state', {}).get(folder_str, True)
        mount_str = "Mounted" if is_mounted else "Drive Not Connected"

        status_lbl = QLabel(f"Status: {rc.get('status', 'Ready')} ({mount_str})  |  Last Synced: {last_sync_str}")
        status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        card.setProperty("status_lbl", status_lbl)
        l.addWidget(status_lbl)

        progress_lbl = QLabel("")
        progress_lbl.setStyleSheet("color: #9B59B6; font-size: 11px;")
        card.setProperty("progress_lbl", progress_lbl)
        l.addWidget(progress_lbl)

        info_h = QHBoxLayout()
        path_lbl = QLabel(f"Path: {folder_str}")
        path_lbl.setStyleSheet("color: #888; font-size: 11px;")
        info_h.addWidget(path_lbl, 1)

        open_btn = QPushButton("Open Folder")
        open_btn.setToolTip("Open this folder in File Explorer")
        open_btn.setFixedWidth(115)
        open_btn.clicked.connect(lambda chk=False, f=folder_str: self._open_folder(f))
        info_h.addWidget(open_btn)

        l.addLayout(info_h)
        return card

    def _pause_chain_sync(self, chain_id: str, duration_seconds: int):
        self.config_manager.pause_client_chain(chain_id, duration_seconds)
        self.refresh_cards()

    def _resume_chain_sync(self, chain_id: str):
        self.config_manager.resume_client_chain(chain_id)
        self.refresh_cards()

    def _bind_chain_wifi(self, chain_id: str, ssid: str):
        self.config_manager.bind_client_wifi(chain_id, ssid)
        self.refresh_cards()

    def _prompt_custom_wifi(self, chain_id: str):
        ssid, ok = QInputDialog.getText(self, "Wi-Fi SSID Binding", "Enter Wi-Fi Network SSID:")
        if ok and ssid.strip():
            self._bind_chain_wifi(chain_id, ssid.strip())

    def _delete_chain(self, chain_id: str):
        if QMessageBox.question(self, "Confirm Removal", "Are you sure you want to remove this sync chain? (Audio files on disk will remain untouched)") == QMessageBox.Yes:
            # Check if removable chain
            removables_dict = getattr(self.parent_app, 'active_removable_drives', {})
            with self.parent_app._runtime_state_lock:
                for f_str, rc in list(removables_dict.items()):
                    if rc.get('id') == chain_id:
                        removables_dict.pop(f_str, None)
                        if hasattr(self.parent_app, 'mount_state'):
                            self.parent_app.mount_state.pop(f_str, None)
                        tag_path = str(Path(rc.get('folder_path', '')) / SYNC_TAG_FILENAME)
                        # Deleting TAG.yaml means talking to the drive, so it is
                        # done in a worker thread rather than in this click handler.
                        def _remove_tag(path=tag_path):
                            try:
                                p = Path(path)
                                if p.exists():
                                    p.unlink()
                            except Exception:
                                pass
                        threading.Thread(target=_remove_tag, daemon=True).start()
            self.config_manager.remove_chain(chain_id)
            if hasattr(self.parent_app, 'refresh_sync_watchers'):
                self.parent_app.refresh_sync_watchers()
            self.refresh_cards(force=True)

    def _sync_single_client_chain(self, cc: dict):
        cid = cc.get('id')
        if cid in self.sync_threads and self.sync_threads[cid].isRunning():
            return

        cc['status'] = "Syncing..."
        self.parent_app.sync_progress_state[cid] = {'status': 'Syncing...', 'progress': ''}
        self.refresh_cards()

        thread = ClientSyncThread(cc)
        self.sync_threads[cid] = thread

        chain_name = cc.get('name', 'Sync')

        def _on_status(txt):
            self.parent_app.sync_progress_state.setdefault(cid, {})['status'] = txt
            self._update_client_card_label(cid, "status_lbl", txt)
            if hasattr(self.parent_app, 'dl_progress_signal'):
                self.parent_app.dl_progress_signal.emit(f"[Sync: {chain_name}] {txt}")

        def _on_progress(done, total, filename, idx, total_items):
            pct = int(done / total * 100) if total > 0 else 0
            prog_txt = f"[{idx}/{total_items}] ({pct}%) {filename}"
            self.parent_app.sync_progress_state.setdefault(cid, {})['progress'] = prog_txt
            self._update_client_card_label(cid, "progress_lbl", prog_txt)
            if hasattr(self.parent_app, 'dl_progress_signal'):
                self.parent_app.dl_progress_signal.emit(f"[Sync: {chain_name}] {prog_txt}")

        def _on_finish(ok, msg, transferred, deleted):
            cc['status'] = "Up to date" if ok else f"Failed: {msg}"
            if ok:
                cc['last_synced'] = time.time()
            self.config_manager.save()
            self.parent_app.sync_progress_state.pop(cid, None)
            self._update_client_card_label(cid, "progress_lbl", "")
            self.refresh_cards()
            if self.parent_app.local_current_path == cc.get('folder_path'):
                # The synced folder may be a slow device: scan it on a worker
                # thread instead of in front of the UI.
                self.parent_app._refresh_local_list_async()
            if hasattr(self.parent_app, 'dl_progress_signal'):
                self.parent_app.dl_progress_signal.emit("")

        thread.status_signal.connect(_on_status)
        thread.progress_signal.connect(_on_progress)
        thread.finished_signal.connect(_on_finish)
        thread.start()

    def _sync_single_removable_chain(self, rc: dict):
        if hasattr(self.parent_app, '_auto_sync_removable_chain'):
            self.parent_app._auto_sync_removable_chain(rc)
            self.refresh_cards()

    def _update_client_card_label(self, chain_id: str, prop_name: str, text: str):
        """Update a visible card's label (status_lbl or progress_lbl) by chain_id."""
        for i in range(self.cards_layout.count()):
            item = self.cards_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if w.property("chain_id") == chain_id:
                    lbl = w.property(prop_name)
                    if lbl:
                        try:
                            lbl.setText(text)
                        except RuntimeError:
                            pass  # widget deleted (dialog closed mid-sync)
                    break

    def _restore_in_progress_labels(self):
        """After refresh_cards(), re-populate status/progress labels for any currently running syncs."""
        state = getattr(self.parent_app, 'sync_progress_state', {})
        threads = getattr(self.parent_app, 'sync_threads', {})
        for cid, ps in state.items():
            thread = threads.get(cid)
            if thread and thread.isRunning():
                if ps.get('status'):
                    self._update_client_card_label(cid, "status_lbl", ps['status'])
                if ps.get('progress'):
                    self._update_client_card_label(cid, "progress_lbl", ps['progress'])

    def _force_sync_all(self):
        # 1. Sync all subscribed client chains
        for cc in self.config_manager.client_chains:
            self._sync_single_client_chain(cc)
        # 2. Sync all removable media chains whose drives are currently
        #    connected. Mount state is read from the background probe's cache so
        #    this click never waits on a busy drive.
        mount_state = getattr(self.parent_app, 'mount_state', {})
        for rc in list(getattr(self.parent_app, 'active_removable_drives', {}).values()):
            if mount_state.get(rc.get('folder_path', ''), True):
                self._sync_single_removable_chain(rc)
        # 3. Push update notification to clients of our hosted chains (force clients to sync)
        port = getattr(self.parent_app.sync_host_server, 'active_port', 0)
        if port > 0:
            codes = [str(hc.get('sync_code')) for hc in self.config_manager.hosted_chains if hc.get('sync_code')]

            def _notify(codes=codes, port=port):
                for code in codes:
                    send_lan_update_notification(code, port)
            threading.Thread(target=_notify, daemon=True).start()
        if hasattr(self.parent_app, 'status_signal'):
            self.parent_app.status_signal.emit("Force Sync initiated: syncing clients & removable drives, notified LAN peers.", False, "#1abd33")


# ═════════════════════════════════════════════════════════════════════════════
# EXPORT / IMPORT PACKAGES
#
# An export package is a single .zip containing:
#   export.yaml             manifest describing everything inside the package
#   config/gui-config.json  GUI settings (never contains sync chain keys unless
#                           "Sync Chains" was checked when exporting)
#   sync/sync-chains.json   hosted chains, client chains and sync settings
#   music/<folder>/...      copies of the music folders that were selected
#
# PyYAML is not a dependency of this app (TAG.yaml is hand-formatted too), so
# the manifest is written and read by the small YAML helpers below. They cover
# exactly the shapes export.yaml needs: nested mappings, lists of scalars, and
# lists of flat mappings.
# ═════════════════════════════════════════════════════════════════════════════

EXPORT_MANIFEST_NAME = "export.yaml"
EXPORT_CONFIG_ENTRY = "config/gui-config.json"
EXPORT_SYNC_ENTRY = "sync/sync-chains.json"
EXPORT_FORMAT_VERSION = 1
SYNC_ONLY_CONFIG_KEYS = ("sync_settings", "hosted_chains", "client_chains")
EXPORT_SKIP_DIRS = {"$recycle.bin", "system volume information", "__pycache__", ".git"}


def _yaml_scalar_repr(value) -> str:
    """Render a single scalar the way the export manifest writes it."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if value is None:
        return "null"
    text = str(value)
    needs_quotes = (
        text == ""
        or text != text.strip()
        or any(ch in text for ch in ("#", "\n", "\r", '"', "'", "\\"))
        or ": " in text
        or text.endswith(":")
        or text[0] in "-?&*!|>%@`{}[]"
        or text.lower() in ("true", "false", "null", "yes", "no", "on", "off")
    )
    return json.dumps(text) if needs_quotes else text


def yaml_dump(data, indent: int = 0) -> str:
    """Serialize the small YAML subset used by export.yaml."""
    pad = " " * indent
    lines: List[str] = []
    if not isinstance(data, dict):
        return "\n".join(lines)
    for key, value in data.items():
        key = str(key)
        if isinstance(value, dict):
            if value:
                lines.append(f"{pad}{key}:")
                lines.append(yaml_dump(value, indent + 2))
            else:
                lines.append(f"{pad}{key}: {{}}")
        elif isinstance(value, list):
            if value:
                lines.append(f"{pad}{key}:")
                lines.append(_yaml_dump_list(value, indent + 2))
            else:
                lines.append(f"{pad}{key}: []")
        else:
            lines.append(f"{pad}{key}: {_yaml_scalar_repr(value)}")
    return "\n".join(lines)


def _yaml_dump_list(items: List, indent: int) -> str:
    pad = " " * indent
    lines: List[str] = []
    for item in items:
        if isinstance(item, dict):
            if not item:
                lines.append(f"{pad}- {{}}")
            elif any(isinstance(value, (dict, list)) for value in item.values()):
                lines.append(f"{pad}-")
                lines.append(yaml_dump(item, indent + 2))
            else:
                pairs = list(item.items())
                first_key, first_value = pairs[0]
                lines.append(f"{pad}- {first_key}: {_yaml_scalar_repr(first_value)}")
                for key, value in pairs[1:]:
                    lines.append(f"{pad}  {key}: {_yaml_scalar_repr(value)}")
        elif isinstance(item, list):
            if item:
                lines.append(f"{pad}-")
                lines.append(_yaml_dump_list(item, indent + 2))
            else:
                lines.append(f"{pad}- []")
        else:
            lines.append(f"{pad}- {_yaml_scalar_repr(item)}")
    return "\n".join(lines)


def _yaml_scalar_parse(body: str):
    """Inverse of _yaml_scalar_repr for the scalar shapes export.yaml uses."""
    body = body.strip()
    if body == "[]":
        return []
    if body == "{}":
        return {}
    if body.startswith('"'):
        try:
            return json.loads(body)
        except Exception:
            return body.strip('"')
    lowered = body.lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    if lowered in ("null", "~", ""):
        return None
    if re.fullmatch(r"-?\d+", body):
        return int(body)
    if re.fullmatch(r"-?\d+\.\d+", body):
        return float(body)
    return body


def yaml_load(text: str) -> dict:
    """Parse export.yaml back into a dict (comments and blank lines are ignored)."""
    lines: List[Tuple[int, str]] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append((len(raw_line) - len(raw_line.lstrip(" ")), stripped))
    if not lines:
        return {}

    pos = 0

    def parse_mapping(indent: int) -> dict:
        nonlocal pos
        result: dict = {}
        while pos < len(lines):
            current_indent, content = lines[pos]
            if current_indent < indent or content.startswith("-"):
                break
            if current_indent > indent:
                pos += 1
                continue
            key, _, rest = content.partition(":")
            key = key.strip().strip('"')
            rest = rest.strip()
            pos += 1
            if rest:
                result[key] = _yaml_scalar_parse(rest)
                continue
            if pos < len(lines) and lines[pos][0] > indent:
                child_indent = lines[pos][0]
                if lines[pos][1].startswith("-"):
                    result[key] = parse_sequence(child_indent)
                else:
                    result[key] = parse_mapping(child_indent)
            else:
                result[key] = None
        return result

    def parse_sequence(indent: int) -> list:
        nonlocal pos
        result: list = []
        while pos < len(lines):
            current_indent, content = lines[pos]
            if current_indent != indent or not content.startswith("-"):
                break
            body = content[1:].strip()
            pos += 1
            if not body:
                if pos < len(lines) and lines[pos][0] > indent:
                    child_indent = lines[pos][0]
                    if lines[pos][1].startswith("-"):
                        result.append(parse_sequence(child_indent))
                    else:
                        result.append(parse_mapping(child_indent))
                else:
                    result.append(None)
            elif ":" in body and not body.startswith('"'):
                key, _, rest = body.partition(":")
                item = {key.strip(): _yaml_scalar_parse(rest) if rest.strip() else None}
                if pos < len(lines) and lines[pos][0] > indent:
                    item.update(parse_mapping(lines[pos][0]))
                result.append(item)
            else:
                result.append(_yaml_scalar_parse(body))
        return result

    top_indent = lines[0][0]
    if lines[0][1].startswith("-"):
        return {"items": parse_sequence(top_indent)}
    return parse_mapping(top_indent)


def default_export_config() -> dict:
    """A fresh default GUI config, used when only sync chains are exported."""
    default_dl = os.path.join(os.path.expanduser("~"), "Downloads")
    return {
        'format': 'mp3',
        'bitrate': '192',
        'folders': [default_dl],
        'accent': 'System',
        'mode': 'Dark',
        'volume': 100,
        'local_folders': [],
        'local_current_path': '',
        'show_local_metadata': False,
        'minimize_to_tray': False,
        'recent_playlists': [],
        'splitter_sizes': [300, 800, 300],
        'use_custom_args': False,
        'custom_args': '',
        'last_search': '',
        'save_place': False,
        'session_data': {},
        'run_renamer': False,
        'renamer_path': '',
        'run_custom_script': False,
        'custom_script_path': '',
        'normalization_mode': 'ask',
        'auto_rename': False,
        'silence_pad_dur': 2.0,
        'silence_trim': True,
        'use_custom_norm_cmd': False,
        'custom_norm_cmd': '',
        'download_threads': 3,
        'normalization_threads': max(1, os.cpu_count() // 2),
        'local_rescan_interval': 60,
        'disable_update_checks': False,
        'disable_ytdlp_updates': False,
    }


def build_exported_config(current_config: dict, include_config: bool,
                          include_chains: bool, sync_payload: dict) -> dict:
    """Build the gui-config.json copy that goes inside the package.

    Config only   -> the live settings, with every sync chain key removed.
    Chains only   -> a default config with the current sync chains added to it.
    Both          -> the live settings, including the current sync chains.
    """
    base = dict(current_config) if include_config else default_export_config()
    for key in SYNC_ONLY_CONFIG_KEYS:
        base.pop(key, None)
    if include_chains and sync_payload:
        base.update(sync_payload)
    return base


def build_export_manifest_text(include_config: bool, include_chains: bool, include_music: bool,
                              music_entries: List[dict]) -> str:
    """The export.yaml text: what is in the package, and where it lives."""
    manifest = {
        'format_version': EXPORT_FORMAT_VERSION,
        'created': time.strftime("%m-%d-%Y %H:%M:%S"),
        'app_version': APP_VERSION,
        'includes': {
            'config': bool(include_config),
            'sync_chains': bool(include_chains),
            'music': bool(include_music),
        },
        'files': {
            'manifest': EXPORT_MANIFEST_NAME,
            'config': EXPORT_CONFIG_ENTRY,
            'sync_chains': EXPORT_SYNC_ENTRY if include_chains else "",
        },
        'music_folders': list(music_entries or []),
    }
    header = (
        "# yt-msd export package manifest. DO NOT EDIT.\n"
        "# yt-msd reads this file to know what is inside this .zip and how to restore it.\n\n"
    )
    return header + yaml_dump(manifest) + "\n"


def sanitize_archive_name(raw_name: str, fallback: str = "Music") -> str:
    """Make a folder name safe to use as a folder name inside the zip."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(raw_name or "")).strip().strip(".")
    return name or fallback


def unique_music_archive_name(folder: str, used_names: set) -> Tuple[str, str]:
    """Archive path and folder name for a music folder, kept unique inside the zip."""
    name = sanitize_archive_name(os.path.basename(os.path.abspath(folder).rstrip("\\/")))
    candidate = name
    counter = 2
    while candidate.lower() in used_names:
        candidate = f"{name}-{counter}"
        counter += 1
    used_names.add(candidate.lower())
    return f"music/{candidate}", candidate


def iter_folder_files(folder: str, include_subfolders: bool):
    """Yield (absolute path, path relative to the folder) for the files to package."""
    root = os.path.abspath(folder)
    if include_subfolders:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d.lower() not in EXPORT_SKIP_DIRS]
            for filename in filenames:
                full_path = os.path.join(dirpath, filename)
                yield full_path, os.path.relpath(full_path, root)
        return
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                try:
                    if entry.is_file():
                        yield entry.path, entry.name
                except OSError:
                    continue
    except OSError:
        pass


def zip_folder_into(zf, folder: str, archive_root: str, include_subfolders: bool) -> int:
    """Copy one folder into the zip. Returns how many files were written."""
    written = 0
    for full_path, relative_path in iter_folder_files(folder, include_subfolders):
        arcname = f"{archive_root}/{relative_path.replace(os.sep, '/')}"
        try:
            zf.write(full_path, arcname)
            written += 1
        except Exception:
            continue
    return written


def read_import_package(zip_path: str) -> dict:
    """Read export.yaml plus the config / sync payloads out of an export package."""
    with zipfile.ZipFile(zip_path, 'r') as zf:
        names = set(zf.namelist())
        if EXPORT_MANIFEST_NAME not in names:
            raise ValueError("it has no export.yaml manifest, so it is not a yt-msd package")
        manifest = yaml_load(zf.read(EXPORT_MANIFEST_NAME).decode('utf-8', errors='ignore'))
        files = manifest.get('files') if isinstance(manifest.get('files'), dict) else {}
        config_name = str(files.get('config') or EXPORT_CONFIG_ENTRY)
        sync_name = str(files.get('sync_chains') or EXPORT_SYNC_ENTRY)
        config_payload = None
        sync_payload = None
        if config_name in names:
            try:
                config_payload = json.loads(zf.read(config_name).decode('utf-8', errors='ignore'))
            except Exception:
                config_payload = None
        if sync_name in names:
            try:
                sync_payload = json.loads(zf.read(sync_name).decode('utf-8', errors='ignore'))
            except Exception:
                sync_payload = None
        return {'manifest': manifest, 'config': config_payload, 'sync': sync_payload}


def music_import_destination(source_path: str, folder_name: str) -> str:
    """Where a packaged music folder should be restored to.

    The original location is used when its parent folder still exists (same
    machine, or the same share on a new one). Otherwise the folder lands in
    Downloads/yt-msd Import.
    """
    source_path = str(source_path or "").strip()
    if source_path:
        absolute = os.path.abspath(source_path)
        parent = os.path.dirname(absolute)
        if parent and os.path.isdir(parent):
            return absolute
    return os.path.join(os.path.expanduser("~"), "Downloads", "yt-msd Import",
                        sanitize_archive_name(folder_name))


def extract_package_music(zf, manifest: dict,
                         status_cb: Optional[Callable[[str], None]] = None) -> List[dict]:
    """Unpack every music folder the manifest says is in the package."""
    results: List[dict] = []
    names = zf.namelist()
    for entry in manifest.get('music_folders') or []:
        if not isinstance(entry, dict):
            continue
        archive_path = str(entry.get('archive_path') or "").strip().strip("/")
        folder_name = str(entry.get('name') or "") or (archive_path.rsplit("/", 1)[-1] if archive_path else "")
        prefix = ""
        members: List[str] = []
        for candidate in [p for p in (archive_path, f"music/{folder_name}") if p]:
            candidate = candidate.rstrip("/") + "/"
            found = [n for n in names if n.startswith(candidate) and not n.endswith("/")]
            if found:
                prefix, members = candidate, found
                break
        dest_dir = music_import_destination(str(entry.get('source_path') or ""), folder_name)
        dest_root = os.path.normpath(dest_dir)
        written = 0
        error = ""
        for member in members:
            relative = member[len(prefix):].replace("/", os.sep)
            target = os.path.normpath(os.path.join(dest_root, relative))
            if target != dest_root and not target.startswith(dest_root + os.sep):
                continue
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(member) as packed_file:
                    data = packed_file.read()
                with open(target, 'wb') as out_file:
                    out_file.write(data)
                written += 1
            except Exception as exc:
                error = str(exc)
        results.append({'name': folder_name or os.path.basename(dest_root), 'dest': dest_dir,
                        'files': written, 'error': error})
        if status_cb:
            status_cb(f"Restored {written} files to {dest_dir}")
    return results


class ExportDialog(QDialog):
    """Choose what goes into a yt-msd export package (.zip)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Named main_app and not parent, for the reason spelled out in SettingsDialog:
        # self.parent would replace the Qt method of the same name on this dialog.
        self.main_app = parent
        self.setWindowTitle("Export Package")
        self.setMinimumWidth(620)
        self.music_rows: List[dict] = []      # {'path': str, 'check': QCheckBox, 'row': QWidget}
        # How small the window was before the Music section first grew it, so
        # unchecking Music can put the dialog back to that size.
        self._collapsed_size = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title_lbl = QLabel("EXPORT PACKAGE")
        title_lbl.setFont(QFont("Segoe UI Semibold", 11))
        layout.addWidget(title_lbl)
        desc_lbl = QLabel("Everything checked here is packed into one .zip file, described by an export.yaml manifest.\n"
                          "Import that file on another machine to put it all back.")
        desc_lbl.setFont(QFont("Segoe UI", 9))
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        self.config_cb = QCheckBox("Config")
        self.config_cb.setToolTip("Copy your settings (gui-config.json) without any sync chain information.")
        self.config_cb.setChecked(True)
        self.config_cb.toggled.connect(self._update_state)
        layout.addWidget(self.config_cb)

        self.chains_cb = QCheckBox("Sync Chains")
        self.chains_cb.setToolTip("Copy your hosted chains, client chains, and sync settings.")
        self.chains_cb.setChecked(True)
        self.chains_cb.toggled.connect(self._update_state)
        layout.addWidget(self.chains_cb)

        self.music_cb = QCheckBox("Music")
        self.music_cb.setToolTip("Copy the music folders you choose into the package.")
        self.music_cb.toggled.connect(self._toggle_music_section)
        layout.addWidget(self.music_cb)

        # ── MUSIC SECTION (only shown when Music is checked) ──
        self.music_widget = QWidget()
        music_layout = QVBoxLayout(self.music_widget)
        music_layout.setContentsMargins(26, 0, 0, 0)
        music_layout.setSpacing(8)

        folder_row = QHBoxLayout()
        self.add_folder_btn = QPushButton("Add Folder...")
        self.add_folder_btn.setToolTip("Browse for a folder to copy into the package")
        self.add_folder_btn.clicked.connect(self._add_music_folder)
        folder_row.addWidget(self.add_folder_btn)
        folder_row.addStretch()
        music_layout.addLayout(folder_row)

        self.music_rows_widget = QWidget()
        self.music_rows_layout = QVBoxLayout(self.music_rows_widget)
        self.music_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.music_rows_layout.setSpacing(4)
        self.music_rows_layout.addStretch()
        music_layout.addWidget(self._make_row_scroll(self.music_rows_widget, 140))

        layout.addWidget(self.music_widget)
        self.music_widget.setVisible(False)

        # ── FOOTER ──
        footer = QHBoxLayout()
        self.summary_lbl = QLabel("Nothing selected to export.")
        self.summary_lbl.setFont(QFont("Segoe UI", 9))
        footer.addWidget(self.summary_lbl)
        footer.addStretch()
        self.export_btn = QPushButton("Export Package...")
        self.export_btn.setToolTip("Choose where to save the .zip package")
        self.export_btn.clicked.connect(self._choose_export_file)
        footer.addWidget(self.export_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)
        layout.addLayout(footer)

        self._update_state()


    def _make_row_scroll(self, inner_widget: QWidget, max_height: int) -> QScrollArea:
        """A bounded, frameless scroll area for the folder rows."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner_widget)
        scroll.setMaximumHeight(max_height)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        return scroll

    def _toggle_music_section(self, state: bool):
        state = bool(state)
        if state and self._collapsed_size is None:
            # The checkbox changes before the section is shown, so this is still
            # the size the window had without the Music rows.
            self._collapsed_size = self.size()
        self.music_widget.setVisible(state)
        if not state and self._collapsed_size is not None:
            # Hiding a section never shrinks a Qt window by itself, and the layout
            # keeps reporting the expanded minimum size until it is recomputed, so
            # recompute it first and then go back to the size Music was added at.
            dialog_layout = self.layout()
            if dialog_layout is not None:
                dialog_layout.invalidate()
                dialog_layout.activate()
            if self.size() != self._collapsed_size:
                self.resize(self._collapsed_size)
            if self.size() != self._collapsed_size:
                # A layout pass that was already queued can push the window back
                # open, so try once more after the event loop has settled.
                QTimer.singleShot(0, lambda: self.resize(self._collapsed_size))
        self._update_state()

    def _add_music_folder(self):
        start = ""
        if self.music_rows:
            last = self.music_rows[-1]['path']
            start = os.path.dirname(last) or last
        folder = QFileDialog.getExistingDirectory(self, "Choose a Music Folder", start)
        if not folder:
            return
        self._add_music_row(os.path.abspath(folder))
        self._update_state()

    def _add_music_row(self, folder_path: str):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        path_lbl = QLabel(folder_path)
        path_lbl.setFont(QFont("Segoe UI", 9))
        path_lbl.setToolTip(folder_path)
        row_layout.addWidget(path_lbl, 1)

        sub_cb = QCheckBox("subfolders")
        sub_cb.setToolTip("Include everything inside this folder's subfolders")
        sub_cb.setChecked(True)
        sub_cb.toggled.connect(self._update_state)
        row_layout.addWidget(sub_cb)

        remove_btn = QPushButton("Remove")
        remove_btn.setToolTip("Do not include this folder")
        remove_btn.clicked.connect(lambda checked=False, path=folder_path: self._remove_row(self.music_rows, path, 'path'))
        row_layout.addWidget(remove_btn)

        # Keep the trailing stretch last so rows stay top-aligned.
        self.music_rows_layout.insertWidget(self.music_rows_layout.count() - 1, row_widget)
        self.music_rows.append({'path': folder_path, 'check': sub_cb, 'row': row_widget})

    def _remove_row(self, rows: List[dict], key_value: str, key_name: str):
        for entry in list(rows):
            if entry.get(key_name) == key_value:
                rows.remove(entry)
                self.music_rows_layout.removeWidget(entry['row'])
                entry['row'].deleteLater()
                break
        self._update_state()


    def build_options(self, require_selection: bool = False):
        """What the user picked, in the shape MainApp.start_export expects."""
        include_config = self.config_cb.isChecked()
        include_chains = self.chains_cb.isChecked()
        want_music = self.music_cb.isChecked()
        folders: List[dict] = []
        if want_music:
            folders = [{'path': entry['path'], 'subfolders': bool(entry['check'].isChecked())}
                       for entry in self.music_rows]
        include_music = bool(folders)
        if require_selection and not (include_config or include_chains or include_music):
            return None
        return {
            'include_config': include_config,
            'include_chains': include_chains,
            'include_music': include_music,
            'music_folders': folders,
        }

    def _update_state(self):
        options = self.build_options(require_selection=True)
        parts: List[str] = []
        if options:
            if options['include_config']:
                parts.append("config")
            if options['include_chains']:
                parts.append("sync chains")
            if options['include_music']:
                parts.append(f"{len(options['music_folders'])} music folder(s)")
        if parts:
            self.summary_lbl.setText("Will export: " + ", ".join(parts))
            self.export_btn.setEnabled(True)
        else:
            self.summary_lbl.setText("Nothing selected to export.")
            self.export_btn.setEnabled(False)

    def _choose_export_file(self):
        options = self.build_options(require_selection=True)
        if options is None:
            return
        default_name = f"yt-msd-export-{time.strftime('%Y-%m-%d')}.zip"
        start_dir = getattr(self.main_app, 'download_path', '') or os.path.expanduser("~")
        target, _ = QFileDialog.getSaveFileName(self, "Save Export Package",
                                               os.path.join(start_dir, default_name),
                                               "yt-msd Package (*.zip)")
        if not target:
            return
        if not target.lower().endswith(".zip"):
            target += ".zip"
        options['zip_path'] = target
        self.main_app.start_export(options)
        self.accept()


class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        # The window that opened this dialog, held under a name that is not 'parent'.
        # It used to be self.parent, and that meant the name of a Qt method this dialog
        # inherits: QDialog.parent() is how Qt hands back the widget a dialog sits inside,
        # and an instance attribute of the same name replaces it for Python callers.
        # MainApp installs itself as an application-wide event filter, and every key press
        # makes it walk up from the focused control asking each widget for its parent -
        # so while this dialog was open, a key typed into any box of it reached the
        # MainApp window through self.parent and asked the window to be called as a
        # method. That is the "TypeError: 'MainApp' object is not callable" the installed
        # exe logged on every keystroke in Settings, and why only typing was affected and
        # not the spin-box arrows, which are clicks and not key presses.
        self.main_app = parent
        self.setWindowTitle("Settings")
        self.setMinimumWidth(820)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # 2-Column Horizontal Container
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(20)
        
        # ── LEFT COLUMN ──
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        
        # APPEARANCE MODE
        left_layout.addWidget(QLabel("APPEARANCE MODE", font=QFont("Segoe UI Semibold", 10)))
        mode_layout = QHBoxLayout()
        self.mode_btns = {}
        for mode in ["System", "Light", "Dark"]:
            btn = QPushButton(mode)
            btn.setToolTip(f"Switch to {mode.lower()} appearance")
            btn.setCheckable(True)
            if parent.appearance_mode == mode: btn.setChecked(True)
            btn.clicked.connect(lambda checked=False, m=mode: self._change_mode(m))
            mode_layout.addWidget(btn)
            self.mode_btns[mode] = btn
        left_layout.addLayout(mode_layout)
        
        # ACCENT COLOR
        left_layout.addWidget(QLabel("ACCENT COLOR", font=QFont("Segoe UI Semibold", 10)))
        grid = QGridLayout()
        grid.setSpacing(6)
        colors = ["System"] + list(THEME_COLORS.keys())
        self.accent_btns = {}
        for i, color in enumerate(colors):
            r, c = i // 5, i % 5
            btn = QPushButton()
            btn.setFixedSize(32, 32)
            c_val = get_system_accent_color() if color == "System" else THEME_COLORS[color][0]
            btn.setStyleSheet(f"background-color: {c_val}; border-radius: 6px; border: {'2px solid white' if parent.accent_color_name == color else 'none'};")
            # The System chip is a plain swatch of the live Windows accent colour, exactly like the
            # THEME_COLORS chips. It used to paint a glyph (U+E771) in Segoe MDL2 Assets on top of the
            # swatch, but that codepoint has no glyph in the font here, so the chip showed a tofu box.
            # The background colour alone already says "system", so the chip carries no text at all.
            btn.clicked.connect(lambda checked=False, clr=color: self._change_accent(clr))
            grid.addWidget(btn, r, c)
            self.accent_btns[color] = btn
        left_layout.addLayout(grid)
        
        # ADVANCED YT-DLP
        left_layout.addWidget(QLabel("CUSTOM YT-DLP ARGUMENTS (ADVANCED)", font=QFont("Segoe UI Semibold", 10)))
        arg_h = QHBoxLayout()
        self.args_cb = QCheckBox()
        self.args_cb.setChecked(parent.use_custom_args)
        self.args_cb.toggled.connect(self._toggle_args)
        arg_h.addWidget(self.args_cb)
        _fmt = parent.format_combo.currentText() if hasattr(parent, 'format_combo') else getattr(parent, 'audio_format', 'mp3')
        _brate = parent.bitrate_combo.currentText() if hasattr(parent, 'bitrate_combo') else getattr(parent, 'bitrate', '320')
        _default_args = f"--format bestaudio/best --audio-format {_fmt} --audio-quality {_brate} --retries 15 --fragment-retries 15"
        _initial_args = parent.custom_args if parent.custom_args else _default_args
        self.args_edit = QLineEdit(_initial_args)
        self.args_edit.setPlaceholderText("e.g. --format bestaudio/best --audio-format mp3 --audio-quality 320")
        self.args_edit.setEnabled(parent.use_custom_args)
        self.args_edit.textChanged.connect(self._update_args)
        arg_h.addWidget(self.args_edit, 1)
        left_layout.addLayout(arg_h)
        left_layout.addWidget(QLabel("Manual override ignores GUI bitrate/format settings.", font=QFont("Segoe UI", 8)))
        
        # OPTIONS
        self.startup_cb = QCheckBox("Run yt-msd on Windows Startup")
        self.startup_cb.setChecked(is_run_on_startup_enabled())
        self.startup_cb.toggled.connect(self._toggle_startup)
        left_layout.addWidget(self.startup_cb)

        self.tray_cb = QCheckBox("Minimize to System Tray")
        self.tray_cb.setChecked(parent.minimize_to_tray)
        self.tray_cb.toggled.connect(self._toggle_tray)
        left_layout.addWidget(self.tray_cb)
        
        self.session_cb = QCheckBox("Restore Last Session on Startup")
        self.session_cb.setChecked(getattr(parent, 'save_place', False))
        self.session_cb.toggled.connect(self._toggle_session)
        left_layout.addWidget(self.session_cb)
        
        # Parallel downloads option
        dl_threads_h = QHBoxLayout()
        dl_threads_h.addWidget(QLabel("Parallel download threads:"))
        self.dl_threads_edit = QLineEdit(str(parent.download_threads))
        self.dl_threads_edit.setFixedWidth(50)
        self.dl_threads_edit.setPlaceholderText("e.g. 3")
        self.dl_threads_edit.textChanged.connect(self._update_dl_threads)
        dl_threads_h.addWidget(self.dl_threads_edit)
        dl_threads_h.addStretch()
        left_layout.addLayout(dl_threads_h)
        left_layout.addWidget(QLabel("Disclaimer: Too many parallel downloads may cause your internet\n"
                                     "to throttle or YouTube to rate-limit requests.", font=QFont("Segoe UI", 8)))
        
        # Local folder auto-rescan interval
        rescan_h = QHBoxLayout()
        rescan_h.addWidget(QLabel("Local folder auto-rescan:"))
        self.rescan_combo = QComboBox()
        self.rescan_options = [
            ("Disabled", 0),
            ("15 minutes", 15),
            ("30 minutes", 30),
            ("1 hour (Default)", 60),
            ("2 hours", 120),
            ("4 hours", 240),
            ("12 hours", 720),
            ("24 hours", 1440)
        ]
        for label, mins in self.rescan_options:
            self.rescan_combo.addItem(label, mins)

        current_mins = getattr(parent, 'local_rescan_interval', 60)
        idx = self.rescan_combo.findData(current_mins)
        if idx >= 0:
            self.rescan_combo.setCurrentIndex(idx)
        else:
            self.rescan_combo.setCurrentIndex(3)  # 1 hour default

        self.rescan_combo.currentIndexChanged.connect(self._update_rescan_interval)
        rescan_h.addWidget(self.rescan_combo)
        rescan_h.addStretch()
        left_layout.addLayout(rescan_h)
        left_layout.addStretch()
        
        # Vertical Divider Frame
        divider = QFrame()
        divider.setFrameShape(QFrame.VLine)
        divider.setFrameShadow(QFrame.Sunken)
        
        # ── RIGHT COLUMN ──
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)
        
        # MP3 RENAMER
        right_layout.addWidget(QLabel("MP3 RENAMER & NORMALIZER", font=QFont("Segoe UI Semibold", 10)))

        # Normalization mode
        norm_h = QHBoxLayout()
        norm_h.addWidget(QLabel("Normalization after download:"))
        self.norm_btns = {}
        for mode, label in [("on", "ON"), ("off", "OFF"), ("ask", "ASK")]:
            btn = QPushButton(label)
            btn.setToolTip({"on": "Always normalize after download", "off": "Never normalize after download", "ask": "Ask before normalizing each download"}[mode])
            btn.setCheckable(True)
            btn.setChecked(parent.normalization_mode == mode)
            btn.clicked.connect(lambda checked=False, m=mode: self._set_norm_mode(m))
            norm_h.addWidget(btn)
            self.norm_btns[mode] = btn
        norm_h.addStretch()
        right_layout.addLayout(norm_h)
        right_layout.addWidget(QLabel("ON = always normalize  |  OFF = always skip  |  ASK = prompt each time",
                                      font=QFont("Segoe UI", 8)))

        # Auto-rename
        self.auto_rename_cb = QCheckBox("Auto-rename without prompts (auto-accept predictions)")
        self.auto_rename_cb.setChecked(parent.auto_rename)
        self.auto_rename_cb.toggled.connect(self._toggle_auto_rename)
        right_layout.addWidget(self.auto_rename_cb)

        # Silence pad duration
        pad_h = QHBoxLayout()
        pad_h.addWidget(QLabel("Silence padded at end of file (seconds):"))
        self.silence_pad_edit = QLineEdit(str(parent.silence_pad_dur))
        self.silence_pad_edit.setFixedWidth(70)
        self.silence_pad_edit.setPlaceholderText("e.g. 2.0")
        self.silence_pad_edit.textChanged.connect(self._update_silence_pad)
        pad_h.addWidget(self.silence_pad_edit)
        pad_h.addStretch()
        right_layout.addLayout(pad_h)
        
        # Normalization threads
        from PySide6.QtWidgets import QSpinBox
        norm_threads_h = QHBoxLayout()
        norm_threads_h.addWidget(QLabel("Normalization threads:"))
        self.norm_threads_spin = QSpinBox()
        self.norm_threads_spin.setRange(1, max(1, os.cpu_count() - 1))
        self.norm_threads_spin.setValue(parent.normalization_threads)
        self.norm_threads_spin.valueChanged.connect(self._update_norm_threads)
        norm_threads_h.addWidget(self.norm_threads_spin)
        norm_threads_h.addStretch()
        right_layout.addLayout(norm_threads_h)

        # Silence trimming on/off. This is its own part of the filter chain and is
        # completely independent of the loudnorm/EQ override below.
        self.silence_trim_cb = QCheckBox("Trim silence from the start and end of the file")
        self.silence_trim_cb.setToolTip(
            f"Removes leading and trailing silence during normalization.\n"
            f"Built-in filter (unchanged): silenceremove=start_periods=1:\n"
            f"start_duration={SILENCE_DURATION}:start_threshold={SILENCE_THRESHOLD}:\n"
            f"start_silence={SILENCE_KEEP}:stop_silence={SILENCE_KEEP}, applied forwards and reversed.\n"
            f"Turning this off does NOT change the loudnorm/EQ override,\n"
            f"and using a loudnorm/EQ override does NOT change this filter.")
        self.silence_trim_cb.setChecked(parent.silence_trim)
        self.silence_trim_cb.toggled.connect(self._toggle_silence_trim)
        right_layout.addWidget(self.silence_trim_cb)

        # Custom loudnorm/EQ override (replaces only the loudnorm filter, never the silence trim)
        right_layout.addWidget(QLabel("LOUDNORM/EQ OVERRIDE (ADVANCED)", font=QFont("Segoe UI Semibold", 10)))
        norm_cmd_h = QHBoxLayout()
        self.norm_cmd_cb = QCheckBox()
        self.norm_cmd_cb.setToolTip("Replace the built-in whole-track gain with your own loudnorm/EQ filter")
        self.norm_cmd_cb.setChecked(parent.use_custom_norm_cmd)
        self.norm_cmd_cb.toggled.connect(self._toggle_norm_cmd)
        norm_cmd_h.addWidget(self.norm_cmd_cb)
        _default_loudnorm = f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA={LOUDNESS_RANGE}"
        initial_norm = parent.custom_norm_cmd if parent.custom_norm_cmd else _default_loudnorm
        self.norm_cmd_edit = QLineEdit(initial_norm)
        self.norm_cmd_edit.setPlaceholderText(_default_loudnorm)
        self.norm_cmd_edit.setEnabled(parent.use_custom_norm_cmd)
        self.norm_cmd_edit.textChanged.connect(self._update_norm_cmd)
        norm_cmd_h.addWidget(self.norm_cmd_edit, 1)
        norm_cmd_h.addWidget(self._make_info_btn(
            f"Replaces ONLY the loudnorm part of the ffmpeg filter chain.\n"
            f"The silence trim and the end-of-file pad are still applied around it.\n"
            f"Exact loudnorm values used by default: I={TARGET_LUFS} LUFS | TP={TRUE_PEAK} dB | LRA={LOUDNESS_RANGE}.\n"
            f"Want EQ too? Append it after the loudnorm part in this same box, e.g.\n"
            f"{_default_loudnorm},equalizer=f=100:width_type=o:width=2:g=-3"))
        right_layout.addLayout(norm_cmd_h)

        # Run a custom file after a download batch finishes
        right_layout.addWidget(QLabel("CUSTOM SCRIPT ON DOWNLOAD FINISH", font=QFont("Segoe UI Semibold", 10)))
        cs_h = QHBoxLayout()
        self.custom_script_cb = QCheckBox()
        self.custom_script_cb.setToolTip("Run a chosen script or executable after each download batch finishes")
        self.custom_script_cb.setChecked(parent.run_custom_script)
        self.custom_script_cb.toggled.connect(self._toggle_custom_script)
        cs_h.addWidget(self.custom_script_cb)
        self.custom_script_edit = QLineEdit(parent.custom_script_path)
        self.custom_script_edit.setPlaceholderText("Path to a script or executable to run after downloads")
        self.custom_script_edit.textChanged.connect(self._update_custom_script)
        cs_h.addWidget(self.custom_script_edit, 1)
        self.custom_script_browse_btn = QPushButton("\uE8B7")
        self.custom_script_browse_btn.setObjectName("topIconBtn")
        self.custom_script_browse_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px; padding: 0px;")
        self.custom_script_browse_btn.setFixedSize(36, 30)
        self.custom_script_browse_btn.setToolTip("Browse for the file to run")
        self.custom_script_browse_btn.clicked.connect(self._browse_custom_script)
        cs_h.addWidget(self.custom_script_browse_btn)
        cs_h.addWidget(self._make_info_btn(
            "Runs one file after a download batch finishes.\n"
            "Supports .py, .exe, .bat/.cmd, .ps1, and any file type Windows can open.\n"
            "It receives the download folder as its first argument,\n"
            "then the path of each downloaded file."))
        right_layout.addLayout(cs_h)

        # SYSTEM YT-DLP
        right_layout.addWidget(QLabel("YT-DLP (ON THIS SYSTEM)", font=QFont("Segoe UI Semibold", 10)))
        ytdlp_h = QHBoxLayout()
        known_version = getattr(parent, 'ytdlp_version', '')
        self.ytdlp_version_lbl = QLabel(f"Version: {known_version}" if known_version else "Version: checking...")
        self.ytdlp_version_lbl.setFont(QFont("Segoe UI", 9))
        ytdlp_h.addWidget(self.ytdlp_version_lbl)
        ytdlp_h.addStretch()
        self.ytdlp_update_btn = QPushButton("Update with winget")
        self.ytdlp_update_btn.setObjectName("topIconBtn")
        self.ytdlp_update_btn.setToolTip("Run: winget upgrade --id yt-dlp.yt-dlp")
        self.ytdlp_update_btn.clicked.connect(self._update_yt_dlp)
        ytdlp_h.addWidget(self.ytdlp_update_btn)
        ytdlp_h.addWidget(self._make_info_btn(
            "yt-msd searches and downloads with the yt-dlp installed on this system,\n"
            "not a copy bundled inside yt-msd, so yt-dlp can be kept current without\n"
            "a new yt-msd build. This button runs winget, which ships with Windows 10\n"
            "and 11. yt-msd also asks GitHub once a week whether a newer yt-dlp exists."))
        right_layout.addLayout(ytdlp_h)

        self.ytdlp_never_cb = QCheckBox("Never notify me about yt-dlp updates")
        self.ytdlp_never_cb.setToolTip("Stop the weekly yt-dlp version check (yt-msd updates are not affected)")
        self.ytdlp_never_cb.setChecked(getattr(parent, 'disable_ytdlp_updates', False))
        self.ytdlp_never_cb.toggled.connect(self._toggle_ytdlp_updates)
        right_layout.addWidget(self.ytdlp_never_cb)

        if not known_version:
            # The startup lookup may still be running; ask for the version again so
            # this row is never left showing "checking...".
            parent.refresh_yt_dlp_version()

        right_layout.addSpacing(10)
        version_lbl = QLabel(APP_VERSION)
        version_lbl.setFont(QFont("Segoe UI", 8))
        version_lbl.setAlignment(Qt.AlignRight)
        version_lbl.setStyleSheet("background: transparent; border: none;")
        right_layout.addWidget(version_lbl)
        right_layout.addStretch()
        
        columns_layout.addWidget(left_widget, 1)
        columns_layout.addWidget(divider)
        columns_layout.addWidget(right_widget, 1)
        
        main_layout.addLayout(columns_layout)
        
        # FOOTER / RESET & SYNC
        footer = QHBoxLayout()
        self.reset_btn = QPushButton("Reset to Default Config")
        self.reset_btn.setObjectName("topIconBtn")
        self.reset_btn.setToolTip("Reset all settings to their defaults")
        self.reset_btn.clicked.connect(self._reset_defaults)
        footer.addWidget(self.reset_btn)

        self.sync_btn = QPushButton("Sync Chains Manager")
        self.sync_btn.setToolTip("Open the Sync Chains Manager")
        self.sync_btn.clicked.connect(self._open_sync_manager)
        footer.addWidget(self.sync_btn)

        self.export_btn = QPushButton("Export...")
        self.export_btn.setToolTip("Pack your config, sync chains, and music into a single .zip file")
        self.export_btn.clicked.connect(self._open_export_dialog)
        footer.addWidget(self.export_btn)

        self.import_btn = QPushButton("Import...")
        self.import_btn.setToolTip("Restore a yt-msd export package from a .zip file")
        self.import_btn.clicked.connect(self._open_import_package)
        footer.addWidget(self.import_btn)

        footer.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setFixedWidth(100)
        ok_btn.setToolTip("Close settings")
        ok_btn.clicked.connect(self.accept)
        footer.addWidget(ok_btn)
        
        main_layout.addLayout(footer)
        self.update_styles()

    def update_styles(self):
        accent = get_accent_color(self.main_app.accent_color_name)
        mode = self.main_app.appearance_mode
        if mode == "System": mode = get_system_appearance_mode()
        is_light = mode == "Light"
        
        r = int(accent[1:3], 16)
        g = int(accent[3:5], 16)
        b = int(accent[5:7], 16)
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        accent_fg = "black" if brightness > 150 else "white"
        
        for m, b in self.mode_btns.items():
            if m == self.main_app.appearance_mode:
                b.setStyleSheet(f"background-color: {accent}; color: {accent_fg}; border-radius: 4px;")
            else:
                b.setStyleSheet(f"background-color: {'#ddd' if is_light else '#444'}; color: {'black' if is_light else 'white'}; border-radius: 4px;")
        
        for color, btn in self.accent_btns.items():
            c_val = get_system_accent_color() if color == "System" else THEME_COLORS[color][0]
            border = f"2px solid {'black' if is_light else 'white'}" if self.main_app.accent_color_name == color else "none"
            btn.setStyleSheet(f"background-color: {c_val}; border-radius: 6px; border: {border};")

        for m, btn in self.norm_btns.items():
            if m == self.main_app.normalization_mode:
                btn.setStyleSheet(f"background-color: {accent}; color: {accent_fg}; border-radius: 4px;")
            else:
                btn.setStyleSheet(f"background-color: {'#ddd' if is_light else '#444'}; color: {'black' if is_light else 'white'}; border-radius: 4px;")

    def _change_mode(self, mode):
        self.main_app.appearance_mode = mode
        self.main_app.apply_theme()
        self.update_styles()
        self.main_app.save_config()

    def _change_accent(self, color):
        self.main_app.accent_color_name = color
        self.main_app.apply_theme()
        self.update_styles()
        self.main_app.save_config()
        
    def _toggle_args(self, state):
        self.main_app.use_custom_args = state
        self.args_edit.setEnabled(state)
        self.main_app.save_config()
        
    def _update_args(self, text):
        self.main_app.custom_args = text
        self.main_app.save_config()
        
    def set_ytdlp_version(self, version):
        """Show the yt-dlp version found by a background thread in the main window."""
        if version and hasattr(self, 'ytdlp_version_lbl'):
            self.ytdlp_version_lbl.setText(f"Version: {version}")

    def _update_yt_dlp(self):
        """Ask the main window to run the winget upgrade for yt-dlp."""
        self.main_app.update_yt_dlp_now()

    def _toggle_ytdlp_updates(self, state):
        self.main_app.disable_ytdlp_updates = state
        self.main_app.save_config()
        
    def _toggle_startup(self, state):
        set_run_on_startup(bool(state))

    def _toggle_tray(self, state):
        self.main_app.minimize_to_tray = state
        self.main_app.save_config()
        
    def _toggle_session(self, state):
        self.main_app.save_place = state
        self.main_app.save_config()

    # --- MP3 Renamer settings ---
    def _set_norm_mode(self, mode):
        self.main_app.normalization_mode = mode
        for m, btn in self.norm_btns.items():
            btn.setChecked(m == mode)
        self.main_app.save_config()
        self.update_styles()

    def _toggle_auto_rename(self, state):
        self.main_app.auto_rename = state
        self.main_app.save_config()

    def _update_silence_pad(self, text):
        try:
            val = float(text)
            if val >= 0:
                self.main_app.silence_pad_dur = val
                global SILENCE_PAD_DUR
                SILENCE_PAD_DUR = val
                self.main_app.save_config()
        except ValueError:
            pass

    def _update_dl_threads(self, text):
        try:
            val = int(text)
            if val > 0:
                self.main_app.download_threads = val
                self.main_app.save_config()
        except ValueError:
            pass

    def _update_rescan_interval(self, index):
        mins = self.rescan_combo.itemData(index)
        if mins is not None:
            self.main_app.local_rescan_interval = mins
            self.main_app._update_local_rescan_timer()
            self.main_app.save_config()

    def _update_norm_threads(self, val):
        self.main_app.normalization_threads = val
        self.main_app.save_config()

    def _toggle_silence_trim(self, state):
        self.main_app.silence_trim = state
        global SILENCE_TRIM
        SILENCE_TRIM = state
        self.main_app.save_config()

    def _toggle_norm_cmd(self, state):
        self.main_app.use_custom_norm_cmd = state
        self.norm_cmd_edit.setEnabled(state)
        if state and not self.norm_cmd_edit.text().strip():
            self.norm_cmd_edit.setText(f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA={LOUDNESS_RANGE}")
        global CUSTOM_NORM_CMD
        CUSTOM_NORM_CMD = self.main_app.custom_norm_cmd if state else ""
        self.main_app.save_config()

    def _update_norm_cmd(self, text):
        self.main_app.custom_norm_cmd = text
        global CUSTOM_NORM_CMD
        if self.main_app.use_custom_norm_cmd:
            CUSTOM_NORM_CMD = text
        self.main_app.save_config()

    def _toggle_custom_script(self, state):
        # The checkbox only gates whether the script runs after a download; the
        # path field and browse button stay usable so a path can always be set.
        self.main_app.run_custom_script = state
        self.main_app.save_config()

    def _update_custom_script(self, text):
        self.main_app.custom_script_path = text.strip()
        self.main_app.save_config()

    def _browse_custom_script(self):
        start = self.custom_script_edit.text().strip() or ""
        f, _ = QFileDialog.getOpenFileName(
            self, "Select File To Run After Download", start,
            "All files (*);;Python (*.py);;Executable (*.exe);;Batch (*.bat *.cmd);;PowerShell (*.ps1)"
        )
        if f:
            self.custom_script_edit.setText(f)
            self.main_app.custom_script_path = f
            self.main_app.save_config()

    def _make_info_btn(self, text):
        """Small 'i' info button; the description is shown as a hover tooltip."""
        mode = self.main_app.appearance_mode
        if mode == "System":
            mode = get_system_appearance_mode()
        is_light = (mode == "Light")
        fg = "#1a1a1a" if is_light else "#ffffff"
        border = "#ccc" if is_light else "#555"
        accent = get_accent_color(self.main_app.accent_color_name)
        btn = QPushButton("i")
        btn.setObjectName("infoBtn")
        btn.setFixedSize(24, 24)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(text)
        btn.setStyleSheet(
            f"QPushButton#infoBtn {{ background: transparent; color: {fg}; "
            f"border: 1px solid {border}; border-radius: 12px; "
            f"font-family: 'Segoe UI'; font-weight: bold; font-size: 13px; padding: 0px; }}"
            f"QPushButton#infoBtn:hover {{ border-color: {accent}; color: {accent}; }}"
            "QToolTip { font-size: 11px; }"
        )
        return btn

    def _open_export_dialog(self):
        """Pack the selected pieces into a .zip export package."""
        dialog = ExportDialog(self.main_app)
        dialog.exec()

    def _open_import_package(self):
        """Pick a .zip export package and restore it."""
        self.main_app.open_import_dialog()

    def _open_sync_manager(self):
        # Leave the settings dialog open in the background, open sync manager in foreground
        self.main_app.open_sync_manager(parent_dialog=self)

    def _reset_defaults(self):
        # Wording that matches what reset_to_defaults() actually clears: every stored setting and
        # history entry, plus the hosted and client chains. A drive that has been initialised keeps
        # its own TAG.yaml marker on the device, so its card reappears while it is plugged in - but
        # with the hosted/client chains gone there is nothing left for it to sync against. Music
        # files themselves are never touched, on this machine or on a drive.
        warning = ("This wipes everything yt-msd remembers: every setting, your download and local "
                   "folder history, your playlist history, and every hosted and client sync chain. "
                   "An initialised drive keeps its marker on the device, so its card comes back "
                   "while it is plugged in. Your music files are not touched. Continue?")
        if QMessageBox.question(self, "Confirm Reset", warning) == QMessageBox.Yes:
            self.main_app.reset_to_defaults()
            self.accept()

class PlaylistDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Open Playlist")
        self.setFixedSize(420, 200)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)
        l = QVBoxLayout(self)
        l.setContentsMargins(20, 20, 20, 20)
        l.addWidget(QLabel("Enter URL or select from history:"))
        self.url_cb = QComboBox()
        self.url_cb.setEditable(True)
        self.url_cb.setMinimumHeight(32)
        if parent and hasattr(parent, 'recent_playlists'):
            display_values = []
            for p in parent.recent_playlists:
                if isinstance(p, dict): display_values.append(p.get("name", "Unknown Playlist"))
                else: display_values.append(str(p))
            self.url_cb.addItems(display_values)
        l.addWidget(self.url_cb)
        l.addStretch()
        h = QHBoxLayout()
        h.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip("Cancel")
        cancel_btn.clicked.connect(self.reject)
        open_btn = QPushButton("Open Playlist")
        open_btn.setToolTip("Open the selected playlist")
        open_btn.clicked.connect(self.accept)
        # Assuming app aesthetic injection
        accent = get_accent_color(parent.accent_color_name if parent else "Blue")
        r = int(accent[1:3], 16); g = int(accent[3:5], 16); b = int(accent[5:7], 16)
        accent_fg = "black" if (r * 299 + g * 587 + b * 114) / 1000 > 150 else "white"
        open_btn.setStyleSheet(f"background-color: {accent}; color: {accent_fg}; border-radius: 4px; padding: 6px 12px; font-weight: bold;")
        cancel_btn.setStyleSheet("background-color: #555555; color: white; border-radius: 4px; padding: 6px 12px; font-weight: bold;")
        h.addWidget(cancel_btn)
        h.addWidget(open_btn)
        l.addLayout(h)

class TrayProgressPopup(QWidget):
    """Custom frameless floating popup near system tray displaying current track and playback progress."""
    def __init__(self, parent=None):
        super().__init__(parent, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SubWindow)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.frame = QFrame()
        self.frame.setObjectName("trayPopupFrame")
        self.frame.setStyleSheet("""
            QFrame#trayPopupFrame {
                background-color: #1e1e1e;
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 8px;
            }
        """)
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(14, 12, 14, 12)
        frame_layout.setSpacing(6)

        # Header row
        header_h = QHBoxLayout()
        header_h.setContentsMargins(0, 0, 0, 0)
        header_lbl = QLabel("NOW PLAYING")
        header_lbl.setStyleSheet("color: #3B8ED0; font-weight: bold; font-size: 11px; letter-spacing: 0.5px;")
        header_h.addWidget(header_lbl)
        header_h.addStretch()
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(18, 18)
        close_btn.setToolTip("Close")
        close_btn.setStyleSheet("background: transparent; color: #888; font-size: 11px; border: none; font-weight: bold;")
        close_btn.clicked.connect(self.hide)
        header_h.addWidget(close_btn)
        frame_layout.addLayout(header_h)

        # Song Title
        self.title_lbl = QLabel("No track currently playing")
        self.title_lbl.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: bold;")
        self.title_lbl.setWordWrap(True)
        frame_layout.addWidget(self.title_lbl)

        # Progress info
        self.progress_lbl = QLabel("")
        self.progress_lbl.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        frame_layout.addWidget(self.progress_lbl)

        main_layout.addWidget(self.frame)
        self.setFixedWidth(320)

    def mousePressEvent(self, event):
        self.hide()

    def show_track_info(self, title: str, progress_txt: str):
        if not title:
            self.title_lbl.setText("No track currently playing")
            self.progress_lbl.setText("")
        else:
            self.title_lbl.setText(title)
            if progress_txt and progress_txt != "0:00 / 0:00":
                self.progress_lbl.setText(progress_txt)
            else:
                self.progress_lbl.setText("Playing")

        self.adjustSize()
        
        # Position in bottom right above taskbar
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.right() - self.width() - 16
        y = screen.bottom() - self.height() - 16
        self.move(x, y)
        self.show()
        self.raise_()
        self.hide_timer.start(3500)


class UpdateAvailableDialog(QDialog):
    """Notifies the user that a newer yt-msd release is available and offers to download it."""
    def __init__(self, parent_window, latest_tag, release_name, current_version, asset_name=""):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.never_notify = False
        # Whether this copy is the installed program or a copy started from the
        # source decides which file of the release is offered, and what downloading
        # it does to this folder.
        self.packaged = is_packaged_build()
        self.wanted_asset = INSTALLER_ASSET if self.packaged else SOURCE_ASSET
        self.asset_name = (asset_name or "").strip()
        self.setWindowTitle("Update Available - yt-msd")
        self.setFixedWidth(470)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title_lbl = QLabel("A NEW UPDATE IS AVAILABLE")
        title_lbl.setFont(QFont("Segoe UI Semibold", 11))
        layout.addWidget(title_lbl)

        desc = QLabel(
            f"A newer version of yt-msd ({latest_tag}) is available.\n"
            f"You are currently running {current_version}."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(desc)

        if release_name and release_name != latest_tag:
            name_lbl = QLabel(f"Release: {release_name}")
            name_lbl.setWordWrap(True)
            name_lbl.setStyleSheet("color: #888; font-size: 11px;")
            layout.addWidget(name_lbl)

        self.never_cb = QCheckBox("Never notify me again about updates")
        self.never_cb.setToolTip("Stop checking for updates entirely")
        layout.addWidget(self.never_cb)

        if self.asset_name:
            what_lbl = QLabel(
                f"Download: {self.asset_name}\n"
                + ("This copy of yt-msd is the installed program, so the setup program is downloaded "
                   "and the whole yt-msd folder is replaced once it has run."
                   if self.packaged else
                   "This copy of yt-msd is running from its source file, so the new source file is "
                   "downloaded over the file you are running.")
            )
        elif self.packaged:
            what_lbl = QLabel(f"This release has no {INSTALLER_ASSET} setup program to download.")
        else:
            what_lbl = QLabel(f"This release has no {SOURCE_ASSET} source file to download.")
        what_lbl.setWordWrap(True)
        what_lbl.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(what_lbl)

        layout.addStretch()

        btn_h = QHBoxLayout()
        btn_h.addStretch()

        ignore_btn = QPushButton("Ignore")
        ignore_btn.setToolTip("Skip this update until the next check")
        ignore_btn.clicked.connect(self._on_ignore)
        btn_h.addWidget(ignore_btn)

        dl_btn = QPushButton("Download update")
        if self.packaged:
            dl_btn.setToolTip("Download the setup program into the folder yt-msd is running from")
        else:
            dl_btn.setToolTip(f"Download the new {SOURCE_ASSET} over the file yt-msd is running from")
        dl_btn.clicked.connect(self._on_download)
        btn_h.addWidget(dl_btn)
        layout.addLayout(btn_h)

    def _on_download(self):
        self.never_notify = self.never_cb.isChecked()
        self.accept()

    def _on_ignore(self):
        self.never_notify = self.never_cb.isChecked()
        self.reject()


class UpdateReadyDialog(QDialog):
    """Shown after a successful download; asks whether to close this version and move to the new one."""
    def __init__(self, parent_window, new_path, old_path, tag, mode=UPDATE_MODE_SWAP):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.setWindowTitle("Launch Update? - yt-msd")
        self.setFixedWidth(520)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title_lbl = QLabel("UPDATE DOWNLOADED")
        title_lbl.setFont(QFont("Segoe UI Semibold", 11))
        layout.addWidget(title_lbl)

        self.mode = mode
        if mode == UPDATE_MODE_INSTALLER:
            # The download is a setup program, not another copy of this program: it
            # replaces the whole yt-msd folder, so this file is not the thing that
            # gets removed.
            desc = QLabel(
                f"The new version ({tag}) has been downloaded to:\n{new_path}\n\n"
                "Would you like to close this version and run that installer? It replaces "
                "the whole yt-msd folder, so this file is left where it is until the "
                "installer has finished. Choosing Cancel leaves both untouched."
            )
            ok_tip = "Close this version and run the setup program"
            cancel_tip = "Keep both files; run the setup program yourself"
        elif mode == UPDATE_MODE_REPLACE:
            # The download was written over the file this program was started from,
            # so the update is already on disk and only a restart is missing.
            desc = QLabel(
                f"The new version ({tag}) has been downloaded over the yt-msd file you are running:\n{new_path}\n\n"
                "Would you like to close this version and launch that file? Choosing Cancel leaves "
                "the updated file where it is and keeps this version running until you close it."
            )
            ok_tip = "Close this version and launch the updated file"
            cancel_tip = "Keep this version running; restart it yourself later"
        else:
            desc = QLabel(
                f"The new version ({tag}) has been downloaded to:\n{new_path}\n\n"
                "Would you like to automatically close this version, delete the old file, and launch the new version? "
                "Choosing Cancel keeps both files so you can swap them yourself."
            )
            ok_tip = "Close this version, delete the old file, and launch the new version"
            cancel_tip = "Keep both files; swap them manually"
        desc.setWordWrap(True)
        layout.addWidget(desc)

        if mode == UPDATE_MODE_SWAP:
            old_lbl = QLabel(f"Old version file that would be removed: {old_path}")
            old_lbl.setWordWrap(True)
            old_lbl.setStyleSheet("color: #888; font-size: 11px;")
            layout.addWidget(old_lbl)

        layout.addStretch()

        btn_h = QHBoxLayout()
        btn_h.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip(cancel_tip)
        cancel_btn.clicked.connect(self.reject)
        btn_h.addWidget(cancel_btn)

        ok_btn = QPushButton("OK")
        ok_btn.setToolTip(ok_tip)
        ok_btn.clicked.connect(self.accept)
        btn_h.addWidget(ok_btn)
        layout.addLayout(btn_h)


class YtDlpUpdateDialog(QDialog):
    """Notifies the user that the system yt-dlp is behind and offers to update it."""
    def __init__(self, parent_window, installed_version, latest_version):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.never_notify = False
        self.setWindowTitle("yt-dlp Update Available - yt-msd")
        self.setFixedWidth(470)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title_lbl = QLabel("A NEW YT-DLP VERSION IS AVAILABLE")
        title_lbl.setFont(QFont("Segoe UI Semibold", 11))
        layout.addWidget(title_lbl)

        desc = QLabel(
            f"yt-msd searches and downloads with the yt-dlp installed on this system.\n"
            f"Installed: {installed_version}    Newest: {latest_version}\n"
            "yt-msd can run winget to bring it up to date."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(desc)

        self.never_cb = QCheckBox("Never notify me about yt-dlp updates")
        self.never_cb.setToolTip("Stop checking for yt-dlp updates (yt-msd updates are not affected)")
        layout.addWidget(self.never_cb)

        layout.addStretch()

        btn_h = QHBoxLayout()
        btn_h.addStretch()

        ignore_btn = QPushButton("Ignore")
        ignore_btn.setToolTip("Keep the current yt-dlp until the next check")
        ignore_btn.clicked.connect(self._on_ignore)
        btn_h.addWidget(ignore_btn)

        update_btn = QPushButton("Update with winget")
        update_btn.setToolTip("Run: winget upgrade --id yt-dlp.yt-dlp")
        update_btn.clicked.connect(self._on_update)
        btn_h.addWidget(update_btn)
        layout.addLayout(btn_h)

    def _on_update(self):
        self.never_notify = self.never_cb.isChecked()
        self.accept()

    def _on_ignore(self):
        self.never_notify = self.never_cb.isChecked()
        self.reject()


def _sanitize_filename(name: str) -> str:
    """Strip characters that Windows filenames cannot contain."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    return re.sub(r'\s+', ' ', cleaned).strip(' .')


def _split_artist_title(stem: str) -> Tuple[str, str]:
    """Best-effort 'Artist - Title' split, used to pre-fill the renamer when a
    file has no tags but is already named in that format."""
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
        return artist.strip(), title.strip()
    return "", stem.strip()


class MetadataRenameDialog(QDialog):
    """Metadata renamer used by the local file editor.

    Reads the artist/title tags embedded in each selected track, lets the user
    correct them inline, then renames every file to 'Artist - Title' from that
    metadata. The (possibly edited) tags can also be written back into the file.
    """

    def __init__(self, parent_window, file_paths):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.file_paths = list(file_paths)
        self.results = []
        self.rows = []
        self.setWindowTitle("Rename From Metadata")
        self.setWindowFlags(self.windowFlags() | Qt.Tool)

        row_h = 30
        max_visible_rows = 8

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        title_lbl = QLabel(f"RENAME {len(self.file_paths)} FILE(S) FROM METADATA")
        title_lbl.setFont(QFont("Segoe UI Semibold", 10))
        title_lbl.setToolTip("Artist and title are read from each file's tags. Correct them here and the "
                            "file is renamed to 'Artist - Title'.")
        layout.addWidget(title_lbl)

        # One compact line per file: current name, editable artist, editable
        # title, and the resulting 'Artist - Title' name.
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(3)
        grid.setColumnMinimumWidth(0, 168)
        grid.setColumnMinimumWidth(3, 168)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        for col, header in enumerate(("Current File", "Artist", "Title", "New Name")):
            head = QLabel(header)
            head.setFont(QFont("Segoe UI Semibold", 8))
            head.setStyleSheet("color: #888; font-size: 10px;")
            grid.addWidget(head, 0, col)

        for row_idx, path in enumerate(self.file_paths, start=1):
            p = Path(path)
            artist, title = read_metadata_tags(p)
            if not title:
                guess_artist, guess_title = _split_artist_title(p.stem)
                artist = artist or guess_artist
                title = title or guess_title
            artist_edit = QLineEdit(artist or "")
            title_edit = QLineEdit(title or "")
            # The app-wide line edit style uses generous padding, which clips the
            # text inside a one-line-tall row; trim it and give the row enough
            # height for the full glyph height of the UI font.
            for edit in (artist_edit, title_edit):
                edit.setObjectName("renameField")
                edit.setStyleSheet("padding: 2px 4px;")
                edit.setFixedHeight(row_h)
            old_lbl = QLabel(self._elide(p.name, 164))
            old_lbl.setToolTip(path)
            new_lbl = QLabel("")
            new_lbl.setObjectName("durationLabel")
            row = {'path': str(p), 'artist_edit': artist_edit, 'title_edit': title_edit, 'new_lbl': new_lbl}
            artist_edit.textChanged.connect(lambda _, r=row: self._update_preview(r))
            title_edit.textChanged.connect(lambda _, r=row: self._update_preview(r))
            self._update_preview(row)
            grid.addWidget(old_lbl, row_idx, 0)
            grid.addWidget(artist_edit, row_idx, 1)
            grid.addWidget(title_edit, row_idx, 2)
            grid.addWidget(new_lbl, row_idx, 3)
            self.rows.append(row)

        # Only very large selections scroll, and even then the dialog stays short.
        if len(self.rows) > max_visible_rows:
            body = QWidget()
            body.setLayout(grid)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidget(body)
            layout.addWidget(scroll, 1)
        else:
            layout.addLayout(grid)
        self.resize(700, 108 + min(len(self.rows), max_visible_rows) * (row_h + 3))

        self.write_tags_cb = QCheckBox("Write tags back into the file (MP3, M4A)")
        self.write_tags_cb.setChecked(True)
        self.write_tags_cb.setToolTip("Update the embedded tags so they match the new file name")
        self.write_tags_cb.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.write_tags_cb)

        btn_h = QHBoxLayout()
        btn_h.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip("Close without renaming anything")
        cancel_btn.clicked.connect(self.reject)
        rename_btn = QPushButton("Rename")
        rename_btn.setToolTip("Rename the selected files to 'Artist - Title'")
        rename_btn.clicked.connect(self._apply_renames)
        accent = get_accent_color(parent_window.accent_color_name if parent_window else "Blue")
        r = int(accent[1:3], 16); g = int(accent[3:5], 16); b = int(accent[5:7], 16)
        accent_fg = "black" if (r * 299 + g * 587 + b * 114) / 1000 > 150 else "white"
        rename_btn.setStyleSheet(f"background-color: {accent}; color: {accent_fg}; border-radius: 4px; padding: 4px 10px; font-weight: bold;")
        cancel_btn.setStyleSheet("background-color: #555555; color: white; border-radius: 4px; padding: 4px 10px; font-weight: bold;")
        btn_h.addWidget(cancel_btn)
        btn_h.addWidget(rename_btn)
        layout.addLayout(btn_h)
        if self.rows:
            self.rows[0]['title_edit'].setFocus()

    def _elide(self, text: str, width: int) -> str:
        fm = QFontMetrics(QFont("Segoe UI", 10))
        return fm.elidedText(text, Qt.ElideRight, width)

    def _new_stem_for(self, row) -> str:
        artist = row['artist_edit'].text().strip()
        title = row['title_edit'].text().strip()
        combined = f"{artist} - {title}" if artist and title else (title or artist)
        return _sanitize_filename(combined)

    def _update_preview(self, row):
        stem = self._new_stem_for(row)
        suffix = Path(row['path']).suffix
        text = f"{stem}{suffix}" if stem else "(enter an artist or a title)"
        row['new_lbl'].setText(self._elide(text, 164))
        row['new_lbl'].setToolTip(text)

    def _apply_renames(self):
        write_tags = self.write_tags_cb.isChecked()
        for row in self.rows:
            old = Path(row['path'])
            artist = row['artist_edit'].text().strip()
            title = row['title_edit'].text().strip()
            if not old.exists():
                self.results.append({'old': str(old), 'new': str(old), 'name': old.name,
                                     'status': 'missing', 'message': 'File no longer exists'})
                continue
            stem = self._new_stem_for(row)
            if not stem:
                self.results.append({'old': str(old), 'new': str(old), 'name': old.name,
                                     'status': 'skipped', 'message': 'Artist and title are both empty'})
                continue
            new_path = old.with_name(f"{stem}{old.suffix}")
            if new_path == old:
                status = 'unchanged'
            elif new_path.exists():
                self.results.append({'old': str(old), 'new': str(new_path), 'name': old.name,
                                     'status': 'conflict', 'message': f"'{new_path.name}' already exists"})
                continue
            try:
                old.rename(new_path)
                status = 'renamed'
            except Exception as e:
                self.results.append({'old': str(old), 'new': str(old), 'name': old.name,
                                     'status': 'failed', 'message': str(e)})
                continue
            if write_tags and artist and title:
                write_metadata_tags(new_path, artist, title)
            self.results.append({'old': str(old), 'new': str(new_path), 'name': old.name,
                                 'status': status, 'message': new_path.name})
        self.accept()

class MainApp(QMainWindow):
    status_signal = Signal(str, bool, str)
    search_results_signal = Signal(list, bool)
    search_failed_signal = Signal()
    thumbnails_loaded_signal = Signal(str, QPixmap)
    playback_started_signal = Signal(str, str, bool)
    queue_update_signal = Signal()
    queue_status_changed_signal = Signal(int)
    dl_progress_signal = Signal(str)
    renamer_finished_signal = Signal()
    host_activity_signal = Signal(str, str, str)
    _probe_results_signal = Signal(dict)  # cached drive/chain state from the drive probe thread
    local_list_refresh_signal = Signal()  # ask for a non-blocking local folder rescan
    _local_listing_signal = Signal(object)  # (render_id, folder_path, items) from the folder scan thread
    update_available_signal = Signal(str, str, str, str)  # tag, release_name, download_url, asset_name
    update_downloaded_signal = Signal(str, str, str)  # new_file_path, tag, how it is applied (emitted from the download bg thread)
    missing_deps_signal = Signal(str)  # html fragment of missing dependencies (emitted from the VLC init thread)
    import_finished_signal = Signal(object)  # prepared export package, read on the import thread
    import_failed_signal = Signal(str)  # import problem, reported from the import thread
    ytdlp_missing_signal = Signal(str)  # yt-dlp absent or not installable (from a bg thread)
    ytdlp_update_signal = Signal(str, str)  # installed yt-dlp version, newest yt-dlp version
    ytdlp_version_signal = Signal(str)  # yt-dlp version found by a bg thread, shown on the GUI thread
    stream_refreshed_signal = Signal(bool, str)  # (re-resolved ok, track title) from the stream-refresh thread

    def __init__(self):
        super().__init__()
        self.setWindowTitle("yt-msd | YouTube Media Downloader")
        # Started by the MusicBee plugin (it passes --from-musicbee, see
        # MusicBee Plugin/Plugin.cs): open compact, and come back at whatever size
        # and position it was last closed at. Started normally, nothing changes.
        self.launched_by_host = "--from-musicbee" in sys.argv
        if self.launched_by_host:
            self.resize(1100, 700)
        else:
            self.resize(1804, 935)
        
        # State Arrays
        self.search_results = []
        self.queue_items = []
        self.local_folders = []
        self.recent_folders = []
        self.recent_playlists = []
        # Local file editor state: File Explorer style multi-selection.
        self.local_selected_paths = set()
        self.local_rows = []
        self.local_row_by_path = {}
        self.local_btns = []
        # Every folder switch gets its own id. Rows produced by a scan of a folder that
        # has already been replaced are dropped by it instead of landing on the folder
        # that is on screen now.
        self._local_render_id = 0
        # The listing of the folder currently filling the pane, less the rows that have
        # already been drawn, plus what the last chunk cost the GUI thread. A fill that is
        # still running is abandoned by the next folder switch.
        self._local_render_pending = None
        self._local_render_pending_id = 0
        self._local_render_pending_path = None
        self._local_render_step = 0
        self._local_render_chunk_end = None
        self._local_render_chunk_cost = 0.0
        self._local_render_chunk_rows = 0
        self._local_render_row_cost = 0.0
        self._local_render_row_height = LOCAL_RENDER_ROW_HEIGHT_GUESS
        # How many rows the folder on screen is going to have, and the height already handed to
        # the pane for them. See _reserve_local_extent.
        self._local_render_total_rows = 0
        self._local_render_extent_height = 0
        # Chunk N+1 is queued on a zero timer, which Qt runs after it has already laid out
        # and polished chunk N - the reason a folder fills in instead of arriving at once.
        self._local_render_timer = QTimer()
        self._local_render_timer.setSingleShot(True)
        self._local_render_timer.timeout.connect(self._fill_local_chunk)
        self.local_selection_anchor = None
        self.current_local_file_path = ""
        self.splitter_sizes = [300, 800, 300]
        # Qt's own serialisation of the window frame, kept only for windows that
        # were opened from MusicBee. See _apply_host_window_geometry.
        self.host_window_geometry = ""
        self.thumbnail_cache = {}
        self.thumbnail_cache_size = 0
        
        # Config Map
        self.format_var = "mp3"
        self.bitrate_var = "192"
        self.download_path = ""
        self.local_current_path = ""
        self.appearance_mode = "Dark" 
        self.accent_color_name = "Blue"
        self.volume_val = 100
        self.use_custom_args = False
        self.custom_args = ""
        self.minimize_to_tray = False
        self.save_place = False
        self.last_session = {}
        self.last_search = ""
        self.run_renamer = False
        self.renamer_path = ""
        self.run_custom_script = False
        self.custom_script_path = ""
        self._last_downloaded_files = []
        self.normalization_mode = "ask"  # "on" | "off" | "ask"
        self.auto_rename = False
        self.silence_pad_dur = 2.0
        self.silence_trim = True
        self.use_custom_norm_cmd = False
        self.custom_norm_cmd = ""
        self.download_threads = 3
        self.normalization_threads = max(1, os.cpu_count() // 2)
        self.local_rescan_interval = 60  # minutes (default 1 hour)
        self.disable_update_checks = False  # True once the user opts out of update notifications
        self._update_check_running = False  # guards against overlapping network update checks
        self._downloaded_update_tag = None  # tag already downloaded this session (avoid re-prompting)
        self.ytdlp_version = ""  # version the system yt-dlp reported, "" until it is known
        self.disable_ytdlp_updates = False  # True once the user opts out of yt-dlp update prompts
        self.ytdlp_last_update_check = 0.0  # epoch seconds of the last yt-dlp version check
        self._ytdlp_update_check_running = False  # guards against overlapping yt-dlp checks
        self.local_rescan_timer = QTimer(self)
        self.local_rescan_timer.timeout.connect(self._auto_rescan_local_folder)
        
        # Player Flags
        self.is_playing = False
        self.is_downloading = False
        self.cancel_download = False
        self.current_video_id = None
        self.current_playing_title = ""
        self.playback_index = -1
        # The row currently carrying the playing/paused colour: (pane, key, state), or None.
        # Compared against on every player tick so the colour moves only when it has to.
        self._playback_box = None
        self.is_shuffled = False
        self.shuffle_history = []
        self.shuffle_order = []
        # "Stop after current": off / once / always, cycled by the player-bar button
        # and the tray entry (see the prefetch and stop-after block near play_result).
        self.stop_after_current = STOP_AFTER_OFF
        # Which track an automatic "once" belongs to. A new search arms one for the
        # stream that is playing (see _arm_stop_after_for_new_search), and this id is
        # what lets that arming be forgotten again when a different track starts.
        # None means the armed state, if there is one, is the user's own.
        self._search_stop_after_track = None
        # Streams resolved seconds ahead of time: video id -> (url, user agent, epoch).
        # Written only by the prefetch thread, read once by the play path; the lock is
        # what keeps those two from tripping over the same dictionary.
        self._prefetched_streams = {}
        self._prefetch_lock = threading.Lock()
        self._prefetch_busy = set()     # video ids currently being resolved
        self._prefetch_decision = None  # (video id, next index, next video) decided ahead
        self._prefetch_trigger_key = None  # the track the decision was made for
        # The stream the player is actually loaded with: (video id, url, user agent, how old
        # that URL already was when it was resolved). This is what a dead stream is re-resolved
        # from, and it is None while a local file is playing or nothing has been played - a
        # file on disk is not a link with an expiry, so every question in the stream-liveness
        # block (see the block before "Stop after current") starts by asking whether this is set.
        # The rest is the watchdog for it: the last position libVLC reported and the moment it
        # last moved, whether the stream has been noticed dead, whether it is being re-resolved
        # right now, how many times this track has already reloaded itself, whether anybody has
        # ever heard this media advancing, and a position the user asked for that has to wait
        # until the fresh media answers.
        self._loaded_stream = None
        self._loaded_stream_at = None
        self._stream_seen_ms = -1
        self._stream_moved_at = None
        self._stream_dead = False
        # Only a stream that has been heard advancing can count as having gone idle, which is the
        # only case where the age of its URL is on its own a reason to re-resolve it. A track the
        # session restore preloads at start up starts here as False and stays that way until
        # somebody plays it. See _stream_needs_renew.
        self._stream_listened = False
        self._stream_refetching = False
        self._stream_refetch_attempts = 0
        self._stream_renew_started_at = None
        self._pending_stream_seek_frac = None
        self._pending_stream_seek_ms = None
        self._pending_stream_pause = False
        self._pending_stream_seek_at = None
        self.is_muted = False
        self.active_downloads = {}
        self.active_downloads_lock = threading.Lock()
        self.sync_manager_dialog = None
        self.last_wifi_ssid = get_current_wifi_ssid()
        # Persistent sync thread registry - lives at MainApp level so it survives dialog close/reopen
        self.sync_threads = {}  # chain_id -> QThread
        self.sync_progress_state = {}  # chain_id -> {'status': str, 'progress': str}
        # Runtime-only registry of currently connected removable drives (not persisted)
        self.active_removable_drives: dict = {}  # folder_path_str -> rc dict
        # Cached answers about the filesystem. Only the background probe thread
        # ever touches a drive; the GUI reads these instead, so a slow USB stick
        # or MP3 player can never stall the interface.
        self.known_connected_drives: set = set()  # drive roots seen by the last probe
        self.mount_state: dict = {}  # folder_path_str -> bool (mounted?)
        self.chain_track_counts: dict = {}  # chain_id -> audio file count
        self._drive_probe_lock = threading.Lock()
        self._drive_probe_busy = False
        self._drive_probe_pending = False
        # Only one import or export at a time: both do heavy filesystem work.
        self._export_import_busy = False
        # Guards the cached drive/chain state above: the probe thread reads it,
        # the GUI thread writes it.
        self._runtime_state_lock = threading.RLock()
        
        if getattr(sys, 'frozen', False):
            self.config_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            self.config_dir = os.path.dirname(os.path.abspath(__file__))
            
        self.config_path = os.path.join(self.config_dir, "gui_config.json")
        self.load_config()

        # Apply the normalization globals from the loaded config immediately
        global SILENCE_TRIM, SILENCE_PAD_DUR, CUSTOM_NORM_CMD
        SILENCE_TRIM = bool(self.silence_trim)
        SILENCE_PAD_DUR = float(self.silence_pad_dur)
        if self.use_custom_norm_cmd and self.custom_norm_cmd.strip():
            CUSTOM_NORM_CMD = self.custom_norm_cmd.strip()

        # Placeholder so UI code can check readiness before VLC is initialized
        self.vlc_instance = None
        self.vlc_player = None
        self._vlc_ready = False

        self.setup_ui()
        self.apply_theme()

        self.status_signal.connect(self._on_status_update)
        self.search_results_signal.connect(self._on_search_results)
        self.search_failed_signal.connect(self._on_search_failed)
        self.playback_started_signal.connect(self._on_playback_started)
        self.stream_refreshed_signal.connect(self._on_stream_refreshed)
        self.queue_update_signal.connect(self._refresh_queue_display)
        self.queue_status_changed_signal.connect(self._on_queue_status_changed)
        self.thumbnails_loaded_signal.connect(self._on_thumbnail_loaded)
        self.dl_progress_signal.connect(lambda txt: self.dl_progress_label.setText(txt))
        self.renamer_finished_signal.connect(self._on_renamer_finished)
        self.host_activity_signal.connect(self._on_host_activity)
        self._probe_results_signal.connect(self._apply_probe_results)
        self.local_list_refresh_signal.connect(self._refresh_local_list_async)
        self._local_listing_signal.connect(self._on_local_listing)
        self.update_available_signal.connect(self._show_update_dialog)
        self.update_downloaded_signal.connect(self._prompt_swap_dialog)
        self.missing_deps_signal.connect(self._show_missing_dependencies)
        self.import_finished_signal.connect(self._apply_import_results)
        self.import_failed_signal.connect(self._on_import_failed)
        self.ytdlp_missing_signal.connect(self._show_ytdlp_missing_dialog)
        self.ytdlp_update_signal.connect(self._show_ytdlp_update_dialog)
        self.ytdlp_version_signal.connect(self._apply_ytdlp_version)

        self.player_timer = QTimer(self)
        self.player_timer.timeout.connect(self.update_player_ui)
        self.player_timer.start(16)

        self.setup_tray()
        self._update_local_rescan_timer()

        # Wi-Fi network change monitor timer (checks every 15s)
        self.wifi_monitor_timer = QTimer(self)
        self.wifi_monitor_timer.timeout.connect(self._check_wifi_network_change)
        self.wifi_monitor_timer.start(15000)

        # Removable drive auto-detect timer (checks every 3s for plugged drives with TAG.yaml).
        # The very first probe is deferred: enumerating drives at startup would
        # stat every root on the UI thread, including a slow player that happens
        # to be plugged in.
        self.drive_monitor_timer = QTimer(self)
        self.drive_monitor_timer.timeout.connect(self._check_removable_drives_change)
        self.drive_monitor_timer.start(3000)
        QTimer.singleShot(600, self._check_removable_drives_change)

        # Startup dependency validation runs inside the VLC init thread below,
        # so it never blocks the UI thread while the window is appearing.

        # Update check on startup (runs again with every local-folder rescan)
        QTimer.singleShot(1500, self._check_for_updates)

        # Initialize VLC in a background thread (plugin scanning can take seconds)
        threading.Thread(target=self._init_vlc_background, daemon=True).start()

        # yt-dlp lives outside the executable: find it, and install it with winget
        # on the first run. This stays in a background thread so the window still
        # appears exactly as fast as before.
        threading.Thread(target=self._ensure_yt_dlp_background, daemon=True).start()

        # Defer local folder load until after the window is shown
        if self.local_current_path:
            QTimer.singleShot(0, lambda: self.load_local_folder(self.local_current_path))

        if getattr(self, 'save_place', False) and hasattr(self, 'session_data'):
            sd = self.session_data
            if sd.get('current_video_id') == "local" and sd.get('local_current_path'):
                idx = sd.get('local_playback_index', -1)
                # The folder opened above has only just started streaming its rows, so
                # the track to resume on is remembered here and looked up by
                # _finish_local_render, which runs when that list is actually complete.
                # The folder it belongs to is remembered with it, because a folder that
                # cannot be opened - or one the user switches away from before the rows
                # land - must not have a track of another folder resumed in it.
                self._pending_local_restore_index = idx
                self._pending_local_restore_path = sd.get('local_current_path')

        # --- Local Network Sync Chains Subsystem ---
        self.sync_config_manager = SyncConfigManager(self.config_dir)
        self.sync_host_server = SyncHostServer(
            lambda: self.sync_config_manager.hosted_chains,
            on_client_activity_cb=self.host_activity_signal.emit
        )
        self.udp_beacon = UDPBeaconBroadcaster(
            lambda: self.sync_config_manager.hosted_chains,
            lambda: self.sync_host_server.active_port,
            on_chain_updated_cb=self._on_lan_chain_updated
        )
        self.host_watcher = HostFolderWatcher(self._on_hosted_folder_changed)

        # Client Auto-Sync Periodic Timer
        self.sync_timer = QTimer(self)
        self.sync_timer.timeout.connect(self._auto_sync_client_chains)

        # Start host server, UDP beacon, folder watchers, and client check on a background thread
        def _deferred_sync_startup():
            def _bg_init():
                try:
                    self.sync_host_server.start()
                    self.udp_beacon.start()
                    self.refresh_sync_watchers()
                except Exception:
                    pass
            threading.Thread(target=_bg_init, daemon=True).start()
            self._update_sync_timer()
            QTimer.singleShot(2500, self._auto_sync_client_chains)

        QTimer.singleShot(150, _deferred_sync_startup)

        if self.launched_by_host:
            self._apply_host_window_geometry()

        QApplication.instance().installEventFilter(self)

    def _on_host_activity(self, sync_code: str, client_ip: str, activity: str):
        """Called when a client connects or pulls files from our hosted sync chain."""
        chain_name = "Playlist"
        if hasattr(self, 'sync_config_manager'):
            for c in self.sync_config_manager.hosted_chains:
                if str(c.get('sync_code')) == str(sync_code):
                    chain_name = c.get('name', 'Playlist')
                    break
        msg = f"[Sync Host: {chain_name}] {activity} ({client_ip})"
        if hasattr(self, 'dl_progress_signal'):
            self.dl_progress_signal.emit(msg)
            def _clear_prog():
                try:
                    if self.dl_progress_label.text() == msg:
                        self.dl_progress_signal.emit("")
                except Exception:
                    pass
            QTimer.singleShot(4000, _clear_prog)
        if hasattr(self, 'sync_manager_dialog') and self.sync_manager_dialog and self.sync_manager_dialog.isVisible():
            self.sync_manager_dialog._on_host_activity_received(sync_code, client_ip, activity)

    def _on_renamer_finished(self):
        self._on_status_update("MP3 Renamer finished execution.", False, "#1abd33")
        self.refresh_local_list()

    def _update_local_rescan_timer(self):
        mins = getattr(self, 'local_rescan_interval', 60)
        if mins > 0:
            self.local_rescan_timer.start(mins * 60 * 1000)
        else:
            self.local_rescan_timer.stop()

    def _auto_rescan_local_folder(self):
        # Hourly auto-rescan: the folder scan runs on a worker thread so a slow
        # drive cannot freeze the window when the timer fires.
        self._refresh_local_list_async()
        # Every local-folder scan (startup + the hourly auto-rescan) also checks for updates.
        self._check_for_updates()
        # ... and the same pass checks whether the yt-dlp on this system is out of
        # date (that check throttles itself, so it is not a network call every hour).
        self._check_yt_dlp_updates()

    def refresh_sync_watchers(self):
        """Registers all hosted sync chains with the watchdog monitor in a background thread."""
        if hasattr(self, 'host_watcher') and hasattr(self, 'sync_config_manager'):
            def _bg():
                try:
                    self.host_watcher.stop_all()
                    for hc in list(self.sync_config_manager.hosted_chains):
                        cid = hc.get('id')
                        folder = hc.get('folder_path')
                        code = hc.get('sync_code')
                        delay = hc.get('notify_delay_mins', 5)
                        if cid and folder and code:
                            self.host_watcher.add_or_update_chain(cid, folder, code, delay)
                except Exception:
                    pass
            threading.Thread(target=_bg, daemon=True).start()

    def _on_hosted_folder_changed(self, sync_code: str):
        """Called from the folder watcher's debounce thread when a hosted folder changes."""
        port = self.sync_host_server.active_port if hasattr(self, 'sync_host_server') else 63350
        send_lan_update_notification(sync_code, port)
        # Emitted, not called directly: this runs on a watcher thread.
        self.status_signal.emit(f"Sync Chain (Code {sync_code}) updated. Notified clients on LAN.", False, "#1abd33")

    def _update_sync_timer(self):
        if hasattr(self, 'sync_config_manager') and hasattr(self, 'sync_timer'):
            mins = self.sync_config_manager.settings.get('auto_sync_interval_mins', 30)
            if mins > 0:
                self.sync_timer.start(mins * 60 * 1000)
            else:
                self.sync_timer.stop()

    def _auto_sync_client_chains(self):
        """Background routine that runs sync checks for all client sync chains with live progress reporting."""
        if not hasattr(self, 'sync_config_manager') or not self.sync_config_manager.client_chains:
            return

        def _bg():
            # Asked for here rather than before the thread starts: this is a
            # subprocess call and it has no business running on the UI thread.
            curr_wifi = get_current_wifi_ssid()
            for cc in list(self.sync_config_manager.client_chains):
                # Respect pause duration
                paused, _ = is_client_chain_paused(cc)
                if paused:
                    continue

                # Respect Wi-Fi binding if set
                req_wifi = cc.get('wifi_ssid', '').strip()
                if req_wifi and curr_wifi and req_wifi.lower() != curr_wifi.lower():
                    continue

                chain_name = cc.get('name', 'Sync')
                def _status(t):
                    if hasattr(self, 'dl_progress_signal'):
                        self.dl_progress_signal.emit(f"[Sync: {chain_name}] {t}")

                def _prog(done, total, fname, idx, total_items):
                    pct = int(done / total * 100) if total > 0 else 0
                    if hasattr(self, 'dl_progress_signal'):
                        self.dl_progress_signal.emit(f"[Sync: {chain_name}] [{idx}/{total_items}] ({pct}%) {fname}")

                ok, msg, transferred, deleted = SyncClientWorker.sync_chain(
                    cc,
                    status_cb=_status,
                    progress_cb=_prog
                )
                if hasattr(self, 'dl_progress_signal'):
                    self.dl_progress_signal.emit("")
                if ok:
                    cc['last_synced'] = time.time()
                    cc['status'] = "Up to date"
                    if transferred > 0 or deleted > 0:
                        self.status_signal.emit(f"Sync Chain '{cc.get('name')}': {transferred} updated, {deleted} removed.", False, "#1abd33")
                        if self.local_current_path == cc.get('folder_path'):
                            self.local_list_refresh_signal.emit()
                else:
                    cc['status'] = f"Host Offline"
            self.sync_config_manager.save()

        threading.Thread(target=_bg, daemon=True).start()

    def _on_lan_chain_updated(self, sync_code: str):
        """Called from the UDP beacon thread when a host announces an update."""
        if not hasattr(self, 'sync_config_manager') or not self.sync_config_manager.client_chains:
            return
        matching = [cc for cc in self.sync_config_manager.client_chains if str(cc.get('sync_code')) == str(sync_code)]
        if not matching:
            return

        for cc in matching:
            def _bg(c=cc):
                # Pause checks, the Wi-Fi lookup and the status line all belong
                # in the worker: this callback arrives on the beacon thread.
                paused, _ = is_client_chain_paused(c)
                if paused:
                    return
                req_wifi = c.get('wifi_ssid', '').strip()
                if req_wifi:
                    curr_wifi = get_current_wifi_ssid()
                    if curr_wifi and req_wifi.lower() != curr_wifi.lower():
                        return

                self.status_signal.emit(
                    f"Sync Chain '{c.get('name', 'Sync')}': Push notification received from host. Syncing...",
                    False, "#3B8ED0")

                ok, msg, transferred, deleted = SyncClientWorker.sync_chain(
                    c,
                    status_cb=lambda t: self.dl_progress_signal.emit(f"[Sync: {c.get('name', 'Sync')}] {t}") if hasattr(self, 'dl_progress_signal') else None,
                    progress_cb=lambda done, total, fname, idx, total_items: self.dl_progress_signal.emit(
                        f"[Sync: {c.get('name', 'Sync')}] [{idx}/{total_items}] ({int(done/total*100) if total > 0 else 0}%) {fname}"
                    ) if hasattr(self, 'dl_progress_signal') else None
                )
                if hasattr(self, 'dl_progress_signal'):
                    self.dl_progress_signal.emit("")
                if ok:
                    c['last_synced'] = time.time()
                    c['status'] = "Up to date"
                    if transferred > 0 or deleted > 0:
                        self.status_signal.emit(f"Sync Chain '{c.get('name')}': {transferred} updated, {deleted} removed.", False, "#1abd33")
                        if self.local_current_path == c.get('folder_path'):
                            self.local_list_refresh_signal.emit()
                self.sync_config_manager.save()
            threading.Thread(target=_bg, daemon=True).start()

    def _check_wifi_network_change(self):
        """Monitors for Wi-Fi SSID changes and triggers auto-sync for bound sync chains."""
        def _bg():
            curr = get_current_wifi_ssid()
            if not curr:
                return
            last = getattr(self, 'last_wifi_ssid', None)
            if curr != last:
                self.last_wifi_ssid = curr
                if hasattr(self, 'sync_config_manager') and self.sync_config_manager.client_chains:
                    bound = [
                        cc for cc in self.sync_config_manager.client_chains
                        if cc.get('wifi_ssid', '').strip().lower() == curr.lower() and not is_client_chain_paused(cc)[0]
                    ]
                    if bound:
                        self.status_signal.emit(f"Connected to Wi-Fi '{curr}': Auto-syncing bound sync chain(s)...", False, "#1abd33")
                        self._auto_sync_client_chains()
        threading.Thread(target=_bg, daemon=True).start()

    def _get_current_system_drives(self) -> set:
        drives = set()
        _skip_drives = {'C:\\'}  # Never scan the system drive
        if sys.platform == 'win32':
            try:
                import ctypes
                bitmask = ctypes.windll.kernel32.GetLogicalDrives()
                for i in range(26):
                    if bitmask & (1 << i):
                        drive = f"{chr(65 + i)}:\\"
                        if drive.upper() in _skip_drives:
                            continue
                        if os.path.exists(drive):
                            drives.add(drive)
            except Exception:
                import string
                for letter in string.ascii_uppercase:
                    drive = f"{letter}:\\"
                    if drive.upper() in _skip_drives:
                        continue
                    if os.path.exists(drive):
                        drives.add(drive)
        return drives

    def _check_removable_drives_change(self):
        """Starts a drive probe. Performs no filesystem work on the GUI thread."""
        if not hasattr(self, 'sync_config_manager'):
            return
        with self._drive_probe_lock:
            if self._drive_probe_busy:
                # A slow device can keep a probe busy for a while. Instead of
                # stacking threads on top of the same busy drive, ask the one
                # that is already running to do one more pass when it finishes.
                self._drive_probe_pending = True
                return
            self._drive_probe_busy = True
            # Whether the sync manager is open is decided here, on the GUI
            # thread, so the probe thread never has to ask a widget anything.
            collect_counts = bool(self.sync_manager_dialog and self.sync_manager_dialog.isVisible())
        threading.Thread(target=self._probe_drives_background, args=(collect_counts,), daemon=True).start()

    def _probe_drives_background(self, collect_counts: bool = False):
        """Every drive touch the sync monitor makes happens here, off the UI thread."""
        try:
            while True:
                with self._drive_probe_lock:
                    self._drive_probe_pending = False

                payload = {'drives': set(), 'mount_updates': {}, 'removed': [],
                           'scanned': [], 'counts': {}}
                try:
                    current_drives = self._get_current_system_drives()
                except Exception:
                    current_drives = set()
                payload['drives'] = current_drives

                # Mount state for the removable chains already registered
                with self._runtime_state_lock:
                    registered_paths = list(self.active_removable_drives.keys())
                for fp in registered_paths:
                    try:
                        mounted = os.path.exists(fp)
                    except Exception:
                        mounted = False
                    payload['mount_updates'][fp] = mounted
                    if not mounted:
                        payload['removed'].append(fp)

                # Look for TAG.yaml folders on the remaining drives
                busy_roots = self._busy_drive_roots()
                _skip = {'C:\\'}
                for drive in sorted(current_drives):
                    if drive.upper() in _skip:
                        continue
                    if str(Path(drive).anchor) in busy_roots:
                        # A sync is mid-transfer on this device; its contents
                        # are already known, so do not interrupt it with a scan.
                        continue
                    try:
                        tagged_folders = find_tagged_sync_folders_on_drive(drive)
                    except Exception:
                        continue
                    for folder_path, tag_data in tagged_folders:
                        sync_code = str(tag_data.get('sync_code', '')).strip()
                        if not sync_code:
                            continue
                        f_str = str(folder_path)
                        del_mode = tag_data.get('deletion_mode', 'mirror')
                        chain_name = (tag_data.get('chain_name', '') or
                                      folder_path.name or
                                      f"Drive ({drive[0]}:)")
                        cid = make_removable_chain_id(sync_code, f_str)
                        rc = {
                            'id': cid,
                            'sync_code': sync_code,
                            'name': chain_name,
                            'folder_path': f_str,
                            'deletion_mode': del_mode,
                            'last_synced': tag_data.get('last_synced', ''),
                            'status': 'Ready',
                            'drive_root': drive,
                        }
                        payload['scanned'].append(rc)
                        payload['mount_updates'][f_str] = True

                payload['counts'] = self._collect_chain_track_counts(collect_counts)
                # Deliver the cached results to the main thread
                self._probe_results_signal.emit(payload)

                with self._drive_probe_lock:
                    if not self._drive_probe_pending:
                        break
        finally:
            with self._drive_probe_lock:
                self._drive_probe_busy = False

    def _busy_drive_roots(self) -> set:
        """Drive roots that a sync thread is currently working on."""
        roots = set()
        with self._runtime_state_lock:
            running = list(self.sync_threads.values())
        for thread in running:
            try:
                if not thread.isRunning():
                    continue
            except (RuntimeError, AttributeError):
                continue
            cfg = getattr(thread, 'removable_config', None) or getattr(thread, 'chain_config', None)
            if not cfg:
                continue
            try:
                roots.add(str(Path(cfg.get('folder_path', '')).anchor))
            except Exception:
                pass
        return roots

    def _collect_chain_track_counts(self, collect_counts: bool = False) -> dict:
        """Track counts for the hosted cards, computed off the UI thread and only
        while the sync manager is actually open (the caller decides that on the
        GUI thread and passes the answer in)."""
        counts = {}
        if not collect_counts:
            return counts
        try:
            for hc in list(self.sync_config_manager.hosted_chains):
                cid = hc.get('id')
                folder = hc.get('folder_path', '')
                if not cid or not folder:
                    continue
                counts[cid] = len(filter_audio_files(Path(folder)))
        except Exception:
            pass
        return counts

    def _apply_probe_results(self, payload: dict):
        """Main-thread slot. Reads cached results only - never touches a drive."""
        if not isinstance(payload, dict):
            return
        new_chains = []
        with self._runtime_state_lock:
            self.known_connected_drives = payload.get('drives') or set()
            for fp, mounted in (payload.get('mount_updates') or {}).items():
                self.mount_state[fp] = bool(mounted)
            for fp in payload.get('removed') or []:
                self.active_removable_drives.pop(fp, None)
                self.mount_state.pop(fp, None)
            self.chain_track_counts = payload.get('counts') or {}

            for rc in payload.get('scanned') or []:
                f_str = rc['folder_path']
                sync_code = rc['sync_code']
                is_hosted = any(str(hc.get('sync_code', '')).strip() == sync_code
                                for hc in self.sync_config_manager.hosted_chains)
                is_client = any(str(cc.get('sync_code', '')).strip() == sync_code
                                for cc in self.sync_config_manager.client_chains)
                if f_str not in self.active_removable_drives:
                    self.active_removable_drives[f_str] = rc
                    self.mount_state[f_str] = True
                    if is_hosted or is_client:
                        new_chains.append(rc)
                else:
                    self.active_removable_drives[f_str]['name'] = rc['name']
                    self.active_removable_drives[f_str]['drive_root'] = rc['drive_root']

        for rc in new_chains:
            self._auto_sync_removable_chain(rc)

        # refresh_cards() skips the rebuild itself when nothing about the chains
        # changed, so this stays cheap even though the monitor runs every 3s.
        if self.sync_manager_dialog and self.sync_manager_dialog.isVisible():
            try:
                self.sync_manager_dialog.refresh_cards()
            except RuntimeError:
                pass

    def _auto_sync_removable_chain(self, rc: dict):
        """Launch a background removable chain sync via RemovableSyncThread so it shows in the sync manager."""
        cid = rc.get('id', '')
        # Don't start if already in progress
        existing = self.sync_threads.get(cid)
        if existing and existing.isRunning():
            return

        chain_name = rc.get('name', 'Removable Media')
        rc['status'] = 'Syncing...'
        self.sync_progress_state[cid] = {'status': 'Status: Syncing...  |  Last Synced: Syncing...', 'progress': ''}
        self.status_signal.emit(f"Removable media detected for '{chain_name}'. Starting auto-sync...", False, "#3B8ED0")
        if self.sync_manager_dialog and self.sync_manager_dialog.isVisible():
            try:
                self.sync_manager_dialog.refresh_cards()
            except RuntimeError:
                pass

        thread = RemovableSyncThread(rc, self.sync_config_manager)
        self.sync_threads[cid] = thread
        # The worker may stop short of overwriting a drive that holds a newer
        # version of the chain. Asking about that belongs on the GUI thread, so
        # the worker parks until this app answers it.
        thread.confirm_enabled = True
        thread.confirm_signal.connect(self._on_retrograde_sync_confirm)

        def _on_status(txt):
            status_text = f"Status: {txt}  |  Last Synced: Syncing..."
            self.sync_progress_state.setdefault(cid, {})['status'] = status_text
            if hasattr(self, 'dl_progress_signal'):
                self.dl_progress_signal.emit(f"[USB Sync: {chain_name}] {txt}")
            if self.sync_manager_dialog and self.sync_manager_dialog.isVisible():
                self.sync_manager_dialog._update_client_card_label(cid, "status_lbl", status_text)

        def _on_progress(done, total, fname, idx, total_items):
            pct = int(done / total * 100) if total > 0 else 0
            prog_txt = f"[{idx}/{total_items}] ({pct}%) {fname}"
            self.sync_progress_state.setdefault(cid, {})['progress'] = prog_txt
            if hasattr(self, 'dl_progress_signal'):
                self.dl_progress_signal.emit(f"[USB Sync: {chain_name}] {prog_txt}")
            if self.sync_manager_dialog and self.sync_manager_dialog.isVisible():
                self.sync_manager_dialog._update_client_card_label(cid, "progress_lbl", prog_txt)

        def _on_finish(ok, msg, transferred, deleted):
            # A skipped retrograde sync is a decision, not a fault, so it is
            # reported as such instead of as a failed sync.
            skipped = (not ok) and str(msg).startswith("Sync skipped")
            if ok:
                rc['status'] = "Up to date"
            elif skipped:
                rc['status'] = str(msg)
            else:
                rc['status'] = f"Sync Failed: {msg}"
            if ok:
                rc['last_synced'] = time.time()
            self.sync_progress_state.pop(cid, None)
            if hasattr(self, 'dl_progress_signal'):
                self.dl_progress_signal.emit("")
            if ok:
                self.status_signal.emit(f"Removable media '{chain_name}' sync complete: {transferred} updated, {deleted} removed.", False, "#1abd33")
            elif skipped:
                self.status_signal.emit(f"Removable media '{chain_name}' was left as it is: {msg}", False, "#FF8C00")
            else:
                self.status_signal.emit(f"Removable media '{chain_name}' sync failed: {msg}", False, "#E31E24")
            if self.sync_manager_dialog:
                try:
                    QTimer.singleShot(0, self.sync_manager_dialog.refresh_cards)
                except RuntimeError:
                    pass

        thread.status_signal.connect(_on_status)
        thread.progress_signal.connect(_on_progress)
        thread.finished_signal.connect(_on_finish)
        thread.start()

    def _on_retrograde_sync_confirm(self, chain_id: str, question: str):
        """Main-thread slot for a removable sync that stopped short of rolling a
        newer drive back to an older copy. The worker parks until this answers, so
        the question is asked on the GUI thread and defaulting to No keeps the
        drive exactly as it is."""
        thread = self.sync_threads.get(chain_id)
        if thread is None or not hasattr(thread, 'answer_confirm'):
            return
        parent = None
        try:
            if self.sync_manager_dialog is not None and self.sync_manager_dialog.isVisible():
                parent = self.sync_manager_dialog
        except RuntimeError:
            parent = None
        try:
            answer = QMessageBox.question(parent, "Removable Drive Holds a Newer Version", question,
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            proceed = (answer == QMessageBox.Yes)
        except Exception:
            proceed = False
        try:
            thread.answer_confirm(proceed)
        except RuntimeError:
            pass

    def open_sync_manager(self, parent_dialog=None):
        """Opens or brings the Sync Chains Manager to the foreground directly with Main < Settings < Sync stacking."""
        if self.sync_manager_dialog is not None:
            try:
                self.sync_manager_dialog.refresh_cards()
            except RuntimeError:
                self.sync_manager_dialog = None

        if self.sync_manager_dialog is None:
            dlg = SyncManagerDialog(self)
            self.sync_manager_dialog = dlg
            dlg.setWindowModality(Qt.NonModal)
            dlg.setAttribute(Qt.WA_DeleteOnClose, False)

        # Enforce stacking: Main window < Settings window < Sync window
        self.raise_()
        if parent_dialog and parent_dialog.isVisible():
            parent_dialog.raise_()
        elif hasattr(self, 'settings_dialog') and self.settings_dialog and self.settings_dialog.isVisible():
            self.settings_dialog.raise_()

        self.sync_manager_dialog.show()
        self.sync_manager_dialog.raise_()
        self.sync_manager_dialog.activateWindow()

    def _show_missing_dependencies(self, missing_html: str):
        """Show the startup dependency warning. Runs on the GUI thread; the probing
        itself happens in the background VLC-init thread (see _init_vlc_background)."""
        msg = QMessageBox(self)
        msg.setWindowTitle("Missing Required Dependencies - yt-msd")
        msg.setIcon(QMessageBox.Warning)
        msg.setTextFormat(Qt.RichText)
        msg.setText(
            "<h3>Required Dependencies Missing</h3>"
            "yt-msd detected that the following components are not installed or could not be found:<br><br>"
            + missing_html
            + "<br><br>Some features (music playback, audio conversion, normalization) will not function until installed."
        )
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()

    def _check_for_updates(self):
        """Query the GitHub releases page and notify the user if the newest release is newer than this build."""
        if getattr(self, 'disable_update_checks', False):
            return
        if getattr(self, '_update_check_running', False):
            return
        self._update_check_running = True

        def _bg():
            try:
                api_url = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
                req = urllib.request.Request(api_url, headers={"User-Agent": "yt-msd-updater"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                tag = (data.get("tag_name") or "").strip()
                release_name = (data.get("name") or tag).strip()
                assets = data.get("assets") or []
                # Which file is wanted depends on what kind of yt-msd this is, and it
                # is looked up by name: a release page lists its files in the order
                # they were uploaded, so the setup program is not always the first one.
                wanted_asset = INSTALLER_ASSET if is_packaged_build() else SOURCE_ASSET
                asset_name, download_url = select_release_asset(assets, wanted_asset)
                if not tag:
                    return
                if tag == getattr(self, '_downloaded_update_tag', None):
                    return  # already downloaded this session; don't nag again
                if _version_is_newer(_extract_version_number(tag), _extract_version_number(APP_VERSION)):
                    self.update_available_signal.emit(tag, release_name, download_url, asset_name)
            except Exception:
                pass
            finally:
                self._update_check_running = False

        threading.Thread(target=_bg, daemon=True).start()

    def _show_update_dialog(self, tag, release_name, download_url, asset_name):
        """Show the update dialog on the GUI thread and act on the user's choice."""
        dlg = UpdateAvailableDialog(self, tag, release_name, APP_VERSION, asset_name)
        choice = dlg.exec()
        if dlg.never_notify:
            self.disable_update_checks = True
            self.save_config()
        if choice != QDialog.Accepted:
            return
        if not download_url or not asset_name:
            wanted = INSTALLER_ASSET if is_packaged_build() else SOURCE_ASSET
            self.status_signal.emit(
                f"Release {tag} has no {wanted} file this copy of yt-msd can download.",
                False, "#E31E24"
            )
            return
        self._download_update(download_url, asset_name, tag)

    def _download_update(self, url, filename, tag):
        """Download the release file this kind of yt-msd needs, into the folder it runs from."""
        if not url:
            self.status_signal.emit("Update has no downloadable file to fetch.", False, "#E31E24")
            return
        running_path = self._current_executable_path()
        running_name = os.path.basename(running_path).lower()
        if is_packaged_build():
            # The installed program is updated by its setup program, which replaces the
            # whole yt-msd folder around this exe. Only a download carrying this exe's
            # own name is a file-for-file replacement of the running file.
            base_dir = self.config_dir
            if os.path.basename(filename).lower() == running_name:
                mode = UPDATE_MODE_SWAP
            else:
                mode = UPDATE_MODE_INSTALLER
        else:
            # A copy started from the source is updated by writing the new source file
            # over the very file that is being run, whatever the release page calls it.
            base_dir = os.path.dirname(running_path)
            filename = os.path.basename(running_path)
            mode = UPDATE_MODE_REPLACE
        dest_path = os.path.join(base_dir, filename)
        self.status_signal.emit(f"Downloading update {tag}...", False, "#3B8ED0")

        def _bg():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "yt-msd-updater"})
                with urllib.request.urlopen(req, timeout=120) as resp:
                    payload = resp.read()
                # The whole file is in memory before anything is written, so a failed
                # download never leaves a half-written file where yt-msd runs from.
                with open(dest_path, "wb") as out:
                    out.write(payload)
                self._downloaded_update_tag = tag
                self.status_signal.emit(f"Update {tag} downloaded to: {dest_path}", False, "#1abd33")
                self.update_downloaded_signal.emit(dest_path, tag, mode)
            except Exception as e:
                self.status_signal.emit(f"Update download failed: {e}", False, "#E31E24")

        threading.Thread(target=_bg, daemon=True).start()

    def _current_executable_path(self):
        """Absolute path of the file this instance is currently running from."""
        if is_packaged_build():
            return os.path.abspath(sys.executable)
        return os.path.abspath(__file__)

    def _prompt_swap_dialog(self, new_path, tag, mode=UPDATE_MODE_SWAP):
        """After a successful download, offer to close this version and move on to the new one."""
        old_path = self._current_executable_path()
        if mode == UPDATE_MODE_REPLACE:
            # The new source file was written over the file this program was started
            # from, so it already sits exactly where the old one was.
            new_path = old_path
        dlg = UpdateReadyDialog(self, new_path, old_path, tag, mode)
        choice = dlg.exec()
        if choice == QDialog.Accepted:
            # Only a drop-in update deletes the file this program was started from: an
            # installer overwrites the whole folder itself, and a replaced source file
            # is already in place.
            self._launch_swap_helper(new_path, old_path, delete_old=(mode == UPDATE_MODE_SWAP))
            # closeEvent() saves the settings, hides the tray, and ends the event
            # loop, which brings the process down a moment later - exactly what
            # the swap helper started above is waiting for.
            self.close()
        elif mode == UPDATE_MODE_INSTALLER:
            self.status_signal.emit(
                f"Update ready. Run {new_path} when you want to update yt-msd; this version is left as it is.",
                False, "#FF8C00"
            )
        elif mode == UPDATE_MODE_REPLACE:
            self.status_signal.emit(
                f"Update ready. {new_path} is already the new version; restart yt-msd to run it.",
                False, "#FF8C00"
            )
        else:
            self.status_signal.emit(
                f"Update ready. New file: {new_path} (old file kept: {old_path}). Swap them manually to finish.",
                False, "#FF8C00"
            )

    def _launch_swap_helper(self, new_path, old_path, delete_old=True):
        """Write a temporary helper script that waits for this process to exit, deletes the old file,
        launches the new version, then deletes itself."""
        pid = os.getpid()
        if is_packaged_build():
            launch_cmd = f'"{new_path}"'
        else:
            interp = os.path.abspath(sys.executable)
            # Prefer the windowless interpreter so the relaunched app doesn't open a console.
            if os.path.basename(interp).lower() == "python.exe":
                candidate = os.path.join(os.path.dirname(interp), "pythonw.exe")
                if os.path.exists(candidate):
                    interp = candidate
            launch_cmd = f'"{interp}" "{new_path}"'

        swap_path = os.path.join(tempfile.gettempdir(), f"ytmsd_swap_{pid}.bat")
        # UPDATE_MODE_INSTALLER leaves this file alone and lets the setup program
        # overwrite the whole yt-msd folder. UPDATE_MODE_REPLACE has already written the
        # new source file over this one, so there is nothing to delete. UPDATE_MODE_SWAP
        # is a drop-in update: the file this program was started from goes first.
        drop_old = (
            'if not "%OLD%"=="%NEW%" (\r\n'
            '  if exist "%OLD%" del /F /Q "%OLD%"\r\n'
            ')\r\n'
        ) if delete_old else ""
        bat = (
            "@echo off\r\n"
            f'set "PID={pid}"\r\n'
            f'set "OLD={old_path}"\r\n'
            f'set "NEW={new_path}"\r\n'
            'powershell -NoProfile -Command "while (Get-Process -Id %PID% -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 300 }"\r\n'
            + drop_old +
            f'start "" {launch_cmd}\r\n'
            'del /F /Q "%~f0"\r\n'
        )
        try:
            with open(swap_path, "w", encoding="utf-8") as f:
                f.write(bat)
        except Exception:
            return
        try:
            # CREATE_NO_WINDOW (0x08000000) keeps the helper itself invisible.
            subprocess.Popen(["cmd.exe", "/c", swap_path], creationflags=0x08000000)
        except Exception:
            pass

    def _ensure_yt_dlp_background(self):
        """First-run setup for yt-dlp: use the copy on this system, or install it.

        yt-dlp is not inside the yt-msd executable, so the first run has to put it
        on the machine. winget ships with Windows 10/11, so it is asked for the
        official yt-dlp package: nothing is installed into the yt-msd folder and
        nothing is installed through pip.
        """
        exe = find_yt_dlp_executable()
        version = get_yt_dlp_version(exe) if exe else ""
        if version:
            self.ytdlp_version_signal.emit(version)
            return

        self.status_signal.emit("yt-dlp not found - installing it with winget...", False, "#3B8ED0")
        rc, out, err = run_winget(["install", "--id", YTDLP_WINGET_ID, "-e",
                                   "--accept-package-agreements", "--accept-source-agreements",
                                   "--disable-interactivity"])
        exe = find_yt_dlp_executable(refresh=True)
        version = get_yt_dlp_version(exe) if exe else ""
        if version:
            self.ytdlp_version_signal.emit(version)
            self.status_signal.emit(f"yt-dlp {version} installed with winget.", False, "#1abd33")
            return

        lines = [line for line in (err or out or "").strip().splitlines() if line.strip()]
        self.ytdlp_missing_signal.emit(
            "yt-msd could not install yt-dlp automatically."
            + (f"<br><br>winget said: <code>{lines[-1]}</code>" if lines else "")
        )

    def _check_yt_dlp_updates(self):
        """Ask GitHub whether the yt-dlp on this system is behind, at most once per interval."""
        if getattr(self, 'disable_update_checks', False) or getattr(self, 'disable_ytdlp_updates', False):
            return
        if getattr(self, '_ytdlp_update_check_running', False):
            return
        last_check = float(getattr(self, 'ytdlp_last_update_check', 0.0) or 0.0)
        if last_check and (time.time() - last_check) < YTDLP_UPDATE_CHECK_INTERVAL:
            return
        self._ytdlp_update_check_running = True

        def _bg():
            try:
                installed = getattr(self, 'ytdlp_version', '') or get_yt_dlp_version()
                if not installed:
                    return
                self.ytdlp_version_signal.emit(installed)
                latest = latest_yt_dlp_release()
                # Remembered so the hourly rescan does not ask GitHub again for a week.
                self.ytdlp_last_update_check = time.time()
                if not latest:
                    return
                if _version_is_newer(_extract_version_number(latest), _extract_version_number(installed)):
                    self.ytdlp_update_signal.emit(installed, latest)
            except Exception:
                pass
            finally:
                self._ytdlp_update_check_running = False

        threading.Thread(target=_bg, daemon=True).start()

    def _show_ytdlp_missing_dialog(self, reason):
        """Explain how to get yt-dlp when it is missing and could not be installed."""
        msg = QMessageBox(self)
        msg.setWindowTitle("yt-dlp Not Installed - yt-msd")
        msg.setIcon(QMessageBox.Warning)
        msg.setTextFormat(Qt.RichText)
        msg.setText(
            "<h3>yt-dlp Is Not Installed</h3>"
            + reason
            + "<br><br>yt-msd drives yt-dlp as a separate program so it can be kept current "
            "without rebuilding yt-msd. Install it with:<br><br>"
            "<code>winget install --id yt-dlp.yt-dlp -e</code><br><br>"
            "If winget is unavailable, download <code>yt-dlp.exe</code> from "
            "<a href='https://github.com/yt-dlp/yt-dlp/releases/latest'>github.com/yt-dlp/yt-dlp</a> "
            "and put it in the yt-msd folder or anywhere on your PATH. Then restart yt-msd."
        )
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()

    def _show_ytdlp_update_dialog(self, installed, latest):
        """Show the yt-dlp update dialog on the GUI thread and act on the choice."""
        dlg = YtDlpUpdateDialog(self, installed, latest)
        choice = dlg.exec()
        if dlg.never_notify:
            self.disable_ytdlp_updates = True
            self.save_config()
        if choice == QDialog.Accepted:
            self.update_yt_dlp_now()

    def update_yt_dlp_now(self):
        """Update the yt-dlp installed on this system, in place, with winget.

        Used both by the yt-dlp update dialog and by the Settings dialog button. If
        winget does not manage this copy of yt-dlp (it was placed in the folder by
        hand, for example), it is installed properly instead, so the next update is
        an ordinary winget upgrade.
        """
        self.status_signal.emit("Updating yt-dlp with winget...", False, "#3B8ED0")

        def _bg():
            winget_args = ["--id", YTDLP_WINGET_ID, "-e",
                           "--accept-package-agreements", "--accept-source-agreements",
                           "--disable-interactivity"]
            rc, out, err = run_winget(["upgrade"] + winget_args)
            if rc is None:
                self.ytdlp_missing_signal.emit("winget is not available, so yt-msd cannot update yt-dlp for you.")
                return
            if rc != 0:
                rc, out, err = run_winget(["install"] + winget_args)
            exe = find_yt_dlp_executable(refresh=True)
            version = get_yt_dlp_version(exe) if exe else ""
            if version:
                self.ytdlp_version_signal.emit(version)
                self.status_signal.emit(f"yt-dlp is now at {version}.", False, "#1abd33")
                return
            lines = [line for line in (err or out or "").strip().splitlines() if line.strip()]
            detail = lines[-1] if lines else "winget could not complete the update."
            self.status_signal.emit(f"yt-dlp update failed: {detail}", False, "#E31E24")

        threading.Thread(target=_bg, daemon=True).start()

    def _apply_ytdlp_version(self, version):
        """Store a yt-dlp version found in a background thread, and show it in Settings."""
        if not version:
            return
        self.ytdlp_version = version
        settings_dialog = getattr(self, 'settings_dialog', None)
        if settings_dialog is not None and hasattr(settings_dialog, 'set_ytdlp_version'):
            settings_dialog.set_ytdlp_version(version)

    def refresh_yt_dlp_version(self):
        """Look for yt-dlp again on a worker thread (the Settings dialog asks for it)."""
        def _bg():
            exe = find_yt_dlp_executable(refresh=True)
            version = get_yt_dlp_version(exe) if exe else ""
            if version:
                self.ytdlp_version_signal.emit(version)
            else:
                self.ytdlp_missing_signal.emit("No yt-dlp was found on this system.")
        threading.Thread(target=_bg, daemon=True).start()

    def _init_vlc_background(self):
        """Initialize libVLC in a background thread to avoid blocking the UI during plugin scanning.
        The startup dependency check rides along here: it reuses this libvlc instance instead of
        creating a second one, and it never touches the UI thread."""
        vlc_error = ""
        if not _VLC_MODULE_AVAILABLE or vlc is None:
            self.vlc_instance = None
            self.vlc_player = None
            self._vlc_ready = True
            vlc_error = getattr(sys.modules[__name__], '_VLC_IMPORT_ERROR', 'python-vlc not available')
        else:
            try:
                instance = vlc.Instance('--quiet', '--no-video')
                player = instance.media_player_new() if instance else None
                # Switch to main-thread ownership safely
                self.vlc_instance = instance
                self.vlc_player = player
                if self.vlc_player:
                    self.vlc_player.audio_set_volume(self.volume_val)
                self._vlc_ready = True
                if player is None:
                    vlc_error = "libvlc.dll not found."
            except Exception as e:
                self.vlc_instance = None
                self.vlc_player = None
                self._vlc_ready = True  # Still mark ready so playback attempts don't hang
                vlc_error = str(e)

        missing = []
        if vlc_error:
            missing.append(
                "• <b>VLC Media Player (libvlc.dll)</b><br>"
                "Audio playback requires VLC Media Player (64-bit).<br>"
                "Please download and install 64-bit VLC from: <a href='https://www.videolan.org/vlc/'>https://www.videolan.org/vlc/</a>"
            )
        if not check_ffmpeg_available():
            missing.append(
                "• <b>FFmpeg (ffmpeg.exe)</b><br>"
                "Audio extraction, conversion, and loudness normalization require FFmpeg.<br>"
                "Please install FFmpeg and make sure <code>ffmpeg.exe</code> is in your system PATH or placed in the application folder."
            )
        if missing:
            self.missing_deps_signal.emit("<br><br>".join(missing))


    def load_config(self):
        default_dl = os.path.join(os.path.expanduser("~"), "Downloads")
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    c = json.load(f)
                    self.format_var = c.get('format', DEFAULT_DOWNLOAD_FORMAT)
                    # A format that is no longer offered must not survive in a config
                    # written by an older version. aac, flac and wav were all dropped
                    # because the tagger cannot write artist/title into any of them, and
                    # setCurrentText with a value the combo does not contain leaves the
                    # combo showing the default while format_var still holds the dead
                    # name - the next download would then go out with an --audio-format
                    # the app no longer supports. Fall back to the default instead.
                    if self.format_var not in DOWNLOAD_FORMATS:
                        self.format_var = DEFAULT_DOWNLOAD_FORMAT
                    self.bitrate_var = c.get('bitrate', '192')
                    self.recent_folders = c.get('folders', [default_dl])
                    self.download_path = self.recent_folders[0] if self.recent_folders else default_dl
                    self.accent_color_name = c.get('accent', 'System')
                    self.appearance_mode = c.get('mode', 'Dark')
                    self.volume_val = c.get('volume', 100)
                    self.local_folders = c.get('local_folders', [])
                    self.local_current_path = c.get('local_current_path', "")
                    self.show_local_metadata = c.get('show_local_metadata', False)
                    self.minimize_to_tray = c.get('minimize_to_tray', False)
                    self.recent_playlists = c.get('recent_playlists', [])
                    self.splitter_sizes = c.get('splitter_sizes', [300, 800, 300])
                    self.host_window_geometry = c.get('host_window_geometry', '')
                    self.use_custom_args = c.get('use_custom_args', False)
                    self.custom_args = c.get('custom_args', '')
                    self.appearance_mode = c.get('mode', 'Dark')
                    self.last_search = c.get('last_search', '')
                    self.save_place = c.get('save_place', False)
                    self.run_renamer = c.get('run_renamer', False)
                    self.renamer_path = c.get('renamer_path', '')
                    self.run_custom_script = c.get('run_custom_script', False)
                    self.custom_script_path = c.get('custom_script_path', '')
                    self.normalization_mode = c.get('normalization_mode', 'ask')
                    self.auto_rename = c.get('auto_rename', False)
                    self.silence_pad_dur = c.get('silence_pad_dur', 2.0)
                    self.silence_trim = bool(c.get('silence_trim', True))
                    self.use_custom_norm_cmd = c.get('use_custom_norm_cmd', False)
                    self.custom_norm_cmd = c.get('custom_norm_cmd', '')
                    self.download_threads = c.get('download_threads', 3)
                    self.normalization_threads = c.get('normalization_threads', max(1, os.cpu_count() // 2))
                    self.local_rescan_interval = c.get('local_rescan_interval', 60)
                    self.disable_update_checks = c.get('disable_update_checks', False)
                    self.disable_ytdlp_updates = c.get('disable_ytdlp_updates', False)
                    self.ytdlp_last_update_check = float(c.get('ytdlp_last_update_check', 0.0) or 0.0)
                    if hasattr(self, 'local_rescan_timer'):
                        self._update_local_rescan_timer()
                    if self.save_place:
                        self.session_data = c.get('session_data', {})
        except Exception: pass
        if not self.recent_folders:
            self.recent_folders = [default_dl]; self.download_path = default_dl

    def save_config(self):
        # Merge into the existing file instead of overwriting it, so keys owned by
        # other subsystems (hosted_chains / client_chains / sync_settings written by
        # SyncConfigManager.save) are preserved. The whole read-modify-write runs
        # under a shared lock so it never interleaves with SyncConfigManager.save().
        with _CONFIG_WRITE_LOCK:
            c = {}
            try:
                if os.path.exists(self.config_path):
                    with open(self.config_path, 'r') as f:
                        c = json.load(f)
            except Exception:
                c = {}
            c.update({
            'format': self.format_combo.currentText(),
            'bitrate': self.bitrate_combo.currentText(),
            'mode': self.appearance_mode,
            'accent': self.accent_color_name,
            'folders': self.recent_folders,
            'local_folders': self.local_folders,
            'local_current_path': self.local_current_path,
            'volume': self.volume_val,
            'show_local_metadata': getattr(self, 'show_local_metadata', False),
            'minimize_to_tray': self.minimize_to_tray,
            'use_custom_args': self.use_custom_args,
            'custom_args': self.custom_args,
            'recent_playlists': self.recent_playlists,
            'splitter_sizes': [self.main_splitter.sizes()[0]] + self.content_splitter.sizes() if hasattr(self, 'main_splitter') else self.splitter_sizes,
            'last_search': self.search_entry.text() if hasattr(self, 'search_entry') else self.last_search,
            'save_place': self.save_place,
            'run_renamer': self.run_renamer_cb.isChecked() if hasattr(self, 'run_renamer_cb') else self.run_renamer,
            'renamer_path': getattr(self, 'renamer_path', ''),
            'run_custom_script': getattr(self, 'run_custom_script', False),
            'custom_script_path': getattr(self, 'custom_script_path', ''),
            'normalization_mode': self.normalization_mode,
            'auto_rename': self.auto_rename,
            'silence_pad_dur': self.silence_pad_dur,
            'silence_trim': self.silence_trim,
            'use_custom_norm_cmd': self.use_custom_norm_cmd,
            'custom_norm_cmd': self.custom_norm_cmd,
            'download_threads': self.download_threads,
            'normalization_threads': self.normalization_threads,
            'local_rescan_interval': getattr(self, 'local_rescan_interval', 60),
            'disable_update_checks': getattr(self, 'disable_update_checks', False),
            'disable_ytdlp_updates': getattr(self, 'disable_ytdlp_updates', False),
            'ytdlp_last_update_check': getattr(self, 'ytdlp_last_update_check', 0.0),
            'session_data': {
                'search_results': self.search_results,
                'playback_index': self.playback_index,
                'current_video_id': self.current_video_id,
                'local_current_path': self.local_current_path,
                'local_playback_index': getattr(self, 'local_playback_index', -1)
            }
            })
            if getattr(self, 'launched_by_host', False):
                # Only a window opened from MusicBee keeps its own size; a normal
                # launch still opens at its fixed default. Leaving the key out here
                # means the read-modify-write above does not clear a saved value.
                try:
                    c['host_window_geometry'] = bytes(self.saveGeometry().toBase64()).decode('ascii')
                except Exception:
                    pass
            try:
                with open(self.config_path, 'w') as f: json.dump(c, f, indent=4)
            except: pass

    def _apply_host_window_geometry(self):
        # Opened from MusicBee: come back at the size and place it was closed at,
        # or at the compact default if this is the first time. restoreGeometry is
        # given exactly what saveGeometry wrote, base64-encoded for the JSON file.
        if not getattr(self, 'launched_by_host', False) or not self.host_window_geometry:
            return
        try:
            geometry = QByteArray.fromBase64(self.host_window_geometry.encode('ascii'))
            if geometry.isEmpty():
                return
            self.restoreGeometry(geometry)
            # A size remembered on a monitor that has since been unplugged would come
            # back off-screen and impossible to grab, so a window that lands outside
            # every screen falls back to the compact default, centred.
            desktop = QApplication.primaryScreen().virtualGeometry()
            if not self.geometry().intersects(desktop):
                available = QApplication.primaryScreen().availableGeometry()
                self.resize(1100, 700)
                centre = available.center()
                self.move(centre.x() - 550, centre.y() - 350)
        except Exception:
            pass

    def setup_tray(self):
        self.tray_popup = TrayProgressPopup()
        self.tray_click_timer = QTimer(self)
        self.tray_click_timer.setSingleShot(True)
        self.tray_click_timer.setInterval(250)
        self.tray_click_timer.timeout.connect(self._show_tray_progress_popup)

        self.tray_icon = QSystemTrayIcon(self)
        
        # The program icon, or the drawn circle if icon-256x256.ico is not available
        tray_qicon = app_icon()
        if tray_qicon is None:
            pixmap = QPixmap(64, 64)
            pixmap.fill(QColor("transparent"))
            painter = QPainter(pixmap)
            painter.setBrush(QColor(get_accent_color(self.accent_color_name)))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(8, 8, 48, 48)
            painter.end()
            tray_qicon = QIcon(pixmap)
        self.tray_icon.setIcon(tray_qicon)
        self.tray_icon.setToolTip("yt-msd")
        
        self.tray_menu = QMenu(self)
        self.tray_menu.aboutToShow.connect(self._build_tray_menu)
        self._build_tray_menu()
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()

    def _truncate_title(self, title: str, max_chars: int = 24) -> str:
        title = title.strip()
        if len(title) > max_chars:
            return title[:max_chars - 3].rstrip() + "..."
        return title

    def _build_tray_menu(self):
        self.tray_menu.clear()
        
        # Current song header (compact, truncated title)
        title = getattr(self, 'current_playing_title', '').strip()
        time_txt = self.time_label.text().strip() if hasattr(self, 'time_label') else ""
        if title:
            trunc_t = self._truncate_title(title, 24)
            if time_txt and time_txt != "0:00 / 0:00":
                header_text = f"{trunc_t} | {time_txt}"
            else:
                header_text = trunc_t
        else:
            header_text = "No Track Playing"
        
        self.tray_header_action = self.tray_menu.addAction(header_text)
        self.tray_header_action.setEnabled(False)
        self.tray_menu.addSeparator()

        # Play / Pause Action
        is_playing = getattr(self, 'is_playing', False)
        play_label = "Pause" if is_playing else "Play"
        play_action = self.tray_menu.addAction(play_label)
        play_action.triggered.connect(self.toggle_playback)

        # Prev / Next Track Actions
        prev_action = self.tray_menu.addAction("Previous Track")
        prev_action.triggered.connect(self.play_previous)
        next_action = self.tray_menu.addAction("Next Track")
        next_action.triggered.connect(self.play_next)

        # Stop After Current - the same control as the player-bar button: one entry,
        # three states, one click each (off -> once -> always -> off). The menu is
        # rebuilt every time it opens, so the label and the tick always match.
        stop_mode = getattr(self, 'stop_after_current', STOP_AFTER_OFF)
        stop_act = self.tray_menu.addAction(f"Stop After Current ({STOP_AFTER_LABELS[stop_mode]})")
        stop_act.setCheckable(True)
        stop_act.setChecked(stop_mode != STOP_AFTER_OFF)
        stop_act.setToolTip(STOP_AFTER_TOOLTIPS[stop_mode])
        stop_act.triggered.connect(lambda checked=False: self.cycle_stop_after_current())

        self.tray_menu.addSeparator()

        # Volume Controls Submenu
        vol_menu = self.tray_menu.addMenu(f"Volume ({self.volume_val}%)")
        
        vol_up = vol_menu.addAction("Volume Up (+10%)")
        vol_up.triggered.connect(lambda: self._set_tray_volume(self.volume_val + 10))
        
        vol_down = vol_menu.addAction("Volume Down (-10%)")
        vol_down.triggered.connect(lambda: self._set_tray_volume(self.volume_val - 10))
        
        mute_act = vol_menu.addAction("Mute (0%)")
        mute_act.triggered.connect(lambda: self._set_tray_volume(0))
        
        vol_menu.addSeparator()
        for p in [25, 50, 75, 100, 125, 150]:
            p_act = vol_menu.addAction(f"{p}%")
            if self.volume_val == p:
                p_act.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))
            p_act.triggered.connect(lambda checked=False, val=p: self._set_tray_volume(val))

        self.tray_menu.addSeparator()
        
        restore_action = self.tray_menu.addAction("Restore Window")
        restore_action.triggered.connect(self._restore_from_tray)
        
        exit_action = self.tray_menu.addAction("Exit")
        exit_action.triggered.connect(self.close)

    def _set_tray_volume(self, val: int):
        clamped = max(0, min(150, val))
        if hasattr(self, 'vol_slider'):
            self.vol_slider.setValue(clamped)
        else:
            self.on_volume_changed(clamped)

    def _restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _show_tray_progress_popup(self):
        title = getattr(self, 'current_playing_title', '').strip()
        time_txt = self.time_label.text().strip() if hasattr(self, 'time_label') else ""
        if hasattr(self, 'tray_popup') and self.tray_popup:
            self.tray_popup.show_track_info(title, time_txt)

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            if hasattr(self, 'tray_click_timer'):
                self.tray_click_timer.stop()
            if hasattr(self, 'tray_popup') and self.tray_popup and self.tray_popup.isVisible():
                self.tray_popup.hide()
            self._restore_from_tray()
        elif reason == QSystemTrayIcon.Trigger:
            if hasattr(self, 'tray_click_timer'):
                self.tray_click_timer.start()

    def changeEvent(self, event):
        if event.type() == event.Type.WindowStateChange:
            if self.isMinimized() and self.minimize_to_tray:
                self.hide()
        super().changeEvent(event)

    def request_attention(self):
        """Come forward because a second copy of yt-msd was started.

        The second copy exits itself (see ask_running_instance_to_show); this is
        the answer it asked for, and it is the only thing that happens.
        """
        try:
            if not self.isVisible():
                self.show()
            if self.isMinimized():
                self.showNormal()
            self.raise_()
            self.activateWindow()
            self._on_status_update("yt-msd is already running - this is that window.",
                                   False, "white")
        except Exception:
            pass

    def closeEvent(self, event):
        """Save settings, stop the background work, and end the Qt event loop.

        The process itself is exited by the entry block at the bottom of this
        file. Ending it here instead - os._exit() called from inside a Qt
        virtual override - tears the process down while shiboken is still
        unwinding the close event and while the sync, folder-watcher and
        subprocess threads are mid-call. That faults in shiboken6.abi3.dll, and
        the window and its Task Manager entry then stay where they are for the
        seconds Windows Error Reporting takes to write the crash dump.
        """
        self.shutdown_for_exit()
        event.accept()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def shutdown_for_exit(self):
        """One-shot shutdown, ordered so that nothing reaches this window again
        once it is on its way out. Safe to call twice."""
        if getattr(self, '_shutdown_done', False):
            return
        self._shutdown_done = True

        # A dialog raised on the way out would hold the process open until someone
        # dismissed it, so from here a failure is written to yt-msd-crash.log and not
        # shown. silence_crash_dialogs() stops only the dialogs.
        silence_crash_dialogs()

        # A background thread that is still working when this window goes away
        # reaches for a signal on an object Qt has already deleted. The hard
        # exit used to cut those threads off before they could say so; now the
        # interpreter outlives them long enough to print a traceback for each.
        # That one race is quieted below; nothing else is.
        previous_thread_excepthook = threading.excepthook

        def _thread_excepthook(args):
            # Only the one race Qt can lose here, and only as a RuntimeError:
            # shiboken's "Internal C++ object ... already deleted" and Qt's own
            # "Signal source has been deleted". Anything else a thread raises
            # still reports itself, as it did before.
            if args.exc_type is RuntimeError:
                text = str(args.exc_value)
                if 'has been deleted' in text or 'already deleted' in text:
                    return
            try:
                previous_thread_excepthook(args)
            except Exception:
                pass

        threading.excepthook = _thread_excepthook

        try:
            self.save_config()
        except Exception:
            pass

        try:
            if hasattr(self, 'sync_config_manager') and self.sync_config_manager:
                self.sync_config_manager.save()
        except Exception:
            pass

        # Timers first: the 16 ms player tick is the likeliest thing to still
        # reach the window after this point.
        for timer_name in ('player_timer', 'wifi_monitor_timer', 'drive_monitor_timer',
                           'local_rescan_timer', 'sync_timer', 'tray_click_timer'):
            timer = getattr(self, timer_name, None)
            if timer is not None:
                try:
                    timer.stop()
                except Exception:
                    pass

        # Sync workers: ask them to stop and give each a moment, so they are not
        # emitting signals into a window that is going away.
        for thread in list(getattr(self, 'sync_threads', {}).values()):
            try:
                thread.requestInterruption()
                thread.quit()
                thread.wait(1000)
            except Exception:
                pass

        # The LAN services: their threads call back into this window.
        for service_name in ('udp_beacon', 'sync_host_server'):
            service = getattr(self, service_name, None)
            if service is not None:
                try:
                    service.stop()
                except Exception:
                    pass

        # The folder watchers are stopped off the UI thread. Each observer is
        # bounded - remove_chain() joins it with a 0.3 s timeout - but a chain
        # whose handler is mid-callback still holds the stop up, and this window
        # should not wait for that. Measured here: 30+ seconds.
        try:
            if getattr(self, 'host_watcher', None) is not None:
                threading.Thread(target=self.host_watcher.stop_all, daemon=True).start()
        except Exception:
            pass

        try:
            if getattr(self, 'vlc_player', None) is not None:
                self.vlc_player.stop()
        except Exception:
            pass

        # This window installed itself as an application-wide event filter (the
        # Space key shortcut); nothing should reach it after this point.
        try:
            app = QApplication.instance()
            if app is not None:
                app.removeEventFilter(self)
        except Exception:
            pass

        try:
            if hasattr(self, 'tray_popup') and self.tray_popup:
                self.tray_popup.hide()
        except Exception:
            pass

        try:
            if hasattr(self, 'tray_icon') and self.tray_icon:
                self.tray_icon.hide()
        except Exception:
            pass

    def reset_to_defaults(self):
        if os.path.exists(self.config_path):
            try: os.remove(self.config_path)
            except: pass
        
        # Reset variables
        self.appearance_mode = "Dark"
        self.accent_color_name = "Blue"
        self.volume_val = 100
        self.save_place = False
        self.use_custom_args = False
        self.custom_args = ""
        self.last_search = ""
        self.minimize_to_tray = False
        self.run_renamer = False
        self.renamer_path = ""
        self.run_custom_script = False
        self.custom_script_path = ""
        self._last_downloaded_files = []
        self.normalization_mode = "ask"
        self.auto_rename = False
        self.silence_pad_dur = 2.0
        self.silence_trim = True
        self.use_custom_norm_cmd = False
        self.custom_norm_cmd = ""
        self.disable_update_checks = False
        self.disable_ytdlp_updates = False
        # These two opt-outs live on MainApp only, never in the settings list save_config() writes
        # from scratch, so without this they survived a "factory reset": save_config() writes
        # whatever the attributes hold and load_config() reads it back on the next launch, so the
        # user stayed opted out of app-update and yt-dlp-update prompts through a reset that claimed
        # to put everything back to default.
        global SILENCE_TRIM, SILENCE_PAD_DUR, CUSTOM_NORM_CMD
        SILENCE_TRIM = True
        SILENCE_PAD_DUR = self.silence_pad_dur
        CUSTOM_NORM_CMD = ""
        # The renamer half is a second copy of this program launched in a console, and it reads the
        # module globals above rather than the MainApp attributes. Resetting only the attributes left
        # every renamer this window launched running with the pre-reset trim / pad / override until
        # the app was restarted. load_config() and _apply_imported_config() push the globals for the
        # same reason; a reset has to do it too.
        self.download_threads = 3
        self.normalization_threads = max(1, os.cpu_count() // 2)
        self.local_rescan_interval = 60
        # Everything else gui_config.json stores. The file is deleted at the top of this method, but
        # save_config() at the bottom writes a fresh one out of whatever these attributes and widgets
        # hold, so anything not cleared here was straight back in the file the reset had just removed.
        # These are the parts a user would call "my recent data": the download folders and the
        # destination the top bar shows, the local folders and the folder open in the tree pane, the
        # playlist history, the format and bitrate the two top-bar combos are set to, the metadata tick
        # on the local pane, and the window geometry kept for MusicBee launches. session_data needs
        # nothing: save_config() rebuilds it from the live window on every save, and load_config() only
        # reads it back when "save place" is on, which this reset turns off. ytdlp_last_update_check is
        # cleared as well so the next launch behaves like a first run and looks for a newer yt-dlp
        # instead of trusting a timestamp left over from before the reset.
        default_dl = os.path.join(os.path.expanduser("~"), "Downloads")
        self.format_var = "mp3"
        self.bitrate_var = "192"
        self.recent_folders = [default_dl]
        self.download_path = default_dl
        self.local_folders = []
        self.local_current_path = ""
        self.recent_playlists = []
        self.show_local_metadata = False
        self.host_window_geometry = ""
        self.ytdlp_last_update_check = 0.0
        # ...and the widgets that display those values, because save_config() reads the format, the
        # bitrate and the download folder straight off them. Left where they were, they would put the
        # old values back into the new file on the next save. Signals are blocked so no handler runs
        # against a value that has already been changed underneath it.
        if hasattr(self, 'format_combo'):
            self.format_combo.blockSignals(True)
            self.format_combo.setCurrentText(self.format_var)
            self.format_combo.blockSignals(False)
        if hasattr(self, 'bitrate_combo'):
            self.bitrate_combo.blockSignals(True)
            self.bitrate_combo.setCurrentText(self.bitrate_var)
            self.bitrate_combo.blockSignals(False)
        if hasattr(self, 'path_combo'):
            self.path_combo.blockSignals(True)
            self.path_combo.clear()
            self.path_combo.addItems([str(folder) for folder in self.recent_folders])
            self.path_combo.setCurrentText(self.download_path)
            self.path_combo.blockSignals(False)
        if hasattr(self, 'local_meta_cb'):
            self.local_meta_cb.blockSignals(True)
            self.local_meta_cb.setChecked(False)
            self.local_meta_cb.blockSignals(False)
        if hasattr(self, 'local_path_combo'):
            # Rebuilds the address bar from the now-empty recent list without firing
            # load_local_folder, which would try to scan a folder this reset has just forgotten.
            self.set_local_explorer_address("")
        # local_current_path is empty, so the scan returns None and the pane is cleared instead of
        # continuing to list the files of a folder that is no longer set anywhere.
        self.refresh_local_list()
        if hasattr(self, 'local_rescan_timer'):
            self._update_local_rescan_timer()
        if hasattr(self, 'run_renamer_cb'):
            self.run_renamer_cb.blockSignals(True)
            self.run_renamer_cb.setChecked(False)
            self.run_renamer_cb.blockSignals(False)
        self.splitter_sizes = [300, 800, 300]
        
        # Apply changes
        self.apply_theme()
        # The old form of this read self.splitter, which MainApp never creates: the two real
        # splitters are main_splitter (local pane | everything else) and content_splitter
        # (results | queue), and save_config() stores three sizes by reading both of them. The
        # hasattr() was therefore always false, so the panel widths survived the reset and were
        # written straight back into the new file. Same split the startup code applies.
        if hasattr(self, 'main_splitter') and hasattr(self, 'content_splitter'):
            self.main_splitter.setSizes([self.splitter_sizes[0], self.splitter_sizes[1] + self.splitter_sizes[2]])
            self.content_splitter.setSizes([self.splitter_sizes[1], self.splitter_sizes[2]])
            # Clear what each splitter kept as the user's own arrangement, or the next double-click
            # on a handle restores the pre-reset widths instead of the default pair.
            for splitter in (self.main_splitter, self.content_splitter):
                splitter._last_custom_sizes = []
        if hasattr(self, 'vol_slider'):
            self.vol_slider.setValue(100)
        # The Settings dialog is cached on MainApp and reused, and it reads the MainApp attributes
        # only when it is first built. Resetting without dropping it left the very dialog the user
        # just clicked "reset" in showing the old tick marks and the old pad value - and the next
        # toggle would have written those stale values straight back. _apply_imported_config()
        # throws the cached dialog away for the same reason; do the same here. The caller closes
        # this dialog right after the reset, so closing it from here is safe.
        settings_dialog = getattr(self, 'settings_dialog', None)
        if settings_dialog is not None:
            try:
                settings_dialog.close()
            except Exception:
                pass
            self.settings_dialog = None
        # Sync chains and sync settings live in the same file this method deletes, but
        # SyncConfigManager holds live copies of all three - hosted_chains, client_chains and
        # settings - and the Sync dialog, the export dialog and the removable-drive path all read
        # that manager rather than the file. Clearing only the file therefore left every chain in
        # memory, and the next save() - on close, or from any chain operation - wrote them back into
        # a brand-new file, so no chain was ever actually removed. That write-back is worth keeping
        # for the case where the file is deleted by hand while the app is running: the manager still
        # re-creates it on exit. It must not survive an explicit reset, so the manager is emptied
        # here too.
        # A mirror sync works on the drive it is copying to for its whole run. Stopping the chains
        # first while one is mid-flight would leave it adding and deleting files against a chain
        # definition that no longer exists, so the threads are asked to stop before the chains go.
        for thread in list(getattr(self, 'sync_threads', {}).values()):
            try:
                thread.requestInterruption()
                thread.quit()
                thread.wait(1000)
            except Exception:
                pass
        sync_threads = getattr(self, 'sync_threads', None)
        if sync_threads is not None:
            sync_threads.clear()  # in place again: SyncManagerDialog aliases this same dict
        # The per-chain "Syncing... / [3/40] (7%)" lines the cards show are keyed by chain id.
        # Left behind they describe chains this reset has just removed, and a card for a new chain
        # with the same sync code would inherit the old progress text.
        progress_state = getattr(self, 'sync_progress_state', None)
        if progress_state is not None:
            progress_state.clear()
        sync_manager = getattr(self, 'sync_config_manager', None)
        if sync_manager is not None:
            # Emptied in place. The open Sync dialog keeps references to these very objects, so
            # rebinding them to new lists would leave that window showing chains that are gone.
            sync_manager.hosted_chains.clear()
            sync_manager.client_chains.clear()
            sync_manager.settings.clear()
            sync_manager.settings.update(DEFAULT_SYNC_SETTINGS)
        watcher = getattr(self, 'host_watcher', None)
        if watcher is not None:
            try:
                watcher.stop_all()
            except Exception:
                pass
        if hasattr(self, 'sync_timer'):
            # Re-arms the client auto-sync timer on the default interval. With no client chains the
            # callback returns immediately, but it should not keep running on an interval the user
            # picked before the reset.
            self._update_sync_timer()
        sync_dialog = getattr(self, 'sync_manager_dialog', None)
        if sync_dialog is not None:
            try:
                sync_dialog.refresh_cards(force=True)
            except Exception:
                pass
        self.save_config()
        self._on_status_update("Settings, recent data and sync chains reset to defaults.", False, "#3B8ED0")

    # ── EXPORT / IMPORT PACKAGES ──────────────────────────────────────────────
    def open_export_dialog(self):
        dialog = ExportDialog(self)
        dialog.exec()

    def start_export(self, options: dict):
        """Build the .zip package on a worker thread: copying music or reading a
        config off a slow drive must never block the window."""
        if self._export_import_busy:
            self._on_status_update("Please wait: an import or export is already running.", False, "#d9822b")
            return
        self._export_import_busy = True
        threading.Thread(target=self._export_worker, args=(dict(options),), daemon=True).start()
        self._on_status_update("Exporting package...", False, "#3B8ED0")

    def _export_worker(self, options: dict):
        zip_path = str(options.get('zip_path') or "")
        include_config = bool(options.get('include_config'))
        include_chains = bool(options.get('include_chains'))
        include_music = bool(options.get('include_music'))
        file_count = 0
        try:
            if not zip_path:
                raise ValueError("no destination file was chosen")
            parent_dir = os.path.dirname(os.path.abspath(zip_path))
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)

            # Read the config under the shared lock: MainApp.save_config and
            # SyncConfigManager.save both write this file.
            with _CONFIG_WRITE_LOCK:
                current_config = {}
                if os.path.exists(self.config_path):
                    with open(self.config_path, 'r', encoding='utf-8') as config_file:
                        current_config = json.load(config_file)

            sync_payload: dict = {}
            if include_chains:
                manager = self.sync_config_manager
                sync_payload = {
                    'sync_settings': dict(manager.settings),
                    'hosted_chains': [dict(chain) for chain in manager.hosted_chains],
                    'client_chains': [dict(chain) for chain in manager.client_chains],
                }

            exported_config = build_exported_config(current_config, include_config, include_chains, sync_payload)
            music_entries: List[dict] = []

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(EXPORT_CONFIG_ENTRY, json.dumps(exported_config, indent=4))
                file_count += 1
                if include_chains:
                    archive.writestr(EXPORT_SYNC_ENTRY, json.dumps(sync_payload, indent=4))
                    file_count += 1
                if include_music:
                    used_names: set = set()
                    for entry in options.get('music_folders') or []:
                        folder = str((entry or {}).get('path') or "").strip()
                        if not folder or not os.path.isdir(folder):
                            continue
                        archive_path, folder_name = unique_music_archive_name(folder, used_names)
                        self.status_signal.emit(f"Exporting music: {folder_name}...", False, "#3B8ED0")
                        with_subfolders = bool((entry or {}).get('subfolders'))
                        written = zip_folder_into(archive, folder, archive_path, with_subfolders)
                        music_entries.append({
                            'name': folder_name,
                            'archive_path': archive_path,
                            'source_path': os.path.abspath(folder),
                            'subfolders': with_subfolders,
                            'files': written,
                        })
                        file_count += written
                archive.writestr(EXPORT_MANIFEST_NAME, build_export_manifest_text(
                    include_config, include_chains, include_music, music_entries))
        except Exception as exc:
            self._export_import_busy = False
            self.status_signal.emit(f"Export failed: {exc}", False, "#d9822b")
            return

        self._export_import_busy = False
        self.status_signal.emit(f"Exported {file_count} files to {zip_path}", False, "#1abd33")

    def open_import_dialog(self):
        """Pick a .zip export package; everything else follows export.yaml."""
        if self._export_import_busy:
            self._on_status_update("Please wait: an import or export is already running.", False, "#d9822b")
            return
        start_dir = getattr(self, 'download_path', '') or os.path.expanduser("~")
        zip_path, _ = QFileDialog.getOpenFileName(self, "Import yt-msd Package", start_dir,
                                                  "yt-msd Package (*.zip);;All Files (*)")
        if not zip_path:
            return
        self._export_import_busy = True
        self._on_status_update("Importing package...", False, "#3B8ED0")
        threading.Thread(target=self._import_worker, args=(zip_path,), daemon=True).start()

    def _import_worker(self, zip_path: str):
        """Read the manifest and unpack any music off the GUI thread."""
        try:
            package = read_import_package(zip_path)
        except Exception as exc:
            self.import_failed_signal.emit(f"Could not read {os.path.basename(zip_path)}: {exc}")
            return

        manifest = package.get('manifest') if isinstance(package.get('manifest'), dict) else {}
        includes = manifest.get('includes') if isinstance(manifest.get('includes'), dict) else {}
        music_results: List[dict] = []
        try:
            if includes.get('music'):
                with zipfile.ZipFile(zip_path, 'r') as archive:
                    music_results = extract_package_music(
                        archive, manifest,
                        status_cb=lambda text: self.status_signal.emit(text, False, "#3B8ED0"))
        except Exception as exc:
            self.import_failed_signal.emit(f"Import failed while unpacking: {exc}")
            return

        self.import_finished_signal.emit({
            'config': package.get('config') if includes.get('config') else None,
            'sync': package.get('sync') if includes.get('sync_chains') else None,
            'music': music_results,
        })

    def _on_import_failed(self, message: str):
        self._export_import_busy = False
        self._on_status_update(message, False, "#d9822b")

    def _apply_import_results(self, plan: dict):
        """Restore an imported package on the GUI thread: settings, chains, music."""
        plan = plan if isinstance(plan, dict) else {}
        summary: List[str] = []

        config_payload = plan.get('config')
        needs_local_rescan = False
        if isinstance(config_payload, dict) and config_payload:
            needs_local_rescan = bool(self._apply_imported_config(config_payload))
            summary.append("settings")

        sync_payload = plan.get('sync')
        if isinstance(sync_payload, dict) and sync_payload:
            hosted_count, client_count = self._apply_imported_sync_chains(sync_payload)
            summary.append(f"{hosted_count} hosted / {client_count} client chains")

        music_results = [result for result in (plan.get('music') or []) if isinstance(result, dict)]
        if music_results:
            restored_files = sum(int(result.get('files') or 0) for result in music_results)
            summary.append(f"{restored_files} music files")
            for result in music_results:
                if result.get('error'):
                    self._on_status_update(f"Could not fully restore {result.get('name')}: {result['error']}",
                                           False, "#d9822b")

        # Refresh the local list last: files restored by this same import have to
        # be on disk before the folder is scanned. The scan itself runs on a
        # worker thread, not here.
        if needs_local_rescan:
            self.local_list_refresh_signal.emit()

        self._export_import_busy = False
        if summary:
            self._on_status_update("Imported package: " + ", ".join(summary), False, "#1abd33")
        else:
            self._on_status_update("Imported package: nothing in it to restore.", False, "#d9822b")

    def _apply_imported_sync_chains(self, payload: dict) -> Tuple[int, int]:
        """Add imported chains, skipping any chain this machine already has."""
        manager = self.sync_config_manager
        settings = payload.get('sync_settings')
        if isinstance(settings, dict) and settings:
            merged = dict(manager.settings)
            merged.update(settings)
            manager.settings = merged

        hosted_ids = {str(chain.get('id')) for chain in manager.hosted_chains}
        hosted_codes = {str(chain.get('sync_code')) for chain in manager.hosted_chains}
        client_ids = {str(chain.get('id')) for chain in manager.client_chains}
        client_codes = {str(chain.get('sync_code')) for chain in manager.client_chains}
        added_hosted = 0
        added_clients = 0

        for chain in payload.get('hosted_chains') or []:
            if not isinstance(chain, dict):
                continue
            if str(chain.get('id')) in hosted_ids or str(chain.get('sync_code')) in hosted_codes:
                continue
            manager.hosted_chains.append(dict(chain))
            hosted_ids.add(str(chain.get('id')))
            hosted_codes.add(str(chain.get('sync_code')))
            added_hosted += 1

        for chain in payload.get('client_chains') or []:
            if not isinstance(chain, dict):
                continue
            if str(chain.get('id')) in client_ids or str(chain.get('sync_code')) in client_codes:
                continue
            manager.client_chains.append(dict(chain))
            client_ids.add(str(chain.get('id')))
            client_codes.add(str(chain.get('sync_code')))
            added_clients += 1

        manager.save()
        self._update_sync_timer()
        self.refresh_sync_watchers()
        dialog = getattr(self, 'sync_manager_dialog', None)
        if dialog is not None and dialog.isVisible():
            dialog.refresh_cards(force=True)
        return added_hosted, added_clients

    def _apply_imported_config(self, cfg: dict):
        """Apply an imported config payload to the running app, then save it.
        Anything the package does not mention is left exactly as it was.
        Returns True when the package changed the local folder, so the caller
        knows the local file list has to be rescanned."""
        if 'format' in cfg and hasattr(self, 'format_combo'):
            _imported_format = str(cfg.get('format')).strip().lower()
            # Same rule as load_config(): an imported package that still names a
            # format this build no longer offers would otherwise put the combo into a
            # no-current-item state, and the next download would go out with a blank
            # --audio-format. Unknown formats are ignored and the current pick stands.
            if _imported_format in DOWNLOAD_FORMATS:
                self.format_combo.setCurrentText(_imported_format)
        if 'bitrate' in cfg and hasattr(self, 'bitrate_combo'):
            self.bitrate_combo.setCurrentText(str(cfg.get('bitrate')))
        if 'mode' in cfg:
            self.appearance_mode = str(cfg.get('mode'))
        if 'accent' in cfg:
            self.accent_color_name = str(cfg.get('accent'))
        if 'volume' in cfg:
            try:
                self.volume_val = int(cfg.get('volume'))
            except (TypeError, ValueError):
                self.volume_val = 100
            if hasattr(self, 'vol_slider'):
                self.vol_slider.setValue(self.volume_val)
        if isinstance(cfg.get('folders'), list) and cfg.get('folders'):
            self.recent_folders = [str(folder) for folder in cfg['folders']]
            self.download_path = self.recent_folders[0]
        touched_local = isinstance(cfg.get('local_folders'), list) or 'local_current_path' in cfg
        if isinstance(cfg.get('local_folders'), list):
            self.local_folders = [str(folder) for folder in cfg['local_folders']]
        if 'local_current_path' in cfg:
            self.local_current_path = str(cfg.get('local_current_path') or "")
        if touched_local:
            # The address bar is filled once at startup, so an imported folder
            # list has to be pushed into it here or it stays stale until relaunch.
            self.set_local_explorer_address(self.local_current_path,
                                           add_to_recent=os.path.isdir(self.local_current_path or ""))
        if 'show_local_metadata' in cfg:
            self.show_local_metadata = bool(cfg.get('show_local_metadata'))
        if 'minimize_to_tray' in cfg:
            self.minimize_to_tray = bool(cfg.get('minimize_to_tray'))
        if 'use_custom_args' in cfg:
            self.use_custom_args = bool(cfg.get('use_custom_args'))
        if 'custom_args' in cfg:
            self.custom_args = str(cfg.get('custom_args') or "")
        if isinstance(cfg.get('recent_playlists'), list):
            self.recent_playlists = [entry for entry in cfg['recent_playlists']
                                     if isinstance(entry, dict)][:5]
        if 'last_search' in cfg and hasattr(self, 'search_entry'):
            self.last_search = str(cfg.get('last_search') or "")
            self.search_entry.setText(self.last_search)
        if isinstance(cfg.get('splitter_sizes'), list) and len(cfg.get('splitter_sizes')) == 3:
            try:
                sizes = [int(value) for value in cfg['splitter_sizes']]
            except (TypeError, ValueError):
                sizes = [300, 800, 300]
            self.splitter_sizes = sizes
            if hasattr(self, 'main_splitter'):
                self.main_splitter.setSizes([sizes[0], sizes[1] + sizes[2]])
            if hasattr(self, 'content_splitter'):
                self.content_splitter.setSizes([sizes[1], sizes[2]])

        if 'save_place' in cfg:
            self.save_place = bool(cfg.get('save_place'))
        if isinstance(cfg.get('session_data'), dict):
            self.session_data = cfg['session_data']
        if 'run_renamer' in cfg:
            self.run_renamer = bool(cfg.get('run_renamer'))
            if hasattr(self, 'run_renamer_cb'):
                self.run_renamer_cb.blockSignals(True)
                self.run_renamer_cb.setChecked(self.run_renamer)
                self.run_renamer_cb.blockSignals(False)
        if 'renamer_path' in cfg:
            self.renamer_path = str(cfg.get('renamer_path') or "")
        if 'run_custom_script' in cfg:
            self.run_custom_script = bool(cfg.get('run_custom_script'))
        if 'custom_script_path' in cfg:
            self.custom_script_path = str(cfg.get('custom_script_path') or "")
        if cfg.get('normalization_mode') in ("on", "off", "ask"):
            self.normalization_mode = str(cfg.get('normalization_mode'))
        if 'auto_rename' in cfg:
            self.auto_rename = bool(cfg.get('auto_rename'))
        if 'silence_pad_dur' in cfg:
            try:
                self.silence_pad_dur = float(cfg.get('silence_pad_dur'))
            except (TypeError, ValueError):
                self.silence_pad_dur = 2.0
        if 'silence_trim' in cfg:
            self.silence_trim = bool(cfg.get('silence_trim'))
        if 'use_custom_norm_cmd' in cfg:
            self.use_custom_norm_cmd = bool(cfg.get('use_custom_norm_cmd'))
        if 'custom_norm_cmd' in cfg:
            self.custom_norm_cmd = str(cfg.get('custom_norm_cmd') or "")
        global SILENCE_TRIM, SILENCE_PAD_DUR, CUSTOM_NORM_CMD
        SILENCE_TRIM = bool(self.silence_trim)
        SILENCE_PAD_DUR = float(self.silence_pad_dur)
        CUSTOM_NORM_CMD = self.custom_norm_cmd.strip() if (self.use_custom_norm_cmd and self.custom_norm_cmd.strip()) else ""
        if 'download_threads' in cfg:
            try:
                self.download_threads = max(1, int(cfg.get('download_threads')))
            except (TypeError, ValueError):
                self.download_threads = 3
        if 'normalization_threads' in cfg:
            try:
                self.normalization_threads = max(1, int(cfg.get('normalization_threads')))
            except (TypeError, ValueError):
                self.normalization_threads = max(1, os.cpu_count() // 2)
        if 'local_rescan_interval' in cfg:
            try:
                self.local_rescan_interval = int(cfg.get('local_rescan_interval'))
            except (TypeError, ValueError):
                self.local_rescan_interval = 60
            self._update_local_rescan_timer()
        if 'disable_update_checks' in cfg:
            self.disable_update_checks = bool(cfg.get('disable_update_checks'))
        if 'disable_ytdlp_updates' in cfg:
            self.disable_ytdlp_updates = bool(cfg.get('disable_ytdlp_updates'))

        self.apply_theme()
        # The settings dialog reads these values when it is built, so the cached
        # one is dropped: reopening it shows the imported settings.
        settings_dialog = getattr(self, 'settings_dialog', None)
        if settings_dialog is not None:
            try:
                settings_dialog.close()
            except Exception:
                pass
            self.settings_dialog = None
        self.save_config()
        # The caller refreshes the local list once everything the package carries
        # has been restored, so the scan sees the imported files too.
        return touched_local and os.path.isdir(self.local_current_path or "")

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main Layout (Horizontal)
        self.main_layout = QHBoxLayout(central_widget)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(0)
        
        # Splitter Logic
        class ResetHandle(QSplitterHandle):
            _last_click = 0
            def mousePressEvent(self, e):
                import time
                now = time.time()
                if now - ResetHandle._last_click < 0.35:
                    sp = self.splitter()
                    if sp.orientation() == Qt.Horizontal:
                        current_sizes = sp.sizes()
                        is_main = (sp == getattr(self.window(), 'main_splitter', None))
                        target_idx = 0 if is_main else 1
                        
                        if current_sizes[target_idx] > 0:
                            sp._last_custom_sizes = current_sizes
                            if is_main:
                                sp.setSizes([0, sum(current_sizes)])
                            else:
                                sp.setSizes([sum(current_sizes), 0])
                        else:
                            if hasattr(sp, '_last_custom_sizes') and sp._last_custom_sizes and sp._last_custom_sizes[target_idx] > 0:
                                sp.setSizes(sp._last_custom_sizes)
                            else:
                                if is_main:
                                    sp.setSizes([300, max(0, sum(current_sizes)-300)])
                                else:
                                    sp.setSizes([max(0, sum(current_sizes)-300), 300])
                    e.accept(); return
                ResetHandle._last_click = now
                super().mousePressEvent(e)

        class ResetSplitter(QSplitter):
            def createHandle(self):
                return ResetHandle(self.orientation(), self)

        # Main Splitter (Horizontal: Local | Content)
        self.main_splitter = ResetSplitter(Qt.Horizontal)
        self.main_layout.addWidget(self.main_splitter, 1)
        
        self._setup_local_pane()
        
        # Right Content Area
        self.right_content = QWidget()
        self.right_layout = QVBoxLayout(self.right_content)
        self.right_layout.setContentsMargins(5, 0, 0, 0)
        self.right_layout.setSpacing(5)
        self.main_splitter.addWidget(self.right_content)
        
        # Content Splitter (Horizontal: Results | Queue)
        self.content_splitter = ResetSplitter(Qt.Horizontal)
        self.right_layout.addWidget(self.content_splitter, 1)
        
        self._setup_results_pane()
        self._setup_queue_pane()
        
        # Initial Sizes
        sz = getattr(self, 'splitter_sizes', [300, 800, 300])
        if len(sz) == 3:
            self.main_splitter.setSizes([sz[0], sz[1] + sz[2]])
            self.content_splitter.setSizes([sz[1], sz[2]])
        else:
            self.main_splitter.setSizes([300, 1340])
            self.content_splitter.setSizes([1000, 300])

        # Controls UI
        controls_frame = QFrame()
        c_layout = QVBoxLayout(controls_frame)
        c_layout.setContentsMargins(5, 5, 5, 5)
        c_layout.setSpacing(5)
        self.right_layout.addWidget(controls_frame)
        
        search_r = QHBoxLayout()
        self.toggle_pane_btn = QPushButton("\uE8A0")
        self.toggle_pane_btn.setObjectName("topIconBtn")
        self.toggle_pane_btn.setFixedSize(36, 30)
        self.toggle_pane_btn.setToolTip("Toggle File Browser")
        self.toggle_pane_btn.clicked.connect(self.toggle_local_pane)
        search_r.addWidget(self.toggle_pane_btn)
        
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("Search YouTube or Paste a Video Link")
        self.search_entry.returnPressed.connect(self.perform_search)
        self.search_btn = QPushButton("Search")
        self.search_btn.setToolTip("Search YouTube for songs or playlists")
        self.search_btn.clicked.connect(self.perform_search)
        self.playlist_btn = QPushButton("\uE142")
        self.playlist_btn.setObjectName("topIconBtn")
        self.playlist_btn.setFixedSize(36, 30)
        self.playlist_btn.setToolTip("Recent Playlists")
        self.playlist_btn.clicked.connect(self.open_playlist_dialog)
        
        search_r.addWidget(self.search_entry, 1)
        search_r.addWidget(self.search_btn)
        search_r.addWidget(self.playlist_btn)
        settings_btn = QPushButton("\uE713")
        settings_btn.setObjectName("topIconBtn")
        settings_btn.setFixedSize(36, 30)
        settings_btn.setToolTip("Settings")
        settings_btn.clicked.connect(self.open_settings_dialog)
        search_r.addWidget(settings_btn)
        c_layout.addLayout(search_r)
        
        set_r = QHBoxLayout()
        set_r.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(list(DOWNLOAD_FORMATS))
        self.format_combo.setCurrentText(self.format_var)
        self.format_combo.currentTextChanged.connect(self.save_config)
        set_r.addWidget(self.format_combo)
        
        set_r.addWidget(QLabel("Bitrate:"))
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.addItems(["128", "192", "256", "320"])
        self.bitrate_combo.setCurrentText(self.bitrate_var)
        self.bitrate_combo.currentTextChanged.connect(self.save_config)
        set_r.addWidget(self.bitrate_combo)
        
        set_r.addWidget(QLabel("Save to:"))
        
        self.open_folder_btn = QPushButton("\uE8DA")
        self.open_folder_btn.setObjectName("topIconBtn")
        self.open_folder_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px; padding: 0px;")
        self.open_folder_btn.setFixedSize(36, 30)
        self.open_folder_btn.setToolTip("Open Folder in File Explorer")
        self.open_folder_btn.clicked.connect(self.open_current_download_folder)
        set_r.addWidget(self.open_folder_btn)
        
        self.path_combo = QComboBox()
        self.path_combo.addItems(self.recent_folders)
        if self.download_path not in self.recent_folders:
            self.path_combo.addItem(self.download_path)
        self.path_combo.setCurrentText(self.download_path)
        self.path_combo.currentTextChanged.connect(self.on_path_changed)
        set_r.addWidget(self.path_combo, 1)
        
        self.browse_btn = QPushButton("\uE8B7")
        self.browse_btn.setObjectName("topIconBtn")
        self.browse_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px; padding: 0px;")
        self.browse_btn.setFixedSize(36, 30)
        self.browse_btn.setToolTip("Browse destination folder")
        self.browse_btn.clicked.connect(self.browse_folder)
        set_r.addWidget(self.browse_btn)
        set_r.addSpacing(6)
        c_layout.addLayout(set_r)
        
        option_r = QHBoxLayout()
        self.run_renamer_cb = QCheckBox("Run MP3 Renamer after download")
        self.run_renamer_cb.setChecked(self.run_renamer)
        self.run_renamer_cb.toggled.connect(self.on_run_renamer_toggled)
        option_r.addWidget(self.run_renamer_cb)
        option_r.addStretch()
        c_layout.addLayout(option_r)
        
        status_bar = QHBoxLayout()
        self.playing_label = QLabel("")
        self.playing_label.setTextFormat(Qt.PlainText)
        self.playing_label.setStyleSheet("font-size: 11px; margin-top: -2px;")
        self.status_label = QLabel("Ready")
        self.status_label.setTextFormat(Qt.PlainText)
        self.status_label.setStyleSheet("font-size: 11px; margin-top: -2px;")
        self.dl_progress_label = QLabel("")
        self.dl_progress_label.setTextFormat(Qt.PlainText)
        self.dl_progress_label.setStyleSheet("font-size: 11px; margin-top: -2px; color: #888;")
        self.dl_progress_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        status_bar.addWidget(self.playing_label)
        status_bar.addWidget(self.status_label)
        status_bar.addStretch()
        status_bar.addWidget(self.dl_progress_label)
        c_layout.addLayout(status_bar)

        # Bottom Player
        player_frame = QFrame()
        p_layout = QVBoxLayout(player_frame)
        p_layout.setContentsMargins(8, 4, 8, 4)
        p_layout.setSpacing(0)
        self.right_layout.addWidget(player_frame)
        
        class VolLabel(QLabel):
            def mouseDoubleClickEvent(self, e):
                win = self.window()
                if hasattr(win, 'vol_slider'):
                    win.vol_slider.setValue(100)
                e.accept()

        c = QHBoxLayout()
        c.addWidget(VolLabel("Volume"))
        
        class VolSlider(QSlider):
            def mouseDoubleClickEvent(self, e):
                self.setValue(100)
                e.accept()
                
        self.vol_slider = VolSlider(Qt.Horizontal)
        self.vol_slider.setObjectName("volSlider")
        _init_state = "red" if self.volume_val > 115 else ("orange" if self.volume_val > 100 else "normal")
        self.vol_slider.setProperty("volume_state", _init_state)
        self.vol_slider.setRange(0, 150); self.vol_slider.setValue(self.volume_val)
        self.vol_slider.setFixedWidth(100)
        self.vol_slider.valueChanged.connect(self.on_volume_changed)
        c.addWidget(self.vol_slider)
        
        self.vol_pct = VolLabel(f"{self.volume_val}%")
        self.vol_pct.setFixedWidth(50)
        if self.volume_val > 115:
            self.vol_pct.setStyleSheet("color: #E31E24; font-weight: bold;")
        elif self.volume_val > 100:
            self.vol_pct.setStyleSheet("color: #FF8C00; font-weight: bold;")
        c.addWidget(self.vol_pct)
        
        c.addStretch(1)
        _btn_ss = "background: transparent; color: white; font-family: 'Segoe MDL2 Assets'; font-size: 14px; border-radius: 4px; padding: 2px 4px;"
        _btn_ss_hover = "background: transparent; color: white; font-family: 'Segoe MDL2 Assets'; font-size: 14px; border-radius: 4px; padding: 2px 4px;" + " /* hover set via stylesheet */"
        
        self.prev_btn = QPushButton("\uE892")
        self.prev_btn.setObjectName("playerBtn")
        self.prev_btn.setFixedSize(36, 36)
        self.prev_btn.setToolTip("Previous track")
        self.prev_btn.clicked.connect(self.play_previous)
        c.addWidget(self.prev_btn)
        
        self.play_btn = QPushButton("\uE768")
        self.play_btn.setObjectName("playerPlayBtn")
        self.play_btn.setFixedSize(44, 44)
        self.play_btn.setToolTip("Play / Pause")
        self.play_btn.clicked.connect(self.toggle_playback)
        c.addWidget(self.play_btn)
        
        self.next_btn = QPushButton("\uE893")
        self.next_btn.setObjectName("playerBtn")
        self.next_btn.setFixedSize(36, 36)
        self.next_btn.setToolTip("Next track")
        self.next_btn.clicked.connect(self.play_next)
        c.addWidget(self.next_btn)

        self.shuffle_btn = QPushButton("\uE8B1")
        self.shuffle_btn.setObjectName("playerBtn")
        self.shuffle_btn.setFixedSize(36, 36)
        self.shuffle_btn.setToolTip("Shuffle Playback (Toggle)")
        self.shuffle_btn.clicked.connect(self.toggle_shuffle)
        c.addWidget(self.shuffle_btn)

        # Stop After Current: one button, three states (off -> once -> always).
        # U+25A0 BLACK SQUARE rather than a Segoe MDL2 Assets private-use codepoint:
        # the previous caption (U+E76A "Replay") is not in this machine's MDL2 font, so
        # Qt fell back to the .notdef glyph and the button drew an empty box. U+25A0 is a
        # normal text glyph that Segoe MDL2 Assets (the family the #stopAfterBtn rule
        # asks for), Segoe UI and the fallback fonts all have, so it paints as a filled
        # square whichever font the rule resolves to.
        self.stop_after_btn = QPushButton("\u25A0")
        self.stop_after_btn.setObjectName("stopAfterBtn")
        self.stop_after_btn.setFixedSize(36, 36)
        self.stop_after_btn.setProperty("stop_after_state", STOP_AFTER_STATE_NAMES[self.stop_after_current])
        self.stop_after_btn.setToolTip(STOP_AFTER_TOOLTIPS[self.stop_after_current])
        self.stop_after_btn.clicked.connect(self.cycle_stop_after_current)
        c.addWidget(self.stop_after_btn)
        c.addStretch(1)
        
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setStyleSheet("font-size: 11px;")
        c.addWidget(self.time_label)
        p_layout.addLayout(c)
        
        self.progress_slider = ClickableSlider(Qt.Horizontal)
        self.progress_slider.setFixedHeight(20)
        self.progress_slider.setRange(0, 10000)
        self.progress_slider.sliderMoved.connect(self.on_seek)
        p_layout.addWidget(self.progress_slider)

        # Restore last search
        if getattr(self, 'last_search', ''):
            self.search_entry.setText(self.last_search)
        
        # Restore session
        if self.save_place and hasattr(self, 'session_data'):
            sd = self.session_data
            if sd.get('search_results'):
                self._on_search_results(sd['search_results'], False, reset_view=False)
                self.playback_index = sd.get('playback_index', -1)
            
            # Restore playback state if item exists
            v_id = sd.get('current_video_id')
            if v_id and v_id != "local":
                # Find the video object in results if possible
                results = sd.get('search_results', [])
                idx = sd.get('playback_index', -1)
                if 0 <= idx < len(results):
                    video = results[idx]
                    self.play_result(video, paused_at_start=True)

        # Re-search in background to update cache
        if getattr(self, 'last_search', ''):
            is_pl = False
            for p in self.recent_playlists:
                if isinstance(p, dict) and p.get("url") == self.last_search: is_pl = True; break
                elif p == self.last_search: is_pl = True; break
            self.perform_search(is_playlist=is_pl)


    def toggle_local_pane(self):
        sizes = self.main_splitter.sizes()
        if sizes[0] > 0:
            self.main_splitter._last_custom_sizes = sizes
            self.main_splitter.setSizes([0, sizes[0] + sizes[1]])
        else:
            if hasattr(self.main_splitter, '_last_custom_sizes') and self.main_splitter._last_custom_sizes and self.main_splitter._last_custom_sizes[0] > 0:
                self.main_splitter.setSizes(self.main_splitter._last_custom_sizes)
            else:
                self.main_splitter.setSizes([300, max(0, sum(sizes) - 300)])

    def _setup_local_pane(self):
        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(0,0,0,0)
        l.addWidget(QLabel("Local Folder"))
        
        h = QHBoxLayout()
        
        self.open_local_folder_btn = QPushButton("\uE8DA")
        self.open_local_folder_btn.setObjectName("topIconBtn")
        self.open_local_folder_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px; padding: 0px;")
        self.open_local_folder_btn.setFixedSize(36, 30)
        self.open_local_folder_btn.setToolTip("Open Local Folder in File Explorer")
        self.open_local_folder_btn.clicked.connect(self.open_current_local_folder)
        h.addWidget(self.open_local_folder_btn)
        
        self.local_path_combo = QComboBox()
        self.local_path_combo.addItems(self.local_folders)
        self.local_path_combo.currentTextChanged.connect(self.load_local_folder)
        h.addWidget(self.local_path_combo, 1)
        local_browse_btn = QPushButton("\uE8B7")
        local_browse_btn.setObjectName("topIconBtn")
        local_browse_btn.setToolTip("Browse for a local folder")
        local_browse_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px; padding: 0px;")
        local_browse_btn.setFixedSize(36, 30)
        local_browse_btn.clicked.connect(lambda: self.load_local_folder(QFileDialog.getExistingDirectory(self)))
        h.addWidget(local_browse_btn)
        h.addSpacing(6)
        l.addLayout(h)
        
        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(8)
        self.local_meta_cb = QCheckBox("Show Metadata")
        self.local_meta_cb.setChecked(getattr(self, 'show_local_metadata', False))
        self.local_meta_cb.stateChanged.connect(self.toggle_local_metadata)
        meta_row.addWidget(self.local_meta_cb)
        meta_row.addStretch()
        self.local_sel_label = QLabel("")
        self.local_sel_label.setStyleSheet("border: none; background: transparent; font-size: 11px; font-weight: bold;")
        meta_row.addWidget(self.local_sel_label)
        l.addLayout(meta_row)
        
        # Rename / copy / delete actions live in the right-click menu on a row.
        
        self.local_list = QScrollArea()
        self.local_list.setWidgetResizable(True)
        self.local_content = QWidget()
        self.local_content.setObjectName("scrollContent")
        self.local_vbox = QVBoxLayout(self.local_content)
        self.local_vbox.setAlignment(Qt.AlignTop)
        self.local_list.setWidget(self.local_content)
        l.addWidget(self.local_list, 1)
        self.main_splitter.addWidget(w)

    def _setup_results_pane(self):
        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(0,0,0,0)
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 16, 0)
        h.addWidget(QLabel("Search Results"))
        h.addStretch()
        
        self.queue_all_cb = QCheckBox("Queue All")
        self.queue_all_cb.setChecked(False)
        self.queue_all_cb.stateChanged.connect(self.toggle_queue_all)
        h.addWidget(self.queue_all_cb)
        
        self.header_divider = QLabel("  |  ")
        self.header_divider.setStyleSheet("color: #888888; font-weight: bold;")
        h.addWidget(self.header_divider)
        
        self.open_yt_btn = QPushButton("")
        self.open_yt_btn.setObjectName("topIconBtn")
        self.open_yt_btn.setToolTip("Open search / playlist on YouTube")
        self.open_yt_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 14px; padding: 2px 6px;")
        self.open_yt_btn.setFixedSize(30, 26)
        self.open_yt_btn.clicked.connect(self.open_search_on_youtube)
        h.addWidget(self.open_yt_btn)
        l.addLayout(h)
        
        self.results_area = QScrollArea()
        self.results_area.setWidgetResizable(True)
        self.results_content = QWidget()
        self.results_content.setObjectName("scrollContent")
        self.results_vbox = QVBoxLayout(self.results_content)
        self.results_vbox.setAlignment(Qt.AlignTop)
        self.results_area.setWidget(self.results_content)
        self.results_area.verticalScrollBar().valueChanged.connect(self.lazy_load_visible_results)
        l.addWidget(self.results_area, 1)
        self.content_splitter.addWidget(w)
        
    def _setup_queue_pane(self):
        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(0,0,0,0)
        h = QHBoxLayout()
        self.queue_label = QLabel("Download Queue (0)")
        h.addWidget(self.queue_label)
        h.addStretch()
        self.dl_btn = QPushButton("Download All")
        self.dl_btn.setToolTip("Download all pending tracks in queue")
        self.dl_btn.clicked.connect(self.start_batch_download)
        h.addWidget(self.dl_btn)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setToolTip("Cancel ongoing download")
        self.cancel_btn.clicked.connect(self.cancel_batch_download)
        self.cancel_btn.setVisible(False)
        h.addWidget(self.cancel_btn)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setToolTip("Clear finished items from queue")
        self.clear_btn.clicked.connect(self.clear_completed)
        h.addWidget(self.clear_btn)
        l.addLayout(h)
        
        self.queue_area = QScrollArea()
        self.queue_area.setWidgetResizable(True)
        self.queue_content = DraggableQueueWidget()
        self.queue_content.setObjectName("scrollContent")
        self.queue_vbox = QVBoxLayout(self.queue_content)
        self.queue_vbox.setAlignment(Qt.AlignTop)
        self.queue_area.setWidget(self.queue_content)
        self.queue_area.verticalScrollBar().valueChanged.connect(self.lazy_load_visible_queue)
        self.queue_content.order_changed.connect(self._on_queue_order_changed)
        l.addWidget(self.queue_area, 1)
        self.content_splitter.addWidget(w)

    def _on_queue_order_changed(self):
        if hasattr(self.queue_content, '_pending_reorder'):
            src_idx, dst_idx = self.queue_content._pending_reorder
            if 0 <= src_idx < len(self.queue_items) and 0 <= dst_idx < len(self.queue_items):
                src_item = self.queue_items[src_idx]
                dst_item = self.queue_items[dst_idx]
                if src_item.get('status') == 'Pending' and dst_item.get('status') == 'Pending':
                    item = self.queue_items.pop(src_idx)
                    self.queue_items.insert(dst_idx, item)
                    self.queue_update_signal.emit()

    def apply_theme(self):
        mode = self.appearance_mode
        if mode == "System": mode = get_system_appearance_mode()
        
        accent = get_accent_color(self.accent_color_name)
        
        r = int(accent[1:3], 16)
        g = int(accent[3:5], 16)
        b = int(accent[5:7], 16)
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        accent_fg = "#000000" if brightness > 150 else "#ffffff"
        
        # Write checkmark SVG to a temp file
        import tempfile, os as _os
        checkmark_svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{accent_fg}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
        if not hasattr(self, '_checkmark_svg_path') or not _os.path.exists(self._checkmark_svg_path):
            tmp = tempfile.NamedTemporaryFile(suffix='.svg', delete=False, mode='w', encoding='utf-8')
            tmp.write(checkmark_svg)
            tmp.close()
            self._checkmark_svg_path = tmp.name.replace('\\', '/')
        else:
            with open(self._checkmark_svg_path, 'w', encoding='utf-8') as f:
                f.write(checkmark_svg)
        checkmark_path = self._checkmark_svg_path
        
        # Write downarrow SVG to a temp file
        downarrow_svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{accent_fg}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>'
        if not hasattr(self, '_downarrow_svg_path') or not _os.path.exists(self._downarrow_svg_path):
            tmp = tempfile.NamedTemporaryFile(suffix='.svg', delete=False, mode='w', encoding='utf-8')
            tmp.write(downarrow_svg)
            tmp.close()
            self._downarrow_svg_path = tmp.name.replace('\\', '/')
        else:
            with open(self._downarrow_svg_path, 'w', encoding='utf-8') as f:
                f.write(downarrow_svg)
        downarrow_path = self._downarrow_svg_path
        
        if mode == "Light":
            bg = "#f3f3f3"
            fg = "#1a1a1a"
            frame_bg = "#ffffff"
            input_bg = "#e8e8e8"
            input_border = "#ccc"
            scroll_bg = "#ffffff"
            splitter_handle = "#ddd"
            slider_bg = "#ddd"
            hover_bg = "#000000"
            hover_fg = "#ffffff"
            queue_item_bg = "#e8e8e8"
            queue_item_bg_finished = "#ffffff"
            btn_hover = "rgba(0, 0, 0, 0.1)"
            if self.accent_color_name == "White" or accent.upper() == "#FFFFFF":
                main_btn_border = "1px solid #ccc"
            else:
                main_btn_border = "none"
        else:
            bg = "#1e1e1e"
            fg = "#ffffff"
            frame_bg = "#2a2a2a"
            input_bg = "#333333"
            input_border = "#555"
            scroll_bg = "#1a1a1a"
            splitter_handle = "#333333"
            slider_bg = "#333"
            hover_bg = "#dddddd"
            hover_fg = "#1a1a1a"
            queue_item_bg = "#333333"
            queue_item_bg_finished = "#1a1a1a"
            btn_hover = "rgba(255, 255, 255, 0.1)"
            main_btn_border = "none"

        secondary_fg = "#777777" if mode == "Light" else "#999999"

        # Canonical tooltip style. Applied to the whole application (see below) so
        # every window — the main window and all dialogs — shows identical tooltips
        # with the same font size and appearance as the playback controls.
        tooltip_css = (
            "QToolTip {"
            f" background-color: {frame_bg};"
            f" color: {fg};"
            f" border: 1px solid {input_border};"
            " padding: 2px 6px;"
            " border-radius: 4px;"
            " font-family: 'Segoe UI';"
            " font-size: 10px;"
            " font-weight: normal;"
            " show-delay: 4000ms;"
            " }"
        )

        full_css = """
            QMainWindow, QDialog {{ background-color: {bg}; }}
            QWidget {{ color: {fg}; font-family: 'Segoe UI'; font-size: 13px; }}
            QWidget#scrollContent, DraggableQueueWidget#scrollContent {{ background-color: {scroll_bg}; }}
            QWidget#queueItemPending {{ background-color: {queue_item_bg}; border-radius: 4px; margin-bottom: 2px; }}
            QWidget#queueItemFinished {{ background-color: {queue_item_bg_finished}; border-radius: 4px; margin-bottom: 2px; }}
            QLabel {{ color: {fg}; }}
            QLabel#durationLabel {{ color: {secondary_fg}; font-size: 11px; background: transparent; border: none; }}
            QLabel#channelLabel {{ color: {secondary_fg}; font-size: 11px; background: transparent; border: none; }}
            QPushButton {{ 
                background-color: {accent}; 
                color: {accent_fg}; border: {main_btn_border}; padding: 6px 12px; border-radius: 4px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {hover_bg}; color: {hover_fg}; }}
            QPushButton:disabled {{ background-color: #555555; color: #888888; }}
            QLineEdit {{ 
                background-color: {input_bg}; color: {fg}; border: 1px solid {input_border}; padding: 6px; border-radius: 4px;
            }}
            QComboBox {{ 
                background-color: {input_bg}; color: {fg}; border: 1px solid {input_border}; padding: 6px; border-radius: 4px;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border-left: 1px solid {input_border};
                background-color: {accent};
                border-top-right-radius: 3px;
                border-bottom-right-radius: 3px;
            }}
            QComboBox::down-arrow {{
                image: url("{downarrow_path}");
                width: 16px; height: 16px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {input_bg};
                color: {fg};
                selection-background-color: {accent};
                selection-color: {accent_fg};
                border: 1px solid {input_border};
            }}
            QScrollArea {{ border: none; background-color: {scroll_bg}; border-radius: 6px;}}
            QFrame {{ background-color: {frame_bg}; border-radius: 6px; padding: 5px;}}
            QSplitter::handle {{ background-color: {splitter_handle}; width: 6px; margin: 0px 2px; }}
            QSlider::groove:horizontal {{ border: none; height: 4px; background: {slider_bg}; border-radius: 2px; }}
            QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: {accent}; width: 16px; height: 16px; margin-top: -6px; margin-bottom: -6px; border-radius: 8px; }}
            QSlider#volSlider[volume_state="normal"]::sub-page:horizontal {{ background: {accent}; }}
            QSlider#volSlider[volume_state="normal"]::handle:horizontal {{ background: {accent}; }}
            QSlider#volSlider[volume_state="orange"]::sub-page:horizontal {{ background: #FF8C00; }}
            QSlider#volSlider[volume_state="orange"]::handle:horizontal {{ background: #FF8C00; }}
            QSlider#volSlider[volume_state="red"]::sub-page:horizontal {{ background: #E31E24; }}
            QSlider#volSlider[volume_state="red"]::handle:horizontal {{ background: #E31E24; }}
            QSlider#volSlider::sub-page:horizontal {{ border-radius: 1px; }}
            
            QCheckBox {{ color: {fg}; spacing: 8px; }}
            QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {accent}; border-radius: 3px; background: {frame_bg}; }}
            QCheckBox::indicator:checked {{ background: {accent}; image: url("{checkmark_path}"); }}
            
            QPushButton#transparentBtn {{
                background-color: transparent;
                color: {fg};
                font-weight: normal;
                border-radius: 0px;
                padding: 4px;
                text-align: left;
            }}
            QPushButton#transparentBtn:hover {{
                background-color: {btn_hover};
            }}
            QWidget#localRow {{
                background-color: transparent;
                border-radius: 4px;
            }}
            QWidget#localRow[selected="true"] {{
                background-color: {accent};
            }}
            /* The row that is the track the player is holding wears the colour of that
               state - green while it runs, orange while it is held - and it is written
               after the selection rule so that a row which is both selected and playing
               says the thing the listener is looking at the folder list to find out. */
            QWidget#localRow[play_state="playing"] {{
                background-color: {THUMB_BOX_PLAYING};
            }}
            QWidget#localRow[play_state="paused"] {{
                background-color: {THUMB_BOX_PAUSED};
            }}
            /* A green and an orange row both carry saturated colour behind the text, so
               the text on them is fixed rather than left to the theme's own foreground,
               which is chosen to sit on the dark panes and not on these. */
            QWidget#localRow[play_state="playing"] QPushButton#transparentBtn,
            QWidget#localRow[play_state="paused"] QPushButton#transparentBtn,
            QWidget#localRow[play_state="playing"] QLabel#durationLabel,
            QWidget#localRow[play_state="paused"] QLabel#durationLabel {{
                color: #1a1a1a;
                font-weight: bold;
            }}
            QPushButton#transparentBtn[selected="true"] {{
                background-color: transparent;
                color: {accent_fg};
            }}
            QPushButton#transparentBtn[selected="true"]:hover {{
                background-color: {btn_hover};
            }}
            QLabel#durationLabel[selected="true"] {{ color: {accent_fg}; }}
            /* The duration sits just off the right edge of a local row. Saying it once
               here instead of styling every row separately keeps the row build cheap,
               and it is scoped to the local pane, where that 6px gap was designed. */
            QWidget#localRow QLabel#durationLabel {{ padding-right: 6px; }}
            QMenu#localContextMenu {{
                background-color: {frame_bg};
                color: {fg};
                border: 1px solid {input_border};
                border-radius: 4px;
                padding: 4px;
            }}
            QMenu#localContextMenu::item {{
                padding: 6px 28px 6px 12px;
                border-radius: 3px;
            }}
            QMenu#localContextMenu::item:selected {{
                background-color: {accent};
                color: {accent_fg};
            }}
            QMenu#localContextMenu::item:disabled {{ color: {secondary_fg}; }}
            QMenu#localContextMenu::separator {{
                height: 1px;
                background: {input_border};
                margin: 4px 6px;
            }}
            QPushButton#iconBtn {{
                background-color: transparent;
                color: {fg};
                font-weight: normal;
                padding: 0px;
            }}
            QPushButton#topIconBtn {{
                background-color: transparent;
                color: {fg};
                font-family: 'Segoe MDL2 Assets';
                font-size: 15px;
                font-weight: normal;
                border: 1px solid {input_border};
                border-radius: 4px;
                padding: 0px;
            }}
            QPushButton#topIconBtn:hover {{
                background-color: {btn_hover};
            }}
            QPushButton#playerBtn {{
                background-color: transparent;
                color: {fg};
                font-family: 'Segoe MDL2 Assets';
                font-size: 20px;
                font-weight: normal;
                border-radius: 6px;
                padding: 0px;
            }}
            QPushButton#playerBtn:hover {{
                background-color: {btn_hover};
            }}
            QPushButton#playerBtn[active="true"] {{
                background-color: {accent};
                color: {accent_fg};
                font-weight: bold;
            }}
            QPushButton#playerBtn[active="true"]:hover {{
                background-color: {hover_bg};
                color: {hover_fg};
            }}
            QPushButton#playerPlayBtn {{
                background-color: transparent;
                color: {fg};
                font-family: 'Segoe MDL2 Assets';
                font-size: 30px;
                font-weight: normal;
                border-radius: 8px;
                padding: 0px;
            }}
            QPushButton#playerPlayBtn:hover {{
                background-color: {btn_hover};
            }}
            QPushButton#stopAfterBtn {{
                background-color: transparent;
                color: {secondary_fg};
                font-family: 'Segoe MDL2 Assets';
                font-size: 20px;
                font-weight: normal;
                border-radius: 6px;
                padding: 0px;
            }}
            QPushButton#stopAfterBtn:hover {{
                background-color: {btn_hover};
                color: {fg};
            }}
            QPushButton#stopAfterBtn[stop_after_state="once"] {{
                background-color: {accent};
                color: {accent_fg};
                font-weight: bold;
            }}
            QPushButton#stopAfterBtn[stop_after_state="always"] {{
                background-color: #E31E24;
                color: white;
                font-weight: bold;
            }}
            {tooltip_css}
        """.format(
            bg=bg, fg=fg, frame_bg=frame_bg, input_bg=input_bg, input_border=input_border,
            scroll_bg=scroll_bg, splitter_handle=splitter_handle, slider_bg=slider_bg,
            hover_bg=hover_bg, hover_fg=hover_fg, accent=accent, accent_fg=accent_fg,
            queue_item_bg=queue_item_bg, queue_item_bg_finished=queue_item_bg_finished,
            btn_hover=btn_hover, checkmark_path=checkmark_path, downarrow_path=downarrow_path,
            main_btn_border=main_btn_border, secondary_fg=secondary_fg,
            # The colours a row wears when it is the track the player is holding, shared with
            # the thumbnail box of a search row so both panes say the same thing in the same
            # green and the same orange.
            THUMB_BOX_PLAYING=THUMB_BOX_PLAYING, THUMB_BOX_PAUSED=THUMB_BOX_PAUSED,
            tooltip_css=tooltip_css
        )
        # Apply the theme at the widget level (as in 2.3). A single
        # self.setStyleSheet re-polishes only this window's subtree; routing it
        # through QApplication.setStyleSheet instead re-polishes every widget in
        # every top-level window, which is what made theme switching laggy. The
        # tooltip rules are embedded in full_css above and propagate to child
        # dialogs through this stylesheet, so no app-level call is required.
        self.setStyleSheet(full_css)
        self.update_shuffle_btn_style()
        self._update_stop_after_ui()

    # --- Local Folder Logic ---
    def set_local_explorer_address(self, path: str = "", add_to_recent: bool = False):
        """Show a folder in the local file explorer's address bar. This only
        rebuilds the address bar and its recent list; scanning the folder is a
        separate step, so a slow drive never holds the GUI thread hostage."""
        if not hasattr(self, 'local_path_combo'):
            return
        path = os.path.abspath(path) if path else ""
        if add_to_recent and path and path not in self.local_folders:
            self.local_folders.insert(0, path)
            self.local_folders = self.local_folders[:5]
        # The whole list is rebuilt rather than just appended to, because an
        # imported config can bring a different set of recent folders with it.
        self.local_path_combo.blockSignals(True)
        self.local_path_combo.clear()
        self.local_path_combo.addItems([str(folder) for folder in self.local_folders])
        if path:
            self.local_path_combo.setCurrentText(path)
        self.local_path_combo.blockSignals(False)

    def load_local_folder(self, path):
        if not path or not os.path.exists(path): return
        path = os.path.abspath(path)
        self.local_current_path = path

        self.set_local_explorer_address(path, add_to_recent=True)
        self.save_config()
        self.refresh_local_list()

    def toggle_local_metadata(self, state):
        self.show_local_metadata = (state == Qt.Checked.value)
        self.save_config()
        self.refresh_local_list()

    def refresh_local_list(self):
        """Re-render the open folder. The switch itself is instant and the rows then fill
        in a screenful at a time - see _start_local_render - so a folder holding hundreds
        of files no longer delays the screen change the user asked for."""
        self._start_local_render(self.local_current_path)

    def _refresh_local_list_async(self):
        """Rescan the open folder for every refresh that was not caused by the user
        directly (a sync finishing, the hourly auto-rescan). _start_local_render already
        does its scanning off the GUI thread, so this is the same path under the name the
        callers that must not block use."""
        self._start_local_render(self.local_current_path)

    def _start_local_render(self, path):
        """Show `path` now, and let its rows come in afterwards.

        The rows of the folder being replaced are torn down and the scan starts on a
        worker thread before this returns, so nothing about the screen change is waiting
        on the folder: the view is cleared to the new folder in the time it takes to drop
        the old rows, and the first rows land as soon as the listing is known. The
        listing itself is the cheap part - scandir hands over the name, size and timestamp
        of every entry as it walks the folder, so 500 files list in a few milliseconds -
        and it is sorted before the first batch because the batch order is the order the
        rows appear in, and File Explorer order is what the user expects to land on.

        Each render has its own id. The scan thread checks it before handing the listing
        over and the GUI thread checks it again before every chunk of rows it builds, so
        the rows of a folder that has already been left behind - or of a drive pulled out
        mid-listing - cannot arrive on the folder that is on screen instead."""
        self._local_render_id = getattr(self, '_local_render_id', 0) + 1
        render_id = self._local_render_id
        # A fill still under way belongs to the folder being replaced.
        self._local_render_timer.stop()
        self._local_render_pending = None
        # The metadata reads of the folder being replaced are cancelled here rather than
        # per chunk, because the chunks of one folder have to keep reading under the same
        # pass. See _fetch_local_metadata_bg.
        self._local_meta_pass = getattr(self, '_local_meta_pass', 0) + 1
        self._reset_local_rows()

        def _list_and_feed():
            items = self._scan_local_items(path)
            if render_id != getattr(self, '_local_render_id', 0):
                return  # a newer folder is on screen now; this listing is stale
            # The whole listing crosses to the GUI thread in one go, because how big a
            # chunk of rows should be depends on what building and painting them costs on
            # this machine, and only the GUI thread can know that. A folder that cannot be
            # listed comes back as None and is reported as an empty render, so the pane
            # stays clear for it instead of keeping rows from a drive that is gone.
            self._emit_local_listing(render_id, path, items)

        threading.Thread(target=_list_and_feed, daemon=True).start()

    def _emit_local_listing(self, render_id, path, items):
        """Hand the finished listing to the GUI thread, which does the chunking. Returning
        False means the signal is gone - the window is being torn down."""
        try:
            self._local_listing_signal.emit((render_id, path, items))
            return True
        except RuntimeError:
            return False

    def _on_local_listing(self, payload):
        """The GUI-thread half of a render: the new folder is on screen and its listing is
        known, so the pane starts filling with it - one screenful of rows first, everything
        after that behind it. A listing whose render id is not the current one belongs to a
        folder the user has already moved on from and is dropped."""
        render_id, path, items = payload
        if render_id != getattr(self, '_local_render_id', 0):
            return  # this listing was listed for a folder that has since been replaced
        if path != self.local_current_path:
            return  # and so was this one
        if not items:
            # A folder with nothing in it has no chunks to fill, but the render still has to
            # be closed out: the selection, and any track left paused when the window was
            # closed, are settled against a list that is now known to be empty.
            self._local_render_pending = None
            self._finish_local_render()
            return
        self._local_render_pending = items
        self._local_render_pending_id = render_id
        self._local_render_pending_path = path
        self._local_render_total_rows = len(items)
        self._local_render_step = self._local_screenful_rows()
        self._local_render_chunk_end = None
        self._local_render_chunk_cost = 0.0
        self._local_render_chunk_rows = 0
        self._local_render_row_cost = 0.0
        self._fill_local_chunk()

    def _local_screenful_rows(self):
        """How many rows the pane can show at once, which is the size of the first chunk:
        the rows the user switched folders to look at are the rows built first, and a folder
        smaller than a screen is built in one go, exactly as fast as it always was."""
        pane = getattr(self, 'local_list', None)
        height = pane.viewport().height() if pane is not None else 0
        fits = int(height // max(1.0, self._local_render_row_height)) if height > 0 else 0
        return max(fits, LOCAL_RENDER_FIRST_CHUNK_ROWS)

    def _fill_local_chunk(self):
        """Create the rows of the next chunk and hand control back. The event loop lays
        those rows out and polishes them before the zero timer runs this again, which is
        what makes a big folder fill in on screen instead of arriving all at once.

        The gap between one chunk ending and the next starting is what that chunk cost, its
        painting included, so it is divided by the rows that chunk produced to get what a row
        costs on this machine, and the next chunk is made as big as that cost allows within
        the budget. A folder of rows that are expensive - long titles, tags that have to be
        read - fills in smaller chunks than a folder of cheap ones, and both stay answerable."""
        pending = getattr(self, '_local_render_pending', None)
        if not pending:
            self._local_render_pending = None
            return
        if (self._local_render_pending_id != getattr(self, '_local_render_id', 0)
                or self._local_render_pending_path != self.local_current_path):
            self._local_render_pending = None
            return  # the user moved on while this folder was still filling in

        now = time.perf_counter()
        if self._local_render_chunk_end is not None:
            spent = (now - self._local_render_chunk_end) + self._local_render_chunk_cost
            cost_per_row = spent / max(1, self._local_render_chunk_rows)
            previous = self._local_render_row_cost
            # Smoothed, so one chunk that happened to land on a slow stretch - a folder
            # whose tags still have to be read, a window being dragged - does not decide
            # the size of every chunk after it.
            self._local_render_row_cost = (previous * 0.4 + cost_per_row * 0.6) \
                if previous > 0.0 else cost_per_row
            budget = max(0.001, LOCAL_RENDER_CHUNK_BUDGET_S)
            self._local_render_step = int(min(LOCAL_RENDER_CHUNK_MAX_ROWS,
                                              max(LOCAL_RENDER_CHUNK_MIN_ROWS,
                                                  budget / max(self._local_render_row_cost,
                                                              1e-6))))

        step = max(1, self._local_render_step)
        self._local_render_pending = pending[step:] or None
        rows_before = len(self.local_rows)
        try:
            self._append_local_rows(pending[:step])
        except RuntimeError:
            self._local_render_pending = None
            return  # the pane is being taken down around us
        self._local_render_chunk_cost = time.perf_counter() - now
        self._local_render_chunk_end = time.perf_counter()
        rows_added = len(self.local_rows) - rows_before
        self._local_render_chunk_rows = rows_added
        if rows_added:
            self._measure_local_row_pitch(rows_before)
            # The listing has always said how many rows there are going to be, and the fill knows
            # what a row of this folder costs the list, so the height of the finished folder is
            # known here - before any of these rows have been painted - and the pane is given it.
            # Everything the fill does after this point happens inside a pane that is already the
            # size it is going to end up.
            self._reserve_local_extent()
        if self._local_render_pending:
            self._local_render_timer.start(0)
        else:
            self._finish_local_render()

    def _measure_local_row_pitch(self, rows_before):
        """What one row of this folder costs the list, read off the rows already on screen.

        The height the pane's content reports lags a fill like this one: a row container has only
        just been created, so it has nothing to report about its own height until the event loop
        has polished it and laid it out. Measuring a row from that number is measuring the rows of
        the chunk before last, and an estimate built from it is a little different at every chunk -
        which makes the pane a slightly different size at every chunk, the thing the reservation
        below exists to prevent. The rows the previous chunk built have been laid out by now, and
        where the first and last of them ended up says exactly what a row costs: the row itself and
        the spacing the list puts between rows.
        """
        if rows_before < 2:
            return  # nothing has been laid out yet, so the guess stands
        first_row = self.local_rows[0][0]
        settled_row = self.local_rows[rows_before - 1][0]
        span = settled_row.y() - first_row.y()
        if span <= 0:
            return  # and this chunk got its turn before those rows were laid out
        self._local_render_row_height = span / (rows_before - 1)

    def _reserve_local_extent(self):
        """Hand the pane the height the finished folder is going to take up.

        The listing has said how many rows the folder has since before the first row existed, and
        the fill knows what a row of this folder costs the list, so the height the finished folder
        is going to occupy is worked out here - before any of its rows have been painted - and the
        content widget is given it as its own minimum. From here on the fill happens inside a pane
        that is already the size it is going to end up: the rows already drawn do not move, the
        scrollbar spans the whole folder before its last row exists, and each chunk after the first
        is built into room that is already there instead of making the folder taller under the user
        a batch at a time. That is the cheaper shape as well - a content widget whose own height
        has changed makes Qt lay out every row it already has again, and doing that twenty-odd
        times is most of what a streamed fill costs.

        The estimate is reworked at every chunk and only worth acting on when it has moved by more
        than a row, so the pane is sized once, early, and left alone.
        """
        pane = getattr(self, 'local_list', None)
        content = getattr(self, 'local_content', None)
        total = getattr(self, '_local_render_total_rows', 0)
        if pane is None or content is None or total <= 0:
            return
        row_pitch = max(1.0, self._local_render_row_height)
        # The space the list leaves above its first row and below its last. The rows carry the
        # top one in their own position on screen; the bottom one is the same margin.
        top_margin = 0
        if self.local_rows:
            top_margin = max(0, self.local_rows[0][0].y())
        height = int(total * row_pitch + 2 * top_margin + 0.5)
        height = max(height, pane.viewport().height())
        applied = getattr(self, '_local_render_extent_height', 0)
        if applied and abs(height - applied) <= row_pitch:
            return  # the pane already has room for the whole folder
        self._local_render_extent_height = height
        content.setMinimumHeight(height)

    def _release_local_extent(self):
        """Take back the height reserved for a folder that is no longer filling in.

        Two moments want it. At the end of a fill the rows themselves are the better answer for
        how tall the pane's content is than the estimate the fill was working to, and dropping
        the estimate is what keeps a folder whose rows came out a little shorter than expected
        from leaving a strip of blank pane under it. And when a folder is being replaced, the
        reserved height belongs to a listing that is going away; the incoming folder reserves its
        own as soon as its first chunk has landed.
        """
        self._local_render_total_rows = 0
        self._local_render_extent_height = 0
        content = getattr(self, 'local_content', None)
        if content is not None:
            content.setMinimumHeight(0)

    def _scan_local_items(self, folder_path: str):
        """All filesystem work for the local file list. Returns None when the
        folder is unavailable, otherwise the rows that should be displayed."""
        if not folder_path or not os.path.exists(folder_path):
            return None
        items = []
        try:
            parent = os.path.dirname(folder_path)
            if parent and parent != folder_path:
                items.append({'name': ".. (Back)", 'path': parent, 'is_dir': True, 'selectable': False})
            with os.scandir(folder_path) as current_dir:
                for entry in current_dir:
                    if entry.is_dir():
                        items.append({'name': entry.name, 'path': entry.path, 'is_dir': True, 'selectable': True})
                    elif entry.is_file():
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in AUDIO_EXTENSIONS:
                            item = {'name': entry.name, 'path': entry.path, 'is_dir': False, 'selectable': True}
                            # Anything this session has already read for this file comes
                            # straight out of the cache, so a folder that has been opened
                            # before renders with its durations already written and no
                            # reading at all. DirEntry.stat() costs nothing extra here:
                            # Windows already hands the size and the timestamp over
                            # inside the directory listing scandir is walking.
                            cached = None
                            try:
                                st = entry.stat()
                                cached = _local_meta_cache.get((entry.path, st.st_mtime_ns, st.st_size))
                            except OSError:
                                cached = None
                            if cached is not None:
                                title, artist, duration, tags_resolved = cached
                                # Tags only count as known when they were actually read:
                                # "Show artist/title" switched on later has to be able to
                                # ask for the ones that were skipped while it was off.
                                if tags_resolved or not getattr(self, 'show_local_metadata', False):
                                    item['meta_name'] = _local_display_name(item['name'], title, artist)
                                    item['duration_str'] = _format_audio_duration(duration)
                            items.append(item)
        except Exception:
            pass
        items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        return items

    def _build_local_rows(self, items):
        """Render a list that is already fully known in one pass. Folder switches use
        _start_local_render, which streams the rows in batch by batch; this is kept for
        callers that have the whole listing in hand."""
        self._reset_local_rows()
        self._append_local_rows(items or [])
        self._finish_local_render()

    def _reset_local_rows(self):
        """Tear down the rows of the folder being replaced. What was selected survives,
        so a refresh of the folder already on screen - a sync landing new files - does not
        quietly drop the user's selection. The row the shift-ranges were anchored to does
        not survive, and the count beside the metadata checkbox waits until the new rows
        exist rather than reporting the selection of rows that are no longer there."""
        while self.local_vbox.count():
            item = self.local_vbox.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        self.local_rows = []
        self.local_row_by_path = {}
        self.local_btns = []
        # These rows are gone, and with them the row this app was colouring.
        self._forget_playback_box()
        self.current_local_items = []
        self.local_selection_anchor = None
        self._update_local_selection_ui()
        # The height handed to the pane for the rows of the folder being replaced goes with
        # them; the incoming folder reserves its own once its first chunk has landed.
        self._release_local_extent()

    def _append_local_rows(self, items):
        """Create the widgets for one batch of rows. Numbering continues from the rows
        already on screen, so selection ranges and the right-click menu keep working
        while a folder is still being filled in. The metadata reads for this batch start
        here rather than at the end of the folder, so a duration appears on a row the
        user can already see."""
        base_index = len(self.local_rows)
        prev_btns = len(self.local_btns)

        for offset, item in enumerate(items):
            idx = base_index + offset
            raw_title = item.get('meta_name', item['name']) if getattr(self, 'show_local_metadata', False) else item['name']
            escaped_title = raw_title.replace('&', '&&')

            # Every row is wrapped in a styled container so a selection can be
            # highlighted across the whole row, the way File Explorer does it.
            row_w = QWidget()
            row_w.setObjectName("localRow")
            row_w.setAttribute(Qt.WA_StyledBackground, True)
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(2, 1, 2, 1)
            row_l.setSpacing(4)

            if item['is_dir']:
                full_title = f"📁  {escaped_title}"
                btn = DoubleClickButton(full_title)
                btn.setObjectName("transparentBtn")
                btn.setToolTip("Click to select | Double-click to open folder")
                btn._elide = _ElideTextFilter(full_title, reserve=12).attach(btn)
                if item.get('selectable', True):
                    btn.singleClicked.connect(lambda i=item, k=idx: self._on_local_select(i, k))
                else:
                    btn.singleClicked.connect(lambda i=item: self._on_local_click(i))
                btn.doubleClicked.connect(lambda i=item: self._on_local_click(i))
                dur_lbl = None
            else:
                full_title = f"🎵  {escaped_title}"
                btn = DoubleClickButton(full_title)
                btn.setObjectName("transparentBtn")
                btn.setToolTip("Click to select | Double-click to play")
                btn.doubleClicked.connect(lambda i=item: self._on_local_click(i))
                btn.singleClicked.connect(lambda i=item, k=idx: self._on_local_select(i, k))
                btn._elide = _ElideTextFilter(full_title, reserve=12).attach(btn)

                # Nothing styled per row here: QLabel#durationLabel in the app
                # stylesheet already carries the colour, the size and the spacing.
                # Parsing a style string for every row is work the pane does on the
                # GUI thread while it should be laying the folder out.
                dur_lbl = QLabel(item.get('duration_str', ''))
                dur_lbl.setObjectName("durationLabel")

            row_l.addWidget(btn, 1)
            if dur_lbl is not None:
                row_l.addWidget(dur_lbl)
            self.local_vbox.addWidget(row_w)

            # Right-click menu on the row, the way File Explorer does it.
            for menu_target in (row_w, btn):
                menu_target.setContextMenuPolicy(Qt.CustomContextMenu)
                menu_target.customContextMenuRequested.connect(
                    lambda pos, w=menu_target, i=item, k=idx: self._show_local_context_menu(w, pos, i, k))

            self.local_rows.append((row_w, btn, dur_lbl, item, idx))
            self.local_row_by_path[item['path']] = len(self.local_rows) - 1
            if not item['is_dir']:
                self.local_btns.append((btn, dur_lbl, item))

        self.current_local_items.extend(items)
        # A selection that survived a refresh of the folder has to pick up the rows built
        # after it. When nothing is selected there is nothing to pick up: a fresh row
        # carries no 'selected' property at all and the stylesheet only styles
        # selected="true", so skipping this pass is what keeps a 500-file folder from
        # re-polishing every row it has already drawn, batch after batch.
        if getattr(self, 'local_selected_paths', ()):
            self._apply_local_selection_styles()
        # The play state is not part of the selection, so it is put onto the new rows on its
        # own: a folder refreshed under a playing file rebuilds the row for that file, and
        # that row has to come back carrying the colour it had before it was replaced.
        self._reapply_playback_box_after_rebuild()
        self._fetch_local_metadata_bg(self.local_btns[prev_btns:])

    def _finish_local_render(self):
        """The last batch of this render has landed. Only now is it known whether a
        selection that survived the refresh still points at something in the folder, and
        a local track the session was closed on can be resumed against a list that is
        finally complete."""
        self._release_local_extent()
        previous_selection = set(getattr(self, 'local_selected_paths', ()))
        self.local_selected_paths = {p for p in previous_selection if p in self.local_row_by_path}
        self._apply_local_selection_styles()
        self._update_local_selection_ui()

        resume_index = getattr(self, '_pending_local_restore_index', None)
        if resume_index is None:
            return
        resume_path = getattr(self, '_pending_local_restore_path', None)
        if resume_path is not None and os.path.abspath(resume_path) != self.local_current_path:
            return  # this folder is not the one that track was left on
        self._pending_local_restore_index = None
        audio_files = [x for x in self.current_local_items if not x.get('is_dir')]
        if 0 <= resume_index < len(audio_files):
            QTimer.singleShot(100, lambda: self._on_local_click(audio_files[resume_index], paused_at_start=True))
            
    def _fetch_local_metadata_bg(self, rows=None):
        """Fill in the durations and the artist/title of the rows handed to it - the
        batch of rows that just landed, or every row of the folder when called without
        any. mutagen reads them inside this process; ffprobe is only reached for the
        files mutagen cannot open or cannot tag. A row whose values were already answered
        from the cache while the folder was scanned is not touched at all, and each row
        that does need reading is written back on its own instead of the whole list being
        rebuilt around it."""
        from PySide6.QtCore import QObject, Signal

        class MetaWorker(QObject):
            meta_done = Signal(object, object, object)

        if getattr(self, '_meta_worker', None) is None:
            self._meta_worker = MetaWorker()
            self._meta_worker.meta_done.connect(self._apply_local_row_meta)

        # The pass belongs to the render, not to this call. Every batch of the folder on
        # screen reads under the same pass, so a batch landing a second into a 500-file
        # folder cannot cancel the reads of the batches before it. Switching folders bumps
        # the pass in _start_local_render, and that is what stops the reads of the folder
        # that has been replaced - a backlog that was a large part of what made the next
        # folder slow to fill in.
        this_pass = getattr(self, '_local_meta_pass', 0)

        source = self.local_btns if rows is None else rows
        pending = [(btn, d_lbl, item) for (btn, d_lbl, item) in source
                   if 'duration_str' not in item]
        if not pending:
            return

        want_tags = getattr(self, 'show_local_metadata', False)
        workers = max(1, min(4, os.cpu_count() or 1))

        # One reader pool per render rather than one per batch: the batches of a streamed
        # folder arrive every few milliseconds, and each with its own pool of readers would
        # pile threads onto the disk the folder is being read from.
        pool = getattr(self, '_meta_pool', None)
        if pool is None or getattr(self, '_meta_pool_pass', None) != this_pass:
            old_pool = pool
            pool = ThreadPoolExecutor(max_workers=workers)
            self._meta_pool = pool
            self._meta_pool_pass = this_pass
            if old_pool is not None:
                try:
                    # Reads queued for the folder that has just been replaced are pointless.
                    old_pool.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass

        def read_row(btn, d_lbl, item):
            if self._local_meta_pass != this_pass:
                return  # a newer folder is on screen; this row is gone
            path = item['path']
            ext = os.path.splitext(path)[1].lower()
            # What the file IS, taken before anything is read from it. The read and the
            # cache entry are pinned to this same identity, so a file that is being
            # written right now cannot have one version's values filed under another's.
            try:
                st_before = os.stat(path)
                cache_key = (path, st_before.st_mtime_ns, st_before.st_size)
            except OSError:
                cache_key = None
            read = _read_local_audio_meta(path)
            if read is None:
                title, artist, duration = None, None, None
                tags_unknown = True   # mutagen will not open this format at all
            else:
                title, artist, duration = read
                # mutagen read the tag system in this container and found no title, so
                # there is no title to find. Where it has no tag API at all (wav, aiff)
                # or cannot open the file (mka, ape), the tags stay unknown until
                # either ffprobe has answered or the pane stops asking for tags.
                tags_unknown = not title and ext not in MUTAGEN_TAGGABLE_EXTENSIONS

            if duration is None or (tags_unknown and want_tags):
                ff_title, ff_artist, ff_duration = _ffprobe_audio_meta(path)
                if duration is None:
                    duration = ff_duration
                if tags_unknown:
                    title, artist = ff_title, ff_artist
                tags_resolved = True
            else:
                tags_resolved = not tags_unknown

            item['meta_name'] = _local_display_name(item['name'], title, artist)
            item['duration_str'] = _format_audio_duration(duration)
            if cache_key is not None:
                try:
                    st_after = os.stat(path)
                except OSError:
                    st_after = None
                # Worth remembering only if the file is still the one that was read.
                if st_after is not None and (st_after.st_mtime_ns, st_after.st_size) == cache_key[1:]:
                    _local_meta_cache_put(cache_key, title, artist, duration, tags_resolved)
            if self._local_meta_pass != this_pass:
                return  # superseded while the read was running: there is no row to write onto
            self._meta_worker.meta_done.emit(btn, d_lbl, item)

        # The rows are queued on the render's own pool. submit() is what starts the reader
        # threads and it costs microseconds, so the GUI thread is back at the event loop
        # building the next batch of rows while these reads run.
        for btn, d_lbl, item in pending:
            try:
                pool.submit(read_row, btn, d_lbl, item)
            except Exception:
                break  # this pool was already closed by a newer render

    def _apply_local_row_meta(self, btn, d_lbl, item):
        """Write the values a background read produced onto that one row: the name
        through the elide filter, so the row keeps its trimming behaviour, and the
        duration straight into its own label. Nothing else in the list is touched."""
        row_index = getattr(self, 'local_row_by_path', {}).get(item['path'])
        if row_index is None or row_index >= len(self.local_rows) or self.local_rows[row_index][1] is not btn:
            return  # a newer rebuild has since replaced this row
        try:
            raw_title = item.get('meta_name', item['name']) if getattr(self, 'show_local_metadata', False) else item['name']
            btn._elide.set_full_text(f"🎵  {raw_title.replace('&', '&&')}")
            if d_lbl is not None:
                d_lbl.setText(item.get('duration_str', ''))
        except RuntimeError:
            pass  # a newer rebuild has already torn this row down

    def _on_local_click(self, item, paused_at_start=False, from_nav=False):
        if item['is_dir']: 
            self.load_local_folder(item['path'])
        else:
            # If VLC is still initializing in background, retry after a short delay
            if not getattr(self, '_vlc_ready', False):
                QTimer.singleShot(200, lambda: self._on_local_click(item, paused_at_start, from_nav))
                return
            if self.vlc_instance is None or self.vlc_player is None:
                self._on_status_update("Playback unavailable: VLC Media Player is not installed.", False, "#E31E24")
                return

            display_name = item.get('meta_name', item['name']) if getattr(self, 'show_local_metadata', False) else item['name']
            self._on_status_update(f"Playing Local: {display_name}", False, "#3B8ED0")
            url = item['path'].replace("\\", "/")
            if not url.startswith("file:///"): url = "file:///" + url
            self.current_video_id = "local"
            # A file from the local pane is not the track a search armed its one-shot
            # for, and it steps through the folder list, which a search does not touch.
            self._release_search_stop_after("local")
            self.current_local_file_path = item['path']
            
            audio_files = [x for x in getattr(self, 'current_local_items', []) if x.get('is_dir') is False]
            for i, af in enumerate(audio_files):
                if af.get('path') == item.get('path'):
                    self.local_playback_index = i
                    break

            if not from_nav:
                # User manually selected a track: reset shuffle history with this track
                self.shuffle_history = [getattr(self, 'local_playback_index', 0)]
                    
            media = self.vlc_instance.media_new(url)
            self.vlc_player.set_media(media)
            if paused_at_start:
                self.vlc_player.audio_set_mute(True)
                self.vlc_player.play()
                def delay_pause():
                    self.vlc_player.set_pause(1)
                    self.vlc_player.set_position(0)
                    self.vlc_player.audio_set_mute(False)
                QTimer.singleShot(250, delay_pause)
            else:
                self.vlc_player.play()
            # A file on disk is not a signed link with a lifetime, so there is nothing here that
            # can expire: the stream watchdog is told to watch nothing on this track.
            self._note_loaded_stream(None)
            self.playback_started_signal.emit(display_name, "local", paused_at_start)

    # --- Local file editor: selection, delete, rename ---
    def _on_local_select(self, item, index):
        """Single-click selection for a local list row, mirroring File Explorer:
        a plain click selects only that row, Ctrl+click toggles rows in and out
        of the selection, and Shift+click selects everything between the row that
        was selected before and this one."""
        if not item.get('selectable', True):
            self._on_local_click(item)
            return
        mods = QApplication.keyboardModifiers()
        ctrl = bool(mods & (Qt.ControlModifier | Qt.MetaModifier))
        shift = bool(mods & Qt.ShiftModifier)
        path = item['path']

        if shift and getattr(self, 'local_selection_anchor', None) is not None:
            lo, hi = sorted((self.local_selection_anchor, index))
            for _, _, _, row_item, row_idx in self.local_rows:
                if lo <= row_idx <= hi and row_item.get('selectable', True):
                    self.local_selected_paths.add(row_item['path'])
        elif ctrl:
            if path in self.local_selected_paths:
                self.local_selected_paths.discard(path)
            else:
                self.local_selected_paths.add(path)
            self.local_selection_anchor = index
        else:
            self.local_selected_paths = {path}
            self.local_selection_anchor = index

        self._apply_local_selection_styles()
        self._update_local_selection_ui()

    def _selected_local_items(self):
        return [row_item for _, _, _, row_item, _ in getattr(self, 'local_rows', [])
                if row_item.get('selectable', True) and row_item['path'] in self.local_selected_paths]

    def select_all_local_files(self):
        if not getattr(self, 'local_rows', []):
            return
        self.local_selected_paths = {row_item['path'] for _, _, _, row_item, _ in self.local_rows
                                     if row_item.get('selectable', True)}
        self._apply_local_selection_styles()
        self._update_local_selection_ui()

    def clear_local_selection(self):
        self.local_selected_paths = set()
        self.local_selection_anchor = None
        self._apply_local_selection_styles()
        self._update_local_selection_ui()

    def _open_local_selection(self):
        items = self._selected_local_items()
        if len(items) == 1:
            self._on_local_click(items[0])

    def _focus_is_in_local_pane(self, widget=None) -> bool:
        """True when that widget - or the one holding focus when none is given - sits
        inside the local file list.

        The walk goes through parentWidget and not parent, because two of this
        program's dialogs keep the window that opened them in an attribute named parent,
        which replaces the Qt method of the same name on those instances. Walking with
        parent() from a control inside such a dialog therefore ends up calling the
        MainApp window itself, which is what raised
        "TypeError: 'MainApp' object is not callable" out of eventFilter on every key
        typed into Settings. parentWidget is a name the dialogs here never reassign.
        """
        w = widget if widget is not None else QApplication.focusWidget()
        if w is None or not hasattr(self, 'local_list'):
            return False
        while w is not None:
            if w is self.local_list or w is self.local_content:
                return True
            w = w.parentWidget()
        return False

    # ------------------------------------------------------------------
    # Which row the player is holding, in colour
    # ------------------------------------------------------------------
    # A search row already has a grey box around its thumbnail and a local row already
    # takes a background when it is selected, so the play state is not a new widget to
    # draw - it is one more thing those existing surfaces can say.
    #
    # The colour comes from what libVLC reports rather than from is_playing, because
    # is_playing is what the listener last asked for and not what the media is doing: a
    # stream whose URL has given out is neither playing nor held, and the box should say
    # that about it too. Opening and Buffering are left uncoloured for the same reason -
    # a track still on its way is not a track the player has got hold of yet.
    def _playback_box_state(self):
        """The play-state token for the state the player is in, or None when it holds
        nothing it could be playing."""
        if not self.vlc_player:
            return None
        try:
            state = self.vlc_player.get_state()
        except Exception:
            return None
        if state == vlc.State.Playing:
            return "playing"
        if state == vlc.State.Paused:
            return "paused"
        return None

    def _playback_box_key(self):
        """(where, which, state) for the row that carries the play state right now, or
        None when no row should. 'where' picks the pane and 'which' is the video id of a
        search row or the path of a local one - the same keys those panes already index
        their rows by."""
        state = self._playback_box_state()
        if state is None:
            return None
        vid_id = self.current_video_id
        if vid_id == "local":
            path = getattr(self, 'current_local_file_path', '')
            if not path:
                return None
            return ("local", path, state)
        if not vid_id:
            return None
        return ("search", vid_id, state)

    def _refresh_playback_highlights(self):
        """Move the coloured row to whichever track the player is holding, when that has
        changed since the last look.

        This runs from the player's own tick, which is already asking libVLC for the state,
        so a play, a pause, a resume, an automatic advance, prev/next, a local file and a
        stream that had to be re-resolved all land here without anything else having to
        remember to say so. A tick where nothing changed - which is nearly every tick -
        stops at this comparison, so a pane full of rows is not repolished sixty times a
        second while a track runs."""
        key = self._playback_box_key()
        previous = getattr(self, '_playback_box', None)
        if key == previous:
            return
        if previous is not None and key is not None and previous[:2] == key[:2]:
            # The same row changing colour - play into pause and back again - only has to
            # be repainted once, rather than cleared and painted again.
            self._apply_playback_box(key)
        else:
            if previous is not None:
                self._apply_playback_box((previous[0], previous[1], None))
            self._apply_playback_box(key)
        self._playback_box = key

    def _apply_playback_box(self, key):
        """Write a play state onto the row that key names. A state of None puts that row
        back to the plain look it has when it is not the loaded track."""
        if key is None:
            return
        where, target, state = key
        if where == "local":
            self._set_local_row_play_state(target, state)
        elif where == "search":
            self._set_search_row_box(target, state)

    def _forget_playback_box(self):
        """The row this app coloured is no longer there to uncolour. Dropping the record of
        it is what lets the next highlight reach the row that exists now instead of being
        skipped as already done - a new search and a rebuilt folder each replace every row
        the pane had, and a row that is rebuilt starts plain."""
        self._playback_box = None

    def _set_search_row_box(self, vid_id, state):
        label = getattr(self, '_thumbnail_labels', {}).get(vid_id)
        if label is None:
            return  # this row is scrolled out of view, so it has no thumbnail box to colour
        tile = label.parentWidget()
        if tile is None or not hasattr(tile, 'set_highlight'):
            return
        try:
            tile.set_highlight(state)
        except RuntimeError:
            pass  # the row was torn down between the lookup and the colouring

    def _set_local_row_play_state(self, path, state):
        index = getattr(self, 'local_row_by_path', {}).get(path)
        if index is None or index >= len(self.local_rows):
            return  # this file is not a row of the folder currently on screen
        row_w = self.local_rows[index][0]
        # An empty token matches no rule of the stylesheet, which is how the row gets its
        # plain background back. Local rows are coloured through the stylesheet rather than
        # per row so that filling a folder does not parse a style string for every file in it.
        token = state or ""
        try:
            if row_w.property('play_state') == token:
                return
            row_w.setProperty('play_state', token)
            row_w.style().unpolish(row_w)
            row_w.style().polish(row_w)
            row_w.update()
        except RuntimeError:
            pass  # a newer rebuild has already torn this row down

    def _reapply_playback_box_after_rebuild(self):
        """Put the play state back onto the rows that have just been created, when the track
        they contain is the one the player is holding."""
        box = getattr(self, '_playback_box', None)
        if box is None:
            return
        self._apply_playback_box(box)

    def _apply_local_selection_styles(self):
        selected_paths = getattr(self, 'local_selected_paths', set())
        for row_w, btn, dur_lbl, row_item, _ in getattr(self, 'local_rows', []):
            selected = row_item.get('selectable', True) and row_item['path'] in selected_paths
            targets = [row_w, btn] + ([dur_lbl] if dur_lbl is not None else [])
            for w in targets:
                if w.property('selected') == selected:
                    continue
                w.setProperty('selected', selected)
                try:
                    w.style().unpolish(w)
                    w.style().polish(w)
                except Exception:
                    pass
                w.update()

    def _update_local_selection_ui(self):
        count = len(self._selected_local_items())
        if hasattr(self, 'local_sel_label'):
            self.local_sel_label.setText(f"{count} selected" if count else "")

    def _show_local_context_menu(self, source_widget, pos, item, index):
        """Right-click menu for a row of the local file list, like File Explorer.
        Right-clicking a row that is not part of the selection selects it first."""
        if not item.get('selectable', True):
            menu = QMenu(self)
            menu.setObjectName("localContextMenu")
            open_act = menu.addAction("Open")
            open_act.triggered.connect(lambda checked=False, i=item: self._on_local_click(i))
            menu.exec(source_widget.mapToGlobal(pos))
            menu.deleteLater()
            return

        if item['path'] not in getattr(self, 'local_selected_paths', set()):
            self._on_local_select(item, index)

        # Keep the keyboard shortcuts (Ctrl+C, Del, F2) live after a right-click.
        try:
            self.local_rows[self.local_row_by_path[item['path']]][1].setFocus()
        except Exception:
            pass

        selected = self._selected_local_items()
        files = [i for i in selected if not i['is_dir']]

        menu = QMenu(self)
        menu.setObjectName("localContextMenu")
        if len(selected) == 1:
            only = selected[0]
            open_act = menu.addAction("Play" if not only['is_dir'] else "Open")
            open_act.setToolTip("Open this folder" if only['is_dir'] else "Play this file")
            open_act.triggered.connect(lambda checked=False, i=only: self._on_local_click(i))
        rename_act = menu.addAction("Rename from metadata\tF2")
        rename_act.setToolTip("Rename the selected files from their artist / title tags")
        rename_act.setEnabled(bool(files))
        rename_act.triggered.connect(lambda checked=False: self.rename_local_selected())
        copy_act = menu.addAction("Copy\tCtrl+C")
        copy_act.setToolTip("Copy the selected files so they can be pasted into File Explorer")
        copy_act.setEnabled(bool(selected))
        copy_act.triggered.connect(lambda checked=False: self.copy_local_selected())
        menu.addSeparator()
        delete_act = menu.addAction("Delete\tDel")
        delete_act.setToolTip("Delete the selected files")
        delete_act.setEnabled(bool(selected))
        delete_act.triggered.connect(lambda checked=False: self.delete_local_selected())
        menu.exec(source_widget.mapToGlobal(pos))
        menu.deleteLater()

    def copy_local_selected(self):
        """Copy the selected files to the clipboard as real file references, so
        they can be pasted into File Explorer or any other file-aware target."""
        items = self._selected_local_items()
        if not items:
            self._on_status_update("Nothing selected to copy.", False, "#E31E24")
            return
        paths = [i['path'] for i in items]
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        mime.setText("\n".join(paths))
        QApplication.clipboard().setMimeData(mime)
        label = Path(paths[0]).name if len(paths) == 1 else f"{len(paths)} files"
        self._on_status_update(f"Copied {label} to the clipboard.", False, "#3B8ED0")

    def delete_local_selected(self):
        """Delete the selected files (and empty folders) after a confirmation."""
        items = self._selected_local_items()
        if not items:
            self._on_status_update("Nothing selected to delete.", False, "#E31E24")
            return
        names = [i['name'] for i in items]
        preview = "\n".join(names[:10]) + ("\n..." if len(names) > 10 else "")
        answer = QMessageBox.question(
            self, "Delete Selected",
            f"Permanently delete {len(items)} item(s)?\n\n{preview}\n\n"
            "Folders are only deleted when they are empty.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        deleted_files = 0
        deleted_folders = 0
        problems = []
        playing = getattr(self, 'current_local_file_path', '')
        for it in items:
            target = it['path']
            try:
                if it['is_dir']:
                    if os.listdir(target):
                        problems.append(f"{it['name']} (folder not empty)")
                        continue
                    os.rmdir(target)
                    deleted_folders += 1
                else:
                    os.remove(target)
                    deleted_files += 1
            except Exception as e:
                problems.append(f"{it['name']} ({e})")
                continue
            if playing and os.path.abspath(target) == os.path.abspath(playing):
                player = getattr(self, 'vlc_player', None)
                if player is not None:
                    try:
                        player.stop()
                    except Exception:
                        pass
                self.current_local_file_path = ""
        self.clear_local_selection()
        self.refresh_local_list()
        msg = f"Deleted {deleted_files} file(s)"
        if deleted_folders:
            msg += f" and {deleted_folders} folder(s)"
        if problems:
            msg += ". Skipped: " + ", ".join(problems[:4])
        self._on_status_update(msg, False, "#1abd33" if not problems else "#E31E24")

    def rename_local_selected(self):
        """Open the metadata renamer for the selected tracks, then rename every
        one of them to 'Artist - Title' built from the tags they carry."""
        files = [i for i in self._selected_local_items() if not i['is_dir']]
        if not files:
            self._on_status_update("Rename: select at least one audio file.", False, "#E31E24")
            return
        dlg = MetadataRenameDialog(self, [i['path'] for i in files])
        results = dlg.results if dlg.exec() == QDialog.Accepted else []
        renamed = [r for r in results if r['status'] == 'renamed']
        skipped = [r for r in results if r['status'] in ('conflict', 'failed')]
        playing = getattr(self, 'current_local_file_path', '')
        for r in renamed:
            if playing and os.path.abspath(r['old']) == os.path.abspath(playing):
                self.current_local_file_path = r['new']
                break
        self.clear_local_selection()
        self.refresh_local_list()
        if not results:
            return
        msg = f"Renamed {len(renamed)} file(s) to 'Artist - Title' from metadata."
        if skipped:
            msg += f" Skipped {len(skipped)}: " + ", ".join(s['message'] for s in skipped[:3])
        self._on_status_update(msg, False, "#1abd33" if not skipped else "#E31E24")

    def open_settings_dialog(self):
        if not hasattr(self, 'settings_dialog') or self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(self)
            self.settings_dialog.setWindowModality(Qt.NonModal)
            self.settings_dialog.setAttribute(Qt.WA_DeleteOnClose, False)
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def open_playlist_dialog(self):
        d = PlaylistDialog(self)
        if d.exec() == QDialog.Accepted and d.url_cb.currentText():
            val = d.url_cb.currentText()
            url = val
            for p in self.recent_playlists:
                if isinstance(p, dict) and p.get("name") == val:
                    url = p.get("url")
                    break
            self.search_entry.setText(url)
            self.perform_search(is_playlist=True)

    def perform_search(self, is_playlist=False):
        query = self.search_entry.text()
        if not query: return
        # A new search is read from its first row, not from wherever the last one was left
        self._reset_results_scroll()
        self._on_status_update("Searching...", False, "#3B8ED0")
        self.search_btn.setEnabled(False)
        
        def bg_search():
            try:
                if "youtube.com" in query or "youtu.be" in query or "http" in query:
                    info = run_yt_dlp_json([
                        "--flat-playlist", "-J", "--playlist-items", "1-100", query,
                    ])
                    
                    if info and 'entries' in info:
                        res = [e for e in info['entries'] if e]
                        if len(info['entries']) >= 100:
                            start_idx = 101
                            chunk_size = 100
                            while True:
                                self.status_signal.emit(f"Searching... (Retrieved {len(res)} items)", False, "#3B8ED0")
                                chunk_info = run_yt_dlp_json([
                                    "--flat-playlist", "-J",
                                    "--playlist-items", f"{start_idx}-{start_idx + chunk_size - 1}",
                                    query,
                                ])
                                if not chunk_info or 'entries' not in chunk_info:
                                    break
                                entries = [e for e in chunk_info['entries'] if e]
                                if not entries:
                                    break
                                res.extend(entries)
                                if len(chunk_info['entries']) < chunk_size:
                                    break
                                start_idx += chunk_size
                    else:
                        res = [info] if info else []
                else:
                    info = run_yt_dlp_json(["--flat-playlist", "-J", f"ytsearch15:{query}"])
                    res = [e for e in info['entries'] if e.get('id')]
                        
                if is_playlist and ('youtube.com' in query or 'youtu.be' in query):
                    title = info.get('title', query) if isinstance(info, dict) else query
                    updated = False
                    for i, rp in enumerate(self.recent_playlists):
                        if isinstance(rp, dict) and rp.get("url") == query:
                            self.recent_playlists[i]["name"] = title
                            updated = True; break
                        elif rp == query:
                            self.recent_playlists[i] = {"name": title, "url": query}
                            updated = True; break
                    if not updated:
                        self.recent_playlists.insert(0, {"name": title, "url": query})
                        self.recent_playlists = self.recent_playlists[:5]
                    
                self.search_results_signal.emit(res, False)
            except Exception as exc:
                self.search_failed_signal.emit()
                if isinstance(exc, YtDlpMissingError):
                    self.ytdlp_missing_signal.emit("Searching and downloading both need yt-dlp.")
                
        threading.Thread(target=bg_search, daemon=True).start()

    def _on_search_results(self, res, is_playlist, reset_view=True):
        self.search_btn.setEnabled(True)
        self.search_results = res
        self._thumbnail_labels = getattr(self, '_thumbnail_labels', {})
        self._thumbnail_labels.clear()
        # Every row these results had is about to be deleted, so the row this app was
        # colouring goes with them and cannot be coloured back to plain later.
        self._forget_playback_box()
        
        while self.results_vbox.count():
            item = self.results_vbox.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        height = 54
        for video in res:
            placeholder = QWidget()
            placeholder.setFixedHeight(height)
            placeholder.setProperty("video", video)
            placeholder.setProperty("has_ui", False)
            self.results_vbox.addWidget(placeholder)
            
        # reset_view is True when these are results from a search that was just run, and
        # False when the same list is only being redrawn (settings
        # import, session restore). A new search is read from its first row, and the
        # successor decided for the list being replaced is no longer part of the playlist
        # playback is stepping through; a redraw of the same list is neither.
        # A search replaces the list playback is stepping through, so the track that
        # is playing when it lands is armed with a one-shot stop instead of being
        # followed by whatever row happens to sit at its index in the new list.
        search_armed_stop_after = False
        if reset_view:
            self.invalidate_next_track_prefetch()
            self._reset_results_scroll()
            search_armed_stop_after = self._arm_stop_after_for_new_search()
        if search_armed_stop_after:
            self._on_status_update(f"Found {len(res)} results - Stop after current", False, "#FF8C00")
        else:
            self._on_status_update(f"Found {len(res)} results.", False, "white")
        QTimer.singleShot(0, self.lazy_load_visible_results)
        # Lazy loading re-expands rows as they are built; land at the top again after it.
        if reset_view:
            QTimer.singleShot(0, self._reset_results_scroll)
        self.update_queue_all_checkbox_state()

    def _reset_results_scroll(self):
        """Scroll the results pane back to its top."""
        if getattr(self, 'results_area', None):
            self.results_area.verticalScrollBar().setValue(0)

    def _on_search_failed(self):
        self.search_btn.setEnabled(True)
        self._on_status_update("Search failed. Check your connection or URL.", False, "red")

    def toggle_queue(self, video, state):
        checked = state == Qt.Checked.value
        in_queue = any(q['video']['id'] == video['id'] for q in self.queue_items)
        if checked and not in_queue:
            self.queue_items.append({'video': video, 'status': 'Pending'})
        elif not checked and in_queue:
            self.queue_items = [q for q in self.queue_items if q['video']['id'] != video['id']]
        self.queue_update_signal.emit()

    def toggle_queue_all(self, state):
        checked = state == Qt.Checked.value
        if not self.search_results:
            return
            
        # Quick set for O(1) membership lookups to check if search results already exist in queue
        search_ids = {v['id'] for v in self.search_results if 'id' in v}
        
        # Modify queue in-place in bulk
        if checked:
            existing_queue_ids = {q['video']['id'] for q in self.queue_items if 'video' in q and 'id' in q['video']}
            new_items = []
            for video in self.search_results:
                if 'id' in video and video['id'] not in existing_queue_ids:
                    new_items.append({'video': video, 'status': 'Pending'})
            if new_items:
                self.queue_items.extend(new_items)
        else:
            self.queue_items = [q for q in self.queue_items if 'video' not in q or q['video'].get('id') not in search_ids]
            
        # Bulk-update checking of all currently visible result checkboxes to avoid individual trigger overhead
        for i in range(self.results_vbox.count()):
            layout_item = self.results_vbox.itemAt(i)
            if layout_item and layout_item.widget():
                widget = layout_item.widget()
                checkboxes = widget.findChildren(QCheckBox)
                for cb in checkboxes:
                    cb.blockSignals(True)
                    cb.setChecked(checked)
                    cb.blockSignals(False)
                    
        self.queue_update_signal.emit()

    def update_queue_all_checkbox_state(self):
        if not hasattr(self, 'queue_all_cb') or not self.search_results:
            return
            
        # Highly-optimized O(N + M) set-based comparison to prevent slowness/lag
        queue_ids = {q['video']['id'] for q in self.queue_items if 'video' in q and 'id' in q['video']}
        all_in_queue = True
        for video in self.search_results:
            if 'id' in video:
                if video['id'] not in queue_ids:
                    all_in_queue = False
                    break
                    
        self.queue_all_cb.blockSignals(True)
        self.queue_all_cb.setChecked(all_in_queue)
        self.queue_all_cb.blockSignals(False)

    def build_result_ui(self, placeholder, video, queue_ids):
        l = QHBoxLayout(placeholder)
        l.setContentsMargins(2,2,2,2)
        
        tw = ThumbnailWidget(video, self)
        l.addWidget(tw)
        self._thumbnail_labels[video['id']] = tw.thumb_label
        # A row that has just been built starts with the plain box, so the state it is in -
        # this row is the track that is running, held, or neither - has to be put on it now.
        box = getattr(self, '_playback_box', None)
        if box is not None and box[0] == "search" and box[1] == video.get('id', ''):
            tw.set_highlight(box[2])
        threading.Thread(target=self._fetch_thumbnail, args=(video,), daemon=True).start()
            
        title = video.get('title', 'Unknown')
        cb = QCheckBox(f"{title.replace('&', '&&')}")
        cb.setProperty("video_id", video.get('id', ''))
        
        # Persist checked state
        cb.setChecked(video.get('id') in queue_ids)
            
        cb.stateChanged.connect(lambda state, v=video: self.toggle_queue(v, state))
        cb._elide = _ElideTextFilter(f"{title.replace('&', '&&')}", reserve=28).attach(cb)
        l.addWidget(cb, 1)
        
        # Channel name (to the left of duration/timestamp)
        channel = video.get('channel') or video.get('uploader') or ''
        if channel:
            if len(channel) > 25:
                channel = channel[:23] + '…'
            ch_lbl = QLabel(channel)
            ch_lbl.setObjectName("channelLabel")
            ch_lbl.setStyleSheet("border: none; background: transparent; padding-right: 6px;")
            l.addWidget(ch_lbl)

        # Duration/timestamp
        dur = video.get('duration_string')
        if not dur and video.get('duration'):
            try:
                d = float(video['duration'])
                if d >= 3600:
                    dur = f"{int(d//3600)}:{int((d%3600)//60):02d}:{int(d%60):02d}"
                else:
                    dur = f"{int(d//60)}:{int(d%60):02d}"
            except:
                dur = ""
        if dur:
            dur_lbl = QLabel(dur)
            dur_lbl.setObjectName("durationLabel")
            dur_lbl.setStyleSheet("border: none; background: transparent; padding-right: 4px;")
            l.addWidget(dur_lbl)
        
        # Open on YouTube button
        yt_btn = QPushButton("")
        yt_btn.setObjectName("iconBtn")
        yt_btn.setToolTip("Open on YouTube")
        yt_btn.setFixedSize(28, 28)
        yt_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 13px;")
        vid_id = video.get('id', '')
        yt_btn.clicked.connect(lambda checked=False, vid=vid_id: __import__('webbrowser').open(f'https://www.youtube.com/watch?v={vid}'))
        l.addWidget(yt_btn)
        
        placeholder.setProperty("has_ui", True)

    def clear_result_ui(self, placeholder):
        video = placeholder.property("video")
        if video and 'id' in video and video['id'] in self._thumbnail_labels:
            try:
                del self._thumbnail_labels[video['id']]
            except KeyError:
                pass
            
        layout = placeholder.layout()
        if layout:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            placeholder.setLayout(None)
            layout.deleteLater()
            
        placeholder.setProperty("has_ui", False)

    def lazy_load_visible_results(self):
        if not self.search_results or not hasattr(self, 'results_area'):
            return
            
        scrollbar = self.results_area.verticalScrollBar()
        scroll_val = scrollbar.value()
        viewport_height = self.results_area.viewport().height()
        
        # Buffer of 200px to ensure smooth scrolling
        buffer = 200
        load_top = scroll_val - buffer
        load_bottom = scroll_val + viewport_height + buffer
        
        queue_ids = {q['video']['id'] for q in self.queue_items if 'video' in q and 'id' in q['video']}
        
        for i in range(self.results_vbox.count()):
            layout_item = self.results_vbox.itemAt(i)
            if layout_item and layout_item.widget():
                placeholder = layout_item.widget()
                video = placeholder.property("video")
                if not video:
                    continue
                    
                y = placeholder.y()
                h = placeholder.height()
                
                is_visible = (y + h >= load_top and y <= load_bottom)
                has_ui = placeholder.property("has_ui")
                
                if is_visible:
                    if not has_ui:
                        self.build_result_ui(placeholder, video, queue_ids)
                else:
                    if has_ui:
                        self.clear_result_ui(placeholder)

    def build_queue_item_ui(self, placeholder, q, idx):
        l = QHBoxLayout(placeholder)
        l.setContentsMargins(5,5,5,5)
        
        st = "\uE73E " if q['status'] == "Finished" else ("\uE896 " if q['status'] == "Downloading" else "")
        t = q['video'].get('title', 'Unknown')
        if len(t) > 40: t = t[:37] + "..."
        import html
        t_escaped = html.escape(t)
        
        lbl = QLabel(f"<span style='font-family: \"Segoe MDL2 Assets\";'>{st}</span> {t_escaped}")
        l.addWidget(lbl, 1)
        
        rm_btn = QPushButton("\uE711")
        rm_btn.setObjectName("iconBtn")
        rm_btn.setToolTip("Remove from queue")
        rm_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 14px;")
        rm_btn.setFixedSize(26, 26)
        rm_btn.clicked.connect(lambda checked=False, i=idx: self.remove_from_queue(i))
        l.addWidget(rm_btn)
        
        placeholder.setObjectName("queueItemFinished" if q['status'] == "Finished" else "queueItemPending")
        placeholder.style().unpolish(placeholder)
        placeholder.style().polish(placeholder)
        
        placeholder.setProperty("has_ui", True)

    def _on_queue_status_changed(self, idx):
        """Update only the status icon/color of a single queue item in-place, no full rebuild."""
        if idx >= len(self.queue_items) or idx >= self.queue_vbox.count():
            return
        layout_item = self.queue_vbox.itemAt(idx)
        if not layout_item or not layout_item.widget():
            return
        placeholder = layout_item.widget()
        q = self.queue_items[idx]
        # Keep the stored property up to date
        placeholder.setProperty("queue_item", q)
        # If widget is already rendered, patch its label in-place
        if placeholder.property("has_ui"):
            labels = placeholder.findChildren(QLabel)
            if labels:
                st = "\uE73E " if q['status'] == "Finished" else ("\uE896 " if q['status'] == "Downloading" else "")
                t = q['video'].get('title', 'Unknown')
                if len(t) > 40: t = t[:37] + "..."
                import html
                labels[0].setText(f"<span style='font-family: \"Segoe MDL2 Assets\";'>{st}</span> {html.escape(t)}")
            new_name = "queueItemFinished" if q['status'] == "Finished" else "queueItemPending"
            if placeholder.objectName() != new_name:
                placeholder.setObjectName(new_name)
                placeholder.style().unpolish(placeholder)
                placeholder.style().polish(placeholder)

    def clear_queue_item_ui(self, placeholder):
        layout = placeholder.layout()
        if layout:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            placeholder.setLayout(None)
            layout.deleteLater()
        placeholder.setProperty("has_ui", False)

    def lazy_load_visible_queue(self):
        if not self.queue_items or not hasattr(self, 'queue_area'):
            return
            
        scrollbar = self.queue_area.verticalScrollBar()
        scroll_val = scrollbar.value()
        viewport_height = self.queue_area.viewport().height()
        
        buffer = 200
        load_top = scroll_val - buffer
        load_bottom = scroll_val + viewport_height + buffer
        
        for i in range(self.queue_vbox.count()):
            layout_item = self.queue_vbox.itemAt(i)
            if layout_item and layout_item.widget():
                placeholder = layout_item.widget()
                q = placeholder.property("queue_item")
                idx = placeholder.property("queue_index")
                if q is None or idx is None:
                    continue
                    
                y = placeholder.y()
                h = placeholder.height()
                
                is_visible = (y + h >= load_top and y <= load_bottom)
                has_ui = placeholder.property("has_ui")
                
                if is_visible:
                    if not has_ui:
                        self.build_queue_item_ui(placeholder, q, idx)
                else:
                    if has_ui:
                        self.clear_queue_item_ui(placeholder)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.lazy_load_visible_results)
        QTimer.singleShot(0, self.lazy_load_visible_queue)

    def _refresh_queue_display(self):
        while self.queue_vbox.count():
            item = self.queue_vbox.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        self.queue_label.setText(f"Download Queue ({len(self.queue_items)})")
        
        for idx, q in enumerate(self.queue_items):
            placeholder = QWidget()
            placeholder.setFixedHeight(36)
            placeholder.setProperty("queue_item", q)
            placeholder.setProperty("queue_index", idx)
            placeholder.setProperty("has_ui", False)
            self.queue_vbox.addWidget(placeholder)
            
        QTimer.singleShot(0, self.lazy_load_visible_queue)
            
        # Synchronize search result checkboxes with current queue state in a highly-optimized manner
        queue_ids = {q['video']['id'] for q in self.queue_items if 'video' in q and 'id' in q['video']}
        for i in range(self.results_vbox.count()):
            layout_item = self.results_vbox.itemAt(i)
            if layout_item and layout_item.widget():
                widget = layout_item.widget()
                checkboxes = widget.findChildren(QCheckBox)
                for cb in checkboxes:
                    vid_id = cb.property("video_id")
                    if vid_id:
                        cb.blockSignals(True)
                        cb.setChecked(vid_id in queue_ids)
                        cb.blockSignals(False)
                        
        self.update_queue_all_checkbox_state()

    def remove_from_queue(self, idx):
        if idx < len(self.queue_items):
            self.queue_items.pop(idx)
            self.queue_update_signal.emit()

    def clear_completed(self, checked=False):
        has_finished = any(q['status'] == "Finished" for q in self.queue_items)
        if has_finished:
            # Default: remove only finished items
            self.queue_items = [q for q in self.queue_items if q['status'] != "Finished"]
        else:
            # No finished items — remove all pending (un-downloaded) items
            self.queue_items = [q for q in self.queue_items if q['status'] not in ("Pending",)]
        # Defer the expensive layout rebuild to avoid UI freeze while download thread is active
        QTimer.singleShot(0, self._refresh_queue_display)

    def cancel_batch_download(self, checked=False):
        self.cancel_download = True
        self.cancel_btn.setText("Cancelling...")
        self.cancel_btn.setEnabled(False)

    def start_batch_download(self):
        if self.is_downloading: return
        pending = [q for q in self.queue_items if q['status'] == "Pending"]
        if not pending: return

        self.is_downloading = True
        self.cancel_download = False
        self._batch_total_count = len(pending)
        self.dl_btn.setEnabled(False)
        self.dl_btn.setText("Downloading...")
        self.cancel_btn.setText("Cancel")
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setVisible(True)
        self.save_config()
        # Everything read from a widget is read here, on the GUI thread. Qt
        # objects belong to the thread that created them, and reading the
        # settings once also stops a mid-batch change of format, bitrate or
        # folder from splitting one queue across two different targets.
        folder = self.path_combo.currentText()
        target_format = self.format_combo.currentText().lower()
        audio_quality = str(self.bitrate_combo.currentText())
        ffmpeg_location = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable)) if getattr(sys, 'frozen', False) else None
        extra_args = shlex.split(self.custom_args) if (getattr(self, 'use_custom_args', False) and getattr(self, 'custom_args', '')) else []

        def bg_download():
            try:
                _run_batch()
            except Exception as e:
                # Nothing here may end a batch without a final status line:
                # that line is what re-enables the Download button, so one
                # unhandled error used to leave the queue stuck on
                # "Downloading..." with the rest of the list never attempted.
                print(f"Batch download error: {e}")
                self.status_signal.emit(f"Batch complete (stopped early: {e}).", False, "#E31E24")

        def _run_batch():
            import time
            from concurrent.futures.thread import ThreadPoolExecutor  # see the note at the top

            with self.active_downloads_lock:
                self.active_downloads.clear()

            threads_count = max(1, int(getattr(self, 'download_threads', 3)))
            downloaded_filepaths = []
            downloaded_lock = threading.Lock()
            # id(queue item) -> the file that item produced. Kept out of the
            # queue dicts so the verification pass can check each track on its
            # own instead of guessing from counts.
            produced_files = {}
            # Two queue entries can be different videos that share a title, and
            # yt-dlp names its output after the title. Left alone, two threads
            # write the same .part file at the same moment and one of them
            # fails or writes garbage - which is why the skipping used to get
            # worse with every extra thread. Same-title tracks are downloaded
            # one at a time instead.
            title_locks = {}
            title_locks_guard = threading.Lock()
            start_slot_guard = threading.Lock()
            start_slot = [0]

            def title_lock_for(title):
                key = _title_match_key(title) or title
                with title_locks_guard:
                    lock = title_locks.get(key)
                    if lock is None:
                        lock = threading.Lock()
                        title_locks[key] = lock
                    return lock

            def reset_start_slots():
                with start_slot_guard:
                    start_slot[0] = 0

            def take_start_slot():
                with start_slot_guard:
                    slot = start_slot[0]
                    start_slot[0] += 1
                return slot

            def repaint(q):
                """Repaint one queue row, looking up where that item is now.

                The index a worker was handed goes stale the moment the queue is
                reordered or something is taken out of it, and painting the wrong
                row is part of how a finished track kept showing as pending.
                """
                for i, item in enumerate(getattr(self, 'queue_items', [])):
                    if item is q:
                        self.queue_status_changed_signal.emit(i)
                        return

            def find_downloaded_file(title, not_before=0.0):
                """Find the file a successful yt-dlp run left behind, by its title."""
                try:
                    entries = list(os.scandir(folder))
                except OSError:
                    return None
                best = None
                for entry in entries:
                    try:
                        if not entry.is_file():
                            continue
                        if not _title_matches_filename(title, entry.name):
                            continue
                        info = entry.stat()
                    except OSError:
                        continue
                    if info.st_size <= 1024 or info.st_mtime < not_before - 5:
                        continue
                    if best is None or info.st_mtime > best[1]:
                        best = (entry.path, info.st_mtime)
                return best[0] if best else None

            def download_single(item):
                _, q = item
                vid_id = q['video'].get('id', '')
                if not vid_id: return
                title = q['video'].get('title', '') or ''
                q.pop('permanent_failure', None)
                if getattr(self, 'cancel_download', False):
                    q['status'] = "Pending"
                    repaint(q)
                    return
                q['status'] = "Downloading"
                repaint(q)

                # The options the Python API used, written as yt-dlp CLI flags.
                cli_args = [
                    "--newline",
                    "--format", "bestaudio/best",
                    "--extract-audio",
                    "--audio-format", target_format,
                    "--audio-quality", audio_quality,
                    "--retries", "15",
                    "--fragment-retries", "15",
                    "--file-access-retries", "10",
                    "--output", f"{folder}/%(title)s.%(ext)s",
                ]
                if ffmpeg_location:
                    cli_args.extend(["--ffmpeg-location", ffmpeg_location])
                if extra_args:
                    # Appended last, so the advanced field wins over the GUI picks
                    # exactly like the Settings dialog says it should.
                    cli_args.extend(extra_args)
                # The track itself: yt-dlp takes URLs positionally, so it goes
                # after every option. Without it yt-dlp exits with
                # "You must provide at least one URL" and nothing downloads.
                cli_args.append(f"https://www.youtube.com/watch?v={vid_id}")

                # Stagger the first starts of a pass. Every thread asking
                # YouTube for a stream in the same instant is what gets the
                # requests throttled, and a throttled request is what used to
                # come back as a song that "skipped".
                slot = take_start_slot()
                if slot > 0:
                    time.sleep(min(0.4 * slot, 2.0))

                downloaded_file = None
                failure = None
                with title_lock_for(title):
                    for attempt in range(1, DOWNLOAD_ITEM_ATTEMPTS + 1):
                        if getattr(self, 'cancel_download', False):
                            break
                        attempt_started = time.time()
                        failure = None
                        try:
                            downloaded_file = run_yt_dlp_download(
                                cli_args,
                                progress_cb=lambda pct: self._dl_progress_percent(vid_id, pct),
                                cancelled_cb=lambda: getattr(self, 'cancel_download', False),
                            )
                            # run_yt_dlp_download raises for anything that truly
                            # failed, so getting here means the track is on
                            # disk. Only its name is uncertain.
                            if not downloaded_file or not os.path.isfile(downloaded_file):
                                downloaded_file = find_downloaded_file(title, attempt_started)
                            break
                        except Exception as e:
                            failure = str(e)
                            downloaded_file = None
                            print(f"Download attempt {attempt}/{DOWNLOAD_ITEM_ATTEMPTS} failed for {vid_id}: {failure}")
                            if getattr(self, 'cancel_download', False):
                                break
                            if _is_permanent_download_error(failure):
                                # The video itself is gone, so a later pass of
                                # the queue would only fail it all over again.
                                q['permanent_failure'] = True
                                break
                            if attempt < DOWNLOAD_ITEM_ATTEMPTS:
                                time.sleep(min(2.0 * attempt, 8.0))

                with self.active_downloads_lock:
                    if vid_id in self.active_downloads:
                        del self.active_downloads[vid_id]

                # A clean yt-dlp exit means the track downloaded, even when no
                # usable path came out of its output. Treating "no path" as a
                # failure is what turned finished downloads into skipped songs.
                if failure is None:
                    if downloaded_file:
                        _add_placeholder_tag(downloaded_file)
                        with downloaded_lock:
                            downloaded_filepaths.append(downloaded_file)
                        produced_files[id(q)] = downloaded_file
                    q['status'] = "Finished"
                else:
                    q['status'] = "Pending"

                if getattr(self, 'cancel_download', False):
                    q['status'] = "Pending"
                repaint(q)

                finished_cnt = len([item_q for item_q in getattr(self, 'queue_items', []) if item_q.get('status') == "Finished"])
                total_cnt = getattr(self, '_batch_total_count', len(getattr(self, 'queue_items', [])))
                prog_prefix = f"({finished_cnt}/{total_cnt}) " if total_cnt > 0 else ""
                with self.active_downloads_lock:
                    if self.active_downloads:
                        vals = list(self.active_downloads.values())
                        if len(vals) > 5:
                            self.dl_progress_signal.emit(f"{prog_prefix}Downloading: {', '.join(vals[:5])} (+{len(vals)-5} more)")
                        else:
                            self.dl_progress_signal.emit(f"{prog_prefix}Downloading: {', '.join(vals)}")
                    else:
                        self.dl_progress_signal.emit(f"{prog_prefix}Processing...")

            max_passes = 4
            for pass_num in range(1, max_passes + 1):
                # Always check UP (from top / index 0) for undownloaded tracks before checking down
                pending_items = sorted(
                    [(idx, q) for idx, q in enumerate(self.queue_items)
                     if q['status'] == "Pending" and not q.get('permanent_failure')],
                    key=lambda x: x[0]
                )
                if not pending_items or getattr(self, 'cancel_download', False):
                    break

                if pass_num > 1:
                    self.status_signal.emit(
                        f"Re-checking queue (Pass {pass_num}: retrying {len(pending_items)} pending downloads)...",
                        False, "#FF8C00"
                    )
                    time.sleep(min(1.5 * pass_num, 8.0))

                max_workers = min(threads_count, len(pending_items))
                reset_start_slots()
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = []
                    for item in pending_items:
                        if getattr(self, 'cancel_download', False):
                            break
                        futures.append(executor.submit(download_single, item))
                    for fut in futures:
                        try:
                            fut.result()
                        except Exception as e:
                            # One track blowing up must not take the rest of the
                            # queue down with it.
                            print(f"Unexpected error while downloading: {e}")

            # --- Verification Pass with Placeholder Tag & Title Matching ---
            if not getattr(self, 'cancel_download', False):
                # Check every finished track against the file it actually
                # produced. The old check compared a file count against a queue
                # count and matched raw titles against sanitized filenames, so
                # any title holding a ':' or a '/' looked missing and was
                # downloaded all over again for no reason.
                missing_items = []
                for idx, q in enumerate(list(self.queue_items)):
                    if q['status'] != "Finished":
                        continue
                    path = produced_files.get(id(q))
                    if path and os.path.isfile(path) and os.path.getsize(path) > 1024:
                        continue
                    path = find_downloaded_file(q['video'].get('title', ''))
                    if path:
                        produced_files[id(q)] = path
                        continue
                    q['status'] = "Pending"
                    missing_items.append((idx, q))
                    repaint(q)

                if missing_items:
                    missing_items.sort(key=lambda x: x[0])
                    self.status_signal.emit(
                        f"Verification: {len(missing_items)} files missing on disk. Redownloading missing tracks...",
                        False, "#FF8C00"
                    )
                    reset_start_slots()
                    with ThreadPoolExecutor(max_workers=min(threads_count, len(missing_items))) as executor:
                        futures = [executor.submit(download_single, item) for item in missing_items]
                        for fut in futures:
                            try:
                                fut.result()
                            except Exception as e:
                                print(f"Unexpected error while redownloading: {e}")

                # Strip placeholder verification tag from all confirmed files
                for f in list(dict.fromkeys(downloaded_filepaths + list(produced_files.values()))):
                    if os.path.exists(f):
                        _remove_placeholder_tag(f)

            self._last_downloaded_files = list(dict.fromkeys(
                downloaded_filepaths + [p for p in produced_files.values() if p]
            ))

            if getattr(self, 'cancel_download', False):
                self.status_signal.emit("Download cancelled.", False, "#E31E24")
            else:
                remaining = [q for q in self.queue_items if q['status'] == "Pending"]
                if remaining:
                    unavailable = len([q for q in remaining if q.get('permanent_failure')])
                    if unavailable:
                        self.status_signal.emit(
                            f"Batch completed ({len(remaining)} failed, {unavailable} unavailable).",
                            False, "#FF8C00"
                        )
                    else:
                        self.status_signal.emit(f"Batch completed ({len(remaining)} failed).", False, "#FF8C00")
                else:
                    self.status_signal.emit("Batch complete!", False, "#1abd33")

        threading.Thread(target=bg_download, daemon=True).start()
        
    def _on_batch_complete(self):
        self.is_downloading = False
        self.cancel_download = False
        self.dl_btn.setEnabled(True)
        self.dl_btn.setText("Download All")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.setText("Cancel")
        self.cancel_btn.setEnabled(True)
        if hasattr(self, 'run_renamer_cb') and self.run_renamer_cb.isChecked():
            self.run_mp3_renamer()
        if getattr(self, 'run_custom_script', False):
            self._run_custom_post_download_script()

    def copy_download_path_to_clipboard(self):
        path = self.path_combo.currentText()
        if path:
            QApplication.clipboard().setText(path)
            self._on_status_update(f"Copied download path to clipboard: {path}", False, "#3B8ED0")

    def on_run_renamer_toggled(self, checked):
        self.run_renamer = checked
        self.save_config()

    def on_path_changed(self, path):
        self.download_path = path
        self.save_config()

    def run_mp3_renamer(self):
        """Launches the integrated MP3 renamer interactive CLI in a new console window."""
        folder = self.path_combo.currentText()
        if not folder or not os.path.exists(folder):
            self._on_status_update("Renamer: Download folder path does not exist.", False, "red")
            return

        # The renamer is an interactive console program: it prints a banner and
        # colours and asks questions with input(). Packaged, the exe is windowed
        # and has no console of its own, so the renamer runs as a second copy of
        # this same exe with --renamer: the launcher inside the exe sees that
        # flag, allocates a console window for the copy and runs the CLI in it.
        # Run from source, it is this file re-run under python.exe with
        # --renamer: never pythonw.exe, which has no console to print into.
        if getattr(sys, 'frozen', False):
            args = [sys.executable, "--renamer", folder]
        else:
            args = [self._console_python(), os.path.abspath(__file__), "--renamer", folder]

        args.append(f'--norm={self.normalization_mode}')
        if self.auto_rename:
            args.append('--auto')
        args.append(f'--silence-pad={str(self.silence_pad_dur)}')
        args.append(f'--norm-threads={self.normalization_threads}')
        args.append(f'--silence-trim={"on" if self.silence_trim else "off"}')
        if self.use_custom_norm_cmd and self.custom_norm_cmd.strip():
            args.append(f'--custom-norm-cmd={self.custom_norm_cmd.strip()}')

        try:
            creationflags = 0x00000010 if sys.platform == "win32" else 0
            proc = subprocess.Popen(args, creationflags=creationflags)
            self._on_status_update("Launched MP3 Renamer in a new console window.", False, "#1abd33")

            def _wait_renamer():
                proc.wait()
                self.renamer_finished_signal.emit()

            threading.Thread(target=_wait_renamer, daemon=True).start()
        except Exception as e:
            self._on_status_update(f"Failed to launch MP3 Renamer: {str(e)}", False, "red")

    def _console_python(self):
        """Return a console-capable python executable (python.exe) so scripts can print/interact."""
        exe = sys.executable
        if getattr(sys, 'frozen', False):
            return "python"
        idx = exe.lower().rfind("pythonw")
        if idx != -1:
            exe = exe[:idx] + "python" + exe[idx + 7:]
        return exe

    def _run_custom_post_download_script(self):
        """Run the user-chosen file after a download batch finishes.
        Supports .py, .exe, .bat/.cmd, .ps1, and any file type Windows can open.
        The file receives the download folder as its first argument (when available),
        followed by the path of each downloaded file."""
        script = getattr(self, 'custom_script_path', '').strip()
        if not script:
            return
        if not os.path.isfile(script):
            self._on_status_update(f"Custom script not found: {script}", False, "#E31E24")
            return

        script = os.path.abspath(script)
        ext = os.path.splitext(script)[1].lower()
        folder = self.path_combo.currentText() if hasattr(self, 'path_combo') else ""
        if not folder or not os.path.isdir(folder):
            folder = ""
        files = [f for f in getattr(self, '_last_downloaded_files', []) if os.path.exists(f)]
        payload = ([folder] if folder else []) + files
        cwd = folder or os.path.dirname(script)

        interp_map = {
            '.py': [self._console_python()],
            '.bat': ['cmd.exe', '/c'],
            '.cmd': ['cmd.exe', '/c'],
            '.ps1': ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File'],
        }

        try:
            if ext in interp_map:
                cmd = interp_map[ext] + [script] + payload
                flags = 0x00000010 if sys.platform == "win32" else 0  # CREATE_NEW_CONSOLE
                subprocess.Popen(cmd, cwd=cwd, creationflags=flags)
            elif ext == '.exe':
                subprocess.Popen([script] + payload, cwd=cwd)
            else:
                # Unknown type: let Windows resolve it through its file associations.
                quoted = ' '.join(f'"{a}"' for a in payload)
                subprocess.Popen(f'"{script}" {quoted}'.strip(), shell=True, cwd=cwd)
            self._on_status_update(f"Ran custom script: {os.path.basename(script)}", False, "#1abd33")
        except Exception as e:
            self._on_status_update(f"Failed to run custom script: {e}", False, "#E31E24")

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Download Folder", self.path_combo.currentText() or "")
        if folder:
            if folder not in self.recent_folders:
                self.recent_folders.insert(0, folder)
                self.recent_folders = self.recent_folders[:5]
                self.path_combo.clear()
                self.path_combo.addItems(self.recent_folders)
            self.path_combo.setCurrentText(folder)
            self.save_config()

    def open_current_download_folder(self):
        path = self.path_combo.currentText()
        if path and os.path.exists(path):
            os.startfile(path)
        else:
            self._on_status_update("Download folder path does not exist.", False, "red")

    def open_current_local_folder(self):
        path = self.local_path_combo.currentText()
        if path and os.path.exists(path):
            os.startfile(path)
        else:
            self._on_status_update("Local folder path does not exist.", False, "red")

    def _dl_progress_percent(self, vid_id, percent):
        """Push one yt-dlp percentage onto the queue progress line."""
        if not vid_id or not percent:
            return

        finished_cnt = len([q for q in getattr(self, 'queue_items', []) if q.get('status') == "Finished"])
        total_cnt = getattr(self, '_batch_total_count', len(getattr(self, 'queue_items', [])))
        prog_prefix = f"({finished_cnt}/{total_cnt}) " if total_cnt > 0 else ""

        with self.active_downloads_lock:
            self.active_downloads[vid_id] = percent
            vals = list(self.active_downloads.values())
            if len(vals) > 5:
                self.dl_progress_signal.emit(f"{prog_prefix}Downloading: {', '.join(vals[:5])} (+{len(vals)-5} more)")
            else:
                self.dl_progress_signal.emit(f"{prog_prefix}Downloading: {', '.join(vals)}")

    # --- Player Logic ---
    def _on_status_update(self, text, is_playing, color):
        if is_playing:
            self.playing_label.setText(text)
        else:
            self.status_label.setText(f"   |   {text}" if self.playing_label.text() else text)
            if color == "white":
                self.status_label.setStyleSheet("font-size: 11px; margin-top: -2px;")
            else:
                self.status_label.setStyleSheet(f"color: {color}; font-size: 11px; margin-top: -2px;")
        if "Batch complete" in text:
            self.dl_progress_signal.emit("")
            self._on_batch_complete()

    # ------------------------------------------------------------------
    # Next-track prefetch (section 8 of the AI Readme)
    # ------------------------------------------------------------------
    # Once the current track has PREFETCH_SECONDS_BEFORE_END seconds left, the track
    # that comes after it is resolved with yt-dlp on its own thread and its stream
    # URL is held ready. The GUI thread only decides which track that is; everything
    # slow happens in the prefetch thread, so the track playing now keeps playing
    # untouched. play_result() then finds the URL already there.

    def _playback_source_items(self):
        """(the list playback is stepping through, is it the local pane)."""
        if getattr(self, 'current_video_id', None) == "local":
            items = [x for x in getattr(self, 'current_local_items', []) if x.get('is_dir') is False]
            return items, True
        return (self.search_results or []), False

    def _next_playback_preview(self):
        """(index, video) for the track that would play next, changing nothing.

        This mirrors play_next()'s rules - local or searched, shuffled or in order -
        but mutates no state. With shuffle on, the random pick is made here and
        remembered in _prefetch_decision, because the prefetch has to fetch the same
        track the player will actually advance to. None means nothing follows.
        """
        items, is_local = self._playback_source_items()
        if not items:
            return None
        current_idx = getattr(self, 'local_playback_index', -1) if is_local else self.playback_index
        if getattr(self, 'is_shuffled', False):
            history = list(getattr(self, 'shuffle_history', []))
            unplayed = [i for i in range(len(items)) if i not in history]
            if not unplayed:
                unplayed = [i for i in range(len(items)) if i != current_idx]
            if not unplayed:
                return None
            next_idx = random.choice(unplayed)
        else:
            next_idx = current_idx + 1
            if not (0 <= next_idx < len(items)):
                return None
        video = items[next_idx]
        if not isinstance(video, dict):
            return None
        return next_idx, video

    def _prefetch_decision_for(self, vid_id):
        """(next index, next video) decided seconds ago for this track, or None if stale."""
        decision = getattr(self, '_prefetch_decision', None)
        if decision and vid_id and decision[0] == vid_id:
            return decision[1], decision[2]
        return None

    def _take_prefetched_stream(self, vid_id):
        """The stream URL resolved ahead of time for this track, consumed once, as
        (url, user agent, how old the URL already was in seconds). The age comes along because
        reading a URL ahead spends that much of its life before the player ever sees it, and
        the stream-liveness watchdog counts a loaded stream from when its URL was resolved.
        """
        with self._prefetch_lock:
            entry = self._prefetched_streams.pop(vid_id, None)
        if not entry:
            return None
        url, user_agent, resolved_at = entry
        age = time.monotonic() - resolved_at
        # A wall-clock stamp would be wrong whenever Windows corrects the clock, so the
        # age is measured with the monotonic clock - the same clock the stamp was taken
        # from in _prefetch_stream_worker().
        if age > PREFETCH_URL_MAX_AGE:
            return None
        return url, user_agent, age

    def _maybe_prefetch_next_track(self):
        """Called from the player timer once the current track is nearing its end.

        Everything done here is cheap: one preview, one remembered decision, and the
        start of a thread. The yt-dlp call itself never runs on the GUI thread.
        """
        if not getattr(self, 'search_results', None):
            return
        # Local files need no resolving, and a track that will not be followed
        # automatically needs nothing ready.
        if getattr(self, 'current_video_id', None) in (None, "", "local"):
            return
        if getattr(self, 'stop_after_current', STOP_AFTER_OFF):
            return
        current_id = self.current_video_id
        # One decision per track: the player timer fires every 16 ms and must not
        # re-decide (or re-fetch) the same track sixty times a second.
        if getattr(self, '_prefetch_trigger_key', None) == current_id:
            return
        preview = self._next_playback_preview()
        self._prefetch_trigger_key = current_id
        if not preview:
            self._prefetch_decision = None
            return
        next_idx, video = preview
        self._prefetch_decision = (current_id, next_idx, video)
        next_id = video.get('id')
        if not next_id:
            return
        with self._prefetch_lock:
            if next_id in self._prefetch_busy or next_id in self._prefetched_streams:
                return
            self._prefetch_busy.add(next_id)
        threading.Thread(target=self._prefetch_stream_worker, args=(next_id,), daemon=True).start()

    def _prefetch_stream_worker(self, vid_id):
        """Resolve one stream URL off the GUI thread. Failures stay silent: the normal
        play path resolves that track again when it is actually started."""
        try:
            url, user_agent = resolve_stream_url(vid_id)
            resolved = (url, user_agent, time.monotonic())
        except Exception:
            resolved = None
        finally:
            with self._prefetch_lock:
                self._prefetch_busy.discard(vid_id)
        if not resolved:
            return
        with self._prefetch_lock:
            self._prefetched_streams[vid_id] = resolved
            while len(self._prefetched_streams) > PREFETCH_CACHE_LIMIT:
                oldest = min(self._prefetched_streams, key=lambda k: self._prefetched_streams[k][2])
                self._prefetched_streams.pop(oldest, None)

    def invalidate_next_track_prefetch(self):
        """Forget a decided successor and any URL already resolved for it, so an
        outdated successor cannot be played as though it came from the new list."""
        self._prefetch_decision = None
        self._prefetch_trigger_key = None
        with self._prefetch_lock:
            self._prefetched_streams.clear()

    # ------------------------------------------------------------------
    # Keeping one track playing - a stream URL that stops answering
    # ------------------------------------------------------------------
    # The constants above STREAM_STALL_SECONDS explain why this exists. The rule the whole
    # block follows: only the media is replaced, never the track. Everything the listener is
    # relying on - the highlighted row, playback_index, shuffle_history, the stop-after state,
    # the decided successor - stays exactly where it is, and only the URL libVLC is reading is
    # swapped for a freshly resolved one of the same video.

    def _note_loaded_stream(self, vid_id, url=None, user_agent=None, url_age=0.0,
                            keep_pending_seek=False):
        """Record what the player has just been handed, and start the watchdog over.

        Called by the two paths that put media on the player: play_result()'s fetch thread,
        with the URL it resolved and how old that URL already was (one read ahead of the play
        by the prefetch thread is that much of the URL's life already spent), and
        _on_local_click(), with no id at all - which is how a file says "there is nothing here
        that can expire". keep_pending_seek is the refresh path's exception: a re-resolve has
        already decided where the listener should end up, and that has to survive the reset.
        """
        self._loaded_stream = (vid_id, url, user_agent, url_age) if vid_id and vid_id != "local" else None
        self._loaded_stream_at = time.monotonic() if self._loaded_stream else None
        self._stream_seen_ms = -1
        # None rather than "now": the stall clock for a fresh media starts the first time the
        # player actually reports Playing, so a stream that takes a while to open is not
        # judged for taking a while to open.
        self._stream_moved_at = None
        self._stream_dead = False
        self._stream_refetch_attempts = 0
        # Whether anybody has heard this particular media advancing. A refresh of a stream that
        # gave out mid-listen is the same listening carried onto new media, so it carries over;
        # anything else - including the track the session restore preloads paused at start up -
        # has not been listened to at all yet, and is not a stream that can have gone idle.
        # _stream_needs_renew uses this to keep age from reloading a track nobody has played.
        self._stream_listened = bool(keep_pending_seek and getattr(self, '_stream_listened', False))
        if not keep_pending_seek:
            self._pending_stream_seek_frac = None
            self._pending_stream_seek_ms = None
            self._pending_stream_pause = False
            self._pending_stream_seek_at = None
            self._stream_renew_started_at = None  # a different track starts with a clean allowance

    def _loaded_stream_age(self):
        """How long ago the URL the media on the player was built from was resolved."""
        stream = getattr(self, '_loaded_stream', None)
        started = getattr(self, '_loaded_stream_at', None)
        if not stream or started is None:
            return 0.0
        return (time.monotonic() - started) + float(stream[3] or 0.0)

    def _stream_is_moving(self):
        """Whether libVLC reported a position that was moving, recently.

        A stream that is measurably advancing is a stream that is working, whatever its age:
        a URL forty minutes old carrying a long mix is not swapped out from under somebody who
        is listening to it without a single problem.
        """
        moved_at = getattr(self, '_stream_moved_at', None)
        return moved_at is not None and (time.monotonic() - moved_at) <= STREAM_STALL_SECONDS

    def _stream_is_switching(self):
        """True while the player is already being handed something else: a track still being
        fetched, or a dead stream already being re-resolved. Nothing in this block acts during
        either, because the media still on the player belongs to the previous track and acting
        on it would hijack a fetch the user started."""
        return bool(getattr(self, '_is_loading_stream', False) or getattr(self, '_stream_refetching', False))

    def _stream_needs_renew(self):
        """Whether the stream on the player should be re-resolved before it is asked for anything.

        Two answers are yes: it was noticed dead - a position that stopped moving, or
        vlc.State.Error - and it is a stream the listener has actually been hearing whose URL has
        outlived STREAM_URL_MAX_AGE while the player is not advancing on it, which is the track
        left running into a link that has since died, or left idle on the player for longer than
        a YouTube URL lasts. Never for a local file, and never while a fetch or a refresh is
        already under way.

        The age of the URL only means something for a stream that has been listened to and has
        then stopped. A track preloaded at start up by the session restore, or one paused within
        the life of its URL, is media nobody is currently hearing: its URL grows old on the
        player without anything going wrong, and re-resolving it there lands the listener back at
        the top of the track, which reads as the track restarting itself. What that track needs is
        the URL it already has being tried, and the watchdog noticing within a few seconds whether
        it still answers - the same rule that already leaves a working stream alone however old
        its URL is.
        """
        if not getattr(self, '_loaded_stream', None) or self._stream_is_switching():
            return False
        if getattr(self, '_stream_dead', False):
            return True
        if self._loaded_stream_age() <= STREAM_URL_MAX_AGE or self._stream_is_moving():
            return False
        return bool(getattr(self, '_stream_listened', False))

    def _mark_stream_dead(self):
        """Say once, in the status line, that the loaded stream has stopped delivering audio."""
        if getattr(self, '_stream_dead', False):
            return
        self._stream_dead = True
        title = (getattr(self, 'current_playing_title', '') or 'this track')
        if getattr(self, '_stream_refetch_attempts', 0) < STREAM_REFETCH_LIMIT:
            self._on_status_update(f"Stream stopped responding - reloading it: {title}", False, "#FF8C00")
        elif not getattr(self, 'is_playing', False):
            self._on_status_update(f"Stream stopped responding - Play will reload it: {title}", False, "#FF8C00")
        else:
            self._on_status_update(
                f"Stream stopped responding and would not reload - pick the track to start it again: {title}",
                False, "#E31E24")

    def _watch_stream_liveness(self, state, ms):
        """Run the loaded stream through the watchdog, once per player-timer tick.

        libVLC never reports "this URL died". A stream that stops answering either falls to
        vlc.State.Error or goes on claiming Playing with a position that has stopped moving,
        and those are the two things this can see. A position that moves is remembered, and if
        the stream had been marked dead it clears that and its allowance of self-healing
        attempts - a stream that dropped for a moment is not punished for it. A position that
        does not move while the app wants the track playing is a dead stream: a pause is a
        still position by request, so it is not a stall. A dead stream the listener never asked
        to stop is reloaded on its own.
        """
        if not getattr(self, '_loaded_stream', None) or self._stream_is_switching():
            return
        if state == vlc.State.Error:
            self._mark_stream_dead()
            self._recover_stream_if_possible()
            return
        if state != vlc.State.Playing:
            return
        if getattr(self, '_stream_moved_at', None) is None:
            self._stream_moved_at = time.monotonic()  # first tick this media has been worth watching
        if ms is not None and ms != getattr(self, '_stream_seen_ms', -1):
            self._stream_seen_ms = ms
            self._stream_moved_at = time.monotonic()
            if getattr(self, 'is_playing', False) and int(ms or 0) > 0:
                # Somebody is hearing this media: from here on it is a stream that can go idle on
                # the listener's hands, which is the only kind the age of its URL is a reason to
                # reload. A media that has merely been loaded and left paused never gets here.
                self._stream_listened = True
            if getattr(self, '_stream_dead', False):
                self._stream_dead = False
                self._stream_refetch_attempts = 0
            return
        if not getattr(self, 'is_playing', False) or getattr(self, '_stream_dead', False):
            return
        if (time.monotonic() - self._stream_moved_at) > STREAM_STALL_SECONDS:
            self._mark_stream_dead()
            self._recover_stream_if_possible()

    def _recover_stream_if_possible(self):
        """Reload a dead stream by itself, and only while the listener never asked it to stop.

        STREAM_REFETCH_LIMIT is what keeps a genuinely unplayable track - one yt-dlp can no
        longer resolve at all - from turning into a fetch that retries itself forever.
        """
        if not getattr(self, 'is_playing', False):
            return False
        if getattr(self, '_stream_refetch_attempts', 0) >= STREAM_REFETCH_LIMIT:
            return False
        return self._renew_loaded_stream()

    def _stream_ended_short(self, total_ms, ms):
        """Whether the media that just reported vlc.State.Ended was a stream that gave up
        before its own length, rather than a track that finished.

        An expired URL ends the media exactly the way the end of a track does, and the only
        thing telling them apart is where the position stopped: a real ending stops a second or
        two short of the reported length, a dead stream stops well short of it. A length the
        media never reported is treated as a finished track, because there is nothing it could
        be short of, and a local file is the whole file - it is never short.
        """
        if not getattr(self, '_loaded_stream', None):
            return False
        if not total_ms or total_ms <= 0:
            return False
        return (int(total_ms) - int(ms)) > STREAM_END_SLACK_MS

    def _renew_loaded_stream(self, force=False):
        """Resolve the track already on the player all over again, and hand libVLC fresh media
        for it.

        This is not the track started again. The position it stopped at - or the row the user
        scrubbed to, or the point a Play press was meant to resume from - is held until the new
        media answers and then applied by the player timer (see _apply_pending_stream_seek), so
        it reads as one long buffer rather than as the song starting over. Nothing else moves:
        playback_index, the row in the list, shuffle_history, the stop-after state and the
        next-track read-ahead are all left exactly as they were, and _pending_fetch_id is the
        same guard play_result() uses, so a track the user picks during the refresh wins the
        player. _ended_trigger is held up for the duration so the dying media cannot spend
        itself as an "ended" track and move the playlist on mid-swap.

        The yt-dlp call runs on its own thread exactly as play_result()'s bg_fetch does, and it
        is that thread - not the GUI thread - that calls set_media and play: the thread that
        fetches a stream is the one that owns handing it to the player, which is the exception
        the play path already makes to the rule that a background thread stays out of VLC (that
        rule is about the *prefetch* thread, which must not touch the player at all). Everything
        that touches a Qt widget goes through stream_refreshed_signal instead. Returns True when
        a refresh is running or has just been started. force is for the listener asking for it
        directly - a Play press - which is rate limited by a thumb rather than by a dragged seek
        bar, and so does not have to wait out the cooldown.
        """
        stream = getattr(self, '_loaded_stream', None)
        if not stream or not getattr(self, 'vlc_instance', None) or not getattr(self, 'vlc_player', None):
            return False
        if getattr(self, '_stream_refetching', False):
            return True  # one refresh in flight per dead stream; a second scrub only adds a position
        vid_id = stream[0]
        if getattr(self, '_stream_refetch_attempts', 0) >= STREAM_REFETCH_LIMIT:
            return False  # _mark_stream_dead has already said so in the status line
        last_try = getattr(self, '_stream_renew_started_at', None)
        if not force and last_try is not None and (time.monotonic() - last_try) < STREAM_RENEW_COOLDOWN:
            # One yt-dlp call per track per cooldown, and no more. A dead stream is worth
            # reloading, but a seek bar being dragged across it is a hundred sliderMoved
            # signals, and each one would otherwise start its own fetch.
            return False
        player = self.vlc_player
        try:
            hold_ms = max(int(player.get_time() or 0), 0)
        except Exception:
            hold_ms = 0
        if hold_ms == 0:
            # A stream that has given up stops reporting a position altogether, and taking that at
            # its word lands the listener back at the top of the track - which is what makes a
            # reload read as the track starting over. The last position this media did report is
            # where the listener actually was, so that is the position held for the fresh media.
            hold_ms = max(int(getattr(self, '_stream_seen_ms', -1) or 0), 0)
        # Where to land: a scrub the user just asked for beats whatever the dead media thinks
        # its own position is, and only one of the two is ever left pending.
        if hold_ms > 0 and getattr(self, '_pending_stream_seek_frac', None) is None:
            self._pending_stream_seek_ms = hold_ms
        self._pending_stream_pause = not bool(getattr(self, 'is_playing', False))
        self._pending_stream_seek_at = time.monotonic()
        self._stream_renew_started_at = time.monotonic()
        self._stream_refetch_attempts += 1
        self._stream_refetching = True
        self._pending_fetch_id = vid_id
        self._is_loading_stream = True
        self._ended_trigger = True
        title = (getattr(self, 'current_playing_title', '') or vid_id)
        self._on_status_update(f"Re-fetching stream: {title}...", False, "#3B8ED0")

        def bg_renew():
            try:
                url, user_agent = resolve_stream_url(vid_id)
            except Exception as e:
                print(f"Stream refresh error: {e}")
                self._stream_refetching = False
                if getattr(self, '_pending_fetch_id', None) == vid_id:
                    self._is_loading_stream = False
                self.stream_refreshed_signal.emit(False, title)
                return
            if getattr(self, '_pending_fetch_id', None) != vid_id:
                return  # another track was started during the refresh; that one owns the player now
            media = self.vlc_instance.media_new(url)
            media.add_option(f':http-user-agent={user_agent}')
            self.vlc_player.set_media(media)
            self.vlc_player.play()
            self._note_loaded_stream(vid_id, url, user_agent, 0.0, keep_pending_seek=True)
            self._stream_refetching = False
            self._is_loading_stream = False
            self.stream_refreshed_signal.emit(True, title)
        threading.Thread(target=bg_renew, daemon=True).start()
        return True

    def _apply_pending_stream_seek(self):
        """Put the listener where they were - or where they asked to be - on freshly resolved media.

        Neither a restored position nor a scrubbed-to one can be set on a media that has not
        opened yet: libVLC says nothing about a stream it has not read, and that is the other
        half of why a dead stream looked unresponsive. Both wait here until the player reports
        Playing, then are applied once. A scrub is held as a fraction of the track for the same
        reason - a media that is not open again reports no length to turn it into milliseconds.
        A request nothing accepted within STREAM_SEEK_RESTORE_TIMEOUT seconds is dropped rather
        than left to pounce on the track minutes later.
        """
        player = getattr(self, 'vlc_player', None)
        if player is None:
            return
        asked_frac = getattr(self, '_pending_stream_seek_frac', None)
        asked_ms = getattr(self, '_pending_stream_seek_ms', None)
        asked_pause = bool(getattr(self, '_pending_stream_pause', False))
        if asked_frac is None and asked_ms is None and not asked_pause:
            return
        started_at = getattr(self, '_pending_stream_seek_at', None)
        if started_at is not None and (time.monotonic() - started_at) > STREAM_SEEK_RESTORE_TIMEOUT:
            self._pending_stream_seek_frac = None
            self._pending_stream_seek_ms = None
            self._pending_stream_pause = False
            return
        if asked_frac is not None:
            if player.set_position(asked_frac) not in (0, None):
                return
            self._pending_stream_seek_frac = None
        elif asked_ms is not None:
            if player.set_time(int(asked_ms)) not in (0, None):
                return
            self._pending_stream_seek_ms = None
        if asked_pause:
            player.set_pause(1)
            self._pending_stream_pause = False

    def _on_stream_refreshed(self, ok, title):
        """The GUI-thread half of a stream refresh, reported from the thread that ran it."""
        if ok:
            if getattr(self, 'is_playing', False):
                if getattr(self, 'play_btn', None):
                    self.play_btn.setText("\uE769")
                self._on_status_update(f"Playing: {title}", True, "gray")
            else:
                if getattr(self, 'play_btn', None):
                    self.play_btn.setText("\uE768")
                self._on_status_update(f"Ready: {title}", True, "gray")
        else:
            self._on_status_update(f"Could not re-fetch the stream for {title} - pick the track to try again.",
                                   False, "#E31E24")

    # ------------------------------------------------------------------
    # "Stop after current" - three states, one click each
    # ------------------------------------------------------------------
    # Off    : a track ending advances to the next one, exactly as it always did.
    # Once   : the current track is the last one; when it ends the state resets to Off
    #          and the track stays stopped where it is.
    # Always : every track stops when it ends and stays stopped, until clicked again.
    # One click walks the cycle Off -> Once -> Always -> Off, from the player-bar
    # button or from the tray menu. A manual "Next Track" always advances regardless.

    def cycle_stop_after_current(self):
        """Move to the next state in the off -> once -> always -> off cycle."""
        current = getattr(self, 'stop_after_current', STOP_AFTER_OFF)
        # A click is the user taking the state in hand, so an arming a search left
        # behind is no longer what he wants and goes with it.
        self._search_stop_after_track = None
        self.set_stop_after_current((int(current) + 1) % 3)

    def set_stop_after_current(self, state):
        try:
            state = int(state)
        except (TypeError, ValueError):
            state = STOP_AFTER_OFF
        if state not in (STOP_AFTER_OFF, STOP_AFTER_ONCE, STOP_AFTER_ALWAYS):
            state = STOP_AFTER_OFF
        self.stop_after_current = state
        self._update_stop_after_ui()
        if state == STOP_AFTER_OFF:
            self._on_status_update("Stop after current: off - playback will advance to the next track.", False, "white")
        elif state == STOP_AFTER_ONCE:
            self._on_status_update("Stop after current: once - this track is the last one.", False, "#FF8C00")
        else:
            self._on_status_update("Stop after current: always - every track stops when it ends.", False, "#E31E24")

    def _update_stop_after_ui(self):
        """Reflect the state in the player-bar button. The tray menu is rebuilt every
        time it opens (_build_tray_menu), so it needs no live update."""
        btn = getattr(self, 'stop_after_btn', None)
        if btn is None:
            return
        state = getattr(self, 'stop_after_current', STOP_AFTER_OFF)
        btn.setProperty("stop_after_state", STOP_AFTER_STATE_NAMES[state])
        btn.setToolTip(STOP_AFTER_TOOLTIPS[state])
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def _finish_stop_after_current(self):
        """A track ended while "stop after current" was armed: hold here instead of
        advancing, and spend the one-shot state back to off."""
        self.is_playing = False
        if getattr(self, 'play_btn', None):
            self.play_btn.setText("\uE768")
        # The successor readied seconds ago is not wanted now; its resolved URL stays
        # in the cache in case the user presses Next themselves. The trigger key goes
        # too, so a track the user starts again by hand reads ahead once more.
        self._prefetch_decision = None
        self._prefetch_trigger_key = None
        # Whichever way the arming was set - the button or a new search - it has now
        # been spent on the track that just finished.
        self._search_stop_after_track = None
        if getattr(self, 'stop_after_current', STOP_AFTER_OFF) == STOP_AFTER_ONCE:
            self.set_stop_after_current(STOP_AFTER_OFF)
            self._on_status_update("Stopped after the current track.", False, "gray")
        else:
            self._on_status_update("Stopped after the current track - Stop after current is still on.", False, "gray")

    def _stream_track_in_progress(self):
        """The video id of the stream the player is committed to, or None when there
        is no stream for a new search to interrupt.

        "Committed" covers a stream playing, paused, or still being resolved by
        yt-dlp: a paused track resumes and then advances exactly like one that was
        playing, and a track being fetched starts on its own the moment yt-dlp
        answers. Local files are left out on purpose - a search replaces
        search_results, which is the list a searched track steps through, and it
        leaves the folder list a local file steps through untouched.
        """
        if getattr(self, '_is_loading_stream', False):
            return getattr(self, '_pending_fetch_id', None) or None
        vid_id = getattr(self, 'current_video_id', None)
        if not vid_id or vid_id == "local":
            return None
        player = getattr(self, 'vlc_player', None)
        if player is None:
            return None
        if player.get_state() not in (vlc.State.Playing, vlc.State.Paused):
            return None
        return vid_id

    def _arm_stop_after_for_new_search(self):
        """Arm "stop after current: once" for the track playing when a new search lands.

        play_next() steps through search_results by index, and a new search replaces
        search_results underneath the track that is already playing. That track is
        still a track of the previous list, but its index now counts into the new
        one, so when it finished the listener was dropped into the middle of the
        search they had just run - which looked like the player moving on to some
        video at random. The one-shot state makes the track already playing the last
        one of the list it came from, and leaves the new search to be started by
        hand. Returns True only when it armed: a state the user chose by clicking is
        never overwritten, and a search with no stream in progress arms nothing.
        """
        if getattr(self, 'stop_after_current', STOP_AFTER_OFF) != STOP_AFTER_OFF:
            return False
        vid_id = self._stream_track_in_progress()
        if not vid_id:
            return False
        self._search_stop_after_track = vid_id
        self.set_stop_after_current(STOP_AFTER_ONCE)
        return True

    def _release_search_stop_after(self, new_vid_id=None):
        """Forget a "once" that a search armed, as opposed to one the user clicked.

        Such an arming belongs to one track only. Once a different track starts - a
        row clicked in the new list, a manual Next or Previous, a file from the local
        pane - it has nothing left to protect, and leaving it armed would have
        stopped the track the user just chose after it finished. The same track
        started again keeps its arming, because it still came from the old list.
        """
        armed_for = getattr(self, '_search_stop_after_track', None)
        if not armed_for:
            return
        if new_vid_id and new_vid_id == armed_for:
            return
        self._search_stop_after_track = None
        if getattr(self, 'stop_after_current', STOP_AFTER_OFF) == STOP_AFTER_ONCE:
            self.set_stop_after_current(STOP_AFTER_OFF)

    def play_result(self, video, paused_at_start=False, from_nav=False):
        # If VLC is still initializing in background, defer and retry
        if not getattr(self, '_vlc_ready', False):
            QTimer.singleShot(200, lambda: self.play_result(video, paused_at_start, from_nav))
            return
        if self.vlc_instance is None or self.vlc_player is None:
            self._on_status_update("Playback unavailable: VLC Media Player is not installed.", False, "#E31E24")
            return

        self._on_status_update(f"Fetching stream: {video.get('title', 'Unknown')}...", False, "#3B8ED0")
        
        # Track pending fetch ID and loading state
        vid_id = video.get('id', '')
        # The one-shot a search armed belongs to the track that was playing when that
        # search ran. The track the user has just picked is not it, so the arming is
        # dropped here instead of stopping this track after it ends.
        self._release_search_stop_after(vid_id)
        self._pending_fetch_id = vid_id
        self._is_loading_stream = True
        self._has_played_current = False
        self._ended_trigger = True
        
        # update index
        self.playback_index = -1
        for i, res in enumerate(self.search_results):
            if res.get('id') == vid_id:
                self.playback_index = i; break

        if not from_nav:
            # User manually clicked a track: reset shuffle history with this track
            self.shuffle_history = [self.playback_index] if self.playback_index >= 0 else []
                
        def bg_fetch():
            try:
                # Resolved seconds ago by the prefetch thread? Use that and skip yt-dlp
                # entirely - this is what removes the gap at a changeover.
                prefetched = self._take_prefetched_stream(vid_id)
                if prefetched:
                    url, user_agent, url_age = prefetched
                else:
                    url, user_agent = resolve_stream_url(vid_id)
                    url_age = 0.0

                # If another stream request started while fetching, ignore this one
                if getattr(self, '_pending_fetch_id', None) != vid_id:
                    return

                media = self.vlc_instance.media_new(url)
                media.add_option(f':http-user-agent={user_agent}')
                self.vlc_player.set_media(media)
                if paused_at_start:
                    self.vlc_player.audio_set_mute(True)
                    self.vlc_player.play()
                    import time
                    time.sleep(0.25)
                    self.vlc_player.set_pause(1)
                    self.vlc_player.set_position(0)
                    self.vlc_player.audio_set_mute(False)
                else:
                    self.vlc_player.play()
                self._is_loading_stream = False
                # Remember what the player is now loaded with, so that a stream which stops
                # answering later can be re-resolved without this track being picked out of the
                # list again - and so that a track left paused past the life of its URL can be
                # picked up where it stopped.
                self._note_loaded_stream(vid_id, url, user_agent, url_age)
                self.playback_started_signal.emit(video.get('title', 'Unknown'), vid_id, paused_at_start)
            except Exception as e:
                print(f"Stream error: {e}")
                if getattr(self, '_pending_fetch_id', None) == vid_id:
                    self._is_loading_stream = False
                self.search_failed_signal.emit()
        threading.Thread(target=bg_fetch, daemon=True).start()

    def _on_playback_started(self, title, vid_id, paused_at_start=False):
        self.current_playing_title = title
        self.current_video_id = vid_id
        if paused_at_start:
            self.is_playing = False
            self.play_btn.setText("\uE768")
            self._on_status_update(f"Ready: {title}", True, "gray")
        else:
            self.is_playing = True
            self.play_btn.setText("\uE769")
            self._on_status_update(f"Playing: {title}", True, "gray")

    def eventFilter(self, obj, event):
        if event.type() == event.Type.KeyPress:
            fw = QApplication.focusWidget()
            if event.key() == Qt.Key_Space and not isinstance(fw, QLineEdit):
                self.toggle_playback()
                return True
            # File Explorer style keys, but only while the local file list has focus.
            if self._focus_is_in_local_pane(fw):
                if event.key() == Qt.Key_Escape:
                    self.clear_local_selection()
                    return True
                if not isinstance(fw, (QLineEdit, QComboBox)):
                    if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                        self.delete_local_selected()
                        return True
                    if event.key() == Qt.Key_F2:
                        self.rename_local_selected()
                        return True
                    if event.key() == Qt.Key_A and event.modifiers() & Qt.ControlModifier:
                        self.select_all_local_files()
                        return True
                    if event.key() == Qt.Key_C and event.modifiers() & Qt.ControlModifier:
                        self.copy_local_selected()
                        return True
                    if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                        self._open_local_selection()
                        return True
        return super().eventFilter(obj, event)

    def open_search_on_youtube(self):
        import webbrowser, urllib.parse
        query = self.search_entry.text().strip()
        if not query: return
        if 'youtube.com' in query or 'youtu.be' in query:
            webbrowser.open(query)
        else:
            webbrowser.open(f'https://www.youtube.com/results?search_query={urllib.parse.quote(query)}')

    def toggle_playback(self):
        if not self.vlc_player: return
        if self._stream_needs_renew():
            # Pressing play on a stream that has stopped answering is the listener asking for the
            # music, not for the media that happens to be loaded: a dead media answers neither a
            # play nor a seek, which is exactly what made this look like a play button that does
            # nothing. Re-resolve this same track and pick up where it stopped - a play the user
            # asked for gets the whole allowance back, is not held by the seek cooldown, and
            # leaves the app wanting the track playing even if the cooldown still has this one
            # waiting, because the next press of the button goes through.
            self.is_playing = True
            if getattr(self, 'play_btn', None):
                self.play_btn.setText("\uE769")
            self._stream_refetch_attempts = 0
            self._renew_loaded_stream(force=True)
            return
        if getattr(self, '_loaded_stream', None) and getattr(self, '_stream_refetching', False):
            # Play pressed while the re-resolution the previous press started is still running:
            # the fresh media is already on its way, so all this means is "play it when it lands"
            # - the queued position stops asking for a pause, and the dying media is not paused
            # and unpaused behind a fetch that is about to replace it.
            self.is_playing = True
            if getattr(self, 'play_btn', None):
                self.play_btn.setText("\uE769")
            self._pending_stream_pause = False
            self._pending_stream_seek_at = time.monotonic()
            return
        if self.vlc_player.is_playing():
            self.vlc_player.pause()
            self.play_btn.setText("\uE768")
            self.is_playing = False
        else:
            self.vlc_player.play()
            self.play_btn.setText("\uE769")
            self.is_playing = True

    def toggle_shuffle(self):
        self.is_shuffled = not self.is_shuffled
        self.update_shuffle_btn_style()
        if self.is_shuffled:
            if self.current_video_id == "local" and hasattr(self, 'local_playback_index') and self.local_playback_index >= 0:
                self.shuffle_history = [self.local_playback_index]
            elif self.playback_index >= 0:
                self.shuffle_history = [self.playback_index]
            else:
                self.shuffle_history = []
        else:
            self.shuffle_history = []

    def update_shuffle_btn_style(self):
        if hasattr(self, 'shuffle_btn'):
            self.shuffle_btn.setProperty("active", "true" if getattr(self, 'is_shuffled', False) else "false")
            self.shuffle_btn.style().unpolish(self.shuffle_btn)
            self.shuffle_btn.style().polish(self.shuffle_btn)

    def play_previous(self):
        if self.current_video_id == "local" and hasattr(self, 'local_playback_index'):
            audio_files = [x for x in getattr(self, 'current_local_items', []) if x.get('is_dir') is False]
            if not audio_files: return
            if getattr(self, 'is_shuffled', False):
                hist = getattr(self, 'shuffle_history', [])
                if len(hist) > 1:
                    hist.pop()  # remove current
                    prev_idx = hist[-1]
                    if 0 <= prev_idx < len(audio_files):
                        self.local_playback_index = prev_idx
                        self._on_local_click(audio_files[prev_idx], from_nav=True)
                        return
            if self.local_playback_index > 0:
                self.local_playback_index -= 1
                self._on_local_click(audio_files[self.local_playback_index], from_nav=True)
            return
            
        if not self.search_results: return
        if getattr(self, 'is_shuffled', False):
            hist = getattr(self, 'shuffle_history', [])
            if len(hist) > 1:
                hist.pop()  # remove current
                prev_idx = hist[-1]
                if 0 <= prev_idx < len(self.search_results):
                    self.playback_index = prev_idx
                    self.play_result(self.search_results[prev_idx], from_nav=True)
                    return
        if self.playback_index > 0:
            self.playback_index -= 1
            self.play_result(self.search_results[self.playback_index], from_nav=True)
            
    def play_next(self):
        if self.current_video_id == "local" and hasattr(self, 'local_playback_index'):
            audio_files = [x for x in getattr(self, 'current_local_items', []) if x.get('is_dir') is False]
            if not audio_files: return
            if getattr(self, 'is_shuffled', False):
                if not hasattr(self, 'shuffle_history'):
                    self.shuffle_history = []
                unplayed = [i for i in range(len(audio_files)) if i not in self.shuffle_history]
                if not unplayed:
                    self.shuffle_history = [self.local_playback_index] if hasattr(self, 'local_playback_index') else []
                    unplayed = [i for i in range(len(audio_files)) if i != getattr(self, 'local_playback_index', -1)]
                if unplayed:
                    next_idx = random.choice(unplayed)
                    self.shuffle_history.append(next_idx)
                    self.local_playback_index = next_idx
                    self._on_local_click(audio_files[next_idx], from_nav=True)
                    return
                elif len(audio_files) == 1:
                    self._on_local_click(audio_files[0], from_nav=True)
                    return
            if self.local_playback_index + 1 < len(audio_files):
                self.local_playback_index += 1
                self._on_local_click(audio_files[self.local_playback_index], from_nav=True)
            return
            
        if not self.search_results: return

        # A successor decided seconds ago (see _maybe_prefetch_next_track) is honoured
        # first, so the stream that was already resolved is the stream that plays.
        decided = self._prefetch_decision_for(getattr(self, 'current_video_id', ''))
        if decided is not None:
            self._prefetch_decision = None
            next_idx, next_video = decided
            if (next_video is not None and 0 <= next_idx < len(self.search_results)
                    and self.search_results[next_idx].get('id') == next_video.get('id')):
                if getattr(self, 'is_shuffled', False):
                    self.shuffle_history.append(next_idx)
                self.playback_index = next_idx
                self.play_result(next_video, from_nav=True)
                return

        if getattr(self, 'is_shuffled', False):
            if not hasattr(self, 'shuffle_history'):
                self.shuffle_history = []
            unplayed = [i for i in range(len(self.search_results)) if i not in self.shuffle_history]
            if not unplayed:
                self.shuffle_history = [self.playback_index] if self.playback_index >= 0 else []
                unplayed = [i for i in range(len(self.search_results)) if i != self.playback_index]
            if unplayed:
                next_idx = random.choice(unplayed)
                self.shuffle_history.append(next_idx)
                self.playback_index = next_idx
                self.play_result(self.search_results[next_idx], from_nav=True)
                return
            elif len(self.search_results) == 1:
                self.play_result(self.search_results[0], from_nav=True)
                return
        if self.playback_index + 1 < len(self.search_results):
            self.playback_index += 1
            self.play_result(self.search_results[self.playback_index], from_nav=True)

    def on_seek(self, val):
        if not self.vlc_player:
            return
        frac = float(val) / 10000.0
        if self._stream_needs_renew() or getattr(self, '_stream_refetching', False):
            # Scrubbing a stream that has stopped answering does nothing at all, and that is how
            # the whole problem hid: the slider moved and libVLC ignored it. Keep the position
            # they asked for - as a fraction, because a media that is not open again reports no
            # length to convert it - and re-resolve this same track; _apply_pending_stream_seek
            # puts them there once the fresh media answers. A drag that keeps moving only ever
            # queues the last position asked for, because one refresh is enough for one dead
            # stream and STREAM_RENEW_COOLDOWN keeps a dragged bar from becoming a fetch storm.
            self._pending_stream_seek_frac = frac
            self._pending_stream_seek_ms = None
            if self._renew_loaded_stream():
                return
            # Nothing worth re-resolving - the cooldown is still running, or this track has used
            # up its attempts. That is no reason to ignore the scrub itself, so ask the media the
            # ordinary way and let the listener drag the bar as they always could.
            self._pending_stream_seek_frac = None
        self.vlc_player.set_position(frac)

    def on_volume_changed(self, val):
        self.volume_val = val
        if self.vlc_player:
            # VLC uses 0-200 (100=normal). Map slider 0-100 → vlc 0-100, 101-150 → vlc 101-200
            vlc_vol = val if val <= 100 else int(100 + (val - 100) * 2)
            self.vlc_player.audio_set_volume(vlc_vol)
        if hasattr(self, 'vol_pct'):
            self.vol_pct.setText(f"{val}%")
            if val > 115:
                self.vol_pct.setStyleSheet("color: #E31E24; font-weight: bold;")
                self.vol_slider.setProperty("volume_state", "red")
            elif val > 100:
                self.vol_pct.setStyleSheet("color: #FF8C00; font-weight: bold;")
                self.vol_slider.setProperty("volume_state", "orange")
            else:
                self.vol_pct.setStyleSheet("")
                self.vol_slider.setProperty("volume_state", "normal")
            self.vol_slider.style().unpolish(self.vol_slider)
            self.vol_slider.style().polish(self.vol_slider)

    def update_player_ui(self):
        # The tick that already asks libVLC what the media is doing is the one place in
        # this app that knows the play state, so it is the one place that colours the row
        # of the track that state belongs to.
        self._refresh_playback_highlights()
        title = getattr(self, 'current_playing_title', '').strip()
        time_txt = ""

        if self.vlc_player and self.current_video_id:
            state = self.vlc_player.get_state()
            pos = self.vlc_player.get_position() * 10000
            ms = self.vlc_player.get_time()
            total_ms = self.vlc_player.get_length()
            # This timer is also what notices that a stream has stopped answering, because
            # libVLC never reports it itself - see the stream-liveness block above "Stop after
            # current". The position it reports is the only evidence there is.
            self._watch_stream_liveness(state, ms)
            if state == vlc.State.Playing:
                self._has_played_current = True
                if not getattr(self, '_stream_refetching', False):
                    # A refresh in flight means this Playing still belongs to the dying media: its
                    # ending is being held by _renew_loaded_stream, and a position queued for the
                    # fresh media must not be spent on the media that is about to be replaced. The
                    # fresh media reporting Playing both clears the held ending and lands the
                    # position, which is what makes the whole thing read as one continuous buffer.
                    self._ended_trigger = False
                    self._apply_pending_stream_seek()
            elif state == vlc.State.Ended:
                # ONLY trigger auto-advance if this track actually played and hasn't triggered ended yet
                if getattr(self, '_has_played_current', False) and not getattr(self, '_ended_trigger', False) and getattr(self, 'is_playing', False):
                    if self._stream_ended_short(total_ms, ms) and self._recover_stream_if_possible():
                        # A stream whose URL gave out mid-track reports the same Ending as a track
                        # that finished, so this one is held rather than advanced: the track the
                        # listener was hearing is the one worth saving. The fresh media reporting
                        # Playing puts both of these flags back on its own. A reload that has
                        # already used up its attempts gets here as False, and the track is taken
                        # as finished by the rules below.
                        self._ended_trigger = True
                        self._has_played_current = False
                    else:
                        self._ended_trigger = True
                        self._has_played_current = False
                        # "Stop after current" armed: hold on this track instead of advancing.
                        if getattr(self, 'stop_after_current', STOP_AFTER_OFF):
                            self._finish_stop_after_current()
                        else:
                            self.play_next()
                
            if total_ms > 0:
                cur_str = f"{int(ms/60000)}:{int((ms%60000)/1000):02d}"
                tot_str = f"{int(total_ms/60000)}:{int((total_ms%60000)/1000):02d}"
                time_txt = f"{cur_str} / {tot_str}"
                self.time_label.setText(time_txt)
                if not self.progress_slider.isSliderDown():
                    self.progress_slider.blockSignals(True)
                    self.progress_slider.setValue(int(pos))
                    self.progress_slider.blockSignals(False)

            # Nearing the end? Have the next track's stream resolved already, on its own
            # thread, so the changeover does not stall on yt-dlp.
            if state == vlc.State.Playing and total_ms and total_ms > 0:
                if (total_ms - ms) <= PREFETCH_SECONDS_BEFORE_END * 1000:
                    self._maybe_prefetch_next_track()

        # Update hover tooltip continuously
        if hasattr(self, 'tray_icon') and self.tray_icon:
            if title:
                if not time_txt and hasattr(self, 'time_label'):
                    time_txt = self.time_label.text().strip()
                if time_txt and time_txt != "0:00 / 0:00":
                    self.tray_icon.setToolTip(f"yt-msd - {title} | {time_txt}")
                else:
                    self.tray_icon.setToolTip(f"yt-msd - {title}")
            else:
                self.tray_icon.setToolTip("yt-msd")

        # Dynamic right-click tray menu track progress
        if hasattr(self, 'tray_menu') and self.tray_menu and self.tray_menu.isVisible():
            if hasattr(self, 'tray_header_action') and self.tray_header_action:
                if title:
                    if not time_txt and hasattr(self, 'time_label'):
                        time_txt = self.time_label.text().strip()
                    trunc_t = self._truncate_title(title, 24)
                    if time_txt and time_txt != "0:00 / 0:00":
                        hdr = f"{trunc_t} | {time_txt}"
                    else:
                        hdr = trunc_t
                    self.tray_header_action.setText(hdr)
                else:
                    self.tray_header_action.setText("No Track Playing")

    def _on_thumbnail_loaded(self, vid_id, pixmap):
        if hasattr(self, '_thumbnail_labels') and vid_id in self._thumbnail_labels:
            if not pixmap.isNull():
                # Covering the box and cutting back to it, so the box is the same width on
                # all four sides of the picture whatever shape the thumbnail arrived in.
                self._thumbnail_labels[vid_id].setPixmap(cover_thumbnail(pixmap))

    def _fetch_thumbnail(self, v):
        vid_id = v.get('id')
        if not vid_id: return
        if vid_id in self.thumbnail_cache:
            self.thumbnails_loaded_signal.emit(vid_id, self.thumbnail_cache[vid_id])
            return

        try:
            url = f"https://i.ytimg.com/vi/{vid_id}/mqdefault.jpg"
            with urllib.request.urlopen(url) as req:
                data = req.read()
                if self.thumbnail_cache_size + len(data) > 256 * 1024 * 1024:
                    self.thumbnail_cache.clear(); self.thumbnail_cache_size = 0
                
                img = Image.open(io.BytesIO(data))
                qpixmap = pil_to_qpixmap(img)
                self.thumbnail_cache[vid_id] = qpixmap
                self.thumbnail_cache_size += len(data)
                self.thumbnails_loaded_signal.emit(vid_id, qpixmap)
        except: pass

# ============================================================
# ONE COPY AT A TIME
# ============================================================
# yt-msd keeps its settings in a gui_config.json beside its own exe and watches
# the folders it is pointed at. Two copies of it means two processes writing the
# same settings file - whichever closes last wins - and two sets of folder
# watchers, LAN services and VLC instances on the same folders.
#
# So the first copy to start keeps a local server under this name. A second copy
# finds it, asks it to come forward, and stops there; it never builds a MainApp,
# so it never opens a second set of anything. A named local server is used rather
# than a lock file because the running copy is the one that has to react, and it
# is the only one that can bring its own window back.

SINGLE_INSTANCE_NAME = "yt-msd-gui-single-instance"


def ask_running_instance_to_show():
    """True if another copy owns the name, having just been asked to come forward.

    Nothing is created when this succeeds, which is the point: the second copy
    has done all it needs to and the caller can exit.
    """
    client = QLocalSocket()
    try:
        client.connectToServer(SINGLE_INSTANCE_NAME)
        if not client.waitForConnected(300):
            return False
        client.write(b"show")
        client.flush()
        client.waitForBytesWritten(300)
        client.disconnectFromServer()
        return True
    except Exception:
        return False
    finally:
        try:
            client.abort()
        except Exception:
            pass


def take_single_instance_name():
    """Claim the name for this copy, or None if it cannot be claimed.

    A name left behind by a copy that was killed rather than closed is dropped
    first, so a crash does not lock the program out of starting again.
    """
    try:
        QLocalServer.removeServer(SINGLE_INSTANCE_NAME)
        server = QLocalServer()
        if not server.listen(SINGLE_INSTANCE_NAME):
            return None
        return server
    except Exception:
        return None


def accept_instance_request(server, window):
    """Read the second copy's request, close its end of it, and answer it."""
    client = server.nextPendingConnection()
    if client is None:
        return
    try:
        client.waitForReadyRead(200)
        client.deleteLater()
    except Exception:
        pass
    window.request_attention()

# ============================================================
# CRASH REPORTING - where an unhandled error goes
#
# The installed program is a windowed exe: no console, no terminal behind it, and a
# windowed PyInstaller build gives print() nowhere to go. An error that no part of
# the program caught has had nowhere to say itself out loud - the window simply
# stopped doing whatever it was doing, and the only way to read the reason was to
# run the .pyw from a terminal with "py yt-msd-gui.pyw".
#
# So an unhandled error is written to yt-msd-crash.log in the folder the program
# sits in (or in %LOCALAPPDATA%\yt-msd when that folder cannot be written to) and,
# while the window is still there, shown in a dialog that names the failure and
# points at the log. This lives in the source rather than in the build, so the .pyw
# and the compiled exe behave the same; install_crash_reporting() is called by the
# entry block below, before any of the program's own work starts.
# ============================================================

CRASH_LOG_NAME = "yt-msd-crash.log"
CRASH_LOG_MAX = 256 * 1024          # past this, the older half of the log is dropped
MAX_CRASH_DIALOGS_PER_MINUTE = 3    # a fault that repeats is logged, not repeated

_crash_state = {"writing_log": False, "in_dialog": False,
                "dialogs_allowed": True, "dialog_times": []}
_crash_reporter = None  # the QObject that carries a background error to the GUI thread


def traceback_text(exc_type, exc_value, exc_traceback):
    """The traceback as text, or a plain description when it will not format."""
    try:
        return "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    except Exception:
        return "Error could not be formatted: %r: %r" % (exc_type, exc_value)


def crash_log_folders():
    r"""The folders the crash log may live in, best first.

    First is the folder the program itself sits in, which is where gui_config.json
    already is; the installer puts that under %LOCALAPPDATA%, so it is writable
    without an administrator. %LOCALAPPDATA%\yt-msd is the fallback for a copy run
    from somewhere it may not be allowed to write to - C:\Program Files, a read-only
    share, a USB drive that was pulled out mid-run.
    """
    folders = []
    if getattr(sys, "frozen", False):
        folders.append(os.path.dirname(os.path.abspath(sys.executable)))
        folders.append(getattr(sys, "_MEIPASS", ""))
    else:
        try:
            folders.append(os.path.dirname(os.path.abspath(__file__)))
        except NameError:  # a module that was never given a file at all
            pass
    local = os.environ.get("LOCALAPPDATA") or ""
    if local:
        folders.append(os.path.join(local, "yt-msd"))
    unique = []
    for folder in folders:
        if folder and folder not in unique:
            unique.append(folder)
    return unique


def trim_crash_log(path):
    """Drop the older half of the log once it passes CRASH_LOG_MAX, so a program
    that fails most days does not end up with a file no one can open."""
    try:
        if os.path.getsize(path) <= CRASH_LOG_MAX:
            return
        keep = CRASH_LOG_MAX // 2
        with open(path, "rb") as handle:
            handle.seek(-keep, os.SEEK_END)
            tail = handle.read()
        note = b"[the oldest entries were dropped to keep this file small]\n"
        with open(path, "wb") as handle:
            handle.write(note + tail)
    except OSError:
        pass  # the log is the last thing a failing program can still do


def crash_log_entry(what, detail):
    """One entry: when, which program, which build, how it was started, and the
    traceback itself. Enough to read an error without the machine it happened on."""
    build = "installed program" if getattr(sys, "frozen", False) else "python source"
    lines = [
        "=" * 72,
        "%s | yt-msd %s | %s | %s" % (time.strftime("%Y-%m-%d %H:%M:%S"),
                                      APP_VERSION, build, what),
        "Python %s on %s" % (sys.version.split()[0], sys.platform),
        "Started as: %s" % " ".join(sys.argv),
        detail.rstrip(),
        "",
    ]
    return "\n".join(lines)


def write_crash_log(what, detail):
    """Append one crash to yt-msd-crash.log, in the first folder that will take it.
    Returns the path written, or None when no folder would.

    Nothing here is allowed to fail loudly: this runs when the program is already
    failing, and a second fault while reporting the first would hide it.
    """
    entry = crash_log_entry(what, detail)
    for folder in crash_log_folders():
        try:
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, CRASH_LOG_NAME)
            trim_crash_log(path)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(entry)
            return path
        except OSError:
            continue
    return None


class CrashReporter(QObject):
    """The bridge a background thread uses to reach the GUI thread.

    A widget may only be created in the thread that runs the event loop, so a thread
    that fails cannot raise a dialog itself. It emits this signal instead, and Qt
    delivers it in the thread this object was created in - the GUI thread.
    """
    report_requested = Signal(str, str, str)

    def __init__(self):
        super().__init__()
        self.report_requested.connect(self._show)

    def _show(self, what, detail, path):
        show_crash_dialog(what, detail, path or None)


def crash_dialog_allowed():
    """At most MAX_CRASH_DIALOGS_PER_MINUTE dialogs a minute. A fault inside a
    repaint or a one-second timer would otherwise raise a new dialog on every tick
    of it, and the log keeps every one of them."""
    now = time.time()
    recent = [shown for shown in _crash_state["dialog_times"] if now - shown < 60.0]
    if len(recent) >= MAX_CRASH_DIALOGS_PER_MINUTE:
        _crash_state["dialog_times"] = recent
        return False
    recent.append(now)
    _crash_state["dialog_times"] = recent
    return True


def open_crash_log(path):
    """Open the log in whatever edits .log files. Only the button on the dialog
    calls this, and nothing depends on it working."""
    try:
        os.startfile(path)
        return True
    except OSError:
        return False


def show_crash_dialog(what, detail, path):
    """The dialog: what stopped, the traceback behind "Show Details", and where the
    same text was written. Returns True when a dialog was raised."""
    if not _crash_state["dialogs_allowed"] or _crash_state["in_dialog"]:
        return False
    if QApplication.instance() is None or not crash_dialog_allowed():
        return False
    _crash_state["in_dialog"] = True
    try:
        box = QMessageBox()  # no parent: a crash may have taken the window with it
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("yt-msd ran into an error")
        box.setText("yt-msd hit an error it could not handle: %s\n\n"
                    "Whatever was running when it happened stopped. The full error is "
                    "behind \"Show Details\", and in the log file." % what)
        if path:
            box.setInformativeText("Written to: %s" % path)
        else:
            box.setInformativeText("The error could not be written to a log file - "
                                   "use \"Show Details\" to read it or copy it.")
        box.setDetailedText(detail)
        if path:
            open_button = box.addButton("Open the log file", QMessageBox.ActionRole)
            open_button.clicked.connect(lambda checked=False, log=path: open_crash_log(log))
        box.setStandardButtons(QMessageBox.Ok)
        box.exec()
        return True
    except Exception:
        return False
    finally:
        _crash_state["in_dialog"] = False


def report_crash(what, detail, want_dialog=True):
    """Write the failure down, then say so: a dialog while the window is up, the
    traceback on stderr when it is not - the renamer console, a "--console" run of
    the exe, or a failure so early there is no window yet."""
    path = None
    if not _crash_state["writing_log"]:
        _crash_state["writing_log"] = True
        try:
            path = write_crash_log(what, detail)
        except Exception:
            path = None
        finally:
            _crash_state["writing_log"] = False

    if want_dialog and _crash_reporter is not None and QApplication.instance() is not None:
        try:
            _crash_reporter.report_requested.emit(what, detail, path or "")
            return path
        except RuntimeError:  # the GUI thread that owned the reporter is gone
            pass

    stream = getattr(sys, "stderr", None)
    if stream is not None:
        try:
            stream.write("%s\n%s\n" % (what, detail))
            stream.flush()
        except Exception:
            pass
    return path


def handle_unhandled_error(exc_type, exc_value, exc_traceback):
    """sys.excepthook - anything that escapes the program's own try/except blocks."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    report_crash("Unhandled error", traceback_text(exc_type, exc_value, exc_traceback))


def handle_thread_error(args):
    """threading.excepthook - a background job that died on its own. The window
    carries on; the job that was running in that thread does not."""
    name = getattr(args.thread, "name", "") or "unnamed"
    report_crash("Background thread error (%s)" % name,
                 traceback_text(args.exc_type, args.exc_value, args.exc_traceback))


def handle_unraisable_error(args):
    """sys.unraisablehook - an error Python could not hand to anyone: inside a __del__,
    inside a garbage-collection pass, inside the clean-up done at exit. Those are
    written down and left alone, because they are rarely the reason something stopped.
    """
    try:
        detail = "%s\n%s" % (getattr(args, "err_msg", "Unraisable exception"),
                             traceback_text(getattr(args, "exc_type", None),
                                           getattr(args, "exc_value", None),
                                           getattr(args, "exc_traceback", None)))
    except Exception:
        detail = repr(args)
    report_crash("Unraisable error", detail, want_dialog=False)


def install_crash_reporting():
    """Point every route an unhandled error can take at the log and the dialog.
    Called once from the entry block, before the window or the renamer starts."""
    global _crash_reporter
    sys.excepthook = handle_unhandled_error
    threading.excepthook = handle_thread_error
    if hasattr(sys, "unraisablehook"):
        sys.unraisablehook = handle_unraisable_error
    if _crash_reporter is None and QApplication.instance() is not None:
        _crash_reporter = CrashReporter()
    return _crash_reporter


def silence_crash_dialogs():
    """Stop raising dialogs, which is what the window does on its way out: a dialog
    raised during shutdown would hold the process open until someone dismissed it.
    The logging side keeps working."""
    _crash_state["dialogs_allowed"] = False


if __name__ == "__main__":
    # "--console" means "this copy needs somewhere to print errors". For the installed
    # exe the launcher answers that by giving the copy a console (see attach_console
    # in the launcher); for the .pyw the terminal is already there. Either way the
    # flag is dropped here, so Qt is not handed an option that is ours, not Qt's.
    sys.argv = [a for a in sys.argv if a != "--console"]
    if len(sys.argv) > 1 and ("--renamer" in sys.argv or "-r" in sys.argv):
        sys.argv = [a for a in sys.argv if a not in ("--renamer", "-r")]
        install_crash_reporting()
        run_integrated_renamer_cli()
    else:
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        app = QApplication(sys.argv)
        install_crash_reporting()
        # Title bar + taskbar icon for every window of the app (Qt uses the
        # application icon for any window that does not set its own).
        _window_icon = app_icon()
        if _window_icon is not None:
            app.setWindowIcon(_window_icon)
        # One copy at a time. A second copy asks the first to come forward and
        # exits before it can open a second set of watchers, LAN services or
        # settings file. If the name cannot be claimed at all the copy carries on
        # - a machine where this fails is not a reason to not open the program.
        if ask_running_instance_to_show():
            sys.exit(0)
        instance_server = take_single_instance_name()
        window = MainApp()
        window.show()
        if instance_server is not None:
            instance_server.newConnection.connect(
                lambda: accept_instance_request(instance_server, window))
        ret = app.exec()
        # closeEvent() has already saved the settings and stopped the background
        # work; this only covers an exit that did not come through it. Then the
        # interpreter finishes on its own terms. A hard os._exit() here faults
        # in shiboken whenever a worker thread is still mid-call, and that is
        # what kept the window on screen for seconds after the tray icon was
        # already gone: Windows spends that long writing the crash dump.
        window.shutdown_for_exit()
        sys.exit(ret)
