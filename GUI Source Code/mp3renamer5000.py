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
    print(f"{Colors.DIM}Converted from Rename-MP3s.ps1 • Powered by Python & FFmpeg{Colors.END}\n")
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
    Predicts a clean 'Artist - Title' filename by stripping YouTube junk patterns.
    """
    title = filename
    
    # 1. Parenthesized or bracketed parts containing common YouTube video tags
    junk_keywords = [
        "official", "video", "audio", "lyric", "lyrics", "hq", "hd", "4k", "1080p", "720p",
        "visualizer", "music video", "clip", "full song", "remaster", "remastered",
        "videoclip", "officialvideo", "officially", "mv", "m/v", "hdtv", "bluray", "rip",
        "sub", "subbed", "subs", "subtitles", "karaoke", "live", "concert", "performance",
        "vertical video", "behind the scenes", "making of", "teaser", "trailer", "studio version"
    ]
    
    # Regex to find parenthesized or bracketed blocks
    bracket_pattern = r'(\([^\)]*\)|\[[^\]]*\])'
    
    def replace_bracket(match):
        content = match.group(0).lower()
        if any(kw in content for kw in junk_keywords):
            return ""
        return match.group(0)  # Keep it (e.g. "(feat. Guest)")
        
    title = re.sub(bracket_pattern, replace_bracket, title)
    
    # 2. Split and remove junk suffixes separated by symbols like |, //
    # e.g., "Artist - Title | Official Music Video"
    for sep in ["|", "//", "///"]:
        if sep in title:
            parts = title.split(sep)
            new_parts = []
            for i, part in enumerate(parts):
                part_strip = part.strip()
                part_lower = part_strip.lower()
                # If it's a following part and contains junk OR is empty, strip it
                if i > 0 and (any(kw in part_lower for kw in junk_keywords) or len(part_strip) == 0):
                    continue
                new_parts.append(part)
            if new_parts:
                title = sep.join(new_parts)
                
    # 3. Clean up extra whitespaces and dangling hyphens
    title = re.sub(r'\s+', ' ', title)  # Collapse multiple spaces
    title = title.strip()
    
    title = re.sub(r'\s*-\s*$', '', title)  # Remove trailing hyphen
    title = re.sub(r'^\s*-\s*', '', title)  # Remove leading hyphen
    title = title.strip()
    
    # 4. Clean invalid Windows filename characters
    # Invalid: \ / : * ? " < > |
    invalid_chars = r'[\\/:*?"<>|]'
    title = re.sub(invalid_chars, '_', title)
    
    # Double check space collapse after replace
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
                # Fallback / create empty tags structure
                tags = EasyMP4(filepath)
            tags["artist"] = artist
            tags["title"] = title
            tags.save()
            return True
    except Exception as e:
        print(f"{Colors.RED}Error writing tags to {filepath.name}: {e}{Colors.END}")
        
    return False

def clean_and_tag_files(folder_path):
    # Find all .mp3 and .m4a files, sorted by name
    extensions = {".mp3", ".m4a"}
    files = sorted([f for f in folder_path.iterdir() if f.is_file() and f.suffix.lower() in extensions])
    
    if not files:
        print(f"{Colors.YELLOW}No MP3 or M4A files found in this folder.{Colors.END}")
        return
        
    print(f"{Colors.GREEN}Found {len(files)} audio files for renaming.{Colors.END}\n")
    
    for idx, file in enumerate(files, 1):
        stem = file.stem
        suffix = file.suffix.lower()
        
        # 1. Predict clean name
        predicted_name = clean_youtube_title(stem)
        
        # 2. Extract components
        predicted_artist, predicted_title = None, None
        if " - " in predicted_name:
            parts = predicted_name.split(" - ", 1)
            predicted_artist = parts[0].strip()
            predicted_title = parts[1].strip()
            
        # 3. Check existing metadata
        existing_artist, existing_title = read_metadata_tags(file)
        
        # Check if the file is already formatted correctly on disk AND has metadata tags
        filename_is_correct = (predicted_name == stem and " - " in stem)
        has_valid_tags = bool(existing_artist and existing_title)
        
        if filename_is_correct and has_valid_tags:
            print(f"{Colors.DIM}[{idx}/{len(files)}] {Colors.GREEN}✔ Already formatted and tagged: {Colors.END}{file.name}")
            continue
            
        # 4. User Interaction Prompt
        print(f"{Colors.DIM}─" * 60)
        print(f"{Colors.BOLD}[{idx}/{len(files)}] File: {Colors.END}{file.name}")
        print(f"  {Colors.YELLOW}Original  :{Colors.END} {stem}")
        print(f"  {Colors.GREEN}Predicted :{Colors.END} {predicted_name}")
        
        if has_valid_tags:
            print(f"  {Colors.CYAN}Tags found:{Colors.END} Artist='{existing_artist}', Title='{existing_title}'")
        else:
            print(f"  {Colors.DIM}Tags found: [None/Missing]{Colors.END}")
            
        try:
            prompt = f"\n  {Colors.BOLD}Accept predicted name?{Colors.END}\n  {Colors.CYAN}[ENTER]{Colors.END} to accept, type a new {Colors.BOLD}Artist - Title{Colors.END}, or type {Colors.YELLOW}'s'{Colors.END} to skip:\n  > "
            user_input = input(prompt).strip()
        except KeyboardInterrupt:
            print(f"\n\n{Colors.RED}Process interrupted by user. Exiting.{Colors.END}")
            sys.exit(0)
            
        if user_input.lower() == 's':
            print(f"  {Colors.YELLOW}Skipped.{Colors.END}\n")
            continue
            
        # Decide final name
        final_name = user_input if user_input else predicted_name
        
        # Clean final name in case the user typed invalid characters
        final_name = clean_youtube_title(final_name)
        
        if not final_name:
            print(f"  {Colors.RED}Invalid name. Skipped.{Colors.END}\n")
            continue
            
        new_filename = f"{final_name}{suffix}"
        new_filepath = folder_path / new_filename
        
        # 5. Rename file if name has changed
        renamed = False
        active_filepath = file
        
        if final_name != stem:
            if new_filepath.exists():
                print(f"  {Colors.RED}Error: A file named '{new_filename}' already exists. Skipping rename.{Colors.END}\n")
                continue
            try:
                file.rename(new_filepath)
                print(f"  {Colors.GREEN}Renamed to:{Colors.END} {new_filename}")
                active_filepath = new_filepath
                renamed = True
            except Exception as e:
                print(f"  {Colors.RED}Rename failed: {e}{Colors.END}\n")
                continue
                
        # 6. Tag metadata
        # Re-split final name for artist/title metadata tagging
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

# ==========================================
# LOUDNESS NORMALIZATION IMPLEMENTATION
# ==========================================

def check_ffmpeg_available():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False

def normalize_file(index, total, filepath):
    """
    Runs FFmpeg loudnorm on a single file.
    Safeguards mutagen tags by backing them up and restoring them post-write.
    """
    safe_print(f"[{index}/{total}] {Colors.CYAN}Normalizing:{Colors.END} {filepath.name}...")
    
    suffix = filepath.suffix.lower()
    
    # 1. Back up existing Mutagen tags to prevent any tag loss during FFmpeg processing
    artist, title = read_metadata_tags(filepath)
    
    # 2. Create temporary file
    try:
        temp_fd, temp_path = tempfile.mkstemp(suffix=suffix)
        os.close(temp_fd)
    except Exception as e:
        return False, filepath.name, f"Failed to create temp file: {e}"
        
    # 3. Assemble FFmpeg Command
    command = [
        "ffmpeg",
        "-y",
        "-i", str(filepath),
        "-af", f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA={LOUDNESS_RANGE}"
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
    
    # 4. Run FFmpeg
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
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
        
    # 5. Overwrite the original file with the normalized version
    try:
        os.replace(temp_path, str(filepath))
    except Exception as e:
        return False, filepath.name, f"Failed to replace original file with temp: {e}"
        
    # 6. Restore backed up Mutagen tags on the newly normalized file
    if (artist or title) and MUTAGEN_AVAILABLE:
        write_metadata_tags(filepath, artist, title)
        
    return True, filepath.name, None

def run_loudness_normalization(folder_path):
    print(f"\n{Colors.CYAN}{Colors.BOLD}========================================{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}=== LOUDNESS NORMALIZATION PASS ========{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}========================================{Colors.END}\n")
    
    # Check if FFmpeg is installed
    if not check_ffmpeg_available():
        print(f"{Colors.YELLOW}[!] FFmpeg was not found in your system's PATH.{Colors.END}")
        print(f"{Colors.DIM}    Loudness normalization requires FFmpeg to process files.{Colors.END}")
        print(f"{Colors.DIM}    Skipping normalization pass.{Colors.END}\n")
        return
        
    extensions = {".mp3", ".m4a"}
    # Scan folder again to grab all audio files (renamed or not)
    files = sorted([f for f in folder_path.iterdir() if f.is_file() and f.suffix.lower() in extensions])
    
    if not files:
        print(f"{Colors.YELLOW}No MP3 or M4A files found to normalize.{Colors.END}\n")
        return
        
    print(f"{Colors.GREEN}Starting normalization on {len(files)} files with {MAX_WORKERS} worker threads...{Colors.END}")
    print(f"{Colors.DIM}Settings: Target={TARGET_LUFS} LUFS | Range={LOUDNESS_RANGE} LRA (Preserved Music Dynamics) | Peak={TRUE_PEAK} dB | Bitrate={BITRATE}{Colors.END}\n")
    
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
                safe_print(f"  {Colors.GREEN}✔ Normalized:{Colors.END} {filename}")
            else:
                failed += 1
                safe_print(f"\n  {Colors.RED}✘ Failed to normalize {filename}:{Colors.END}")
                safe_print(f"{Colors.DIM}{error}{Colors.END}\n")
                
    print(f"\n{Colors.CYAN}{Colors.BOLD}Normalization Pass Complete!{Colors.END}")
    print(f"  {Colors.GREEN}Success: {completed}{Colors.END} | {Colors.RED}Failed: {failed}{Colors.END}\n")

# ==========================================

def main():
    print_banner()
    folder = select_folder()
    clean_and_tag_files(folder)
    run_loudness_normalization(folder)
    print(f"{Colors.CYAN}{Colors.BOLD}Done! All processes complete.{Colors.END}")

if __name__ == "__main__":
    main()
