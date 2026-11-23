# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.audio.tags).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
import os
from yt_msd.util.console import Colors


from mutagen.easyid3 import EasyID3

from mutagen.id3 import ID3, COMM, ID3NoHeaderError

from mutagen.easymp4 import EasyMP4

from mutagen import File as MutagenFile


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
