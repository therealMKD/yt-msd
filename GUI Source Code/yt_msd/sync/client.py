# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.sync.client).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
import os
from pathlib import Path
import threading
import time
import socket
from typing import List, Optional, Tuple, Callable
from PySide6.QtCore import Signal, QThread
from yt_msd.audio.tags import read_metadata_tags, write_metadata_tags
from yt_msd.sync.config import delete_confirm_limit
from yt_msd.sync.discovery import discover_host_on_lan
from yt_msd.sync.lan import SYNC_CONFIRM_PING_INTERVAL, SYNC_SOCKET_TIMEOUT, get_local_ip
from yt_msd.sync.transfer import compute_file_sha256, filter_audio_files, get_drive_io_lock, make_throttled_progress_cb, recv_file_from_socket, recv_json_msg, send_json_msg


class _HostKeepalive:
    """Keeps a host patient while the client has stopped to ask the user something.

    A host reads the next command with a 30-second timeout (SyncHostServer._handle_client), so a
    client that parks to show a dialog would find the connection closed and the whole sync
    reported as a failure before anyone had answered. While it runs, this sends PING - the one
    command every host since 3.0 answers - often enough that the host's read never times out, and
    throws the reply away. It is only ever started for the length of one question, so an ordinary
    sync sends exactly the commands it always sent, and nothing else may touch the socket while it
    is running.
    """

    def __init__(self, sock: socket.socket, interval: Optional[float] = None):
        self.sock = sock
        # Read when it is asked for rather than bound when this is defined, so the value the
        # program holds is the value used - and so the test harness can shorten it.
        self.interval = SYNC_CONFIRM_PING_INTERVAL if interval is None else interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _run(self):
        # Event.wait rather than a sleep: a question answered at once stops this before it has
        # sent anything.
        while not self._stop.wait(self.interval):
            try:
                send_json_msg(self.sock, {'cmd': 'PING'})
                recv_json_msg(self.sock, timeout=self.interval)
            except Exception:
                # The host is not answering any more. Stop rather than keep writing into a
                # connection nobody is reading; the sync finds that out when it resumes, and says
                # so the way it always has.
                return

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            # Long enough that the thread has finished whatever send/recv pair it was in. Joining
            # short would leave a PONG unread on a socket the sync is about to read a file answer
            # from, and the client would mistake the answer to its PING for the answer to its pull.
            self._thread.join(timeout=self.interval + 1.0)


# The wording a sync_chain message carries when the user refused a batch of deletions. Named here
# so the one place that builds it and the places that look for it cannot drift apart.
DELETIONS_DECLINED_NOTE = "deletion(s) left undone - you said no."


def deletions_were_declined(message) -> bool:
    """Whether a finished client sync is reporting deletions the user turned down."""
    return DELETIONS_DECLINED_NOTE in str(message)


def _deletion_question(dest_folder: Path, names: List[str], limit: int) -> str:
    """The text a client shows before deleting more tracks than its chain may delete on its own."""
    shown = names[:8]
    listing = "\n".join(f"    {name}" for name in shown)
    hidden = len(names) - len(shown)
    if hidden > 0:
        listing += f"\n    ... and {hidden} more"
    return (
        f"The host has stopped offering {len(names)} file(s) that are in:\n"
        f"    {dest_folder}\n\n"
        f"{listing}\n\n"
        f"Delete {len(names)} file(s)?\n\n"
        f"(This chain asks once it has more than {limit} to delete. Change that number in Sync "
        f"Chains - or set it to 0 to delete any number without being asked.)"
    )


def make_delete_confirm_cb(app, chain_name: str) -> Optional[Callable[[str], bool]]:
    """The confirm_cb a client sync is given when something on screen can answer it.

    The worker calls this from its own thread. The app it is built from puts the question on the
    GUI thread and parks this one until the answer comes back. An app that cannot ask - a stand-in
    in the test suite, a probe calling the worker directly - gets None, which the worker reads as
    "nobody is here to ask", and the chain deletes the way it always has.
    """
    ask = getattr(app, 'ask_sync_confirm', None)
    if not callable(ask):
        return None

    def _confirm(question: str) -> bool:
        return bool(ask(f"Sync Chain '{chain_name}' - Delete Files?", question))

    return _confirm



class SyncClientWorker:
    """Executes client synchronization against a remote host."""
    @staticmethod
    def sync_chain(chain_config: dict,
                   status_cb: Optional[Callable[[str], None]] = None,
                   progress_cb: Optional[Callable[[int, int, str, int, int], None]] = None,
                   confirm_cb: Optional[Callable[[str], bool]] = None) -> Tuple[bool, str, int, int]:
        sync_code = str(chain_config.get('sync_code', ''))
        folder_str = chain_config.get('folder_path', '')
        dest_folder = Path(folder_str)
        dest_folder.mkdir(parents=True, exist_ok=True)

        host_ip = chain_config.get('last_known_host_ip', '')
        host_port = int(chain_config.get('host_port', 63350))
        deletion_mode = chain_config.get('deletion_mode', 'mirror')

        # Progress is reported at a bounded rate no matter how fast the device
        # is, so a sync can never starve the UI event loop.
        progress_cb = make_throttled_progress_cb(progress_cb)

        if status_cb:
            status_cb(f"Connecting to host for Sync Code {sync_code}...")

        sock = None
        if host_ip and host_port > 0:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3.0)
                sock.connect((host_ip, host_port))
            except Exception:
                sock = None

        if not sock:
            if status_cb:
                status_cb(f"Host unreachable at {host_ip}. Broadcasting LAN discovery...")
            found = discover_host_on_lan(sync_code, timeout=3.0)
            if not found:
                return False, f"Could not find active host for Sync Code {sync_code} on local network.", 0, 0
            host_ip, host_port, host_chain = found
            chain_config['last_known_host_ip'] = host_ip
            chain_config['host_port'] = host_port
            # The name came back with the address. A chain whose host changed address is found again
            # by its code, and the answer that found it names the chain - which is the name the host
            # calls it by, and the one worth having on the card for a chain whose own folder name was
            # typed in by hand.
            if host_chain:
                chain_config['host_chain_name'] = str(host_chain).strip()
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(SYNC_SOCKET_TIMEOUT)
                sock.connect((host_ip, host_port))
            except Exception as e:
                return False, f"Failed to connect to host at {host_ip}:{host_port}: {e}", 0, 0

        transferred = 0
        deleted = 0
        # Tracks a Mirror sync was asked to delete and the user said no to. They stay on disk, and
        # the count is what the status line and the returned message report them with.
        unconfirmed = 0
        # Everything below reads and writes dest_folder, which may be a slow
        # device: hold the per-drive lock so only one sync works it over.
        drive_lock = get_drive_io_lock(dest_folder)
        drive_lock.acquire()
        try:
            sock.settimeout(SYNC_SOCKET_TIMEOUT)
            send_json_msg(sock, {'cmd': 'AUTH', 'sync_code': sync_code, 'client_ip': get_local_ip()})
            auth_resp = recv_json_msg(sock)
            if not auth_resp or auth_resp.get('status') != 'OK':
                err = auth_resp.get('reason', 'Authentication rejected by host') if auth_resp else 'No auth response'
                return False, err, 0, 0

            # The host names its own chain in the answer to an AUTH, and that name is the one the
            # host's card shows and the folder on the host carries. A chain joined by an address and
            # a code typed in by hand had no way of ever learning it, so a client that joined
            # "Christian" by number kept calling it whatever it typed into the connect window.
            host_chain_name = str(auth_resp.get('chain_name') or '').strip()
            if host_chain_name:
                chain_config['host_chain_name'] = host_chain_name

            if status_cb:
                status_cb("Fetching file index from host...")
            send_json_msg(sock, {'cmd': 'GET_INDEX'})
            index_resp = recv_json_msg(sock, timeout=25.0)
            if not index_resp or index_resp.get('status') != 'OK':
                return False, "Failed to retrieve file index from host.", 0, 0

            host_files: List[dict] = index_resp.get('files', [])
            host_files_map = {f['name']: f for f in host_files}

            local_files = filter_audio_files(dest_folder)
            local_files_map = {f.name: f for f in local_files}

            def _remove_offered_no_more(names: List[str]):
                nonlocal deleted
                for local_name in names:
                    local_path = local_files_map.get(local_name)
                    if local_path is None:
                        continue
                    try:
                        local_path.unlink()
                        deleted += 1
                        if status_cb:
                            status_cb(f"Removed deleted track: {local_name}")
                    except Exception:
                        pass

            # Everything Mirror mode would delete, listed before a single file is removed. Only a
            # Mirror chain deletes at all, so an Additive chain never reaches the question, and a
            # removable-media sync (which pulls from here but writes to a drive) is handed no
            # confirm_cb and so is never held up asking either.
            doomed = [name for name in local_files_map if name not in host_files_map] \
                if deletion_mode == 'mirror' else []
            limit = delete_confirm_limit(chain_config)

            if doomed:
                if confirm_cb is None or limit == 0 or len(doomed) <= limit:
                    _remove_offered_no_more(doomed)
                else:
                    if status_cb:
                        status_cb(f"Host no longer offers {len(doomed)} local track(s) - asking before deleting...")
                    # The host gives up on an idle connection after 30 seconds, so the connection
                    # is kept warm for as long as the user takes.
                    keepalive = _HostKeepalive(sock)
                    keepalive.start()
                    try:
                        approved = bool(confirm_cb(_deletion_question(dest_folder, doomed, limit)))
                    finally:
                        keepalive.stop()
                    if approved:
                        _remove_offered_no_more(doomed)
                    else:
                        unconfirmed = len(doomed)
                        if status_cb:
                            status_cb(f"Deletions not confirmed - {unconfirmed} track(s) left where they are")

            total_items = len(host_files)
            for idx, hf in enumerate(host_files, 1):
                name = hf['name']
                h_size = hf['size']
                h_sha256 = hf['sha256']
                h_mtime = hf.get('mtime', 0)
                h_artist = hf.get('artist')
                h_title = hf.get('title')

                target_path = dest_folder / name
                needs_download = False
                needs_tag_update = False

                if not target_path.exists():
                    needs_download = True
                else:
                    l_size = target_path.stat().st_size
                    l_mtime = target_path.stat().st_mtime
                    if l_size != h_size or h_mtime > l_mtime + 1.0:
                        l_sha256 = compute_file_sha256(target_path)
                        if l_sha256.lower() != h_sha256.lower():
                            l_art, l_tit = read_metadata_tags(target_path)
                            if (l_art != h_artist or l_tit != h_title) and abs(l_size - h_size) < 4096:
                                write_metadata_tags(target_path, h_artist or "", h_title or "")
                                if compute_file_sha256(target_path).lower() == h_sha256.lower():
                                    needs_tag_update = True
                                else:
                                    needs_download = True
                            else:
                                needs_download = True

                if needs_download:
                    if status_cb:
                        status_cb(f"Downloading [{idx}/{total_items}]: {name}")
                    send_json_msg(sock, {'cmd': 'PULL_FILE', 'filename': name})
                    pull_resp = recv_json_msg(sock)
                    if not pull_resp or pull_resp.get('status') != 'SENDING':
                        continue

                    def _progress(bytes_done, bytes_total, _name=name, _idx=idx, _tot=total_items):
                        if progress_cb:
                            progress_cb(bytes_done, bytes_total, _name, _idx, _tot)

                    ok = recv_file_from_socket(sock, target_path, h_size, h_sha256, _progress)
                    if ok:
                        transferred += 1
                        try:
                            os.utime(target_path, (time.time(), h_mtime))
                        except Exception:
                            pass
                elif needs_tag_update:
                    if status_cb:
                        status_cb(f"Updated metadata [{idx}/{total_items}]: {name}")
                    transferred += 1

            note = f" {unconfirmed} {DELETIONS_DECLINED_NOTE}" if unconfirmed else ""
            return True, f"Synced successfully ({transferred} updated, {deleted} removed).{note}", transferred, deleted
        except Exception as e:
            return False, f"Sync error: {e}", transferred, deleted
        finally:
            drive_lock.release()
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass



class ClientSyncThread(QThread):
    status_signal = Signal(str)
    progress_signal = Signal(int, int, str, int, int)
    finished_signal = Signal(bool, str, int, int)

    def __init__(self, chain_config: dict, confirm_cb: Optional[Callable[[str], bool]] = None):
        super().__init__()
        self.chain_config = chain_config
        # Left None by anything that cannot put a question on screen; the worker then proceeds
        # exactly as it did before this existed.
        self.confirm_cb = confirm_cb

    def run(self):
        def _status(txt):
            self.status_signal.emit(txt)

        def _progress(done, total, filename, idx, total_items):
            self.progress_signal.emit(done, total, filename, idx, total_items)

        ok, msg, transferred, deleted = SyncClientWorker.sync_chain(
            self.chain_config,
            status_cb=_status,
            progress_cb=_progress,
            confirm_cb=self.confirm_cb
        )
        self.finished_signal.emit(ok, msg, transferred, deleted)
