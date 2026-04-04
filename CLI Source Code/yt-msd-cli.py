#Open Source Software under the Apache License, Version 2.0
#This is the CLI version of yt-msd. It is much more limited than the GUI version, but if you only need simple downloading, this works.
#This was only partially vibe coded, I swear I know what I'm doing.
#There will be a config.json file in the same directory as this script once you have ran it once. 
#By default, it is OFF. The script will ignore it, unless you change it to ON.
#Running this script as-is will require you to have the following dependencies installed THROUGH PYTHON (not individually):
# yt-dlp "py -m pip install yt-dlp"

import yt_dlp
import json
import os
import threading
import sys

def get_ffmpeg_path():
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return None

def self_install_to_path():
    #Only runs when packaged as an .exe — skips entirely when running as a .py script
    if not getattr(sys, 'frozen', False):
        return
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    user_path = os.environ.get('PATH', '')
    #Check if the exe's folder is already accessible via PATH
    if exe_dir.lower() in [p.lower() for p in user_path.split(os.pathsep)]:
        return
    #Also check the persistent User PATH from the registry
    if sys.platform != 'win32':
        return
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Environment', 0, winreg.KEY_READ) as key:
            saved_path, _ = winreg.QueryValueEx(key, 'PATH')
    except (FileNotFoundError, OSError):
        saved_path = ''
    if exe_dir.lower() in [p.lower() for p in saved_path.split(os.pathsep)]:
        return
    print(f"{C_INFO}yt-msd is not on your system PATH yet.{C_RESET}")
    print(f"{C_INFO}Adding it would let you run 'yt-msd' from any terminal window.{C_RESET}")
    answer = input(f"{C_PROMPT}Add to PATH? (y/n): {C_RESET}").strip().lower()
    if answer in ('y', 'yes'):
        new_path = f"{saved_path};{exe_dir}" if saved_path else exe_dir
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Environment', 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, 'PATH', 0, winreg.REG_EXPAND_SZ, new_path)
            #Broadcast the change so Explorer picks it up without a reboot
            import ctypes
            HWND_BROADCAST = 0xFFFF
            WM_SETTINGCHANGE = 0x001A
            ctypes.windll.user32.SendMessageTimeoutW(
                HWND_BROADCAST, WM_SETTINGCHANGE, 0, 'Environment', 0x0002, 5000, ctypes.byref(ctypes.c_long())
            )
            print(f"{C_SUCCESS}Done! Open a new terminal and you can use 'yt-msd' from anywhere.{C_RESET}")
        except OSError as e:
            print(f"{C_ERROR}Could not update PATH: {e}{C_RESET}")
    else:
        print(f"{C_INFO}Skipped. You can always move yt-msd.exe into a folder on your PATH later.{C_RESET}")

#Color references, the colors are what it says on the tin
C_INFO = '\033[94m'    # Bright Blue
C_PROMPT = '\033[38;5;165m'  # Purple (Couldn't get the color I wanted so I switched to 256 color mode)
C_SUCCESS = '\033[92m' # Bright Green
C_ERROR = '\033[91m'   # Bright Red
C_RESULT = '\033[97m'  # White (Is there such a thing as bright white?)
C_RESET = '\033[0m'    # Reset

#If you change the download path in the config.json file, you MUST use forward slashes instead of backslashes.
CONFIG_FILE = "config.json"

def get_config_dir():
    """Returns the directory where config.json should live — next to the .exe when frozen, next to the .py when running as a script, or next to the .pex when running as a ZipApp."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    
    # Check if we are running from a zipapp/pex
    if ".pex" in __file__ or ".pyz" in __file__ or ".zip" in __file__:
        # Return the directory of the script itself (the .pex file)
        return os.path.dirname(os.path.abspath(sys.argv[0]))
        
    return os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = {
    "use_config": False,
    "format": "mp3",
    "bitrate": "192",
    "download_path": "",
    "recent_paths": [],
    "last_custom_format": ""
}

def load_config():
    config_path = os.path.join(get_config_dir(), CONFIG_FILE)
    
    if not os.path.exists(config_path):
        with open(config_path, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        return DEFAULT_CONFIG
    
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
            for key, value in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = value
            return config
    except json.JSONDecodeError:
        print(f"{C_ERROR}Error reading config.json. Did you mess it up? Overwriting with default settings.{C_RESET}")
        with open(config_path, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        return DEFAULT_CONFIG

def save_config(config):
    config_path = os.path.join(get_config_dir(), CONFIG_FILE)
    try:
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"{C_ERROR}Error saving config: {e}{C_RESET}")

def search_youtube(query, max_results=10):
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'skip_download': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
        
        results = []
        for entry in info['entries']:
            if entry.get('_type') == 'url' or entry.get('ie_key') == 'Youtube':
                results.append(entry)

        return results


def choose_format(config):
    if config.get("use_config"):
        choice = config.get("format", "")
        bitrate = str(config.get("bitrate", "192"))
    else:
        #You can change these default options in the code if you want, just make sure your new ones are valid yt-dlp arguments.
        print(f"\n{C_INFO}Select output format (leave blank for mp3): Keep in mind, Youtube has already compressed the audio, so wav and flac will not be better quality.{C_RESET}")
        print(f"{C_RESULT}  1) mp4")
        print(f"{C_RESULT}  2) flac")
        print(f"{C_RESULT}  3) wav")
        print(f"  4) aac{C_RESET}")
        last_fmt = config.get("last_custom_format")
        if last_fmt:
            print(f"{C_RESULT}  5) Last custom: {C_RESET}")
        print(f"{C_INFO}Or type a custom yt-dlp format string (e.g., 'bestaudio/best') or codec name.{C_RESET}")
        choice = input(f"{C_PROMPT}Format [mp3]: {C_RESET}").strip()

        if choice == '5' and last_fmt:
            choice = last_fmt
        elif choice and choice.lower() not in ('1', 'mp4', '2', 'flac', '3', 'wav', '4', 'aac', 'mp3'):
            config["last_custom_format"] = choice
            save_config(config)
            
        print(f"\n{C_INFO}Select audio bitrate: (This doesn't really matter since youtube has already compressed the audio. Higher bitrates will give you larger files){C_RESET}")
        print(f"{C_RESULT}  1) 192 (Default)")
        print("  2) 256 (Medium)")
        print(f"  3) 320 (High){C_RESET}")
        br_input = input(f"{C_PROMPT}Bitrate [1]: {C_RESET}").strip()

        if br_input == '3':
            bitrate = '320'
        elif br_input == '2':
            bitrate = '256'
        else:
            bitrate = '192'

#By default, this script will download in mp3. If you want a different format by default, you can substitute it in the config.json
    if not choice or choice.lower() == 'mp3':
        return {'codec': 'mp3', 'format': None, 'bitrate': bitrate}

    low = choice.lower()
    if low in ('1', 'mp4'):
        return {'codec': 'm4a', 'format': None, 'bitrate': bitrate}
    if low in ('2', 'flac'):
        return {'codec': 'flac', 'format': None, 'bitrate': bitrate}
    if low in ('3', 'wav'):
        return {'codec': 'wav', 'format': None, 'bitrate': bitrate}
    if low in ('4', 'aac'):
        return {'codec': 'aac', 'format': None, 'bitrate': bitrate}

    return {'codec': None, 'format': choice, 'bitrate': bitrate}


def download_audio(url, config, chosen=None):
    if chosen is None:
        chosen = choose_format(config)
#If you want to hard code a download path, insert it into the config.json file
    if config.get("use_config"):
        download_path = config.get("download_path", "")
    else:
        recent_paths = config.get("recent_paths", [])
        if recent_paths:
            print(f"\n{C_INFO}Recent download paths:")
            for idx, path in enumerate(recent_paths, 1):
                print(f"  {idx}) {path}{C_RESET}")
        
        download_path_input = input(f"\n{C_PROMPT}Enter download path (leave blank for current directory, or choose a saved previous directory): {C_RESET}").strip()
        
        if download_path_input.isdigit() and 1 <= int(download_path_input) <= len(recent_paths):
            download_path = recent_paths[int(download_path_input) - 1]
        else:
            download_path = download_path_input

        if download_path:
            download_path = download_path.strip(' \t"\'').replace("\\", "/")
            if download_path in recent_paths:
                recent_paths.remove(download_path)
            recent_paths.insert(0, download_path)
            config["recent_paths"] = recent_paths[:3]
            save_config(config)

    ydl_opts = {}

    ffmpeg_location = get_ffmpeg_path()
    if ffmpeg_location:
        ydl_opts['ffmpeg_location'] = ffmpeg_location

    if chosen.get('format'):
        ydl_opts['format'] = chosen['format']
    else:
        ydl_opts['format'] = 'bestaudio/best'

    outtmpl = '%(title)s.%(ext)s'
    if download_path:
        outtmpl = f"{download_path}/%(title)s.%(ext)s"

    ydl_opts['outtmpl'] = outtmpl

    if chosen.get('codec'):
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': chosen['codec'],
            'preferredquality': chosen.get('bitrate', '192'),
        }]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def main():
    config = load_config()
    self_install_to_path()

    try:
        #Is it necessary? Nope. Is it cool? Yes.
        ascii_art = [
            r" __ __  _____       _____  _____  ____  ",
            r"|  |  ||_   _| ___ |     ||   __||    \ ",
            r"|_   _|  | |  |___|| | | ||__   ||  |  |",
            r"  |_|    |_|       |_|_|_||_____||____/ "
        ]
        colors = [91, 93, 92, 96, 94, 95]
        for line in ascii_art:
            print("".join(f"\033[{colors[i % len(colors)]}m{char}" for i, char in enumerate(line)) + "\033[0m")
        print(f"\n{C_INFO}This is the CLI version of yt-msd. The GUI version has more options, and can be found at https://github.com/therealMKD/yt-msd{C_RESET}")
        while True:
            query = input(f"{C_PROMPT}Search YouTube or enter a video/playlist URL (Ctrl+C to quit): {C_RESET}").strip()
            if not query:
                continue
                
            if query.startswith(("http://", "https://", "www.youtube.com", "youtu.be")):
                print(f"\n{C_INFO}Downloading URL: {query}\n{C_RESET}")
                download_audio(query, config)
                print(f"\n{C_SUCCESS}Download complete!{C_RESET}")
                if not config.get("use_config"):
                    print(f"\n{C_INFO}If you want to automatically apply custom settings, edit the config.json file, and enable it.{C_RESET}")
                else:
                    print(f"\n{C_INFO}You are currently using a config file. If you want to change settings, change them in the config, or disable the config.{C_RESET}")
                continue

            print(f"\n{C_INFO}Searching...{C_RESET}\n")
            current_limit = 10
            results = search_youtube(query, max_results=current_limit)

            if not results:
                print(f"{C_ERROR}No valid video results found.{C_RESET}")
                continue

            def bg_fetch():
                more_results = search_youtube(query, max_results=110)
                if len(more_results) > len(results):
                    results.extend(more_results[len(results):])

            bg_thread = threading.Thread(target=bg_fetch, daemon=True)
            bg_thread.start()

            display_start = 0
            selected = None

            while True:
                page_results = results[display_start:display_start + 10]

                if not page_results:
                    print(f"\n{C_ERROR}No more results available. Try searching on youtube on your own, and pasting the URL in.{C_RESET}")
                    break
                
                for i, video in enumerate(page_results):
                    title = video.get('title', 'Unknown title')
                    channel = video.get('uploader', 'Unknown channel')

                    print(f"{C_RESULT}{display_start + i + 1}. {title} | Channel: {channel}{C_RESET}")

                print("")
                choice_str = input(f"{C_PROMPT}Select a number to download (or 'next' for more, Enter to cancel): {C_RESET}").strip()
                
                if not choice_str:
                    break
                
                if choice_str.lower() == 'next':
                    display_start += 10
                    
                    if display_start >= len(results):
                        if bg_thread.is_alive():
                            print(f"\n{C_INFO}Hold on one sec - Still doing stuff{C_RESET}")
                            bg_thread.join()
                            
                        if display_start >= len(results):
                            print(f"\n{C_ERROR}No more results available. Try searching on youtube on your own, and pasting the URL in.{C_RESET}")
                            break
                    continue
                
                try:
                    choice = int(choice_str) - 1
                    if choice < 0 or choice >= len(results):
                        print(f"{C_ERROR}Invalid selection.{C_RESET}")
                        continue
                    selected = results[choice]
                    break
                except ValueError:
                    print(f"{C_ERROR}Invalid selection.{C_RESET}")
                    continue
            
            if not selected:
                continue

            url = f"https://www.youtube.com/watch?v={selected['id']}"

            print(f"\n{C_RESULT}Downloading: {selected.get('title', 'Unknown')}\n{C_RESET}")
            download_audio(url, config)

            print(f"\n{C_SUCCESS}Download complete!{C_RESET}")
            if not config.get("use_config"):
                print(f"\n{C_INFO}If you want to automatically apply custom settings, edit the config.json file, and enable it.{C_RESET}")
            else:
                print(f"\n{C_INFO}You are currently using a config file. If you want to change settings, change them in the config, or disable the config.{C_RESET}")
            
    except KeyboardInterrupt:
        print(f"\n\n{C_RESULT}Exiting program...\nThank you, Come again!{C_RESET}")

if __name__ == "__main__":
    main()