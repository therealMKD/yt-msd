import yt_dlp


def search_youtube(query, max_results=10):
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'skip_download': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)

        # Filter only actual videos (skip channels/playlists)
        results = []
        for entry in info['entries']:
            if entry.get('_type') == 'url' or entry.get('ie_key') == 'Youtube':
                results.append(entry)

        return results


def download_audio(url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': '%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def main():
    query = input("Search YouTube: ")

    print("\nSearching...\n")
    results = search_youtube(query)

    if not results:
        print("No valid video results found.")
        return

    # Display results with channel names
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
    download_audio(url)

    print("\nDownload complete!")


if __name__ == "__main__":
    main()