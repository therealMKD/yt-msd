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
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
try:
    import winreg
except ImportError:
    winreg = None
import yt_dlp
import webbrowser
import urllib.request
import io
import vlc
import shlex
import time
import random
import socket
import struct
import hashlib
from typing import Dict, List, Optional, Tuple, Callable
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
                               QSizePolicy, QStyle, QToolTip, QStyleOption, QSpinBox, QProgressBar)
from PySide6.QtCore import Qt, Signal, QTimer, Slot, QPoint, QRect, QMargins, QThread
from PySide6.QtGui import QIcon, QPixmap, QImage, QAction, QColor, QPalette, QPainter, QBrush, QFont, QDrag
from PySide6.QtCore import QMimeData

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
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, startupinfo=startupinfo)
        return True
    except Exception:
        return False

def measure_loudness(filepath):
    command = [
        "ffmpeg",
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
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(filepath)]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
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

    command = ["ffmpeg", "-y", "-i", str(filepath), "-af", af_chain]
    
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
    command = ["ffmpeg", "-y", "-i", str(filepath), "-af", af_chain]
    
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
    """QPushButton that only triggers its primary action on double-click."""
    doubleClicked = Signal()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        # Absorb single click so it doesn't trigger clicked signal for playback
        # (still allow default visual press styling)
        event.accept()


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
SYNC_CHUNK_SIZE = 64 * 1024


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
    def __init__(self, get_hosted_chains_cb: Callable[[], List[dict]], get_tcp_port_cb: Callable[[], int]):
        self.get_hosted_chains_cb = get_hosted_chains_cb
        self.get_tcp_port_cb = get_tcp_port_cb
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

    def _run_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
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
                        sock.sendto(raw, ('<broadcast>', UDP_BEACON_PORT))
                except Exception:
                    pass

            if is_bound:
                try:
                    msg, addr = sock.recvfrom(2048)
                    data = json.loads(msg.decode('utf-8'))
                    if data.get('type') == 'PROBE':
                        target_code = str(data.get('sync_code', ''))
                        chains = self.get_hosted_chains_cb()
                        tcp_port = self.get_tcp_port_cb()
                        for c in chains:
                            if str(c.get('sync_code')) == target_code and tcp_port > 0:
                                reply = {
                                    'type': 'PROBE_REPLY',
                                    'sync_code': target_code,
                                    'chain_name': c.get('name', 'Audio Playlist'),
                                    'tcp_port': tcp_port,
                                    'host_ip': get_local_ip()
                                }
                                sock.sendto(json.dumps(reply).encode('utf-8'), addr)
                                break
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


def discover_host_on_lan(sync_code: str, timeout: float = 2.5) -> Optional[Tuple[str, int, str]]:
    """Broadcasts a UDP discovery probe for a 4-digit sync code; returns (host_ip, tcp_port, chain_name) or None."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    if sys.platform == 'win32':
        try:
            sock.ioctl(0x9800000C, False)
        except Exception:
            pass
    sock.settimeout(0.4)

    probe = json.dumps({'type': 'PROBE', 'sync_code': str(sync_code)}).encode('utf-8')
    start_time = time.time()
    result = None

    try:
        sock.sendto(probe, ('<broadcast>', UDP_BEACON_PORT))
        while time.time() - start_time < timeout:
            try:
                msg, (sender_ip, _) = sock.recvfrom(2048)
                data = json.loads(msg.decode('utf-8'))
                if data.get('type') == 'PROBE_REPLY' and str(data.get('sync_code')) == str(sync_code):
                    port = int(data.get('tcp_port', 63350))
                    name = data.get('chain_name', 'Audio Playlist')
                    ip = data.get('host_ip') or sender_ip
                    result = (ip, port, name)
                    break
            except socket.timeout:
                try:
                    sock.sendto(probe, ('<broadcast>', UDP_BEACON_PORT))
                except Exception:
                    pass
            except Exception:
                pass
    finally:
        try:
            sock.close()
        except Exception:
            pass
    return result


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
        sock.sendto(payload, ('<broadcast>', UDP_BEACON_PORT))
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
                   progress_cb: Optional[Callable[[int, int, str], None]] = None) -> Tuple[bool, str, int, int]:
        sync_code = str(chain_config.get('sync_code', ''))
        folder_str = chain_config.get('folder_path', '')
        dest_folder = Path(folder_str)
        dest_folder.mkdir(parents=True, exist_ok=True)

        host_ip = chain_config.get('last_known_host_ip', '')
        host_port = int(chain_config.get('host_port', 63350))
        deletion_mode = chain_config.get('deletion_mode', 'mirror')

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

                    def _progress(bytes_done, bytes_total):
                        if progress_cb:
                            progress_cb(bytes_done, bytes_total, name)

                    ok = recv_file_from_socket(sock, target_path, h_size, h_sha256, _progress)
                    if ok:
                        transferred += 1
                        try:
                            os.utime(target_path, (time.time(), h_mtime))
                        except Exception:
                            pass
                elif needs_tag_update:
                    transferred += 1

            return True, f"Synced successfully ({transferred} updated, {deleted} removed).", transferred, deleted
        except Exception as e:
            return False, f"Sync error: {e}", transferred, deleted
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass


class SyncConfigManager:
    """Manages persistence of sync_config.json for hosted and client chains."""
    def __init__(self, config_dir: str):
        self.config_file = os.path.join(config_dir, "sync_config.json")
        self.settings: dict = {"auto_sync_interval_mins": 30, "firewall_prompted": False}
        self.hosted_chains: List[dict] = []
        self.client_chains: List[dict] = []
        self.load()

    def load(self):
        if not os.path.exists(self.config_file):
            return
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.settings = data.get('settings', self.settings)
                self.hosted_chains = data.get('hosted_chains', [])
                self.client_chains = data.get('client_chains', [])
        except Exception:
            pass

    def save(self):
        data = {
            'settings': self.settings,
            'hosted_chains': self.hosted_chains,
            'client_chains': self.client_chains
        }
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception:
            pass

    def generate_unique_sync_code(self) -> str:
        import random
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
                         host_port: int = 63350, deletion_mode: str = 'mirror') -> dict:
        chain = {
            'id': f'cc_{sync_code}',
            'sync_code': sync_code,
            'name': name,
            'folder_path': folder_path,
            'last_known_host_ip': host_ip,
            'host_port': host_port,
            'deletion_mode': deletion_mode,
            'created_at': time.time(),
            'last_synced': 0,
            'status': 'Pending Sync'
        }
        self.client_chains.append(chain)
        self.save()
        return chain

    def remove_chain(self, chain_id: str):
        self.hosted_chains = [c for c in self.hosted_chains if c.get('id') != chain_id]
        self.client_chains = [c for c in self.client_chains if c.get('id') != chain_id]
        self.save()


class ClientSyncThread(QThread):
    status_signal = Signal(str)
    progress_signal = Signal(int, int, str)
    finished_signal = Signal(bool, str, int, int)

    def __init__(self, chain_config: dict):
        super().__init__()
        self.chain_config = chain_config

    def run(self):
        def _status(txt):
            self.status_signal.emit(txt)

        def _progress(done, total, filename):
            self.progress_signal.emit(done, total, filename)

        ok, msg, transferred, deleted = SyncClientWorker.sync_chain(
            self.chain_config,
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
        cancel_btn.clicked.connect(self.reject)
        btn_h.addWidget(cancel_btn)

        create_btn = QPushButton("Create Chain")
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
        self.setFixedSize(540, 420)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title_lbl = QLabel("CONNECT TO A REMOTE SYNC CHAIN")
        title_lbl.setFont(QFont("Segoe UI Semibold", 11))
        layout.addWidget(title_lbl)

        desc = QLabel("Enter the Host PC's IP and 4-digit Sync Code, or use auto-discovery on your local network.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(desc)

        layout.addWidget(QLabel("Host Computer IP Address:"))
        ip_h = QHBoxLayout()
        self.ip_edit = QLineEdit()
        self.ip_edit.setPlaceholderText("e.g. 192.168.1.50")
        ip_h.addWidget(self.ip_edit, 1)

        self.discover_btn = QPushButton("🔍 Discover on LAN")
        self.discover_btn.clicked.connect(self._discover_on_lan)
        ip_h.addWidget(self.discover_btn)
        layout.addLayout(ip_h)

        layout.addWidget(QLabel("4-Digit Sync Code:"))
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("e.g. 1002")
        self.code_edit.setFixedWidth(100)
        layout.addWidget(self.code_edit)

        layout.addWidget(QLabel("Local Folder where files should be synced:"))
        folder_h = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Base folder (e.g. C:\\Music)...")
        folder_h.addWidget(self.folder_edit, 1)

        browse_btn = QPushButton("Browse...")
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
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color: #3B8ED0; font-size: 11px;")
        btn_h.addWidget(self.status_lbl, 1)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_h.addWidget(cancel_btn)

        connect_btn = QPushButton("Connect & Join")
        connect_btn.clicked.connect(self._connect_chain)
        btn_h.addWidget(connect_btn)
        layout.addLayout(btn_h)

    def _browse_base_folder(self):
        f = QFileDialog.getExistingDirectory(self, "Select Base Music Directory", self.folder_edit.text() or "")
        if f:
            self.folder_edit.setText(f)

    def _discover_on_lan(self):
        code = self.code_edit.text().strip()
        if not code:
            QMessageBox.information(self, "Sync Code Needed", "Please enter the 4-digit Sync Code first to search for its host on LAN.")
            return

        self.status_lbl.setText("Searching local network for host...")
        self.discover_btn.setEnabled(False)

        def _bg():
            found = discover_host_on_lan(code, timeout=3.0)
            def _ui():
                self.discover_btn.setEnabled(True)
                if found:
                    host_ip, host_port, chain_name = found
                    self.ip_edit.setText(host_ip)
                    if not self.playlist_name_edit.text().strip():
                        self.playlist_name_edit.setText(chain_name)
                    self.status_lbl.setText(f"✔ Found Host '{chain_name}' at {host_ip}")
                    self.status_lbl.setStyleSheet("color: #1abd33; font-size: 11px;")
                else:
                    self.status_lbl.setText("✘ No host found on LAN for this code.")
                    self.status_lbl.setStyleSheet("color: #E31E24; font-size: 11px;")
            QTimer.singleShot(0, _ui)

        threading.Thread(target=_bg, daemon=True).start()

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


class SyncManagerDialog(QDialog):
    """Main Sync Chains Management Dialog with Host & Client chain cards and live transfer tracking."""
    def __init__(self, parent_app):
        super().__init__(parent_app)
        self.parent_app = parent_app
        self.config_manager: SyncConfigManager = parent_app.sync_config_manager
        self.setWindowTitle("Sync Chains Manager - Local Network Playlist Sync")
        self.resize(880, 600)

        # Trigger firewall socket binding if opening for the first time
        if not self.config_manager.settings.get('firewall_prompted', False):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('', SYNC_PORT_START))
                s.listen(1)
                s.close()
                self.config_manager.settings['firewall_prompted'] = True
                self.config_manager.save()
            except Exception:
                pass

        self.sync_threads = {}

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(12)

        top_bar = QHBoxLayout()
        local_ip = get_local_ip()
        self.ip_badge = QLabel(f"🖥️  Your Local IP: <b>{local_ip}</b>")
        self.ip_badge.setStyleSheet("background: rgba(59, 142, 208, 0.15); border: 1px solid #3B8ED0; padding: 6px 12px; border-radius: 4px; font-size: 12px;")
        top_bar.addWidget(self.ip_badge)

        copy_ip_btn = QPushButton("Copy IP")
        copy_ip_btn.setFixedWidth(75)
        copy_ip_btn.clicked.connect(lambda: QApplication.clipboard().setText(local_ip))
        top_bar.addWidget(copy_ip_btn)

        top_bar.addStretch()

        create_btn = QPushButton("➕ Create Chain (Host)")
        create_btn.clicked.connect(self._open_create_dialog)
        top_bar.addWidget(create_btn)

        connect_btn = QPushButton("🔗 Connect Chain (Client)")
        connect_btn.clicked.connect(self._open_connect_dialog)
        top_bar.addWidget(connect_btn)

        sync_all_btn = QPushButton("🔄 Force Sync All")
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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("scrollContent")

        self.cards_container = QWidget()
        self.cards_container.setObjectName("scrollContent")
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        self.cards_layout.setSpacing(10)
        scroll.setWidget(self.cards_container)
        main_layout.addWidget(scroll, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        main_layout.addLayout(footer)

        self.refresh_cards()

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

    def refresh_cards(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        hosted = self.config_manager.hosted_chains
        clients = self.config_manager.client_chains

        if not hosted and not clients:
            empty_lbl = QLabel("No active Sync Chains. Click 'Create Chain' to host a folder or 'Connect Chain' to join an existing one.")
            empty_lbl.setAlignment(Qt.AlignCenter)
            empty_lbl.setStyleSheet("color: #888; padding: 40px; font-size: 13px;")
            self.cards_layout.addWidget(empty_lbl)
            self.cards_layout.addStretch()
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

        self.cards_layout.addStretch()

    def _build_host_card(self, hc: dict) -> QWidget:
        card = QFrame()
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
        copy_code_btn.setFixedWidth(80)
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
        folder_path = Path(folder_str)
        audio_cnt = len(filter_audio_files(folder_path)) if folder_path.is_dir() else 0

        info_h = QHBoxLayout()
        path_lbl = QLabel(f"📁 {folder_str} ({audio_cnt} tracks)")
        path_lbl.setStyleSheet("color: #888; font-size: 11px;")
        info_h.addWidget(path_lbl, 1)

        open_btn = QPushButton("Open Folder")
        open_btn.setFixedWidth(90)
        open_btn.clicked.connect(lambda chk=False, f=folder_str: os.startfile(f) if Path(f).exists() else None)
        info_h.addWidget(open_btn)

        l.addLayout(info_h)
        return card

    def _build_client_card(self, cc: dict) -> QWidget:
        card = QFrame()
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

        sync_btn = QPushButton("🔄 Sync Now")
        sync_btn.clicked.connect(lambda chk=False, c=cc: self._sync_single_client_chain(c))
        header.addWidget(sync_btn)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(26, 26)
        del_btn.setToolTip("Remove this client sync chain")
        del_btn.setStyleSheet("background: #E31E24; color: white; border: none; border-radius: 3px; font-weight: bold;")
        cid_val = cc.get('id')
        del_btn.clicked.connect(lambda chk=False, cid=cid_val: self._delete_chain(cid))
        header.addWidget(del_btn)

        l.addLayout(header)

        folder_str = cc.get('folder_path', '')
        last_sync = cc.get('last_synced', 0)
        last_sync_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_sync)) if last_sync > 0 else "Never"
        del_mode = cc.get('deletion_mode', 'mirror').capitalize()

        status_lbl = QLabel(f"Status: {cc.get('status', 'Idle')}  |  Last Synced: {last_sync_str}  |  Mode: {del_mode}")
        status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        card.setProperty("status_lbl", status_lbl)
        l.addWidget(status_lbl)

        info_h = QHBoxLayout()
        path_lbl = QLabel(f"📁 {folder_str}")
        path_lbl.setStyleSheet("color: #888; font-size: 11px;")
        info_h.addWidget(path_lbl, 1)

        open_btn = QPushButton("Open Folder")
        open_btn.setFixedWidth(90)
        open_btn.clicked.connect(lambda chk=False, f=folder_str: os.startfile(f) if Path(f).exists() else None)
        info_h.addWidget(open_btn)

        l.addLayout(info_h)
        return card

    def _delete_chain(self, chain_id: str):
        if QMessageBox.question(self, "Confirm Removal", "Are you sure you want to remove this sync chain? (Audio files on disk will remain untouched)") == QMessageBox.Yes:
            self.config_manager.remove_chain(chain_id)
            if hasattr(self.parent_app, 'refresh_sync_watchers'):
                self.parent_app.refresh_sync_watchers()
            self.refresh_cards()

    def _sync_single_client_chain(self, cc: dict):
        cid = cc.get('id')
        if cid in self.sync_threads and self.sync_threads[cid].isRunning():
            return

        cc['status'] = "Syncing..."
        self.refresh_cards()

        thread = ClientSyncThread(cc)
        self.sync_threads[cid] = thread

        def _on_finish(ok, msg, transferred, deleted):
            cc['status'] = "Up to date" if ok else f"Failed: {msg}"
            if ok:
                cc['last_synced'] = time.time()
            self.config_manager.save()
            self.refresh_cards()
            if self.parent_app.local_current_path == cc.get('folder_path'):
                self.parent_app.refresh_local_list()

        thread.finished_signal.connect(_on_finish)
        thread.start()

    def _force_sync_all(self):
        for cc in self.config_manager.client_chains:
            self._sync_single_client_chain(cc)


class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("Settings")
        self.setMinimumWidth(820)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)
        
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
        self.args_edit = QLineEdit(parent.custom_args)
        self.args_edit.setPlaceholderText("Arguments...")
        self.args_edit.setEnabled(parent.use_custom_args)
        self.args_edit.textChanged.connect(self._update_args)
        arg_h.addWidget(self.args_edit, 1)
        left_layout.addLayout(arg_h)
        left_layout.addWidget(QLabel("Manual override ignores GUI bitrate/format settings.", font=QFont("Segoe UI", 8)))
        
        # OPTIONS
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
        self.eq_edit = QLineEdit(parent.custom_eq_string)
        self.eq_edit.setPlaceholderText("e.g. equalizer=f=100:width_type=o:width=2:g=-10")
        self.eq_edit.setEnabled(parent.use_custom_eq)
        self.eq_edit.textChanged.connect(self._update_eq)
        eq_h.addWidget(self.eq_edit, 1)
        right_layout.addLayout(eq_h)
        right_layout.addWidget(QLabel("Appended to the ffmpeg filter chain during normalization.",
                                      font=QFont("Segoe UI", 8)))

        # Custom normalization command override (replaces built-in filter chain)
        right_layout.addWidget(QLabel("CUSTOM NORM/TRIM COMMAND OVERRIDE (ADVANCED)", font=QFont("Segoe UI Semibold", 10)))
        norm_cmd_h = QHBoxLayout()
        self.norm_cmd_cb = QCheckBox()
        self.norm_cmd_cb.setChecked(parent.use_custom_norm_cmd)
        self.norm_cmd_cb.toggled.connect(self._toggle_norm_cmd)
        norm_cmd_h.addWidget(self.norm_cmd_cb)
        self.norm_cmd_edit = QLineEdit(parent.custom_norm_cmd)
        self.norm_cmd_edit.setPlaceholderText("e.g. loudnorm=I=-16:TP=-1.5:LRA=11")
        self.norm_cmd_edit.setEnabled(parent.use_custom_norm_cmd)
        self.norm_cmd_edit.textChanged.connect(self._update_norm_cmd)
        norm_cmd_h.addWidget(self.norm_cmd_edit, 1)
        right_layout.addLayout(norm_cmd_h)
        right_layout.addWidget(QLabel("Replaces the entire -af filter chain for normalization AND silence trim.",
                                      font=QFont("Segoe UI", 8)))
        right_layout.addStretch()
        
        columns_layout.addWidget(left_widget, 1)
        columns_layout.addWidget(divider)
        columns_layout.addWidget(right_widget, 1)
        
        main_layout.addLayout(columns_layout)
        
        # FOOTER / RESET & SYNC
        footer = QHBoxLayout()
        self.reset_btn = QPushButton("Reset to Default Config")
        self.reset_btn.setObjectName("topIconBtn")
        self.reset_btn.clicked.connect(self._reset_defaults)
        footer.addWidget(self.reset_btn)

        self.sync_btn = QPushButton("🔗 Sync Chains Manager")
        self.sync_btn.clicked.connect(self._open_sync_manager)
        footer.addWidget(self.sync_btn)

        footer.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setFixedWidth(100)
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
        global CUSTOM_NORM_CMD
        CUSTOM_NORM_CMD = self.parent.custom_norm_cmd if state else ""
        self.parent.save_config()

    def _update_norm_cmd(self, text):
        self.parent.custom_norm_cmd = text
        global CUSTOM_NORM_CMD
        if self.parent.use_custom_norm_cmd:
            CUSTOM_NORM_CMD = text
        self.parent.save_config()

    def _open_sync_manager(self):
        dlg = SyncManagerDialog(self.parent)
        dlg.exec()

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
        cancel_btn.clicked.connect(self.reject)
        open_btn = QPushButton("Open Playlist")
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

    def __init__(self):
        super().__init__()
        self.setWindowTitle("yt-msd | YouTube Media Downloader")
        self.resize(1640, 850)
        
        # State Arrays
        self.search_results = []
        self.queue_items = []
        self.local_folders = []
        self.recent_folders = []
        self.recent_playlists = []
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
        self.shuffle_order = []
        self.is_muted = False
        self.active_downloads = {}
        self.active_downloads_lock = threading.Lock()
        
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

        self.player_timer = QTimer(self)
        self.player_timer.timeout.connect(self.update_player_ui)
        self.player_timer.start(16)

        self.setup_tray()
        self._update_local_rescan_timer()

        # Initialize VLC in a background thread (plugin scanning can take seconds)
        _startup_pool = ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 4))
        _startup_pool.submit(self._init_vlc_background)
        _startup_pool.shutdown(wait=False)

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
        self.sync_host_server = SyncHostServer(lambda: self.sync_config_manager.hosted_chains)
        self.udp_beacon = UDPBeaconBroadcaster(
            lambda: self.sync_config_manager.hosted_chains,
            lambda: self.sync_host_server.active_port
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
        if self.local_current_path and os.path.exists(self.local_current_path):
            self.refresh_local_list()

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
        """Called when a hosted folder has changed after the debounce timer elapses."""
        port = self.sync_host_server.active_port if hasattr(self, 'sync_host_server') else 63350
        send_lan_update_notification(sync_code, port)
        self._on_status_update(f"Sync Chain (Code {sync_code}) updated. Notified clients on LAN.", False, "#1abd33")

    def _update_sync_timer(self):
        if hasattr(self, 'sync_config_manager') and hasattr(self, 'sync_timer'):
            mins = self.sync_config_manager.settings.get('auto_sync_interval_mins', 30)
            if mins > 0:
                self.sync_timer.start(mins * 60 * 1000)
            else:
                self.sync_timer.stop()

    def _auto_sync_client_chains(self):
        """Background routine that runs sync checks for all client sync chains."""
        if not hasattr(self, 'sync_config_manager') or not self.sync_config_manager.client_chains:
            return

        def _bg():
            for cc in list(self.sync_config_manager.client_chains):
                ok, msg, transferred, deleted = SyncClientWorker.sync_chain(cc)
                if ok:
                    cc['last_synced'] = time.time()
                    cc['status'] = "Up to date"
                    if transferred > 0 or deleted > 0:
                        self.status_signal.emit(f"Sync Chain '{cc.get('name')}': {transferred} updated, {deleted} removed.", False, "#1abd33")
                        if self.local_current_path == cc.get('folder_path'):
                            QTimer.singleShot(0, self.refresh_local_list)
                else:
                    cc['status'] = f"Host Offline"
            self.sync_config_manager.save()

        threading.Thread(target=_bg, daemon=True).start()

    def _init_vlc_background(self):
        """Initialize libVLC in a background thread to avoid blocking the UI during plugin scanning."""
        try:
            instance = vlc.Instance('--quiet', '--no-video')
            player = instance.media_player_new()
            # Switch to main-thread ownership safely
            self.vlc_instance = instance
            self.vlc_player = player
            if self.vlc_player:
                self.vlc_player.audio_set_volume(self.volume_val)
            self._vlc_ready = True
        except Exception:
            self.vlc_instance = None
            self.vlc_player = None
            self._vlc_ready = True  # Still mark ready so playback attempts don't hang


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
                    if hasattr(self, 'local_rescan_timer'):
                        self._update_local_rescan_timer()
                    if self.save_place:
                        self.session_data = c.get('session_data', {})
        except Exception: pass
        if not self.recent_folders:
            self.recent_folders = [default_dl]; self.download_path = default_dl

    def save_config(self):
        c = {
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
            'session_data': {
                'search_results': self.search_results,
                'playback_index': self.playback_index,
                'current_video_id': self.current_video_id,
                'local_current_path': self.local_current_path,
                'local_playback_index': getattr(self, 'local_playback_index', -1)
            }
        }
        try:
            with open(self.config_path, 'w') as f: json.dump(c, f, indent=4)
        except: pass

    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        
        # Generate Icon safely
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor("transparent"))
        painter = QPainter(pixmap)
        painter.setBrush(QColor(get_accent_color(self.accent_color_name)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(8, 8, 48, 48)
        painter.end()
        self.tray_icon.setIcon(QIcon(pixmap))
        
        menu = QMenu(self)
        restore_action = menu.addAction("Restore")
        restore_action.triggered.connect(self.showNormal)
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(QApplication.quit)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def changeEvent(self, event):
        if event.type() == event.Type.WindowStateChange:
            if self.isMinimized() and self.minimize_to_tray:
                self.hide()
        super().changeEvent(event)

    def closeEvent(self, event):
        self.save_config()
        if self.vlc_player: self.vlc_player.stop()
        if hasattr(self, 'sync_host_server'): self.sync_host_server.stop()
        if hasattr(self, 'udp_beacon'): self.udp_beacon.stop()
        if hasattr(self, 'host_watcher'): self.host_watcher.stop_all()
        super().closeEvent(event)

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
        self.prev_btn.setToolTip("Previous track")
        self.prev_btn.clicked.connect(self.play_previous)
        c.addWidget(self.prev_btn)
        
        self.play_btn = QPushButton("\uE768")
        self.play_btn.setObjectName("playerPlayBtn")
        self.play_btn.setToolTip("Play / Pause")
        self.play_btn.clicked.connect(self.toggle_playback)
        c.addWidget(self.play_btn)
        
        self.next_btn = QPushButton("\uE893")
        self.next_btn.setObjectName("playerBtn")
        self.next_btn.setToolTip("Next track")
        self.next_btn.clicked.connect(self.play_next)
        c.addWidget(self.next_btn)
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
        local_browse_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px; padding: 0px;")
        local_browse_btn.setFixedSize(36, 30)
        local_browse_btn.clicked.connect(lambda: self.load_local_folder(QFileDialog.getExistingDirectory(self)))
        h.addWidget(local_browse_btn)
        h.addSpacing(6)
        l.addLayout(h)
        
        self.local_meta_cb = QCheckBox("Show Metadata")
        self.local_meta_cb.setChecked(getattr(self, 'show_local_metadata', False))
        self.local_meta_cb.stateChanged.connect(self.toggle_local_metadata)
        l.addWidget(self.local_meta_cb)
        
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

        self.setStyleSheet("""
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
                font-size: 14px;
                font-weight: normal;
                border-radius: 4px;
                padding: 0px 4px;
            }}
            QPushButton#playerBtn:hover {{
                background-color: {btn_hover};
            }}
            QPushButton#playerPlayBtn {{
                background-color: transparent;
                color: {fg};
                font-family: 'Segoe MDL2 Assets';
                font-size: 22px;
                font-weight: normal;
                border-radius: 6px;
                padding: 0px 4px;
            }}
            QPushButton#playerPlayBtn:hover {{
                background-color: {btn_hover};
            }}
            QToolTip {{
                background-color: {frame_bg};
                color: {fg};
                border: 1px solid {input_border};
                padding: 2px 6px;
                border-radius: 4px;
                font-family: 'Segoe UI';
                font-size: 10px;
                font-weight: normal;
                show-delay: 4000ms;
            }}
        """.format(
            bg=bg, fg=fg, frame_bg=frame_bg, input_bg=input_bg, input_border=input_border,
            scroll_bg=scroll_bg, splitter_handle=splitter_handle, slider_bg=slider_bg,
            hover_bg=hover_bg, hover_fg=hover_fg, accent=accent, accent_fg=accent_fg,
            queue_item_bg=queue_item_bg, queue_item_bg_finished=queue_item_bg_finished,
            btn_hover=btn_hover, checkmark_path=checkmark_path, downarrow_path=downarrow_path,
            main_btn_border=main_btn_border, secondary_fg=secondary_fg
        ))

    # --- Local Folder Logic ---
    def load_local_folder(self, path):
        if not path or not os.path.exists(path): return
        path = os.path.abspath(path)
        self.local_current_path = path
        
        self.local_path_combo.blockSignals(True)
        if path not in self.local_folders:
            self.local_folders.insert(0, path)
            self.local_folders = self.local_folders[:5]
            self.local_path_combo.clear()
            self.local_path_combo.addItems(self.local_folders)
            
        self.local_path_combo.setCurrentText(path)
        self.local_path_combo.blockSignals(False)
        self.save_config()
        self.refresh_local_list()

    def toggle_local_metadata(self, state):
        self.show_local_metadata = (state == Qt.Checked.value)
        self.save_config()
        self.refresh_local_list()

    def refresh_local_list(self):
        while self.local_vbox.count():
            item = self.local_vbox.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        if not self.local_current_path or not os.path.exists(self.local_current_path): return
        
        items = []
        try:
            parent = os.path.dirname(self.local_current_path)
            if parent and parent != self.local_current_path:
                items.append({'name': ".. (Back)", 'path': parent, 'is_dir': True})
            with os.scandir(self.local_current_path) as current_dir:
                for entry in current_dir:
                    if entry.is_dir():
                        items.append({'name': entry.name, 'path': entry.path, 'is_dir': True})
                    elif entry.is_file():
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in AUDIO_EXTENSIONS:
                            items.append({'name': entry.name, 'path': entry.path, 'is_dir': False})
        except: pass
        
        items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        self.current_local_items = items
        
        self.local_btns = []
        for item in items:
            raw_title = item.get('meta_name', item['name']) if getattr(self, 'show_local_metadata', False) else item['name']
            escaped_title = raw_title.replace('&', '&&')
            if item['is_dir']:
                btn = QPushButton(f"📁  {escaped_title}")
                btn.setObjectName("transparentBtn")
                btn.setToolTip("Open folder")
                btn.clicked.connect(lambda checked=False, i=item: self._on_local_click(i))
                self.local_vbox.addWidget(btn)
            else:
                row_w = QWidget()
                row_l = QHBoxLayout(row_w)
                row_l.setContentsMargins(0, 0, 0, 0)
                row_l.setSpacing(4)
                
                btn = DoubleClickButton(f"🎵  {escaped_title}")
                btn.setObjectName("transparentBtn")
                btn.setToolTip("Double-click to play")
                btn.doubleClicked.connect(lambda i=item: self._on_local_click(i))
                row_l.addWidget(btn, 1)
                
                dur_lbl = QLabel(item.get('duration_str', ''))
                dur_lbl.setObjectName("durationLabel")
                dur_lbl.setStyleSheet("border: none; background: transparent; padding-right: 6px;")
                row_l.addWidget(dur_lbl)
                
                self.local_vbox.addWidget(row_w)
                self.local_btns.append((btn, dur_lbl, item))
                
        if self.local_btns:
            self._fetch_local_metadata_bg()
            
    def _fetch_local_metadata_bg(self):
        from PySide6.QtCore import QObject, Signal
        class MetaWorker(QObject):
            meta_done = Signal(object, object, object)
            
        self._meta_worker = MetaWorker()
        self._meta_worker.meta_done.connect(
            lambda b, d_lbl, i: (
                b.setText(f"🎵  {(i.get('meta_name', i['name']) if getattr(self, 'show_local_metadata', False) else i['name']).replace('&', '&&')}"),
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

    def _on_local_click(self, item, paused_at_start=False):
        if item['is_dir']: 
            self.load_local_folder(item['path'])
        else:
            # If VLC is still initializing in background, retry after a short delay
            if self.vlc_instance is None or self.vlc_player is None:
                QTimer.singleShot(200, lambda: self._on_local_click(item, paused_at_start))
                return

            display_name = item.get('meta_name', item['name']) if getattr(self, 'show_local_metadata', False) else item['name']
            self._on_status_update(f"Playing Local: {display_name}", False, "#3B8ED0")
            url = item['path'].replace("\\", "/")
            if not url.startswith("file:///"): url = "file:///" + url
            self.current_video_id = "local"
            
            audio_files = [x for x in getattr(self, 'current_local_items', []) if x.get('is_dir') is False]
            for i, af in enumerate(audio_files):
                if af.get('path') == item.get('path'):
                    self.local_playback_index = i
                    break
                    
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

    def toggle_thumbnails(self, state):
        self.show_thumbnails = state == Qt.Checked.value
        self.save_config()
        if self.search_results:
            self._on_search_results(self.search_results, False)

    def open_settings_dialog(self):
        d = SettingsDialog(self)
        d.exec()

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
                    ydl_opts = {
                        'quiet': True,
                        'extract_flat': True,
                        'playlist_items': '1-100'
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(query, download=False)
                    
                    if info and 'entries' in info:
                        res = [e for e in info['entries'] if e]
                        if len(info['entries']) >= 100:
                            start_idx = 101
                            chunk_size = 100
                            while True:
                                self.status_signal.emit(f"Searching... (Retrieved {len(res)} items)", False, "#3B8ED0")
                                ydl_opts_chunk = {
                                    'quiet': True,
                                    'extract_flat': True,
                                    'playlist_items': f"{start_idx}-{start_idx + chunk_size - 1}"
                                }
                                with yt_dlp.YoutubeDL(ydl_opts_chunk) as ydl_chunk:
                                    chunk_info = ydl_chunk.extract_info(query, download=False)
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
                    with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                        info = ydl.extract_info(f"ytsearch15:{query}", download=False)
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
            except Exception:
                self.search_failed_signal.emit()
                
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
            pbtn.setFixedWidth(40)
            pbtn.setObjectName("iconBtn")
            pbtn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px;")
            pbtn.clicked.connect(lambda checked=False, v=video: self.play_result(v))
            l.addWidget(pbtn)
            
        title = video.get('title', 'Unknown')
        if len(title) > 55: title = title[:52] + "..."
        cb = QCheckBox(f"{title.replace('&', '&&')}")
        cb.setProperty("video_id", video.get('id', ''))
        
        # Persist checked state
        cb.setChecked(video.get('id') in queue_ids)
            
        cb.stateChanged.connect(lambda state, v=video: self.toggle_queue(v, state))
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
                    ydl_opts = {
                        'format': 'bestaudio/best',
                        'outtmpl': f"{folder}/%(title)s.%(ext)s",
                        'postprocessors': [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': target_format,
                            'preferredquality': self.bitrate_combo.currentText(),
                        }],
                        'progress_hooks': [self._dl_progress_hook],
                        'quiet': True,
                        'retries': 15,
                        'fragment_retries': 15,
                        'file_access_retries': 10,
                        'ignoreerrors': False,
                    }
                    if getattr(sys, 'frozen', False):
                        ydl_opts['ffmpeg_location'] = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
                        
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid_id}", download=True)
                        if info:
                            raw_name = ydl.prepare_filename(info)
                            base, _ = os.path.splitext(raw_name)
                            candidate = f"{base}.{target_format}"
                            if os.path.exists(candidate) and os.path.getsize(candidate) > 1024:
                                downloaded_file = candidate
                                success = True
                            else:
                                matching = glob.glob(f"{glob.escape(base)}.*")
                                for m in matching:
                                    if os.path.exists(m) and os.path.getsize(m) > 1024:
                                        downloaded_file = m
                                        success = True
                                        break
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
                pending_items = [(idx, q) for idx, q in enumerate(self.queue_items) if q['status'] == "Pending"]
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

        executable = sys.executable
        if getattr(sys, 'frozen', False):
            executable = "python"
        else:
            idx = executable.lower().rfind("pythonw")
            if idx != -1:
                executable = executable[:idx] + "python" + executable[idx+7:]

        gui_script = os.path.abspath(__file__)

        args = [executable, gui_script, "--renamer", folder]
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

    def _dl_progress_hook(self, d):
        if getattr(self, 'cancel_download', False):
            raise Exception("Download cancelled by user")
            
        info = d.get('info_dict') or {}
        vid_id = info.get('id') if isinstance(info, dict) else None
        if not vid_id:
            return

        finished_cnt = len([q for q in getattr(self, 'queue_items', []) if q.get('status') == "Finished"])
        total_cnt = getattr(self, '_batch_total_count', len(getattr(self, 'queue_items', [])))
        prog_prefix = f"({finished_cnt}/{total_cnt}) " if total_cnt > 0 else ""
            
        if d['status'] == 'downloading':
            p = d.get('_percent_str', '').strip()
            p = re.sub(r'\x1b\[[0-9;]*m', '', p)
            if p:
                with self.active_downloads_lock:
                    self.active_downloads[vid_id] = p
                    vals = list(self.active_downloads.values())
                    if len(vals) > 5:
                        self.dl_progress_signal.emit(
                            f"{prog_prefix}Downloading: {', '.join(vals[:5])} (+{len(vals)-5} more)")
                    else:
                        self.dl_progress_signal.emit(f"{prog_prefix}Downloading: {', '.join(vals)}")
        elif d['status'] == 'finished':
            with self.active_downloads_lock:
                if vid_id in self.active_downloads:
                    del self.active_downloads[vid_id]
                if self.active_downloads:
                    vals = list(self.active_downloads.values())
                    if len(vals) > 5:
                        self.dl_progress_signal.emit(
                            f"{prog_prefix}Downloading: {', '.join(vals[:5])} (+{len(vals)-5} more)")
                    else:
                        self.dl_progress_signal.emit(f"{prog_prefix}Downloading: {', '.join(vals)}")
                else:
                    self.dl_progress_signal.emit(f"{prog_prefix}Processing...")

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

    def play_result(self, video, paused_at_start=False):
        # If VLC is still initializing in background, defer and retry
        if self.vlc_instance is None or self.vlc_player is None:
            QTimer.singleShot(200, lambda: self.play_result(video, paused_at_start))
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
                
        def bg_fetch():
            try:
                ydl_opts = {
                    'quiet': True,
                    'format': 'bestaudio/best',
                    'extractor_args': {'youtube': {'player_client': ['android']}},
                    'noplaylist': True
                }
                if getattr(sys, 'frozen', False):
                    ydl_opts['ffmpeg_location'] = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
                    
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid_id}", download=False)
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
        if event.type() == event.Type.KeyPress and event.key() == Qt.Key_Space:
            fw = QApplication.focusWidget()
            if not isinstance(fw, QLineEdit):
                self.toggle_playback()
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
            
    def play_previous(self):
        if self.current_video_id == "local" and hasattr(self, 'local_playback_index'):
            audio_files = [x for x in getattr(self, 'current_local_items', []) if x.get('is_dir') is False]
            if self.local_playback_index > 0:
                self.local_playback_index -= 1
                self._on_local_click(audio_files[self.local_playback_index])
            return
            
        if self.playback_index > 0:
            self.playback_index -= 1
            self.play_result(self.search_results[self.playback_index])
            
    def play_next(self):
        if self.current_video_id == "local" and hasattr(self, 'local_playback_index'):
            audio_files = [x for x in getattr(self, 'current_local_items', []) if x.get('is_dir') is False]
            if self.local_playback_index + 1 < len(audio_files):
                self.local_playback_index += 1
                self._on_local_click(audio_files[self.local_playback_index])
            return
            
        if self.playback_index + 1 < len(self.search_results):
            self.playback_index += 1
            self.play_result(self.search_results[self.playback_index])

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
        if not self.vlc_player or not self.current_video_id: return
        
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
            self.time_label.setText(f"{cur_str} / {tot_str}")
            if not self.progress_slider.isSliderDown():
                self.progress_slider.blockSignals(True)
                self.progress_slider.setValue(int(pos))
                self.progress_slider.blockSignals(False)

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
        QToolTip.setFont(QFont("Segoe UI", 9))
        window = MainApp()
        window.show()
        sys.exit(app.exec())