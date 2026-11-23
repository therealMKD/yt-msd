# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.audio.renamer).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
import os
import sys
from pathlib import Path
from yt_msd.audio.normalize import run_loudness_normalization
from yt_msd.audio.tags import read_metadata_tags, write_metadata_tags
from yt_msd.audio.tuning import TUNING, _available_threads
from yt_msd.constants import TAGGABLE_EXTENSIONS
from yt_msd.util.console import Colors
from yt_msd.util.text import clean_youtube_title


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
    print(f"{Colors.BOLD}Using {TUNING.max_workers} CPU Threads for Processing{Colors.END}\n")
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

    if args.silence_pad is not None:
        TUNING.silence_pad_dur = args.silence_pad
    TUNING.silence_trim = (args.silence_trim == 'on')
    if args.custom_norm_cmd:
        TUNING.custom_norm_cmd = args.custom_norm_cmd
    if args.norm_threads is not None and args.norm_threads > 0:
        TUNING.max_workers = args.norm_threads

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
    print(f"{Colors.CYAN}{Colors.BOLD}{'═' * 50}{Colors.END}")
    print(f"\n{Colors.CYAN}{Colors.BOLD}All processes complete.{Colors.END}")

    try:
        input(f"\n{Colors.DIM}Press ENTER to exit...{Colors.END}")
    except (KeyboardInterrupt, EOFError):
        pass
