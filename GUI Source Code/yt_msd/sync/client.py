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
from yt_msd.sync.lan import (SYNC_CONFIRM_PING_INTERVAL, SYNC_RESTORE_HANDSHAKE_TIMEOUT,
                             SYNC_SOCKET_TIMEOUT, get_local_ip, restore_code_shape)

from yt_msd.sync.transfer import (compute_file_sha256, filter_audio_files, get_drive_io_lock,
                                  make_throttled_progress_cb, recv_file_from_socket, recv_json_msg,
                                  send_json_msg, stream_file_to_socket)



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


# The three answers a client sync accepts to "the host has stopped offering these files". They are
# words and not button numbers because the box that asks is built on the GUI thread and the sync that
# acts on the answer runs on a worker thread, and the two must be able to agree on what was answered
# without either of them knowing what the other's buttons are called.
SYNC_DECISION_KEEP = 'keep'

SYNC_DECISION_DELETE = 'delete'

# The third answer, and the one that changes what the rest of the sync does: rather than agreeing to
# lose files this machine still has, this machine offers to rebuild the other end of the chain from
# them. See SyncClientWorker._rebuild_host.
SYNC_DECISION_RESTORE = 'restore'


def deletions_were_declined(message) -> bool:
    """Whether a finished client sync is reporting deletions the user turned down."""
    return DELETIONS_DECLINED_NOTE in str(message)


# The wording a sync_chain message carries when the answer to the same warning was Restore Host. Same
# reason as above: the windows that report a finished sync are not the ones that ran it, and they
# should not have to guess which of the three answers the box gave.
HOST_REBUILT_NOTE = "Host rebuilt from this PC"


def host_was_rebuilt(message) -> bool:
    """Whether a finished client sync is reporting that it rebuilt the host instead of deleting."""
    return HOST_REBUILT_NOTE in str(message)


# The two sentences every failed restore ends with, on both halves of the exchange: either nothing was
# deleted here, or the host was left as it was. Named here because the windows that report a chain need
# to tell a restore that did not happen apart from a host that could not be reached - a chain whose
# rebuild was refused, cancelled or mistyped is a chain that reached its host and did nothing, and
# marking it "offline" for that is a lie about the machine it is sitting next to.
RESTORE_UNDONE_NOTES = ("Nothing was deleted here.", "The host was left exactly as it is.")


def restore_was_left_undone(message) -> bool:
    """Whether a failed client sync is reporting a Restore Host that did not take place."""
    # Compared in lower case because these sentences are read out of a longer line that a sentence in
    # the middle of does not start: "Restore Host cancelled - the host was left exactly as it is." is
    # the same report as "'K7PZ' is not a restore code. The host was left exactly as it is.", and a
    # window that had to tell them apart by capital letters would get one wrong.
    text = str(message).lower()
    return any(note.lower() in text for note in RESTORE_UNDONE_NOTES)




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


def make_sync_decision_cb(app, chain_name: str) -> Optional[Callable[[str], str]]:
    """The decision_cb a client sync is given when something on screen can answer it.

    The worker calls this from its own thread. The app it is built from puts the question on the
    GUI thread and parks this one until the answer comes back. An app that cannot ask - a stand-in
    in the test suite, a probe calling the worker directly - gets None, which the worker reads as
    "nobody is here to ask", and the chain deletes the way it always has.

    Anything that is not one of the three words this program names an answer with comes back as
    SYNC_DECISION_KEEP. A half-answer, a garbled one or an answer from a box that has been changed
    since this was written must not be read as permission to delete.
    """
    decide = getattr(app, 'ask_sync_decision', None)
    if not callable(decide):
        return None

    def _decide(question: str) -> str:
        answer = str(decide(f"Sync Chain '{chain_name}' - Delete Files?", question) or '')
        if answer in (SYNC_DECISION_DELETE, SYNC_DECISION_RESTORE):
            return answer
        return SYNC_DECISION_KEEP

    return _decide


def make_restore_code_cb(app, chain_name: str) -> Optional[Callable[[str], Optional[str]]]:
    """The restore_code_cb a client sync is given when something on screen can ask for the code.

    Built from the same app as the decision above, because it is the second half of the same
    question: the user pressed "Restore Host", and now somebody has to read four characters off the
    host's screen and type them in here. The callback is handed a description of the host it is
    waiting on and returns what was typed, or None for "nobody typed anything".
    """
    ask = getattr(app, 'ask_restore_code', None)
    if not callable(ask):
        return None

    def _ask(host_label: str) -> Optional[str]:
        return ask(f"Sync Chain '{chain_name}' - Restore Host", host_label)

    return _ask




class SyncClientWorker:
    """Executes client synchronization against a remote host."""

    @staticmethod
    def _rebuild_host(sock: socket.socket, chain_config: dict, dest_folder: Path, host_label: str,
                      status_cb: Optional[Callable[[str], None]] = None,
                      progress_cb: Optional[Callable[[int, int, str, int, int], None]] = None,
                      restore_code_cb: Optional[Callable[[str], Optional[str]]] = None
                      ) -> Tuple[bool, str, int]:
        """Rebuild the host's copy of this chain from this PC's copy, then go back to being a client.

        This is the answer a client gives when its host has stopped offering files this machine still
        holds: instead of agreeing to lose them, this machine offers them back. Every part of the
        ordinary client half is turned around for the length of one transfer - this end indexes its own
        folder, the host shortlists what it is missing, and the files travel the other way - and then
        this end goes back to being a client on its own. Nothing has to be undone to make that happen:
        a chain's role is a setting on this PC, and not something the exchange touches.

        No file is deleted on either machine anywhere in here. What the host will and will not accept,
        and what it writes when it accepts, is the host's rule (SyncHostServer._receive_restore); this
        half only reads from this folder and offers what it finds.

        Returns (ok, what to report, how many files were sent).
        """
        sync_code = str(chain_config.get('sync_code', ''))

        if status_cb:
            status_cb("Asking the host to open a restore...")
        send_json_msg(sock, {'cmd': 'RESTORE_REQUEST', 'sync_code': sync_code, 'client_ip': get_local_ip()})
        issued = recv_json_msg(sock, timeout=SYNC_SOCKET_TIMEOUT)
        if not issued or issued.get('status') != 'WAITING_FOR_CODE':
            reason = issued.get('reason') if issued else 'the host did not answer'
            return False, f"Restore Host refused by the host: {reason}. Nothing was deleted here.", 0

        # The host has put a code on its own screen by now, and this connection is waiting on somebody
        # reading it out and typing it in. That is the longest wait in this exchange, and the only thing
        # this socket can say while it waits is PING.
        if status_cb:
            status_cb("Waiting for the host's restore code...")
        keepalive = _HostKeepalive(sock)
        keepalive.start()
        try:
            typed = restore_code_cb(host_label) if restore_code_cb is not None else None
        finally:
            keepalive.stop()
        code = restore_code_shape(typed)
        if code is None:
            # Nobody typed anything, or what was typed is not four characters this code is made of. The
            # offer is closed from here so the host's screen stops showing a code nobody will use, and
            # the sync carries on as though Restore Host had never been offered.
            try:
                send_json_msg(sock, {'cmd': 'RESTORE_CANCEL', 'sync_code': sync_code})
            except Exception:
                pass
            if typed is None:
                return False, "Restore Host cancelled - the host was left exactly as it is.", 0
            return False, f"'{typed}' is not a restore code. The host was left exactly as it is.", 0

        send_json_msg(sock, {'cmd': 'RESTORE_CONFIRM', 'sync_code': sync_code, 'code': code})
        accepted = recv_json_msg(sock, timeout=SYNC_SOCKET_TIMEOUT)
        if not accepted or accepted.get('status') != 'CODE_ACCEPTED':
            reason = accepted.get('reason') if accepted else 'the host did not answer'
            return False, f"The host did not accept that code: {reason}. Nothing was deleted here.", 0

        # The slow part, done with nothing else running on this socket: the host is waiting to read the
        # index this is about to send, and it would read a PING as the mistake it is.
        if status_cb:
            status_cb("Listing this PC's copy for the host...")
        index = []
        for path in filter_audio_files(dest_folder):
            try:
                stat = path.stat()
                artist, title = read_metadata_tags(path)
                index.append({'name': path.name, 'size': stat.st_size, 'mtime': stat.st_mtime,
                              'sha256': compute_file_sha256(path), 'artist': artist, 'title': title})
            except Exception:
                continue
        send_json_msg(sock, {'cmd': 'PUSH_INDEX', 'sync_code': sync_code, 'files': index})

        shortlist = recv_json_msg(sock, timeout=SYNC_RESTORE_HANDSHAKE_TIMEOUT)
        if not shortlist or shortlist.get('status') != 'RESTORING':
            reason = shortlist.get('reason') if shortlist else 'the host did not answer'
            return False, f"The host would not take this PC's copy: {reason}. Nothing was deleted here.", 0

        needed = [str(name) for name in shortlist.get('files') or []]
        already_there = int(shortlist.get('already_there') or 0)
        by_name = {entry['name']: entry for entry in index}
        total = len(needed)
        sent = 0

        for idx, name in enumerate(needed, 1):
            target_path = dest_folder / name
            try:
                stat_now = target_path.stat()
            except Exception:
                # The host asked for a file this PC had a moment ago and no longer has - deleted here,
                # or the drive went away. It is skipped, and the host's own answer lists it as missing.
                if status_cb:
                    status_cb(f"Skipping {name} - it is no longer in this folder")
                continue
            entry = by_name.get(name)
            if entry is None or stat_now.st_size != entry['size']:
                # Changed since it was listed, so what the host is offered has to be what is here now
                # and not what was measured before the code was typed.
                entry = {'name': name, 'size': stat_now.st_size, 'mtime': stat_now.st_mtime,
                         'sha256': compute_file_sha256(target_path)}
            if status_cb:
                status_cb(f"Restoring [{idx}/{total}] onto the host: {name}")

            def _progress(bytes_done, bytes_total, _name=name, _idx=idx, _tot=total):
                if progress_cb:
                    progress_cb(bytes_done, bytes_total, _name, _idx, _tot)

            send_json_msg(sock, {'cmd': 'PUSH_FILE', 'filename': name, 'filesize': entry['size'],
                                 'sha256': entry['sha256'], 'mtime': entry['mtime']})
            go_ahead = recv_json_msg(sock, timeout=SYNC_RESTORE_HANDSHAKE_TIMEOUT)
            if not go_ahead or go_ahead.get('status') != 'RECEIVING':
                if status_cb:
                    status_cb(f"Host would not take {name}: "
                              f"{go_ahead.get('reason') if go_ahead else 'no answer from the host'}")
                continue
            stream_file_to_socket(sock, target_path, _progress)
            receipt = recv_json_msg(sock, timeout=SYNC_RESTORE_HANDSHAKE_TIMEOUT)
            if receipt and receipt.get('status') == 'OK':
                sent += 1
            elif status_cb:
                status_cb(f"Host would not take {name}: "
                          f"{receipt.get('reason') if receipt else 'no answer from the host'}")

        send_json_msg(sock, {'cmd': 'PUSH_DONE', 'sync_code': sync_code})
        done = recv_json_msg(sock, timeout=SYNC_RESTORE_HANDSHAKE_TIMEOUT)
        if not done or done.get('status') != 'SYNCED':
            return False, ("The host never confirmed the rebuild - the connection was lost part way. "
                           "Nothing was deleted here."), sent
        missing = done.get('missing') or []
        note = f"Host rebuilt from this PC: {sent} file(s) written to {host_label}, {already_there} already there"
        if missing:
            note += f", {len(missing)} the host asked for did not arrive"
        return True, note + ". Nothing was deleted here.", sent

    @staticmethod
    def sync_chain(chain_config: dict,
                   status_cb: Optional[Callable[[str], None]] = None,
                   progress_cb: Optional[Callable[[int, int, str, int, int], None]] = None,
                   confirm_cb: Optional[Callable[[str], bool]] = None,
                   decision_cb: Optional[Callable[[str], str]] = None,
                   restore_code_cb: Optional[Callable[[str], Optional[str]]] = None
                   ) -> Tuple[bool, str, int, int]:

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
            # removable-media sync (which pulls from here but writes to a drive) is handed neither the
            # decision callback nor a confirm_cb and so is never held up asking either.

            doomed = [name for name in local_files_map if name not in host_files_map] \
                if deletion_mode == 'mirror' else []
            limit = delete_confirm_limit(chain_config)

            if doomed:
                if limit == 0 or len(doomed) <= limit:
                    _remove_offered_no_more(doomed)
                elif decision_cb is not None:
                    if status_cb:
                        status_cb(f"Host no longer offers {len(doomed)} local track(s) - asking before deleting...")
                    # The host gives up on an idle connection after 30 seconds, so the connection is
                    # kept warm for as long as the question is being answered - and Restore Host makes
                    # that a good deal longer than it used to be, because the answer now involves
                    # somebody reading four characters off another machine's screen.
                    keepalive = _HostKeepalive(sock)
                    keepalive.start()
                    try:
                        decision = str(decision_cb(_deletion_question(dest_folder, doomed, limit))
                                       or SYNC_DECISION_KEEP)
                    finally:
                        keepalive.stop()
                    if decision == SYNC_DECISION_RESTORE and restore_code_cb is not None:
                        ok, note, sent = SyncClientWorker._rebuild_host(
                            sock, chain_config, dest_folder, f"{host_ip}:{host_port}", status_cb,
                            progress_cb, restore_code_cb)
                        # The swap is an answer to the question, and the one answer that changes what
                        # the rest of this sync does. Nothing is deleted here, and nothing is pulled
                        # from a host that has just been rebuilt out of this folder: the two ends match
                        # by construction, and a download pass over them would be a pass over files
                        # that are already the same.
                        return ok, note, sent, 0
                    elif decision == SYNC_DECISION_RESTORE:
                        # The box this app builds has a Restore Host button but the worker was given
                        # nothing to ask the host's code with. An answer that cannot be carried out
                        # leaves the files where they are, which is what every other unfinished answer
                        # in here already does.
                        unconfirmed = len(doomed)
                        if status_cb:
                            status_cb(f"Restore Host not carried out - no way to ask the host for its code; "
                                      f"{unconfirmed} track(s) left where they are")
                    elif decision == SYNC_DECISION_DELETE:
                        _remove_offered_no_more(doomed)
                    else:
                        unconfirmed = len(doomed)
                        if status_cb:
                            status_cb(f"Deletions not confirmed - {unconfirmed} track(s) left where they are")
                elif confirm_cb is not None:
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
                else:
                    # Nobody is here to ask. This is the call shape every earlier build of this program
                    # used, and the one the USB half still calls: no decision callback, no confirm
                    # callback, and a chain that deletes the way it always has. A sync that cannot put a
                    # question on screen must not quietly turn into a sync that deletes nothing.
                    _remove_offered_no_more(doomed)


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

    def __init__(self, chain_config: dict,
                 decision_cb: Optional[Callable[[str], str]] = None,
                 restore_code_cb: Optional[Callable[[str], Optional[str]]] = None):
        super().__init__()
        self.chain_config = chain_config
        # Left None by anything that cannot put a question on screen; the worker then proceeds
        # exactly as it did before this existed. The second one is only reached if the first one is
        # answered with Restore Host.
        self.decision_cb = decision_cb
        self.restore_code_cb = restore_code_cb

    def run(self):
        def _status(txt):
            self.status_signal.emit(txt)

        def _progress(done, total, filename, idx, total_items):
            self.progress_signal.emit(done, total, filename, idx, total_items)

        ok, msg, transferred, deleted = SyncClientWorker.sync_chain(
            self.chain_config,
            status_cb=_status,
            progress_cb=_progress,
            decision_cb=self.decision_cb,
            restore_code_cb=self.restore_code_cb
        )
        self.finished_signal.emit(ok, msg, transferred, deleted)

