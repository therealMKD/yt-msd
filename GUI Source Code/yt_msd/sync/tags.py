# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.sync.tags).
from pathlib import Path
import time
import hashlib
from typing import List, Optional, Tuple, Union



# Placeholder tag file placed in removable media / USB drive folders
SYNC_TAG_FILENAME = "TAG.yaml"


def write_sync_tag_file(folder_path: Union[str, Path], sync_code: str, chain_name: str = '',
                        sync_style: str = 'Mirror', last_synced_by: str = 'Host',
                        parent_sync_folder: str = '') -> bool:
    try:
        p = Path(folder_path)
        p.mkdir(parents=True, exist_ok=True)
        tag_file = p / SYNC_TAG_FILENAME
        now_str = time.strftime("%m-%d-%Y %H:%M:%S")
        content = (
            "# This is a marker file for yt-msd syncing. DO NOT DELETE!\n"
            "# This file is automatically created by yt-msd, when syncing a playlist onto removable media (Like an SD card)\n"
            "# Modifying or deleting this file will break the sync process. If you no longer want to sync, delete the sync chain inside of yt-msd.\n\n"
            f"sync_code: {sync_code}\n\n"
            "# Human-readable name for this sync chain\n"
            f"chain_name: {chain_name}\n\n"
            "# Either Mirror, or Additive\n"
            f"sync_style: {sync_style}\n\n"
            f"last_synced: {now_str}\n\n"
            "# Either Host (this machine hosts the chain) or Client (subscribed to a remote host).\n"
            f"last_synced_by: {last_synced_by}\n\n"
            "# Filepath of master folder on host\n"
            f"parent_sync_folder: {parent_sync_folder}\n"
        )
        with open(tag_file, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"Error writing sync tag file to {folder_path}: {e}")
        return False


def read_sync_tag_file(folder_path: Union[str, Path]) -> Optional[dict]:
    p = Path(folder_path)
    for fname in (SYNC_TAG_FILENAME, "TAG.yaml", "tag.yaml", "TAG.yml", "tag.yml", ".ytmsd_sync_tag"):
        tag_file = p / fname
        if tag_file.is_file():
            try:
                res = {}
                with open(tag_file, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if ':' in line:
                            parts = line.split(':', 1)
                            k = parts[0].strip().lower()
                            v = parts[1].strip().strip("'\"")
                            res[k] = v
                sync_code = (res.get('sync_code') or res.get('sync code') or res.get('code') or '').strip()
                if sync_code and sync_code.upper() != 'XXXX':
                    res['sync_code'] = sync_code
                    style = (res.get('sync_style') or res.get('sync style') or res.get('style') or 'Mirror').strip()
                    res['sync_style'] = style
                    res['deletion_mode'] = 'mirror' if style.lower() == 'mirror' else 'additive'
                    res['chain_name'] = res.get('chain_name') or res.get('chain name') or res.get('name') or p.name
                    res['last_synced'] = res.get('last_synced') or res.get('last synced') or ''
                    return res
            except Exception as e:
                print(f"Error reading sync tag from {tag_file}: {e}")
    return None


# A TAG.yaml records last_synced as a local wall-clock string, while the chain
# dicts in sync-chains.json keep it as an epoch number. Both forms have to be
# comparable before a removable drive is written to, otherwise a client that has
# not spoken to its host in a while can roll a drive that is still current back
# to an older version of the chain.
SYNC_TAG_TIME_FORMATS = ("%m-%d-%Y %H:%M:%S", "%m-%d-%Y %H:%M",
                         "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")

# Two machines' clocks are never perfectly in step. A drive that only looks a
# minute ahead is clock drift, not a newer version of the chain.
SYNC_RETROGRADE_GRACE_SECONDS = 60



def parse_sync_timestamp(value) -> Optional[float]:
    """Normalize a last_synced value - epoch number or TAG.yaml date string - to epoch seconds."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        return ts if ts > 0 else None
    text = str(value).strip()
    if not text:
        return None
    try:  # An epoch stored as text (older configs did this)
        ts = float(text)
        return ts if ts > 0 else None
    except ValueError:
        pass
    for fmt in SYNC_TAG_TIME_FORMATS:
        try:
            return time.mktime(time.strptime(text, fmt))
        except (ValueError, TypeError):
            continue
    return None



def format_sync_timestamp(ts: Optional[float]) -> str:
    """The readable form of a parsed last_synced, for status lines and prompts."""
    if not ts:
        return "never"
    try:
        return time.strftime("%m-%d-%Y %H:%M:%S", time.localtime(ts))
    except (ValueError, OSError, OverflowError):
        return "an unknown time"



def drive_last_synced_timestamp(folder_path: Union[str, Path]) -> Optional[float]:
    """The last_synced recorded in the TAG.yaml sitting on a drive, if it has one."""
    tag = read_sync_tag_file(folder_path)
    if not tag:
        return None
    return parse_sync_timestamp(tag.get('last_synced'))



def find_tagged_sync_folders_on_drive(drive_root: str) -> List[Tuple[Path, dict]]:
    """Scans drive root and one level of subdirectories for yt-msd TAG.yaml files.
    Playlists are always placed as a direct subfolder on the drive root."""
    results = []
    root = Path(drive_root)
    if not root.exists():
        return results

    # 1. Check drive root itself
    tag = read_sync_tag_file(root)
    if tag and tag.get('sync_code'):
        results.append((root, tag))

    # 2. Check direct subdirectories only (depth 1)
    skip_names = {'$recycle.bin', 'system volume information', 'windows',
                  'program files', 'program files (x86)', 'appdata', '.git', '.gemini'}
    try:
        for entry in root.iterdir():
            if entry.is_dir() and entry.name.lower() not in skip_names and not entry.name.startswith('.'):
                tag_data = read_sync_tag_file(entry)
                if tag_data and tag_data.get('sync_code'):
                    results.append((entry, tag_data))
    except (PermissionError, OSError):
        pass

    return results



def make_removable_chain_id(sync_code: str, folder_path: str) -> str:
    """Stable, collision-resistant id for a runtime removable-media chain."""
    digest = hashlib.md5(str(folder_path).encode('utf-8')).hexdigest()[:8]
    return f"rc_{sync_code}_{digest}"
