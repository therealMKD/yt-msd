#Open Source Software under the Apache License, Version 2.0
#This was only partially vibe coded, I swear I know what I'm doing.
#There will be a config.json file in the same directory as this script. By default, it is OFF. The script will ignore it, unless you change it to ON.
#Running this script as-is will require you to have the following dependencies installed THROUGH PYTHON (not individually):
# yt-dlp "py -m pip install yt-dlp"

import yt_dlp
import json
import os
#If you change the download path in the config.json file, you MUST use forward slashes instead of backslashes.
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "use_config": False,
    "format": "mp3",
    "bitrate": "192",
    "download_path": "",
    "recent_paths": [],
    "last_custom_format": ""
}

def load_config():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, CONFIG_FILE)
    
    if not os.path.exists(config_path):
        with open(config_path, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        return DEFAULT_CONFIG
    
    with open(config_path, "r") as f:
        try:
            config = json.load(f)
            for key, value in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = value
            return config
        except json.JSONDecodeError:
            print("Error reading config.json, using default settings.")
            return DEFAULT_CONFIG

def save_config(config):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, CONFIG_FILE)
    try:
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error saving config: {e}")

# Youtube search function. If you aren't finding what you want in the first 10 results, you can change max_results to something higher
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
        print("\nSelect output format (leave blank for mp3): Keep in mind, Youtube has already compressed the audio, so wav and flac will not be better quality.")
        print("  1) mp4")
        print("  2) flac")
        print("  3) wav")
        print("  4) aac")
        last_fmt = config.get("last_custom_format")
        if last_fmt:
            print(f"  5) Last custom: {last_fmt}")
        print("Or type a custom yt-dlp format string (e.g., 'bestaudio/best') or codec name.")
        choice = input("Format [mp3]: ").strip()

        if choice == '5' and last_fmt:
            choice = last_fmt
        elif choice and choice.lower() not in ('1', 'mp4', '2', 'flac', '3', 'wav', '4', 'aac', 'mp3'):
            config["last_custom_format"] = choice
            save_config(config)
            
        print("\nSelect audio bitrate:")
        print("  1) 192 (Default)")
        print("  2) 256 (Medium)")
        print("  3) 320 (High)")
        br_input = input("Bitrate [1]: ").strip()

        if br_input == '3':
            bitrate = '320'
        elif br_input == '2':
            bitrate = '256'
        else:
            bitrate = '192'

# By default, this script will download in mp3. If you want a different format by default, you can substitute it in the config.json
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
            print("\nRecent download paths:")
            for idx, path in enumerate(recent_paths, 1):
                print(f"  {idx}) {path}")
        
        download_path_input = input("\nEnter download path (leave blank for current directory, or choose a saved previous directory): ").strip()
        
        if download_path_input.isdigit() and 1 <= int(download_path_input) <= len(recent_paths):
            download_path = recent_paths[int(download_path_input) - 1]
        else:
            download_path = download_path_input

        if download_path:
            download_path = download_path.replace("\\", "/")
            if download_path in recent_paths:
                recent_paths.remove(download_path)
            recent_paths.insert(0, download_path)
            config["recent_paths"] = recent_paths[:3]  # keep only last 3
            save_config(config)

    ydl_opts = {}

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

    try:
        while True:
            print("\nThis is the CLI version of yt-msd. The GUI version has more opt")
            query = input("Search YouTube or enter a video/playlist URL (Ctrl+C to quit): ").strip()
            if not query:
                continue
                
            if query.startswith(("http://", "https://", "www.youtube.com", "youtu.be")):
                print(f"\nDownloading URL: {query}\n")
                download_audio(query, config)
                print("\nDownload complete!")
                if not config.get("use_config"):
                    print("\nIf you want to automatically apply custom settings, edit the config.json file, and enable it.")
                else:
                    print("")
                continue

            print("\nSearching...\n")
            results = search_youtube(query)

            if not results:
                print("No valid video results found.")
                continue
            
            for i, video in enumerate(results):
                title = video.get('title', 'Unknown title')
                channel = video.get('uploader', 'Unknown channel')

                print(f"{i + 1}. {title}")
                print(f"   Channel: {channel}\n")

            try:
                choice_str = input("Select a number to download (or press Enter to cancel): ")
                if not choice_str.strip():
                    continue
                choice = int(choice_str) - 1
                if choice < 0 or choice >= len(results):
                    print("Invalid selection.")
                    continue
                selected = results[choice]
            except ValueError:
                print("Invalid selection.")
                continue

            url = f"https://www.youtube.com/watch?v={selected['id']}"

            print(f"\nDownloading: {selected.get('title', 'Unknown')}\n")
            download_audio(url, config)

            print("\nDownload complete!")
            if not config.get("use_config"):
                print("\nIf you want to automatically apply custom settings, edit the config.json file, and enable it.")
            else:
                print("")
            
    except KeyboardInterrupt:
        print("\n\nExiting program...\nThank you, Come again!")

if __name__ == "__main__":
    main()