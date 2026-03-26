#Open Source Software under the Apache License, Version 2.0
#This was only partially vibe coded, I swear I know what I'm doing.
#Running this script as-is will require you to have the following dependencies installed THROUGH PYTHON (not individually):
# yt-dlp "py -m pip install yt-dlp"

import yt_dlp
import json
import os

CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "use_config": False,
    "format": "",
    "download_path": ""
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
            return json.load(f)
        except json.JSONDecodeError:
            print("Error reading config.json, using default settings.")
            return DEFAULT_CONFIG

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
    else:
        print("\nSelect output format (leave blank for mp3): Keep in mind, Youtube has already compressed the audio, so wav and flac will not be better quality.")
        print("  1) mp4")
        print("  2) flac")
        print("  3) wav")
        print("  4) aac")
        print("Or type a custom yt-dlp format string (e.g., 'bestaudio/best') or codec name.")
        choice = input("Format [mp3]: ").strip()
# By default, this script will download in mp3. If you want a different format by default, you can substitute it in the return statement below.
    if not choice or choice.lower() == 'mp3':
        return {'codec': 'mp3', 'format': None}

    low = choice.lower()
    if low in ('1', 'mp4'):
        return {'codec': 'm4a', 'format': None}
    if low in ('2', 'flac'):
        return {'codec': 'flac', 'format': None}
    if low in ('3', 'wav'):
        return {'codec': 'wav', 'format': None}
    if low in ('4', 'aac'):
        return {'codec': 'aac', 'format': None}

    return {'codec': None, 'format': choice}


def download_audio(url, config, chosen=None):
    if chosen is None:
        chosen = choose_format(config)
#If you want to hard code a download path, delete this input statement and insert the path as a string. E.g. "C:/Users/user/Music"
    if config.get("use_config"):
        download_path = config.get("download_path", "")
    else:
        download_path = input("Enter download path (leave blank for current directory): ").strip()

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
            'preferredquality': '320',
        }]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def main():
    config = load_config()

    query = input("Search YouTube: ")

    print("\nSearching...\n")
    results = search_youtube(query)

    if not results:
        print("No valid video results found.")
        return
    
    for i, video in enumerate(results):
        title = video.get('title', 'Unknown title')
        channel = video.get('uploader', 'Unknown channel')

        print(f"{i + 1}. {title}")
        print(f"   Channel: {channel}\n")

    try:
        choice = int(input("Select a number to download: ")) - 1
        selected = results[choice]
    except (ValueError, IndexError):
        print("Invalid selection.")
        return

    url = f"https://www.youtube.com/watch?v={selected['id']}"

    print(f"\nDownloading: {selected.get('title', 'Unknown')}\n")
    download_audio(url, config)

    print("\nDownload complete!")


if __name__ == "__main__":
    main()