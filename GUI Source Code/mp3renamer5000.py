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
# LOUDNESS NORMALIZATION & TRIM SETTINGS
# ==========================================
TARGET_LUFS = "-16"       # Balanced loudness target for music listening
TRUE_PEAK = "-1.5"        # Prevents clipping
LOUDNESS_RANGE = "11"     # LRA of 11 preserves dynamics (not squishing music range)
BITRATE = "320k"          # High quality output bitrate
MAX_WORKERS = available_threads // 2  # Auto-adjusts to half of available threads
SILENCE_THRESHOLD = "-60dB" # Sensitive threshold to prevent cutting quiet outros
SILENCE_DURATION = "0.5"
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

def clean_youtube_title(filename):
    """
    Predicts a clean 'Artist - Title' filename by stripping YouTube junk patterns
    and applying custom parsing logic rules.
    """
    title = filename
    
    # 1. Convert em dashes, en dashes, or multiple hyphens to standard hyphens
    title = re.sub(r'[—–]+', '-', title)
    title = re.sub(r'-+', '-', title)

    # 2. Handle Pipe symbols (|)
    if "|" in title:
        if "-" not in title:
            # If there is a pipe but no dash separator, turn the pipe into a separator
            title = title.replace("|", " - ")
        else:
            # Remove anything after a "|" symbol and any spaces before it
            title = title.split("|")[0].rstrip()

    # 3. Handle features "ft.", "feat.", "featuring" (case-insensitive)
    title = re.compile(r'\b(ft|feat|featuring)\b\.?', re.IGNORECASE).split(title)[0]

    # 4. Remove anything directly connected to a # symbol (hashtags)
    title = re.sub(r'#\S+', '', title)

    # 5. Remove all single and double quotes (keep the text inside them)
    title = title.replace('"', '').replace("'", "")

    # 6. Remove all emojis and miscellaneous symbols
    try:
        # Filter using regex matching outside typical text ranges (covers emoticons, symbols, pictographs)
        emoji_pattern = re.compile(r'[\U00010000-\U0010ffff\u2600-\u27bf]', flags=re.UNICODE)
        title = emoji_pattern.sub('', title)
    except re.error:
        pass

    # 7. Parenthesized or bracketed parts containing common YouTube video tags
    junk_keywords = [
        "official", "video", "audio", "lyric", "lyrics", "hq", "hd", "4k", "1080p", "720p",
        "visualizer", "music video", "clip", "full song", "remaster", "remastered",
        "videoclip", "officialvideo", "officially", "mv", "m/v", "hdtv", "bluray", "rip",
        "sub", "subbed", "subs", "subtitles", "karaoke", "live", "concert", "performance",
        "vertical video", "behind the scenes", "making of", "teaser", "trailer", "studio version"
    ]
    
    bracket_pattern = r'(\([^\)]*\)|\[[^\]]*\]|\{[^\}]*\})'
    title = re.sub(bracket_pattern, "", title)
    
    # 8. Split and remove junk suffixes separated by symbols like //
    for sep in ["//", "///"]:
        if sep in title:
            parts = title.split(sep)
            new_parts = []
            for i, part in enumerate(parts):
                part_strip = part.strip()
                part_lower = part_strip.lower()
                if i > 0 and (any(kw in part_lower for kw in junk_keywords) or len(part_strip) == 0):
                    continue
                new_parts.append(part)
            if new_parts:
                title = sep.join(new_parts)

    # 9. Clean up multiple whitespaces and ensure uniform formatting around separators
    title = re.sub(r'\s+', ' ', title).strip()
    
    # Handle spacing / formatting around standard separators safely
    if " - " in title:
        parts = title.split(" - ", 1)
        artist_part = parts[0].strip()
        title_part = parts[1].strip()

        # If the artist area has a comma, assume it is a second artist and remove everything after it
        if "," in artist_part:
            artist_part = artist_part.split(",")[0].strip()

        title = f"{artist_part} - {title_part}"
    else:
        # If no explicit separator, fix edge-case dangling dashes or trailing spaces
        title = re.sub(r'\s*-\s*$', '', title)
        title = re.sub(r'^\s*-\s*', '', title)
        title = title.strip()
    
    # 10. Clean invalid Windows filename characters
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
        return
        
    print(f"{Colors.GREEN}Found {len(files)} audio files for renaming.{Colors.END}\n")
    
    idx = 1
    while idx <= len(files):
        file = files[idx - 1]
        stem = file.stem
        suffix = file.suffix.lower()
        
        predicted_name = clean_youtube_title(stem)
        existing_artist, existing_title = read_metadata_tags(file)
        
        filename_is_correct = (predicted_name == stem and " - " in stem)
        has_valid_tags = bool(existing_artist and existing_title)
        
        if filename_is_correct and has_valid_tags:
            print(f"{Colors.DIM}[{idx}/{len(files)}] {Colors.GREEN}✔ Already formatted and tagged: {Colors.END}{file.name}")
            idx += 1
            continue
            
        print(f"{Colors.DIM}─" * 60)
        print(f"{Colors.BOLD}[{idx}/{len(files)}] File: {Colors.END}{file.name}")
        print(f"  {Colors.YELLOW}Original  :{Colors.END} {stem}")
        print(f"  {Colors.GREEN}Predicted :{Colors.END} {predicted_name}")
        
        if has_valid_tags:
            print(f"  {Colors.CYAN}Tags found:{Colors.END} Artist='{existing_artist}', Title='{existing_title}'")
        else:
            print(f"  {Colors.DIM}Tags found: [None/Missing]{Colors.END}")
            
        try:
            if " - " not in predicted_name and predicted_name:
                artist_prompt = (
                    f"\n  {Colors.CYAN}No artist found.{Colors.END} Predicted title: {Colors.BOLD}{predicted_name}{Colors.END}\n"
                    f"  Type the {Colors.GREEN}artist name{Colors.END} to build '{Colors.BOLD}Artist - {predicted_name}{Colors.END}',\n"
                    f"  {Colors.YELLOW}'n'{Colors.END} to enter a full name manually, or {Colors.YELLOW}'s'{Colors.END} to skip:\n  > "
                )
                artist_input = input(artist_prompt).strip()
                
                if artist_input.lower() == 's':
                    print(f"  {Colors.YELLOW}Skipped.{Colors.END}\n")
                    idx += 1
                    continue
                elif artist_input.lower() == 'n' or not artist_input:
                    pass
                else:
                    user_input = f"{artist_input} - {predicted_name}"
                    final_name = clean_youtube_title(user_input)
                    if not final_name:
                        print(f"  {Colors.RED}Invalid name. Skipped.{Colors.END}\n")
                        idx += 1
                        continue
                    
                    new_filename = f"{final_name}{suffix}"
                    new_filepath = folder_path / new_filename
                    renamed = False
                    active_filepath = file
                    if final_name != stem:
                        if new_filepath.exists():
                            print(f"  {Colors.RED}Error: A file named '{new_filename}' already exists. Skipping rename.{Colors.END}\n")
                            idx += 1
                            continue
                        try:
                            file.rename(new_filepath)
                            print(f"  {Colors.GREEN}Renamed to:{Colors.END} {new_filename}")
                            active_filepath = new_filepath
                            renamed = True
                        except Exception as e:
                            print(f"  {Colors.RED}Rename failed: {e}{Colors.END}\n")
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
                    continue
                    
            prompt = f"\n  {Colors.BOLD}Accept predicted name?{Colors.END}\n  {Colors.CYAN}[ENTER]{Colors.END} to accept, type {Colors.GREEN}'f'{Colors.END} to flip Artist/Title, type a new {Colors.BOLD}Artist - Title{Colors.END}, or {Colors.YELLOW}'s'{Colors.END} to skip:\n  > "
            user_input = input(prompt).strip()
        except KeyboardInterrupt:
            print(f"\n\n{Colors.RED}Process interrupted by user. Exiting.{Colors.END}")
            sys.exit(0)
            
        if user_input.lower() == 's':
            print(f"  {Colors.YELLOW}Skipped.{Colors.END}\n")
            idx += 1
            continue

        if user_input.lower() == 'f':
            # Flip the logic layout order of Artist and Title
            if " - " in predicted_name:
                parts = predicted_name.split(" - ", 1)
                flipped_name = f"{parts[1]} - {parts[0]}"
                predicted_name = clean_youtube_title(flipped_name)
                print(f"  {Colors.CYAN}Flipped Layout Prediction to:{Colors.END} {predicted_name}")
                # Loop back to let the user review/approve the flipped layout
                continue
            else:
                print(f"  {Colors.RED}Cannot flip; no ' - ' separator detected!{Colors.END}")
                continue
            
        final_name = user_input if user_input else predicted_name
        final_name = clean_youtube_title(final_name)
        
        if not final_name:
            print(f"  {Colors.RED}Invalid name. Skipped.{Colors.END}\n")
            idx += 1
            continue

        new_filename = f"{final_name}{suffix}"
        new_filepath = folder_path / new_filename
        
        renamed = False
        active_filepath = file
        
        if final_name != stem:
            if new_filepath.exists():
                print(f"  {Colors.RED}Error: A file named '{new_filename}' already exists. Skipping rename.{Colors.END}\n")
                idx += 1
                continue
            try:
                file.rename(new_filepath)
                print(f"  {Colors.GREEN}Renamed to:{Colors.END} {new_filename}")
                active_filepath = new_filepath
                renamed = True
            except Exception as e:
                print(f"  {Colors.RED}Rename failed: {e}{Colors.END}\n")
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
    suffix = filepath.suffix.lower()
    artist, title = read_metadata_tags(filepath)
    
    input_i, input_tp, err = measure_loudness(filepath)
    if err:
        return False, filepath.name, f"Loudness measurement failed: {err}"
        
    target_lufs = float(TARGET_LUFS)
    true_peak_limit = float(TRUE_PEAK)
    
    gain = target_lufs - input_i
    max_gain = true_peak_limit - input_tp
    final_gain = min(gain, max_gain)
    
    limit_str = " (Peak Limited)" if final_gain < gain else ""
    safe_print(
        f"[{index}/{total}] {Colors.CYAN}Processing:{Colors.END} {filepath.name}...\n"
        f"  ├─ Measured: {input_i:+.2f} LUFS | True Peak: {input_tp:+.2f} dB\n"
        f"  └─ Applying Whole-Track Gain: {final_gain:+.2f} dB{limit_str} (Target: {target_lufs} LUFS)"
    )
    
    try:
        temp_fd, temp_path = tempfile.mkstemp(suffix=suffix)
        os.close(temp_fd)
    except Exception as e:
        return False, filepath.name, f"Failed to create temp file: {e}"
        
    af_chain = (
        f"silenceremove=start_periods=1:start_duration={SILENCE_DURATION}:start_threshold={SILENCE_THRESHOLD},"
        f"areverse,"
        f"silenceremove=start_periods=1:start_duration={SILENCE_DURATION}:start_threshold={SILENCE_THRESHOLD},"
        f"areverse,"
        f"volume={final_gain:.2f}dB"
    )
    command = [
        "ffmpeg",
        "-y",
        "-i", str(filepath),
        "-af", af_chain
    ]
    
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

def run_loudness_normalization(folder_path):
    print(f"\n{Colors.CYAN}{Colors.BOLD}========================================{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}=== TWO-PASS VOLUME ADJUSTMENT PASS ===={Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}========================================{Colors.END}\n")
    
    if not check_ffmpeg_available():
        print(f"{Colors.YELLOW}[!] FFmpeg was not found in your system's PATH.{Colors.END}")
        print(f"{Colors.DIM}    Loudness normalization requires FFmpeg to process files.{Colors.END}")
        print(f"{Colors.DIM}    Skipping volume adjustment pass.{Colors.END}\n")
        return
        
    extensions = {".mp3", ".m4a"}
    files = sorted([f for f in folder_path.iterdir() if f.is_file() and f.suffix.lower() in extensions])
    
    if not files:
        print(f"{Colors.YELLOW}No MP3 or M4A files found to adjust.{Colors.END}\n")
        return
        
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

# ==========================================

def trim_silence_file(index, total, filepath):
    """
    Trims silence from the front and back of an audio file safely using areverse.
    """
    safe_print(f"[{index}/{total}] {Colors.CYAN}Trimming silence:{Colors.END} {filepath.name}...")
    
    suffix = filepath.suffix.lower()
    artist, title = read_metadata_tags(filepath)
    
    try:
        temp_fd, temp_path = tempfile.mkstemp(suffix=suffix)
        os.close(temp_fd)
    except Exception as e:
        return False, filepath.name, f"Failed to create temp file: {e}"
    
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
        return
    
    extensions = {".mp3", ".m4a"}
    files = sorted([f for f in folder_path.iterdir() if f.is_file() and f.suffix.lower() in extensions])
    
    if not files:
        print(f"{Colors.YELLOW}No MP3 or M4A files found to trim.{Colors.END}\n")
        return
    
    print(f"{Colors.GREEN}Trimming silence on {len(files)} files with {MAX_WORKERS} worker threads...{Colors.END}")
    print(f"{Colors.DIM}Threshold: {SILENCE_THRESHOLD} | Min silence duration: {SILENCE_DURATION}s{Colors.END}\n")
    
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

# ==========================================

def main():
    print_banner()
    folder = select_folder()
    clean_and_tag_files(folder)
    
    try:
        print(f"{Colors.BOLD}Volume Adjustment / Loudness Normalization{Colors.END}")
        choice = input(f"Do you want to run the volume adjustment pass? ({Colors.GREEN}y{Colors.END}/{Colors.RED}n{Colors.END}): ").strip().lower()
        if choice in ('y', 'yes'):
            run_loudness_normalization(folder)
        else:
            print(f"\n{Colors.YELLOW}Skipping volume adjustment pass.{Colors.END}\n")
            print(f"{Colors.BOLD}Silence Trimming{Colors.END}")
            trim_choice = input(f"Do you want to trim silence from the front and back of each file? ({Colors.GREEN}y{Colors.END}/{Colors.RED}n{Colors.END}): ").strip().lower()
            if trim_choice in ('y', 'yes'):
                run_silence_trim(folder)
            else:
                print(f"\n{Colors.YELLOW}Skipping silence trim pass.{Colors.END}\n")
    except KeyboardInterrupt:
        print(f"\n\n{Colors.RED}Process interrupted by user. Exiting.{Colors.END}")
        sys.exit(0)
        
    print(f"{Colors.CYAN}{Colors.BOLD}Done! All processes complete.{Colors.END}")

if __name__ == "__main__":
    main()