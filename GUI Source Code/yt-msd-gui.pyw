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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from PySide6.QtCore import Qt, Signal, QTimer, Slot, QPoint, QRect, QMargins, QThread, QEvent, QObject
from PySide6.QtGui import QIcon, QPixmap, QImage, QAction, QColor, QPalette, QPainter, QBrush, QFont, QDrag, QFontMetrics
from PySide6.QtCore import QMimeData, QUrl

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
CUSTOM_EQ_STRING = ""
CUSTOM_NORM_CMD = ""  # Optional full ffmpeg -af override for normalization/trim

# Internal version number — keep this in sync with the latest GitHub release tag.
# (Matches the latest published release tag exactly: RELEASE-3.0)
APP_VERSION = "RELEASE-3.0"

# GitHub repository whose releases page is polled for newer versions.
UPDATE_REPO = "therealMKD/yt-msd"

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
    # 1. Remove balanced double-quote pairs ("x") - outermost first
    old = None
    while old != title:
        old = title
        title = re.sub(r'"([^"]*)"', r'\1', title)
    title = re.sub(r'(?<![a-zA-Z0-9])"(?![a-zA-Z0-9])', '', title)
    title = title.replace('"', '')

    # 2. Mask interior word contractions (e.g. Don't, won't, it's, rock'n'roll)
    MASK = "\x00APOS\x00"
    title = re.sub(r"([a-zA-Z0-9])'([a-zA-Z0-9])", rf"\1{MASK}\2", title)

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
    extensions = {".mp3", ".m4a"}
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
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, check=True, startupinfo=startupinfo)
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


def run_yt_dlp_download(args, progress_cb=None, cancelled_cb=None):
    """Run a real yt-dlp download and report its progress while it runs.

    Returns the path of the finished file (None when yt-dlp reported nothing).
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
        if line.startswith("[ExtractAudio] Destination:"):
            final_path = line.split(":", 1)[1].strip()
        elif line.startswith("[ExtractAudio] Not converting audio "):
            final_path = line[len("[ExtractAudio] Not converting audio "):].split(";")[0].strip()
        elif line.startswith("[download] Destination:"):
            staged_path = line.split(":", 1)[1].strip()
        elif line.startswith("[download] ") and line.endswith(" has already been downloaded"):
            final_path = line[len("[download] "): -len(" has already been downloaded")].strip('"')
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
    return final_path or staged_path

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
        "ffmpeg",
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

def _get_audio_duration(filepath):
    """Return duration in seconds via ffprobe, or None on failure."""
    try:
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        cmd = ["ffprobe", "-nostdin", "-v", "quiet", "-print_format", "json", "-show_format", str(filepath)]
        result = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding='utf-8', errors='ignore',
                                startupinfo=startupinfo)
        if result.returncode == 0 and result.stdout:
            import json as _json
            data = _json.loads(result.stdout)
            dur = data.get('format', {}).get('duration')
            if dur:
                return float(dur)
    except Exception:
        pass
    return None

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
    _safe_print(
        f"[{index}/{total}] {Colors.CYAN}Processing:{Colors.END} {filepath.name}...\n"
        f"  ├─ Measured: {input_i:+.2f} LUFS | True Peak: {input_tp:+.2f} dB\n"
        f"  └─ Applying Whole-Track Gain: {final_gain:+.2f} dB{limit_str} (Target: {target_lufs} LUFS)"
    )
    
    try:
        temp_fd, temp_path = tempfile.mkstemp(suffix=suffix)
        os.close(temp_fd)
    except Exception as e:
        return False, filepath.name, f"Failed to create temp file: {e}"
        
    SILENCE_THRESHOLD = "-60dB"
    SILENCE_DURATION = "0.5"
    SILENCE_KEEP = "0.5"
    af_chain = (
        f"silenceremove=start_periods=1:start_duration={SILENCE_DURATION}:start_threshold={SILENCE_THRESHOLD}:start_silence={SILENCE_KEEP}:stop_silence={SILENCE_KEEP},"
        f"areverse,"
        f"silenceremove=start_periods=1:start_duration={SILENCE_DURATION}:start_threshold={SILENCE_THRESHOLD}:start_silence={SILENCE_KEEP}:stop_silence={SILENCE_KEEP},"
        f"areverse,"
        f"volume={final_gain:.2f}dB"
    )
    if SILENCE_PAD_DUR > 0:
        af_chain += f",apad=pad_dur={SILENCE_PAD_DUR}"
    if CUSTOM_EQ_STRING:
        af_chain += f",{CUSTOM_EQ_STRING}"

    # Allow full af_chain override from custom norm command
    _effective_norm_cmd = custom_norm_cmd or CUSTOM_NORM_CMD
    if _effective_norm_cmd:
        af_chain = _effective_norm_cmd

    command = ["ffmpeg", "-nostdin", "-y", "-i", str(filepath), "-af", af_chain]
    
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
    
    # Report silence removal stats
    new_duration = _get_audio_duration(filepath)
    if orig_duration is not None and new_duration is not None:
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
        
    extensions = {".mp3", ".m4a"}
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
    print(f"{Colors.DIM}Settings: Target Loudness={TARGET_LUFS} LUFS | Max Peak={TRUE_PEAK} dB | Output Bitrate={BITRATE}{Colors.END}\n")
    
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

def trim_silence_file(index, total, filepath, custom_norm_cmd=None):
    _safe_print(f"[{index}/{total}] {Colors.CYAN}Trimming silence:{Colors.END} {filepath.name}...")
    suffix = filepath.suffix.lower()
    artist, title = read_metadata_tags(filepath)

    try:
        temp_fd, temp_path = tempfile.mkstemp(suffix=suffix)
        os.close(temp_fd)
    except Exception as e:
        return False, filepath.name, f"Failed to create temp file: {e}"
    
    SILENCE_THRESHOLD = "-60dB"
    SILENCE_DURATION = "0.5"
    SILENCE_KEEP = "0.5"
    af_chain = (
        f"silenceremove=start_periods=1:start_duration={SILENCE_DURATION}:start_threshold={SILENCE_THRESHOLD}:start_silence={SILENCE_KEEP}:stop_silence={SILENCE_KEEP},"
        f"areverse,"
        f"silenceremove=start_periods=1:start_duration={SILENCE_DURATION}:start_threshold={SILENCE_THRESHOLD}:start_silence={SILENCE_KEEP}:stop_silence={SILENCE_KEEP},"
        f"areverse"
    )
    _effective_norm_cmd = custom_norm_cmd or CUSTOM_NORM_CMD
    if _effective_norm_cmd:
        af_chain = _effective_norm_cmd
    command = ["ffmpeg", "-nostdin", "-y", "-i", str(filepath), "-af", af_chain]
    
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
    
    if not check_ffmpeg_available():
        print(f"{Colors.YELLOW}[!] FFmpeg was not found in your system's PATH.{Colors.END}")
        print(f"{Colors.DIM}    Skipping silence trim pass.{Colors.END}\n")
        return 0, 0
    
    extensions = {".mp3", ".m4a"}
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
    print(f"{Colors.DIM}Threshold: -50 dB | Min silence duration: 0.5s{Colors.END}\n")
    
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
    parser.add_argument('--eq', default=None,
                        help="Extra ffmpeg -af filter string appended after the main chain")
    parser.add_argument('--custom-norm-cmd', default=None,
                        help="Replace the entire ffmpeg -af filter chain for normalization and silence trim")
    args, _ = parser.parse_known_args()

    global SILENCE_PAD_DUR, CUSTOM_EQ_STRING, MAX_WORKERS, CUSTOM_NORM_CMD
    if args.silence_pad is not None:
        SILENCE_PAD_DUR = args.silence_pad
    if args.eq:
        CUSTOM_EQ_STRING = args.eq
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
    _ext = {".mp3", ".m4a"}
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

AUDIO_EXTENSIONS = {'.mp3', '.flac', '.wav', '.m4a', '.ogg', '.opus', '.aac', '.wma', '.mka', '.aiff', '.alac', '.ape', '.wv'}

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


class ThumbnailWidget(QWidget):

    def __init__(self, video, parent_app, parent=None):
        super().__init__(parent)
        self.setFixedSize(90, 50)
        self.video = video
        self.parent_app = parent_app
        
        self.thumb_label = QLabel(self)
        self.thumb_label.setFixedSize(90, 50)
        self.thumb_label.setStyleSheet("background-color: #2b2b2b;")
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
        self.lock = threading.Lock()

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


class SyncConfigManager:
    """Manages persistence of sync configuration within the unified gui_config.json."""
    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        self.config_file = os.path.join(config_dir, "gui_config.json")
        self.legacy_file = os.path.join(config_dir, "sync_config.json")
        self.settings: dict = {"auto_sync_interval_mins": 30, "firewall_prompted": False}
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
                c['bound_wifi_ssid'] = ssid.strip()
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
                             progress_cb: Optional[Callable[[int, int, str, int, int], None]] = None) -> Tuple[bool, str, int, int]:
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
                matching_hc, matching_cc)
        finally:
            for lock in reversed(drive_locks):
                lock.release()

    @staticmethod
    def _sync_removable_chain_locked(sync_code: str, dest_path: Path, del_mode: str,
                                     chain_name: str, config_manager: SyncConfigManager,
                                     status_cb: Optional[Callable[[str], None]],
                                     progress_cb: Optional[Callable[[int, int, str, int, int], None]],
                                     matching_hc: Optional[dict] = None,
                                     matching_cc: Optional[dict] = None) -> Tuple[bool, str, int, int]:
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
            # 1. Sync client from host first over network
            if status_cb:
                status_cb(f"[USB Sync: {chain_name}] Step 1/2: Updating client chain from host...")
            ok, msg, t, d = SyncClientWorker.sync_chain(matching_cc, status_cb=status_cb, progress_cb=progress_cb)
            if not ok and status_cb:
                status_cb(f"[USB Sync: {chain_name}] Host offline, syncing with local client cache...")

            src_dir = Path(matching_cc.get('folder_path', ''))
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

    def __init__(self, removable_config: dict, config_manager: SyncConfigManager):
        super().__init__()
        self.removable_config = removable_config
        self.config_manager = config_manager

    def run(self):
        def _status(txt):
            self.status_signal.emit(txt)

        def _progress(done, total, filename, idx, total_items):
            self.progress_signal.emit(done, total, filename, idx, total_items)

        ok, msg, transferred, deleted = SyncRemovableWorker.sync_removable_chain(
            self.removable_config,
            self.config_manager,
            status_cb=_status,
            progress_cb=_progress
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
                ("Forever (Until Re-enabled)", 0)
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
        'show_thumbnails': False,
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
        'use_custom_eq': False,
        'custom_eq_string': '',
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
        self.parent = parent
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
        start_dir = getattr(self.parent, 'download_path', '') or os.path.expanduser("~")
        target, _ = QFileDialog.getSaveFileName(self, "Save Export Package",
                                               os.path.join(start_dir, default_name),
                                               "yt-msd Package (*.zip)")
        if not target:
            return
        if not target.lower().endswith(".zip"):
            target += ".zip"
        options['zip_path'] = target
        self.parent.start_export(options)
        self.accept()


class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
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
            if color == "System": btn.setText("\uE771"); btn.setFont(QFont("Segoe MDL2 Assets", 12))
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

        # Custom EQ string
        right_layout.addWidget(QLabel("CUSTOM FFMPEG EQ FILTER (ADVANCED)", font=QFont("Segoe UI Semibold", 10)))
        eq_h = QHBoxLayout()
        self.eq_cb = QCheckBox()
        self.eq_cb.setChecked(parent.use_custom_eq)
        self.eq_cb.toggled.connect(self._toggle_eq)
        eq_h.addWidget(self.eq_cb)
        initial_eq = parent.custom_eq_string if parent.custom_eq_string else "equalizer=f=100:width_type=o:width=2:g=0"
        self.eq_edit = QLineEdit(initial_eq)
        self.eq_edit.setPlaceholderText("e.g. equalizer=f=100:width_type=o:width=2:g=-10")
        self.eq_edit.setEnabled(parent.use_custom_eq)
        self.eq_edit.textChanged.connect(self._update_eq)
        eq_h.addWidget(self.eq_edit, 1)
        eq_h.addWidget(self._make_info_btn("Appended to the ffmpeg filter chain during normalization."))
        right_layout.addLayout(eq_h)

        # Custom normalization command override (replaces built-in filter chain)
        right_layout.addWidget(QLabel("CUSTOM NORM/TRIM COMMAND OVERRIDE (ADVANCED)", font=QFont("Segoe UI Semibold", 10)))
        norm_cmd_h = QHBoxLayout()
        self.norm_cmd_cb = QCheckBox()
        self.norm_cmd_cb.setChecked(parent.use_custom_norm_cmd)
        self.norm_cmd_cb.toggled.connect(self._toggle_norm_cmd)
        norm_cmd_h.addWidget(self.norm_cmd_cb)
        initial_norm = parent.custom_norm_cmd if parent.custom_norm_cmd else f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA=11"
        self.norm_cmd_edit = QLineEdit(initial_norm)
        self.norm_cmd_edit.setPlaceholderText("e.g. loudnorm=I=-16:TP=-1.5:LRA=11")
        self.norm_cmd_edit.setEnabled(parent.use_custom_norm_cmd)
        self.norm_cmd_edit.textChanged.connect(self._update_norm_cmd)
        norm_cmd_h.addWidget(self.norm_cmd_edit, 1)
        norm_cmd_h.addWidget(self._make_info_btn("Replaces the entire -af filter chain for normalization AND silence trim."))
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
        accent = get_accent_color(self.parent.accent_color_name)
        mode = self.parent.appearance_mode
        if mode == "System": mode = get_system_appearance_mode()
        is_light = mode == "Light"
        
        r = int(accent[1:3], 16)
        g = int(accent[3:5], 16)
        b = int(accent[5:7], 16)
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        accent_fg = "black" if brightness > 150 else "white"
        
        for m, b in self.mode_btns.items():
            if m == self.parent.appearance_mode:
                b.setStyleSheet(f"background-color: {accent}; color: {accent_fg}; border-radius: 4px;")
            else:
                b.setStyleSheet(f"background-color: {'#ddd' if is_light else '#444'}; color: {'black' if is_light else 'white'}; border-radius: 4px;")
        
        for color, btn in self.accent_btns.items():
            c_val = get_system_accent_color() if color == "System" else THEME_COLORS[color][0]
            border = f"2px solid {'black' if is_light else 'white'}" if self.parent.accent_color_name == color else "none"
            btn.setStyleSheet(f"background-color: {c_val}; border-radius: 6px; border: {border};")

        for m, btn in self.norm_btns.items():
            if m == self.parent.normalization_mode:
                btn.setStyleSheet(f"background-color: {accent}; color: {accent_fg}; border-radius: 4px;")
            else:
                btn.setStyleSheet(f"background-color: {'#ddd' if is_light else '#444'}; color: {'black' if is_light else 'white'}; border-radius: 4px;")

    def _change_mode(self, mode):
        self.parent.appearance_mode = mode
        self.parent.apply_theme()
        self.update_styles()
        self.parent.save_config()

    def _change_accent(self, color):
        self.parent.accent_color_name = color
        self.parent.apply_theme()
        self.update_styles()
        self.parent.save_config()
        
    def _toggle_args(self, state):
        self.parent.use_custom_args = state
        self.args_edit.setEnabled(state)
        self.parent.save_config()
        
    def _update_args(self, text):
        self.parent.custom_args = text
        self.parent.save_config()
        
    def set_ytdlp_version(self, version):
        """Show the yt-dlp version found by a background thread in the main window."""
        if version and hasattr(self, 'ytdlp_version_lbl'):
            self.ytdlp_version_lbl.setText(f"Version: {version}")

    def _update_yt_dlp(self):
        """Ask the main window to run the winget upgrade for yt-dlp."""
        self.parent.update_yt_dlp_now()

    def _toggle_ytdlp_updates(self, state):
        self.parent.disable_ytdlp_updates = state
        self.parent.save_config()
        
    def _toggle_startup(self, state):
        set_run_on_startup(bool(state))

    def _toggle_tray(self, state):
        self.parent.minimize_to_tray = state
        self.parent.save_config()
        
    def _toggle_session(self, state):
        self.parent.save_place = state
        self.parent.save_config()

    # --- MP3 Renamer settings ---
    def _set_norm_mode(self, mode):
        self.parent.normalization_mode = mode
        for m, btn in self.norm_btns.items():
            btn.setChecked(m == mode)
        self.parent.save_config()
        self.update_styles()

    def _toggle_auto_rename(self, state):
        self.parent.auto_rename = state
        self.parent.save_config()

    def _update_silence_pad(self, text):
        try:
            val = float(text)
            if val >= 0:
                self.parent.silence_pad_dur = val
                self.parent.save_config()
        except ValueError:
            pass

    def _toggle_eq(self, state):
        self.parent.use_custom_eq = state
        self.eq_edit.setEnabled(state)
        if state and not self.eq_edit.text().strip():
            self.eq_edit.setText("equalizer=f=100:width_type=o:width=2:g=0")
        self.parent.save_config()

    def _update_dl_threads(self, text):
        try:
            val = int(text)
            if val > 0:
                self.parent.download_threads = val
                self.parent.save_config()
        except ValueError:
            pass

    def _update_rescan_interval(self, index):
        mins = self.rescan_combo.itemData(index)
        if mins is not None:
            self.parent.local_rescan_interval = mins
            self.parent._update_local_rescan_timer()
            self.parent.save_config()

    def _update_norm_threads(self, val):
        self.parent.normalization_threads = val
        self.parent.save_config()

    def _update_eq(self, text):
        self.parent.custom_eq_string = text
        self.parent.save_config()

    def _toggle_norm_cmd(self, state):
        self.parent.use_custom_norm_cmd = state
        self.norm_cmd_edit.setEnabled(state)
        if state and not self.norm_cmd_edit.text().strip():
            self.norm_cmd_edit.setText(f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA=11")
        global CUSTOM_NORM_CMD
        CUSTOM_NORM_CMD = self.parent.custom_norm_cmd if state else ""
        self.parent.save_config()

    def _update_norm_cmd(self, text):
        self.parent.custom_norm_cmd = text
        global CUSTOM_NORM_CMD
        if self.parent.use_custom_norm_cmd:
            CUSTOM_NORM_CMD = text
        self.parent.save_config()

    def _toggle_custom_script(self, state):
        # The checkbox only gates whether the script runs after a download; the
        # path field and browse button stay usable so a path can always be set.
        self.parent.run_custom_script = state
        self.parent.save_config()

    def _update_custom_script(self, text):
        self.parent.custom_script_path = text.strip()
        self.parent.save_config()

    def _browse_custom_script(self):
        start = self.custom_script_edit.text().strip() or ""
        f, _ = QFileDialog.getOpenFileName(
            self, "Select File To Run After Download", start,
            "All files (*);;Python (*.py);;Executable (*.exe);;Batch (*.bat *.cmd);;PowerShell (*.ps1)"
        )
        if f:
            self.custom_script_edit.setText(f)
            self.parent.custom_script_path = f
            self.parent.save_config()

    def _make_info_btn(self, text):
        """Small 'i' info button; the description is shown as a hover tooltip."""
        mode = self.parent.appearance_mode
        if mode == "System":
            mode = get_system_appearance_mode()
        is_light = (mode == "Light")
        fg = "#1a1a1a" if is_light else "#ffffff"
        border = "#ccc" if is_light else "#555"
        accent = get_accent_color(self.parent.accent_color_name)
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
        dialog = ExportDialog(self.parent)
        dialog.exec()

    def _open_import_package(self):
        """Pick a .zip export package and restore it."""
        self.parent.open_import_dialog()

    def _open_sync_manager(self):
        # Leave the settings dialog open in the background, open sync manager in foreground
        self.parent.open_sync_manager(parent_dialog=self)

    def _reset_defaults(self):
        if QMessageBox.question(self, "Confirm Reset", "This will wipe your config and recent data. Continue?") == QMessageBox.Yes:
            self.parent.reset_to_defaults()
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
    def __init__(self, parent_window, latest_tag, release_name, current_version):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.never_notify = False
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

        layout.addStretch()

        btn_h = QHBoxLayout()
        btn_h.addStretch()

        ignore_btn = QPushButton("Ignore")
        ignore_btn.setToolTip("Skip this update until the next check")
        ignore_btn.clicked.connect(self._on_ignore)
        btn_h.addWidget(ignore_btn)

        dl_btn = QPushButton("Download update")
        dl_btn.setToolTip("Download the new version into the folder yt-msd is running from")
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
    """Shown after a successful download; asks whether to auto-swap to the new version."""
    def __init__(self, parent_window, new_path, old_path, tag):
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

        desc = QLabel(
            f"The new version ({tag}) has been downloaded to:\n{new_path}\n\n"
            "Would you like to automatically close this version, delete the old file, and launch the new version? "
            "Choosing Cancel keeps both files so you can swap them yourself."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        old_lbl = QLabel(f"Old version file that would be removed: {old_path}")
        old_lbl.setWordWrap(True)
        old_lbl.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(old_lbl)

        layout.addStretch()

        btn_h = QHBoxLayout()
        btn_h.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip("Keep both files; swap them manually")
        cancel_btn.clicked.connect(self.reject)
        btn_h.addWidget(cancel_btn)

        ok_btn = QPushButton("OK")
        ok_btn.setToolTip("Close this version, delete the old file, and launch the new version")
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
    _local_items_signal = Signal(object)  # (folder_path, scanned items) from the folder scan thread
    update_available_signal = Signal(str, str, str, str)  # tag, release_name, download_url, asset_name
    update_downloaded_signal = Signal(str, str)  # new_file_path, tag (emitted from the download bg thread)
    missing_deps_signal = Signal(str)  # html fragment of missing dependencies (emitted from the VLC init thread)
    import_finished_signal = Signal(object)  # prepared export package, read on the import thread
    import_failed_signal = Signal(str)  # import problem, reported from the import thread
    ytdlp_missing_signal = Signal(str)  # yt-dlp absent or not installable (from a bg thread)
    ytdlp_update_signal = Signal(str, str)  # installed yt-dlp version, newest yt-dlp version
    ytdlp_version_signal = Signal(str)  # yt-dlp version found by a bg thread, shown on the GUI thread

    def __init__(self):
        super().__init__()
        self.setWindowTitle("yt-msd | YouTube Media Downloader")
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
        self.local_selection_anchor = None
        self.current_local_file_path = ""
        self.splitter_sizes = [300, 800, 300]
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
        self.show_thumbnails = False
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
        self.use_custom_eq = False
        self.custom_eq_string = ""
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
        self.is_shuffled = False
        self.shuffle_history = []
        self.shuffle_order = []
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

        # Apply CUSTOM_NORM_CMD global from loaded config immediately
        global CUSTOM_NORM_CMD
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
        self.queue_update_signal.connect(self._refresh_queue_display)
        self.queue_status_changed_signal.connect(self._on_queue_status_changed)
        self.thumbnails_loaded_signal.connect(self._on_thumbnail_loaded)
        self.dl_progress_signal.connect(lambda txt: self.dl_progress_label.setText(txt))
        self.renamer_finished_signal.connect(self._on_renamer_finished)
        self.host_activity_signal.connect(self._on_host_activity)
        self._probe_results_signal.connect(self._apply_probe_results)
        self.local_list_refresh_signal.connect(self._refresh_local_list_async)
        self._local_items_signal.connect(self._apply_local_items)
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
                audio_files = [x for x in getattr(self, 'current_local_items', []) if x.get('is_dir') is False]
                if 0 <= idx < len(audio_files):
                    QTimer.singleShot(100, lambda: self._on_local_click(audio_files[idx], paused_at_start=True))

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
            rc['status'] = "Up to date" if ok else f"Sync Failed: {msg}"
            if ok:
                rc['last_synced'] = time.time()
            self.sync_progress_state.pop(cid, None)
            if hasattr(self, 'dl_progress_signal'):
                self.dl_progress_signal.emit("")
            if ok:
                self.status_signal.emit(f"Removable media '{chain_name}' sync complete: {transferred} updated, {deleted} removed.", False, "#1abd33")
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
                download_url = (assets[0].get("browser_download_url") or "") if assets else ""
                asset_name = (assets[0].get("name") or "") if assets else ""
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
        dlg = UpdateAvailableDialog(self, tag, release_name, APP_VERSION)
        choice = dlg.exec()
        if dlg.never_notify:
            self.disable_update_checks = True
            self.save_config()
        if choice == QDialog.Accepted:
            filename = asset_name or f"yt-msd-{tag}.pyw"
            self._download_update(download_url, filename, tag)

    def _download_update(self, url, filename, tag):
        """Download the newest release asset into the folder yt-msd is currently running from."""
        if not url:
            self.status_signal.emit("Update has no downloadable file to fetch.", False, "#E31E24")
            return
        dest_path = os.path.join(self.config_dir, filename)
        self.status_signal.emit(f"Downloading update {tag}...", False, "#3B8ED0")

        def _bg():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "yt-msd-updater"})
                with urllib.request.urlopen(req, timeout=120) as resp:
                    payload = resp.read()
                with open(dest_path, "wb") as out:
                    out.write(payload)
                self._downloaded_update_tag = tag
                self.status_signal.emit(f"Update {tag} downloaded to: {dest_path}", False, "#1abd33")
                self.update_downloaded_signal.emit(dest_path, tag)
            except Exception as e:
                self.status_signal.emit(f"Update download failed: {e}", False, "#E31E24")

        threading.Thread(target=_bg, daemon=True).start()

    def _current_executable_path(self):
        """Absolute path of the file this instance is currently running from."""
        if getattr(sys, 'frozen', False):
            return os.path.abspath(sys.executable)
        return os.path.abspath(__file__)

    def _prompt_swap_dialog(self, new_path, tag):
        """After a successful download, offer to auto-close, delete the old file, and launch the new version."""
        old_path = self._current_executable_path()
        dlg = UpdateReadyDialog(self, new_path, old_path, tag)
        choice = dlg.exec()
        if choice == QDialog.Accepted:
            self._launch_swap_helper(new_path, old_path)
            # closeEvent() saves config, hides the tray, and hard-exits the process (os._exit).
            self.close()
        else:
            self.status_signal.emit(
                f"Update ready. New file: {new_path} (old file kept: {old_path}). Swap them manually to finish.",
                False, "#FF8C00"
            )

    def _launch_swap_helper(self, new_path, old_path):
        """Write a temporary helper script that waits for this process to exit, deletes the old file,
        launches the new version, then deletes itself."""
        pid = os.getpid()
        if getattr(sys, 'frozen', False):
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
        bat = (
            "@echo off\r\n"
            f'set "PID={pid}"\r\n'
            f'set "OLD={old_path}"\r\n'
            f'set "NEW={new_path}"\r\n'
            'powershell -NoProfile -Command "while (Get-Process -Id %PID% -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 300 }"\r\n'
            'if not "%OLD%"=="%NEW%" (\r\n'
            '  if exist "%OLD%" del /F /Q "%OLD%"\r\n'
            ')\r\n'
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
                    self.format_var = c.get('format', 'mp3')
                    self.bitrate_var = c.get('bitrate', '192')
                    self.recent_folders = c.get('folders', [default_dl])
                    self.download_path = self.recent_folders[0] if self.recent_folders else default_dl
                    self.accent_color_name = c.get('accent', 'System')
                    self.appearance_mode = c.get('mode', 'Dark')
                    self.volume_val = c.get('volume', 100)
                    self.local_folders = c.get('local_folders', [])
                    self.local_current_path = c.get('local_current_path', "")
                    self.show_thumbnails = c.get('show_thumbnails', False)
                    self.show_local_metadata = c.get('show_local_metadata', False)
                    self.minimize_to_tray = c.get('minimize_to_tray', False)
                    self.recent_playlists = c.get('recent_playlists', [])
                    self.splitter_sizes = c.get('splitter_sizes', [300, 800, 300])
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
                    self.use_custom_eq = c.get('use_custom_eq', False)
                    self.custom_eq_string = c.get('custom_eq_string', '')
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
            'show_thumbnails': self.show_thumbnails,
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
            'use_custom_eq': self.use_custom_eq,
            'custom_eq_string': self.custom_eq_string,
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
            try:
                with open(self.config_path, 'w') as f: json.dump(c, f, indent=4)
            except: pass

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

    def closeEvent(self, event):
        try:
            self.save_config()
        except Exception:
            pass

        try:
            if hasattr(self, 'sync_config_manager') and self.sync_config_manager:
                self.sync_config_manager.save()
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

        event.accept()
        os._exit(0)

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
        self.show_thumbnails = False
        self.minimize_to_tray = False
        self.run_renamer = False
        self.renamer_path = ""
        self.run_custom_script = False
        self.custom_script_path = ""
        self._last_downloaded_files = []
        self.normalization_mode = "ask"
        self.auto_rename = False
        self.silence_pad_dur = 2.0
        self.use_custom_eq = False
        self.custom_eq_string = ""
        self.use_custom_norm_cmd = False
        self.custom_norm_cmd = ""
        self.download_threads = 3
        self.normalization_threads = max(1, os.cpu_count() // 2)
        self.local_rescan_interval = 60
        if hasattr(self, 'local_rescan_timer'):
            self._update_local_rescan_timer()
        if hasattr(self, 'run_renamer_cb'):
            self.run_renamer_cb.blockSignals(True)
            self.run_renamer_cb.setChecked(False)
            self.run_renamer_cb.blockSignals(False)
        self.splitter_sizes = [300, 800, 300]
        
        # Apply changes
        self.apply_theme()
        if hasattr(self, 'splitter'):
            self.splitter.setSizes(self.splitter_sizes)
        if hasattr(self, 'vol_slider'):
            self.vol_slider.setValue(100)
        self.save_config()
        self._on_status_update("Settings reset to defaults.", False, "#3B8ED0")

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
            self.format_combo.setCurrentText(str(cfg.get('format')))
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
        if 'show_thumbnails' in cfg:
            self.show_thumbnails = bool(cfg.get('show_thumbnails'))
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
        if 'use_custom_eq' in cfg:
            self.use_custom_eq = bool(cfg.get('use_custom_eq'))
        if 'custom_eq_string' in cfg:
            self.custom_eq_string = str(cfg.get('custom_eq_string') or "")
        if 'use_custom_norm_cmd' in cfg:
            self.use_custom_norm_cmd = bool(cfg.get('use_custom_norm_cmd'))
        if 'custom_norm_cmd' in cfg:
            self.custom_norm_cmd = str(cfg.get('custom_norm_cmd') or "")
        global CUSTOM_NORM_CMD
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
        if 'show_thumbnails' in cfg and getattr(self, 'search_results', None):
            self._on_search_results(self.search_results, False)
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
        self.format_combo.addItems(["mp3", "m4a", "flac", "wav", "aac"])
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
                self._on_search_results(sd['search_results'], False)
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
        
        self.show_thumb_cb = QCheckBox("Show Thumbnails")
        self.show_thumb_cb.setChecked(self.show_thumbnails)
        self.show_thumb_cb.stateChanged.connect(self.toggle_thumbnails)
        h.addWidget(self.show_thumb_cb)
        
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
            QPushButton#transparentBtn[selected="true"] {{
                background-color: transparent;
                color: {accent_fg};
            }}
            QPushButton#transparentBtn[selected="true"]:hover {{
                background-color: {btn_hover};
            }}
            QLabel#durationLabel[selected="true"] {{ color: {accent_fg}; }}
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
            {tooltip_css}
        """.format(
            bg=bg, fg=fg, frame_bg=frame_bg, input_bg=input_bg, input_border=input_border,
            scroll_bg=scroll_bg, splitter_handle=splitter_handle, slider_bg=slider_bg,
            hover_bg=hover_bg, hover_fg=hover_fg, accent=accent, accent_fg=accent_fg,
            queue_item_bg=queue_item_bg, queue_item_bg_finished=queue_item_bg_finished,
            btn_hover=btn_hover, checkmark_path=checkmark_path, downarrow_path=downarrow_path,
            main_btn_border=main_btn_border, secondary_fg=secondary_fg,
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
        self._build_local_rows(self._scan_local_items(self.local_current_path))

    def _refresh_local_list_async(self):
        """Rescan the open folder on a worker thread. Used for every refresh that
        was not caused by the user directly (a sync finishing, the hourly
        auto-rescan), so a slow drive never holds the UI hostage."""
        path = self.local_current_path

        def _bg():
            items = self._scan_local_items(path)
            try:
                self._local_items_signal.emit((path, items))
            except RuntimeError:
                pass

        threading.Thread(target=_bg, daemon=True).start()

    def _apply_local_items(self, payload):
        path, items = payload
        if path != self.local_current_path:
            return  # the folder changed while the scan was running
        self._build_local_rows(items)

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
                            items.append({'name': entry.name, 'path': entry.path, 'is_dir': False, 'selectable': True})
        except Exception:
            pass
        items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        return items

    def _build_local_rows(self, items):
        while self.local_vbox.count():
            item = self.local_vbox.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        self.local_rows = []
        self.local_row_by_path = {}
        self.local_selection_anchor = None
        if items is None:
            self.current_local_items = []
            self.local_selected_paths = set()
            self._update_local_selection_ui()
            return
        
        self.current_local_items = items
        
        self.local_btns = []
        for idx, item in enumerate(items):
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

                dur_lbl = QLabel(item.get('duration_str', ''))
                dur_lbl.setObjectName("durationLabel")
                dur_lbl.setStyleSheet("border: none; background: transparent; padding-right: 6px;")

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

        # Drop any selection that no longer points at something in this folder.
        previous_selection = set(getattr(self, 'local_selected_paths', ()))
        self.local_selected_paths = {p for p in previous_selection if p in self.local_row_by_path}
        self._apply_local_selection_styles()
        self._update_local_selection_ui()

        if self.local_btns:
            self._fetch_local_metadata_bg()
            
    def _fetch_local_metadata_bg(self):
        from PySide6.QtCore import QObject, Signal
        class MetaWorker(QObject):
            meta_done = Signal(object, object, object)
            
        self._meta_worker = MetaWorker()
        self._meta_worker.meta_done.connect(
            lambda b, d_lbl, i: (
                b._elide.set_full_text(f"🎵  {(i.get('meta_name', i['name']) if getattr(self, 'show_local_metadata', False) else i['name']).replace('&', '&&')}"),
                d_lbl.setText(i.get('duration_str', ''))
            )
        )
        
        btns_to_process = list(self.local_btns)
        
        import sys, os, subprocess, json
        ffprobe_path = 'ffprobe'
        if getattr(sys, 'frozen', False):
            base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
            ff_exe = os.path.join(base_dir, 'ffprobe.exe')
            if os.path.exists(ff_exe):
                ffprobe_path = ff_exe
                
        def bg_task():
            for btn, d_lbl, item in btns_to_process:
                if 'meta_name' not in item or 'duration_str' not in item:
                    try:
                        cmd = [ffprobe_path, '-v', 'quiet', '-print_format', 'json', '-show_format', item['path']]
                        # 0x08000000 is CREATE_NO_WINDOW on Windows
                        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', creationflags=0x08000000)
                        if result.stdout:
                            data = json.loads(result.stdout)
                            fmt = data.get('format', {})
                            tags = fmt.get('tags', {})
                            
                            title = tags.get('title') or tags.get('TITLE')
                            artist = tags.get('artist') or tags.get('ARTIST')
                            
                            if title:
                                item['meta_name'] = f"{artist} - {title}" if artist else title
                            else:
                                item['meta_name'] = item['name']
                                
                            dur = fmt.get('duration')
                            if dur:
                                d = float(dur)
                                if d >= 3600:
                                    item['duration_str'] = f"{int(d//3600)}:{int((d%3600)//60):02d}:{int(d%60):02d}"
                                else:
                                    item['duration_str'] = f"{int(d//60)}:{int(d%60):02d}"
                            else:
                                item['duration_str'] = ""
                        else:
                            item['meta_name'] = item['name']
                            item['duration_str'] = ""
                    except Exception:
                        item['meta_name'] = item['name']
                        item['duration_str'] = ""
                # Update UI safely
                self._meta_worker.meta_done.emit(btn, d_lbl, item)
        threading.Thread(target=bg_task, daemon=True).start()

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
        w = widget if widget is not None else QApplication.focusWidget()
        if w is None or not hasattr(self, 'local_list'):
            return False
        while w is not None:
            if w is self.local_list or w is self.local_content:
                return True
            w = w.parent()
        return False

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

    def toggle_thumbnails(self, state):
        self.show_thumbnails = state == Qt.Checked.value
        self.save_config()
        if self.search_results:
            self._on_search_results(self.search_results, False)

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

    def _on_search_results(self, res, is_playlist):
        self.search_btn.setEnabled(True)
        self.search_results = res
        self._thumbnail_labels = getattr(self, '_thumbnail_labels', {})
        self._thumbnail_labels.clear()
        
        while self.results_vbox.count():
            item = self.results_vbox.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        height = 54 if self.show_thumbnails else 34
        for video in res:
            placeholder = QWidget()
            placeholder.setFixedHeight(height)
            placeholder.setProperty("video", video)
            placeholder.setProperty("has_ui", False)
            self.results_vbox.addWidget(placeholder)
            
        self._on_status_update(f"Found {len(res)} results.", False, "white")
        QTimer.singleShot(0, self.lazy_load_visible_results)
        self.update_queue_all_checkbox_state()

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
        
        if self.show_thumbnails:
            tw = ThumbnailWidget(video, self)
            l.addWidget(tw)
            self._thumbnail_labels[video['id']] = tw.thumb_label
            threading.Thread(target=self._fetch_thumbnail, args=(video,), daemon=True).start()
        else:
            pbtn = QPushButton("\uE768")
            pbtn.setToolTip("Play this track")
            pbtn.setFixedWidth(40)
            pbtn.setObjectName("iconBtn")
            pbtn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px;")
            pbtn.clicked.connect(lambda checked=False, v=video: self.play_result(v))
            l.addWidget(pbtn)
            
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
        folder = self.path_combo.currentText()
        
        def bg_download():
            from concurrent.futures import ThreadPoolExecutor
            import time, glob
            
            with self.active_downloads_lock:
                self.active_downloads.clear()
                
            threads_count = max(1, int(getattr(self, 'download_threads', 3)))
            target_format = self.format_combo.currentText().lower()
            downloaded_filepaths = []
            downloaded_lock = threading.Lock()
            
            def download_single(item):
                idx, q = item
                vid_id = q['video'].get('id', '')
                if not vid_id: return
                if getattr(self, 'cancel_download', False):
                    q['status'] = "Pending"
                    self.queue_status_changed_signal.emit(idx)
                    return
                q['status'] = "Downloading"
                self.queue_status_changed_signal.emit(idx)
                
                success = False
                downloaded_file = None
                try:
                    # The options the Python API used, written as yt-dlp CLI flags.
                    cli_args = [
                        "--newline",
                        "--format", "bestaudio/best",
                        "--extract-audio",
                        "--audio-format", target_format,
                        "--audio-quality", str(self.bitrate_combo.currentText()),
                        "--retries", "15",
                        "--fragment-retries", "15",
                        "--file-access-retries", "10",
                        "--output", f"{folder}/%(title)s.%(ext)s",
                    ]
                    if getattr(sys, 'frozen', False):
                        cli_args.extend(["--ffmpeg-location", getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))])
                    if getattr(self, 'use_custom_args', False) and getattr(self, 'custom_args', ''):
                        # Appended last, so the advanced field wins over the GUI picks
                        # exactly like the Settings dialog says it should.
                        cli_args.extend(shlex.split(self.custom_args))
                    # The track itself: yt-dlp takes URLs positionally, so it goes
                    # after every option. Without it yt-dlp exits with
                    # "You must provide at least one URL" and nothing downloads.
                    cli_args.append(f"https://www.youtube.com/watch?v={vid_id}")

                    downloaded_file = run_yt_dlp_download(
                        cli_args,
                        progress_cb=lambda pct: self._dl_progress_percent(vid_id, pct),
                        cancelled_cb=lambda: getattr(self, 'cancel_download', False),
                    )
                    if not downloaded_file:
                        # Nothing reported (already downloaded, or an older yt-dlp):
                        # match the title on disk the way prepare_filename used to.
                        title_stem = _sanitize_filename(q['video'].get('title', '') or '')
                        if title_stem:
                            for m in glob.glob(glob.escape(os.path.join(folder, title_stem)) + ".*"):
                                if os.path.exists(m) and os.path.getsize(m) > 1024:
                                    downloaded_file = m
                                    break
                    if downloaded_file and os.path.exists(downloaded_file) and os.path.getsize(downloaded_file) > 1024:
                        success = True
                except Exception as e:
                    print(f"Download exception for {vid_id}: {e}")
                    success = False
                finally:
                    with self.active_downloads_lock:
                        if vid_id in self.active_downloads:
                            del self.active_downloads[vid_id]
                
                if success and downloaded_file:
                    _add_placeholder_tag(downloaded_file)
                    with downloaded_lock:
                        downloaded_filepaths.append(downloaded_file)
                    q['status'] = "Finished"
                else:
                    q['status'] = "Pending"
                    
                if getattr(self, 'cancel_download', False):
                    q['status'] = "Pending"
                self.queue_status_changed_signal.emit(idx)

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
                    [(idx, q) for idx, q in enumerate(self.queue_items) if q['status'] == "Pending"],
                    key=lambda x: x[0]
                )
                if not pending_items or getattr(self, 'cancel_download', False):
                    break
                
                if pass_num > 1:
                    self.status_signal.emit(
                        f"Re-checking queue (Pass {pass_num}: retrying {len(pending_items)} pending downloads)...",
                        False, "#FF8C00"
                    )
                    time.sleep(1.0)
                
                max_workers = min(threads_count, len(pending_items))
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = []
                    for item in pending_items:
                        if getattr(self, 'cancel_download', False):
                            break
                        futures.append(executor.submit(download_single, item))
                    for fut in futures:
                        fut.result()
            
            # --- Verification Pass with Placeholder Tag & Title Matching ---
            if not getattr(self, 'cancel_download', False):
                valid_tagged_files = [f for f in downloaded_filepaths if os.path.exists(f) and os.path.getsize(f) > 1024]
                queued_finished = [q for q in self.queue_items if q['status'] == "Finished"]
                
                if len(valid_tagged_files) < len(queued_finished):
                    missing_items = []
                    for idx, q in enumerate(self.queue_items):
                        if q['status'] == "Finished":
                            title = q['video'].get('title', '')
                            found = any(title.lower() in os.path.basename(f).lower() for f in valid_tagged_files)
                            if not found:
                                q['status'] = "Pending"
                                missing_items.append((idx, q))
                                self.queue_status_changed_signal.emit(idx)
                                
                    if missing_items:
                        missing_items.sort(key=lambda x: x[0])
                        self.status_signal.emit(
                            f"Verification: {len(missing_items)} files missing on disk. Redownloading missing tracks...",
                            False, "#FF8C00"
                        )
                        with ThreadPoolExecutor(max_workers=min(threads_count, len(missing_items))) as executor:
                            futures = [executor.submit(download_single, item) for item in missing_items]
                            for fut in futures:
                                fut.result()
                
                # Strip placeholder verification tag from all confirmed files
                for f in downloaded_filepaths:
                    if os.path.exists(f):
                        _remove_placeholder_tag(f)
            
            self._last_downloaded_files = list(downloaded_filepaths)

            if getattr(self, 'cancel_download', False):
                self.status_signal.emit("Download cancelled.", False, "#E31E24")
            else:
                remaining = [q for q in self.queue_items if q['status'] == "Pending"]
                if remaining:
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
        if self.use_custom_eq and self.custom_eq_string.strip():
            args.append(f'--eq={self.custom_eq_string.strip()}')
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
                cli_args = [
                    "-J",
                    "--format", "bestaudio/best",
                    "--extractor-args", "youtube:player_client=android",
                    "--no-playlist",
                ]
                if getattr(sys, 'frozen', False):
                    cli_args.extend(["--ffmpeg-location", getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))])
                info = run_yt_dlp_json(cli_args + [f"https://www.youtube.com/watch?v={vid_id}"])
                url = info.get('url') if info else None
                if not url and info and 'formats' in info:
                    for f in reversed(info['formats']):
                        if f.get('url') and (f.get('acodec') != 'none' or f.get('vcodec') == 'none'):
                            url = f['url']
                            break
                    if not url and info['formats']:
                        url = info['formats'][-1].get('url')

                if not url:
                    raise Exception("No playable audio stream URL found")

                headers = info.get('http_headers', {}) if info else {}
                user_agent = headers.get('User-Agent', 'com.google.android.youtube/19.29.37 (Linux; U; Android 11)')

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
        if self.vlc_player:
            self.vlc_player.set_position(float(val)/10000.0)

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
        title = getattr(self, 'current_playing_title', '').strip()
        time_txt = ""

        if self.vlc_player and self.current_video_id:
            state = self.vlc_player.get_state()
            if state == vlc.State.Playing:
                self._has_played_current = True
                self._ended_trigger = False
            elif state == vlc.State.Ended:
                # ONLY trigger auto-advance if this track actually played and hasn't triggered ended yet
                if getattr(self, '_has_played_current', False) and not getattr(self, '_ended_trigger', False) and getattr(self, 'is_playing', False):
                    self._ended_trigger = True
                    self._has_played_current = False
                    self.play_next()
                
            pos = self.vlc_player.get_position() * 10000
            ms = self.vlc_player.get_time()
            total_ms = self.vlc_player.get_length()
            if total_ms > 0:
                cur_str = f"{int(ms/60000)}:{int((ms%60000)/1000):02d}"
                tot_str = f"{int(total_ms/60000)}:{int((total_ms%60000)/1000):02d}"
                time_txt = f"{cur_str} / {tot_str}"
                self.time_label.setText(time_txt)
                if not self.progress_slider.isSliderDown():
                    self.progress_slider.blockSignals(True)
                    self.progress_slider.setValue(int(pos))
                    self.progress_slider.blockSignals(False)

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
                scaled_pixmap = pixmap.scaled(90, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self._thumbnail_labels[vid_id].setPixmap(scaled_pixmap)

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

if __name__ == "__main__":
    if len(sys.argv) > 1 and ("--renamer" in sys.argv or "-r" in sys.argv):
        sys.argv = [a for a in sys.argv if a not in ("--renamer", "-r")]
        run_integrated_renamer_cli()
    else:
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        app = QApplication(sys.argv)
        # Title bar + taskbar icon for every window of the app (Qt uses the
        # application icon for any window that does not set its own).
        _window_icon = app_icon()
        if _window_icon is not None:
            app.setWindowIcon(_window_icon)
        window = MainApp()
        window.show()
        ret = app.exec()
        try:
            window.close()
        except Exception:
            pass
        os._exit(ret)
