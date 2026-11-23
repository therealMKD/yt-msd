"""The sync-chain regression harness.

Sections SY-A..SY-L cover the sync half of `GUI Source Code/yt-msd-gui.pyw`: the TAG.yaml marker
a chain leaves on removable media and what comes back when it is read, the two forms `last_synced`
takes (an epoch in the chain dict, a wall-clock string in TAG.yaml) and the clock grace between
them, the drive scan that looks for tagged folders, sync-chain persistence inside the shared
gui_config.json, the length-prefixed socket protocol both ends of a chain speak, the host server's
answers to a client, the client worker's decisions about what to download and what to delete, the
removable-media worker and the failsafe that stops a newer drive from being rolled back to an
older copy, and the hosted folder watcher's debounce.

Recipe (AI Readme section 20): same as probe_playback - the `.pyw` is copied to a throwaway `.py`
in this folder's `copy/` and imported, and the functions are driven directly. Every replacement
goes through harness_seam.py, never by writing into the entry point.

This suite does two things probe_playback does not, and both are bounded:

  - it opens sockets, but only on 127.0.0.1 - a listening socket bound to loopback, and connected
    pairs. No LAN address is bound, nothing is broadcast, and LAN discovery itself is patched out
    through the seam so no check can put a probe packet on the network.
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
                                         "HostFolderWatcher", "get_drive_io_lock")))
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







