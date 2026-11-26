# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.sync.wire).
"""A sync-chain client that needs nothing but the standard library.

`docs/sync-protocol.md` is what a new endpoint has to speak; `yt_msd.sync.host` is what answers it today;
this module is what a client looks like when it is written from the document instead of from the GUI - no
PySide6, no Qt, no window, no signals, nothing that needs a desktop. It exists for two reasons.

  - It is the reference a phone is written against. Kotlin reading a Python module is easier than Kotlin
    reading prose, and a phone's every move is here in the order it is allowed to be made: find a host,
    say which chain, ask for its list, take a file, ask for its settings, keep a connection warm while a
    person reads a code off a screen, rebuild a host, push a handful of new files.
  - It is testable today. `GUI Test Suite/probe_phone_wire.py` drives this module against a real
    `SyncHostServer` over loopback and records every frame both ends exchange, so the exchange a phone
    will have is fixed by checks before a phone exists. When the app is written, the frames it sends are
    compared with the recorded ones - the same frames, byte for byte, are the contract.

It is not what the desktop app runs. The app's client half is `yt_msd.sync.client`, which owns the
decisions this module leaves to whoever calls it: what to download, what to delete, which question to ask
a person and what to do with the answer. A phone makes those decisions in its own windows, so this module
moves files and asks questions and answers with what the host said, and nothing else.
"""
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from yt_msd.audio.tags import read_metadata_tags
from yt_msd.sync import protocol
from yt_msd.sync.lan import (SCAN_CONNECT_TIMEOUT, SCAN_MAX_CONCURRENCY, SCAN_MAX_TARGETS,
                             SYNC_CONFIRM_PING_INTERVAL, SYNC_RESTORE_HANDSHAKE_TIMEOUT,
                             SYNC_SOCKET_TIMEOUT, get_local_ip)
from yt_msd.sync.transfer import (compute_file_sha256, filter_audio_files, recv_file_from_socket,
                                  recv_json_msg, send_json_msg, stream_file_to_socket)


def probe_host(host_ip: str, port: int, sync_code: str = "",
               timeout: float = SCAN_CONNECT_TIMEOUT + 0.5,
               protocol_version: Optional[int] = None) -> Optional[dict]:
    """Ask one address on one port "are you a yt-msd, and what do you host there?".

    A `HELLO` names no chain and asks for nothing, and a host answers it and lets the connection go: it is
    the only thing the program says about a chain to a machine it has not authenticated. Ask it with a sync
    code and a private chain answers too, because a machine holding the code is a machine that can sync it
    anyway.

    Returns the host's own answer, or nothing at all when there is no yt-msd on that address - a closed
    port, a port that answers with something that is not JSON, and a port that says nothing are the same
    answer as far as a search is concerned, and are the common case on a network of any size.
    """
    frame: Dict[str, Any] = {"cmd": protocol.CMD_HELLO}
    if sync_code:
        frame["sync_code"] = str(sync_code)
    if protocol_version is not None:
        frame[protocol.PROTOCOL_VERSION_KEY] = int(protocol_version)
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host_ip, int(port)))
        send_json_msg(sock, frame)
        return recv_json_msg(sock, timeout=timeout)
    except Exception:
        return None
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


def scan_for_hosts(targets: List[str], ports: List[int], sync_code: str = "",
                   max_workers: int = SCAN_MAX_CONCURRENCY, budget: float = 14.0,
                   on_reply: Optional[Callable[[str, int, dict], None]] = None) -> List[dict]:
    """Ask a list of addresses on a list of ports for their `HELLO` answers, in port order.

    Port order is not a detail and this keeps the rule the desktop search keeps: the host server takes the
    first free port upward from `SYNC_PORT_START`, so almost every host answers on 63350, and asking that
    one port across the whole network first is what puts an answer on a screen in the first second rather
    than the last.

    Returns one record per answer - the address, the port and what the host said - and hands each one to
    `on_reply` as it arrives, which is what lets a phone put a host on its list while the rest of the
    network is still being asked. `SCAN_MAX_TARGETS` is the same budget the desktop search spends, and it
    is what stops a phone with a wide idea of its subnet from spending the afternoon on it.
    """
    targets = [str(target) for target in targets][:SCAN_MAX_TARGETS]
    ordered_ports = sorted(int(port) for port in ports)
    pairs = [(target, port) for port in ordered_ports for target in targets]
    found: List[dict] = []
    if not pairs:
        return found
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(1, min(int(max_workers), len(pairs)))) as pool:
        futures = {pool.submit(probe_host, target, port, sync_code): (target, port)
                   for target, port in pairs}
        for future, (target, port) in futures.items():
            remaining = budget - (time.monotonic() - started)
            if remaining <= 0:
                break
            try:
                answer = future.result(timeout=remaining)
            except Exception:
                continue
            if not answer:
                continue
            found.append({"host_ip": target, "port": int(port), "reply": answer})
            if on_reply is not None:
                on_reply(target, int(port), answer)
        for future in futures:
            future.cancel()
    return found


def library_index(folder) -> List[dict]:
    """The index a client sends when it is asked what its own folder holds.

    The same six facts a host sends about its own folder, measured the same way: name, size, mtime, sha256,
    and the artist and title the file carries inside it. A file that cannot be measured is left out rather
    than listed with a guess in it, because a listing is what the other end of a chain decides from, and a
    row of a listing that is wrong is a row that gets downloaded, deleted or rebuilt.
    """
    folder = Path(folder)
    rows: List[dict] = []
    for path in filter_audio_files(folder):
        try:
            stat = path.stat()
            artist, title = read_metadata_tags(path)
            rows.append({"name": path.name, "size": stat.st_size, "mtime": stat.st_mtime,
                         "sha256": compute_file_sha256(path), "artist": artist, "title": title})
        except Exception:
            continue
    return rows


class Keepalive:
    """Pings a host while the machine on the other end of this socket has stopped to ask a question.

    A host reads the next command with a 30-second timeout, so a client that parks to show a box - a phone
    waiting for somebody to read a four-character code off another screen - would find its connection
    closed and its exchange reported as a failure before anybody had answered. This sends `PING` often
    enough that the host's read never times out, and throws the answer away.

    It is the same trick `yt_msd.sync.client._HostKeepalive` runs on a desktop, written without Qt. It runs
    for the length of one question and nothing else, and nothing else may touch the socket while it runs: a
    `PING` sent in the middle of a file transfer is bytes the host reads as its next frame.

    `sent` counts the pings that went out, which is what a check reads - a keepalive that ran and sent
    nothing is a keepalive that only looks like it is working.
    """

    def __init__(self, sock: socket.socket, interval: Optional[float] = None,
                 trace: Optional[List[dict]] = None):
        self.sock = sock
        self.interval = SYNC_CONFIRM_PING_INTERVAL if interval is None else float(interval)
        self.trace = trace
        self.sent = 0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _run(self):
        # Event.wait rather than a sleep: a question answered at once stops this before it has sent
        # anything, which is what keeps an ordinary exchange free of extra frames.
        while not self._stop.wait(self.interval):
            try:
                send_json_msg(self.sock, {"cmd": protocol.CMD_PING})
                self.sent += 1
                if self.trace is not None:
                    self.trace.append({"dir": "send", "frame": {"cmd": protocol.CMD_PING}})
                answer = recv_json_msg(self.sock, timeout=self.interval)
                if self.trace is not None:
                    self.trace.append({"dir": "recv", "frame": answer or {}})
            except Exception:
                # The host has stopped answering. Stop rather than keep writing into a connection nobody is
                # reading; the exchange that resumes finds out the way it always has.
                return

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            # Long enough that the thread has finished whatever send/read pair it was in. Joining short
            # leaves a PONG unread on a socket the exchange is about to read its next answer from, and the
            # exchange then mistakes the answer to its PING for the answer to its request.
            self._thread.join(timeout=self.interval + 1.0)


class WireClient:
    """One connection to one host, speaking the protocol as `docs/sync-protocol.md` describes it.

    Built for a machine that has no chain configuration to read: a phone is handed an address, a port and a
    sync code - found by a scan, typed in from a card, or remembered from last time - and this is what it
    does with them. Every method is one exchange, returns what the host answered, and leaves the decisions
    about what to do next to the caller.

    `trace` is a list this client writes every frame into, in the order they go and come back, marked `send`
    or `recv`. That is what makes a phone's exchange testable before a phone exists: a probe records a whole
    session, and a later machine that claims to speak this protocol is compared against the recording.
    """

    def __init__(self, host_ip: str, port: int, sync_code: str, client_ip: Optional[str] = None,
                 connect_timeout: float = 3.0, socket_timeout: float = SYNC_SOCKET_TIMEOUT,
                 handshake_timeout: float = SYNC_RESTORE_HANDSHAKE_TIMEOUT,
                 trace: Optional[List[dict]] = None):
        self.host_ip = str(host_ip)
        self.port = int(port)
        self.sync_code = str(sync_code)
        # What this machine calls itself, which is what the host writes on its card. Sent as text and
        # compared as text; a machine that cannot name its own address names the routing table's guess.
        self.client_ip = str(client_ip or get_local_ip())
        self.connect_timeout = float(connect_timeout)
        self.socket_timeout = float(socket_timeout)
        self.handshake_timeout = float(handshake_timeout)
        self.trace = trace
        self.sock: Optional[socket.socket] = None
        self.chain_name = ""
        # The protocol version the host named in its answer to AUTH. None means it named none, which says a
        # 3.0-to-3.5 host - worth knowing before sending it a command only newer hosts answer.
        self.host_protocol_version: Optional[int] = None

    # -- the wire, and the recording of it ---------------------------------------------------------

    def _record(self, direction: str, frame: Any) -> None:
        if self.trace is not None:
            self.trace.append({"dir": direction, "frame": frame if frame is not None else {}})

    def _send(self, frame: Dict[str, Any]) -> None:
        if self.sock is None:
            raise ConnectionError("WireClient is not connected")
        self._record("send", frame)
        send_json_msg(self.sock, frame)

    def _recv(self, timeout: Optional[float] = None) -> Optional[dict]:
        if self.sock is None:
            raise ConnectionError("WireClient is not connected")
        answer = recv_json_msg(self.sock, timeout=self.handshake_timeout if timeout is None else timeout)
        self._record("recv", answer)
        return answer

    def connect(self) -> socket.socket:
        """Open the connection. It says nothing; `authenticate` is what says anything.

        The connect timeout is short on purpose and is the 3.0 seconds the desktop client uses: a phone
        looking for a host that is asleep wants the answer in seconds, and the address it tries first is the
        one the host last answered from.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.connect_timeout)
        sock.connect((self.host_ip, self.port))
        sock.settimeout(self.socket_timeout)
        self.sock = sock
        return sock

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None

    def __enter__(self):
        if self.sock is None:
            self.connect()
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        self.close()

    # -- the door, and the questions every exchange starts with ------------------------------------

    def authenticate(self) -> dict:
        """Say which chain this is, and learn what the host calls it.

        `AUTH` is the first thing a client that wants anything says, and this names the protocol version in
        the same breath - the only place in the exchange a version is named, and enough for both ends to know
        what the other speaks before a single file is offered.

        A host that turns this away answers once and lets the connection go, so the answer is read once and
        nothing after it is attempted.
        """
        self._send(protocol.with_protocol_version({"cmd": protocol.CMD_AUTH,
                                                   "sync_code": self.sync_code,
                                                   "client_ip": self.client_ip}))
        answer = self._recv(self.socket_timeout) or {}
        if answer.get("status") == protocol.STATUS_OK:
            self.chain_name = str(answer.get("chain_name") or "").strip()
            self.host_protocol_version = protocol.answered_protocol_version(answer)
        return answer

    def index(self, timeout: float = 25.0) -> Tuple[List[dict], str]:
        """Ask for the host's file list, and say what went wrong when there is no list.

        The longer timeout is the desktop client's, for the same reason: answering this means hashing the
        whole hosted folder, which is a slow drive doing a lot of work rather than a dead connection, and a
        client that gave up after twelve seconds would be a client that cannot use a big library.
        """
        self._send({"cmd": protocol.CMD_GET_INDEX})
        answer = self._recv(timeout) or {}
        if answer.get("status") != protocol.STATUS_OK:
            return [], str(answer.get("reason") or "the host did not answer with a file list")
        return list(answer.get("files") or []), ""

    def ping(self) -> dict:
        """Keep this connection warm once, and report the answer.

        A host answers `PONG`. The two answers that are not `PONG` are the ones a phone has to act on:
        `RESTORE_CLOSED` and `PUSH_CLOSED` say the offer this machine was waiting on has come off the host's
        screen - cancelled, replaced by another client, or out of time - and a client that keeps waiting for
        a code that is never coming back is a phone sitting on a dead exchange.
        """
        self._send({"cmd": protocol.CMD_PING})
        return self._recv(self.socket_timeout) or {}

    def fetch_config(self) -> Tuple[bool, str, Optional[dict]]:
        """Ask the host for its settings, and bring back what it answers.

        The shortest exchange a chain has, and the only one that moves no audio: a host that has agreed this
        machine belongs to one of its chains sends its own settings file whole, and which of those settings
        describe the machine that asked is decided here, at the receiving end, and not by the host.

        Returns (ok, what to report, what arrived).
        """
        self._send({"cmd": protocol.CMD_GET_CONFIG, "sync_code": self.sync_code,
                    "client_ip": self.client_ip})
        answer = self._recv(self.socket_timeout) or {}
        if answer.get("status") != protocol.STATUS_CONFIG:
            reason = str(answer.get("reason") or "the host refused without a reason")
            return False, f"Settings refused by the host: {reason}. Nothing here was changed.", None
        payload = answer.get("config")
        if not isinstance(payload, dict) or not payload:
            return False, "The host answered with no settings. Nothing here was changed.", None
        return True, f"Settings received from {self.host_ip}:{self.port}.", payload

    # -- taking a file (PY: pull, the only way a phone gets a track) ------------------------------

    def pull(self, filename: str, target_path, progress_cb: Optional[Callable[[int, int], None]] = None
             ) -> Tuple[bool, str]:
        """Ask for one file from the host's folder, and write it here.

        The host answers `SENDING` with the size and the checksum it is about to send, and the bytes follow
        that answer on the same socket - so the size and checksum that decide whether the file arrived come
        from the host's answer and not from the index that named the file. A host is reading its own disk at
        the moment it answers, and a file can have changed between the two.

        Nothing is written at `target_path` until every byte is down and the checksum matches: the bytes land
        in a `.tmp_sync` beside it, and only a file that hashes to what was promised takes the name. A phone
        that ends up with a half file with a track's name on it is a phone whose library lies to it, and the
        receiver below is what stops that.
        """
        self._send({"cmd": protocol.CMD_PULL_FILE, "filename": str(filename)})
        answer = self._recv(self.socket_timeout) or {}
        if answer.get("status") != protocol.STATUS_SENDING:
            return False, str(answer.get("reason") or f"the host would not send {filename}")
        size = int(answer.get("filesize") or 0)
        promised = str(answer.get("sha256") or "")
        if size <= 0 or len(promised) != protocol.SHA256_HEX_LENGTH:
            return False, f"the host named no size or no checksum for {filename}"
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not recv_file_from_socket(self.sock, target, size, promised, progress_cb):
            return False, f"{filename} did not arrive whole"
        return True, f"{filename} received"

    # -- sending files, which a rebuild and a push both do, in the same order --------------------

    def _send_files(self, needed: List[str], by_name: Dict[str, dict], folder,
                    progress_cb: Optional[Callable[[int, int, str, int, int], None]] = None
                    ) -> Tuple[int, List[str]]:
        """Offer the files this host agreed to take, one at a time, and count what it accepted.

        `PUSH_FILE` names the file, its size, its checksum and the date it was made; the host answers
        `RECEIVING` and the bytes follow on the same socket; the host answers `OK` once it has hashed them.
        The file is re-measured on the way out when it has changed since it was listed, because what the host
        is given has to be what is here now and not what was measured before a code was typed.

        A file the host asked for that this machine no longer has is skipped and named in the return - the
        host's own `PUSH_DONE` answer lists it as missing, and a client that invented a reason for its own
        empty folder would be a client reporting something the other end has not agreed to.
        """
        sent = 0
        skipped: List[str] = []
        total = len(needed)
        for idx, name in enumerate(needed, 1):
            path = Path(folder) / name
            try:
                stat_now = path.stat()
            except Exception:
                skipped.append(str(name))
                continue
            entry = by_name.get(str(name))
            if entry is None or stat_now.st_size != int(entry.get("size") or -1):
                entry = {"name": str(name), "size": stat_now.st_size, "mtime": stat_now.st_mtime,
                         "sha256": compute_file_sha256(path)}
            self._send({"cmd": protocol.CMD_PUSH_FILE, "filename": str(name),
                        "filesize": entry["size"], "sha256": entry["sha256"], "mtime": entry["mtime"]})
            go_ahead = self._recv() or {}
            if go_ahead.get("status") != protocol.STATUS_RECEIVING:
                continue
            stream_file_to_socket(self.sock, path,
                                  lambda done, tot, _n=str(name), _i=idx, _t=total:
                                  progress_cb(done, tot, _n, _i, _t) if progress_cb else None)
            receipt = self._recv() or {}
            if receipt.get("status") == protocol.STATUS_OK:
                sent += 1
        return sent, skipped

    # -- rebuilding a host (the phone's "I have the copy you lost") -----------------------------

    def restore_request(self) -> dict:
        """Ask the host to put a rebuild code on its screen.

        The code never travels on this socket and that is the whole design: it appears on the host's own
        screen, and the only way this machine learns it is a person reading it out. The answer is
        `WAITING_FOR_CODE` with the chain's name and how long the offer lives, and it is the moment a
        keepalive starts - somebody is about to be asked to type four characters on a phone, and a host that
        reads the next command with a 30-second timeout must not be the thing that ends this.
        """
        self._send({"cmd": protocol.CMD_RESTORE_REQUEST, "sync_code": self.sync_code,
                    "client_ip": self.client_ip})
        return self._recv(self.socket_timeout) or {}

    def restore_cancel(self) -> dict:
        """Take the code off the host's screen because nobody read it out."""
        self._send({"cmd": protocol.CMD_RESTORE_CANCEL, "sync_code": self.sync_code})
        return self._recv(self.socket_timeout) or {}

    def restore(self, code: str, folder,
                progress_cb: Optional[Callable[[int, int, str, int, int], None]] = None
                ) -> Tuple[bool, str, int]:
        """Name the code and rebuild the host from this machine's copy.

        The exchange is the rebuild's own, and the rule inside it is what keeps a rebuild safe: the client
        lists its whole folder, the host answers with the part of it it still needs, and only those files are
        sent. A file the host already holds byte for byte is not sent twice, nothing the host holds is
        deleted, and a code typed wrong closes the offer rather than leaving it open to be guessed at.

        Returns (ok, what to report, how many files the host wrote).
        """
        self._send({"cmd": protocol.CMD_RESTORE_CONFIRM, "sync_code": self.sync_code, "code": str(code)})
        accepted = self._recv(self.socket_timeout) or {}
        if accepted.get("status") != protocol.STATUS_CODE_ACCEPTED:
            reason = str(accepted.get("reason") or "the host did not answer")
            return False, f"The host did not accept that code: {reason}. Nothing was deleted here.", 0

        rows = library_index(folder)
        self._send({"cmd": protocol.CMD_PUSH_INDEX, "sync_code": self.sync_code, "files": rows})
        shortlist = self._recv() or {}
        if shortlist.get("status") != protocol.STATUS_RESTORING:
            reason = str(shortlist.get("reason") or "the host did not answer")
            return False, f"The host would not take this copy: {reason}. Nothing was deleted here.", 0

        needed = [str(name) for name in shortlist.get("files") or []]
        already_there = int(shortlist.get("already_there") or 0)
        sent, _skipped = self._send_files(needed, {row["name"]: row for row in rows}, folder, progress_cb)

        self._send({"cmd": protocol.CMD_PUSH_DONE, "sync_code": self.sync_code})
        done = self._recv() or {}
        if done.get("status") != protocol.STATUS_SYNCED:
            return False, ("The host never confirmed the rebuild - the connection was lost part way. "
                           "Nothing was deleted here."), sent
        missing = [str(name) for name in (done.get("missing") or [])]
        note = (f"Host rebuilt from this machine: {sent} file(s) written to {self.host_ip}:{self.port}, "
                f"{already_there} already there")
        if missing:
            note += f", {len(missing)} the host asked for did not arrive"
        return True, note + ". Nothing was deleted here.", sent

    # -- pushing files (the phone's "I made these here and you do not have them") ---------------

    def push_request(self) -> dict:
        """Ask whether this machine may offer its new files to the host.

        Two answers are a yes: `PUSH_ALLOWED` means this address has already been given leave on the host's
        own screen and needs no code, and `WAITING_FOR_PUSH_CODE` means a code is on that screen now and
        somebody has to read it out. The rest are refusals, and the fact worth reading out of all of them is
        the limit - a host takes a handful of files per push and says how many, and a client that measured a
        whole library before asking is a client that hashed 400 files to be offered five.
        """
        self._send({"cmd": protocol.CMD_PUSH_REQUEST, "sync_code": self.sync_code,
                    "client_ip": self.client_ip})
        return self._recv(self.socket_timeout) or {}

    def push_start(self, code: Optional[str] = None) -> dict:
        """Begin the push: name the code, or name nothing when this address was let through already."""
        frame: Dict[str, Any] = {"cmd": protocol.CMD_PUSH_START, "sync_code": self.sync_code}
        if code:
            frame["code"] = str(code)
        self._send(frame)
        return self._recv(self.socket_timeout) or {}

    def push_cancel(self) -> dict:
        """Take the push code off the host's screen."""
        self._send({"cmd": protocol.CMD_PUSH_CANCEL, "sync_code": self.sync_code})
        return self._recv(self.socket_timeout) or {}

    def push(self, names: List[str], folder,
             progress_cb: Optional[Callable[[int, int, str, int, int], None]] = None
             ) -> Tuple[bool, str, int, int]:
        """Offer this machine's new files to the host, and report what it took.

        Only the named files are measured: a client that measures its whole library when it was asked about
        four files is a client doing work nobody asked it for. The host answers with what it will take - a
        name it already holds stays its own, newest first up to its limit - and the files sent are exactly
        that list. Nothing here pulls, nothing here deletes, and nothing the host holds is replaced.

        Returns (ok, what to report, how many the host wrote, how many it refused).
        """
        rows: List[dict] = []
        for name in names:
            path = Path(folder) / str(name)
            try:
                stat = path.stat()
                rows.append({"name": str(name), "size": stat.st_size, "mtime": stat.st_mtime,
                             "sha256": compute_file_sha256(path)})
            except Exception:
                continue
        if not rows:
            return False, "Nothing to push - they are no longer in this folder.", 0, 0

        self._send({"cmd": protocol.CMD_PUSH_INDEX, "sync_code": self.sync_code, "files": rows})
        shortlist = self._recv() or {}
        if shortlist.get("status") != protocol.STATUS_PUSHING:
            reason = str(shortlist.get("reason") or "the host did not answer")
            return False, f"The host would not take these files: {reason}. Nothing was pushed.", 0, 0

        wanted = [str(name) for name in shortlist.get("files") or []]
        refused = int(shortlist.get("refused") or 0)
        already_there = int(shortlist.get("already_there") or 0)
        sent, _skipped = self._send_files(wanted, {row["name"]: row for row in rows}, folder, progress_cb)

        self._send({"cmd": protocol.CMD_PUSH_DONE, "sync_code": self.sync_code})
        done = self._recv() or {}
        if done.get("status") != protocol.STATUS_SYNCED:
            return False, ("The host never confirmed the push - the connection was lost part way. "
                           "Nothing here was deleted."), sent, refused
        refused = int(done.get("refused") or refused)
        missing = [str(name) for name in (done.get("missing") or [])]
        note = (f"{sent} file(s) added to {self.host_ip}:{self.port}, {already_there} already there, "
                f"{refused} refused")
        if missing:
            note += f", {len(missing)} the host agreed to take never arrived"
        return True, note + ". Nothing was deleted here.", sent, refused







