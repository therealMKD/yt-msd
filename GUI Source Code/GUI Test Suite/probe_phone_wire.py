"""A phone's whole conversation with a host, proved before there is a phone.

`docs/sync-protocol.md` writes down what a new endpoint has to speak, and this suite is what proves the
document is true of the program that answers it. A phone is a client with no chain configuration, no
window, no Qt and no Python: everything it can do is what `yt_msd.sync.wire` does, and every one of those
moves is driven here against a real `SyncHostServer` over a real socket.

  PW1 - PW8    the wire layer speaks no Qt, and `protocol.py` names the words `host.py` speaks
  PW9 - PW14   the discovery a phone runs: a `HELLO` scan across addresses, and what a host may say
  PW15 - PW21  the whole offline-playback session: AUTH, GET_INDEX, PULL_FILE, GET_CONFIG, PING
  PW22 - PW26  the refusals at the door a phone must read as refusals, and a keepalive that hands the
               socket back clean
  PW27 - PW31  the whole Restore Host exchange - requested, taken away, wrong code, given up, rebuilt
  PW32 - PW36  a Push, with a code and without one, and the host keeping its own copy of a name it holds
  PW37 - PW39  the recorded session compared with `fixtures/protocol/phone_session.json`, the shapes the
               wire promises, and the fixture folders gone again

Recipe, and it is the one suite in this folder that is different: this suite does not copy
`GUI Source Code/yt-msd-gui.pyw` and does not use `harness_seam.py`. A phone speaks to the `yt_msd`
package and not to the GUI, so what is under test is the package boundary itself -
`yt_msd.sync.wire`, `yt_msd.sync.host` and `yt_msd.sync.protocol`, imported as the modules a phone's
equivalent would import. Nothing here replaces anything in the entry point, which is all the seam is for.

Two boundaries, and they are the ones probe_sync draws for the same reasons:

  - Sockets are on 127.0.0.1 only, and `SyncHostServer.start()` is never called: binding
    `SYNC_PORT_START..SYNC_PORT_END` could collide with a yt-msd genuinely running on this machine. The
    host is served on a listener bound to port 0 over loopback and its `_handle_client` is what answers.
    No beacon is started, nothing is broadcast, and the scan in PW12 is handed its addresses by hand.
  - Files live under `copy/phone_wire_fixture/`, rebuilt at the start of every run and deleted at the
    end. No check touches a real device, the app's own config folder, or a real music library.

Fixture files carry fixed timestamps and fixed bytes, which is what makes PW35 possible: a recorded
session's index entries, sizes and checksums are the same on every machine, so the golden fixture is a
recording of a real exchange and not a template of one.
"""
import hashlib
import json
import os
import shutil
import socket
import sys
import threading
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))                    # .../GUI Source Code/GUI Test Suite
SRC_DIR = os.path.dirname(HERE)                                      # GUI Source Code, which holds yt_msd
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from yt_msd.sync import host as host_mod
from yt_msd.sync import protocol
from yt_msd.sync import wire

RECORD = "--record" in sys.argv

CHECKS = 0
FAILS = []


def check(label, cond, detail=""):
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"ok   {label}")
    else:
        FAILS.append(label)
        print(f"FAIL {label} {detail}")


# ---------------------------------------------------------------------------
# Fixtures: the two libraries, and the host that serves one of them
# ---------------------------------------------------------------------------

FIXTURE_ROOT = Path(HERE) / "copy" / "phone_wire_fixture"
shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)
FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)
FIXTURES = Path(HERE) / "fixtures" / "protocol"
GOLDEN = FIXTURES / "phone_session.json"

HOST_FOLDER = FIXTURE_ROOT / "host library"
HOST_FOLDER.mkdir(parents=True, exist_ok=True)
PUSH_FOLDER = FIXTURE_ROOT / "host library taking pushes"
PUSH_FOLDER.mkdir(parents=True, exist_ok=True)
PUSH2_FOLDER = FIXTURE_ROOT / "host library asked for a code"
PUSH2_FOLDER.mkdir(parents=True, exist_ok=True)
PHONE_FOLDER = FIXTURE_ROOT / "phone library"
PHONE_FOLDER.mkdir(parents=True, exist_ok=True)
PUSH_SOURCE = FIXTURE_ROOT / "phone library that made files"
PUSH_SOURCE.mkdir(parents=True, exist_ok=True)

FIXED_MTIME = 1700000000.0


def audio_file(folder, name, body, mtime=FIXED_MTIME):
    """A file with an audio suffix and a fixed date. The contents are bytes rather than real audio, so
    `read_metadata_tags` finds no tags in it - which is the sparse case a phone has to survive anyway."""
    path = Path(folder) / name
    path.write_bytes(body)
    os.utime(path, (mtime, mtime))
    return path


audio_file(HOST_FOLDER, "one.mp3", b"the first track a phone will ask for")
audio_file(HOST_FOLDER, "two.mp3", b"the second track, longer than the first one", FIXED_MTIME + 5)
(HOST_FOLDER / "notes.txt").write_text("not a track at all", encoding="utf-8")
audio_file(PUSH_FOLDER, "old song.mp3", b"the host's own copy of this name")
audio_file(PUSH2_FOLDER, "old song.mp3", b"the second host's own copy of this name")
audio_file(PHONE_FOLDER, "old song.mp3", b"the phone's different copy of the same name")
for _n, _body in enumerate([b"made on the phone, first", b"made on the phone, second",
                            b"made on the phone, third", b"made on the phone, fourth"], 1):
    audio_file(PHONE_FOLDER, f"new {_n}.mp3", _body, FIXED_MTIME + _n)
audio_file(PUSH_SOURCE, "old song.mp3", b"the phone's own copy of a name the host holds")
for _n, _body in enumerate([b"pushed from the phone, first", b"pushed from the phone, second",
                            b"pushed from the phone, third", b"pushed from the phone, fourth"], 1):
    audio_file(PUSH_SOURCE, f"new {_n}.mp3", _body, FIXED_MTIME + _n)

# The settings the host hands a client that asks. Plain keys of its own - the phone's own rules about
# which of them describe it are proved in probe_windows against a settings file of its own.
HOST_SETTINGS = {"format": "m4a", "bitrate": "192", "mode": "Light", "accent": "Teal", "volume": 60,
                 "last_search": "grass roots", "folders": ["D:\\Host Downloads"],
                 "hosted_chains": [{"id": "hc_7301", "sync_code": "7301", "name": "Phone Test"}],
                 "client_chains": [], "sync_settings": {"auto_sync_interval_mins": 20}}

HOST_ACTIVITY = []
RESTORE_EVENTS = []

CHAINS = [
    {"sync_code": "7301", "name": "Phone Test", "folder_path": str(HOST_FOLDER), "visible": True,
     "max_pushed_files": 3},
    {"sync_code": "7302", "name": "Private Test", "folder_path": str(HOST_FOLDER), "visible": False},
    {"sync_code": "7303", "name": "Trusted Push", "folder_path": str(PUSH_FOLDER),
     "push_trusted_ips": ["127.0.0.1"], "max_pushed_files": 5},
    {"sync_code": "7304", "name": "Push Test", "folder_path": str(PUSH2_FOLDER),
     "push_trusted_ips": [], "max_pushed_files": 3},
]

SERVER = host_mod.SyncHostServer(
    lambda: CHAINS,
    on_client_activity_cb=lambda code, ip, note: HOST_ACTIVITY.append((code, note)),
    on_restore_event_cb=lambda code, ip, event, note: RESTORE_EVENTS.append((code, event, note)),
    get_config_cb=lambda: dict(HOST_SETTINGS))


class LoopbackHost:
    """A sync host served over loopback, on a port nobody else is using.

    `SyncHostServer.start()` is what a running yt-msd calls, and this suite must not call it: it binds
    63350 to 63370, and a yt-msd genuinely running on this machine is already sitting on the first free one
    of those. So the server's own `_handle_client` is what answers, behind a listener on port 0 that the
    operating system hands a free port to, and a phone's `connect()` is a real connect to a real port.
    Everything the wire layer does - framing, ordering, timeouts, the raw bytes of a file - is exercised
    over a socket pair, which is the only way a check of a protocol is worth anything.
    """

    def __init__(self, server):
        self.server = server
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(8)
        self.port = self.listener.getsockname()[1]
        self._stop = threading.Event()
        self._workers = []

    def start(self):
        # `start()` is also what records the port on the server, and the server's HELLO answer names that
        # port as the one a client should fetch from. Set it here, or every discovery answer below says 0
        # and the check that reads it is a check of nothing.
        self.server.active_port = self.port
        self.server._running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                connection, address = self.listener.accept()
            except OSError:
                return
            worker = threading.Thread(target=self._serve, args=(connection, address[0]), daemon=True)
            self._workers.append(worker)
            worker.start()

    def _serve(self, connection, peer_ip):
        try:
            # The peer of the socket, which is the address a host trusts a push from - not the address a
            # client chooses to name in its own message.
            self.server._handle_client(connection, peer_ip)
        except Exception:
            pass
        finally:
            try:
                connection.close()
            except Exception:
                pass

    def stop(self):
        self._stop.set()
        self.server._running = False
        try:
            self.listener.close()
        except Exception:
            pass
        for worker in self._workers:
            worker.join(3)


HOST = LoopbackHost(SERVER)
HOST.start()

# ---------------------------------------------------------------------------
# PW1 - PW8: the wire layer is Qt-free, and protocol.py names the words host.py speaks
#
# A phone cannot import PySide6, so "Qt-free" is not a style preference here - it is the thing that makes
# the reference importable at all. And a phone reads a list of names rather than a control flow: every
# command and every status protocol.py names has to be a word the host actually says, or the document and
# the code drift apart and the phone is written against a protocol that does not exist.
# ---------------------------------------------------------------------------

import ast                                                     # noqa: E402  (with the suite's imports)

WIRE_PATH = os.path.join(SRC_DIR, "yt_msd", "sync", "wire.py")
PROTOCOL_PATH = os.path.join(SRC_DIR, "yt_msd", "sync", "protocol.py")
HOST_PATH = os.path.join(SRC_DIR, "yt_msd", "sync", "host.py")
DISCOVERY_PATH = os.path.join(SRC_DIR, "yt_msd", "sync", "discovery.py")
HOST_SOURCE = Path(HOST_PATH).read_text(encoding="utf-8")


def _imported_names(path):
    """Every module this file imports, read out of its own syntax tree."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append(node.module or "")
    return found


def _spoken(source, word):
    """Is this word said in this source as a string, and not merely part of a longer word?"""
    return f"'{word}'" in source or f'"{word}"' in source


check("PW1 the wire layer and the protocol module import nothing from Qt",
      not any("PySide6" in name or "PyQt" in name
              for name in _imported_names(WIRE_PATH) + _imported_names(PROTOCOL_PATH)),
      _imported_names(WIRE_PATH))

check("PW2 importing the wire layer puts no Qt module in this process",
      not [name for name in sys.modules if name.startswith("PySide6")],
      [name for name in sys.modules if name.startswith("PySide6")][:3])

check("PW3 every command protocol.py names is a command the host answers",
      all(_spoken(HOST_SOURCE, command) for command in protocol.CLIENT_COMMANDS),
      [command for command in sorted(protocol.CLIENT_COMMANDS) if not _spoken(HOST_SOURCE, command)])

check("PW4 every status protocol.py names is a status the host sends",
      all(_spoken(HOST_SOURCE, status) for status in protocol.HOST_STATUSES),
      [status for status in sorted(protocol.HOST_STATUSES) if not _spoken(HOST_SOURCE, status)])

check("PW5 the discovery frame types are the types the beacon loop speaks",
      all(_spoken(Path(DISCOVERY_PATH).read_text(encoding="utf-8"), kind)
          for kind in protocol.DISCOVERY_TYPES),
      sorted(protocol.DISCOVERY_TYPES))

check("PW6 this machine speaks one protocol version, and says which",
      protocol.PROTOCOL_VERSION == 1 and protocol.SUPPORTED_PROTOCOL_VERSIONS == (1,)
      and protocol.APP_NAME == host_mod.DISCOVERY_APP_NAME
      and protocol.SHA256_HEX_LENGTH == 64 and protocol.SYNC_CODE_LENGTH == 4,
      (protocol.PROTOCOL_VERSION, protocol.SUPPORTED_PROTOCOL_VERSIONS, protocol.APP_NAME))

check("PW7 a request that names no version, or names nonsense, is read as the version 3.0 speaks",
      protocol.requested_protocol_version({}) == 1
      and protocol.requested_protocol_version({"protocol_version": "2"}) == 2
      and protocol.requested_protocol_version({"protocol_version": True}) == 1
      and protocol.requested_protocol_version({"protocol_version": 0}) == 1
      and protocol.requested_protocol_version({"protocol_version": "last tuesday"}) == 1
      and protocol.requested_protocol_version(None) == 1, None)

check("PW8 a refusal names the version the host speaks and the one it was asked for, in both directions",
      protocol.version_answer({}) is None
      and protocol.version_answer({"protocol_version": 1}) is None
      and "version 1" in protocol.version_refusal(9) and "9" in protocol.version_refusal(9)
      and "on this machine" in protocol.version_refusal(9)
      and "the machine that asked" in protocol.version_refusal(0)
      and protocol.answered_protocol_version({"protocol_version": 1}) == 1
      and protocol.answered_protocol_version({}) is None
      and protocol.with_protocol_version({"cmd": "AUTH"}) == {"cmd": "AUTH", "protocol_version": 1},
      protocol.version_refusal(9))

# ---------------------------------------------------------------------------
# PW9 - PW13: the discovery a phone runs
#
# A phone has no chain file to read, so a scan is where it starts. What it may learn from a stranger is the
# rule the desktop has always had: a visible chain names itself freely, and a private chain names itself
# only to a machine that already has its code - which is the code that machine would need to sync it
# anyway.
# ---------------------------------------------------------------------------

ANSWER = wire.probe_host("127.0.0.1", HOST.port)
NAMED = (ANSWER or {}).get("chains") or []

check("PW9 a HELLO answers the app's name, the machine's name, the port a client would fetch from, and the protocol it speaks",
      (ANSWER or {}).get("status") == "OK" and (ANSWER or {}).get("app") == protocol.APP_NAME
      and (ANSWER or {}).get("port") == HOST.port and (ANSWER or {}).get("protocol_version") == 1
      and bool((ANSWER or {}).get("host_name")), ANSWER)

check("PW10 a HELLO names a visible chain by code and name, and never names the folder it lives in",
      any(row.get("sync_code") == "7301" and row.get("name") == "Phone Test" and row.get("visible")
          for row in NAMED) and not any("folder_path" in row for row in NAMED), NAMED)

check("PW11 a private chain is named to no untargeted search",
      not any(row.get("sync_code") == "7302" for row in NAMED), NAMED)

PRIVATE = wire.probe_host("127.0.0.1", HOST.port, "7302") or {}
check("PW12 a private chain answers a search that already has its code, because that is the code it would need to sync it",
      PRIVATE.get("status") == "OK"
      and any(row.get("sync_code") == "7302" and row.get("visible") is False
              for row in PRIVATE.get("chains") or []), PRIVATE)

check("PW13 an address with nothing behind it answers nothing at all",
      wire.probe_host("127.0.0.1", 0) is None and wire.probe_host("127.0.0.1", 1) is None, None)

SCAN_SEEN = []
SCAN = wire.scan_for_hosts(["127.0.0.1", "127.0.0.2"], [HOST.port, HOST.port + 1], "7301",
                           on_reply=lambda ip, port, reply: SCAN_SEEN.append((ip, port)))
check("PW14 a scan finds the host, tells the caller about each answer as it arrives, and ignores the addresses with nothing behind them",
      len(SCAN) == 1 and SCAN[0]["host_ip"] == "127.0.0.1" and SCAN[0]["port"] == HOST.port
      and SCAN_SEEN == [("127.0.0.1", HOST.port)]
      and SCAN[0]["reply"].get("status") == "OK", (SCAN, SCAN_SEEN))

# ---------------------------------------------------------------------------
# PW15 - PW21: the whole session a phone needs before it can play anything
#
# This is the MVP in one block: say which chain, ask what it holds, take a file, ask for the settings, keep
# the connection warm. Every frame of it is recorded, because PW36 compares the recording with a fixture a
# phone's every move can be checked against.
# ---------------------------------------------------------------------------

SESSION_TRACE: List[dict] = []
RECEIVED = PHONE_FOLDER / "received"
RECEIVED.mkdir(parents=True, exist_ok=True)

phone = wire.WireClient("127.0.0.1", HOST.port, "7301", client_ip="192.168.1.77",
                        socket_timeout=8.0, handshake_timeout=20.0, trace=SESSION_TRACE)
phone.connect()
AUTH = phone.authenticate()
FILES, INDEX_ERROR = phone.index()

check("PW15 a phone says which chain it is and learns what the host calls it, and both ends learn the protocol they are speaking",
      AUTH.get("status") == "OK" and AUTH.get("chain_name") == "Phone Test"
      and phone.chain_name == "Phone Test" and AUTH.get("protocol_version") == 1
      and phone.host_protocol_version == 1
      and SESSION_TRACE[0]["frame"].get("cmd") == "AUTH"
      and SESSION_TRACE[0]["frame"].get("protocol_version") == 1
      and SESSION_TRACE[0]["frame"].get("sync_code") == "7301", (AUTH, SESSION_TRACE[0]))

check("PW16 the host's list names every track with the size, date, hash and tags a phone judges a file by",
      INDEX_ERROR == "" and [row["name"] for row in FILES] == ["one.mp3", "two.mp3"]
      and all(row["size"] == (HOST_FOLDER / row["name"]).stat().st_size
              and len(row["sha256"]) == protocol.SHA256_HEX_LENGTH
              and abs(row["mtime"] - (HOST_FOLDER / row["name"]).stat().st_mtime) < 1.0
              and "artist" in row and "title" in row for row in FILES), (FILES, INDEX_ERROR))

PULLED = []
for _row in FILES:
    _ok, _note = phone.pull(_row["name"], RECEIVED / _row["name"])
    PULLED.append((_row["name"], _ok, _note))
    SESSION_TRACE.append({"dir": "recv_bytes", "frame": {
        "filename": _row["name"],
        "size": (RECEIVED / _row["name"]).stat().st_size if (RECEIVED / _row["name"]).exists() else -1,
        "sha256": hashlib.sha256((RECEIVED / _row["name"]).read_bytes()).hexdigest()
        if (RECEIVED / _row["name"]).exists() else ""}})

check("PW17 a pulled file arrives byte for byte, is checked against the hash the host announced, and leaves no temporary behind",
      all(ok for _n, ok, _t in PULLED)
      and all((RECEIVED / name).read_bytes() == (HOST_FOLDER / name).read_bytes()
              for name in ["one.mp3", "two.mp3"])
      and not list(RECEIVED.glob("*.tmp_sync")), PULLED)

check("PW18 a pull that is asked for twice is answered twice: the host sends the file again and the client keeps the copy it has",
      phone.pull("one.mp3", RECEIVED / "one.mp3")[0]
      and (RECEIVED / "one.mp3").read_bytes() == (HOST_FOLDER / "one.mp3").read_bytes(), None)

RETRY = wire.WireClient("127.0.0.1", HOST.port, "7301", client_ip="192.168.1.77",
                        socket_timeout=8.0, handshake_timeout=20.0)
RETRY.connect()
RETRY.authenticate()
NOT_A_TRACK = RETRY.pull("notes.txt", RECEIVED / "notes.txt")
check("PW19 a host will not hand over a file that is not a track, and says which it is",
      NOT_A_TRACK[0] is False and "audio" in NOT_A_TRACK[1]
      and not (RECEIVED / "notes.txt").exists(), NOT_A_TRACK)

CONFIG_OK, CONFIG_NOTE, CONFIG = phone.fetch_config()
check("PW20 the host sends its settings whole to a client that authenticated, and the phone keeps them as a file of another machine",
      CONFIG_OK is True and CONFIG == HOST_SETTINGS and f"{HOST.port}" in CONFIG_NOTE, (CONFIG_OK, CONFIG_NOTE))

check("PW21 a PING in an ordinary session is answered with a PONG and nothing else moves",
      phone.ping() == {"status": "PONG"}, phone.ping())

phone.close()
RETRY.close()

# ---------------------------------------------------------------------------
# PW22 - PW26: the refusals at the door, and a connection kept warm
#
# A phone has to read a refusal as a refusal. A host answers once at its door and lets the connection go,
# which a client that is not built for it reads as a hung request - and a phone that reports "the host did
# not answer" for a chain it was never given is a phone that tells a person to try again on a machine that
# has already said no.
# ---------------------------------------------------------------------------


def _raw_round(messages, expecting):
    """Send these frames to the host over a real connection and read back what it answers.

    Reads are guarded: a host that refuses at its door closes the connection, and on Windows reading a
    socket the other end has just closed can raise rather than answer nothing.
    """
    sock = socket.create_connection(("127.0.0.1", HOST.port), timeout=8.0)
    answers = []
    try:
        for message in messages:
            wire.send_json_msg(sock, message)
        for _ in range(expecting):
            try:
                answers.append(wire.recv_json_msg(sock, timeout=8.0))
            except OSError:
                answers.append(None)
    finally:
        sock.close()
    return answers


ANSWERS = _raw_round([{"cmd": "GET_INDEX"}], 1)
check("PW22 a client that opens with anything but AUTH is turned away before it is told anything",
      ANSWERS[0] == {"status": "ERROR", "reason": "Expected AUTH command"}, ANSWERS)

ANSWERS = _raw_round([{"cmd": "AUTH", "sync_code": "9999"}], 1)
check("PW23 a sync code this host does not have is refused by name, and the refusal is the only answer",
      ANSWERS[0].get("status") == "ERROR" and "9999" in ANSWERS[0].get("reason", ""), ANSWERS)

# The two halves are read in the order the exchange happens rather than sent together. A host that refuses
# at its door closes the connection, and a socket closed with data it has not read discards what it had
# already queued to send - a client that fires its follow-up request first can be left reading a reset
# instead of the refusal it was given.
REFUSED = []
_refused = socket.create_connection(("127.0.0.1", HOST.port), timeout=8.0)
try:
    wire.send_json_msg(_refused, {"cmd": "AUTH", "sync_code": "7301", "protocol_version": 99})
    try:
        REFUSED.append(wire.recv_json_msg(_refused, timeout=8.0))
    except OSError:
        REFUSED.append(None)
    wire.send_json_msg(_refused, {"cmd": "GET_INDEX"})
    try:
        REFUSED.append(wire.recv_json_msg(_refused, timeout=8.0))
    except OSError:
        REFUSED.append(None)
finally:
    _refused.close()
check("PW24 a client naming a protocol this host does not speak is refused at the door, told which, and not answered at",
      (REFUSED[0] or {}).get("status") == "ERROR"
      and "protocol version 1" in (REFUSED[0] or {}).get("reason", "")
      and "99" in (REFUSED[0] or {}).get("reason", "")
      and not any((answer or {}).get("status") == "OK" for answer in REFUSED[1:]), REFUSED)

ANSWERS = _raw_round([{"cmd": "AUTH", "sync_code": "7301"}, {"cmd": "WAT"}, {"cmd": "GET_INDEX"}], 3)
check("PW25 a command the host does not know is answered as an error naming it, and the session carries on after it",
      ANSWERS[1].get("status") == "ERROR" and "WAT" in ANSWERS[1].get("reason", "")
      and ANSWERS[2].get("status") == "OK" and "files" in ANSWERS[2], ANSWERS)

WARM = wire.WireClient("127.0.0.1", HOST.port, "7301", client_ip="192.168.1.77",
                       socket_timeout=8.0, handshake_timeout=20.0)
WARM.connect()
WARM.authenticate()
KEEP = wire.Keepalive(WARM.sock, interval=0.3)
KEEP.start()
time.sleep(0.75)
KEEP.stop()
WARM_INDEX, WARM_INDEX_ERROR = WARM.index()
check("PW26 a keepalive pings while a person reads a code, and hands the socket back clean - the next command is the next command and not somebody's PONG",
      KEEP.sent >= 2 and WARM_INDEX_ERROR == "" and len(WARM_INDEX) == 2
      and ("7301", "Connected") in HOST_ACTIVITY, (KEEP.sent, WARM_INDEX_ERROR))
WARM.close()

# ---------------------------------------------------------------------------
# PW27 - PW31: rebuilding a host, with a person reading a code off a screen
#
# The exchange a phone is worst at, because the thing that authorises it never travels on the wire: the
# host puts four characters on its own screen and the only way they reach the phone is a person reading
# them out. Every way that can go wrong is here - the offer taken away while somebody is typing, the code
# mistyped, the person giving up, and the rebuild itself.
# ---------------------------------------------------------------------------


def _session(sync_code, trace=None):
    """An authenticated session on one chain, as a phone opens one."""
    client = wire.WireClient("127.0.0.1", HOST.port, sync_code, client_ip="192.168.1.77",
                             socket_timeout=8.0, handshake_timeout=25.0, trace=trace)
    client.connect()
    client.authenticate()
    return client


def _latest_offer(sync_code, event):
    """The code this host last put on its screen for this chain.

    The host reports it to the window that shows it, which is the only place it exists: a client cannot
    ask for it, and that is the design. A test reads it out of the same report, and a phone gets it from a
    person's thumb on a keypad.
    """
    for _code, _event, _note in reversed(RESTORE_EVENTS):
        if _code == sync_code and _event == event:
            return _note
    return None


REBUILD = _session("7301")
REQUEST = REBUILD.restore_request()
check("PW27 a restore request puts a code on the host's screen, names the chain, and says how long the offer lives",
      REQUEST.get("status") == "WAITING_FOR_CODE" and REQUEST.get("chain_name") == "Phone Test"
      and int(REQUEST.get("expires_in") or 0) >= 60
      and _latest_offer("7301", "requested") is not None, REQUEST)

SERVER.cancel_restore_request("7301")
CLOSED = REBUILD.ping()
check("PW28 a code taken off the host's screen is reported to the machine waiting on it, on the next PING",
      CLOSED.get("status") == "RESTORE_CLOSED"
      and _latest_offer("7301", "cancelled") == "offer closed", CLOSED)
REBUILD.close()

REBUILD = _session("7301")
REBUILD.restore_request()
WRONG = REBUILD.restore("NOPE", PHONE_FOLDER)
check("PW29 a code typed wrong is an answer and not a hint: the host refuses it by what it is and closes the offer",
      WRONG[0] is False and "not the code on the host screen" in WRONG[1] and WRONG[2] == 0
      and _latest_offer("7301", "cancelled") == "wrong code", WRONG)
REBUILD.close()

REBUILD = _session("7301")
REBUILD.restore_request()
GAVE_UP = REBUILD.restore_cancel()
check("PW30 nobody read the code out: the client closes the offer and the host takes it off its screen",
      GAVE_UP.get("status") == "CANCELLED"
      and _latest_offer("7301", "cancelled") == "client cancelled", GAVE_UP)
REBUILD.close()

REBUILD = _session("7301")
REBUILD.restore_request()
CODE = _latest_offer("7301", "requested")
REBUILT_OK, REBUILT_NOTE, REBUILT_COUNT = REBUILD.restore(CODE, PHONE_FOLDER)
REBUILD.close()
HOST_NAMES = sorted(p.name for p in HOST_FOLDER.iterdir())
check("PW31 a rebuild writes what the host asked for, keeps what it held, and deletes nothing",
      REBUILT_OK is True and REBUILT_COUNT == 5
      and all((HOST_FOLDER / name).read_bytes() == (PHONE_FOLDER / name).read_bytes()
              for name in ["old song.mp3", "new 1.mp3", "new 2.mp3", "new 3.mp3", "new 4.mp3"])
      and (HOST_FOLDER / "one.mp3").exists() and (HOST_FOLDER / "two.mp3").exists()
      and (HOST_FOLDER / "notes.txt").exists()
      and "Nothing was deleted here." in REBUILT_NOTE
      and abs((HOST_FOLDER / "new 4.mp3").stat().st_mtime - (FIXED_MTIME + 4)) < 2.0,
      (REBUILT_OK, REBUILT_NOTE, REBUILT_COUNT, HOST_NAMES))

# ---------------------------------------------------------------------------
# PW32 - PW36: a Push, with a code and without one
#
# The one thing a client can do to somebody else's library, so the host decides all of it: whether this
# address needs a code, how many files it may bring, and which of them it will take. A name the host
# already holds stays the host's, however different the two copies are.
# ---------------------------------------------------------------------------

PUSHNAMES = sorted(p.name for p in PUSH_SOURCE.iterdir())

CODED = _session("7304")
ASK = CODED.push_request()
check("PW32 an address that has not been given leave to push is offered a code, told the chain's name and how many files the host takes",
      ASK.get("status") == "WAITING_FOR_PUSH_CODE" and ASK.get("chain_name") == "Push Test"
      and int(ASK.get("limit") or 0) == 3 and int(ASK.get("expires_in") or 0) >= 60
      and _latest_offer("7304", "push_requested") is not None, ASK)

BAD_START = CODED.push_start("NOPE")
check("PW33 a push code typed wrong closes the offer, and nothing is written",
      BAD_START.get("status") == "ERROR" and "not the code on the host screen" in BAD_START.get("reason", "")
      and _latest_offer("7304", "push_cancelled") == "wrong code", BAD_START)

CODED.push_request()
START = CODED.push_start(_latest_offer("7304", "push_requested"))
CODED_OK, CODED_NOTE, CODED_SENT, CODED_REFUSED = CODED.push(PUSHNAMES, PUSH_SOURCE)
CODED_INDEX, CODED_INDEX_ERROR = CODED.index()
check("PW34 a coded push writes the newest files up to the host's limit, keeps its own copy of a name it holds, and leaves the connection open",
      START.get("status") == "PUSH_ACCEPTED" and START.get("code_required") is True
      and CODED_OK is True and CODED_SENT == 3 and CODED_REFUSED == 2
      and all((PUSH2_FOLDER / name).read_bytes() == (PUSH_SOURCE / name).read_bytes()
              for name in ["new 2.mp3", "new 3.mp3", "new 4.mp3"])
      and not (PUSH2_FOLDER / "new 1.mp3").exists()
      and (PUSH2_FOLDER / "old song.mp3").read_bytes() == b"the second host's own copy of this name"
      and CODED_INDEX_ERROR == "" and len(CODED_INDEX) == 4,
      (START, CODED_OK, CODED_NOTE, CODED_SENT, CODED_REFUSED))
CODED.close()

TRUSTED = _session("7303")
TRUSTED_ASK = TRUSTED.push_request()
TRUSTED_START = TRUSTED.push_start()
TRUSTED_OK, TRUSTED_NOTE, TRUSTED_SENT, TRUSTED_REFUSED = TRUSTED.push(PUSHNAMES, PUSH_SOURCE)
check("PW35 an address the host has already let through pushes with no code at all, and takes the host's whole limit",
      TRUSTED_ASK.get("status") == "PUSH_ALLOWED" and TRUSTED_ASK.get("code_required") is False
      and TRUSTED_START.get("status") == "PUSH_ACCEPTED"
      and TRUSTED_START.get("code_required") is False and TRUSTED_OK is True
      and TRUSTED_SENT == 4 and TRUSTED_REFUSED == 1
      and all((PUSH_FOLDER / name).read_bytes() == (PUSH_SOURCE / name).read_bytes()
              for name in ["new 1.mp3", "new 2.mp3", "new 3.mp3", "new 4.mp3"])
      and (PUSH_FOLDER / "old song.mp3").read_bytes() == b"the host's own copy of this name",
      (TRUSTED_ASK, TRUSTED_OK, TRUSTED_NOTE, TRUSTED_SENT, TRUSTED_REFUSED))
TRUSTED.close()

CANCELLER = _session("7304")
CANCELLER.push_request()
PUSH_GAVE_UP = CANCELLER.push_cancel()
check("PW36 a push nobody read the code for is closed, and the host takes the code off its screen",
      PUSH_GAVE_UP.get("status") == "CANCELLED"
      and _latest_offer("7304", "push_cancelled") == "client cancelled", PUSH_GAVE_UP)
CANCELLER.close()

# ---------------------------------------------------------------------------
# PW37 - PW39: the recording of the session, and the shapes the wire promises
#
# This is the check the Android app will be measured against. Every frame the phone sends and every frame
# the host answered, in order, from PW15 to PW21 - recorded once into
# `fixtures/protocol/phone_session.json` and compared byte for byte on every run since. Run this suite with
# `--record` to write a new one, read what it wrote, and commit it; the frames a phone will speak are the
# frames in that file.
# ---------------------------------------------------------------------------

RECORDED = {"protocol_version": protocol.PROTOCOL_VERSION, "chain": "7301",
            "client_ip": "192.168.1.77", "frames": SESSION_TRACE}

if RECORD:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    with open(GOLDEN, "w", encoding="utf-8") as handle:
        json.dump(RECORDED, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(f"    recorded {len(SESSION_TRACE)} frames into {os.path.relpath(GOLDEN, HERE)}")

check("PW37 the recorded session is the session in the fixture - the frames a phone will be written against",
      GOLDEN.exists() and json.load(open(GOLDEN, encoding="utf-8")) == RECORDED,
      "run: python probe_phone_wire.py --record, read the file, commit it")

check("PW38 the index a client sends has exactly the six facts the host judges a file by",
      all(set(row) == set(protocol.INDEX_ENTRY_KEYS) for row in wire.library_index(PHONE_FOLDER))
      and len(wire.library_index(PHONE_FOLDER)) == 5,
      wire.library_index(PHONE_FOLDER)[:1])

HOST.stop()
shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)
check("PW39 every folder this suite wrote is gone again", not FIXTURE_ROOT.exists())

print(f"{CHECKS - len(FAILS)} / {CHECKS} checks passed")
if FAILS:
    print("FAILED: " + "; ".join(FAILS))
    raise SystemExit(1)







