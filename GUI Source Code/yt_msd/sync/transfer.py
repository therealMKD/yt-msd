# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.sync.transfer).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
import json
import threading
from pathlib import Path
import time
import socket
import struct
import hashlib
from typing import Dict, List, Optional, Callable, Union
from yt_msd.constants import AUDIO_EXTENSIONS
from yt_msd.sync.lan import SYNC_CHUNK_SIZE, SYNC_SOCKET_TIMEOUT



def compute_file_sha256(filepath: Path) -> str:
    """Computes SHA-256 hash of a file in streaming chunks."""
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(SYNC_CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()



def filter_audio_files(folder_path: Path) -> List[Path]:
    """Scans folder non-recursively, filtering ONLY audio files (ignoring dirs, zips, etc.)."""
    if not folder_path.is_dir():
        return []
    files = []
    try:
        for entry in folder_path.iterdir():
            if entry.is_file() and entry.suffix.lower() in AUDIO_EXTENSIONS:
                files.append(entry)
    except Exception:
        pass
    return sorted(files, key=lambda p: p.name.lower())



# ---------------------------------------------------------------------------
# Slow-device helpers
#
# A sluggish USB stick or MP3 player can stall a single directory call for
# several seconds while it is busy. Anything running on the GUI thread must
# therefore never touch one of those devices directly - it reads the cached
# results produced by the background probe instead, and every real file
# operation happens inside a worker thread.
# ---------------------------------------------------------------------------

_DRIVE_IO_LOCKS: Dict[str, threading.RLock] = {}

_DRIVE_IO_LOCKS_GUARD = threading.Lock()



def get_drive_io_lock(path: Union[str, Path]) -> threading.RLock:
    """Per-drive lock so only one sync ever hammers a given device at a time.

    Reentrant: a removable chain may sync a client folder that lives on the
    very same device, and nested acquisition must not deadlock.
    """
    try:
        anchor = str(Path(path).anchor) or str(path)
    except Exception:
        anchor = str(path)
    with _DRIVE_IO_LOCKS_GUARD:
        lock = _DRIVE_IO_LOCKS.get(anchor)
        if lock is None:
            lock = threading.RLock()
            _DRIVE_IO_LOCKS[anchor] = lock
        return lock



def make_throttled_progress_cb(progress_cb: Optional[Callable[[int, int, str, int, int], None]],
                              min_interval: float = 0.15):
    """Coalesce progress callbacks so a long sync cannot flood the GUI queue."""
    if progress_cb is None:
        return None
    last = [0.0]

    def _emit(done, total, name, idx, total_items):
        now = time.monotonic()
        is_final = total > 0 and done >= total
        if is_final or (now - last[0]) >= min_interval:
            last[0] = now
            progress_cb(done, total, name, idx, total_items)

    return _emit



def send_json_msg(sock: socket.socket, data: dict) -> None:
    raw = json.dumps(data).encode('utf-8')
    header = struct.pack('!I', len(raw))
    sock.sendall(header + raw)



def recv_json_msg(sock: socket.socket, timeout: float = SYNC_SOCKET_TIMEOUT) -> Optional[dict]:
    sock.settimeout(timeout)
    header = _recv_all(sock, 4)
    if not header:
        return None
    length = struct.unpack('!I', header)[0]
    payload = _recv_all(sock, length)
    if not payload:
        return None
    return json.loads(payload.decode('utf-8'))



def _recv_all(sock: socket.socket, n: int) -> Optional[bytes]:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)



def stream_file_to_socket(sock: socket.socket, filepath: Path, progress_cb: Optional[Callable[[int, int], None]] = None) -> str:
    total_size = filepath.stat().st_size
    h = hashlib.sha256()
    sent_bytes = 0
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(SYNC_CHUNK_SIZE)
            if not chunk:
                break
            sock.sendall(chunk)
            h.update(chunk)
            sent_bytes += len(chunk)
            if progress_cb:
                progress_cb(sent_bytes, total_size)
    return h.hexdigest()



def recv_file_from_socket(sock: socket.socket, target_path: Path, expected_size: int, expected_sha256: str,
                          progress_cb: Optional[Callable[[int, int], None]] = None) -> bool:
    tmp_path = target_path.with_suffix(target_path.suffix + '.tmp_sync')
    h = hashlib.sha256()
    received_bytes = 0
    try:
        with open(tmp_path, 'wb') as f:
            while received_bytes < expected_size:
                to_read = min(SYNC_CHUNK_SIZE, expected_size - received_bytes)
                chunk = sock.recv(to_read)
                if not chunk:
                    raise ConnectionError("Socket closed prematurely while receiving file")
                f.write(chunk)
                h.update(chunk)
                received_bytes += len(chunk)
                if progress_cb:
                    progress_cb(received_bytes, expected_size)

        actual_sha256 = h.hexdigest()
        if actual_sha256.lower() != expected_sha256.lower():
            if tmp_path.exists():
                tmp_path.unlink()
            return False

        if target_path.exists():
            target_path.unlink()
        tmp_path.replace(target_path)
        return True
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        return False
