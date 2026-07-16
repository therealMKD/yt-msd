#!/usr/bin/env python3
import os
import re
import sys
import subprocess
import tempfile
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Enable ANSI escape sequences on Windows for beautiful terminal output
if sys.platform == "win32":
    os.system("")

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

# Thread lock for clean console output during multithreading
print_lock = threading.Lock()

def safe_print(msg):
    with print_lock:
        print(msg)

available_threads = os.cpu_count()

# ==========================================
# LOUDNESS NORMALIZATION SETTINGS (For Music)
# ==========================================
TARGET_LUFS = "-16"       # Balanced loudness target for music listening
TRUE_PEAK = "-1.5"        # Prevents clipping
LOUDNESS_RANGE = "11"     # LRA of 11 preserves dynamics (not squishing music range)
BITRATE = "320k"          # High quality output bitrate
MAX_WORKERS = available_threads // 2  # Auto-adjusts to half of available threads
# ==========================================

# Attempt to load mutagen for ID3 (MP3) and MP4 (M4A) tagging support
MUTAGEN_AVAILABLE = False
try:
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import ID3NoHeaderError
    from mutagen.easymp4 import EasyMP4
    MUTAGEN_AVAILABLE = True
except ImportError:
    pass

def print_banner():
    banner = rf"""{Colors.CYAN}{Colors.BOLD}                                                  
 _____ _____ ___    _____                           
|     |  _  |_  |  | __  |___ ___ ___ _____ ___ ___ 
| | | |   __|_  |  |    -| -_|   | .'|     | -_|  _|
|_|_|_|__|  |___|  |__|__|___|_|_|__,|_|_|_|___|_|  
{Colors.END}"""
    print(banner)
    print(f"{Colors.BOLD}Interactive MP3/M4A Renamer, Tagger & Loudness Normalizer{Colors.END}")
    print(f"{Colors.BOLD}Available CPU Threads: {available_threads}{Colors.END}\n")
    print(f"{Colors.BOLD}Using {MAX_WORKERS} CPU Threads for Processing{Colors.END}\n")

    if MUTAGEN_AVAILABLE:
        print(f"{Colors.GREEN}[✓] Mutagen library active. Automatic metadata tagging is enabled.{Colors.END}\n")
    else:
        print(f"{Colors.YELLOW}[!] Mutagen library not found. Metadata tagging will be disabled.{Colors.END}")
        print(f"{Colors.DIM}    Run 'pip install mutagen' in your terminal to enable tagging.{Colors.END}")
        print(f"{Colors.DIM}    Continuing in Rename-Only mode.{Colors.END}\n")

def select_folder():
    """
    Selects a folder using a GUI dialog, falling back to command-line input.
    """
    print(f"{Colors.BLUE}Please select the folder containing your audio files...{Colors.END}")
    folder_path = ""
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.withdraw()  # Hide the main root window
        root.focus_force()  # Focus on the upcoming dialog
        folder_path = filedialog.askdirectory(title="Select Audio Folder (MP3/M4A)")
        root.destroy()
    except Exception:
        # Fallback if Tkinter is not installed or GUI is unsupported
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

def is_romanized(text):
    # Check if the text contains non-romanized scripts (CJK, Cyrillic, Greek, Arabic)
    non_roman = re.search(
        r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af\u0400-\u04ff\u0370-\u03ff\u0600-\u06ff]',
        text
    )
    return non_roman is None

def clean_youtube_title(filename):
    """
    Predicts a clean 'Artist - Title' filename by stripping YouTube junk patterns
    and applying custom parsing logic rules.
    """
    title = filename
    
    # 1. Convert fancy characters to standard ones
    # Fancy hyphens
    title = re.sub(r'[\u2010-\u2015—–‐‑‒―]+', '-', title)
    title = re.sub(r'-+', '-', title)
    # Fancy vertical bars
    title = re.sub(r'[｜│┃ǀ]+', '|', title)
    # Fancy colons
    title = title.replace('：', ':')
    # Fancy single quotes
    title = title.replace('’', "'").replace('‘', "'").replace('`', "'").replace('´', "'")
    # Fancy double quotes
    title = title.replace('“', '"').replace('”', '"')

    # 1b. Mask separators inside parentheses/brackets so Steps 2-5 don't treat them as separators.
    # Replace ' - ', '|', and ':' inside any bracket group with placeholders.
    MASK_HYPHEN = "\x00HYPHEN\x00"
    MASK_PIPE   = "\x00PIPE\x00"
    MASK_COLON  = "\x00COLON\x00"

    def mask_separators_in_brackets(text):
        result = []
        depth = 0
        i = 0
        while i < len(text):
            ch = text[i]
            if ch in '([{':
                depth += 1
                result.append(ch)
                i += 1
            elif ch in ')]}':
                depth -= 1
                result.append(ch)
                i += 1
            elif depth > 0:
                # Inside brackets: check for separators to mask
                if text[i:i+3] == ' - ':
                    result.append(MASK_HYPHEN)
                    i += 3
                elif text[i] == '|':
                    result.append(MASK_PIPE)
                    i += 1
                elif text[i] == ':':
                    result.append(MASK_COLON)
                    i += 1
                else:
                    result.append(ch)
                    i += 1
            else:
                result.append(ch)
                i += 1
        return ''.join(result)

    title = mask_separators_in_brackets(title)

    # 2. Turn colons ' : ' into separators
    title = re.sub(r'\s*:\s*', ' - ', title)

    # 3. Handle Pipe symbols (|)
    if "|" in title:
        if "-" not in title:
            # If there is a pipe but no dash separator, turn the pipe into a separator
            title = title.replace("|", " - ")
        else:
            # Remove anything after a "|" symbol and any spaces before it
            title = title.split("|")[0].rstrip()

    # 4. Standardize spacing around ' - ' (only if there are spaces on both sides)
    title = re.sub(r'\s+-\s+', ' - ', title)

    # 5. Remove anything after a second ' - ' separator
    parts = title.split(" - ")
    if len(parts) > 2:
        title = " - ".join(parts[:2])

    # 5b. Restore masked separators back to their original forms
    title = title.replace(MASK_HYPHEN, ' - ')
    title = title.replace(MASK_PIPE, '|')
    title = title.replace(MASK_COLON, ':')

    # 6. If the title is not romanized, look for anything in parenthesis or brackets and set that to the title.
    # ONLY if that parenthesized text contains a non-English character.
    # Do this BEFORE removing the brackets and parenthesis.
    if " - " in title:
        parts = title.split(" - ", 1)
        artist_part = parts[0].strip()
        title_part = parts[1].strip()
        
        if not is_romanized(title_part):
            m = re.search(r'[\(\[\{]([^\)\}\]]+)[\)\]\}]', title_part)
            if m:
                inside = m.group(1).strip()
                if not is_romanized(inside):
                    title_part = inside
        
        title = f"{artist_part} - {title_part}"
    else:
        if not is_romanized(title):
            m = re.search(r'[\(\[\{]([^\)\}\]]+)[\)\]\}]', title)
            if m:
                inside = m.group(1).strip()
                if not is_romanized(inside):
                    title = inside

    # 7. Treat anything after '&' OR ' x ' (x with spaces on both sides) like a second artist, and remove it.
    # ONLY if it appears before the divider (which is the separator).
    if " - " in title:
        parts = title.split(" - ", 1)
        artist_part = parts[0].strip()
        title_part = parts[1].strip()
        
        # Split by & (optional spaces) or ' x ' / ' X ' (spaces required)
        artist_part = re.split(r'\s*&\s*|\s+[xX]\s+', artist_part)[0].strip()
        
        title = f"{artist_part} - {title_part}"

    # 8. Process parentheses, brackets, and braces:
    # Only keep the contents inside if a non-English character is used.
    # Otherwise, discard the parenthesis block entirely.
    def process_brackets(match):
        inside = match.group(2)
        if not is_romanized(inside):
            return inside
        return ""
    
    # Run replacement on matched bracket/parenthesis/brace pairs (innermost first)
    bracket_pair_pattern = r'(\(|\[|\{)([^\(\)\[\]\{\}]*)(\)|\]|\})'
    old_title = ""
    while old_title != title:
        old_title = title
        title = re.sub(bracket_pair_pattern, process_brackets, title)

    # 9. Remove ALL remaining parenthesis, brackets, and braces characters themselves
    # (e.g. hanging/unbalanced brackets)
    title = re.sub(r'[\(\)\[\]\{\}]', '', title)

    # 9b. Remove specific junk words (case-insensitive, on word boundaries)
    # Target words: HD, Version, Original, Official, 4K, UHD, Upgraded, Upscaled, Remastered
    junk_words_pattern = r'\b(hd|version|original|official|4k|uhd|upgraded|upscaled|remastered)\b'
    title = re.sub(junk_words_pattern, '', title, flags=re.IGNORECASE)

    # 10. Handle features "ft.", "feat.", "featuring" (case-insensitive)
    title = re.compile(r'\b(ft|feat|featuring)\b\.?', re.IGNORECASE).split(title)[0]

    # 11. Remove anything directly connected to a # symbol (hashtags)
    title = re.sub(r'#\S+', '', title)

    # 12. Don't remove single quotes attached to ANY letters on either side (e.g. her's, don't, wavin')
    title = title.replace('"', '')
    title = re.sub(r"(?<![a-zA-Z])'(?![a-zA-Z])", "", title)

    # 13. Remove all emojis and miscellaneous symbols
    try:
        emoji_pattern = re.compile(r'[\U00010000-\U0010ffff\u2600-\u27bf]', flags=re.UNICODE)
        title = emoji_pattern.sub('', title)
    except re.error:
        pass

    # 14. Clean up multiple whitespaces and ensure uniform formatting around separators
    title = re.sub(r'\s+', ' ', title).strip()
    
    # Final cleanup of separator spacing
    if " - " in title:
        parts = title.split(" - ", 1)
        artist_part = parts[0].strip()
        title_part = parts[1].strip()
        
        # If the artist area has a comma, assume it is a second artist and remove everything after it
        if "," in artist_part:
            artist_part = artist_part.split(",")[0].strip()
            
        title = f"{artist_part} - {title_part}"
    else:
        title = re.sub(r'\s*-\s*$', '', title)
        title = re.sub(r'^\s*-\s*', '', title)
        title = title.strip()
    
    # 15. Clean invalid Windows filename characters
    invalid_chars = r'[\\/:*?"<>|]'
    title = re.sub(invalid_chars, '_', title)
    title = re.sub(r'\s+', ' ', title).strip()
    
    return title

def read_metadata_tags(filepath):
    """
    Reads the artist and title tags of the file using mutagen.
    Returns (artist, title) strings, or (None, None) if not present or error.
    """
    if not MUTAGEN_AVAILABLE:
        return None, None
        
    suffix = filepath.suffix.lower()
    try:
        if suffix == ".mp3":
            try:
                tags = EasyID3(filepath)
                artist = tags.get("artist", [None])[0]
                title = tags.get("title", [None])[0]
                return artist, title
            except ID3NoHeaderError:
                return None, None
        elif suffix == ".m4a":
            try:
                tags = EasyMP4(filepath)
                artist = tags.get("artist", [None])[0]
                title = tags.get("title", [None])[0]
                return artist, title
            except Exception:
                return None, None
    except Exception:
        pass
        
    return None, None

def write_metadata_tags(filepath, artist, title):
    """
    Writes the artist and title tags to the file using mutagen.
    """
    if not MUTAGEN_AVAILABLE:
        return False
        
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

def clean_and_tag_files(folder_path):
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
        
        auto_mode = False
        skipped_files = []
        
        idx = 1
        while idx <= len(file_list):
            file = file_list[idx - 1]
            stem = file.stem
            suffix = file.suffix.lower()
            
            current_suggestion = clean_youtube_title(stem)
            existing_artist, existing_title = read_metadata_tags(file)
            
            filename_is_correct = (current_suggestion == stem and " - " in stem)
            has_valid_tags = bool(existing_artist and existing_title)
            
            if not is_manual_skipped_pass and filename_is_correct and has_valid_tags:
                print(f"{Colors.DIM}[{idx}/{len(file_list)}] {Colors.GREEN}✔ Already formatted and tagged: {Colors.END}{file.name}")
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
                if MUTAGEN_AVAILABLE:
                    success = write_metadata_tags(active_filepath, artist, title)
                    if success:
                        tagged_count += 1
                        tag_status = "Renamed & Tagged" if renamed else "Tagged"
                        print(f"  {Colors.GREEN}✔ {tag_status} successfully:{Colors.END} Artist='{artist}', Title='{title}'")
                    else:
                        print(f"  {Colors.YELLOW}Renamed, but failed to write metadata tags.{Colors.END}")
                else:
                    if renamed:
                        print(f"  {Colors.YELLOW}Renamed, but skipped tagging (Mutagen not available).{Colors.END}")
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

# ==========================================
# LOUDNESS NORMALIZATION IMPLEMENTATION
# ==========================================

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
    """
    Runs a fast first pass with FFmpeg loudnorm in print_format=json mode
    to measure the file's integrated loudness (LUFS) and True Peak (dB).
    Returns (input_i, input_tp, error_message) as (float, float, str).
    """
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

def normalize_file(index, total, filepath):
    """
    Applies static whole-track volume adjustment based on measured LUFS.
    Safeguards mutagen tags by backing them up and restoring them post-write.
    """
    suffix = filepath.suffix.lower()
    
    # 1. Back up existing Mutagen tags to prevent any tag loss during FFmpeg processing
    artist, title = read_metadata_tags(filepath)
    
    # 2. First Pass: Measure loudness & peaks
    input_i, input_tp, err = measure_loudness(filepath)
    if err:
        return False, filepath.name, f"Loudness measurement failed: {err}"
        
    target_lufs = float(TARGET_LUFS)
    true_peak_limit = float(TRUE_PEAK)
    
    # Calculate volume adjustment in dB
    gain = target_lufs - input_i
    
    # Bound to avoid clipping beyond True Peak limit
    max_gain = true_peak_limit - input_tp
    final_gain = min(gain, max_gain)
    
    limit_str = " (Peak Limited)" if final_gain < gain else ""
    safe_print(
        f"[{index}/{total}] {Colors.CYAN}Processing:{Colors.END} {filepath.name}...\n"
        f"  ├─ Measured: {input_i:+.2f} LUFS | True Peak: {input_tp:+.2f} dB\n"
        f"  └─ Applying Whole-Track Gain: {final_gain:+.2f} dB{limit_str} (Target: {target_lufs} LUFS)"
    )
    
    # 3. Create temporary file
    try:
        temp_fd, temp_path = tempfile.mkstemp(suffix=suffix)
        os.close(temp_fd)
    except Exception as e:
        return False, filepath.name, f"Failed to create temp file: {e}"
        
    # 4. Assemble FFmpeg Command: silence-trim front & back, then static volume adjustment
    # silenceremove trims leading silence; the areverse/silenceremove/areverse trick trims trailing silence.
    # SILENCE_THRESHOLD is -50 dB (near-total silence), 0.5s minimum duration to avoid clipping musical content.
    SILENCE_THRESHOLD = "-50dB"
    SILENCE_DURATION = "0.5"
    af_chain = (
        f"silenceremove=start_periods=1:start_duration={SILENCE_DURATION}:start_threshold={SILENCE_THRESHOLD},"
        f"areverse,"
        f"silenceremove=start_periods=1:start_duration={SILENCE_DURATION}:start_threshold={SILENCE_THRESHOLD},"
        f"areverse,"
        f"volume={final_gain:.2f}dB,"
        f"apad=pad_dur=2"
    )
    command = [
        "ffmpeg",
        "-y",
        "-i", str(filepath),
        "-af", af_chain
    ]
    
    # Dynamic Suffix Bitrate & Codec matching
    if suffix == ".mp3":
        command += [
            "-codec:a", "libmp3lame",
            "-b:a", BITRATE,
        ]
    elif suffix == ".m4a":
        command += [
            "-codec:a", "aac",
            "-b:a", BITRATE,
        ]
    else:
        command += [
            "-b:a", BITRATE,
        ]
        
    # Keep metadata map and apply faststart only for M4A containers
    command += [
        "-map_metadata", "0",
    ]
    if suffix == ".m4a":
        command += [
            "-movflags", "+faststart",
        ]
        
    command.append(temp_path)
    
    # 5. Run FFmpeg to write the static adjusted file
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
        try:
            os.remove(temp_path)
        except:
            pass
        return False, filepath.name, f"FFmpeg execution failed: {e}"
        
    if result.returncode != 0:
        try:
            os.remove(temp_path)
        except:
            pass
        return False, filepath.name, result.stderr
        
    # 6. Overwrite the original file with the statically gain-adjusted version
    try:
        os.replace(temp_path, str(filepath))
    except Exception as e:
        return False, filepath.name, f"Failed to replace original file with temp: {e}"
        
    # 7. Restore backed up Mutagen tags on the new file
    if (artist or title) and MUTAGEN_AVAILABLE:
        write_metadata_tags(filepath, artist, title)
        
    return True, filepath.name, None

def run_loudness_normalization(folder_path):
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
                safe_print(f"  {Colors.GREEN}✔ Adjusted Volume:{Colors.END} {filename}\n")
            else:
                failed += 1
                safe_print(f"\n  {Colors.RED}✘ Failed to adjust volume {filename}:{Colors.END}")
                safe_print(f"{Colors.DIM}{error}{Colors.END}\n")
                
    print(f"\n{Colors.CYAN}{Colors.BOLD}Volume Adjustment Complete!{Colors.END}")
    print(f"  {Colors.GREEN}Success: {completed}{Colors.END} | {Colors.RED}Failed: {failed}{Colors.END}\n")
    return completed, failed

# ==========================================

def trim_silence_file(index, total, filepath):
    """
    Trims silence from the front and back of an audio file without any volume change.
    Uses the same areverse trick as normalize_file but with a volume=0dB no-op.
    """
    safe_print(f"[{index}/{total}] {Colors.CYAN}Trimming silence:{Colors.END} {filepath.name}...")
    
    suffix = filepath.suffix.lower()
    
    # Back up tags
    artist, title = read_metadata_tags(filepath)
    
    # Create temp file
    try:
        temp_fd, temp_path = tempfile.mkstemp(suffix=suffix)
        os.close(temp_fd)
    except Exception as e:
        return False, filepath.name, f"Failed to create temp file: {e}"
    
    SILENCE_THRESHOLD = "-50dB"
    SILENCE_DURATION = "0.5"
    af_chain = (
        f"silenceremove=start_periods=1:start_duration={SILENCE_DURATION}:start_threshold={SILENCE_THRESHOLD},"
        f"areverse,"
        f"silenceremove=start_periods=1:start_duration={SILENCE_DURATION}:start_threshold={SILENCE_THRESHOLD},"
        f"areverse"
    )
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
        try:
            os.remove(temp_path)
        except:
            pass
        return False, filepath.name, f"FFmpeg execution failed: {e}"
    
    if result.returncode != 0:
        try:
            os.remove(temp_path)
        except:
            pass
        return False, filepath.name, result.stderr
    
    try:
        os.replace(temp_path, str(filepath))
    except Exception as e:
        return False, filepath.name, f"Failed to replace original file with temp: {e}"
    
    if (artist or title) and MUTAGEN_AVAILABLE:
        write_metadata_tags(filepath, artist, title)
    
    return True, filepath.name, None

def run_silence_trim(folder_path):
    print(f"\n{Colors.CYAN}{Colors.BOLD}====================================={Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}=== SILENCE TRIM PASS ==============={Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}====================================={Colors.END}\n")
    
    if not check_ffmpeg_available():
        print(f"{Colors.YELLOW}[!] FFmpeg was not found in your system's PATH.{Colors.END}")
        print(f"{Colors.DIM}    Skipping silence trim pass.{Colors.END}\n")
        return 0, 0
    
    extensions = {".mp3", ".m4a"}
    files = sorted([f for f in folder_path.iterdir() if f.is_file() and f.suffix.lower() in extensions])
    
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
                safe_print(f"  {Colors.GREEN}✔ Trimmed:{Colors.END} {filename}")
            else:
                failed += 1
                safe_print(f"\n  {Colors.RED}✘ Failed to trim {filename}:{Colors.END}")
                safe_print(f"{Colors.DIM}{error}{Colors.END}\n")
    
    print(f"\n{Colors.CYAN}{Colors.BOLD}Silence Trim Complete!{Colors.END}")
    print(f"  {Colors.GREEN}Success: {completed}{Colors.END} | {Colors.RED}Failed: {failed}{Colors.END}\n")
    return completed, failed

# ==========================================

def main():
    print_banner()
    folder = select_folder()
    renamed_count, tagged_count, skipped_count, already_formatted_count = clean_and_tag_files(folder)
    
    norm_completed, norm_failed = 0, 0
    trim_completed, trim_failed = 0, 0
    
    try:
        print(f"{Colors.BOLD}Volume Adjustment / Loudness Normalization{Colors.END}")
        choice = input(f"Do you want to run the volume adjustment pass? ({Colors.GREEN}y{Colors.END}/{Colors.RED}n{Colors.END}): ").strip().lower()
        if choice in ('y', 'yes'):
            norm_completed, norm_failed = run_loudness_normalization(folder)
        else:
            print(f"\n{Colors.YELLOW}Skipping volume adjustment pass.{Colors.END}\n")
            print(f"{Colors.BOLD}Silence Trimming{Colors.END}")
            trim_choice = input(f"Do you want to trim silence from the front and back of each file? ({Colors.GREEN}y{Colors.END}/{Colors.RED}n{Colors.END}): ").strip().lower()
            if trim_choice in ('y', 'yes'):
                trim_completed, trim_failed = run_silence_trim(folder)
            else:
                print(f"\n{Colors.YELLOW}Skipping silence trim pass.{Colors.END}\n")
    except KeyboardInterrupt:
        print(f"\n\n{Colors.RED}Process interrupted by user. Exiting.{Colors.END}")
        sys.exit(0)

    # ── Summary ─────────────────────────────────────────────────────────────
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

if __name__ == "__main__":
    main()