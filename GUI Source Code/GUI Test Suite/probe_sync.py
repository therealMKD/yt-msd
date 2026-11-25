"""The sync-chain regression harness.

Sections SY-A..SY-S cover the sync half of `GUI Source Code/yt-msd-gui.pyw`: the TAG.yaml marker
a chain leaves on removable media and what comes back when it is read, the two forms `last_synced`
takes (an epoch in the chain dict, a wall-clock string in TAG.yaml) and the clock grace between
them, the drive scan that looks for tagged folders, sync-chain persistence inside the shared
gui_config.json, the length-prefixed socket protocol both ends of a chain speak, the host server's
answers to a client, the client worker's decisions about what to download and what to delete, the
number of files a client chain may delete before it has to ask the user and what keeping the host
interested during that question looks like, what a host is willing to say about a chain to somebody
who has not authenticated - which chains a beacon, a probe answer and a `HELLO` name, and what a
search across this machine's own networks makes of each answer - the removable-media worker and the
failsafe that stops a newer drive from being rolled back to an older copy, and the hosted folder
watcher's debounce, and the message a host puts on the network a moment after it comes up - what it
  is shaped like on the wire, which codes it may carry, and what a beacon does when it reads one.

Recipe (AI Readme section 20): same as probe_playback - the `.pyw` is copied to a throwaway `.py`
in this folder's `copy/` and imported, and the functions are driven directly. Every replacement
goes through harness_seam.py, never by writing into the entry point.

This suite does two things probe_playback does not, and both are bounded:

  - it opens sockets, but only on 127.0.0.1 - a listening socket bound to loopback, and connected
    pairs. No LAN address is bound and nothing is broadcast. LAN discovery is patched out through
    the seam so no check can put a packet on the network; the one check that drives the real search
    (SY-N36) lifts that patch for the length of the call and puts it straight back, and the search
    it runs is handed the addresses and ports written out in this file, with `adapter_addresses`
    stood in for, so what it searches is a loopback fixture and not this machine's network.
  - it writes files, but only fixture folders under `copy/sync_fixture/`, rebuilt at the start of
    every run and deleted again at the end. No check touches a real removable device, the app's
    own config folder, the music library, or the Windows startup registry.
"""
import ast
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import sys
import threading
import time

from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))              # .../GUI Source Code/GUI Test Suite
SRC = os.path.join(os.path.dirname(HERE), "yt-msd-gui.pyw")    # the master copy, one folder up
SRC_DIR = os.path.dirname(SRC)       # GUI Source Code, which now also holds the yt_msd package
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)      # the copy below imports that package, so it must be reachable
COPY_DIR = os.path.join(HERE, "copy")
os.makedirs(COPY_DIR, exist_ok=True)
TMP_PY = os.path.join(COPY_DIR, "yt_msd_sync_under_test.py")
shutil.copyfile(SRC, TMP_PY)
_spec = importlib.util.spec_from_file_location("yt_msd_sync_under_test", TMP_PY)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

# Everything this suite replaces goes through the seam, never by writing into the entry
# point. Writing there lands on a re-exported copy that nothing calls once a name has
# moved into yt_msd.*, and the check then passes while testing nothing.
import harness_seam as seam

seam.install(mod, SRC_DIR)

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


def wait_for(predicate, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


# ---------------------------------------------------------------------------
# Fixtures: everything this suite writes lives here, and goes away at the end
# ---------------------------------------------------------------------------
FIXTURE_ROOT = Path(COPY_DIR) / "sync_fixture"
shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)
FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)


def fixture(name):
    """A folder under the fixture root, always fresh."""
    folder = FIXTURE_ROOT / name
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def audio_file(folder, name, body=b"\xff\xfb\x90\x64 fake track", mtime=None):
    """A file with an audio suffix. Its contents are bytes rather than real audio, so
    read_metadata_tags() finds no tags in it - which is the sparse case the sync paths have
    to survive anyway."""
    folder.mkdir(parents=True, exist_ok=True)
    path = Path(folder) / name
    path.write_bytes(body)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def _loopback_pair():
    """A connected pair of sockets over loopback - the stand-in for one link of a chain.

    A listening socket bound to 127.0.0.1 on port 0 is what the Windows firewall leaves alone:
    an ephemeral loopback port is never filtered, and no address on the LAN is touched.
    """
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(listener.getsockname())
    server, _ = listener.accept()
    listener.close()
    client.settimeout(10.0)
    server.settimeout(10.0)
    return client, server


def _drain(sock, count, timeout=10.0):
    """Read exactly `count` bytes off a socket, with a deadline so a wrong answer fails
    in a check rather than hanging the run."""
    sock.settimeout(timeout)
    buf = bytearray()
    while len(buf) < count:
        chunk = sock.recv(count - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)


# ===========================================================================
# SY-A: the TAG.yaml marker - written onto media, read back off it
# ===========================================================================
TAG_FOLDER = fixture("tagged") / "chain" / "on the drive"
check("SY-A1 write_sync_tag_file() creates the folders it needs before writing into them",
      mod.write_sync_tag_file(TAG_FOLDER, "4821", chain_name="Drive Mix")
      and (TAG_FOLDER / "TAG.yaml").is_file())

TAG_DATA = mod.read_sync_tag_file(TAG_FOLDER)
check("SY-A2 the marker holds the chain's own fields, so a drive knows what it is",
      TAG_DATA is not None and TAG_DATA.get("sync_code") == "4821"
      and TAG_DATA.get("chain_name") == "Drive Mix", TAG_DATA)
check("SY-A3 the marker says who wrote it last and where the master folder lives",
      TAG_DATA.get("last_synced_by") == "Host" and TAG_DATA.get("parent_sync_folder") == "", TAG_DATA)
check("SY-A4 the marker carries a last_synced a drive can be compared against",
      mod.drive_last_synced_timestamp(TAG_FOLDER) is not None, TAG_DATA.get("last_synced"))

MIRROR = fixture("mirror")
ADDITIVE = fixture("additive")
mod.write_sync_tag_file(MIRROR, "1111", sync_style="Mirror")
mod.write_sync_tag_file(ADDITIVE, "2222", sync_style="Additive")
check("SY-A5 a Mirror chain reads back as mirror and an Additive one as additive",
      mod.read_sync_tag_file(MIRROR)["deletion_mode"] == "mirror"
      and mod.read_sync_tag_file(ADDITIVE)["deletion_mode"] == "additive",
      (mod.read_sync_tag_file(MIRROR), mod.read_sync_tag_file(ADDITIVE)))

PLACEHOLDER = fixture("placeholder")
mod.write_sync_tag_file(PLACEHOLDER, "XXXX")
check("SY-A6 a placeholder marker - the XXXX a template drive ships with - is not a chain",
      mod.read_sync_tag_file(PLACEHOLDER) is None)
check("SY-A7 a folder with no marker is not a sync folder, and neither is one that is not there",
      mod.read_sync_tag_file(fixture("no marker")) is None
      and mod.read_sync_tag_file(FIXTURE_ROOT / "never created") is None)

ALT = fixture("alt marker")
(ALT / "TAG.yml").write_text("sync_code: 7777\n", encoding="utf-8")
HIDDEN = fixture("alt hidden")
(HIDDEN / ".ytmsd_sync_tag").write_text("sync_code: 8888\n", encoding="utf-8")
check("SY-A8 the older and alternate marker names are still found",
      (mod.read_sync_tag_file(ALT) or {}).get("sync_code") == "7777"
      and (mod.read_sync_tag_file(HIDDEN) or {}).get("sync_code") == "8888")

SLOPPY = fixture("sloppy")
(SLOPPY / "TAG.yaml").write_text('Sync_Code: "5150"\nSYNC_STYLE: Additive\n\n# a note\n',
                                 encoding="utf-8")
SLOPPY_TAG = mod.read_sync_tag_file(SLOPPY)
check("SY-A9 field names are read case-insensitively and quotes are taken off the values",
      SLOPPY_TAG.get("sync_code") == "5150" and SLOPPY_TAG.get("deletion_mode") == "additive",
      SLOPPY_TAG)
check("SY-A10 comments and blank lines are never read as fields",
      not any(str(key).startswith("#") for key in SLOPPY_TAG) and "a note" not in SLOPPY_TAG,
      SLOPPY_TAG)
check("SY-A11 a marker that names no chain takes the name of the folder it sits in",
      SLOPPY_TAG.get("chain_name") == "sloppy", SLOPPY_TAG)

# ===========================================================================
# SY-B: the two forms of last_synced, and the grace between two clocks
# ===========================================================================
NOW = int(time.time())
check("SY-B1 an epoch number is already the form the chain dicts keep",
      mod.parse_sync_timestamp(NOW) == float(NOW))
check("SY-B2 an epoch written as text (older configs did this) is read as the same number",
      mod.parse_sync_timestamp(str(NOW)) == float(NOW))
check("SY-B3 a timestamp of zero or earlier is no timestamp",
      mod.parse_sync_timestamp(0) is None and mod.parse_sync_timestamp(-5) is None
      and mod.parse_sync_timestamp("0") is None)
check("SY-B4 a boolean is not a timestamp, however it got into the config",
      mod.parse_sync_timestamp(True) is None and mod.parse_sync_timestamp(False) is None)
check("SY-B5 nothing, an empty string and unparsable text all answer 'no timestamp'",
      mod.parse_sync_timestamp(None) is None and mod.parse_sync_timestamp("") is None
      and mod.parse_sync_timestamp("yesterday") is None
      and mod.parse_sync_timestamp("12/05/2026") is None)
check("SY-B6 the TAG.yaml wall-clock string is a form parse_sync_timestamp() accepts",
      mod.format_sync_timestamp(NOW) == time.strftime("%m-%d-%Y %H:%M:%S", time.localtime(NOW))
      and mod.parse_sync_timestamp(mod.format_sync_timestamp(NOW)) == float(NOW))
check("SY-B7 a marker written without seconds still parses",
      mod.parse_sync_timestamp("01-02-2026 03:04")
      == float(time.mktime(time.strptime("01-02-2026 03:04", "%m-%d-%Y %H:%M"))))
check("SY-B8 the two calendars agree: a timestamp survives the round trip through the readable form",
      mod.parse_sync_timestamp(mod.format_sync_timestamp(NOW - 7)) == float(NOW - 7))
check("SY-B9 a chain that has never synced is 'never', not a date",
      mod.format_sync_timestamp(None) == "never" and mod.format_sync_timestamp(0) == "never")
check("SY-B10 an impossible timestamp is reported as an unknown time instead of raising",
      mod.format_sync_timestamp(10 ** 12) == "an unknown time", mod.format_sync_timestamp(10 ** 12))
check("SY-B11 the grace between two machines' clocks is seconds, not minutes",
      0 < mod.SYNC_RETROGRADE_GRACE_SECONDS <= 300, mod.SYNC_RETROGRADE_GRACE_SECONDS)

DRIVE_NEWER = fixture("drive newer")
audio_file(DRIVE_NEWER, "track.mp3")
mod.write_sync_tag_file(DRIVE_NEWER, "4821")
(DRIVE_NEWER / "TAG.yaml").write_text(
    "sync_code: 4821\nchain_name: Drive Mix\nsync_style: Mirror\n"
    f"last_synced: {mod.format_sync_timestamp(NOW - 3600)}\n", encoding="utf-8")
check("SY-B12 a drive's own last_synced is read out of its marker as an epoch",
      mod.drive_last_synced_timestamp(DRIVE_NEWER) == float(NOW - 3600),
      mod.drive_last_synced_timestamp(DRIVE_NEWER))
check("SY-B13 a drive with no marker reports no timestamp rather than 'now'",
      mod.drive_last_synced_timestamp(fixture("bare drive")) is None)

# ===========================================================================
# SY-C: finding the chains already on a drive
# ===========================================================================
DRIVE = fixture("drive")
mod.write_sync_tag_file(DRIVE, "1001", chain_name="Root chain")
mod.write_sync_tag_file(DRIVE / "Sub Mix", "2002", chain_name="Sub Mix")
mod.write_sync_tag_file(DRIVE / "Deeper Mix" / "Nested Mix", "3003")
mod.write_sync_tag_file(DRIVE / "System Volume Information", "4004")
mod.write_sync_tag_file(DRIVE / ".git", "5005")
audio_file(DRIVE / "Plain Folder", "track.mp3")
ON_DRIVE = {str(folder): tag.get("sync_code")
            for folder, tag in mod.find_tagged_sync_folders_on_drive(str(DRIVE))}
check("SY-C1 a chain stored at the drive root is found", ON_DRIVE.get(str(DRIVE)) == "1001", ON_DRIVE)
check("SY-C2 a chain one folder down is found", ON_DRIVE.get(str(DRIVE / "Sub Mix")) == "2002", ON_DRIVE)
check("SY-C3 a chain two folders down is not: a chain is always a direct child of the drive root",
      str(DRIVE / "Deeper Mix") not in ON_DRIVE
      and str(DRIVE / "Deeper Mix" / "Nested Mix") not in ON_DRIVE, ON_DRIVE)
check("SY-C4 the folders Windows keeps on a drive are never offered as chains",
      not any("system volume information" in key.lower() or key.endswith(".git") for key in ON_DRIVE),
      ON_DRIVE)
check("SY-C5 a folder holding tracks but no marker is not a chain",
      "Plain Folder" not in ON_DRIVE, ON_DRIVE)
check("SY-C6 a drive that is not there answers with no chains rather than an error",
      mod.find_tagged_sync_folders_on_drive(str(FIXTURE_ROOT / "no such drive")) == [])

# ===========================================================================
# SY-D: the id a runtime removable chain gets
# ===========================================================================
RC_A = mod.make_removable_chain_id("4821", str(DRIVE / "Sub Mix"))
check("SY-D1 the id names the sync code it belongs to", RC_A.startswith("rc_4821_"), RC_A)
check("SY-D2 the same chain on the same folder always gets the same id",
      RC_A == mod.make_removable_chain_id("4821", str(DRIVE / "Sub Mix")))
check("SY-D3 the same sync code on two different drives is two different chains",
      RC_A != mod.make_removable_chain_id("4821", str(DRIVE / "Deeper Mix")))
check("SY-D4 the same drive under two sync codes is two different chains",
      RC_A != mod.make_removable_chain_id("2002", str(DRIVE / "Sub Mix")))

# ===========================================================================
# SY-E: sync-chain persistence, in the config file MainApp also writes
# ===========================================================================
CFG = fixture("config")
(CFG / "gui_config.json").write_text(json.dumps({"library_path": "M:/Music", "volume": 80}),
                                     encoding="utf-8")
CM = mod.SyncConfigManager(str(CFG))
check("SY-E1 a fresh install starts from the defaults the code names, not from a guess at them",
      CM.settings == dict(mod.DEFAULT_SYNC_SETTINGS) and CM.hosted_chains == []
      and CM.client_chains == [], CM.settings)
HC = CM.add_hosted_chain("Kitchen", str(fixture("hosted master")), notify_delay_mins=7)
SHARED = json.loads((CFG / "gui_config.json").read_text(encoding="utf-8"))
check("SY-E2 a hosted chain is saved under an id built from its sync code",
      HC["id"] == f"hc_{HC['sync_code']}" and HC["status"] == "Active"
      and HC["notify_delay_mins"] == 7 and HC["last_synced"] == 0, HC)
check("SY-E3 saving sync settings leaves the rest of the shared config file alone",
      SHARED.get("library_path") == "M:/Music" and SHARED.get("volume") == 80
      and len(SHARED.get("hosted_chains") or []) == 1, SHARED)
AGAIN = mod.SyncConfigManager(str(CFG))
check("SY-E4 the chains are read back the same way on the next run",
      [c["id"] for c in AGAIN.hosted_chains] == [HC["id"]] and AGAIN.settings == CM.settings,
      AGAIN.hosted_chains)

CFG_CODES = fixture("config codes")
CMC = mod.SyncConfigManager(str(CFG_CODES))
CODES = [CMC.add_hosted_chain(f"Chain {n}", str(fixture(f"master {n}")))["sync_code"]
         for n in range(12)]
check("SY-E5 every sync code is four digits, and twelve hosted chains never share one",
      all(code.isdigit() and len(code) == 4 for code in CODES) and len(set(CODES)) == len(CODES),
      CODES)

CC = CM.add_client_chain("Studio", str(fixture("client copy")), "8899", "127.0.0.1",
                         host_port=63350, bound_wifi_ssid="HomeNet")
check("SY-E6 a client chain is created ready to find its host, holding what it remembers of it",
      CC["id"] == "cc_8899" and CC["last_known_host_ip"] == "127.0.0.1"
      and CC["paused_until"] == 0 and CC["status"] == "Pending Sync", CC)
check("SY-E7 a Wi-Fi binding is stored under exactly the name every reader asks for",
      CC.get("wifi_ssid") == "HomeNet" and "bound_wifi_ssid" not in CC, CC)
CM.pause_client_chain(CC["id"], -1)
check("SY-E8 pausing forever is -1, and the pause gate reads it as paused",
      mod.is_client_chain_paused(CC) == (True, -1), CC.get("paused_until"))
CM.pause_client_chain(CC["id"], 3600)
check("SY-E9 a timed pause is a point in the future the chain is held until",
      mod.is_client_chain_paused(CC)[0] is True and CC["paused_until"] > time.time(),
      CC.get("paused_until"))
CC["paused_until"] = int(time.time()) - 5
check("SY-E10 a pause whose time has passed is over, and the chain is left clean for the next pass",
      mod.is_client_chain_paused(CC) == (False, 0) and CC["paused_until"] == 0, CC)
CM.resume_client_chain(CC["id"])
check("SY-E11 resuming clears the pause and saves the clearing",
      mod.is_client_chain_paused(CC) == (False, 0)
      and json.loads((CFG / "gui_config.json").read_text(encoding="utf-8"))["client_chains"][0]["paused_until"] == 0)
CM.bind_client_wifi(CC["id"], "Cafe Net 5G")
check("SY-E12 binding a chain to a network replaces the binding instead of adding a second one",
      CC["wifi_ssid"] == "Cafe Net 5G" and "bound_wifi_ssid" not in CC, CC)
CM.remove_chain(HC["id"])
check("SY-E13 removing a chain takes it out of both lists it could be in",
      CM.hosted_chains == [] and len(CM.client_chains) == 1, CM.hosted_chains)

MIG = fixture("config migration")
(MIG / "gui_config.json").write_text(json.dumps({"client_chains": [
    {"id": "cc_3333", "sync_code": "3333", "bound_wifi_ssid": "HomeNet"}]}), encoding="utf-8")
MIG_CM = mod.SyncConfigManager(str(MIG))
check("SY-E14 a binding an older build wrote under the stray name is folded onto the name readers use",
      MIG_CM.client_chains[0].get("wifi_ssid") == "HomeNet"
      and "bound_wifi_ssid" not in MIG_CM.client_chains[0], MIG_CM.client_chains[0])
check("SY-E15 the fold is written back, so it is fixed for every later run too",
      json.loads((MIG / "gui_config.json").read_text(encoding="utf-8"))["client_chains"][0]["wifi_ssid"]
      == "HomeNet")

LEGACY = fixture("config legacy")
(LEGACY / "sync_config.json").write_text(json.dumps({
    "settings": {"auto_sync_interval_mins": 15, "firewall_prompted": True},
    "hosted_chains": [{"id": "hc_7777", "sync_code": "7777"}], "client_chains": []}), encoding="utf-8")
LEGACY_CM = mod.SyncConfigManager(str(LEGACY))
check("SY-E16 the old separate sync config file is migrated into the shared one",
      LEGACY_CM.settings["auto_sync_interval_mins"] == 15
      and [c["id"] for c in LEGACY_CM.hosted_chains] == ["hc_7777"], LEGACY_CM.settings)
check("SY-E17 and it is removed afterwards, so it cannot migrate itself twice",
      not (LEGACY / "sync_config.json").exists()
      and "hosted_chains" in json.loads((LEGACY / "gui_config.json").read_text(encoding="utf-8")))

# ===========================================================================
# SY-F: the primitives every chain link is built out of
# ===========================================================================
CLIENT_S, SERVER_S = _loopback_pair()
mod.send_json_msg(CLIENT_S, {"cmd": "AUTH", "sync_code": "4821"})
mod.send_json_msg(CLIENT_S, {"cmd": "PING"})
check("SY-F1 a message is length-prefixed, so the far end knows where one ends and the next starts",
      mod.recv_json_msg(SERVER_S) == {"cmd": "AUTH", "sync_code": "4821"}
      and mod.recv_json_msg(SERVER_S) == {"cmd": "PING"})
CLIENT_S.close()
SERVER_S.close()

CLIENT_S, SERVER_S = _loopback_pair()
CLIENT_S.sendall(b"abc")
CLIENT_S.close()
check("SY-F2 a message that never finishes is read as no message, not as a partial one",
      mod._recv_all(SERVER_S, 10) is None and mod.recv_json_msg(SERVER_S) is None)
SERVER_S.close()

SOURCE_FILE = audio_file(fixture("transfer source"), "one.mp3", body=b"A" * 5000)
CLIENT_S, SERVER_S = _loopback_pair()
SENT_SHA = mod.stream_file_to_socket(CLIENT_S, SOURCE_FILE)
RECEIVED = fixture("transfer dest") / "one.mp3"
RECEIVED_OK = mod.recv_file_from_socket(SERVER_S, RECEIVED, SOURCE_FILE.stat().st_size, SENT_SHA)
CLIENT_S.close()
SERVER_S.close()
check("SY-F3 the hash the sender reports is the hash the file alone gives - both ends agree without a second pass",
      SENT_SHA == mod.compute_file_sha256(SOURCE_FILE)
      == hashlib.sha256(SOURCE_FILE.read_bytes()).hexdigest())
check("SY-F4 the received file appears only once every byte of it has arrived and hashed correctly",
      RECEIVED_OK is True and RECEIVED.read_bytes() == SOURCE_FILE.read_bytes()
      and not list(RECEIVED.parent.glob("*.tmp_sync")), list(RECEIVED.parent.iterdir()))

CLIENT_S, SERVER_S = _loopback_pair()
mod.stream_file_to_socket(CLIENT_S, SOURCE_FILE)
BAD_TARGET = fixture("transfer bad") / "one.mp3"
check("SY-F5 a file that does not hash to what was promised is thrown away, not renamed into place",
      mod.recv_file_from_socket(SERVER_S, BAD_TARGET, SOURCE_FILE.stat().st_size, "0" * 64) is False
      and not BAD_TARGET.exists() and not list(BAD_TARGET.parent.glob("*.tmp_sync")),
      list(BAD_TARGET.parent.iterdir()))
CLIENT_S.close()
SERVER_S.close()

CLIENT_S, SERVER_S = _loopback_pair()
CLIENT_S.sendall(b"only a part of a file")
CLIENT_S.close()
PARTIAL_TARGET = fixture("transfer partial") / "one.mp3"
check("SY-F6 a link that dies mid-file leaves no half-written track behind",
      mod.recv_file_from_socket(SERVER_S, PARTIAL_TARGET, 5000, SENT_SHA) is False
      and not PARTIAL_TARGET.exists() and not list(PARTIAL_TARGET.parent.glob("*.tmp_sync")),
      list(PARTIAL_TARGET.parent.iterdir()))
SERVER_S.close()

AUDIO_MIX = fixture("audio filter")
audio_file(AUDIO_MIX, "beta.mp3")
audio_file(AUDIO_MIX, "Alpha.mp3")
audio_file(AUDIO_MIX, "track.flac")
audio_file(AUDIO_MIX, "notes.txt")
audio_file(AUDIO_MIX / "zeta", "nested.mp3")
check("SY-F7 a chain folder is read one level deep, keeps only audio suffixes, and sorts by name regardless of case",
      [p.name for p in mod.filter_audio_files(AUDIO_MIX)] == ["Alpha.mp3", "beta.mp3", "track.flac"],
      [p.name for p in mod.filter_audio_files(AUDIO_MIX)])
check("SY-F8 a folder that is not there has no tracks in it",
      mod.filter_audio_files(AUDIO_MIX / "not here") == [])
check("SY-F9 the sync layer works on the same set of audio suffixes as the rest of the program",
      {".mp3", ".flac"} <= mod.AUDIO_EXTENSIONS and ".txt" not in mod.AUDIO_EXTENSIONS)

LOCK_A = mod.get_drive_io_lock(fixture("lock a"))
LOCK_B = mod.get_drive_io_lock(fixture("lock b"))
check("SY-F10 one device is worked over by one sync at a time: every folder on a drive shares its lock",
      LOCK_A is LOCK_B and mod.get_drive_io_lock(str(DRIVE)) is LOCK_A)
_nested_lock = []


def _take_the_lock_twice():
    LOCK_A.acquire()
    LOCK_A.acquire()          # the case that actually happens: a USB chain syncing a folder on the same device
    _nested_lock.append("held twice")
    LOCK_A.release()
    LOCK_A.release()


_nested_thread = threading.Thread(target=_take_the_lock_twice, daemon=True)
_nested_thread.start()
_nested_thread.join(5)
check("SY-F11 the drive lock is reentrant, so a chain that touches its own device does not deadlock itself",
      _nested_lock == ["held twice"] and not _nested_thread.is_alive(), _nested_lock)

_emitted_progress = []
_throttled = mod.make_throttled_progress_cb(
    lambda *args: _emitted_progress.append(args), min_interval=30.0)
for _step in range(51):
    _throttled(_step, 50, "track.mp3", 1, 50)
check("SY-F12 progress is coalesced, so a fast sync cannot flood the GUI queue - and the last one is always sent",
      [entry[0] for entry in _emitted_progress] == [0, 50], _emitted_progress)
check("SY-F13 a sync with nobody to report progress to still runs",
      mod.make_throttled_progress_cb(None) is None)

# ===========================================================================
# SY-G: what the host answers, face to face
# ===========================================================================
HOST_CHAIN_FOLDER = fixture("host chain")
audio_file(HOST_CHAIN_FOLDER, "one.mp3", body=b"the first track")
audio_file(HOST_CHAIN_FOLDER, "two.mp3", body=b"the second track, a bit longer")
(HOST_CHAIN_FOLDER / "notes.txt").write_text("not a track", encoding="utf-8")

HOST_ACTIVITY = []
HOST_SERVER = mod.SyncHostServer(
    lambda: [{"sync_code": "4821", "name": "Kitchen", "folder_path": str(HOST_CHAIN_FOLDER)}],
    on_client_activity_cb=lambda code, ip, note: HOST_ACTIVITY.append((code, note)))
# start() is what normally sets this, and start() is the one thing this suite refuses to do:
# binding SYNC_PORT_START..END could collide with a yt-msd that is genuinely running. The client
# handler itself is driven over a connected loopback pair instead.
HOST_SERVER._running = True


def _host_round(requests, expecting):
    """Send these commands to the host's own handler and read back the answers it gives."""
    client, server = _loopback_pair()
    worker = threading.Thread(target=lambda: HOST_SERVER._handle_client(server, "127.0.0.1"),
                              daemon=True)
    worker.start()
    for message in requests:
        mod.send_json_msg(client, message)
    answers = [mod.recv_json_msg(client, timeout=8.0) for _ in range(expecting)]
    client.close()
    worker.join(8)
    try:
        server.close()
    except Exception:
        pass
    return answers


answers = _host_round([{"cmd": "GET_INDEX"}], 1)
check("SY-G1 a client that does not open with AUTH is turned away before it is told anything",
      answers[0] == {"status": "ERROR", "reason": "Expected AUTH command"}, answers)

answers = _host_round([{"cmd": "AUTH", "sync_code": "9999"}], 1)
check("SY-G2 a sync code this machine does not host is refused by name",
      answers[0].get("status") == "ERROR" and "9999" in answers[0].get("reason", ""), answers)

answers = _host_round([{"cmd": "AUTH", "sync_code": "4821"}, {"cmd": "PING"}], 2)
check("SY-G3 a hosted chain answers with its name and how many tracks it holds",
      answers[0] == {"status": "OK", "chain_name": "Kitchen", "files_count": 2}, answers)
check("SY-G4 a hosted chain stays reachable between commands", answers[1] == {"status": "PONG"}, answers)

answers = _host_round([{"cmd": "AUTH", "sync_code": "4821"}, {"cmd": "GET_INDEX"}], 2)
INDEX = answers[1].get("files") or []
check("SY-G5 the index names every track, and says nothing about the non-audio files sitting among them",
      answers[1].get("status") == "OK" and [entry["name"] for entry in INDEX] == ["one.mp3", "two.mp3"],
      INDEX)
check("SY-G6 every index entry carries the size, mtime and hash the client will judge the file by",
      all(entry["size"] == (HOST_CHAIN_FOLDER / entry["name"]).stat().st_size
          and abs(entry["mtime"] - (HOST_CHAIN_FOLDER / entry["name"]).stat().st_mtime) < 1.0
          and entry["sha256"] == mod.compute_file_sha256(HOST_CHAIN_FOLDER / entry["name"])
          for entry in INDEX), INDEX)
check("SY-G7 a track with no tags in it is indexed as having no artist and no title, not left out",
      all("artist" in entry and "title" in entry for entry in INDEX), INDEX)

answers = _host_round([{"cmd": "AUTH", "sync_code": "4821"}, {"cmd": "PULL_FILE", "filename": "notes.txt"}], 2)
check("SY-G8 the host will not hand over a file that is not a track",
      answers[1].get("status") == "ERROR" and "audio" in answers[1].get("reason", ""), answers)

answers = _host_round([{"cmd": "AUTH", "sync_code": "4821"}, {"cmd": "NONSENSE"}], 2)
check("SY-G9 a command the host does not know is answered as an error rather than ignored",
      answers[1].get("status") == "ERROR" and "NONSENSE" in answers[1].get("reason", ""), answers)

_client, _server = _loopback_pair()
_pull_worker = threading.Thread(target=lambda: HOST_SERVER._handle_client(_server, "192.168.1.7"),
                                daemon=True)
_pull_worker.start()
mod.send_json_msg(_client, {"cmd": "AUTH", "sync_code": "4821"})
mod.send_json_msg(_client, {"cmd": "PULL_FILE", "filename": "two.mp3"})
mod.recv_json_msg(_client, timeout=8.0)                                    # the AUTH answer
sending = mod.recv_json_msg(_client, timeout=8.0)                          # what it is about to send
pulled = _drain(_client, sending["filesize"])
check("SY-G10 a pull announces the size and hash first, then sends exactly that file",
      sending.get("status") == "SENDING" and sending["filename"] == "two.mp3"
      and len(pulled) == sending["filesize"]
      and hashlib.sha256(pulled).hexdigest() == sending["sha256"], sending)
_client.close()
_pull_worker.join(8)
_server.close()

check("SY-G11 the host records what its clients did, which is what the sync window shows as activity",
      HOST_ACTIVITY.count(("4821", "Connected")) >= 1
      and any(note.startswith("Sending two.mp3") for _code, note in HOST_ACTIVITY), HOST_ACTIVITY)

GONE = mod.SyncHostServer(
    lambda: [{"sync_code": "1111", "name": "Gone", "folder_path": str(FIXTURE_ROOT / "deleted folder")}])
GONE._running = True
_client, _server = _loopback_pair()
_gone_worker = threading.Thread(target=lambda: GONE._handle_client(_server, "127.0.0.1"), daemon=True)
_gone_worker.start()
mod.send_json_msg(_client, {"cmd": "AUTH", "sync_code": "1111"})
gone_answer = mod.recv_json_msg(_client, timeout=8.0)
_client.close()
_gone_worker.join(8)
_server.close()
check("SY-G12 a hosted chain whose folder has been deleted says so instead of serving nothing",
      gone_answer.get("status") == "ERROR" and "does not exist on disk" in gone_answer.get("reason", ""),
      gone_answer)

# ===========================================================================
# SY-H: the client half - what it downloads, what it deletes, what it leaves alone
# ===========================================================================
# The machine's own address and LAN discovery are replaced through the seam: "the host is
# unreachable" has to be a fact this suite controls rather than a fact about the machine this
# runs on, and no check may put a broadcast probe on the network.
_local_loopback = lambda: "127.0.0.1"
_no_host_on_lan = lambda sync_code=None, timeout=2.5: None
seam.patch("get_local_ip", _local_loopback)
seam.patch("discover_host_on_lan", _no_host_on_lan)
check("SY-H0 the injection lands on every module holding the name - including the one that makes the call, and no longer the entry point alone",
      all(getattr(module, "discover_host_on_lan") is _no_host_on_lan
          for module in seam.owners("discover_host_on_lan"))
      and any(module.__name__ != mod.__name__ for module in seam.owners("discover_host_on_lan")),
      [module.__name__ for module in seam.owners("discover_host_on_lan")])


class _FakeHost:
    """One end of a chain: a host that speaks the protocol, listening on loopback only."""

    def __init__(self, folder, sync_code="8899", serve=True):
        self.folder = Path(folder)
        self.sync_code = sync_code
        self.serve = serve
        self.commands = []
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]
        self.thread = threading.Thread(target=self._accept, daemon=True)
        self.thread.start()

    def _accept(self):
        while True:
            try:
                sock, _addr = self.listener.accept()
            except OSError:
                return
            sock.settimeout(15.0)
            try:
                self._handle(sock)
            except Exception:
                pass
            finally:
                try:
                    sock.close()
                except Exception:
                    pass

    def _handle(self, sock):
        auth = mod.recv_json_msg(sock, timeout=15.0)
        self.commands.append(auth.get("cmd") if auth else None)
        if not auth or auth.get("cmd") != "AUTH" or not self.serve:
            mod.send_json_msg(sock, {"status": "ERROR",
                                     "reason": f"Sync code {self.sync_code} not found on host"})
            return
        mod.send_json_msg(sock, {"status": "OK", "chain_name": "Remote Mix",
                                 "files_count": len(mod.filter_audio_files(self.folder))})
        while True:
            request = mod.recv_json_msg(sock, timeout=15.0)
            if not request:
                return
            self.commands.append(request.get("cmd"))
            if request.get("cmd") == "GET_INDEX":
                mod.send_json_msg(sock, {"status": "OK", "files": [
                    {"name": held.name, "size": held.stat().st_size, "mtime": held.stat().st_mtime,
                     "sha256": mod.compute_file_sha256(held), "artist": None, "title": None}
                    for held in mod.filter_audio_files(self.folder)]})
            elif request.get("cmd") == "PULL_FILE":
                target = self.folder / request.get("filename", "")
                mod.send_json_msg(sock, {"status": "SENDING", "filename": target.name,
                                         "filesize": target.stat().st_size,
                                         "sha256": mod.compute_file_sha256(target)})
                mod.stream_file_to_socket(sock, target)

    def stop(self):
        try:
            self.listener.close()
        except Exception:
            pass


def _closed_port():
    """A port number with nothing listening on it."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def _client_chain(dest, port, deletion_mode="mirror", last_synced=0):
    return {"id": "cc_8899", "sync_code": "8899", "name": "Studio", "folder_path": str(dest),
            "last_known_host_ip": "127.0.0.1", "host_port": port, "deletion_mode": deletion_mode,
            "paused_until": 0, "wifi_ssid": "", "created_at": 0, "last_synced": last_synced,
            "status": "Pending Sync"}


HOST_MIX = fixture("client host mix")
audio_file(HOST_MIX, "one.mp3", body=b"first track")
audio_file(HOST_MIX, "two.mp3", body=b"second track")
HOST = _FakeHost(HOST_MIX)

ok, message, moved, removed = mod.SyncClientWorker.sync_chain(
    _client_chain(fixture("client dead dest"), _closed_port()))
check("SY-H1 a client that cannot reach its host and cannot find one says so instead of pretending",
      ok is False and moved == 0 and removed == 0 and "Could not find active host" in message, message)

REFUSING = _FakeHost(HOST_MIX, serve=False)
ok, message, moved, removed = mod.SyncClientWorker.sync_chain(
    _client_chain(fixture("client refused"), REFUSING.port))
check("SY-H2 a host that does not know this sync code is reported by the reason it gave",
      ok is False and "not found on host" in message, message)
REFUSING.stop()

DEST = fixture("client dest")
ok, message, moved, removed = mod.SyncClientWorker.sync_chain(_client_chain(DEST, HOST.port))
check("SY-H3 a first sync pulls every track the host offers",
      ok is True and moved == 2 and removed == 0
      and sorted(p.name for p in DEST.iterdir()) == ["one.mp3", "two.mp3"], (ok, message, moved, removed))
check("SY-H4 what arrived is byte for byte what the host held",
      (DEST / "one.mp3").read_bytes() == (HOST_MIX / "one.mp3").read_bytes()
      and (DEST / "two.mp3").read_bytes() == (HOST_MIX / "two.mp3").read_bytes())
check("SY-H5 nothing is left half-received behind", not list(DEST.glob("*.tmp_sync")), list(DEST.iterdir()))
check("SY-H6 the copy keeps the date the host's file had, so the next pass can tell an update from a copy",
      abs((DEST / "one.mp3").stat().st_mtime - (HOST_MIX / "one.mp3").stat().st_mtime) < 2.0)
check("SY-H7 the client asked the host exactly what a client asks: who are you, what have you got, then each file",
      HOST.commands == ["AUTH", "GET_INDEX", "PULL_FILE", "PULL_FILE"], HOST.commands)

ok, message, moved, removed = mod.SyncClientWorker.sync_chain(_client_chain(DEST, HOST.port))
check("SY-H8 a second sync of an identical copy transfers nothing - the file's own hash decides, not the clock",
      ok is True and moved == 0 and removed == 0, (ok, message, moved, removed))

audio_file(DEST, "leftover.mp3", body=b"only mine")
ok, message, moved, removed = mod.SyncClientWorker.sync_chain(_client_chain(DEST, HOST.port))
check("SY-H9 a Mirror chain deletes the track the host has stopped offering",
      ok is True and removed == 1 and not (DEST / "leftover.mp3").exists(), (ok, message, removed))

audio_file(DEST, "leftover.mp3", body=b"only mine")
ok, message, moved, removed = mod.SyncClientWorker.sync_chain(
    _client_chain(DEST, HOST.port, deletion_mode="additive"))
check("SY-H10 an Additive chain keeps a track the host no longer has",
      ok is True and removed == 0 and (DEST / "leftover.mp3").exists(), (ok, message, removed))

(DEST / "one.mp3").write_bytes(b"a longer and different version of the track")
ok, message, moved, removed = mod.SyncClientWorker.sync_chain(_client_chain(DEST, HOST.port))
check("SY-H11 a local track that is not the host's is re-pulled rather than trusted",
      ok is True and moved >= 1
      and (DEST / "one.mp3").read_bytes() == (HOST_MIX / "one.mp3").read_bytes(), (ok, message, moved))

NEW_DEST = fixture("client brand new") / "not made yet"
ok, message, moved, removed = mod.SyncClientWorker.sync_chain(_client_chain(NEW_DEST, HOST.port))
check("SY-H12 a client folder that does not exist yet is made before anything is written into it",
      ok is True and (NEW_DEST / "one.mp3").is_file(), message)

PROGRESS_SEEN = []
ok, message, moved, removed = mod.SyncClientWorker.sync_chain(
    _client_chain(fixture("client progress"), HOST.port), status_cb=lambda text: PROGRESS_SEEN.append(text))
check("SY-H13 the client says what it is doing while it is doing it",
      any("Connecting to host" in text for text in PROGRESS_SEEN)
      and any("Fetching file index" in text for text in PROGRESS_SEEN)
      and any(text.startswith("Downloading [") for text in PROGRESS_SEEN), PROGRESS_SEEN)
HOST.stop()

# ===========================================================================
# SY-I: the removable half - putting a chain onto a stick
# ===========================================================================
MASTER = fixture("removable master")
audio_file(MASTER, "one.mp3", body=b"master one")
audio_file(MASTER, "two.mp3", body=b"master two")
STICK = fixture("removable stick")

ok, message, moved, removed = mod.SyncRemovableWorker.sync_local_folders(MASTER, STICK)
check("SY-I1 a stick starts out holding the chain it is synced to",
      ok is True and moved == 2 and removed == 0
      and (STICK / "one.mp3").read_bytes() == b"master one", (ok, message, moved, removed))
ok, message, moved, removed = mod.SyncRemovableWorker.sync_local_folders(MASTER, STICK)
check("SY-I2 a stick that already matches the master is left alone",
      ok is True and moved == 0 and removed == 0, (ok, message, moved, removed))

audio_file(STICK, "orphan.mp3", body=b"from an older chain")
ok, message, moved, removed = mod.SyncRemovableWorker.sync_local_folders(MASTER, STICK)
check("SY-I3 Mirror mode takes off the stick the track the chain no longer has",
      removed == 1 and not (STICK / "orphan.mp3").exists(), (ok, message, removed))

audio_file(STICK, "orphan.mp3", body=b"from an older chain")
ok, message, moved, removed = mod.SyncRemovableWorker.sync_local_folders(MASTER, STICK,
                                                                         deletion_mode="additive")
check("SY-I4 Additive mode leaves it there",
      removed == 0 and (STICK / "orphan.mp3").exists(), (ok, message, removed))

_touch = time.time() + 60
os.utime(MASTER / "one.mp3", (_touch, _touch))
(STICK / "one.mp3").write_bytes(b"an older copy of it")
ok, message, moved, removed = mod.SyncRemovableWorker.sync_local_folders(MASTER, STICK)
check("SY-I5 a master track touched since the stick was written is copied over the stick's copy",
      moved >= 1 and (STICK / "one.mp3").read_bytes() == b"master one", (ok, message, moved))

ok, message, moved, removed = mod.SyncRemovableWorker.sync_local_folders(MASTER / "gone master", STICK)
check("SY-I6 a master folder that has gone is reported as a problem, not as a sync of nothing",
      ok is False and "does not exist" in message and moved == 0, message)

ok, message, moved, removed = mod.SyncRemovableWorker.sync_local_folders(MASTER,
                                                                          STICK / "stick not made yet")
check("SY-I7 the device folder is made before anything is written into it",
      ok is True and (STICK / "stick not made yet" / "one.mp3").is_file(), message)

# ===========================================================================
# SY-J: the failsafe - a newer drive is not rolled back to an older copy
# ===========================================================================
RC_CM = mod.SyncConfigManager(str(fixture("config removable")))
RC_MASTER = fixture("rc master")
audio_file(RC_MASTER, "one.mp3", body=b"host one")
RC_STICK = fixture("rc stick")


def _removable(config_manager, sync_code, stick, confirm_cb=None, name="Chain"):
    return mod.SyncRemovableWorker.sync_removable_chain(
        {"sync_code": sync_code, "folder_path": str(stick), "deletion_mode": "mirror", "name": name},
        config_manager, confirm_cb=confirm_cb)


HOST_RC = RC_CM.add_hosted_chain("Host Mix", str(RC_MASTER))
ok, message, moved, removed = _removable(RC_CM, HOST_RC["sync_code"], RC_STICK, name="Host Mix")
check("SY-J1 a hosted chain writes its tracks onto the stick and leaves a marker naming where they came from",
      ok is True and moved == 1 and (RC_STICK / "TAG.yaml").is_file()
      and mod.read_sync_tag_file(RC_STICK).get("last_synced_by") == "Host"
      and mod.read_sync_tag_file(RC_STICK).get("parent_sync_folder") == str(RC_MASTER), (ok, message))
check("SY-J2 the marker it leaves carries the stick's own last_synced, which is what a later drive is compared against",
      mod.drive_last_synced_timestamp(RC_STICK) is not None)

RC_CLIENT_FOLDER = fixture("rc client copy")
audio_file(RC_CLIENT_FOLDER, "one.mp3", body=b"client one")
CLIENT_RC = RC_CM.add_client_chain("Client Mix", str(RC_CLIENT_FOLDER), "6677", "127.0.0.1",
                                   host_port=_closed_port())
check("SY-J3 a sync code with neither a hosted nor a client chain behind it is refused by name",
      _removable(RC_CM, "9999", fixture("rc nowhere"))[1].startswith("No hosted or client sync chain"),
      _removable(RC_CM, "9999", fixture("rc nowhere"))[1])


def _drive_holding_a_newer_copy(name):
    """A stick with a track on it and a marker saying it was synced just now."""
    stick = fixture(name)
    audio_file(stick, "on the drive.mp3", body=b"newer than this PC")
    mod.write_sync_tag_file(stick, "6677")
    return stick


RETR_STICK = _drive_holding_a_newer_copy("rc retrograde stick")
CLIENT_RC["last_synced"] = 0
ok, message, moved, removed = _removable(RC_CM, "6677", RETR_STICK, name="Client Mix")
check("SY-J4 a stick holding a newer version, with the host out of reach, is not overwritten by an older copy",
      ok is False and "Sync skipped" in message and (moved, removed) == (0, 0)
      and (RETR_STICK / "on the drive.mp3").exists(), message)

_asked = []
RETR_STICK2 = _drive_holding_a_newer_copy("rc asked stick")
CLIENT_RC["last_synced"] = 0
ok, message, moved, removed = _removable(RC_CM, "6677", RETR_STICK2,
                                         confirm_cb=lambda q: _asked.append(q) or False, name="Client Mix")
check("SY-J5 the listener is asked, in words that name both copies and when each was last synced",
      len(_asked) == 1 and "with an older one" in _asked[0] and "Drive last synced:" in _asked[0]
      and "This PC last synced: never" in _asked[0], _asked)
check("SY-J6 a listener who says no keeps their drive exactly as it was",
      ok is False and (RETR_STICK2 / "on the drive.mp3").exists()
      and not (RETR_STICK2 / "one.mp3").exists(), (ok, message))

RETR_STICK3 = _drive_holding_a_newer_copy("rc agreed stick")
CLIENT_RC["last_synced"] = 0
ok, message, moved, removed = _removable(RC_CM, "6677", RETR_STICK3,
                                         confirm_cb=lambda q: True, name="Client Mix")
check("SY-J7 and the older copy is written only once the listener has agreed to it",
      ok is True and (RETR_STICK3 / "one.mp3").is_file()
      and not (RETR_STICK3 / "on the drive.mp3").exists()
      and mod.read_sync_tag_file(RETR_STICK3).get("last_synced_by") == "Client", (ok, message))

FRESH_STICK = _drive_holding_a_newer_copy("rc fresh stick")
CLIENT_RC["last_synced"] = time.time()
_asked[:] = []
ok, message, moved, removed = _removable(RC_CM, "6677", FRESH_STICK,
                                         confirm_cb=lambda q: _asked.append(q) or True, name="Client Mix")
check("SY-J8 a PC whose copy is not older than the drive writes it without asking anything",
      _asked == [] and ok is True and (FRESH_STICK / "one.mp3").is_file(), (ok, message, _asked))

DRIFT_STICK = fixture("rc drift stick")
audio_file(DRIFT_STICK, "on the drive.mp3", body=b"a minute ahead at most")
(DRIFT_STICK / "TAG.yaml").write_text(
    "sync_code: 6677\nsync_style: Mirror\n"
    f"last_synced: {mod.format_sync_timestamp(time.time() + 30)}\n", encoding="utf-8")
CLIENT_RC["last_synced"] = time.time()
_asked[:] = []
ok, message, moved, removed = _removable(RC_CM, "6677", DRIFT_STICK,
                                         confirm_cb=lambda q: _asked.append(q) or True, name="Client Mix")
check("SY-J9 a drive that only looks a minute ahead is clock drift, and is not treated as a newer chain",
      _asked == [] and ok is True, (ok, message, _asked))

EMPTY_STICK = fixture("rc empty stick")
mod.write_sync_tag_file(EMPTY_STICK, "6677")
CLIENT_RC["last_synced"] = 0
_asked[:] = []
ok, message, moved, removed = _removable(RC_CM, "6677", EMPTY_STICK,
                                         confirm_cb=lambda q: _asked.append(q) or True, name="Client Mix")
check("SY-J10 a drive with nothing on it has nothing to lose, so it is written without a question",
      _asked == [] and ok is True and (EMPTY_STICK / "one.mp3").is_file(), (ok, message, _asked))

STAMP_CFG = fixture("config stamp")
STAMP_CM = mod.SyncConfigManager(str(STAMP_CFG))
STAMP_MIX = fixture("stamp host mix")
audio_file(STAMP_MIX, "one.mp3", body=b"straight off the host")
STAMP_HOST = _FakeHost(STAMP_MIX)
STAMP_CLIENT = STAMP_CM.add_client_chain("Stamp Mix", str(fixture("rc stamp copy")), "7007",
                                         "127.0.0.1", host_port=STAMP_HOST.port)
STAMP_CLIENT["last_synced"] = 0
ok, message, moved, removed = _removable(STAMP_CM, "7007", fixture("rc stamp stick"), name="Stamp Mix")
check("SY-J11 a client copy that genuinely just came off the host is stamped as such, so the next plug-in does not ask the same question",
      ok is True and STAMP_CLIENT["last_synced"] > time.time() - 60
      and json.loads(Path(STAMP_CM.config_file).read_text(encoding="utf-8"))["client_chains"][0]["last_synced"] > 0,
      (ok, message, STAMP_CLIENT["last_synced"]))
STAMP_HOST.stop()

# ===========================================================================
# SY-K: the watcher a hosted chain runs over its own folder
# ===========================================================================
WATCHED_FOLDER = fixture("watched chain folder")
audio_file(WATCHED_FOLDER, "one.mp3")
WATCH_FIRED = []
WATCHER = mod.HostFolderWatcher(lambda sync_code: WATCH_FIRED.append(sync_code))


def _watch_the_same_chain_twice():
    WATCHER.add_or_update_chain("hc_4821", str(WATCHED_FOLDER), "4821", delay_mins=5)
    WATCHER.add_or_update_chain("hc_4821", str(WATCHED_FOLDER), "4821", delay_mins=5)
    WATCHER.stop_all()


_watch_thread = threading.Thread(target=_watch_the_same_chain_twice, daemon=True)
_watch_thread.start()
_watch_thread.join(10)
check("SY-K1 watching a chain, then refreshing the same chain, does not strand the thread that did it",
      not _watch_thread.is_alive(), "the watcher lock is reentrant for a reason")
check("SY-K2 stopping the watchers leaves nothing watched", WATCHER.watched_chains == {},
      WATCHER.watched_chains)
WATCHER.add_or_update_chain("hc_0000", str(FIXTURE_ROOT / "no such folder"), "0000")
check("SY-K3 a chain whose folder is gone is left unwatched rather than watched and failing",
      WATCHER.watched_chains == {}, WATCHER.watched_chains)

WATCHER.watched_chains["hc_1111"] = {"folder_path": str(WATCHED_FOLDER), "sync_code": "1111",
                                     "delay_sec": 0.2, "timer": None, "observer": None}
WATCHER._trigger_debounce("hc_1111")
WATCHER._trigger_debounce("hc_1111")
_fired = wait_for(lambda: bool(WATCH_FIRED), timeout=5.0)
time.sleep(0.5)
check("SY-K4 a change in a watched folder is reported once, not once per file that moved",
      _fired and WATCH_FIRED == ["1111"], WATCH_FIRED)
WATCHER._trigger_debounce("hc nobody")
check("SY-K5 a change in a chain nobody watches is not a notification", WATCH_FIRED == ["1111"],
      WATCH_FIRED)
WATCHER.stop_all()

# ===========================================================================
# SY-M: the deletion guard - how many files a client may delete before it asks
# ===========================================================================
# The mirror half of a client chain deletes every local track its host has stopped offering. This
# section covers the ceiling on that: the number a chain may delete unheard, 0 meaning any number,
# the question shown when the ceiling is passed, and the fact that none of it reaches a chain built
# by an earlier version or a USB drive.
GUARD_MIX = fixture("guard host mix")
audio_file(GUARD_MIX, "keep1.mp3", body=b"still on the host")
audio_file(GUARD_MIX, "keep2.mp3", body=b"still on the host too")
GUARD_HOST = _FakeHost(GUARD_MIX)


def _guard_dest(name, orphans):
    """A client folder holding `orphans` tracks its host has stopped offering."""
    folder = fixture(name)
    for n in range(orphans):
        audio_file(folder, f"orphan{n:02d}.mp3", body=b"mine")
    return folder


check("SY-M1 a chain naming no limit - every chain built before this existed - gets the default, and the default is ten",
      mod.DEFAULT_DELETE_CONFIRM_LIMIT == 10
      and mod.delete_confirm_limit(_client_chain(fixture("guard no limit"), GUARD_HOST.port)) == 10)
check("SY-M2 a limit read out of a hand-edited config is turned into a usable number rather than a crash",
      mod.delete_confirm_limit({"delete_confirm_limit": "12"}) == 12
      and mod.delete_confirm_limit({"delete_confirm_limit": 0}) == 0
      and mod.delete_confirm_limit({"delete_confirm_limit": -5}) == 0
      and mod.delete_confirm_limit({"delete_confirm_limit": True}) == 10
      and mod.delete_confirm_limit({"delete_confirm_limit": "plenty"}) == 10)

GUARD_ASKED = []
GUARD_DEST11 = _guard_dest("guard eleven", 11)
ok, message, moved, removed = mod.SyncClientWorker.sync_chain(
    _client_chain(GUARD_DEST11, GUARD_HOST.port),
    confirm_cb=lambda q: GUARD_ASKED.append(q) or True)
check("SY-M3 eleven is more than ten, so the client stops and asks before deleting a single file",
      len(GUARD_ASKED) == 1 and ok is True and removed == 11
      and not any(track.name.startswith("orphan") for track in GUARD_DEST11.iterdir()),
      (ok, message, removed, len(GUARD_ASKED)))
check("SY-M4 the question says how many, where they are, and what it is asking to do",
      "11" in GUARD_ASKED[0] and str(GUARD_DEST11) in GUARD_ASKED[0]
      and "Delete 11 file(s)?" in GUARD_ASKED[0] and "orphan00.mp3" in GUARD_ASKED[0],
      GUARD_ASKED)
check("SY-M5 a Yes deletes them and still brings down what the host does offer",
      moved == 2 and (GUARD_DEST11 / "keep1.mp3").is_file()
      and (GUARD_DEST11 / "keep2.mp3").is_file(), (ok, message, moved))
check("SY-M6 a quick answer costs nothing on the wire: the host saw exactly the commands a sync always sends",
      GUARD_HOST.commands == ["AUTH", "GET_INDEX", "PULL_FILE", "PULL_FILE"], GUARD_HOST.commands)

GUARD_HOST2 = _FakeHost(GUARD_MIX)
GUARD_EXACT = []
GUARD_DEST10 = _guard_dest("guard ten", 10)
ok, message, moved, removed = mod.SyncClientWorker.sync_chain(
    _client_chain(GUARD_DEST10, GUARD_HOST2.port),
    confirm_cb=lambda q: GUARD_EXACT.append(q) or True)
check("SY-M7 the limit means more than: exactly ten deletions go ahead unheard",
      GUARD_EXACT == [] and ok is True and removed == 10, (GUARD_EXACT, removed))

GUARD_REFUSED = []
GUARD_DESTNO = _guard_dest("guard refused", 11)
ok, message, moved, removed = mod.SyncClientWorker.sync_chain(
    _client_chain(GUARD_DESTNO, GUARD_HOST2.port),
    confirm_cb=lambda q: GUARD_REFUSED.append(q) or False)
check("SY-M8 a No leaves every file exactly where it was, and the sync reports that it did",
      ok is True and removed == 0
      and sum(1 for track in GUARD_DESTNO.iterdir() if track.name.startswith("orphan")) == 11
      and mod.deletions_were_declined(message), (ok, message, removed))
check("SY-M9 a No is about deleting only - the tracks the host still offers came down anyway",
      moved == 2 and (GUARD_DESTNO / "keep2.mp3").is_file(), (ok, message, moved))
CLEAN_MESSAGE = mod.SyncClientWorker.sync_chain(
    _client_chain(_guard_dest("guard clean", 1), GUARD_HOST2.port))[1]
check("SY-M10 a sync that deleted what it was told to is not read as a refused one",
      not mod.deletions_were_declined(CLEAN_MESSAGE), CLEAN_MESSAGE)

UNLIMITED = _client_chain(_guard_dest("guard unlimited", 12), GUARD_HOST2.port)
UNLIMITED["delete_confirm_limit"] = 0
UNLIMITED_ASKED = []
ok, message, moved, removed = mod.SyncClientWorker.sync_chain(
    UNLIMITED, confirm_cb=lambda q: UNLIMITED_ASKED.append(q) or False)
check("SY-M11 a limit of 0 means any number: twelve gone, and a listener who would have said no is never asked",
      UNLIMITED_ASKED == [] and ok is True and removed == 12, (UNLIMITED_ASKED, removed))

ADDITIVE_DEST = _guard_dest("guard additive", 12)
ADDITIVE = _client_chain(ADDITIVE_DEST, GUARD_HOST2.port, deletion_mode="additive")
ADDITIVE["delete_confirm_limit"] = 5
ADDITIVE_ASKED = []
ok, message, moved, removed = mod.SyncClientWorker.sync_chain(
    ADDITIVE, confirm_cb=lambda q: ADDITIVE_ASKED.append(q) or True)
check("SY-M12 an Additive chain keeps local files, so it has nothing to be asked about and nothing to delete",
      ADDITIVE_ASKED == [] and ok is True and removed == 0
      and sum(1 for track in ADDITIVE_DEST.iterdir() if track.name.startswith("orphan")) == 12,
      (ADDITIVE_ASKED, removed))

LEGACY_SHAPE = _guard_dest("guard legacy shape", 12)
ok, message, moved, removed = mod.SyncClientWorker.sync_chain(
    _client_chain(LEGACY_SHAPE, GUARD_HOST2.port))
check("SY-M13 a caller that hands over nobody to ask - the call shape every earlier build and the USB half use - deletes the way it always did",
      ok is True and removed == 12
      and not any(track.name.startswith("orphan") for track in LEGACY_SHAPE.iterdir()),
      (ok, message, removed))
GUARD_HOST.stop()
GUARD_HOST2.stop()

GUARD_RC_CM = mod.SyncConfigManager(str(fixture("config guard removable")))
GUARD_RC_CLIENT = GUARD_RC_CM.add_client_chain("Guard Client", str(_guard_dest("guard rc copy", 12)),
                                               "7113", "127.0.0.1", host_port=_closed_port())
GUARD_RC_CLIENT["delete_confirm_limit"] = 3
GUARD_RC_CLIENT["last_synced"] = time.time()
GUARD_RC_ASKED = []
ok, message, moved, removed = _removable(GUARD_RC_CM, "7113", fixture("guard rc stick"),
                                         confirm_cb=lambda q: GUARD_RC_ASKED.append(q) or True,
                                         name="Guard Client")
check("SY-M14 the USB half is not held up by a chain's delete ceiling: a drive sync asks nothing about files and writes the copy across",
      GUARD_RC_ASKED == [] and ok is True and moved == 12, (GUARD_RC_ASKED, ok, message, moved))


class _SeenSocket:
    """A real socket with a notebook: everything sent through it is kept, everything else is the real thing."""

    def __init__(self, sock):
        self.sock = sock
        self.sent = []

    def sendall(self, data):
        self.sent.append(bytes(data))
        self.sock.sendall(data)

    def recv(self, n):
        return self.sock.recv(n)

    def settimeout(self, timeout):
        self.sock.settimeout(timeout)

    def close(self):
        self.sock.close()


KEEP_MIX = fixture("guard keep mix")
audio_file(KEEP_MIX, "keep1.mp3", body=b"the host still has this")
KEEP_SERVER = mod.SyncHostServer(lambda: [{"sync_code": "8899", "name": "Keeper",
                                           "folder_path": str(KEEP_MIX)}])
KEEP_SERVER._running = True
KEEP_CLIENT, KEEP_SERVER_SIDE = _loopback_pair()
_keep_host = threading.Thread(target=lambda: KEEP_SERVER._handle_client(KEEP_SERVER_SIDE, "127.0.0.1"),
                              daemon=True)
_keep_host.start()
_seen = _SeenSocket(KEEP_CLIENT)
mod.send_json_msg(_seen, {"cmd": "AUTH", "sync_code": "8899"})
keep_auth = mod.recv_json_msg(_seen, timeout=8.0)
before_keeper = len(_seen.sent)
keeper = mod._HostKeepalive(_seen, interval=0.25)
keeper.start()
time.sleep(0.7)
keeper.stop()
sent_after_stop = len(_seen.sent)
time.sleep(0.4)
pings = [json.loads(chunk[4:].decode("utf-8")) for chunk in _seen.sent[before_keeper:]]
check("SY-M15 while the user is deciding, the client keeps its host interested, and sends nothing else",
      keep_auth.get("status") == "OK" and len(pings) >= 2
      and all(command == {"cmd": "PING"} for command in pings), (keep_auth, pings))
check("SY-M16 and it stops the moment it is told to - the keeping-alive does not outlive the question",
      len(_seen.sent) == sent_after_stop, (sent_after_stop, len(_seen.sent)))
mod.send_json_msg(_seen, {"cmd": "PULL_FILE", "filename": "keep1.mp3"})
keep_sending = mod.recv_json_msg(_seen, timeout=8.0)
keep_bytes = _drain(_seen, keep_sending.get("filesize", 0))
check("SY-M17 every PING it sent was answered and read back by the keeper itself, so the pull that follows reads the answer to its own pull",
      keep_sending.get("status") == "SENDING" and keep_sending.get("filename") == "keep1.mp3"
      and keep_bytes == (KEEP_MIX / "keep1.mp3").read_bytes(), (keep_sending, keep_bytes))
_seen.close()
_keep_host.join(8)
KEEP_SERVER._running = False
check("SY-M18 the keepalive is on a schedule the host's own patience allows, so a long think is not mistaken for a dead client",
      0 < mod.SYNC_CONFIRM_PING_INTERVAL < 30.0, mod.SYNC_CONFIRM_PING_INTERVAL)

# ===========================================================================
# SY-N: what a host says to a search, and what a search makes of the answer
# ===========================================================================
# A chain's visibility is a decision about who may be told the chain exists, so what is proved here
# is the answering rather than the windows: which chains a host names to a stranger, which it answers
# only when its code is named back, and what a search across this machine's own networks does with
# each answer. Same bounds as the rest of this suite - loopback sockets on port 0 only, and the
# address lists a search is asked to probe are written out here instead of read off the machine, so
# no check puts a packet on the LAN.
host_chain_is_visible = seam.original("host_chain_is_visible")
advertised_chains = seam.original("advertised_chains")
probe_replies = seam.original("probe_replies")
hello_reply = seam.original("hello_reply")
HostScanner = seam.original("HostScanner")
DISCOVERY_APP = seam.original("DISCOVERY_APP_NAME")

VIS_CFG_PATH = str(fixture("config visibility"))
VIS_CFG = mod.SyncConfigManager(VIS_CFG_PATH)
NEW_HOST_CHAIN = VIS_CFG.add_hosted_chain("Front Room", str(fixture("visible master")), "2468")
check("SY-N1 a chain made by this build carries its own visibility, so nobody has to guess at it afterwards",
      NEW_HOST_CHAIN["visible"] is True
      and mod.SyncConfigManager(VIS_CFG_PATH).hosted_chains[0]["visible"] is True,
      mod.SyncConfigManager(VIS_CFG_PATH).hosted_chains)
VIS_CFG.set_host_chain_visibility("hc_2468", False)
check("SY-N2 and the toggle writes a real decision into the config rather than removing the question",
      mod.SyncConfigManager(VIS_CFG_PATH).hosted_chains[0]["visible"] is False,
      mod.SyncConfigManager(VIS_CFG_PATH).hosted_chains)

check("SY-N3 a chain saved by 3.0-3.4 carries no such key and reads as visible, because visible is what it already was",
      host_chain_is_visible({"sync_code": "1234", "name": "Made by 3.2"}) is True
      and host_chain_is_visible({}) is True, host_chain_is_visible({}))
check("SY-N4 a written False is private, and so is anything a hand-edited config spells out as no",
      host_chain_is_visible({"visible": False}) is False
      and host_chain_is_visible({"visible": "false"}) is False
      and host_chain_is_visible({"visible": "0"}) is False
      and host_chain_is_visible({"visible": "off"}) is False
      and host_chain_is_visible({"visible": ""}) is False
      and host_chain_is_visible({"visible": True}) is True
      and host_chain_is_visible({"visible": "yes"}) is True,
      [host_chain_is_visible({"visible": raw}) for raw in (False, "false", "0", "off", "", True, "yes")])

MIXED_CHAINS = [{"sync_code": "1111", "name": "Open"},
                {"sync_code": "2222", "name": "Study", "visible": False},
                {"sync_code": "3333", "name": "Made by 3.4"}]

check("SY-N5 the beacon names only the visible chains, and it names their codes in the same breath",
      [c["sync_code"] for c in advertised_chains(MIXED_CHAINS)] == ["1111", "3333"],
      advertised_chains(MIXED_CHAINS))
check("SY-N6 a hosted chain with no code in it is named in nothing at all",
      advertised_chains([{"name": "no code"}, {"sync_code": "", "name": "empty code"}]) == [],
      advertised_chains([{"name": "no code"}, {"sync_code": "", "name": "empty code"}]))
check("SY-N7 asked in the general over UDP, a host answers with its visible chains only",
      [r["sync_code"] for r in probe_replies(MIXED_CHAINS, 63350)] == ["1111", "3333"],
      probe_replies(MIXED_CHAINS, 63350))
check("SY-N8 asked by code, a private chain answers - a client holding the code could sync it anyway",
      len(probe_replies(MIXED_CHAINS, 63350, "2222")) == 1
      and probe_replies(MIXED_CHAINS, 63350, "2222")[0]["chain_name"] == "Study"
      and probe_replies(MIXED_CHAINS, 63350, "2222")[0]["visible"] is False,
      probe_replies(MIXED_CHAINS, 63350, "2222"))
check("SY-N9 and a code it does not host gets no answer, private or otherwise",
      probe_replies(MIXED_CHAINS, 63350, "9999") == [], probe_replies(MIXED_CHAINS, 63350, "9999"))

_search_answer = hello_reply(MIXED_CHAINS, '', 63351)
check("SY-N10 the answer a search reads names the visible chains, says what app it is, and says which port it is answering on",
      _search_answer["status"] == "OK" and _search_answer["app"] == DISCOVERY_APP
      and _search_answer["port"] == 63351
      and [c["sync_code"] for c in _search_answer["chains"]] == ["1111", "3333"],
      _search_answer)
check("SY-N11 the hosted folder's own path is not in an answer handed to somebody who has not authenticated",
      all("folder_path" not in chain for chain in _search_answer["chains"]), _search_answer["chains"])
check("SY-N12 a host whose only chains are private advertises nothing rather than a yes naming nobody",
      hello_reply([{"sync_code": "2222", "name": "Study", "visible": False}])
      == {"status": "ERROR", "reason": "This host advertises no sync chain"},
      hello_reply([{"sync_code": "2222", "name": "Study", "visible": False}]))
check("SY-N13 a private chain answers a search that named its code, and says it is private while answering",
      hello_reply(MIXED_CHAINS, "2222")["chains"] == [{"sync_code": "2222", "name": "Study", "visible": False}],
      hello_reply(MIXED_CHAINS, "2222"))
check("SY-N14 a private chain is not named alongside someone else's code either - naming one chain is not naming them all",
      hello_reply(MIXED_CHAINS, "1111")["chains"] == [{"sync_code": "1111", "name": "Open", "visible": True}],
      hello_reply(MIXED_CHAINS, "1111"))


def _round_with(server, requests, expecting):
    """The same drive SY-G uses - the host's own handler over a connected loopback pair."""
    client, server_side = _loopback_pair()
    worker = threading.Thread(target=lambda: server._handle_client(server_side, "127.0.0.1"), daemon=True)
    worker.start()
    for message in requests:
        mod.send_json_msg(client, message)
    answers = [mod.recv_json_msg(client, timeout=8.0) for _ in range(expecting)]
    client.close()
    worker.join(8)
    try:
        server_side.close()
    except Exception:
        pass
    return answers, worker


SEARCH_CHAINS = [{"sync_code": "5301", "name": "Front Room", "folder_path": str(HOST_CHAIN_FOLDER)},
                 {"sync_code": "5302", "name": "Study", "visible": False, "folder_path": str(HOST_CHAIN_FOLDER)}]
SEARCH_SEEN = []
SEARCH_SERVER = mod.SyncHostServer(lambda: SEARCH_CHAINS,
                                   on_client_activity_cb=lambda code, ip, note: SEARCH_SEEN.append((code, note)))
SEARCH_SERVER._running = True

answers, _ = _round_with(SEARCH_SERVER, [{"cmd": "HELLO", "sync_code": ""}], 1)
check("SY-N15 a host answers a search without authenticating it, and a chain saved without a visibility key is in the answer",
      answers[0].get("status") == "OK" and [c["sync_code"] for c in answers[0]["chains"]] == ["5301"],
      answers)
check("SY-N16 the private chain is kept out of that answer, and answers on its own once its code is named",
      all(c["sync_code"] != "5302" for c in answers[0]["chains"])
      and _round_with(SEARCH_SERVER, [{"cmd": "HELLO", "sync_code": "5302"}], 1)[0][0]["chains"]
      == [{"sync_code": "5302", "name": "Study", "visible": False}], answers)
check("SY-N17 a search is not a client: nothing about it reaches the chain's activity reporting",
      SEARCH_SEEN == [], SEARCH_SEEN)

_client, _server_side = _loopback_pair()
_search_worker = threading.Thread(target=lambda: SEARCH_SERVER._handle_client(_server_side, "127.0.0.1"),
                                  daemon=True)
_search_worker.start()
mod.send_json_msg(_client, {"cmd": "HELLO", "sync_code": ""})
_hello_answer = mod.recv_json_msg(_client, timeout=8.0)
_search_worker.join(4)
_handler_closed_up = not _search_worker.is_alive()
try:
    mod.send_json_msg(_client, {"cmd": "AUTH", "sync_code": "5301"})
    _after_search = mod.recv_json_msg(_client, timeout=2.0)
except Exception:
    _after_search = None
_client.close()
_search_worker.join(8)
check("SY-N18 and a search is answered and then done with - finding out a host is there is not being let into its chains",
      _hello_answer.get("status") == "OK" and _handler_closed_up and _after_search is None,
      (_hello_answer, _handler_closed_up, _after_search))

ANSWER_NOTHING = object()


def _search_fixture(chains, answering=None, delay=0.0):
    """One machine answering one search, on loopback, on a port nothing else is using.

    `answering` stands in for an answer the current host would not give - which is how a yt-msd from
    before a search could be answered, and how a machine that is not yt-msd at all, are put in front
    of a search. `delay` is how long it takes to reply, which is the only way a budget gets tested.
    """
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    asked = []

    def _serve():
        try:
            conn, _addr = listener.accept()
        except OSError:
            return
        finally:
            listener.close()
        try:
            request = mod.recv_json_msg(conn, timeout=8.0)
            asked.append(request)
            if delay:
                time.sleep(delay)
            if answering is ANSWER_NOTHING:
                return
            mod.send_json_msg(conn, answering if answering is not None else
                              hello_reply(chains, str((request or {}).get("sync_code", "")), port))
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    threading.Thread(target=_serve, daemon=True).start()
    return port, asked


def _search(chains=MIXED_CHAINS, requested_code="", answering=None, delay=0.0, budget=8.0,
            connect_timeout=1.5, extra_targets=(), extra_ports=(), should_stop=None, on_found=None):
    """Stand one machine up on loopback, search it, and hand back what the search made of it."""
    port, asked = _search_fixture(chains, answering=answering, delay=delay)
    scanner = HostScanner(requested_code=requested_code,
                          targets=["127.0.0.1", *extra_targets],
                          ports=[port, *extra_ports],
                          connect_timeout=connect_timeout, budget=budget)
    return scanner.run(on_found=on_found, should_stop=should_stop), scanner, port, asked


found, scanner, found_port, asked = _search()
check("SY-N19 a search finds the visible chains on an address it was given, naming the port each one answered on",
      [(e["ip"], e["port"], e["sync_code"], e["chain_name"]) for e in found]
      == [("127.0.0.1", found_port, "1111", "Open"), ("127.0.0.1", found_port, "3333", "Made by 3.4")], found)
check("SY-N20 the private chain is not among what a search that named no code found",
      all(e["sync_code"] != "2222" for e in found), found)
check("SY-N21 a search asks in the open, and names no code when nobody gave it one",
      asked == [{"cmd": "HELLO", "sync_code": ""}], asked)

named, _, _, asked_named = _search(requested_code="2222")
check("SY-N22 a private chain answers a search that named its code, and the search reports it as private",
      len(named) == 1 and named[0]["sync_code"] == "2222" and named[0]["visible"] is False
      and asked_named[0]["sync_code"] == "2222", (named, asked_named))

older, _, older_port, _ = _search(answering={"status": "ERROR", "reason": "Expected AUTH command"})
check("SY-N23 a yt-msd from before a search could be answered is still found as a host, with no chain invented for it",
      len(older) == 1 and older[0]["port"] == older_port and older[0]["sync_code"] == ""
      and older[0]["advertised"] is False, older)

older_named, _, _, _ = _search(requested_code="5301",
                               answering={"status": "ERROR", "reason": "Expected AUTH command"})
check("SY-N24 and there the search hands back the code the user already had, because the address was the missing half",
      len(older_named) == 1 and older_named[0]["sync_code"] == "5301", older_named)

_not_hosts = []
for _reply in (ANSWER_NOTHING, {"status": "OK"}, {"status": "OK", "chains": []},
               {"hello": "not this program"}, {"status": "ERROR", "reason": "Something else entirely"}):
    _found_there, _, _, _ = _search(answering=_reply)
    _not_hosts.append(_found_there)
check("SY-N25 a machine with a port open that is not this program is not reported as a host at all",
      all(entries == [] for entries in _not_hosts), _not_hosts)

_broadcast_calls = []
seam.patch("get_broadcast_addresses", lambda: _broadcast_calls.append("broadcast") or [])
_without_broadcast, _, _, _ = _search()
seam.restore("get_broadcast_addresses")
check("SY-N26 a search sends no broadcast packet - it asks each address directly, which is the path a working sync already proved",
      _broadcast_calls == [] and len(_without_broadcast) == 2, (_broadcast_calls, _without_broadcast))

_clock = time.time()
_slow, _slow_scanner, _, _ = _search(delay=2.5, budget=0.4, connect_timeout=2.0)
_spent = time.time() - _clock
check("SY-N27 a search is bounded by its own budget and not by how many addresses it was handed",
      _slow == [] and _slow_scanner.timed_out and _spent < 2.0, (_spent, _slow_scanner.timed_out))

_stopped, _stop_scanner, _, _ = _search(should_stop=lambda: True, budget=8.0)
check("SY-N28 a search stops when it is told to, and stops spending its budget at the same moment",
      _stopped == [] and _stop_scanner.stopped_early and _stop_scanner.searched == 0,
      (_stopped, _stop_scanner.stopped_early, _stop_scanner.searched))

_live = []
_hit, _hit_scanner, _, _ = _search(requested_code="1111", extra_targets=("127.0.0.2",),
                                   extra_ports=(_closed_port(),),
                                   on_found=lambda entry: _live.append(entry["sync_code"]))
check("SY-N29 a search told which code it wanted stops at the first machine answering it, and reports each host as it is found rather than at the end",
      len(_hit) == 1 and _hit_scanner.searched == 2 and _live == ["1111"],
      (_hit, _hit_scanner.searched, _live))

seam.patch("adapter_addresses", lambda: ["192.168.1.50", "10.0.0.9", "192.168.1.77"])
_scope_bases, _scope_own = seam.original("local_scan_scope")()
check("SY-N30 the networks a search covers are the network of every adapter this machine answers on, not one guess about where a packet would leave",
      _scope_bases == ["192.168.1", "10.0.0"] and _scope_own == ["192.168.1.50", "10.0.0.9", "192.168.1.77"],
      (_scope_bases, _scope_own))
_scope_targets = seam.original("subnet_targets")(_scope_bases, exclude=_scope_own)
check("SY-N31 every host number in those networks is asked - .1 through .254 - and this machine is never asked about itself",
      _scope_targets[0] == "192.168.1.1" and _scope_targets[-1] == "10.0.0.254"
      and len(_scope_targets) == 505 and "192.168.1.50" not in _scope_targets
      and "10.0.0.9" not in _scope_targets, (len(_scope_targets), _scope_targets[:2]))
seam.patch("SCAN_MAX_NETWORKS", 1)
check("SY-N32 a machine with adapters on several networks searches the number of networks it is bounded to",
      seam.original("local_scan_scope")()[0] == ["192.168.1"], seam.original("local_scan_scope")()[0])
seam.restore("SCAN_MAX_NETWORKS")
seam.patch("SCAN_MAX_TARGETS", 300)
check("SY-N33 and the addresses a search will ask is capped, so an unusual network is not asked sixty thousand questions",
      len(seam.original("subnet_targets")(_scope_bases)) == 300,
      len(seam.original("subnet_targets")(_scope_bases)))
seam.restore("SCAN_MAX_TARGETS")
_default_targets, _default_ports = HostScanner().scope()
check("SY-N34 a search handed nothing to ask about reads this machine's own networks, on the ports a host listens on",
      _default_targets[0] == "192.168.1.1"
      and _default_ports == list(range(seam.original("SYNC_PORT_START"), seam.original("SYNC_PORT_END") + 1)),
      (_default_targets[:2], _default_ports[:2]))
seam.restore("adapter_addresses")

seam.patch("get_local_ip", lambda: "127.0.0.1")
_own_addresses = seam.original("adapter_addresses")()
seam.restore("get_local_ip")
check("SY-N35 the address list a search reads off this machine never includes the loopback address, whichever adapter it came from",
      "127.0.0.1" not in _own_addresses, _own_addresses)

seam.patch("adapter_addresses", lambda: ["192.168.1.50"])
seam.patch("subnet_targets", lambda bases, exclude=None: ["127.0.0.1"])
_fallback_port, _ = _search_fixture(MIXED_CHAINS)
seam.patch("SYNC_PORT_START", _fallback_port)
seam.patch("SYNC_PORT_END", _fallback_port)
# The standing patch this suite keeps over `discover_host_on_lan` - so no check can put a probe on
# the LAN - is lifted for this one check and put straight back: it is the only check that drives the
# real lookup, and it drives it against a loopback port written out here.
seam.restore("discover_host_on_lan")
_fallback = mod.discover_host_on_lan("3333", timeout=4.0)
seam.patch("discover_host_on_lan", _no_host_on_lan)
seam.restore("SYNC_PORT_START")
seam.restore("SYNC_PORT_END")
seam.restore("subnet_targets")
seam.restore("adapter_addresses")
check("SY-N36 the search a client falls back to when the address it remembers stopped answering is this same search, and still hands back the (ip, port, name) that client reads",
      _fallback == ("127.0.0.1", _fallback_port, "Made by 3.4"), _fallback)

# ===========================================================================
# SY-O: what a host calls its chain, and where a client keeps that name
# ===========================================================================
# Two names travel with a synced chain: the name the client's folder carries, and the name the host's
# chain carries. The host gives its own in both answers a client can get - the HELLO a network search
# reads and the AUTH a sync makes - but the client's record kept only the address and the code, so a
# chain joined by an address typed in by hand was called by a name neither machine agreed with, and the
# search that found a host whose address had moved threw the name away on the way. Bounds as in SY-N:
# loopback sockets on port 0, and no packet put on the LAN.
HOST_TWO_CHAINS = [{"sync_code": "5401", "name": "Other", "folder_path": str(HOST_CHAIN_FOLDER)},
                   {"sync_code": "5402", "name": "Christian", "folder_path": str(HOST_CHAIN_FOLDER)}]
_o_search_answer = hello_reply(HOST_TWO_CHAINS, '', 63360)
check("SY-O1 a host hosting two chains names both to a search, each by the name it gives that chain",
      [(c["sync_code"], c["name"]) for c in _o_search_answer["chains"]]
      == [("5401", "Other"), ("5402", "Christian")], _o_search_answer["chains"])

_o_auth, _ = _round_with(SEARCH_SERVER, [{"cmd": "AUTH", "sync_code": "5301"}], 1)
check("SY-O2 the answer that lets a client into a chain names the chain it is letting it into",
      _o_auth[0].get("status") == "OK" and _o_auth[0].get("chain_name") == "Front Room", _o_auth)

_o_cfg = mod.SyncConfigManager(str(fixture("host chain name")))
_o_named = _o_cfg.add_client_chain(name="Local Folder", folder_path=str(fixture("named dest")),
                                   sync_code="5411", host_ip="127.0.0.1", host_chain_name="Christian")
_o_plain = _o_cfg.add_client_chain(name="Typed In", folder_path=str(fixture("plain dest")),
                                   sync_code="5412", host_ip="127.0.0.1")
_o_cfg.save()
_o_saved = {c["sync_code"]: c for c in mod.SyncConfigManager(_o_cfg.config_dir).client_chains}
check("SY-O3 the name is saved with the chain, and a chain no host has named is saved naming nothing rather than missing the key",
      _o_saved["5411"]["host_chain_name"] == "Christian" and _o_saved["5412"]["host_chain_name"] == "",
      _o_saved)

_o_host_mix = fixture("named host mix")
audio_file(_o_host_mix, "one.mp3", body=b"a hosted track")
_o_host = _FakeHost(_o_host_mix)
_o_chain = _client_chain(fixture("named client dest"), _o_host.port)
_o_ok, _o_msg, _o_moved, _ = mod.SyncClientWorker.sync_chain(_o_chain)
check("SY-O4 a sync that reaches its host keeps the name that host gives its own chain",
      _o_ok is True and _o_chain["host_chain_name"] == "Remote Mix", (_o_chain, _o_msg))
_o_live = _FakeHost(_o_host_mix)
_o_moved_chain = _client_chain(fixture("moved host dest"), _closed_port())
seam.patch("discover_host_on_lan",
           lambda sync_code=None, timeout=2.5: ("127.0.0.1", _o_live.port, "Christian"))
_o_ok2, _o_msg2, _o_moved2, _ = mod.SyncClientWorker.sync_chain(_o_moved_chain)
_o_host.stop()
_o_live.stop()
check("SY-O5 a chain whose host has moved is found again by its code, and the name travels back with the address",
      _o_ok2 is True and _o_moved_chain["host_port"] == _o_live.port
      and _o_moved_chain["host_chain_name"] == "Remote Mix", (_o_moved_chain, _o_msg2))
_o_quiet_chain = _client_chain(fixture("quiet host dest"), _closed_port())
_o_quiet_port = _closed_port()
seam.patch("discover_host_on_lan",
           lambda sync_code=None, timeout=2.5: ("127.0.0.1", _o_quiet_port, "Study"))
_o_ok3, _o_msg3, _, _ = mod.SyncClientWorker.sync_chain(_o_quiet_chain)
seam.patch("discover_host_on_lan", _no_host_on_lan)
check("SY-O6 and even a search that finds an address it cannot reach leaves the name it was given on the chain",
      _o_ok3 is False and _o_quiet_chain["host_chain_name"] == "Study"
      and _o_quiet_chain["last_known_host_ip"] == "127.0.0.1", (_o_quiet_chain, _o_msg3))


# ===========================================================================
# SY-P: Restore Host - the answer that lets a client rebuild the host it is synced to
# ===========================================================================
# Every section above this one assumes the host holds the library and the client is the one catching up
# to it. Restore Host is the same chain turned around: the hosted folder is the one that has lost its
# tracks, the client's folder is the one that still holds them, and what gets written is the host's copy
# instead of the client's. Two things are proved here. The offer - a four-character code that appears on
# the host's own screen and nowhere else, on a clock, that the person standing at the host can close -
# and the rebuild that follows it, which is the one place in this program where a host writes into its
# hosted folder rather than reading out of it: only what it asked for, only inside the folder, and with
# nothing deleted at either end.
#
# The offer half lives in yt_msd.sync.host and the shape of a code in yt_msd.sync.lan, so this section
# reads them off the seam's own map of the program instead of off names the entry point happens to
# re-export: the protocol is what is under test, and the entry point is only one of the places that
# reads it. Naming the module each one is defined in, rather than taking whichever module the map
# happens to list first, so a name that moves out of the file this section is describing fails here
# instead of quietly reading a re-export nobody calls.
def _defined_in(dotted, name):
    """The module this program names in `dotted`, looked up through the seam's own map."""
    found = next((m for m in seam.owners(name) if m.__name__ == dotted), None)
    if found is None:
        raise seam.SeamError(f"{name!r} is not a module-level name in {dotted}.")
    return found


_host_layer = _defined_in("yt_msd.sync.host", "SyncHostServer")
_lan_layer = _defined_in("yt_msd.sync.lan", "restore_code_shape")
_client_layer = _defined_in("yt_msd.sync.client", "SyncClientWorker")

P_HOST_FOLDER = fixture("restore host folder")
audio_file(P_HOST_FOLDER, "here.mp3", body=b"the track the host still has", mtime=1600000000.0)
P_CLIENT_FOLDER = fixture("restore client folder")
audio_file(P_CLIENT_FOLDER, "here.mp3", body=b"the track the host still has", mtime=1600000000.0)
audio_file(P_CLIENT_FOLDER, "lost.mp3", body=b"the track the host lost", mtime=1500000000.0)
audio_file(P_CLIENT_FOLDER, "gone.mp3", body=b"and this one too", mtime=1400000000.0)
(P_CLIENT_FOLDER / "notes.txt").write_text("not a track", encoding="utf-8")

P_EVENTS = []
P_SERVER = mod.SyncHostServer(
    lambda: [{"sync_code": "6001", "name": "Rebuild Me", "folder_path": str(P_HOST_FOLDER)}],
    on_restore_event_cb=lambda code, ip, event, note: P_EVENTS.append((code, ip, event, note)))
# As every other host in this suite is built: the handler is driven over a connected loopback pair,
# because start() binds SYNC_PORT_START..END and a yt-msd that is genuinely running is listening there.
P_SERVER._running = True


def _restore_pair(server, client_ip="192.168.1.20"):
    """One end of a restore: a connected client, and the host's own handler on its own thread."""
    client, server_side = _loopback_pair()
    worker = threading.Thread(target=lambda: server._handle_client(server_side, client_ip), daemon=True)
    worker.start()
    return client, worker


def _authenticate(client, sync_code="6001"):
    mod.send_json_msg(client, {"cmd": "AUTH", "sync_code": sync_code})
    return mod.recv_json_msg(client, timeout=8.0)


def _ask_for_restore(client, sync_code="6001", from_ip="192.168.1.20"):
    """Ask for a rebuild the way a client asks for one, and hand back what the host answered."""
    mod.send_json_msg(client, {"cmd": "RESTORE_REQUEST", "sync_code": sync_code, "client_ip": from_ip})
    return mod.recv_json_msg(client, timeout=8.0)


def _client_index(folder):
    """The index a client offers a host: name, size, date and checksum of every track it holds."""
    entries = []
    for held in mod.filter_audio_files(folder):
        stat = held.stat()
        entries.append({"name": held.name, "size": stat.st_size, "mtime": stat.st_mtime,
                        "sha256": mod.compute_file_sha256(held)})
    return entries


_p_offer = _host_layer.issue_restore_code("6001", "192.168.1.20")
check("SY-P1 a restore code is four characters from an alphabet with the look-alikes taken out, and is never a number a sync code could be",
      _lan_layer.RESTORE_CODE_LENGTH == 4
      and not any(ch in "IO01" for ch in _lan_layer.RESTORE_CODE_ALPHABET)
      and not _p_offer["code"].isdigit(), (_lan_layer.RESTORE_CODE_ALPHABET, _p_offer["code"]))
check("SY-P2 what a person types is read in the shape it can be checked in, and every way it can be wrong is refused before it is compared to anything",
      _lan_layer.restore_code_shape("k7pz") == "K7PZ"
      and _lan_layer.restore_code_shape(" K7-PZ ") == "K7PZ"
      and _lan_layer.restore_code_shape("K7P") is None
      and _lan_layer.restore_code_shape("K7PZZ") is None
      and _lan_layer.restore_code_shape("IO01") is None
      and _lan_layer.restore_code_shape("K7P_") is None
      and _lan_layer.restore_code_shape("") is None
      and _lan_layer.restore_code_shape(None) is None
      and _lan_layer.restore_code_shape(4821) is None)
check("SY-P3 an offer names the chain it belongs to, the machine that asked for it, the code, and the moment it stops being any use",
      _p_offer["sync_code"] == "6001" and _p_offer["client_ip"] == "192.168.1.20"
      and _lan_layer.restore_code_shape(_p_offer["code"]) == _p_offer["code"]
      and abs((_p_offer["expires_at"] - _p_offer["issued_at"]) - _lan_layer.SYNC_RESTORE_CODE_TIMEOUT) < 1.0,
      _p_offer)
_p_second = _host_layer.issue_restore_code("6001", "192.168.1.21")
check("SY-P4 one chain has one open offer at a time: a newer request replaces the older one rather than competing with it, and the replaced code stops being a way in",
      _host_layer.pending_restore_request("6001")["code"] == _p_second["code"]
      and _host_layer.take_restore_offer("6001", _p_offer["code"]) is None
      and _host_layer.pending_restore_request("6001") is None, (_p_offer["code"], _p_second["code"]))
_p_one = _host_layer.issue_restore_code("6002", "192.168.1.22")
_p_guess = "AAAA" if _p_one["code"] != "AAAA" else "BBBB"
check("SY-P5 a code that is not the one open is an answer and not a hint: it closes the offer instead of leaving it open to be guessed at",
      _host_layer.take_restore_offer("6002", _p_guess) is None
      and _host_layer.pending_restore_request("6002") is None, (_p_one["code"], _p_guess))
_p_stale = _host_layer.issue_restore_code("6003", "192.168.1.23", timeout=0.05)
time.sleep(0.1)
check("SY-P6 an offer nobody used stops being one on its own, and it cannot be spent after that",
      _host_layer.pending_restore_request("6003") is None
      and _host_layer.take_restore_offer("6003", _p_stale["code"]) is None, _p_stale)
_p_card = _host_layer.issue_restore_code("6004", "192.168.1.24")
_p_other_code = "AAAA" if _p_card["code"] != "AAAA" else "BBBB"
check("SY-P7 a code window that closes itself closes only the code it is holding - a card refreshed after somebody else was let in cancels nothing - and the code it is holding does close it",
      _host_layer.cancel_restore_offer("6004", _p_other_code) is False
      and _host_layer.pending_restore_request("6004")["code"] == _p_card["code"]
      and _host_layer.cancel_restore_offer("6004", _p_card["code"]) is True
      and _host_layer.pending_restore_request("6004") is None, _p_card)
check("SY-P8 a restored file may only ever be a name this folder can hold: separators, climbs out of the folder and file types a chain cannot hold are all refused",
      _host_layer.restore_target(P_HOST_FOLDER, "lost.mp3") == P_HOST_FOLDER / "lost.mp3"
      and _host_layer.restore_target(P_HOST_FOLDER, "../evil.mp3") is None
      and _host_layer.restore_target(P_HOST_FOLDER, "..\\..\\evil.mp3") is None
      and _host_layer.restore_target(P_HOST_FOLDER, "nested/lost.mp3") is None
      and _host_layer.restore_target(P_HOST_FOLDER, "notes.txt") is None
      and _host_layer.restore_target(P_HOST_FOLDER, "") is None
      and _host_layer.restore_target(P_HOST_FOLDER, ".") is None
      and _host_layer.restore_target(P_HOST_FOLDER, "..") is None
      and _host_layer.restore_target(P_HOST_FOLDER, None) is None)

_p_client, _p_worker = _restore_pair(P_SERVER)
_p_auth = _authenticate(_p_client)
_p_ask = _ask_for_restore(_p_client)
_p_open = _host_layer.pending_restore_request("6001")
check("SY-P9 a client that asks to rebuild the host is told the host is waiting for its code, with the chain's name and how long the wait lasts - and with no code in the answer",
      _p_auth.get("status") == "OK" and _p_ask.get("status") == "WAITING_FOR_CODE"
      and _p_ask.get("chain_name") == "Rebuild Me"
      and _p_ask.get("expires_in") == int(_lan_layer.SYNC_RESTORE_CODE_TIMEOUT)
      and _p_open is not None and _p_open["code"] not in json.dumps(_p_ask), (_p_ask, _p_open))
check("SY-P10 the code that answer is waiting for is on the host's own side of the exchange and in its own callback, so the host's window can show it and the host's window alone can close it",
      any(event[2] == "requested" and event[3] == _p_open["code"] and event[1] == "192.168.1.20"
          for event in P_EVENTS), (P_EVENTS, _p_open))
mod.send_json_msg(_p_client, {"cmd": "PING"})
_p_pong = mod.recv_json_msg(_p_client, timeout=8.0)
check("SY-P11 a client holding its connection open while somebody reads a code off another screen does it with a PING, and a host waiting on that code answers it",
      _p_pong.get("status") == "PONG", _p_pong)
P_SERVER.cancel_restore_request("6001", _p_open["code"])
mod.send_json_msg(_p_client, {"cmd": "PING"})
_p_closed = mod.recv_json_msg(_p_client, timeout=8.0)
check("SY-P12 a code closed on the host's own screen is reported to the machine that was waiting for it, and it is closed rather than left open to be tripped over",
      _p_closed.get("status") == "RESTORE_CLOSED" and "no longer open" in _p_closed.get("reason", "")
      and _host_layer.pending_restore_request("6001") is None
      and any(event[2] == "cancelled" for event in P_EVENTS), (_p_closed, P_EVENTS))
_p_worker.join(8); _p_client.close()

_p_client, _p_worker = _restore_pair(P_SERVER)
_authenticate(_p_client)
_ask_for_restore(_p_client)
_p_code = _host_layer.pending_restore_request("6001")["code"]
_p_wrong = "AAAA" if _p_code != "AAAA" else "BBBB"
mod.send_json_msg(_p_client, {"cmd": "RESTORE_CONFIRM", "sync_code": "6001", "code": _p_wrong})
_p_refused = mod.recv_json_msg(_p_client, timeout=8.0)
check("SY-P13 a code typed wrong on the client is refused, closes the offer rather than leaving it open to be tried again, and writes nothing into the hosted folder",
      _p_refused.get("status") == "ERROR" and "not the code" in _p_refused.get("reason", "")
      and _host_layer.pending_restore_request("6001") is None
      and sorted(held.name for held in mod.filter_audio_files(P_HOST_FOLDER)) == ["here.mp3"]
      and not any(event[2] == "started" for event in P_EVENTS), (_p_refused, _p_wrong))
_p_client.close(); _p_worker.join(8)


def _restore_round(server, requests, expecting, client_ip="192.168.1.30"):
    """A short visit to a host that is mid-restore: send these, read those answers, and go."""
    client, worker = _restore_pair(server, client_ip)
    for message in requests:
        mod.send_json_msg(client, message)
    answers = [mod.recv_json_msg(client, timeout=8.0) for _ in range(expecting)]
    client.close()
    worker.join(8)
    return answers


_p_client, _p_worker = _restore_pair(P_SERVER)
_authenticate(_p_client)
_ask_for_restore(_p_client)
_p_code = _host_layer.pending_restore_request("6001")["code"]
mod.send_json_msg(_p_client, {"cmd": "RESTORE_CONFIRM", "sync_code": "6001", "code": _p_code})
_p_accepted = mod.recv_json_msg(_p_client, timeout=8.0)
check("SY-P14 the right code, accepted on the host, is what lets the machine that typed it through, and the host's own half of the rebuild starts at that moment",
      _p_accepted.get("status") == "CODE_ACCEPTED" and _p_accepted.get("chain_name") == "Rebuild Me"
      and any(event[2] == "started" for event in P_EVENTS)
      and P_SERVER.is_restoring("6001") is True, (_p_accepted, P_EVENTS))
_p_here_before = (P_HOST_FOLDER / "here.mp3").read_bytes()
_p_offered = (_client_index(P_CLIENT_FOLDER)
              + [{"name": "../escape.mp3", "size": 9, "mtime": 1300000000.0, "sha256": ""},
                 {"name": "notes.txt", "size": 11, "mtime": 1300000000.0, "sha256": ""}])
mod.send_json_msg(_p_client, {"cmd": "PUSH_INDEX", "sync_code": "6001", "files": _p_offered})
_p_short = mod.recv_json_msg(_p_client, timeout=_lan_layer.SYNC_RESTORE_HANDSHAKE_TIMEOUT + 4)
check("SY-P15 a host being rebuilt answers with a shortlist of its own: the files its folder still needs, a count of what it already holds, and nothing it was not offered a name for",
      _p_short.get("status") == "RESTORING"
      and set(_p_short.get("files") or []) == {"lost.mp3", "gone.mp3"}
      and _p_short.get("already_there") == 1, (_p_short, _p_offered))
_p_busy = _restore_round(P_SERVER, [{"cmd": "AUTH", "sync_code": "6001"},
                                    {"cmd": "GET_INDEX"},
                                    {"cmd": "PULL_FILE", "sync_code": "6001", "filename": "lost.mp3"},
                                    {"cmd": "RESTORE_REQUEST", "sync_code": "6001"}], 4)
check("SY-P16 while a hosted folder is being rebuilt it is not a host and it is not a half-host either: another machine on the same chain is refused its index, refused a file and refused its own rebuild, each time with a reason that says why",
      _p_busy[0].get("status") == "OK"
      and all(answer.get("status") == "ERROR" for answer in _p_busy[1:])
      and "being rebuilt" in _p_busy[1].get("reason", "")
      and "being rebuilt" in _p_busy[2].get("reason", "")
      and "being rebuilt" in _p_busy[3].get("reason", ""), _p_busy)
mod.send_json_msg(_p_client, {"cmd": "PUSH_FILE", "sync_code": "6001", "filename": "here.mp3",
                              "filesize": 5, "sha256": "x" * 64, "mtime": 1300000000.0})
_p_stray = mod.recv_json_msg(_p_client, timeout=8.0)
mod.send_json_msg(_p_client, {"cmd": "PUSH_FILE", "sync_code": "6001", "filename": "../escape.mp3",
                              "filesize": 5, "sha256": "x" * 64, "mtime": 1300000000.0})
_p_trick = mod.recv_json_msg(_p_client, timeout=8.0)
check("SY-P17 a host being rebuilt takes only what it asked for and only inside its folder: a file it did not ask for is refused, a name that climbs out of the folder is refused, and neither refusal closes the connection or writes anything",
      "did not ask for that file" in _p_stray.get("reason", "")
      and "name this folder can hold" in _p_trick.get("reason", "")
      and (P_HOST_FOLDER / "here.mp3").read_bytes() == _p_here_before
      and not (P_HOST_FOLDER / "escape.mp3").exists()
      and not (P_HOST_FOLDER.parent / "escape.mp3").exists(), (_p_stray, _p_trick))
_p_written = 0
for _p_name in sorted(_p_short.get("files") or []):
    _p_src = P_CLIENT_FOLDER / _p_name
    _p_stat = _p_src.stat()
    mod.send_json_msg(_p_client, {"cmd": "PUSH_FILE", "sync_code": "6001", "filename": _p_name,
                                  "filesize": _p_stat.st_size, "sha256": mod.compute_file_sha256(_p_src),
                                  "mtime": _p_stat.st_mtime})
    mod.recv_json_msg(_p_client, timeout=8.0)
    mod.stream_file_to_socket(_p_client, _p_src)
    if mod.recv_json_msg(_p_client, timeout=8.0).get("status") == "OK":
        _p_written += 1
mod.send_json_msg(_p_client, {"cmd": "PUSH_DONE", "sync_code": "6001"})
_p_done = mod.recv_json_msg(_p_client, timeout=8.0)
_p_client.close(); _p_worker.join(8)
check("SY-P18 the rebuild writes the files the host asked for into its own folder, keeps the dates the tracks were made on, and leaves what the host already held exactly as it was",
      _p_written == 2
      and sorted(held.name for held in mod.filter_audio_files(P_HOST_FOLDER)) == ["gone.mp3", "here.mp3", "lost.mp3"]
      and (P_HOST_FOLDER / "lost.mp3").read_bytes() == b"the track the host lost"
      and abs((P_HOST_FOLDER / "lost.mp3").stat().st_mtime - 1500000000.0) < 2.0
      and abs((P_HOST_FOLDER / "gone.mp3").stat().st_mtime - 1400000000.0) < 2.0
      and (P_HOST_FOLDER / "here.mp3").read_bytes() == _p_here_before
      and abs((P_HOST_FOLDER / "here.mp3").stat().st_mtime - 1600000000.0) < 2.0, _p_written)
check("SY-P19 and it closes with the host saying what it received and what never arrived, with the folder a host again, and with nothing deleted on either side",
      _p_done.get("status") == "SYNCED" and _p_done.get("received") == 2 and _p_done.get("missing") == []
      and P_SERVER.is_restoring("6001") is False
      and any(event[2] == "finished" and "2 file(s) rebuilt" in event[3] for event in P_EVENTS)
      and sorted(held.name for held in mod.filter_audio_files(P_CLIENT_FOLDER)) == ["gone.mp3", "here.mp3", "lost.mp3"],
      (_p_done, P_EVENTS))
_p_client.close()

_p_early, _p_early_worker = _restore_pair(P_SERVER)
_authenticate(_p_early)
_ask_for_restore(_p_early)
_p_code = _host_layer.pending_restore_request("6001")["code"]
mod.send_json_msg(_p_early, {"cmd": "RESTORE_CONFIRM", "sync_code": "6001", "code": _p_code})
mod.recv_json_msg(_p_early, timeout=8.0)
mod.send_json_msg(_p_early, {"cmd": "PUSH_INDEX", "sync_code": "6001", "files": _client_index(P_CLIENT_FOLDER)})
mod.recv_json_msg(_p_early, timeout=_lan_layer.SYNC_RESTORE_HANDSHAKE_TIMEOUT + 4)
mod.send_json_msg(_p_early, {"cmd": "PING"})
_p_mistake = mod.recv_json_msg(_p_early, timeout=8.0)
_p_early.close(); _p_early_worker.join(8)
check("SY-P20 a client that sends the wrong thing in the middle of a restore ends the restore rather than leaving the host stuck in one: the host answers with the mistake it saw, reports the transfer as ended, and is a host again",
      _p_mistake.get("status") == "ERROR" and "Unknown command" in _p_mistake.get("reason", "")
      and any(event[2] == "finished" and "in the middle of a restore" in event[3] for event in P_EVENTS)
      and P_SERVER.is_restoring("6001") is False
      and sorted(held.name for held in mod.filter_audio_files(P_HOST_FOLDER)) == ["gone.mp3", "here.mp3", "lost.mp3"],
      _p_mistake)

for _p_name in ("lost.mp3", "gone.mp3"):
    (P_HOST_FOLDER / _p_name).unlink()
_p_client, _p_worker = _restore_pair(P_SERVER)
_authenticate(_p_client)
_p_said = []
_p_ok, _p_message, _p_sent = _client_layer.SyncClientWorker._rebuild_host(
    _p_client, {"sync_code": "6001", "name": "Rebuild Me"}, P_CLIENT_FOLDER, "192.168.1.20:63350",
    status_cb=lambda line: _p_said.append(line), progress_cb=None,
    restore_code_cb=lambda host_label: _host_layer.pending_restore_request("6001")["code"])
_p_client.close(); _p_worker.join(8)
check("SY-P21 the client half of a restore asks for an offer, waits on the code, lists its own folder, and sends only the files the host comes back and asks for",
      _p_ok is True and _p_sent == 2 and _client_layer.host_was_rebuilt(_p_message)
      and sorted(held.name for held in mod.filter_audio_files(P_HOST_FOLDER)) == ["gone.mp3", "here.mp3", "lost.mp3"]
      and sorted(held.name for held in mod.filter_audio_files(P_CLIENT_FOLDER)) == ["gone.mp3", "here.mp3", "lost.mp3"],
      (_p_ok, _p_message, _p_sent))
check("SY-P22 and the client says what it did in words a window can report without guessing: which host it rebuilt, how much it wrote, and that nothing was deleted here",
      "Host rebuilt from this PC: 2 file(s) written to 192.168.1.20:63350, 1 already there" in _p_message
      and _p_message.endswith("Nothing was deleted here.")
      and any("Asking the host to open a restore" in line for line in _p_said)
      and any("Restoring [1/2]" in line for line in _p_said), (_p_message, _p_said))

_p_client, _p_worker = _restore_pair(P_SERVER)
_authenticate(_p_client)
_p_ok2, _p_message2, _p_sent2 = _client_layer.SyncClientWorker._rebuild_host(
    _p_client, {"sync_code": "6001"}, P_CLIENT_FOLDER, "192.168.1.20:63350",
    restore_code_cb=lambda host_label: "no code")
_p_client.close(); _p_worker.join(8)
check("SY-P23 something typed that is not a restore code stops the restore on the client's own side, closes the offer it was waiting on, and leaves both folders exactly as they were",
      _p_ok2 is False and _p_sent2 == 0 and "'no code' is not a restore code" in _p_message2
      and _client_layer.restore_was_left_undone(_p_message2) is True
      and _host_layer.pending_restore_request("6001") is None
      and sorted(held.name for held in mod.filter_audio_files(P_HOST_FOLDER)) == ["gone.mp3", "here.mp3", "lost.mp3"],
      (_p_ok2, _p_message2))

_p_client, _p_worker = _restore_pair(P_SERVER)
_authenticate(_p_client)
_p_ok3, _p_message3, _p_sent3 = _client_layer.SyncClientWorker._rebuild_host(
    _p_client, {"sync_code": "6001"}, P_CLIENT_FOLDER, "192.168.1.20:63350",
    restore_code_cb=lambda host_label: None)
_p_client.close(); _p_worker.join(8)
check("SY-P24 nobody reading the code off the host's screen is a complete answer too: the client cancels its own side, the host's screen stops showing a code nobody will use, and the host is not written into",
      _p_ok3 is False and _p_sent3 == 0 and "Restore Host cancelled" in _p_message3
      and "the host was left exactly as it is" in _p_message3
      and _host_layer.pending_restore_request("6001") is None
      and any(event[2] == "cancelled" and event[3] == "client cancelled" for event in P_EVENTS),
      (_p_ok3, _p_message3, P_EVENTS))


class _DecisionApp:
    """A stand-in for the app a decision callback is built from: it answers, and remembers being asked."""

    def __init__(self, answer=None, code=None):
        self.answer = answer
        self.code = code
        self.titles = []
        self.questions = []
        self.hosts = []

    def ask_sync_decision(self, title, question):
        self.titles.append(title)
        self.questions.append(question)
        return self.answer

    def ask_restore_code(self, title, host_label):
        self.titles.append(title)
        self.hosts.append(host_label)
        return self.code


class _DecisionOnlyApp(_DecisionApp):
    """An app with the button on its box and no way to read the code off the host's screen."""
    ask_restore_code = None


check("SY-P25 the answer a window gives is read as one of the three answers this program names an answer with, and anything else - a half answer, a garbled one, a window that cannot answer - is read as the one that deletes nothing",
      _client_layer.make_sync_decision_cb(_DecisionApp("restore"), "X")("q") == _client_layer.SYNC_DECISION_RESTORE
      and _client_layer.make_sync_decision_cb(_DecisionApp("delete"), "X")("q") == _client_layer.SYNC_DECISION_DELETE
      and _client_layer.make_sync_decision_cb(_DecisionApp("Keep"), "X")("q") == _client_layer.SYNC_DECISION_KEEP
      and _client_layer.make_sync_decision_cb(_DecisionApp(None), "X")("q") == _client_layer.SYNC_DECISION_KEEP
      and _client_layer.make_sync_decision_cb(_DecisionApp("delete them all"), "X")("q") == _client_layer.SYNC_DECISION_KEEP
      and _client_layer.make_sync_decision_cb(_DecisionOnlyApp("restore"), "X")("q") == _client_layer.SYNC_DECISION_RESTORE
      and _client_layer.make_sync_decision_cb(object(), "X") is None)
_p_asked = _DecisionApp("restore", code="k7pz")
_p_decide_asked = _client_layer.make_sync_decision_cb(_p_asked, "Rebuild Me")
_p_code_asked = _client_layer.make_restore_code_cb(_p_asked, "Rebuild Me")
check("SY-P26 both halves of the question are built with the chain's name in the title they hand the window and the words they were given carried through unchanged, and the code half hands the window the host it is waiting on and passes back exactly what was typed",
      _p_decide_asked("The host has stopped offering 13 file(s)") == _client_layer.SYNC_DECISION_RESTORE
      and _p_code_asked("192.168.1.9:63350") == "k7pz"
      and _p_asked.titles == ["Sync Chain 'Rebuild Me' - Delete Files?", "Sync Chain 'Rebuild Me' - Restore Host"]
      and _p_asked.questions == ["The host has stopped offering 13 file(s)"]
      and _p_asked.hosts == ["192.168.1.9:63350"]
      and _client_layer.make_restore_code_cb(_DecisionOnlyApp("restore"), "Rebuild Me") is None,
      (_p_asked.titles, _p_asked.questions, _p_asked.hosts))
check("SY-P27 a restore that was refused, mistyped or given up on is told apart from a host that could not be reached at all - a chain that reached its host and wrote nothing is not reported as one that never got there",
      _client_layer.restore_was_left_undone("Restore Host refused by the host: no such chain. Nothing was deleted here.") is True
      and _client_layer.restore_was_left_undone("The host did not accept that code: wrong code. Nothing was deleted here.") is True
      and _client_layer.restore_was_left_undone("Restore Host cancelled - the host was left exactly as it is.") is True
      and _client_layer.restore_was_left_undone("Could not find active host for Sync Code 6001 on local network.") is False
      and _client_layer.restore_was_left_undone("Failed to connect to host at 192.168.1.9:63350") is False
      and _client_layer.restore_was_left_undone("Synced successfully (0 updated, 11 removed).") is False
      and _client_layer.host_was_rebuilt("Host rebuilt from this PC: 2 file(s) written to 127.0.0.1:63350") is True
      and _client_layer.host_was_rebuilt("Deletions not confirmed - 11 track(s) left where they are") is False,
      _client_layer.RESTORE_UNDONE_NOTES)

P_KEEP_MIX = fixture("kept decision host")
P_KEEP_DEST = fixture("kept decision folder")
for _p_name in ("shared1.mp3", "shared2.mp3", "shared3.mp3"):
    audio_file(P_KEEP_MIX, _p_name, body=b"a track both sides hold")
    audio_file(P_KEEP_DEST, _p_name, body=b"a track both sides hold")
for _p_number in range(11):
    audio_file(P_KEEP_DEST, f"extra{_p_number}.mp3", body=f"an orphan this end still holds {_p_number}".encode("utf-8"))
P_KEEP_HOST = _FakeHost(P_KEEP_MIX)


def _restore_bridge(server):
    """A listening socket on a spare port, handing every connection to this host's own handler.

    A full client sync connects to an address, so a host that is driven by hand cannot be the far end
    of one. This is the socket in between: it takes the place of the listening socket a running host
    owns - on whatever port the operating system hands out, because the ports a real host listens on
    belong to whatever yt-msd is genuinely running on this machine - and gives it to a chain to connect
    to. Nothing else about the host changes.
    """
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)

    def _accept():
        while True:
            try:
                connection, _address = listener.accept()
            except OSError:
                return
            connection.settimeout(15.0)
            threading.Thread(target=lambda: server._handle_client(connection, "127.0.0.1"),
                             daemon=True).start()

    threading.Thread(target=_accept, daemon=True).start()
    return listener


def _guarded_chain(dest, port):
    """A Mirror chain holding eleven tracks its host has stopped offering, over a ceiling of ten."""
    chain = _client_chain(dest, port)
    chain["delete_confirm_limit"] = 10
    return chain


_p_app = _DecisionApp("keep")
_p_said = []
_p_ok, _p_message, _p_moved, _p_removed = mod.SyncClientWorker.sync_chain(
    _guarded_chain(P_KEEP_DEST, P_KEEP_HOST.port), status_cb=lambda line: _p_said.append(line),
    decision_cb=_client_layer.make_sync_decision_cb(_p_app, "Studio"))
check("SY-P28 the Keep answer keeps every file the host stopped offering, says so out loud, and the rest of the sync still runs",
      _p_ok is True and _p_removed == 0 and len(mod.filter_audio_files(P_KEEP_DEST)) == 14
      and len(_p_app.questions) == 1 and "stopped offering 11 file(s)" in _p_app.questions[0]
      and any("Deletions not confirmed - 11 track(s) left where they are" in line for line in _p_said),
      (_p_ok, _p_message, _p_removed, _p_said))
_p_app = _DecisionApp("delete")
_p_said = []
_p_ok, _p_message, _p_moved, _p_removed = mod.SyncClientWorker.sync_chain(
    _guarded_chain(P_KEEP_DEST, P_KEEP_HOST.port), status_cb=lambda line: _p_said.append(line),
    decision_cb=_client_layer.make_sync_decision_cb(_p_app, "Studio"))
check("SY-P29 the Delete answer means what it has always meant: the same warning, the same files gone, and nothing else touched",
      _p_ok is True and _p_removed == 11
      and sorted(held.name for held in mod.filter_audio_files(P_KEEP_DEST))
      == ["shared1.mp3", "shared2.mp3", "shared3.mp3"]
      and len(_p_app.questions) == 1 and "stopped offering 11 file(s)" in _p_app.questions[0]
      and not any("not confirmed" in line.lower() for line in _p_said), (_p_ok, _p_message, _p_removed))

P_REBUILD_HOST_FOLDER = fixture("folder rebuilt by a client")
audio_file(P_REBUILD_HOST_FOLDER, "here.mp3", body=b"the track the host still has", mtime=1600000000.0)
P_REBUILD_CLIENT_FOLDER = fixture("folder that rebuilt a host")
for _p_name, _p_body, _p_when in (("here.mp3", b"the track the host still has", 1600000000.0),
                                  ("lost.mp3", b"the track the host lost", 1500000000.0),
                                  ("gone.mp3", b"and this one too", 1400000000.0)):
    audio_file(P_REBUILD_CLIENT_FOLDER, _p_name, body=_p_body, mtime=_p_when)
for _p_number in range(11):
    audio_file(P_REBUILD_CLIENT_FOLDER, f"extra{_p_number}.mp3",
               body=f"an orphan this end still holds {_p_number}".encode("utf-8"),
               mtime=1300000000.0 + _p_number)
P_REBUILD_SERVER = mod.SyncHostServer(
    lambda: [{"sync_code": "8899", "name": "Rebuild Me", "folder_path": str(P_REBUILD_HOST_FOLDER)}],
    on_restore_event_cb=lambda code, ip, event, note: P_EVENTS.append((code, ip, event, note)))
P_REBUILD_SERVER._running = True
P_REBUILD_BRIDGE = _restore_bridge(P_REBUILD_SERVER)


class _RebuildApp(_DecisionApp):
    """A window that presses Restore Host and types back the code the host's own screen is showing."""

    def ask_restore_code(self, title, host_label):
        self.titles.append(title)
        self.hosts.append(host_label)
        _p_open = _host_layer.pending_restore_request("8899")
        return _p_open["code"] if _p_open else None


_p_app = _DecisionOnlyApp("restore")
_p_said = []
_p_ok, _p_message, _p_moved, _p_removed = mod.SyncClientWorker.sync_chain(
    _guarded_chain(P_REBUILD_CLIENT_FOLDER, P_REBUILD_BRIDGE.getsockname()[1]),
    status_cb=lambda line: _p_said.append(line),
    decision_cb=_client_layer.make_sync_decision_cb(_p_app, "Studio"))
check("SY-P30 a Restore Host answer the worker cannot carry out - no window to read the code off - leaves every file where it is and writes nothing anywhere",
      _p_ok is True and _p_removed == 0 and _p_moved == 0
      and len(mod.filter_audio_files(P_REBUILD_CLIENT_FOLDER)) == 14
      and sorted(held.name for held in mod.filter_audio_files(P_REBUILD_HOST_FOLDER)) == ["here.mp3"]
      and any("Restore Host not carried out" in line for line in _p_said),
      (_p_ok, _p_message, _p_said))

_p_app = _RebuildApp("restore")
_p_said = []
_p_ok, _p_message, _p_moved, _p_removed = mod.SyncClientWorker.sync_chain(
    _guarded_chain(P_REBUILD_CLIENT_FOLDER, P_REBUILD_BRIDGE.getsockname()[1]),
    status_cb=lambda line: _p_said.append(line),
    decision_cb=_client_layer.make_sync_decision_cb(_p_app, "Studio"),
    restore_code_cb=_client_layer.make_restore_code_cb(_p_app, "Studio"))
_p_host_now = sorted(held.name for held in mod.filter_audio_files(P_REBUILD_HOST_FOLDER))
check("SY-P31 answered with Restore Host and the code read off the host's own screen, a client sync turns its own folder into its host's library, deletes nothing on either machine, and stops there",
      _p_ok is True and _p_removed == 0 and _p_moved == 13 and _client_layer.host_was_rebuilt(_p_message)
      and len(_p_host_now) == 14 and len(mod.filter_audio_files(P_REBUILD_CLIENT_FOLDER)) == 14
      and (P_REBUILD_HOST_FOLDER / "extra7.mp3").read_bytes() == b"an orphan this end still holds 7"
      and abs((P_REBUILD_HOST_FOLDER / "extra7.mp3").stat().st_mtime - 1300000007.0) < 2.0
      and not any("Downloading" in line for line in _p_said)
      and any("Restoring [13/13]" in line for line in _p_said),
      (_p_ok, _p_message, _p_moved, _p_removed, _p_host_now))
check("SY-P32 the host was asked the same question the Delete and Keep answers were given, in the same words, and the code it was typed came from the host that was waiting for it",
      len(_p_app.questions) == 1 and "stopped offering 13 file(s)" in _p_app.questions[0]
      and _p_app.hosts == [f"127.0.0.1:{P_REBUILD_BRIDGE.getsockname()[1]}"]
      and any(event[2] == "requested" and event[0] == "8899" for event in P_EVENTS)
      and any(event[2] == "finished" and "13 file(s) rebuilt" in event[3] for event in P_EVENTS),
      (_p_app.questions, _p_app.hosts, P_EVENTS))
P_REBUILD_BRIDGE.close()

# ===========================================================================
# SY-Q: Push To Host - a client offering its own new files to its host before its own next sync deletes them
# ===========================================================================
# Restore Host hands a host a whole library it has lost. A push is the narrower thing next door: a Mirror
# client has made tracks since the two machines last spoke, its host has never seen them, and this chain's
# own next sync is the thing that would delete them out of this folder to match the host. The offer is made
# before that deletion pass rather than after it, and the host decides what it takes. What is proved here is
# what counts as "newer than the last sync", the host's own rule for what it will accept (never a name it
# already holds, never more than its card allows, newest first), that an address it has not let push before
# needs a code read off this machine's screen, and that nothing on either machine is deleted by any of it.
Q_HOST_FOLDER = fixture("host pushed into")
audio_file(Q_HOST_FOLDER, "here.mp3", body=b"the track both machines hold", mtime=1600000000.0)
audio_file(Q_HOST_FOLDER, "same.mp3", body=b"the host's own copy of that name", mtime=1610000000.0)
Q_CLIENT_FOLDER = fixture("folder that pushed")
audio_file(Q_CLIENT_FOLDER, "here.mp3", body=b"the track both machines hold", mtime=1600000000.0)
audio_file(Q_CLIENT_FOLDER, "same.mp3", body=b"this end's different copy of that name", mtime=1615000000.0)
audio_file(Q_CLIENT_FOLDER, "new1.mp3", body=b"the first new track", mtime=1700000001.0)
audio_file(Q_CLIENT_FOLDER, "new2.mp3", body=b"the second new track", mtime=1700000002.0)
audio_file(Q_CLIENT_FOLDER, "new3.mp3", body=b"the third new track", mtime=1700000003.0)
audio_file(Q_CLIENT_FOLDER, "old.mp3", body=b"here longer than this chain has been syncing", mtime=1200000000.0)

Q_EVENTS = []
Q_CHAINS = [{"sync_code": "7711", "name": "Push Me", "folder_path": str(Q_HOST_FOLDER),
             "max_pushed_files": 2}]
Q_SERVER = mod.SyncHostServer(lambda: Q_CHAINS,
                              on_restore_event_cb=lambda code, ip, event, note: Q_EVENTS.append((code, ip,
                                                                                                 event, note)))
Q_SERVER._running = True


def _q_held(folder):
    return sorted(held.name for held in mod.filter_audio_files(folder))


_q_local = {held.name: held for held in mod.filter_audio_files(Q_CLIENT_FOLDER)}
check("SY-Q1 \"the moment this chain last finished a sync\" is read the same way from the number a sync writes and the date a card or a TAG file writes, and a chain that has never finished one has no moment at all rather than a moment older than everything it holds",
      _client_layer.last_sync_moment({"last_synced": 1500000000}) == 1500000000.0
      and _client_layer.last_sync_moment({"last_synced": mod.format_sync_timestamp(1650000000)}) == 1650000000.0
      and _client_layer.last_sync_moment({}) is None
      and _client_layer.last_sync_moment({"last_synced": 0}) is None
      and _client_layer.last_sync_moment({"last_synced": ""}) is None
      and _client_layer.last_sync_moment({"last_synced": None}) is None,
      _client_layer.last_sync_moment({"last_synced": mod.format_sync_timestamp(1650000000)}))
check("SY-Q2 \"newer than the last sync\" is decided by the date on the file itself: everything made after that moment is offered, everything that was already here when this chain started syncing is not, a chain with no last sync offers nothing, and a file that has gone away since it was listed is not offered either",
      _client_layer.files_since_last_sync({"last_synced": 1650000000.0}, _q_local) == ["new1.mp3", "new2.mp3", "new3.mp3"]
      and _client_layer.files_since_last_sync({"last_synced": 1700000002.0}, _q_local) == ["new3.mp3"]
      and _client_layer.files_since_last_sync({}, _q_local) == []
      and _client_layer.files_since_last_sync({"last_synced": 1650000000.0},
                                              dict(_q_local, **{"vanished.mp3": Q_CLIENT_FOLDER / "vanished.mp3"}))
      == ["new1.mp3", "new2.mp3", "new3.mp3"],
      _client_layer.files_since_last_sync({"last_synced": 1650000000.0}, _q_local))

_q_client, _q_worker = _restore_pair(Q_SERVER, "192.168.1.40")
_authenticate(_q_client, "7711")
mod.send_json_msg(_q_client, {"cmd": "PUSH_REQUEST", "sync_code": "7711", "client_ip": "192.168.1.99",
                              "count": 3})
_q_waiting = mod.recv_json_msg(_q_client, timeout=8.0)
_q_offer = _host_layer.pending_push_request("7711")
# The host puts its 'someone has asked for a push' report on the wire a moment after it sends the answer
# that tells the client to wait, so this waits for the report to arrive rather than reading the list the
# instant the answer does. What is proved is the same report; only the moment it is looked for moves.
_q_push_reported = wait_for(lambda: any(event[2] == "push_requested" and event[1] == "192.168.1.40"
                                        for event in Q_EVENTS), 2.0)
check("SY-Q3 an address this host has never let push gets a wait and not a way in: the answer names the chain, this chain's own limit and how long the wait lasts, and the code it is waiting for stays on the host's side of the wire",
      _q_waiting.get("status") == "WAITING_FOR_PUSH_CODE" and _q_waiting.get("chain_name") == "Push Me"
      and _q_waiting.get("limit") == 2 and _q_waiting.get("expires_in") == int(_lan_layer.SYNC_RESTORE_CODE_TIMEOUT)
      and _q_offer is not None and _q_offer["code"] not in json.dumps(_q_waiting)
      and _q_push_reported,
      (_q_waiting, _q_offer, Q_EVENTS))
check("SY-Q3b and the address that was asked about is the one the connection arrived from and not the one the client chose to name in its own message - a push is permitted to a machine, and a machine is its address",
      _q_offer is not None and _q_offer["client_ip"] == "192.168.1.40"
      and all(event[1] != "192.168.1.99" for event in Q_EVENTS), (_q_offer, Q_EVENTS))
_q_wrong = "AAAA" if _q_offer["code"] != "AAAA" else "BBBB"
mod.send_json_msg(_q_client, {"cmd": "PUSH_START", "sync_code": "7711", "code": _q_wrong})
_q_wrong_answer = mod.recv_json_msg(_q_client, timeout=8.0)
_q_client.close(); _q_worker.join(8)
check("SY-Q4 a push code typed wrong closes the offer instead of leaving it open to be guessed at, and writes nothing into the hosted folder",
      _q_wrong_answer.get("status") == "ERROR" and "not the code" in _q_wrong_answer.get("reason", "")
      and _host_layer.pending_push_request("7711") is None
      and _q_held(Q_HOST_FOLDER) == ["here.mp3", "same.mp3"]
      and any(event[2] == "push_cancelled" and event[3] == "wrong code" for event in Q_EVENTS),
      (_q_wrong_answer, _q_wrong))

_q_client, _q_worker = _restore_pair(Q_SERVER, "192.168.1.41")
_authenticate(_q_client, "7711")
_q_ok, _q_note, _q_sent, _q_refused_count = _client_layer.SyncClientWorker._push_to_host(
    _q_client, {"sync_code": "7711"}, Q_CLIENT_FOLDER, ["new1.mp3", "new2.mp3", "new3.mp3"],
    "192.168.1.41:63350", push_code_cb=lambda host_label: None)
_q_client.close(); _q_worker.join(8)
check("SY-Q5 a push nobody authorised is cancelled from the client's own side, which takes the code off the host's screen as well as off this machine's, and it ends with the sentence a window reports a refused push with",
      _q_ok is False and _q_sent == 0 and _q_note == "Push cancelled - nothing was written to the host."
      and _client_layer.push_was_left_undone(_q_note) is True
      and _client_layer.push_was_left_undone("Could not find active host for Sync Code 7711 on local network.") is False
      and _host_layer.pending_push_request("7711") is None
      and _q_held(Q_HOST_FOLDER) == ["here.mp3", "same.mp3"]
      and any(event[2] == "push_cancelled" and event[3] == "client cancelled" for event in Q_EVENTS),
      (_q_ok, _q_note))

Q_CHAINS[0]["max_pushed_files"] = 0
_q_client, _q_worker = _restore_pair(Q_SERVER, "192.168.1.42")
_authenticate(_q_client, "7711")
mod.send_json_msg(_q_client, {"cmd": "PUSH_REQUEST", "sync_code": "7711", "count": 3})
_q_zero = mod.recv_json_msg(_q_client, timeout=8.0)
_q_client.close(); _q_worker.join(8)
Q_CHAINS[0]["max_pushed_files"] = 2
check("SY-Q6 a chain set to take none says so before any of this work happens: the offer is refused at the request, no code is opened on either screen, and nobody measures and hashes files for nothing",
      _q_zero.get("status") == "ERROR" and "does not accept pushed files" in _q_zero.get("reason", "")
      and _host_layer.pending_push_request("7711") is None
      and not any(event[2] == "push_requested" and event[1] == "192.168.1.42" for event in Q_EVENTS),
      _q_zero)

_q_here = Q_HOST_FOLDER / "here.mp3"
_q_offered = [{"name": "same.mp3", "size": 31, "mtime": 1700000100.0, "sha256": "z" * 64},
              {"name": "here.mp3", "size": _q_here.stat().st_size, "mtime": 1700000101.0,
               "sha256": mod.compute_file_sha256(_q_here)},
              {"name": "../escape.mp3", "size": 5, "mtime": 1700000102.0, "sha256": "y" * 64},
              {"name": "notes.txt", "size": 5, "mtime": 1700000103.0, "sha256": "x" * 64},
              {"name": "made1.mp3", "size": 6, "mtime": 1700000200.0, "sha256": "w" * 64},
              {"name": "made2.mp3", "size": 6, "mtime": 1700000300.0, "sha256": "v" * 64}]
_q_taken, _q_refused_all, _q_already = Q_SERVER._push_shortlist(Q_HOST_FOLDER, _q_offered, 2)
_q_taken_cut, _q_refused_cut, _q_already_cut = Q_SERVER._push_shortlist(Q_HOST_FOLDER, _q_offered, 1)
check("SY-Q7 what a host will take from a push is decided before a single byte arrives, and it is narrower than what a rebuild takes: a name this folder already holds is never overwritten on a stranger's word for it however different the two copies are, a name the folder cannot hold is refused, an identical file is not a push at all, and what is left is cut to this chain's limit newest first",
      _q_taken == ["made2.mp3", "made1.mp3"] and _q_refused_all == 3 and _q_already == 1
      and _q_taken_cut == ["made2.mp3"] and _q_refused_cut == 4 and _q_already_cut == 1
      and _q_held(Q_HOST_FOLDER) == ["here.mp3", "same.mp3"],
      (_q_taken, _q_refused_all, _q_already, _q_taken_cut, _q_refused_cut))

# The same chain, now with this machine's own address on its list of addresses that need no code, over a
# bridge so that a whole client push - open the connection, name the chain, read the host's index, decide
# what is new, offer it - runs the way a card runs it.
Q_BRIDGE = _restore_bridge(Q_SERVER)
Q_CHAINS[0]["push_trusted_ips"] = ["127.0.0.1"]
_q_chain = _client_chain(Q_CLIENT_FOLDER, Q_BRIDGE.getsockname()[1], last_synced=1650000000.0)
_q_chain["sync_code"] = "7711"
_q_said = []
_q_ok, _q_note, _q_sent, _q_refused_now = mod.SyncClientWorker.push_chain(
    _q_chain, status_cb=lambda line: _q_said.append(line), push_code_cb=lambda host_label: None)
check("SY-Q8 a push from an address this host has let through writes its newest files into the host's folder up to that chain's limit, keeps the dates the tracks were made on, and leaves everything the host already held exactly as it was - and leaves every file on this machine where it is",
      _q_ok is True and _q_sent == 2 and _q_refused_now == 1
      and _q_held(Q_HOST_FOLDER) == ["here.mp3", "new2.mp3", "new3.mp3", "same.mp3"]
      and (Q_HOST_FOLDER / "new3.mp3").read_bytes() == b"the third new track"
      and abs((Q_HOST_FOLDER / "new3.mp3").stat().st_mtime - 1700000003.0) < 2.0
      and (Q_HOST_FOLDER / "same.mp3").read_bytes() == b"the host's own copy of that name"
      and _q_held(Q_CLIENT_FOLDER) == ["here.mp3", "new1.mp3", "new2.mp3", "new3.mp3", "old.mp3", "same.mp3"],
      (_q_ok, _q_sent, _q_refused_now, _q_held(Q_HOST_FOLDER)))
check("SY-Q8b and it is reported in words a card can print without guessing: which host it wrote into, what landed, what was refused, and that nothing was deleted here",
      _client_layer.files_were_pushed(_q_note) is True
      and _client_layer.nothing_to_push(_q_note) is False
      and f"Pushed to host: 2 file(s) added to 127.0.0.1:{Q_BRIDGE.getsockname()[1]}, 0 already there, 1 refused" in _q_note
      and _q_note.endswith("Nothing was deleted here.")
      and any("leave to push - no code needed" in line for line in _q_said)
      and any("Pushing [2/2] onto the host" in line for line in _q_said),
      (_q_note, _q_said))
check("SY-Q8c an address this host trusts is never asked for a code: no offer was opened on either screen, the host's own events say a trusted client was let through, and the host knows what that push did",
      not any(event[2] == "push_requested" and event[1] == "127.0.0.1" for event in Q_EVENTS)
      and any(event[2] == "push_started" and event[3] == "trusted client" for event in Q_EVENTS)
      and any(event[2] == "push_finished" and "2 file(s) written" in event[3] and "1 refused" in event[3]
              for event in Q_EVENTS)
      and Q_SERVER.last_push_counts("7711") == (2, 1)
      and Q_SERVER.is_pushing("7711") is False and Q_SERVER.pushing_from("7711") is None,
      Q_EVENTS)

_q_additive = dict(_q_chain)
_q_additive["deletion_mode"] = "additive"
_q_ok2, _q_note2, _q_sent2, _q_refused2 = mod.SyncClientWorker.push_chain(_q_additive)
check("SY-Q9 an Additive chain is turned away at the door: it keeps what it holds whatever its host does, so it has nothing it would lose and no reason to be writing into another machine's folder",
      _q_ok2 is False and _q_sent2 == 0 and "Only a Mirror chain can push" in _q_note2
      and mod.chain_can_push(_q_additive) is False and mod.chain_can_push({"deletion_mode": "mirror"}) is True
      and _q_held(Q_HOST_FOLDER) == ["here.mp3", "new2.mp3", "new3.mp3", "same.mp3"],
      (_q_ok2, _q_note2))

_q_later = dict(_q_chain)
_q_later["last_synced"] = 1750000000.0
_q_ok3, _q_note3, _q_sent3, _q_refused3 = mod.SyncClientWorker.push_chain(_q_later)
check("SY-Q9b a push that found nothing newer than the last sync says exactly that rather than calling a push of nothing a success - the button that asked has to be able to say why it did nothing",
      _q_ok3 is True and _q_sent3 == 0 and _client_layer.nothing_to_push(_q_note3) is True
      and _client_layer.nothing_to_push("Synced successfully (0 updated, 0 removed).") is False
      and _client_layer.nothing_to_push("Pushed to host: 2 file(s) added") is False,
      (_q_ok3, _q_note3))


class _PushApp(_DecisionApp):
    """A window that answers the question a Mirror sync asks before its deletion pass."""

    def __init__(self, answer, code=None):
        super().__init__(answer, code)
        self.push_questions = []

    def ask_push_confirm(self, title, question):
        self.titles.append(title)
        self.push_questions.append(question)
        return self.answer

    def ask_push_code(self, title, host_label):
        self.titles.append(title)
        self.hosts.append(host_label)
        return None


Q_SYNC_HOST = fixture("host taken mid-sync")
audio_file(Q_SYNC_HOST, "shared.mp3", body=b"a track both machines hold", mtime=1600000000.0)
Q_SYNC_DEST = fixture("mirror folder pushed before it was matched")
audio_file(Q_SYNC_DEST, "shared.mp3", body=b"a track both machines hold", mtime=1600000000.0)
audio_file(Q_SYNC_DEST, "justmade.mp3", body=b"made here after the last sync", mtime=1700000000.0)
Q_SYNC_CHAINS = [{"sync_code": "7722", "name": "Mirror Me", "folder_path": str(Q_SYNC_HOST),
                  "max_pushed_files": 5, "push_trusted_ips": ["127.0.0.1"]}]
Q_SYNC_SERVER = mod.SyncHostServer(lambda: Q_SYNC_CHAINS,
                                   on_restore_event_cb=lambda code, ip, event, note: Q_EVENTS.append((code,
                                                                                                      ip, event,
                                                                                                      note)))
Q_SYNC_SERVER._running = True
Q_SYNC_BRIDGE = _restore_bridge(Q_SYNC_SERVER)
_q_sync_chain = _client_chain(Q_SYNC_DEST, Q_SYNC_BRIDGE.getsockname()[1], last_synced=1650000000.0)
_q_sync_chain["sync_code"] = "7722"

_q_app = _PushApp(True)
_q_said = []
_q_ok4, _q_note4, _q_moved4, _q_removed4 = mod.SyncClientWorker.sync_chain(
    _q_sync_chain, status_cb=lambda line: _q_said.append(line),
    push_confirm_cb=_client_layer.make_push_confirm_cb(_q_app, "Mirror Me"),
    push_code_cb=_client_layer.make_push_code_cb(_q_app, "Mirror Me"))
check("SY-Q10 a Mirror sync that is told to push offers the files its own next deletion pass was about to take, re-reads both folders before it deletes anything, and finishes with the file kept at both ends instead of lost at one",
      _q_ok4 is True and _q_removed4 == 0 and _q_moved4 == 0
      and _q_held(Q_SYNC_HOST) == ["justmade.mp3", "shared.mp3"]
      and _q_held(Q_SYNC_DEST) == ["justmade.mp3", "shared.mp3"]
      and _client_layer.files_were_pushed(_q_note4) is True and "1 file(s) added" in _q_note4
      and any("Re-reading the host's index after the push" in line for line in _q_said),
      (_q_ok4, _q_note4, _q_removed4, _q_said))
check("SY-Q10b and the question asked was the one that says what is at stake: which files, in which folder, that the host does not have, and that not answering means this sync deletes them",
      _q_app.titles == ["Sync Chain 'Mirror Me' - Push Files To Host?"]
      and len(_q_app.push_questions) == 1
      and "1 file(s) in this folder are newer than this chain's last sync, and the host does not have them" in _q_app.push_questions[0]
      and "justmade.mp3" in _q_app.push_questions[0]
      and "this sync deletes them from this folder to match the host" in _q_app.push_questions[0]
      and "A push can only add files to a host" in _q_app.push_questions[0],
      (_q_app.titles, _q_app.push_questions))

(Q_SYNC_HOST / "justmade.mp3").unlink()
audio_file(Q_SYNC_DEST, "justmade.mp3", body=b"made here after the last sync", mtime=1700000000.0)
_q_app2 = _PushApp(False)
_q_ok5, _q_note5, _q_moved5, _q_removed5 = mod.SyncClientWorker.sync_chain(
    dict(_q_sync_chain), push_confirm_cb=_client_layer.make_push_confirm_cb(_q_app2, "Mirror Me"))
check("SY-Q10c answering no leaves the sync to do what a Mirror sync has always done - the file this machine made is deleted out of it to match the host - and says nothing about a push that never happened",
      _q_ok5 is True and _q_removed5 == 1
      and _q_held(Q_SYNC_DEST) == ["shared.mp3"] and _q_held(Q_SYNC_HOST) == ["shared.mp3"]
      and _client_layer.files_were_pushed(_q_note5) is False and "added" not in _q_note5
      and len(_q_app2.push_questions) == 1,
      (_q_ok5, _q_note5, _q_removed5))

audio_file(Q_SYNC_DEST, "justmade.mp3", body=b"made here after the last sync", mtime=1700000000.0)
_q_app3 = _PushApp(True)
_q_add_sync = dict(_q_sync_chain)
_q_add_sync["deletion_mode"] = "additive"
_q_ok6, _q_note6, _q_moved6, _q_removed6 = mod.SyncClientWorker.sync_chain(
    _q_add_sync, push_confirm_cb=_client_layer.make_push_confirm_cb(_q_app3, "Mirror Me"))
check("SY-Q10d an Additive sync is never interrupted with this question at all: it keeps the file whatever its host does, so there is nothing here it would lose and no reason to stop a sync asking about it",
      _q_app3.push_questions == [] and _q_ok6 is True and _q_removed6 == 0
      and "justmade.mp3" in _q_held(Q_SYNC_DEST) and "justmade.mp3" not in _q_held(Q_SYNC_HOST)
      and _client_layer.files_were_pushed(_q_note6) is False,
      (_q_app3.push_questions, _q_held(Q_SYNC_DEST), _q_held(Q_SYNC_HOST)))

Q_BRIDGE.close()
Q_SYNC_BRIDGE.close()

# ===========================================================================
# SY-R: the message a host sends when it comes up, and what a beacon does when it reads one
# ===========================================================================
# Twenty seconds after a machine starts as a host, it puts one message on the network naming the
# chains it advertises, and every machine following one of them runs its normal fetch. What is proved
# here is the message and the reading of it: what it is shaped like on the wire, which codes it is
# allowed to carry, and what the beacon does with one - including a beacon built before this message
# existed, which has to read one and carry on doing what it already did. Same bounds as the rest of
# this suite: loopback sockets only, and the port this message is sent to is an ephemeral one this
# file picked rather than the port the program uses on a real network, so no check here puts a packet
# on the LAN.
send_lan_sync_request = seam.original("send_lan_sync_request")
UDPBeaconBroadcaster = seam.original("UDPBeaconBroadcaster")


def _spare_loopback_port():
    """A loopback port this file has just been told is free, and has just given back."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


_WIRE_PORT = _spare_loopback_port()
_WIRE = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
_WIRE.bind(("127.0.0.1", _WIRE_PORT))
_WIRE.settimeout(6.0)
_EXPECTED_HOST_IP = seam.read("get_local_ip")()

with seam.patched("UDP_BEACON_PORT", _WIRE_PORT), \
     seam.patched("get_broadcast_addresses", lambda: ["127.0.0.1"]):
    send_lan_sync_request(63350, ["2468", "  ", "1357"])
    _wire_packet = json.loads(_WIRE.recv(2048).decode("utf-8"))

check("SY-R1 the message is its own type, carries the port a client would fetch from and the address it was sent from, and drops the codes that are nothing",
      _wire_packet.get("type") == "CHAIN_SYNC_REQUEST"
      and _wire_packet.get("sync_codes") == ["2468", "1357"]
      and _wire_packet.get("tcp_port") == 63350
      and _wire_packet.get("host_ip") == _EXPECTED_HOST_IP, _wire_packet)
check("SY-R2 it names chains rather than files: nothing about what changed, because what it says is only that a host is ready",
      set(_wire_packet.keys()) == {"type", "sync_codes", "tcp_port", "host_ip"}, _wire_packet)

_QUIET_PORT = _spare_loopback_port()
_QUIET = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
_QUIET.bind(("127.0.0.1", _QUIET_PORT))
_QUIET.settimeout(0.8)
with seam.patched("UDP_BEACON_PORT", _QUIET_PORT), \
     seam.patched("get_broadcast_addresses", lambda: ["127.0.0.1"]):
    send_lan_sync_request(0, ["2468"])
    send_lan_sync_request(63350, [])
    send_lan_sync_request(63500, ["   ", ""])
    _anything_arrived = True
    try:
        _QUIET.recv(2048)
    except socket.timeout:
        _anything_arrived = False
_QUIET.close()
check("SY-R3 a host with no port open, or with no chain to name, sends nothing at all - there is nothing yet for a client to fetch from",
      not _anything_arrived, _anything_arrived)

_PRIVATE_ONLY_CHAINS = [{"sync_code": "1111", "name": "Open"},
                        {"sync_code": "2222", "name": "Study", "visible": False}]
_ADVERTISED_PORT = _spare_loopback_port()
_ADVERTISED = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
_ADVERTISED.bind(("127.0.0.1", _ADVERTISED_PORT))
_ADVERTISED.settimeout(6.0)
with seam.patched("UDP_BEACON_PORT", _ADVERTISED_PORT), \
     seam.patched("get_broadcast_addresses", lambda: ["127.0.0.1"]):
    send_lan_sync_request(63350, [c["sync_code"] for c in advertised_chains(_PRIVATE_ONLY_CHAINS)])
    _advertised_packet = json.loads(_ADVERTISED.recv(2048).decode("utf-8"))
_ADVERTISED.close()
check("SY-R4 what the host hands this message is the same list it hands its beacon, so a private chain's code is not put on the network by a message sent every time somebody starts yt-msd",
      _advertised_packet.get("sync_codes") == ["1111"], _advertised_packet)

def _send_until_read(send_once, saw_it, attempts=20):
    """Keep sending a packet until the beacon says it read one.

    The beacon binds its socket in the thread that was just started, and a UDP packet sent to a port
    nothing is listening on yet is simply lost. Re-sending until the answer arrives is how this check
    waits for that bind without assuming how long it took.
    """
    for _ in range(attempts):
        send_once()
        if wait_for(saw_it, 0.4):
            return True
    return saw_it()


_REQUEST_SEEN = []
_BEACON_PORT = _spare_loopback_port()
with seam.patched("UDP_BEACON_PORT", _BEACON_PORT):
    _beacon = UDPBeaconBroadcaster(
        lambda: [], lambda: 0,
        on_chain_updated_cb=lambda code: None,
        on_sync_request_cb=lambda host_ip, codes: _REQUEST_SEEN.append((host_ip, codes)))
    _beacon.start()
    _beacon_sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def _send_request():
        _beacon_sender.sendto(json.dumps({
            "type": "CHAIN_SYNC_REQUEST", "sync_codes": ["2468", "  ", "1357"],
            "host_ip": "192.0.2.9", "tcp_port": 63350}).encode("utf-8"), ("127.0.0.1", _BEACON_PORT))

    _read_request = _send_until_read(_send_request, lambda: _REQUEST_SEEN)
    _beacon_sender.close()
    _beacon.stop()
check("SY-R5 a beacon reads the new message and hands over the address it came from and the codes named in it, the blanks dropped on the way",
      _read_request and _REQUEST_SEEN[0][0] == "127.0.0.1" and _REQUEST_SEEN[0][1] == ["2468", "1357"],
      _REQUEST_SEEN)
_beacon_init = seam.original("UDPBeaconBroadcaster").__init__
_beacon_args = _beacon_init.__code__.co_varnames[:_beacon_init.__code__.co_argcount]
check("SY-R6 the new answer is one optional argument added at the end of the beacon's own arguments, so nothing built the way a beacon was built before it still builds",
      _beacon_args[-1] == "on_sync_request_cb"
      and len(_beacon_init.__defaults__ or ()) == 2
      and UDPBeaconBroadcaster(lambda: [], lambda: 0).on_sync_request_cb is None,
      _beacon_args)

_OLD_SEEN = []
_OLD_PORT = _spare_loopback_port()
with seam.patched("UDP_BEACON_PORT", _OLD_PORT):
    _old_beacon = UDPBeaconBroadcaster(lambda: [], lambda: 0,
                                       on_chain_updated_cb=lambda code: _OLD_SEEN.append(code))
    _old_beacon.start()
    _old_sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def _send_old_pair():
        # Both messages in one attempt, so the attempt that proves the beacon was listening is the
        # same attempt that offered it the message it has no answer for.
        _old_sender.sendto(json.dumps({"type": "CHAIN_SYNC_REQUEST", "sync_codes": ["2468"],
                                       "tcp_port": 63350}).encode("utf-8"), ("127.0.0.1", _OLD_PORT))
        _old_sender.sendto(json.dumps({"type": "CHAIN_UPDATED", "sync_code": "2468"}).encode("utf-8"),
                           ("127.0.0.1", _OLD_PORT))

    _old_update = _send_until_read(_send_old_pair, lambda: _OLD_SEEN)
    _old_alive = _old_beacon._thread is not None and _old_beacon._thread.is_alive()
    _old_sender.close()
    _old_beacon.stop()
check("SY-R7 a beacon built before this message existed reads one and carries on: it ignores what it has no answer for, and still delivers the chain updates it has always delivered",
      _old_beacon.on_sync_request_cb is None and _old_update and _old_alive
      and set(_OLD_SEEN) == {"2468"}, (_OLD_SEEN, _old_alive))

# ===========================================================================
# SY-S: a client asking its host for its settings, and the host answering
# ===========================================================================
# Every other command a chain speaks moves tracks. This one moves the settings the machine at the other
# end runs with, and it is proved here at the wire and nowhere else: that a settings request is answered
# only for a client that has already authenticated for a chain this machine hosts; that a host with no
# settings, or with no answer for this command at all, says which it is instead of sending something
# empty; that a config grown past the size a settings message is meant to be is refused rather than
# streamed; that the client half brings the settings back without reading or writing a single file here;
# and that none of this disturbs the commands a chain has always spoken. Which of the settings that
# arrive belong on the machine that received them is decided by the window that asked, and probe_windows
# proves those rules against a settings file of its own.
S_HOST_FOLDER = fixture("settings borrowed from")
audio_file(S_HOST_FOLDER, "one.mp3", body=b"a track on the machine being copied from")

S_SETTINGS = {"format": "m4a", "bitrate": "320", "mode": "Light", "accent": "Green", "volume": 42,
              "last_search": "keyboard sonata", "recent_playlists": [{"name": "Morning"}],
              "download_threads": 7, "normalization_mode": "on",
              "folders": ["D:\\Host Downloads"], "local_folders": ["D:\\Host Music"],
              "local_current_path": "D:\\Host Music",
              "hosted_chains": [{"id": "hc_7002", "sync_code": "7002", "name": "Bedroom"}],
              "client_chains": [], "sync_settings": {"auto_sync_interval_mins": 11},
              "session_data": {"search_results": [{"video_id": "abc"}], "playback_index": 2,
                               "local_current_path": "D:\\Host Music", "local_playback_index": 4}}

S_ACTIVITY = []
S_SERVER = mod.SyncHostServer(
    lambda: [{"sync_code": "5150", "name": "Settings Host", "folder_path": str(S_HOST_FOLDER)}],
    on_client_activity_cb=lambda code, ip, note: S_ACTIVITY.append((code, note)),
    get_config_cb=lambda: dict(S_SETTINGS))
# The handler is driven over a connected loopback pair, as every other host in this suite is: start()
# would bind SYNC_PORT_START..END, and a yt-msd genuinely running is already listening there.
S_SERVER._running = True


def _s_round(server, requests, expecting, client_ip="192.168.1.50"):
    """Send these commands to a host's own handler and read back the answers it gives.

    A host that turns a client away answers once and then closes, which is what it has always done at
    the door: the reading below records that as no answer at all rather than treating it as a failure
    of the test, because a refused machine that could still knock a second time is the thing worth
    knowing about.
    """
    client, server_side = _loopback_pair()
    worker = threading.Thread(target=lambda: server._handle_client(server_side, client_ip), daemon=True)
    worker.start()
    for message in requests:
        try:
            mod.send_json_msg(client, message)
        except OSError:
            break
    answers = []
    for _ in range(expecting):
        try:
            answers.append(mod.recv_json_msg(client, timeout=8.0))
        except OSError:
            answers.append(None)
    client.close()
    worker.join(8)
    return answers


answers = _s_round(S_SERVER, [{"cmd": "GET_CONFIG"}], 1)
check("SY-S1 a settings request from a machine that never said which chain it belongs to is turned away before it is told anything about this one",
      answers[0] == {"status": "ERROR", "reason": "Expected AUTH command"}, answers)

answers = _s_round(S_SERVER, [{"cmd": "AUTH", "sync_code": "5150"},
                              {"cmd": "GET_CONFIG", "sync_code": "5150"}], 2)
check("SY-S2 a client that authenticated for a hosted chain is answered with the host's settings whole, keys and all - including the host's own chains and folders, because which of them describe the machine that asked is that machine's decision and not this one's",
      answers[1].get("status") == "CONFIG" and answers[1].get("config") == S_SETTINGS, answers[1])
check("SY-S3 a host says out loud that its settings were taken, which is the only notice the machine being copied from ever gets",
      ("5150", "Sent its settings") in S_ACTIVITY, S_ACTIVITY)

answers = _s_round(S_SERVER, [{"cmd": "AUTH", "sync_code": "9999"}], 1)
check("SY-S4 a sync code this machine does not host is refused at the door, by name, before anything about this machine is said",
      answers[0] is not None and answers[0].get("status") == "ERROR"
      and "9999" in answers[0].get("reason", ""), answers)
answers = _s_round(S_SERVER, [{"cmd": "AUTH", "sync_code": "9999"},
                              {"cmd": "GET_CONFIG", "sync_code": "9999"}], 2)
check("SY-S4b and the settings behind that door are never reached: a client turned away at the AUTH is answered once and then let go, so it is not left free to keep asking for what it was refused",
      not any((answer or {}).get("status") == "CONFIG" for answer in answers), answers)

S_NO_CALLBACK = mod.SyncHostServer(lambda: [{"sync_code": "5150", "name": "Old Host",
                                             "folder_path": str(S_HOST_FOLDER)}])
S_NO_CALLBACK._running = True
S_EMPTY = mod.SyncHostServer(lambda: [{"sync_code": "5150", "name": "Blank Host",
                                       "folder_path": str(S_HOST_FOLDER)}],
                             get_config_cb=lambda: {})
S_EMPTY._running = True
S_RAISING = mod.SyncHostServer(lambda: [{"sync_code": "5150", "name": "Broken Host",
                                         "folder_path": str(S_HOST_FOLDER)}],
                               get_config_cb=lambda: (_ for _ in ()).throw(OSError("settings unreadable")))
S_RAISING._running = True
S_OVERSIZED = mod.SyncHostServer(lambda: [{"sync_code": "5150", "name": "Huge Host",
                                           "folder_path": str(S_HOST_FOLDER)}],
                                 get_config_cb=lambda: {"folders": ["x" * 4096] * (
                                     _lan_layer.MAX_CONFIG_PAYLOAD_BYTES // 4096 + 2)})
S_OVERSIZED._running = True

answers = _s_round(S_NO_CALLBACK, [{"cmd": "AUTH", "sync_code": "5150"}, {"cmd": "GET_CONFIG"},
                                   {"cmd": "GET_INDEX"}], 3)
check("SY-S5 a host built without anything to answer with - a harness, a probe, a window from before this command existed - refuses it by name and carries on serving every command it always served",
      answers[1].get("status") == "ERROR" and "does not offer its settings" in answers[1].get("reason", "")
      and answers[2].get("status") == "OK" and [f["name"] for f in answers[2].get("files") or []] == ["one.mp3"],
      answers)

answers = _s_round(S_EMPTY, [{"cmd": "AUTH", "sync_code": "5150"}, {"cmd": "GET_CONFIG"}], 2)
check("SY-S6 a host with nothing written yet says it has no settings, rather than sending an empty config that would read at the other end as a machine with no settings at all",
      answers[1].get("status") == "ERROR" and "no settings written yet" in answers[1].get("reason", ""),
      answers)

answers = _s_round(S_RAISING, [{"cmd": "AUTH", "sync_code": "5150"}, {"cmd": "GET_CONFIG"},
                               {"cmd": "PING"}], 3)
check("SY-S7 settings this machine cannot read are reported as that, and the chain is left open: a settings request that fails is not a way to close a client out",
      answers[1].get("status") == "ERROR" and "could not be read" in answers[1].get("reason", "")
      and answers[2].get("status") == "PONG", answers)

answers = _s_round(S_OVERSIZED, [{"cmd": "AUTH", "sync_code": "5150"}, {"cmd": "GET_CONFIG"}], 2)
check("SY-S8 a settings file past the size a settings message is meant to be is refused instead of put on the wire, so a config that has swallowed something enormous costs nobody a stalled connection",
      answers[1].get("status") == "ERROR" and "too large" in answers[1].get("reason", ""), answers)

# The client half, end to end: a host kept on a spare loopback port, and a chain record that knows
# nothing about it but the address and the port to knock on. This is the ordinary door a sync walks
# through and the ordinary name it says, with one more question after them - so the check worth having
# is that a fetch leaves this machine's own disk exactly as it found it.
S_FOLDER = fixture("settings arriving at")
audio_file(S_FOLDER, "mine.mp3", body=b"a track this machine already had")
S_LISTENER = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
S_LISTENER.bind(("127.0.0.1", 0))
S_LISTENER.listen(4)
S_PORT = S_LISTENER.getsockname()[1]
S_STOP = threading.Event()


def _s_accept(server, listener):
    while not S_STOP.is_set():
        try:
            connection, (peer_ip, _peer_port) = listener.accept()
        except OSError:
            break
        threading.Thread(target=lambda c=connection, ip=peer_ip: server._handle_client(c, ip),
                         daemon=True).start()


S_ACCEPT_THREAD = threading.Thread(target=lambda: _s_accept(S_SERVER, S_LISTENER), daemon=True)
S_ACCEPT_THREAD.start()

S_CHAIN = {"id": "cc_5150", "sync_code": "5150", "name": "Settings Host Mirror",
           "folder_path": str(S_FOLDER), "last_known_host_ip": "127.0.0.1", "host_port": S_PORT}
_ok, _note, _payload = _client_layer.SyncClientWorker.fetch_config(S_CHAIN)
check("SY-S9 the client half reaches its host and brings its settings back whole, saying where they came from",
      _ok is True and _payload == S_SETTINGS and "Settings received from 127.0.0.1:" in _note,
      (_ok, _note, _payload))
check("SY-S10 and it learns what the host calls this chain on the way in, the same way a sync does, because a settings request is answered by the same AUTH a sync makes",
      S_CHAIN.get("host_chain_name") == "Settings Host", S_CHAIN)
check("SY-S11 a settings import reads no file and writes no file on the machine that asked for it",
      sorted(held.name for held in S_FOLDER.iterdir()) == ["mine.mp3"]
      and (S_FOLDER / "mine.mp3").read_bytes() == b"a track this machine already had",
      [held.name for held in S_FOLDER.iterdir()])

S_ORPHAN = {"id": "cc_9999", "sync_code": "9999", "name": "Nowhere Chain",
            "folder_path": str(S_FOLDER), "last_known_host_ip": "127.0.0.1", "host_port": S_PORT}
_ok2, _note2, _payload2 = _client_layer.SyncClientWorker.fetch_config(S_ORPHAN)
check("SY-S12 a host that does not know the code asked about says so, and the answer is that refusal rather than a set of empty settings",
      _ok2 is False and "9999" in _note2 and _payload2 is None, (_ok2, _note2))

S_LISTENER2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
S_LISTENER2.bind(("127.0.0.1", 0))
S_LISTENER2.listen(4)
S_PORT2 = S_LISTENER2.getsockname()[1]
S_ACCEPT_THREAD2 = threading.Thread(target=lambda: _s_accept(S_NO_CALLBACK, S_LISTENER2), daemon=True)
S_ACCEPT_THREAD2.start()
S_NO_CB_CHAIN = {"id": "cc_5150", "sync_code": "5150", "name": "Old Host Mirror",
                 "folder_path": str(S_FOLDER), "last_known_host_ip": "127.0.0.1", "host_port": S_PORT2}
_ok3, _note3, _payload3 = _client_layer.SyncClientWorker.fetch_config(S_NO_CB_CHAIN)
S_STOP.set()
S_LISTENER.close()
S_LISTENER2.close()
check("SY-S13 a host that will not hand its settings over is reported as refusing, and nothing is handed back to be written anywhere",
      _ok3 is False and "refused" in _note3.lower() and "Nothing here was changed" in _note3
      and _payload3 is None, (_ok3, _note3))

answers = _s_round(S_SERVER, [{"cmd": "AUTH", "sync_code": "5150"}, {"cmd": "GET_CONFIG"},
                              {"cmd": "GET_INDEX"},
                              {"cmd": "PULL_FILE", "filename": "one.mp3"}], 4)
check("SY-S14 asking for settings in the middle of a chain's ordinary conversation leaves that conversation exactly as it was: the index still arrives, and the track after it still arrives",
      answers[1].get("status") == "CONFIG" and answers[2].get("status") == "OK"
      and answers[3].get("status") == "SENDING" and answers[3].get("filename") == "one.mp3", answers)

S_THREAD_INIT = seam.original("HostConfigFetchThread").__init__
S_THREAD_ARGS = S_THREAD_INIT.__code__.co_varnames[:S_THREAD_INIT.__code__.co_argcount]
check("SY-S15 the fetch runs on a thread of its own and not as another mode of a sync, so a chain's card is never asked to show the progress of something that moves no files",
      S_THREAD_ARGS == ("self", "chain_config") and "mode" not in S_THREAD_ARGS
      and hasattr(_client_layer.SyncClientWorker, "fetch_config")
      and "yt_msd.sync.client" in seam.owned_by("HostConfigFetchThread"),
      (S_THREAD_ARGS, seam.owned_by("HostConfigFetchThread")))
check("SY-S16 every name this added is a module-level one the seam reaches, and the size a settings message may reach lives beside the other sync timings",
      all(seam.owned_by(name) and any(owner != mod.__name__ for owner in seam.owned_by(name))
          for name in ("MAX_CONFIG_PAYLOAD_BYTES", "HostConfigFetchThread", "SyncHostServer",
                       "SyncClientWorker")),
      {name: seam.owned_by(name) for name in ("MAX_CONFIG_PAYLOAD_BYTES", "HostConfigFetchThread")})
S_HOST_INIT = seam.original("SyncHostServer").__init__
S_HOST_ARGS = S_HOST_INIT.__code__.co_varnames[:S_HOST_INIT.__code__.co_argcount]
check("SY-S17 the answer is one optional argument added at the end of the host's own arguments, so a host built the way a host was built before it still builds - and answers a settings request with a refusal",
      S_HOST_ARGS[-1] == "get_config_cb" and len(S_HOST_INIT.__defaults__ or ()) == 3
      and all(server.get_config_cb is None for server in (HOST_SERVER, P_SERVER, Q_SERVER)),
      (S_HOST_ARGS, S_HOST_INIT.__defaults__))

# ===========================================================================
# SY-L: the seam this suite reaches the program through
# ===========================================================================
_real_discovery = seam.original("discover_host_on_lan")
_real_local_ip = seam.original("get_local_ip")
seam.restore("discover_host_on_lan")
seam.restore("get_local_ip")
check("SY-L1 the sync layer is reached by name, not by a copy of it: the patch found the module that owns the name",
      seam.owned_by("discover_host_on_lan") and seam.owned_by("write_sync_tag_file")
      and seam.owned_by("SyncClientWorker"),
      (seam.owned_by("discover_host_on_lan"), seam.owned_by("SyncClientWorker")))
check("SY-L2 restoring hands the program back its own function in every module that holds it",
      seam.read("discover_host_on_lan") is _real_discovery
      and mod.discover_host_on_lan is _real_discovery
      and mod.get_local_ip is _real_local_ip
      and not seam.is_patched("discover_host_on_lan"), seam.owned_by("discover_host_on_lan"))
check("SY-L3 every sync name this suite drives is a module-level name the seam can find at all",
      all(seam.owners(name) for name in ("write_sync_tag_file", "read_sync_tag_file",
                                         "parse_sync_timestamp", "format_sync_timestamp",
                                         "find_tagged_sync_folders_on_drive", "SyncConfigManager",
                                         "SyncHostServer", "SyncRemovableWorker",
                                         "HostFolderWatcher", "get_drive_io_lock",
                                         "delete_confirm_limit", "make_sync_decision_cb",
                                         "make_restore_code_cb", "SYNC_DECISION_KEEP",
                                         "SYNC_DECISION_DELETE", "SYNC_DECISION_RESTORE",
                                         "restore_code_shape", "issue_restore_code",
                                         "pending_restore_request", "take_restore_offer",
                                         "cancel_restore_offer", "restore_target",
                                         "host_was_rebuilt", "restore_was_left_undone",
                                         "deletions_were_declined", "_HostKeepalive",
                                         "host_chain_is_visible", "hello_reply",
                                         "advertised_chains", "probe_replies", "HostScanner",
                                         "adapter_addresses", "local_scan_scope",
                                         "subnet_targets", "send_lan_sync_request",
                                         "UDPBeaconBroadcaster", "UDP_BEACON_PORT",
                                         "HOST_UP_SYNC_REQUEST_DELAY_MS")))
try:
    seam.patch("sync_chain_that_is_not_in_the_program", lambda: None)
    _refused_unowned = False
except seam.SeamError:
    _refused_unowned = True
check("SY-L4 a name nothing in the program owns is refused out loud instead of quietly doing nothing",
      _refused_unowned)

_self_tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
_stray_writes = [f"line {node.lineno}" for node in ast.walk(_self_tree)
                 if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign))
                 and any(isinstance(target, ast.Attribute)
                         and isinstance(target.value, ast.Name)
                         and target.value.id == "mod"
                         for target in ([node.target] if not isinstance(node, ast.Assign)
                                        else node.targets))]
check("SY-L5 this file writes nothing into the entry point by hand - every replacement goes through the seam",
      _stray_writes == [], _stray_writes)
check("SY-L6 the seam maps the package modules too, so a wave that moves a name needs no change in this file",
      "yt_msd.deps" in seam.owned_by("Observer") + seam.owned_by("vlc"),
      (seam.owned_by("Observer"), seam.owned_by("vlc")))

shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)
check("SY-L7 every folder this suite wrote is gone again", not FIXTURE_ROOT.exists())

print(f"{CHECKS - len(FAILS)} / {CHECKS} checks passed")
if FAILS:
    print("FAILED: " + "; ".join(FAILS))
    raise SystemExit(1)







