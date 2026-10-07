"""Runs the real start_batch_download() from the source against a fake MainApp.

The method is lifted out of GUI Source Code/yt-msd-gui.pyw with ast and executed
with a stub yt-dlp, so what is exercised is the code that ships: the per-track
retries, the same-title lock, the "a clean exit means it downloaded" rule and
the verification pass.
"""
import ast
import os
import re
import shutil
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
PYW = os.path.join(ROOT, "GUI Source Code", "yt-msd-gui.pyw")

WANTED_FUNCS = {
    "_clean_reported_path", "_match_reported_path", "_title_match_key",
    "_title_matches_filename", "_is_permanent_download_error", "_sanitize_filename",
}
WANTED_ASSIGNS = {
    "_YTDLP_FINAL_PATH_PATTERNS", "_YTDLP_STAGED_PATH_PATTERNS",
    "_PERMANENT_DOWNLOAD_ERROR_MARKERS", "DOWNLOAD_ITEM_ATTEMPTS",
}

with open(PYW, "r", encoding="utf-8") as fh:
    tree = ast.parse(fh.read())

picked = []
batch_method = None
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in WANTED_FUNCS:
        picked.append(node)
    elif isinstance(node, ast.Assign):
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if names and all(n in WANTED_ASSIGNS for n in names):
            picked.append(node)
    elif isinstance(node, ast.ClassDef):
        for sub in node.body:
            if isinstance(sub, ast.FunctionDef) and sub.name == "start_batch_download":
                batch_method = sub
if batch_method is None:
    raise SystemExit("start_batch_download() not found in the source")

cls = ast.ClassDef(name="Harness", bases=[], keywords=[], body=[batch_method], decorator_list=[])
ast.fix_missing_locations(cls)

tmp = tempfile.mkdtemp(prefix="ytmsd_queue_test_")

calls = {"count": {}, "by_title": {}, "max_concurrent_title": 0}
calls_lock = threading.Lock()
tagged = []
untagged = []

# vid -> how it behaves. Chosen to cover the ways the queue used to skip a song.
SCRIPT = {
    "ok1": {"kind": "ok"},
    # Used to be skipped: the file lands on disk, but yt-dlp never names it in
    # a form the GUI could read.
    "silent": {"kind": "silent"},
    # Used to be skipped: a throttled request. Only the third try gets through.
    "throttled": {"kind": "flaky", "fails": 2,
                  "error": "ERROR: unable to download video data: HTTP Error 403: Forbidden"},
    # A failure no retry can fix: must be tried once, not three times.
    "dead": {"kind": "flaky", "fails": 99, "error": "ERROR: Video unavailable"},
    # Same title as dup2: must not be downloaded at the same moment.
    "dup1": {"kind": "ok", "title": "Same Song (Live): Remaster)"},
    "dup2": {"kind": "ok", "title": "Same Song (Live): Remaster)"},
}


def fake_run_yt_dlp_download(args, progress_cb=None, cancelled_cb=None):
    vid = args[-1].split("v=")[1]
    folder = args[args.index("--output") + 1].split("/%(title)s")[0]
    spec = SCRIPT[vid]
    title = spec.get("title") or ("Track " + vid)
    with calls_lock:
        calls["count"][vid] = calls["count"].get(vid, 0) + 1
        n = calls["count"][vid]
        calls["by_title"][title] = calls["by_title"].get(title, 0) + 1
        calls["max_concurrent_title"] = max(calls["max_concurrent_title"],
                                            calls["by_title"][title])
    try:
        time.sleep(0.15)
        if spec["kind"] == "flaky" and n <= spec["fails"]:
            raise RuntimeError(spec["error"])
        path = os.path.join(folder, _sanitize_filename(title) + ".m4a")
        with open(path, "wb") as fh:
            fh.write(b"x" * 4096)
        if spec["kind"] == "silent":
            return None
        return path
    finally:
        with calls_lock:
            calls["by_title"][title] -= 1


def fake_add_placeholder_tag(path):
    tagged.append(path)


def fake_remove_placeholder_tag(path):
    untagged.append(path)


class Sig:
    def __init__(self):
        self.emitted = []
        self.lock = threading.Lock()

    def emit(self, *a):
        with self.lock:
            self.emitted.append(a)


class Combo:
    def __init__(self, v):
        self.v = v

    def currentText(self):
        return self.v


class Btn:
    def __getattr__(self, name):
        return lambda *a, **k: None


class Harness:
    pass


ns = {
    "os": os, "sys": sys, "re": re, "shlex": __import__("shlex"), "threading": threading,
    "run_yt_dlp_download": fake_run_yt_dlp_download,
    "_add_placeholder_tag": fake_add_placeholder_tag,
    "_remove_placeholder_tag": fake_remove_placeholder_tag,
    "find_yt_dlp_executable": lambda refresh=False: "yt-dlp.exe",
}
exec(compile(ast.Module(body=picked + [cls], type_ignores=[]), PYW, "exec"), ns)

app = ns["Harness"]()
app.is_downloading = False
app.cancel_download = False
app.download_threads = 4
app.use_custom_args = False
app.custom_args = ""
app._batch_total_count = 0
app._last_downloaded_files = []
app.save_config = lambda: None
app.dl_btn = Btn()
app.cancel_btn = Btn()
app.path_combo = Combo(tmp)
app.format_combo = Combo("m4a")
app.bitrate_combo = Combo("320")
app.active_downloads = {}
app.active_downloads_lock = threading.Lock()
app.status_signal = Sig()
app.queue_status_changed_signal = Sig()
app.dl_progress_signal = Sig()
app._dl_progress_percent = lambda vid, pct: None
app.queue_items = [{"video": {"id": vid,
                              "title": SCRIPT[vid].get("title") or ("Track " + vid)},
                    "status": "Pending"} for vid in SCRIPT]

# fake_run_yt_dlp_download lives in this module, so it needs the real
# _sanitize_filename from the source in this module's globals too.
globals()['_sanitize_filename'] = ns['_sanitize_filename']

app.start_batch_download()

deadline = time.time() + 120
while time.time() < deadline:
    if any(("Batch complete" in str(a[0])) or ("Download cancelled" in str(a[0]))
           for a in app.status_signal.emitted):
        break
    time.sleep(0.1)
else:
    raise SystemExit("the batch never finished")

time.sleep(0.3)

problems = []
statuses = {q["video"]["id"]: q["status"] for q in app.queue_items}
expected = {"ok1": "Finished", "silent": "Finished", "throttled": "Finished",
            "dead": "Pending", "dup1": "Finished", "dup2": "Finished"}
for vid, want in expected.items():
    if statuses.get(vid) != want:
        problems.append("%s: status %r, expected %r" % (vid, statuses.get(vid), want))

counts = calls["count"]
if counts.get("dead", 0) != 1:
    problems.append("dead: tried %s times, expected 1 (a permanent error must not be retried)"
                    % counts.get("dead"))
if counts.get("throttled", 0) != 3:
    problems.append("throttled: tried %s times, expected 3 (a transient error must be retried)"
                    % counts.get("throttled"))
if counts.get("ok1", 0) != 1:
    problems.append("ok1: tried %s times, expected 1 (a good download must not be re-run)"
                    % counts.get("ok1"))
if counts.get("silent", 0) != 1:
    problems.append("silent: tried %s times, expected 1 (a download that reported no path "
                    "must not be re-run)" % counts.get("silent"))
if calls["max_concurrent_title"] > 1:
    problems.append("the same-title pair was downloaded at the same time "
                    "(max concurrent for one title = %d)" % calls["max_concurrent_title"])

files = sorted(os.listdir(tmp))
same = [f for f in files if "Same Song" in f]
if len(same) != 1:
    problems.append("the shared-title track produced %d files instead of 1: %s" % (len(same), files))
if not any("Track silent" in f for f in files):
    problems.append("the download that reported no path was not found on disk")
if len(tagged) < 5:
    problems.append("placeholder tags applied %d times, expected one per finished track" % len(tagged))
left_tagged = sorted(set(tagged) - set(untagged))
if left_tagged:
    problems.append("placeholder tags were not stripped from: %s" % left_tagged)

final = [str(a[0]) for a in app.status_signal.emitted if "Batch complete" in str(a[0])]
if not final:
    problems.append("no final status line was emitted")
elif "1 unavailable" not in final[-1]:
    problems.append("final status was %r, expected it to name the unavailable track" % final[-1])
if not app._last_downloaded_files:
    problems.append("_last_downloaded_files was left empty, so the renamer has nothing to run on")
if len(app._last_downloaded_files) != len(set(app._last_downloaded_files)):
    problems.append("_last_downloaded_files contains duplicates")

shutil.rmtree(tmp, ignore_errors=True)

if problems:
    print("FAILED:")
    for p in problems:
        print("  - " + p)
    print("attempt counts: %s" % counts)
    sys.exit(1)

print("start_batch_download() behaved correctly.")
print("  attempts per track: %s" % counts)
print("  files written: %d, tagged: %d, untagged: %d" % (len(files), len(tagged), len(untagged)))



