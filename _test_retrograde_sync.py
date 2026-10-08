"""Checks for the retrograde removable-sync failsafe.

Pulls the tag-file helpers and SyncRemovableWorker straight out of
GUI Source Code/yt-msd-gui.pyw with ast, so what is tested is the text that
actually ships, then drives them with a fake client folder and a fake drive.

Development only: nothing in the app imports this file.
"""
import ast
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

ROOT = os.path.dirname(os.path.abspath(__file__))
PYW = os.path.join(ROOT, "GUI Source Code", "yt-msd-gui.pyw")

WANTED_CONSTS = {"AUDIO_EXTENSIONS", "SYNC_TAG_FILENAME", "SYNC_TAG_TIME_FORMATS",
                 "SYNC_RETROGRADE_GRACE_SECONDS"}
WANTED_FUNCS = {"filter_audio_files", "write_sync_tag_file", "read_sync_tag_file",
                "parse_sync_timestamp", "format_sync_timestamp", "drive_last_synced_timestamp"}
WANTED_CLASSES = {"SyncRemovableWorker"}

with open(PYW, "r", encoding="utf-8") as fh:
    tree = ast.parse(fh.read())

picked = []
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in WANTED_FUNCS:
        picked.append(node)
    elif isinstance(node, ast.ClassDef) and node.name in WANTED_CLASSES:
        picked.append(node)
    elif isinstance(node, ast.Assign):
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if names and all(n in WANTED_CONSTS for n in names):
            picked.append(node)

found = set()
for node in picked:
    if isinstance(node, ast.Assign):
        found.update(t.id for t in node.targets if isinstance(t, ast.Name))
    else:
        found.add(node.name)
missing = (WANTED_CONSTS | WANTED_FUNCS | WANTED_CLASSES) - found
if missing:
    raise SystemExit("could not find in the source: %s" % ", ".join(sorted(missing)))

# ── What the worker talks to, stubbed ─────────────────────────────────────────
_DRIVE_LOCKS = {}


class StubClientWorker:
    """Stands in for the network half. host_reachable decides whether it answers."""
    host_reachable = True
    host_calls = 0
    host_files = []

    @staticmethod
    def sync_chain(chain_config: dict, status_cb=None, progress_cb=None):
        StubClientWorker.host_calls += 1
        if not StubClientWorker.host_reachable:
            return False, "Could not find active host for Sync Code 1234 on local network.", 0, 0
        dest = Path(chain_config.get('folder_path', ''))
        dest.mkdir(parents=True, exist_ok=True)
        for name in dest.glob("*.mp3"):
            name.unlink()
        for name in StubClientWorker.host_files:
            (dest / name).write_text("host copy", encoding="utf-8")
        return True, "Synced successfully (%d updated)." % len(StubClientWorker.host_files), len(StubClientWorker.host_files), 0


class StubConfigManager:
    def __init__(self):
        self.hosted_chains = []
        self.client_chains = []
        self.save_calls = 0

    def save(self):
        self.save_calls += 1


ns = {
    "os": os, "time": time, "threading": threading, "Path": Path,
    "Dict": Dict, "List": List, "Optional": Optional, "Tuple": Tuple,
    "Callable": Callable, "Union": Union,
    "SyncClientWorker": StubClientWorker,
    "SyncConfigManager": StubConfigManager,
    "get_drive_io_lock": lambda p: _DRIVE_LOCKS.setdefault(str(Path(p).anchor), threading.RLock()),
    "make_throttled_progress_cb": lambda cb, min_interval=0.15: cb,
}
exec(compile(ast.Module(body=picked, type_ignores=[]), PYW, "exec"), ns)

Worker = ns["SyncRemovableWorker"]
parse_ts = ns["parse_sync_timestamp"]
format_ts = ns["format_sync_timestamp"]
drive_ts_of = ns["drive_last_synced_timestamp"]
read_tag = ns["read_sync_tag_file"]
grace = ns["SYNC_RETROGRADE_GRACE_SECONDS"]

failures = []
checked = 0


def check(label, got, want):
    global checked
    checked += 1
    if got != want:
        failures.append("%s\n     got:  %r\n     want: %r" % (label, got, want))


def stamp(offset_seconds):
    """A last_synced value in the exact form TAG.yaml is written in."""
    return time.strftime("%m-%d-%Y %H:%M:%S", time.localtime(time.time() + offset_seconds))


def write_drive_tag(folder, last_synced_str, style="Mirror"):
    Path(folder).mkdir(parents=True, exist_ok=True)
    (Path(folder) / "TAG.yaml").write_text(
        "# marker\nsync_code: 1234\n\nchain_name: Test Chain\n\n"
        "sync_style: %s\n\nlast_synced: %s\n\nlast_synced_by: Client\n\n"
        "parent_sync_folder: \n" % (style, last_synced_str), encoding="utf-8")


def put_files(folder, names):
    Path(folder).mkdir(parents=True, exist_ok=True)
    for name in names:
        (Path(folder) / name).write_text("audio", encoding="utf-8")


def run_case(client_last_synced, drive_tag_offset, drive_files, client_files,
             host_reachable, host_files, answer, with_confirm=True, del_mode="mirror"):
    """One removable sync against a throwaway client folder and a throwaway drive."""
    tmp = Path(tempfile.mkdtemp(prefix="ytmsd_retro_"))
    client_dir = tmp / "client"
    drive_dir = tmp / "drive" / "Playlist"
    StubClientWorker.host_reachable = host_reachable
    StubClientWorker.host_calls = 0
    StubClientWorker.host_files = host_files

    put_files(client_dir, client_files)
    put_files(drive_dir, drive_files)
    expected_tag = ""
    if drive_tag_offset is not None:
        tag_when = stamp(drive_tag_offset)
        write_drive_tag(drive_dir, tag_when)
        expected_tag = tag_when

    cfg = StubConfigManager()
    cc = {"sync_code": "1234", "name": "Test Chain", "folder_path": str(client_dir),
          "last_synced": client_last_synced, "deletion_mode": del_mode}
    cfg.client_chains.append(cc)
    rc = {"id": "rc_1234_test", "sync_code": "1234", "name": "Test Chain",
          "folder_path": str(drive_dir), "deletion_mode": del_mode}

    asked = []

    def _confirm(message):
        asked.append(message)
        return answer

    ok, msg, _transferred, _deleted = Worker.sync_removable_chain(
        rc, cfg, confirm_cb=(_confirm if with_confirm else None))
    result = {
        "ok": ok, "msg": msg, "asked": asked,
        "host_calls": StubClientWorker.host_calls,
        "drive_files": sorted(p.name for p in drive_dir.glob("*.mp3")),
        "tag_last_synced": (read_tag(drive_dir) or {}).get("last_synced", ""),
        "expected_tag": expected_tag,
        "client_last_synced": cc.get("last_synced"),
        "save_calls": cfg.save_calls,
    }
    shutil.rmtree(tmp, ignore_errors=True)
    return result


now = time.time()

# ── Timestamp parsing ──────────────────────────────────────────────────────────
check("epoch float", parse_ts(now) == now, True)
check("epoch as text", parse_ts(str(now)) == now, True)
check("zero means never", parse_ts(0), None)
check("empty string", parse_ts(""), None)
check("a bool is not a date", parse_ts(True), None)
check("garbage", parse_ts("last week"), None)
check("TAG.yaml form parses", parse_ts("03-14-2026 09:30:00"),
      time.mktime(time.strptime("03-14-2026 09:30:00", "%m-%d-%Y %H:%M:%S")))
check("unpadded day parses", parse_ts("3-4-2026 9:05:00"),
      time.mktime(time.strptime("03-04-2026 09:05:00", "%m-%d-%Y %H:%M:%S")))
check("never formats as never", format_ts(None), "never")
check("format round-trip", format_ts(parse_ts("03-14-2026 09:30:00")), "03-14-2026 09:30:00")

tmp_tag = Path(tempfile.mkdtemp(prefix="ytmsd_tag_"))
try:
    write_drive_tag(tmp_tag, "03-14-2026 09:30:00")
    check("drive tag date read back", drive_ts_of(tmp_tag),
          time.mktime(time.strptime("03-14-2026 09:30:00", "%m-%d-%Y %H:%M:%S")))
    check("no tag file means no date", drive_ts_of(tmp_tag / "nothing"), None)
finally:
    shutil.rmtree(tmp_tag, ignore_errors=True)

# ── The guard itself ───────────────────────────────────────────────────────────
# Client is a week behind a drive that still holds its tracks, host is offline.
r = run_case(client_last_synced=now - 7 * 86400, drive_tag_offset=-3600,
             drive_files=["newer-a.mp3", "newer-b.mp3"], client_files=["old-a.mp3"],
             host_reachable=False, host_files=[], answer=False)
check("stale client + offline host asks the user", len(r["asked"]), 1)
check("the question names both dates and the track count",
      all(s in r["asked"][0] for s in ("Drive last synced:", "This PC last synced:", "2 track(s)")), True)
check("answering No skips the sync", (r["ok"], r["msg"].startswith("Sync skipped")), (False, True))
check("answering No leaves the drive alone", r["drive_files"], ["newer-a.mp3", "newer-b.mp3"])
check("answering No leaves the drive's tag alone", r["tag_last_synced"], r["expected_tag"])
check("answering No does not stamp the client", r["client_last_synced"], now - 7 * 86400)
check("answering No wrote no config", r["save_calls"], 0)

# Same setup, but the user accepts the older version of the chain.
r = run_case(client_last_synced=now - 7 * 86400, drive_tag_offset=-3600,
             drive_files=["newer-a.mp3", "newer-b.mp3"], client_files=["old-a.mp3"],
             host_reachable=False, host_files=[], answer=True)
check("answering Yes syncs the older copy onto the drive",
      (r["ok"], r["drive_files"]), (True, ["old-a.mp3"]))
check("a sync that ran rewrote the drive tag", r["tag_last_synced"] != r["expected_tag"], True)

# A client that is current is never asked about anything.
r = run_case(client_last_synced=now - 60, drive_tag_offset=-3600,
             drive_files=["old-a.mp3"], client_files=["current-a.mp3", "current-b.mp3"],
             host_reachable=False, host_files=[], answer=False)
check("current client is not asked", r["asked"], [])
check("current client syncs straight through",
      (r["ok"], r["drive_files"]), (True, ["current-a.mp3", "current-b.mp3"]))

# A drive that only looks a few seconds ahead is clock drift, not a newer chain.
r = run_case(client_last_synced=now - 5, drive_tag_offset=0,
             drive_files=["a.mp3"], client_files=["b.mp3"],
             host_reachable=False, host_files=[], answer=False)
check("inside the grace window is not asked", r["asked"], [])
check("the grace window is a minute", grace, 60)

# An empty drive has nothing to lose, so a stale client is not stopped.
r = run_case(client_last_synced=now - 7 * 86400, drive_tag_offset=0,
             drive_files=[], client_files=["old-a.mp3"],
             host_reachable=False, host_files=[], answer=False)
check("empty drive is not asked", r["asked"], [])
check("empty drive just syncs", (r["ok"], r["drive_files"]), (True, ["old-a.mp3"]))

# A client that has never synced at all is assumed stale.
r = run_case(client_last_synced=0, drive_tag_offset=-3600,
             drive_files=["newer-a.mp3"], client_files=["old-a.mp3"],
             host_reachable=False, host_files=[], answer=False)
check("never-synced client is treated as stale", len(r["asked"]), 1)
check("never-synced client is stopped by default", (r["ok"], r["drive_files"]), (False, ["newer-a.mp3"]))

# Stale client, but the host answers: refresh first, ask no one, drive ends current.
r = run_case(client_last_synced=now - 7 * 86400, drive_tag_offset=-3600,
             drive_files=["newer-a.mp3"], client_files=["old-a.mp3"],
             host_reachable=True, host_files=["host-a.mp3", "host-b.mp3"], answer=False)
check("stale client goes to the host first", r["host_calls"], 1)
check("a host that answers means no prompt", r["asked"], [])
check("the host's version is what reaches the drive",
      (r["ok"], r["drive_files"]), (True, ["host-a.mp3", "host-b.mp3"]))
check("a host sync that worked stamps the client", r["client_last_synced"] > now - 5, True)
check("stamping the client is persisted", r["save_calls"] >= 1, True)

# No one to ask (a caller with no GUI behind it) means the drive is left alone.
r = run_case(client_last_synced=now - 7 * 86400, drive_tag_offset=-3600,
             drive_files=["newer-a.mp3"], client_files=["old-a.mp3"],
             host_reachable=False, host_files=[], answer=True, with_confirm=False)
check("no way to ask means no retrograde write", (r["ok"], r["drive_files"]), (False, ["newer-a.mp3"]))

print("checked %d things" % checked)
if failures:
    print("\n".join(failures))
    print("%d FAILED" % len(failures))
    sys.exit(1)
print("all good")


