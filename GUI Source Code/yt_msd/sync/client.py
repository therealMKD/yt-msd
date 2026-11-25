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
from yt_msd.sync.config import chain_can_push, delete_confirm_limit
from yt_msd.sync.discovery import discover_host_on_lan
from yt_msd.sync.lan import (SYNC_CONFIRM_PING_INTERVAL, SYNC_RESTORE_HANDSHAKE_TIMEOUT,
                             SYNC_SOCKET_TIMEOUT, get_local_ip, restore_code_shape)
from yt_msd.sync.tags import parse_sync_timestamp

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


# The wording a finished client sync carries when it sent its own new files up to its host instead of
# letting the next sync take them out of this folder. Named here for the same reason as the two above:
# the windows that report a finished chain are not the ones that ran it, and a chain that added files to
# another machine has to be told apart from one that pulled files off it - the first wrote somewhere
# else, and only the second has anything here to count as updated.
PUSHED_NOTE = "Pushed to host"


def files_were_pushed(message) -> bool:
    """Whether a finished client sync is reporting files this PC sent up to its host."""
    return PUSHED_NOTE in str(message)


# The answer to a push that found nothing to push: every file in this folder was already on the host,
# or the chain has never finished a sync and so has no moment to measure "new" against. Reported as this
# rather than as a successful sync of nothing, because the button that asked has to be able to say why
# it did nothing.
NOTHING_TO_PUSH_NOTE = "Nothing newer than the last sync to push"


def nothing_to_push(message) -> bool:
    """Whether a push attempt is reporting that it found nothing it was allowed to offer."""
    return NOTHING_TO_PUSH_NOTE in str(message)


# The three sentences every failed push ends with, on both halves of the exchange. Named for the same
# reason as the two restore ones above: a chain whose push was refused, cancelled or mistyped reached its
# host and wrote nothing, and calling that a host that is offline is a lie about the machine it is
# sitting next to.
PUSH_UNDONE_NOTES = ("Nothing was pushed.", "Nothing was written to the host.", "Nothing here was deleted.")


def push_was_left_undone(message) -> bool:
    """Whether a failed client sync is reporting a push that did not take place."""
    text = str(message).lower()
    return any(note.lower() in text for note in PUSH_UNDONE_NOTES)


def last_sync_moment(chain_config: dict) -> Optional[float]:
    """The moment this chain last finished a sync, in the seconds a file's own date is measured in.

    A chain's `last_synced` is written as epoch seconds by every sync that finishes, but the card that
    shows it has long accepted a date string too, and the TAG.yaml the removable-media half of this
    program writes has one; both are read through `parse_sync_timestamp()` so that whatever is compared
    against a file's date is always the same kind of number. A chain that has never synced has no
    moment, and returns None rather than 0 - which matters, because 0 is older than every file there is,
    and "newer than the last sync" is a question a chain that has never synced has not yet been asked.
    """
    raw = chain_config.get('last_synced')
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw > 0 else None
    parsed = parse_sync_timestamp(raw)
    return parsed if parsed is not None and parsed > 0 else None


def files_since_last_sync(chain_config: dict, local_files_map: dict) -> List[str]:
    """Which of the files in this folder arrived after this chain last finished a sync.

    This is the test that tells the two ways a file can be here and not on the host apart. Either the
    host stopped offering a file both machines used to have - which is the situation Restore Host exists
    for - or this machine made it since the last sync, which is the situation a push exists for. Dates
    decide it: a file that has been here longer than this chain has been syncing is one the host let go,
    and one made since is one the host has never seen.

    A chain that has never synced gets nothing back, deliberately. Its whole folder is newer than a
    moment that does not exist, and offering a library of three hundred tracks up to a host on its first
    sync is the opposite of what this is for.
    """
    since = last_sync_moment(chain_config)
    if since is None:
        return []
    found = []
    for name, path in local_files_map.items():
        try:
            stamp = path.stat().st_mtime
        except Exception:
            # A file that was in the listing a moment ago and cannot be dated now is a file that is
            # going away, and it is not something to offer to anybody else.
            continue
        if stamp > since:
            found.append(name)
    return sorted(found)





def _push_question(dest_folder: Path, names: List[str]) -> str:
    """The text a Mirror chain shows before offering its own new files to its host."""
    shown = names[:8]
    listing = "\n".join(f"    {name}" for name in shown)
    hidden = len(names) - len(shown)
    if hidden > 0:
        listing += f"\n    ... and {hidden} more"
    return (
        f"{len(names)} file(s) in this folder are newer than this chain's last sync, and the host does "
        f"not have them:\n"
        f"    {dest_folder}\n\n"
        f"{listing}\n\n"
        f"Push {len(names)} file(s) to the host?\n\n"
        "If you don't, this sync deletes them from this folder to match the host - a Mirror chain keeps "
        "only what its host offers. The host decides how many of these it takes, and whatever it does "
        "not take is still deleted here. A push can only add files to a host: nothing the host already "
        "has is changed or removed by it."
    )


def make_push_confirm_cb(app, chain_name: str) -> Optional[Callable[[str], bool]]:
    """The push_confirm_cb a client sync is given when something on screen can ask it.

    Built from the same app as the delete question above and parked on the same arrangement, because it
    is asked in the same place: mid-sync, with the host's connection open and this worker parked until
    somebody answers. The question is whether to offer this folder's own new files to the host before
    the deletion pass takes them out of it, and it is only ever asked of a Mirror chain - an Additive
    chain keeps its files whatever its host does, so it has nothing it would lose and no reason to be
    interrupted.

    Anything that is not a clear yes comes back as no. A window nobody read and a window somebody closed
    without pressing anything both mean "do not write into another machine's folder", which is the answer
    this program gives to every question it cannot hear.
    """
    ask = getattr(app, 'ask_push_confirm', None)
    if not callable(ask):
        return None

    def _confirm(question: str) -> bool:
        return bool(ask(f"Sync Chain '{chain_name}' - Push Files To Host?", question))

    return _confirm


def make_push_code_cb(app, chain_name: str) -> Optional[Callable[[str], Optional[str]]]:
    """The push_code_cb a client push is given when something on screen can ask for the code.

    The second half of the same answer as above, and the same four characters a Restore Host uses: the
    host shows them on its own screen, and the only way they reach this machine is somebody reading them
    out. A client its host has given permanent leave to push never reaches here - there is no code for it
    to type - so this callback is only used by the pushes that need one.
    """
    ask = getattr(app, 'ask_push_code', None)
    if not callable(ask):
        return None

    def _ask(host_label: str) -> Optional[str]:
        return ask(f"Sync Chain '{chain_name}' - Push To Host", host_label)

    return _ask


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
    def _push_to_host(sock: socket.socket, chain_config: dict, dest_folder: Path,
                      names: List[str], host_label: str,
                      status_cb: Optional[Callable[[str], None]] = None,
                      progress_cb: Optional[Callable[[int, int, str, int, int], None]] = None,
                      push_code_cb: Optional[Callable[[str], Optional[str]]] = None
                      ) -> Tuple[bool, str, int, int]:
        """Offer this PC's own new files to the host, and let the host decide what to keep.

        The mirror image of the rebuild above, and deliberately narrower. A rebuild is this PC offering
        its whole folder to a host that has lost its copy; a push is this PC offering the handful of
        files it has made since the two machines last spoke, and the host answers that offer with a list
        of what it will actually take - names it does not already have, up to the number its own card
        allows - before a single byte moves. Whatever is not on that list never leaves this folder, and
        nothing on the host is changed, replaced or removed by any of it: the host's rule for what it
        accepts is `SyncHostServer._push_shortlist` and `_receive_push`, and this half only reads from
        here.

        Returns (ok, what to report, how many were written, how many the host refused).
        """
        sync_code = str(chain_config.get('sync_code', ''))

        if status_cb:
            status_cb(f"Asking the host to take {len(names)} new file(s)...")
        send_json_msg(sock, {'cmd': 'PUSH_REQUEST', 'sync_code': sync_code,
                             'client_ip': get_local_ip(), 'count': len(names)})
        answer = recv_json_msg(sock, timeout=SYNC_SOCKET_TIMEOUT)
        if not answer:
            return False, "The host did not answer the push request. Nothing was pushed.", 0, 0

        status = answer.get('status')
        needs_code = status == 'WAITING_FOR_PUSH_CODE'
        if not needs_code and status != 'PUSH_ALLOWED':
            reason = answer.get('reason') or 'the host did not answer'
            return False, f"Push refused by the host: {reason}. Nothing was pushed.", 0, 0

        if needs_code:
            # The host has put a code on its own screen by now, and this connection is waiting on
            # somebody reading it out and typing it in - the longest wait in this exchange, and the only
            # thing this socket can say while it waits is PING.
            if status_cb:
                status_cb("Waiting for the host's push code...")
            keepalive = _HostKeepalive(sock)
            keepalive.start()
            try:
                typed = push_code_cb(host_label) if push_code_cb is not None else None
            finally:
                keepalive.stop()
            code = restore_code_shape(typed)
            if code is None:
                # Nobody typed anything, or what was typed is not four characters a code like this is
                # made of. The offer is closed from here so the host's screen stops showing a code
                # nobody will use, and nothing on either machine has changed.
                try:
                    send_json_msg(sock, {'cmd': 'PUSH_CANCEL', 'sync_code': sync_code})
                except Exception:
                    pass
                if typed is None:
                    return False, "Push cancelled - nothing was written to the host.", 0, 0
                return False, f"'{typed}' is not a push code. Nothing was written to the host.", 0, 0
            send_json_msg(sock, {'cmd': 'PUSH_START', 'sync_code': sync_code, 'code': code})
        else:
            # This PC's address has already been given leave to push, so there is no code to read off
            # anybody's screen and no window to wait on.
            if status_cb:
                status_cb("This host has given this PC leave to push - no code needed.")
            send_json_msg(sock, {'cmd': 'PUSH_START', 'sync_code': sync_code})

        accepted = recv_json_msg(sock, timeout=SYNC_SOCKET_TIMEOUT)
        if not accepted or accepted.get('status') != 'PUSH_ACCEPTED':
            reason = accepted.get('reason') if accepted else 'the host did not answer'
            return False, f"The host did not accept this push: {reason}. Nothing was pushed.", 0, 0

        # The slow part, done with nothing else running on this socket: the host is waiting to read this
        # list, and it would read a PING as the mistake it is. Only the files this push is about are
        # measured - a client measuring its whole library when it was asked about four files is a client
        # doing work nobody asked it for.
        if status_cb:
            status_cb("Measuring the new files for the host...")
        index: List[dict] = []
        for name in names:
            target_path = dest_folder / name
            try:
                stat = target_path.stat()
                index.append({'name': name, 'size': stat.st_size, 'mtime': stat.st_mtime,
                              'sha256': compute_file_sha256(target_path)})
            except Exception:
                continue
        if not index:
            return False, f"{NOTHING_TO_PUSH_NOTE} - they are no longer in this folder.", 0, 0

        send_json_msg(sock, {'cmd': 'PUSH_INDEX', 'sync_code': sync_code, 'files': index})
        shortlist = recv_json_msg(sock, timeout=SYNC_RESTORE_HANDSHAKE_TIMEOUT)
        if not shortlist or shortlist.get('status') != 'PUSHING':
            reason = shortlist.get('reason') if shortlist else 'the host did not answer'
            return False, f"The host would not take this PC's files: {reason}. Nothing was pushed.", 0, 0

        wanted = [str(name) for name in shortlist.get('files') or []]
        refused = int(shortlist.get('refused') or 0)
        already_there = int(shortlist.get('already_there') or 0)
        by_name = {entry['name']: entry for entry in index}
        total = len(wanted)
        sent = 0

        for idx, name in enumerate(wanted, 1):
            target_path = dest_folder / name
            try:
                stat_now = target_path.stat()
            except Exception:
                # The host agreed to take a file this PC had a moment ago and no longer has - deleted
                # here, or the drive went away. It is skipped, and the host's own answer lists it as one
                # that never arrived.
                if status_cb:
                    status_cb(f"Skipping {name} - it is no longer in this folder")
                continue
            entry = by_name.get(name)
            if entry is None or stat_now.st_size != entry['size']:
                # Changed since it was measured, so what the host is given has to be what is here now
                # and not what was measured before its code was typed.
                entry = {'name': name, 'size': stat_now.st_size, 'mtime': stat_now.st_mtime,
                         'sha256': compute_file_sha256(target_path)}
            if status_cb:
                status_cb(f"Pushing [{idx}/{total}] onto the host: {name}")

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
            return False, ("The host never confirmed the push - the connection was lost part way. "
                           "Nothing here was deleted."), sent, refused

        missing = done.get('missing') or []
        note = (f"{PUSHED_NOTE}: {sent} file(s) added to {host_label}, {already_there} already there, "
                f"{refused} refused")
        if missing:
            note += f", {len(missing)} the host agreed to take never arrived"
        return True, note + ". Nothing was deleted here.", sent, refused

    @staticmethod
    def _open_host(chain_config: dict,
                   status_cb: Optional[Callable[[str], None]] = None
                   ) -> Tuple[Optional[socket.socket], str, int, str]:
        """Reach the host this chain follows - the address it was last seen at, or a search for it.

        The door every client half of this program walks through, named once so that a sync and a push
        cannot end up knocking on two different doors. What it learns is written back onto the chain -
        the address, the port, and the name the host answered with - because a chain that found its host
        on a new address should not have to find it again next time.

        Returns (the socket, the host's address, the host's port, what to report when there is no
        socket). The last is empty whenever there is a socket, and is the whole report when there is
        not.
        """
        sync_code = str(chain_config.get('sync_code', ''))
        host_ip = str(chain_config.get('last_known_host_ip', '') or '')
        try:
            host_port = int(chain_config.get('host_port', 63350))
        except (TypeError, ValueError):
            host_port = 63350

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
                return None, host_ip, host_port, (f"Could not find active host for Sync Code {sync_code} "
                                                  "on local network.")
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
                return None, host_ip, host_port, f"Failed to connect to host at {host_ip}:{host_port}: {e}"

        return sock, host_ip, host_port, ''

    @staticmethod
    def _authenticate(sock: socket.socket, chain_config: dict, sync_code: str) -> Tuple[bool, str]:
        """Say which chain this client belongs to, and learn what the host calls it.

        Returns (ok, what to report if the host said no). The name the host answers with is written onto
        the chain, because the host names its own chain in the answer to an AUTH, and that name is the
        one its card shows and its folder carries. A chain joined by an address and a code typed in by
        hand has no way of ever learning it except from the host itself.
        """
        send_json_msg(sock, {'cmd': 'AUTH', 'sync_code': sync_code, 'client_ip': get_local_ip()})
        auth_resp = recv_json_msg(sock)
        if not auth_resp or auth_resp.get('status') != 'OK':
            err = auth_resp.get('reason', 'Authentication rejected by host') if auth_resp else 'No auth response'
            return False, err
        host_chain_name = str(auth_resp.get('chain_name') or '').strip()
        if host_chain_name:
            chain_config['host_chain_name'] = host_chain_name
        return True, ''

    @staticmethod
    def _host_index(sock: socket.socket, timeout: float = 25.0) -> Tuple[Optional[List[dict]], str]:
        """Ask this host for its file list, and say what went wrong if it did not give one.

        Returns (the list, what to report if there is no list). The timeout is longer than an ordinary
        socket read because answering this means hashing the whole hosted folder, which is a slow drive
        doing a lot of work rather than a dead connection.
        """
        send_json_msg(sock, {'cmd': 'GET_INDEX'})
        index_resp = recv_json_msg(sock, timeout=timeout)
        if not index_resp or index_resp.get('status') != 'OK':
            return None, "Failed to retrieve file index from host."
        return index_resp.get('files', []), ''

    @staticmethod
    def fetch_config(chain_config: dict,
                     status_cb: Optional[Callable[[str], None]] = None
                     ) -> Tuple[bool, str, Optional[dict]]:
        """Ask the host this chain follows for its settings, and bring them back.

        The shortest exchange a chain has. It walks through the same door as a sync (_open_host, which
        is also the half that relearns the host's address when it has moved) and says the same name
        (_authenticate, which is the half that learns what the host calls this chain), and then asks one
        question. Nothing in here reads or writes a single track, and nothing in here touches this
        machine's own settings: what arrives is handed back to the window that asked, which is the only
        place that can tell which of another machine's settings belong on this one.

        Returns (ok, what to report, what arrived).
        """
        sync_code = str(chain_config.get('sync_code', ''))
        sock, host_ip, host_port, connect_error = SyncClientWorker._open_host(chain_config, status_cb)
        if sock is None:
            return False, connect_error, None
        try:
            sock.settimeout(SYNC_SOCKET_TIMEOUT)
            auth_ok, auth_error = SyncClientWorker._authenticate(sock, chain_config, sync_code)
            if not auth_ok:
                return False, auth_error, None

            if status_cb:
                status_cb("Asking the host for its settings...")
            send_json_msg(sock, {'cmd': 'GET_CONFIG', 'sync_code': sync_code, 'client_ip': get_local_ip()})
            answer = recv_json_msg(sock, timeout=SYNC_SOCKET_TIMEOUT)
            if not answer:
                return False, "The host did not answer the settings request.", None
            if answer.get('status') != 'CONFIG':
                reason = answer.get('reason') or 'the host refused without a reason'
                return False, f"Settings refused by the host: {reason}. Nothing here was changed.", None
            payload = answer.get('config')
            if not isinstance(payload, dict) or not payload:
                return False, "The host answered with no settings. Nothing here was changed.", None
            return True, f"Settings received from {host_ip}:{host_port}.", payload
        except Exception as exc:
            return False, f"Settings import error: {exc}", None
        finally:
            try:
                sock.close()
            except Exception:
                pass

    @staticmethod
    def sync_chain(chain_config: dict,
                   status_cb: Optional[Callable[[str], None]] = None,
                   progress_cb: Optional[Callable[[int, int, str, int, int], None]] = None,
                   confirm_cb: Optional[Callable[[str], bool]] = None,
                   decision_cb: Optional[Callable[[str], str]] = None,
                   restore_code_cb: Optional[Callable[[str], Optional[str]]] = None,
                   push_confirm_cb: Optional[Callable[[str], bool]] = None,
                   push_code_cb: Optional[Callable[[str], Optional[str]]] = None
                   ) -> Tuple[bool, str, int, int]:

        sync_code = str(chain_config.get('sync_code', ''))
        folder_str = chain_config.get('folder_path', '')
        dest_folder = Path(folder_str)
        dest_folder.mkdir(parents=True, exist_ok=True)

        deletion_mode = chain_config.get('deletion_mode', 'mirror')

        # Progress is reported at a bounded rate no matter how fast the device
        # is, so a sync can never starve the UI event loop.
        progress_cb = make_throttled_progress_cb(progress_cb)

        sock, host_ip, host_port, connect_error = SyncClientWorker._open_host(chain_config, status_cb)
        if sock is None:
            return False, connect_error, 0, 0

        transferred = 0
        deleted = 0
        # Tracks a Mirror sync was asked to delete and the user said no to. They stay on disk, and
        # the count is what the status line and the returned message report them with.
        unconfirmed = 0
        # How many files this sync wrote into its host's folder, and how many the host refused. Only a
        # Mirror chain ever fills these in, and only when something on this machine can ask the
        # question they came from - a sync with no window to ask through pushes nothing.
        pushed = 0
        push_refused = 0
        # Everything below reads and writes dest_folder, which may be a slow
        # device: hold the per-drive lock so only one sync works it over.
        drive_lock = get_drive_io_lock(dest_folder)
        drive_lock.acquire()
        try:
            sock.settimeout(SYNC_SOCKET_TIMEOUT)
            auth_ok, auth_error = SyncClientWorker._authenticate(sock, chain_config, sync_code)
            if not auth_ok:
                return False, auth_error, 0, 0

            if status_cb:
                status_cb("Fetching file index from host...")
            host_files_list, index_error = SyncClientWorker._host_index(sock)
            if host_files_list is None:
                return False, index_error, 0, 0

            host_files: List[dict] = host_files_list
            host_files_map = {f['name']: f for f in host_files}

            local_files = filter_audio_files(dest_folder)
            local_files_map = {f.name: f for f in local_files}

            # The files this machine made since its last sync that its host has never seen. Only a
            # Mirror chain has a use for them: they are exactly the files this sync is about to delete
            # out of this folder to match the host, and asking about them here - before the deletion
            # pass, and not after it - is the difference between "you made four tracks and they are
            # gone" and "you made four tracks; your host has them now". An Additive chain keeps them
            # whatever happens, so it is never interrupted with this at all.
            if deletion_mode == 'mirror' and push_confirm_cb is not None:
                new_here = [name for name in files_since_last_sync(chain_config, local_files_map)
                            if name not in host_files_map]
                if new_here:
                    if status_cb:
                        status_cb(f"{len(new_here)} local track(s) are newer than the last sync and the "
                                  "host does not have them - asking whether to push them...")
                    # The host gives up on an idle connection after 30 seconds, and the answer to this
                    # one can involve somebody walking to another machine.
                    keepalive = _HostKeepalive(sock)
                    keepalive.start()
                    try:
                        wants_push = bool(push_confirm_cb(_push_question(dest_folder, new_here)))
                    finally:
                        keepalive.stop()
                    if wants_push:
                        pushed_ok, push_note, pushed, push_refused = SyncClientWorker._push_to_host(
                            sock, chain_config, dest_folder, new_here, f"{host_ip}:{host_port}",
                            status_cb, progress_cb, push_code_cb)
                        if not pushed_ok:
                            # A push that did not happen is reported the way a restore that did not
                            # happen is: this machine reached its host, asked, and nothing was written.
                            # What the sync does next - the deletions the user was offered a moment ago
                            # - is decided by the answer to that question rather than by this one.
                            return False, push_note, pushed, 0
                        # The host has just taken some of these files, so the index this sync is holding
                        # is out of date in the one way that costs files: the tracks that landed a moment
                        # ago are still listed as things the host does not offer, and the deletion pass
                        # below would delete them from here for no reason at all. Both sides are read
                        # again before anything is removed.
                        if status_cb:
                            status_cb("Re-reading the host's index after the push...")
                        refreshed, refresh_error = SyncClientWorker._host_index(sock)
                        if refreshed is None:
                            return False, (f"{push_note} The host's file list could not be read again "
                                           "after the push."), pushed, push_refused
                        host_files = refreshed
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
            if pushed:
                # Said in the message as well as on the card: this sync wrote into another machine, and
                # a line that only counts what arrived here does not say that.
                refused_note = f", {push_refused} refused" if push_refused else ""
                note += f" {PUSHED_NOTE}: {pushed} file(s) added{refused_note}."
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



    @staticmethod
    def push_chain(chain_config: dict,
                   status_cb: Optional[Callable[[str], None]] = None,
                   progress_cb: Optional[Callable[[int, int, str, int, int], None]] = None,
                   push_code_cb: Optional[Callable[[str], Optional[str]]] = None
                   ) -> Tuple[bool, str, int, int]:
        """Push this chain's own new files up to its host, because somebody asked for that.

        The button on a Mirror chain's card runs this. It is the same door an ordinary sync walks
        through - reach the host, name this chain, read the host's index - followed by the same test the
        middle of a sync runs: which files are here, are newer than the last sync, and not on the host.
        The only difference is that the question a sync asks in passing is not asked here, because
        pressing the button is the answer.

        Nothing is pulled, nothing is deleted, and nothing the host already holds is replaced. A chain
        that is not a Mirror chain is turned away at the door: an Additive chain is never going to lose
        these files, so it has no reason to send them anywhere.

        Returns (ok, what to report, how many were written, how many the host refused).
        """
        sync_code = str(chain_config.get('sync_code', ''))
        dest_folder = Path(chain_config.get('folder_path', ''))
        dest_folder.mkdir(parents=True, exist_ok=True)
        progress_cb = make_throttled_progress_cb(progress_cb)

        if not chain_can_push(chain_config):
            return False, ("Only a Mirror chain can push files to its host - an Additive chain keeps "
                           "what it holds, so it has nothing it would lose."), 0, 0

        sock, host_ip, host_port, connect_error = SyncClientWorker._open_host(chain_config, status_cb)
        if sock is None:
            return False, connect_error, 0, 0

        # Everything in here reads this folder, which may be a slow device: the same per-drive lock an
        # ordinary sync takes, so a push and a sync of the same folder never work it over at once.
        drive_lock = get_drive_io_lock(dest_folder)
        drive_lock.acquire()
        try:
            sock.settimeout(SYNC_SOCKET_TIMEOUT)
            auth_ok, auth_error = SyncClientWorker._authenticate(sock, chain_config, sync_code)
            if not auth_ok:
                return False, auth_error, 0, 0

            if status_cb:
                status_cb("Fetching file index from host...")
            host_files_list, index_error = SyncClientWorker._host_index(sock)
            if host_files_list is None:
                return False, index_error, 0, 0
            host_files_map = {f['name']: f for f in host_files_list}

            local_files_map = {f.name: f for f in filter_audio_files(dest_folder)}
            new_here = [name for name in files_since_last_sync(chain_config, local_files_map)
                        if name not in host_files_map]
            if not new_here:
                # Either nothing here is newer than the last sync, or this chain has never finished one
                # and so has no moment to measure "new" against. Both are the same report, and both say
                # why the button did nothing instead of calling a push of nothing a success.
                return True, NOTHING_TO_PUSH_NOTE, 0, 0

            return SyncClientWorker._push_to_host(sock, chain_config, dest_folder, new_here,
                                                  f"{host_ip}:{host_port}", status_cb, progress_cb,
                                                  push_code_cb)
        except Exception as e:
            return False, f"Push error: {e}", 0, 0
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
                 restore_code_cb: Optional[Callable[[str], Optional[str]]] = None,
                 push_confirm_cb: Optional[Callable[[str], bool]] = None,
                 push_code_cb: Optional[Callable[[str], Optional[str]]] = None,
                 mode: str = 'sync'):
        super().__init__()
        self.chain_config = chain_config
        # Left None by anything that cannot put a question on screen; the worker then proceeds exactly
        # as it did before this existed. The second is only reached if the first is answered with
        # Restore Host, and the third and fourth only by a Mirror chain holding files its host has never
        # seen.
        self.decision_cb = decision_cb
        self.restore_code_cb = restore_code_cb
        self.push_confirm_cb = push_confirm_cb
        self.push_code_cb = push_code_cb
        # 'sync' runs the ordinary sync, which offers a push when it finds something worth pushing.
        # 'push' runs a push on its own, which is what the button on a chain's card asks for.
        self.mode = mode

    def run(self):
        def _status(txt):
            self.status_signal.emit(txt)

        def _progress(done, total, filename, idx, total_items):
            self.progress_signal.emit(done, total, filename, idx, total_items)

        if self.mode == 'push':
            ok, msg, transferred, deleted = SyncClientWorker.push_chain(
                self.chain_config,
                status_cb=_status,
                progress_cb=_progress,
                push_code_cb=self.push_code_cb
            )
        else:
            ok, msg, transferred, deleted = SyncClientWorker.sync_chain(
                self.chain_config,
                status_cb=_status,
                progress_cb=_progress,
                decision_cb=self.decision_cb,
                restore_code_cb=self.restore_code_cb,
                push_confirm_cb=self.push_confirm_cb,
                push_code_cb=self.push_code_cb
            )
        self.finished_signal.emit(ok, msg, transferred, deleted)


class HostConfigFetchThread(QThread):
    """One chain's host, asked for its settings, on a thread of its own.

    Deliberately not a mode of ClientSyncThread. A sync moves tracks, reports counts of what it moved
    and deletes, and finishes the chain's own record; this moves no files, writes nothing to this
    machine, and hands back one machine's settings for a window to decide about. Keeping them apart is
    also what keeps a settings import out of the bookkeeping a running sync needs - a card showing
    "[12/40] (30%)" is a card about files, and nothing here moves one.
    """
    status_signal = Signal(str)
    # (ok, what to report, the settings that arrived). The third is None whenever the first is False.
    finished_signal = Signal(bool, str, object)

    def __init__(self, chain_config: dict):
        super().__init__()
        self.chain_config = chain_config

    def run(self):
        ok, message, payload = SyncClientWorker.fetch_config(
            self.chain_config, status_cb=lambda txt: self.status_signal.emit(txt))
        self.finished_signal.emit(ok, message, payload)

