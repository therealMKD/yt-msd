# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.sync.host).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
import os
import random
import threading
import time
from pathlib import Path
import socket
from typing import Dict, List, Optional, Callable, Tuple
from yt_msd.audio.tags import read_metadata_tags
from yt_msd.constants import AUDIO_EXTENSIONS
from yt_msd.deps import FileSystemEventHandler, Observer, _WATCHDOG_AVAILABLE
from yt_msd.sync.config import host_chain_is_visible
from yt_msd.sync.lan import (DISCOVERY_APP_NAME, RESTORE_CODE_ALPHABET, RESTORE_CODE_LENGTH,
                             SYNC_PORT_END, SYNC_PORT_START, SYNC_RESTORE_CODE_TIMEOUT,
                             SYNC_RESTORE_HANDSHAKE_TIMEOUT, SYNC_SOCKET_TIMEOUT, restore_code_shape)

from yt_msd.sync.transfer import (compute_file_sha256, filter_audio_files, recv_file_from_socket,
                                  recv_json_msg, send_json_msg, stream_file_to_socket)


def hello_reply(hosted_chains: List[dict], requested_code: str = '', active_port: int = 0) -> dict:
    """What a host says about itself to a client that asks before it authenticates.

    This is the answer a network search reads, so it is the only thing the program says about a
    chain to somebody it has not verified. A visible chain is named freely, code and all - which
    is what "visible" means, and what lets a client join it without being given an address and a
    number to type. A private chain is named to no untargeted search at all, and answers only one
    that already put its code on the request: the code is what that client would have to know to
    sync anyway, and naming it back is what turns "I was told a code" into "here is the machine it
    belongs to". The hosted folder's path is deliberately not in the answer - a search is a
    stranger, and it stays a stranger until an AUTH succeeds.
    """
    wanted = str(requested_code or '').strip()
    named: List[dict] = []
    for chain in hosted_chains:
        code = str(chain.get('sync_code', '')).strip()
        if not code or (wanted and wanted != code):
            continue
        visible = host_chain_is_visible(chain)
        if not visible and not wanted:
            continue
        named.append({'sync_code': code,
                      'name': chain.get('name', 'Audio Playlist'),
                      'visible': visible})
    if not named:
        return {'status': 'ERROR',
                'reason': f'Sync code {wanted} not found on host' if wanted
                else 'This host advertises no sync chain'}
    return {'status': 'OK', 'app': DISCOVERY_APP_NAME, 'host_name': socket.gethostname(),
            'port': int(active_port or 0), 'chains': named}


# ---------------------------------------------------------------------------
# Restore offers: the one answer that lets a client rebuild the host
#
# A client that is about to be told "your host has stopped offering 400 files" is the machine that
# still has them, and the host is the machine that has lost them. Restore Host hands that situation
# back to the listener: the host offers a short code on its own screen, somebody reads it to the
# client, and only a client that can name that code is allowed to write into the hosted folder.
# The code lives here rather than on the connection so the window on the host can cancel it, so a
# second client asking about the same chain replaces the offer rather than competing with it, and so
# an offer nobody accepted stops being good on its own.
# ---------------------------------------------------------------------------

_PENDING_RESTORES: Dict[str, dict] = {}

_PENDING_RESTORES_LOCK = threading.Lock()


def new_restore_code(avoid: Optional[str] = None) -> str:
    """Four characters that can be read off a screen and typed in without being misread."""
    while True:
        code = ''.join(random.choice(RESTORE_CODE_ALPHABET) for _ in range(RESTORE_CODE_LENGTH))
        if code != avoid and code not in _PENDING_RESTORES:
            return code


def issue_restore_code(sync_code: str, client_ip: str,
                       timeout: Optional[float] = None) -> dict:
    """Open one restore offer for one chain, and say what it expires at.

    One at a time per chain, on purpose. Two clients holding the same sync code asking the same host
    to rebuild itself at the same moment is a question with one answer, and the host shows that answer
    once: the older offer is closed rather than put beside the newer one.
    """
    key = str(sync_code)
    wait = SYNC_RESTORE_CODE_TIMEOUT if timeout is None else float(timeout)
    with _PENDING_RESTORES_LOCK:
        _PENDING_RESTORES.pop(key, None)
        session = {'code': new_restore_code(), 'sync_code': key, 'client_ip': client_ip,
                   'issued_at': time.time(), 'expires_at': time.time() + wait}
        _PENDING_RESTORES[key] = session
        return dict(session)


def pending_restore_request(sync_code: str) -> Optional[dict]:
    """The offer still open for this chain, or nothing if it has gone stale."""
    with _PENDING_RESTORES_LOCK:
        session = _PENDING_RESTORES.get(str(sync_code))
        if session is None:
            return None
        if session['expires_at'] <= time.time():
            _PENDING_RESTORES.pop(str(sync_code), None)
            return None
        return dict(session)


def take_restore_offer(sync_code: str, typed_code) -> Optional[dict]:
    """Spend an offer on the code the client named, or refuse and close it.

    The offer is taken out of the registry either way. A code that does not match - or that is not a
    code at all - is not something to keep guessing at: it closes the offer, and a client that wants
    another one has to ask again, which puts a fresh code on the host's screen.
    """
    typed = restore_code_shape(typed_code)
    with _PENDING_RESTORES_LOCK:
        session = _PENDING_RESTORES.pop(str(sync_code), None)
    if typed is None or session is None or session['code'] != typed:
        return None
    if session['expires_at'] <= time.time():
        return None
    return dict(session)



def cancel_restore_offer(sync_code: str, code: Optional[str] = None) -> bool:
    """Close an offer from the host's own window.

    `code` is what the window is showing, and it is checked: a card refreshed a moment after somebody
    else was handed the offer must not cancel that one.
    """
    with _PENDING_RESTORES_LOCK:
        session = _PENDING_RESTORES.get(str(sync_code))
        if session is None:
            return False
        if code is not None and str(code).strip().upper() != session['code']:
            return False
        _PENDING_RESTORES.pop(str(sync_code), None)
        return True


def restore_target(folder_path: Path, name) -> Optional[Path]:
    """Where in this hosted folder a restored file may be written, or nothing.

    A restore is the host taking a filename from another machine and writing it, which is the one
    direction in this whole program where that is possible - so the name is read as a name and not as
    a path. Nothing with a separator in it, nothing that climbs out of the folder, nothing without a
    file type a chain can hold. A client offering `..\\..\\secret.wav` is refused the way an over-long
    sync code is: the answer is an error, and the connection carries on.
    """
    raw = str(name or '').strip()
    if not raw or raw in ('.', '..') or raw != Path(raw).name:
        return None
    target = folder_path / raw
    if target.suffix.lower() not in AUDIO_EXTENSIONS:
        return None
    return target





class HostFolderWatcher:
    """Monitors hosted sync chain folders and debounces notifications to avoid spamming."""
    def __init__(self, on_change_callback: Callable[[str], None]):
        self.on_change_callback = on_change_callback
        self.watched_chains: Dict[str, dict] = {}
        # RLock, not Lock: add_or_update_chain() takes this lock and then calls remove_chain(),
        # which takes it again on the same thread. A plain threading.Lock deadlocks that thread
        # where it stands, holding the lock for good - so the first hosted chain ever created
        # silently killed the watcher (no folder change was ever noticed, so clients were never
        # notified), and every later refresh_sync_watchers() call leaked another stuck thread
        # because stop_all(), remove_chain() and add_or_update_chain() all queue on a lock that
        # nobody will ever release again.
        self.lock = threading.RLock()

    def add_or_update_chain(self, chain_id: str, folder_path: str, sync_code: str, delay_mins: int = 5):
        with self.lock:
            self.remove_chain(chain_id)
            if not _WATCHDOG_AVAILABLE:
                return
            p = Path(folder_path)
            if not p.is_dir():
                return

            delay_sec = max(5, delay_mins * 60)

            class Handler(FileSystemEventHandler):
                def __init__(self, watcher_ref, cid):
                    self.watcher_ref = watcher_ref
                    self.cid = cid
                def on_any_event(self, event):
                    src = getattr(event, 'src_path', '')
                    dest = getattr(event, 'dest_path', '')
                    ext1 = os.path.splitext(src)[1].lower() if src else ''
                    ext2 = os.path.splitext(dest)[1].lower() if dest else ''
                    if ext1 in AUDIO_EXTENSIONS or ext2 in AUDIO_EXTENSIONS:
                        self.watcher_ref._trigger_debounce(self.cid)

            observer = Observer()
            observer.daemon = True
            handler = Handler(self, chain_id)
            observer.schedule(handler, str(p), recursive=False)
            observer.start()

            self.watched_chains[chain_id] = {
                'folder_path': folder_path,
                'sync_code': sync_code,
                'delay_sec': delay_sec,
                'timer': None,
                'observer': observer
            }

    def remove_chain(self, chain_id: str):
        obs = None
        timer = None
        with self.lock:
            info = self.watched_chains.pop(chain_id, None)
            if info:
                timer = info.get('timer')
                obs = info.get('observer')
        if timer and timer.is_alive():
            timer.cancel()
        if obs:
            try:
                obs.stop()
                obs.join(timeout=0.3)
            except Exception:
                pass

    def stop_all(self):
        with self.lock:
            chain_ids = list(self.watched_chains.keys())
        for cid in chain_ids:
            self.remove_chain(cid)

    def _trigger_debounce(self, chain_id: str):
        with self.lock:
            info = self.watched_chains.get(chain_id)
            if not info:
                return
            timer = info.get('timer')
            if timer and timer.is_alive():
                timer.cancel()

            sync_code = info['sync_code']
            delay_sec = info['delay_sec']

            def _fire():
                self.on_change_callback(sync_code)

            new_timer = threading.Timer(delay_sec, _fire)
            new_timer.daemon = True
            info['timer'] = new_timer
            new_timer.start()



class SyncHostServer:
    """TCP Server serving hosted sync chains to connected clients."""
    def __init__(self, get_hosted_chains_cb: Callable[[], List[dict]],
                 on_client_activity_cb: Optional[Callable[[str, str, str], None]] = None,
                 on_restore_event_cb: Optional[Callable[[str, str, str, str], None]] = None):
        self.get_hosted_chains_cb = get_hosted_chains_cb
        self.on_client_activity_cb = on_client_activity_cb
        # Called as (sync_code, client_ip, event, note) at each point of a restore the window has to
        # know about: 'requested' (someone is waiting for the code this host has just made), 'started'
        # (the code was named correctly and the rebuild is writing now), 'cancelled' (either side backed
        # out), 'finished' (this half is a host again). Everything else about a restore happens between
        # the two sockets.
        self.on_restore_event_cb = on_restore_event_cb
        self.server_sock: Optional[socket.socket] = None
        self.active_port: int = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        # Chains whose hosted folder is being rebuilt, and the machine it is coming from. The folder
        # watcher fires once per file written and a rebuild is thousands of them; a client told about a
        # half-built copy can sync against it, and a Mirror chain syncing against a half-built copy
        # deletes files to match it. This is what the window checks before it notifies anybody, and what
        # keeps other clients off a folder that is mid-rewrite.
        self._restoring: Dict[str, str] = {}
        self._restoring_lock = threading.Lock()

    def is_restoring(self, sync_code) -> bool:
        """Is this chain's hosted folder being rebuilt from a client right now?"""
        with self._restoring_lock:
            return str(sync_code) in self._restoring

    def restoring_from(self, sync_code) -> Optional[str]:
        """Which machine the rebuild is coming from, for the host card and the status line."""
        with self._restoring_lock:
            return self._restoring.get(str(sync_code))

    def cancel_restore_request(self, sync_code, code: Optional[str] = None) -> bool:
        """Close a code this host has offered and nobody has named yet."""
        return cancel_restore_offer(sync_code, code)

    def _restore_event(self, event: str, sync_code: str, client_ip: str, note):
        if self.on_restore_event_cb is None:
            return
        try:
            self.on_restore_event_cb(sync_code, client_ip, event, str(note))
        except Exception:
            pass


    def start(self) -> int:
        if self._running:
            return self.active_port

        for port in range(SYNC_PORT_START, SYNC_PORT_END + 1):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('', port))
                s.listen(10)
                self.server_sock = s
                self.active_port = port
                self._running = True
                self._thread = threading.Thread(target=self._accept_loop, daemon=True)
                self._thread.start()
                return port
            except OSError:
                continue
        return 0

    def stop(self):
        self._running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
            self.server_sock = None
        self.active_port = 0

    def _accept_loop(self):
        while self._running and self.server_sock:
            try:
                client_sock, (client_ip, client_port) = self.server_sock.accept()
                threading.Thread(target=self._handle_client, args=(client_sock, client_ip), daemon=True).start()
            except OSError:
                break

    def _handle_client(self, sock: socket.socket, client_ip: str):
        try:
            sock.settimeout(SYNC_SOCKET_TIMEOUT)
            first_msg = recv_json_msg(sock)
            if not first_msg:
                return

            if first_msg.get('cmd') == 'HELLO':
                # Somebody searching the network rather than a client: one answer, and then the
                # connection is done with. It is deliberately not reported as chain activity - a
                # search touches every host on the LAN, and a host card that flashed for each one
                # would be reporting something that is not true.
                send_json_msg(sock, hello_reply(self.get_hosted_chains_cb(),
                                                first_msg.get('sync_code', ''), self.active_port))
                return

            auth_msg = first_msg
            if auth_msg.get('cmd') != 'AUTH':
                send_json_msg(sock, {'status': 'ERROR', 'reason': 'Expected AUTH command'})
                return

            sync_code = str(auth_msg.get('sync_code', ''))
            chains = self.get_hosted_chains_cb()
            matching_chain = None
            for c in chains:
                if str(c.get('sync_code')) == sync_code:
                    matching_chain = c
                    break

            if not matching_chain:
                send_json_msg(sock, {'status': 'ERROR', 'reason': f'Sync code {sync_code} not found on host'})
                return

            folder_path = Path(matching_chain.get('folder_path', ''))
            if not folder_path.is_dir():
                send_json_msg(sock, {'status': 'ERROR', 'reason': 'Hosted folder path does not exist on disk'})
                return

            audio_files = filter_audio_files(folder_path)
            send_json_msg(sock, {
                'status': 'OK',
                'chain_name': matching_chain.get('name', 'Audio Playlist'),
                'files_count': len(audio_files)
            })

            if self.on_client_activity_cb:
                self.on_client_activity_cb(sync_code, client_ip, 'Connected')

            # The code this connection was offered, if it asked for one. It is kept here rather than
            # looked up again from the registry because it belongs to this connection: a second client
            # asking about the same chain takes the offer away from the registry, and the machine that
            # is still sitting on this socket has to be able to find out that it lost.
            restore_offer = None

            while self._running:
                req = recv_json_msg(sock, timeout=30.0)
                if not req:
                    break
                cmd = req.get('cmd')
                if cmd == 'GET_INDEX':
                    if self.is_restoring(sync_code):
                        # Another machine is rewriting this folder right now, and a list of it taken
                        # half-way through is a list of a folder that does not exist yet. A client that
                        # compared against it would download the wrong things - and a Mirror chain would
                        # delete the right ones.
                        send_json_msg(sock, {'status': 'ERROR',
                                             'reason': 'This host is being rebuilt from another PC; try again in a moment'})
                        continue
                    index = []

                    for f in filter_audio_files(folder_path):
                        try:
                            stat = f.stat()
                            art, tit = read_metadata_tags(f)
                            sha = compute_file_sha256(f)
                            index.append({
                                'name': f.name,
                                'size': stat.st_size,
                                'mtime': stat.st_mtime,
                                'sha256': sha,
                                'artist': art,
                                'title': tit
                            })
                        except Exception:
                            pass
                    send_json_msg(sock, {'status': 'OK', 'files': index})

                elif cmd == 'PULL_FILE':
                    filename = req.get('filename', '')
                    target_file = folder_path / filename
                    if self.is_restoring(sync_code):
                        send_json_msg(sock, {'status': 'ERROR', 'reason': 'This host is being rebuilt from another PC'})
                    elif not target_file.is_file() or target_file.suffix.lower() not in AUDIO_EXTENSIONS:
                        send_json_msg(sock, {'status': 'ERROR', 'reason': 'File not found or not an audio file'})

                    else:
                        size = target_file.stat().st_size
                        sha = compute_file_sha256(target_file)
                        send_json_msg(sock, {
                            'status': 'SENDING',
                            'filename': filename,
                            'filesize': size,
                            'sha256': sha
                        })
                        if self.on_client_activity_cb:
                            self.on_client_activity_cb(sync_code, client_ip, f'Sending {filename}')
                        stream_file_to_socket(sock, target_file)

                elif cmd == 'PING':
                    # A client holding a connection open while somebody reads a code off the host's
                    # screen keeps this connection alive with nothing else to say. If the offer behind
                    # it has gone - cancelled on this machine's screen, replaced by another client's
                    # request, or simply out of time - the waiting machine is told instead of left
                    # waiting for a code that is never coming back.
                    if restore_offer is not None and pending_restore_request(sync_code) is None:
                        send_json_msg(sock, {'status': 'RESTORE_CLOSED',
                                             'reason': 'That restore offer is no longer open on the host'})
                        self._restore_event('cancelled', sync_code, client_ip, 'offer closed')
                        break
                    send_json_msg(sock, {'status': 'PONG'})

                elif cmd == 'RESTORE_REQUEST':
                    # "Your host has stopped offering 400 files, and this machine is the one that still
                    # has them." The host does not send the code down the wire - the whole point is that
                    # it appears on this screen and nowhere else, and the only way a client gets it is
                    # somebody reading it out.
                    if restore_offer is not None:
                        send_json_msg(sock, {'status': 'ERROR',
                                             'reason': 'This connection already has a restore offer open'})
                    elif self.is_restoring(sync_code):
                        send_json_msg(sock, {'status': 'ERROR',
                                             'reason': 'This host is already being rebuilt from another PC'})
                    else:
                        session = issue_restore_code(sync_code, client_ip)
                        restore_offer = session['code']
                        send_json_msg(sock, {'status': 'WAITING_FOR_CODE',
                                             'chain_name': matching_chain.get('name', 'Audio Playlist'),
                                             'expires_in': int(session['expires_at'] - session['issued_at'])})
                        self._restore_event('requested', sync_code, client_ip, session['code'])
                        if self.on_client_activity_cb:
                            self.on_client_activity_cb(sync_code, client_ip, 'Restore requested')

                elif cmd == 'RESTORE_CONFIRM':
                    if restore_offer is None:
                        send_json_msg(sock, {'status': 'ERROR',
                                             'reason': 'No restore offer is open on this connection'})
                    else:
                        granted = take_restore_offer(sync_code, req.get('code'))
                        restore_offer = None
                        if granted is None:
                            # The wrong code is an answer, not a hint. It closes the offer rather than
                            # leaving it open to be guessed at, and the client keeps its own copy of
                            # everything and its connection.
                            send_json_msg(sock, {'status': 'ERROR',
                                                 'reason': 'That is not the code on the host screen'})
                            self._restore_event('cancelled', sync_code, client_ip, 'wrong code')
                        else:
                            # Answered before the rebuild starts rather than after it: the client is
                            # about to spend a while adding up its own library, and it should find out
                            # in this moment - and not after that work - whether the code it typed was
                            # the one on this screen.
                            send_json_msg(sock, {'status': 'CODE_ACCEPTED',
                                                 'chain_name': matching_chain.get('name', 'Audio Playlist')})
                            self._restore_event('started', sync_code, client_ip, granted['code'])
                            received, note = self._receive_restore(sock, folder_path, sync_code, client_ip)
                            self._restore_event('finished', sync_code, client_ip, f"{received}: {note}")
                            break


                elif cmd == 'RESTORE_CANCEL':
                    # The client changed its mind, or the person at it gave up reading the code out.
                    # Closed here so this machine's screen stops showing a code that is no longer any
                    # use to anyone.
                    cancel_restore_offer(sync_code, restore_offer)
                    restore_offer = None
                    send_json_msg(sock, {'status': 'CANCELLED'})
                    self._restore_event('cancelled', sync_code, client_ip, 'client cancelled')
                    break

                else:
                    send_json_msg(sock, {'status': 'ERROR', 'reason': f'Unknown command: {cmd}'})

        except Exception:
            pass
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def _restore_shortlist(self, folder_path: Path, offered: List[dict]) -> Tuple[List[str], int]:
        """Which of the client's files this folder still needs, and how many it already holds.

        Already-held is decided by size and checksum and not by name, so a host that has most of the
        library back is not sent the library again, and a host whose copy of a file is a different file
        - a re-encode, a half-written download - is sent the one the client actually has.
        """
        needed: List[str] = []
        already = 0
        for entry in offered:
            target = restore_target(folder_path, entry.get('name', ''))
            if target is None:
                continue
            if target.is_file():
                try:
                    same_size = target.stat().st_size == int(entry.get('size') or -1)
                    promised = str(entry.get('sha256') or '')
                    if same_size and promised and compute_file_sha256(target) == promised:
                        already += 1
                        continue
                except Exception:
                    pass
            needed.append(target.name)
        return needed, already

    def _receive_restore(self, sock: socket.socket, folder_path: Path, sync_code: str,
                         client_ip: str) -> Tuple[int, str]:
        """Rebuild this hosted folder from the client's copy, and hand the host back to itself.

        This is the one place in the program where a host writes into its hosted folder instead of
        reading out of it, so it is kept as narrow as the wire can be made: every name is checked
        against the folder it would be written into, only file types a chain can hold are taken, a file
        this folder already holds byte for byte is not written twice, and nothing is ever deleted. A
        machine that has just lost its own copy has no business deleting anything on the word of the
        machine that still has one - if the two copies genuinely differ, the difference shows up as a
        download on the next ordinary sync, which is the half that asks.
        """
        with self._restoring_lock:
            self._restoring[sync_code] = client_ip
        try:
            index_msg = recv_json_msg(sock, timeout=SYNC_RESTORE_HANDSHAKE_TIMEOUT)
            if not index_msg or index_msg.get('cmd') != 'PUSH_INDEX':
                send_json_msg(sock, {'status': 'ERROR', 'reason': 'The restore index never arrived'})
                return 0, 'the client never sent its index'

            needed, already_there = self._restore_shortlist(folder_path, index_msg.get('files') or [])
            send_json_msg(sock, {'status': 'RESTORING', 'files': needed,
                                 'already_there': already_there})

            # Only what this host asked for. The client named its whole library a moment ago and this
            # folder answered with the part of it it still needs; a file that arrives that was not on
            # that list is the client overwriting something this folder already holds byte for byte,
            # which is not what a restore was asked for.
            awaited = set(needed)
            received = 0
            while self._running:
                req = recv_json_msg(sock, timeout=SYNC_RESTORE_HANDSHAKE_TIMEOUT)
                if not req:
                    break
                cmd = req.get('cmd')
                if cmd == 'PUSH_FILE':
                    target = restore_target(folder_path, req.get('filename', ''))
                    filesize = int(req.get('filesize') or 0)
                    promised_sha = str(req.get('sha256') or '')
                    if target is None:
                        send_json_msg(sock, {'status': 'ERROR',
                                             'reason': 'Not a name this folder can hold'})
                        continue
                    if target.name not in awaited:
                        send_json_msg(sock, {'status': 'ERROR',
                                             'reason': 'This host did not ask for that file'})
                        continue
                    if filesize <= 0:
                        send_json_msg(sock, {'status': 'ERROR', 'reason': 'No size given for that file'})
                        continue
                    if len(promised_sha) != 64:
                        send_json_msg(sock, {'status': 'ERROR',
                                             'reason': 'No checksum to check that file against'})
                        continue
                    send_json_msg(sock, {'status': 'RECEIVING', 'filename': target.name})
                    if not recv_file_from_socket(sock, target, filesize, promised_sha):
                        send_json_msg(sock, {'status': 'ERROR',
                                             'reason': 'That file did not arrive whole'})
                        continue
                    try:
                        # The date the track was made, not the date it landed here. A restored copy that
                        # looks newer than every other copy is the thing that makes a chain decide it has
                        # to be re-fetched, and a rebuild of a whole library is not a reason for one.
                        mtime = float(req.get('mtime') or 0.0)
                        if mtime > 0:
                            os.utime(target, (time.time(), mtime))
                    except Exception:
                        pass
                    awaited.discard(target.name)
                    received += 1
                    send_json_msg(sock, {'status': 'OK', 'filename': target.name})
                    if self.on_client_activity_cb:
                        self.on_client_activity_cb(sync_code, client_ip, f'Restoring {target.name}')
                elif cmd == 'PUSH_DONE':
                    send_json_msg(sock, {'status': 'SYNCED', 'received': received,
                                         'missing': sorted(awaited)})
                    if awaited:
                        return received, f"{received} rebuilt, {len(awaited)} the host asked for never arrived"
                    return received, f"{received} file(s) rebuilt, {already_there} already there"
                else:
                    send_json_msg(sock, {'status': 'ERROR', 'reason': f'Unknown command: {cmd}'})
                    return received, f'the client sent {cmd} in the middle of a restore'
            return received, 'the client stopped in the middle of a restore'

        finally:
            with self._restoring_lock:
                self._restoring.pop(sync_code, None)

