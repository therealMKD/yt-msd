"""The yt-msd GUI regression harness.

Sections A-Z cover the playback behaviour of `GUI Source Code/yt-msd-gui.pyw`: the read-ahead
prefetch and what it hands the player, stream resolution, the three "Stop after current" states
and what a finished track does under each, the results-list scroll reset, the one-shot stop a new
search arms for the track already playing, the stream-liveness watchdog and its resume grace, and
what a track that runs to its end is held as - a replay.

Recipe (AI Readme section 20): importlib cannot import a `.pyw`, so the `.pyw` is copied to a
throwaway `.py` in this folder's `copy/`, imported, and its `MainApp` methods are driven against
harness objects holding only the attributes the method under test touches. Nothing in this suite
uses a temp folder outside the repo, shows a window, touches the network, or reads or writes the
music library. `copy/` is rebuilt on every run and is safe to delete, and the whole folder is
gitignored.
"""
import ast
import importlib.util
import os
import re
import shutil
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
TMP_PY = os.path.join(COPY_DIR, "yt_msd_under_test.py")
shutil.copyfile(SRC, TMP_PY)
_spec = importlib.util.spec_from_file_location("yt_msd_under_test", TMP_PY)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

# Every replacement this suite makes goes through the seam below, never by writing
# into the entry point. Writing there lands on a re-exported copy that nothing
# calls once a name has moved into yt_msd.*, and the check then passes while
# testing nothing. harness_seam.py explains it, and refuses a name nothing owns.
import harness_seam as seam

seam.install(mod, SRC_DIR)

_REAL_RESOLVE = seam.original("resolve_stream_url")
_REAL_YTDLP_JSON = seam.original("run_yt_dlp_json")

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


def wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class Sig:
    """A Qt signal stand-in. `emit` records the call; a slot put in with `connect` is called
    back the same way __init__ connects a real signal to its handler."""

    def __init__(self):
        self.calls = []
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def emit(self, *a):
        self.calls.append(a)
        for slot in self.slots:
            slot(*a)


class FakeScrollBar:
    def __init__(self, start=700):
        self.value = start
        self.set_values = []

    def setValue(self, v):
        self.set_values.append(v)
        self.value = v


class FakeArea:
    def __init__(self):
        self.sb = FakeScrollBar()

    def verticalScrollBar(self):
        return self.sb


class _FakeStyle:
    def unpolish(self, w):
        pass

    def polish(self, w):
        pass


class FakeBtn:
    def __init__(self):
        self.text = ""
        self.props = {}
        self.tooltips = []
        self.enabled = True

    def setText(self, t):
        self.text = t

    def setProperty(self, k, v):
        self.props[k] = v

    def setToolTip(self, t):
        self.tooltips.append(t)

    def setEnabled(self, v):
        self.enabled = v

    def style(self):
        return _FakeStyle()


class FakeLabel:
    def __init__(self):
        self.text_value = ""

    def setText(self, t):
        self.text_value = t

    def text(self):
        return self.text_value

    def setStyleSheet(self, s):
        pass


class FakeSlider:
    def __init__(self):
        self.value = 0

    def isSliderDown(self):
        return False

    def blockSignals(self, b):
        pass

    def setValue(self, v):
        self.value = v


class FakeVBox:
    def __init__(self):
        self.widgets = []

    def count(self):
        return 0

    def takeAt(self, i):
        class _Nothing:
            def widget(self):
                return None
        return _Nothing()



class FakeMedia:
    def __init__(self, url):
        self.url = url
        self.options = []

    def add_option(self, o):
        self.options.append(o)


class FakeInstance:
    def __init__(self):
        self.medias = []

    def media_new(self, url):
        media = FakeMedia(url)
        self.medias.append(media)
        return media


class FakePlayer:
    def __init__(self, state, ms=0, length=0):
        self.state = state
        self.ms = ms
        self.length = length
        self.media = None
        self.played = 0
        self.paused = None
        self.positions = []
        self.times = []

    def get_state(self):
        return self.state

    def get_time(self):
        return self.ms

    def get_length(self):
        return self.length

    def get_position(self):
        return (self.ms / self.length) if self.length else 0.0

    def set_media(self, m):
        self.media = m

    def play(self):
        self.played += 1

    def pause(self):
        # toggle_playback() calls this. The fake reports the state libVLC reports for a paused
        # media, which is what the stream watchdog is read against.
        self.paused = True
        self.state = mod.vlc.State.Paused
        return 0

    def stop(self):
        self.stops = getattr(self, 'stops', 0) + 1
        self.state = mod.vlc.State.Stopped

    def set_pause(self, v):
        self.paused = bool(v)

    def audio_set_mute(self, v):
        pass

    def set_position(self, p):
        self.positions.append(p)
        return 0

    def set_time(self, ms):
        self.times.append(ms)
        self.ms = ms
        return 0

    def is_playing(self):
        return self.state == mod.vlc.State.Playing


def results(count=5):
    return [{"id": f"vid{i}", "title": f"Track {i}"} for i in range(count)]


def make_app(res=None, index=0, vid="vid0", shuffled=False, history=None, mode=0,
             shadow_play=True):
    """A MainApp that never ran __init__, holding only what these methods touch."""
    app = mod.MainApp.__new__(mod.MainApp)
    app.save_calls = 0
    app.save_config = lambda: None  # a click stores the state; this fake has no widgets to read
    app.search_results = results() if res is None else res
    app.playback_index = index
    app.current_video_id = vid
    app.current_playing_title = "Track 0"
    app.is_shuffled = shuffled
    app.shuffle_history = list(history if history is not None else [index])
    app.is_playing = True
    app.stop_after_current = mode
    app._prefetched_streams = {}
    app._prefetch_lock = threading.Lock()
    app._prefetch_busy = set()
    app._prefetch_decision = None
    app._prefetch_trigger_key = None
    app._has_played_current = True
    app._ended_trigger = False
    app._pending_fetch_id = vid
    app._vlc_ready = True
    app.vlc_instance = FakeInstance()
    app.vlc_player = FakePlayer(mod.vlc.State.Playing, ms=0, length=100000)
    app.play_btn = FakeBtn()
    app.stop_after_btn = FakeBtn()
    app.time_label = FakeLabel()
    app.progress_slider = FakeSlider()
    app.search_btn = FakeBtn()
    app.results_area = FakeArea()
    app.results_vbox = FakeVBox()
    app.show_thumbnails = False
    app.queue_items = []
    app.status_messages = []
    app.playback_started_signal = Sig()
    app.search_failed_signal = Sig()
    app.stream_refreshed_signal = Sig()
    app.stream_fetch_failed_signal = Sig()
    app._stream_skip_streak = 0
    # __init__ connects stream_fetch_failed_signal to _on_stream_fetch_failed. A section that
    # wants that step to actually happen - AH - connects it on its own fixture; the sections
    # written before it only ask what bg_fetch emitted.
    # The stream-liveness watchdog state, as __init__ sets it. Nothing is loaded on a fresh
    # harness, which is also how the app starts.
    app._loaded_stream = None
    app._loaded_stream_at = None
    app._stream_seen_ms = -1
    app._stream_moved_at = None
    app._stream_resuming = False
    app._stream_dead = False
    app._stream_refetching = False
    app._stream_refetch_attempts = 0
    app._stream_renew_started_at = None
    app._pending_stream_seek_frac = None
    app._pending_stream_seek_ms = None
    app._pending_stream_pause = False
    app._pending_stream_seek_at = None
    app.started = []
    app._on_status_update = lambda text, playing, color: app.status_messages.append((text, playing, color))
    if shadow_play:
        app.play_result = lambda video, paused_at_start=False, from_nav=False: app.started.append((video, from_nav))
    return app


RESOLVE_CALLS = []
RESOLVE_HOLD = [0.0]      # seconds a fake resolve spends fetching, set per test


def patch_resolve(url="https://example.test/prefetched", user_agent="probe-agent", fail=False,
                  fail_for=()):
    """Fake `resolve_stream_url`. `fail` refuses every id; `fail_for` refuses only the ids
    listed, which is how a list holding one row that has no stream is built."""
    refused = set(fail_for or ())

    def fake_resolve(vid_id):
        if RESOLVE_HOLD[0]:
            time.sleep(RESOLVE_HOLD[0])
        RESOLVE_CALLS.append(vid_id)
        if fail or vid_id in refused:
            raise RuntimeError("simulated stream failure")
        return url, user_agent
    seam.patch("resolve_stream_url", fake_resolve)


def unpatch():
    seam.restore("resolve_stream_url")
    seam.restore("run_yt_dlp_json")
    RESOLVE_CALLS.clear()


    def addWidget(self, w):
        self.widgets.append(w)


# ---------------------------------------------------------------------------
# SEAM. Where a replacement actually lands.
#
#     Every other check in this file only proves something if this section holds.
#     A fake the program never reaches still lets its check pass, quietly, and a
#     suite full of checks that pass while testing nothing is worse than no suite.
#     So the suite checks its own instrument here, including the one hazard the
#     split creates: a name that now lives in two places at once.
# ---------------------------------------------------------------------------
print("=" * 72)
print("SEAM. where a replacement lands")


def _seam_marker(args, timeout=None):
    return "reached"


def _seam_refuses(name):
    """True when patching this name is refused rather than silently doing nothing."""
    try:
        seam.patch(name, None)
    except seam.SeamError:
        return True
    seam.restore(name)
    return False


def _entry_point_writes(path):
    """Names this suite file writes into the entry point, read out of its syntax."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            continue
        targets = list(node.targets) if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                    and target.value.id == "mod"):
                found.append(target.attr)
    return found


_seam_holders = seam.owners("run_yt_dlp_json")
check("SEAM1 a name can already be held by several modules at once - the whole problem",
      len(seam.owners("subprocess")) >= 2 and mod in seam.owners("subprocess"),
      seam.owned_by("subprocess"))
seam.patch("run_yt_dlp_json", _seam_marker)
check("SEAM2 a patch lands on every module holding that name",
      all(getattr(m, "run_yt_dlp_json") is _seam_marker for m in _seam_holders),
      seam.owned_by("run_yt_dlp_json"))
check("SEAM3 and on the entry point too, because MainApp still calls it from there",
      mod in _seam_holders and mod.run_yt_dlp_json(["-J"]) == "reached")
seam.restore("run_yt_dlp_json")
check("SEAM4 restoring hands each module back the value it held for itself",
      all(getattr(m, "run_yt_dlp_json") is _REAL_YTDLP_JSON for m in _seam_holders))
check("SEAM5 a name nothing owns is refused instead of a patch that does nothing",
      _seam_refuses("run_yt_dlp_json_typo"))

_seam_real_subprocess = seam.original("subprocess")
_seam_subprocess = seam.partial_module(_seam_real_subprocess, Popen=lambda *a, **k: None)
check("SEAM6 a stand-in keeps every name the suite did not ask it to replace",
      _seam_subprocess.run is _seam_real_subprocess.run
      and _seam_subprocess.DEVNULL is _seam_real_subprocess.DEVNULL
      and _seam_subprocess.PIPE is _seam_real_subprocess.PIPE
      and _seam_subprocess.Popen is not _seam_real_subprocess.Popen)
seam.patch("subprocess", _seam_subprocess)
check("SEAM7 a replacement reaches across the package boundary, not just the entry point",
      all(getattr(m, "subprocess") is _seam_subprocess for m in seam.owners("subprocess"))
      and "yt_msd.audio.probe" in seam.owned_by("subprocess"),
      seam.owned_by("subprocess"))
seam.restore("subprocess")
check("SEAM8 and the code that was never meant to be faked has the real thing back",
      all(getattr(m, "subprocess") is _seam_real_subprocess for m in seam.owners("subprocess")))

_seam_moved = seam.owners("measure_loudness")
check("SEAM9 a moved name is held by its module and by every re-export, all the same object",
      mod in _seam_moved and len(_seam_moved) >= 2
      and len({getattr(m, "measure_loudness") for m in _seam_moved}) == 1,
      seam.owned_by("measure_loudness"))

_seam_stray = {p.name: _entry_point_writes(p) for p in sorted(Path(HERE).glob("*.py"))}
_seam_stray = {k: v for k, v in _seam_stray.items() if v}
check("SEAM10 nothing left in this suite drives the program by writing into the entry point",
      not _seam_stray, _seam_stray)

print("=" * 72)
print("A. module constants and stream resolution")

check("A1 the prefetch trigger is 30 seconds before the end", mod.PREFETCH_SECONDS_BEFORE_END == 30)
check("A2 the prefetch cache holds four resolved stream URLs at most", mod.PREFETCH_CACHE_LIMIT == 4, mod.PREFETCH_CACHE_LIMIT)
check("A3 a prefetched stream URL is trusted for fifteen minutes", mod.PREFETCH_URL_MAX_AGE == 15 * 60, mod.PREFETCH_URL_MAX_AGE)
check("A4 the stop-after states are off/once/always", (mod.STOP_AFTER_OFF, mod.STOP_AFTER_ONCE, mod.STOP_AFTER_ALWAYS) == (0, 1, 2))
check("A5 every state has a stylesheet name", sorted(mod.STOP_AFTER_STATE_NAMES.values()) == ["always", "off", "once"])
check("A6 every state has a label", all(m in mod.STOP_AFTER_LABELS for m in (0, 1, 2)))
check("A7 every state has a tooltip", all(m in mod.STOP_AFTER_TOOLTIPS for m in (0, 1, 2)))
_args = mod.stream_cli_args()
check("A8 stream resolution asks yt-dlp for JSON", "-J" in _args)
check("A9 stream resolution never drags in a playlist", "--no-playlist" in _args)
check("A10 the prefetch uses the same client the player always used",
      "youtube:player_client=android" in " ".join(_args))


def fake_ytdlp_direct(args, timeout=None):
    return {"url": "https://example.test/direct", "http_headers": {"User-Agent": "ua-1"}}


def fake_ytdlp_formats(args, timeout=None):
    return {"formats": [{"url": "https://x/video-only", "acodec": "none", "vcodec": "avc1"},
                        {"url": "https://x/audio-only", "acodec": "mp4a.40.5", "vcodec": "none"}]}


def fake_ytdlp_empty(args, timeout=None):
    return {"formats": []}


seam.patch("run_yt_dlp_json", fake_ytdlp_direct)
_u, _ua = _REAL_RESOLVE("vidA")
check("A11 a direct stream URL is used when yt-dlp offers one", _u == "https://example.test/direct", _u)
check("A12 the user agent yt-dlp asked for is carried along", _ua == "ua-1", _ua)
seam.patch("run_yt_dlp_json", fake_ytdlp_formats)
_u, _ = _REAL_RESOLVE("vidB")
check("A13 an audio format is preferred over a video-only one", _u == "https://x/audio-only", _u)
seam.patch("run_yt_dlp_json", fake_ytdlp_empty)

_raised = False
try:
    _REAL_RESOLVE("vidC")
except Exception:
    _raised = True
check("A14 a track with no playable stream raises instead of returning nothing", _raised)
unpatch()

print("B. previewing the next track (no state is changed)")
app = make_app()
_idx, _hist = app.playback_index, list(app.shuffle_history)
got = app._next_playback_preview()
check("B1 the preview names the track that follows", got is not None and got[0] == 1 and got[1]["id"] == "vid1", got)
check("B2 the preview does not move playback_index", app.playback_index == _idx)
check("B3 the preview does not touch shuffle history", app.shuffle_history == _hist)
check("B4 nothing is previewed after the last track", make_app(index=4, vid="vid4")._next_playback_preview() is None)
check("B5 nothing is previewed with an empty list", make_app(res=[])._next_playback_preview() is None)
app_sh = make_app(shuffled=True, history=[0, 2])
pv = app_sh._next_playback_preview()
check("B6 a shuffled preview only offers unplayed tracks", pv is not None and pv[0] in (1, 3, 4), pv)
check("B7 a shuffled preview leaves the history alone", app_sh.shuffle_history == [0, 2], app_sh.shuffle_history)
app_full = make_app(shuffled=True, history=[0, 1, 2, 3, 4], index=4, vid="vid4")
pv2 = app_full._next_playback_preview()
check("B8 a shuffled list recycles rather than refusing to continue", pv2 is not None and pv2[0] != 4, pv2)
app_local = make_app()
app_local.current_video_id = "local"
app_local.local_playback_index = 0
app_local.current_local_items = [{"is_dir": True, "path": "D:\\music"},
                                 {"is_dir": False, "path": "D:\\music\\one.mp3"},
                                 {"is_dir": False, "path": "D:\\music\\two.mp3"}]
_items, _is_local = app_local._playback_source_items()
check("B9 local playback steps through audio files only", _is_local and len(_items) == 2, _items)
lpv = app_local._next_playback_preview()
check("B10 a local preview follows the folder order", lpv is not None and lpv[0] == 1 and lpv[1]["path"].endswith("two.mp3"), lpv)


patch_resolve()
print("C. the prefetch runs on its own thread")
app = make_app(index=0, vid="vid0")
app._maybe_prefetch_next_track()
check("C1 a successor is decided for the track now playing",
      app._prefetch_decision is not None and app._prefetch_decision[0] == "vid0", app._prefetch_decision)
check("C2 the decision names the next track in the list",
      app._prefetch_decision[1] == 1 and app._prefetch_decision[2]["id"] == "vid1")
check("C3 the next track's stream is resolved", wait_for(lambda: "vid1" in app._prefetched_streams))
check("C4 exactly one resolution happens", RESOLVE_CALLS == ["vid1"], RESOLVE_CALLS)
check("C5 the resolved URL is held ready", app._prefetched_streams["vid1"][0] == "https://example.test/prefetched")
check("C6 the resolved user agent is held ready", app._prefetched_streams["vid1"][1] == "probe-agent")
check("C7 the track now playing was never re-resolved", "vid0" not in RESOLVE_CALLS)
for _ in range(60):
    app._maybe_prefetch_next_track()
check("C8 the 16 ms player timer cannot re-trigger the same track", RESOLVE_CALLS == ["vid1"], RESOLVE_CALLS)
check("C9 the worker cleans up after itself", wait_for(lambda: not app._prefetch_busy), app._prefetch_busy)
RESOLVE_CALLS.clear()
app_armed = make_app(mode=mod.STOP_AFTER_ONCE)
for _ in range(5):
    app_armed._maybe_prefetch_next_track()
check("C10 a track armed to stop after is read ahead for anyway - a manual Next costs the same",
      wait_for(lambda: "vid1" in RESOLVE_CALLS) and app_armed._prefetch_decision is not None,
      RESOLVE_CALLS)
RESOLVE_CALLS.clear()
app_always = make_app(mode=mod.STOP_AFTER_ALWAYS)
for _ in range(5):
    app_always._maybe_prefetch_next_track()
check("C16 the same on 'always': the read-ahead is never what stops the list",
      wait_for(lambda: "vid1" in RESOLVE_CALLS) and app_always._prefetch_decision is not None,
      RESOLVE_CALLS)
RESOLVE_CALLS.clear()
app_local2 = make_app()
app_local2.current_video_id = "local"
app_local2._maybe_prefetch_next_track()
check("C11 local files need no prefetch", RESOLVE_CALLS == [], RESOLVE_CALLS)
RESOLVE_CALLS.clear()
make_app(res=[])._maybe_prefetch_next_track()
check("C12 an empty search list prefetches nothing", RESOLVE_CALLS == [])
RESOLVE_CALLS.clear()
patch_resolve(fail=True)
_crashed = False
app_bad = make_app(index=0, vid="vid0")
try:
    app_bad._maybe_prefetch_next_track()
except Exception as exc:
    _crashed = True
check("C13 a failed prefetch never surfaces as an error", not _crashed)
check("C14 a failed prefetch leaves nothing behind",
      wait_for(lambda: not app_bad._prefetch_busy) and not app_bad._prefetched_streams)
check("C15 a failed prefetch is simply resolved again when the track is played",
      app_bad._take_prefetched_stream("vid1") is None)
patch_resolve(fail=False)


print("D. handing the prefetched stream to the player")
app = make_app()
app._prefetched_streams["vid9"] = ("https://example.test/stream", "agent-9", time.monotonic())
handed = app._take_prefetched_stream("vid9")
check("D1 the cached stream is handed over as (url, user agent, how old it already is)",
      handed[0] == "https://example.test/stream" and handed[1] == "agent-9" and handed[2] < 1.0, handed)
check("D2 a prefetched stream is spent on use", app._take_prefetched_stream("vid9") is None)
check("D3 a track nobody prefetched has nothing cached", app._take_prefetched_stream("no-such-id") is None)
app._prefetched_streams["old"] = ("https://example.test/stale", "agent", time.monotonic() - mod.PREFETCH_URL_MAX_AGE - 5)
check("D4 an expired stream URL is refused", app._take_prefetched_stream("old") is None)
check("D5 an expired entry is dropped rather than kept", "old" not in app._prefetched_streams)
app_cache = make_app()
for n in range(8):
    app_cache._prefetch_stream_worker(f"fill{n}")
wait_for(lambda: len(app_cache._prefetched_streams) >= mod.PREFETCH_CACHE_LIMIT)
check("D6 the prefetch cache cannot grow without bound",
      len(app_cache._prefetched_streams) <= mod.PREFETCH_CACHE_LIMIT, len(app_cache._prefetched_streams))

print("E. play_result uses the prefetched stream instead of yt-dlp")
RESOLVE_CALLS.clear()
app = make_app(shadow_play=False)
app._prefetched_streams["vid0"] = ("https://example.test/prefetched", "probe-agent", time.monotonic())
app.play_result(app.search_results[0])
check("E1 a prefetched track starts without another yt-dlp run",
      wait_for(lambda: app.vlc_instance.medias) and RESOLVE_CALLS == [], RESOLVE_CALLS)
check("E2 the prefetched URL is the URL VLC is given",
      app.vlc_instance.medias[0].url == "https://example.test/prefetched", app.vlc_instance.medias[0].url)
check("E3 the prefetched user agent travels with it",
      app.vlc_instance.medias[0].options == [":http-user-agent=probe-agent"], app.vlc_instance.medias[0].options)
check("E4 the play button state is still reported to the window",
      wait_for(lambda: app.playback_started_signal.calls) and app.playback_started_signal.calls[0][1] == "vid0",
      app.playback_started_signal.calls)
check("E5 the cache is emptied by being used", app._prefetched_streams == {}, app._prefetched_streams)
RESOLVE_CALLS.clear()
app2 = make_app(shadow_play=False)
app2.play_result(app2.search_results[2])
check("E6 with nothing prefetched the track is resolved as it always was, and that resolution is what VLC is given",
      wait_for(lambda: app2.vlc_instance.medias) and RESOLVE_CALLS == ["vid2"]
      and app2.vlc_instance.medias[0].url == "https://example.test/prefetched",
      (RESOLVE_CALLS, app2.vlc_instance.medias))
RESOLVE_CALLS.clear()
app3 = make_app(shadow_play=False)
app3._prefetch_trigger_key = "vid0"              # the look-ahead has already answered for this track
app3._maybe_prefetch_next_track()
wait_for(lambda: "vid1" in RESOLVE_CALLS)
app3.play_result(app3.search_results[0])         # ... and now the same track is started again
wait_for(lambda: len(app3.playback_started_signal.calls) >= 1)
RESOLVE_CALLS.clear()
app3._maybe_prefetch_next_track()
check("E10 a track started again reads ahead for its own successor instead of riding on the old decision",
      wait_for(lambda: "vid1" in RESOLVE_CALLS), RESOLVE_CALLS)
_play_src = open(SRC, encoding="utf-8").read()     # _source is built later in this file
check("E11 that decision belongs to the track play_result started, whoever started it",
      "self._prefetch_trigger_key = None"
      in _play_src[_play_src.index("def play_result"):][:4000])
check("E12 and the look-ahead asks for a track whatever 'stop after current' is set to",
      "'stop_after_current', STOP_AFTER_OFF)" not in
      _play_src[_play_src.index("def _maybe_prefetch_next_track"):][:1400])

print("F. play_next plays the track that was readied")
RESOLVE_CALLS.clear()
app = make_app(index=0, vid="vid0")
app._prefetch_decision = ("vid0", 2, app.search_results[2])
app.play_next()
check("F1 the readied successor is the track that plays",
      len(app.started) == 1 and app.started[0][0]["id"] == "vid2", app.started)
check("F2 the advance counts as navigation, not a new manual pick", app.started[0][1] is True)
check("F3 playback_index follows the successor", app.playback_index == 2, app.playback_index)
check("F4 the decision is spent", app._prefetch_decision is None)
app_sh = make_app(index=0, vid="vid0", shuffled=True, history=[0])
app_sh._prefetch_decision = ("vid0", 3, app_sh.search_results[3])
app_sh.play_next()
check("F5 a shuffled pick is recorded in the shuffle history",
      app_sh.shuffle_history == [0, 3], app_sh.shuffle_history)
app_stale = make_app(index=0, vid="vid0")
app_stale._prefetch_decision = ("vid0", 2, {"id": "vid-gone", "title": "no longer in the list"})
app_stale.play_next()
check("F6 a successor no longer in the list is refused",
      app_stale.started and app_stale.started[0][0]["id"] == "vid1", app_stale.started)
check("F7 refusing a stale decision falls back to the ordinary next track",
      app_stale.playback_index == 1, app_stale.playback_index)
app_plain = make_app(index=1, vid="vid1")
app_plain.play_next()
check("F8 with no decision play_next behaves exactly as before",
      app_plain.started[0][0]["id"] == "vid2" and app_plain.playback_index == 2, app_plain.started)
app_last = make_app(index=4, vid="vid4")
app_last.play_next()
check("F9 nothing plays after the last track", app_last.started == [], app_last.started)
unpatch()
print("G. 'stop after current' walks off -> once -> always -> off")


class Harness:
    """Real MainApp methods, bound to a plain object holding only what they touch.
    Slicing the functions out of MainApp is how this repo tests window code without
    VLC, a tray icon or a display (AI Readme section 20)."""
    cycle_stop_after_current = mod.MainApp.cycle_stop_after_current
    set_stop_after_current = mod.MainApp.set_stop_after_current
    _update_stop_after_ui = mod.MainApp._update_stop_after_ui
    _finish_stop_after_current = mod.MainApp._finish_stop_after_current
    _reset_results_scroll = mod.MainApp._reset_results_scroll
    invalidate_next_track_prefetch = mod.MainApp.invalidate_next_track_prefetch
    update_player_ui = mod.MainApp.update_player_ui
    _watch_stream_liveness = mod.MainApp._watch_stream_liveness
    _apply_pending_stream_seek = mod.MainApp._apply_pending_stream_seek
    _stream_ended_short = mod.MainApp._stream_ended_short
    _recover_stream_if_possible = mod.MainApp._recover_stream_if_possible
    _renew_loaded_stream = mod.MainApp._renew_loaded_stream
    _stream_needs_renew = mod.MainApp._stream_needs_renew
    _mark_stream_dead = mod.MainApp._mark_stream_dead
    _note_loaded_stream = mod.MainApp._note_loaded_stream
    _loaded_stream_age = mod.MainApp._loaded_stream_age
    _stream_is_moving = mod.MainApp._stream_is_moving
    _stream_is_switching = mod.MainApp._stream_is_switching
    _update_play_button = mod.MainApp._update_play_button
    _hold_finished_track = mod.MainApp._hold_finished_track
    _replay_finished_track = mod.MainApp._replay_finished_track
    _player_media_is_finished = mod.MainApp._player_media_is_finished
    _next_playback_preview = mod.MainApp._next_playback_preview
    _playback_source_items = mod.MainApp._playback_source_items

    def save_config(self):
        """Stand-in for the settings write a stop-after click now performs. The click
        is the one place the state is chosen, so it is the one place it is stored; the
        harness only has to prove it happened and never touches a real file."""
        self.save_calls = getattr(self, 'save_calls', 0) + 1

    def _refresh_playback_highlights(self):
        """No-op. The coloured-row pass was added to update_player_ui() after this harness
        was written, and the harness holds no real rows to colour."""


def harness(state=mod.STOP_AFTER_OFF):
    h = Harness()
    h.save_calls = 0
    h.stop_after_current = state
    h.stop_after_btn = FakeBtn()
    h.play_btn = FakeBtn()
    h.is_playing = True
    h.current_video_id = "vid0"
    h.current_playing_title = "Track 0"
    h.search_results = results()
    h.playback_index = 0
    h.is_shuffled = False
    h.shuffle_history = [0]
    h._prefetch_decision = ("vid0", 1, {"id": "vid1"})
    h._prefetch_trigger_key = "vid0"
    h._prefetched_streams = {"vid1": ("https://example.test/x", "agent", time.monotonic())}
    h._prefetch_lock = threading.Lock()
    h._has_played_current = True
    h._ended_trigger = False
    h.time_label = FakeLabel()
    h.progress_slider = FakeSlider()
    h._loaded_stream = None
    h._loaded_stream_at = None
    h._stream_seen_ms = -1
    h._stream_moved_at = None
    h._stream_dead = False
    h._stream_refetching = False
    h._stream_refetch_attempts = 0
    h._stream_renew_started_at = None
    h._pending_stream_seek_frac = None
    h._pending_stream_seek_ms = None
    h._pending_stream_pause = False
    h._pending_stream_seek_at = None
    h._is_loading_stream = False
    h._pending_fetch_id = None
    h.stream_refreshed_signal = Sig()
    h.advances = []
    h.statuses = []
    h._on_status_update = lambda text, playing, color: h.statuses.append((text, playing, color))
    h.play_next = lambda: h.advances.append(h.playback_index + 1)
    return h


def ended(h):
    """One tick of the player timer with the media reporting that it finished."""
    h._ended_trigger = False
    h._has_played_current = True
    h.is_playing = True
    h.vlc_player = FakePlayer(mod.vlc.State.Ended, ms=100000, length=100000)
    h.update_player_ui()


h = harness()
h.cycle_stop_after_current()
check("G1 one click arms 'stop after this track'", h.stop_after_current == mod.STOP_AFTER_ONCE)
check("G2 the button reports the once state", h.stop_after_btn.props.get("stop_after_state") == "once", h.stop_after_btn.props)
check("G3 the tooltip explains what the state does", "Once" in h.stop_after_btn.tooltips[-1], h.stop_after_btn.tooltips)
check("G4 the status line tells the user", any("once" in s[0] for s in h.statuses), h.statuses)
h.cycle_stop_after_current()
check("G5 a second click leaves it on for every track", h.stop_after_current == mod.STOP_AFTER_ALWAYS)
check("G6 the button reports the always state", h.stop_after_btn.props.get("stop_after_state") == "always", h.stop_after_btn.props)
h.cycle_stop_after_current()
check("G7 one more click turns it off", h.stop_after_current == mod.STOP_AFTER_OFF)
check("G8 the button reports the off state", h.stop_after_btn.props.get("stop_after_state") == "off", h.stop_after_btn.props)
check("G9 the whole cycle is three clicks long", (h.stop_after_current, len(h.statuses)) == (mod.STOP_AFTER_OFF, 3), h.statuses)
h.set_stop_after_current("nonsense")
check("G10 an unknown state falls back to off", h.stop_after_current == mod.STOP_AFTER_OFF)


print("H. what a finished track does under each state")
h = harness(mod.STOP_AFTER_OFF)
ended(h)
check("H1 off: a finished track advances as it always did", h.advances == [1], h.advances)
check("H2 off: the trigger fires once, not on every timer tick",
      h._ended_trigger is True and h._has_played_current is False)
h = harness(mod.STOP_AFTER_ONCE)
ended(h)
check("H3 once: nothing advances", h.advances == [], h.advances)
check("H4 once: playback is left stopped", h.is_playing is False)
check("H6 once: the state reset itself to off", h.stop_after_current == mod.STOP_AFTER_OFF)
check("H7 once: the decided successor is dropped and the read-ahead re-armed for a track started again by hand",
      h._prefetch_decision is None and h._prefetch_trigger_key is None,
      (h._prefetch_decision, h._prefetch_trigger_key))
check("H8 once: the user is told it stopped", any("Stopped after" in s[0] for s in h.statuses), h.statuses)
ended(h)
check("H9 once: after the reset the next finished track advances again", h.advances == [1], h.advances)
h = harness(mod.STOP_AFTER_ALWAYS)
ended(h)
check("H10 always: nothing advances", h.advances == [], h.advances)
check("H11 always: the state stayed armed", h.stop_after_current == mod.STOP_AFTER_ALWAYS)
check("H12 always: the status line says the mode is still on", any("still on" in s[0] for s in h.statuses), h.statuses)
ended(h)
check("H13 always: it keeps stopping after every track",
      h.advances == [] and h.stop_after_current == mod.STOP_AFTER_ALWAYS)
h.cycle_stop_after_current()
ended(h)
check("H14 clicking it off again brings auto-advance back", h.advances == [1], h.advances)
h = harness(mod.STOP_AFTER_ALWAYS)
h.stop_after_btn = None
h._update_stop_after_ui()
check("H15 the state works before the player bar exists", h.stop_after_current == mod.STOP_AFTER_ALWAYS)

print("I. a new search scrolls the results back to the top")
sh = Harness.__new__(Harness)
sh.results_area = FakeArea()
sh.results_area.sb.value = 700
sh._prefetched_streams = {"vid1": ("https://example.test/x", "agent", time.monotonic())}
sh._prefetch_lock = threading.Lock()
sh._prefetch_decision = ("vid0", 1, {"id": "vid1"})
sh._prefetch_trigger_key = "vid0"
check("I1 the scroll position was not already at the top", sh.results_area.sb.value != 0)
sh._reset_results_scroll()
check("I2 the reset puts the pane back at the top", sh.results_area.sb.value == 0, sh.results_area.sb.value)
check("I3 it was the scrollbar that moved", sh.results_area.sb.set_values == [0], sh.results_area.sb.set_values)
sh.invalidate_next_track_prefetch()
check("I4 a fresh list forgets the successor and the URL decided for the old one, and re-arms the read-ahead",
      sh._prefetch_decision is None and sh._prefetched_streams == {} and sh._prefetch_trigger_key is None,
      (sh._prefetch_decision, sh._prefetched_streams, sh._prefetch_trigger_key))
sh_no_area = Harness.__new__(Harness)
sh_no_area.results_area = None
try:
    sh_no_area._reset_results_scroll()
    _i7 = True
except Exception:
    _i7 = False
check("I7 the reset is harmless before the window is built", _i7)

print("J. the wiring the owner will actually click")
# The source is no longer one file. These text checks ask where a rule sits and in what
# order, so they read the entry point first and then every module extracted from it. The
# .pyw comes first so an ordering check between two things that both still live in it
# keeps comparing the positions it has always compared.
def _read_sources():
    texts = [open(SRC, encoding="utf-8").read()]
    pkg = os.path.join(SRC_DIR, "yt_msd")
    for root, _dirs, files in os.walk(pkg):
        for name in sorted(files):
            if name.endswith(".py"):
                texts.append(open(os.path.join(root, name), encoding="utf-8").read())
    return "\n".join(texts)


_source = _read_sources()
check("J1 the player bar gained a Stop After Current button", 'setObjectName("stopAfterBtn")' in _source)
check("J2 the button sits with the other play controls",
      _source.index("c.addWidget(self.shuffle_btn)") < _source.index("c.addWidget(self.stop_after_btn)")
      < _source.index('self.time_label = QLabel("0:00 / 0:00")'))
check("J3 the button click cycles the state", "self.stop_after_btn.clicked.connect(self.cycle_stop_after_current)" in _source)
check("J4 the tray menu gained the option", 'self.tray_menu.addAction(f"Stop After Current' in _source)
check("J5 the tray entry is ticked when armed and cycles on click",
      "stop_act.setChecked(stop_mode != STOP_AFTER_OFF)" in _source
      and "stop_act.triggered.connect(lambda checked=False: self.cycle_stop_after_current())" in _source)
check("J6 a track ending checks the state before advancing", "_finish_stop_after_current()" in _source)
check("J7 the state is drawn in the theme", 'QPushButton#stopAfterBtn[stop_after_state="always"]' in _source)
check("J8 the theme re-applies the state after a colour change",
      "_update_stop_after_ui()" in _source[_source.index("self.setStyleSheet(full_css)"):][:400])
check("J9 perform_search scrolls to the top", "_reset_results_scroll()" in _source[_source.index("def perform_search"):][:700])
check("J10 a new search also drops a stale prefetched successor",
      "self.invalidate_next_track_prefetch()" in _source[_source.index("def _on_search_results"):][:2400])
_caption_match = re.search(r'self\.stop_after_btn = QPushButton\(("[^"]*")\)', _source)
_caption = ast.literal_eval(_caption_match.group(1))
check("J12 the stop-after caption is a real text glyph, not a private-use icon codepoint",
      len(_caption) == 1 and not 0xE000 <= ord(_caption) <= 0xF8FF,
      f"caption=U+{ord(_caption):04X}" if _caption else "no caption")
_rule_at = _source.index('QPushButton#stopAfterBtn {{')
check("J13 the stop-after button names the icon font that owns its caption",
      "font-family: 'Segoe MDL2 Assets';" in _source[_rule_at:_rule_at + 300],
      _source[_rule_at:_rule_at + 300])

check("J11 the prefetch is triggered by the player timer",
      "_maybe_prefetch_next_track()" in _source[_source.index("def update_player_ui"):][:6000])
check("J12a play_result prefers the stream resolved ahead of time",
      "prefetched = self._take_prefetched_stream(vid_id)" in _source)
check("J13a play_result still resolves normally when nothing was prefetched",
      "resolve_stream_url(vid_id)" in _source[_source.index("def play_result"):][:4000])
check("J14 the Cython mirror is regenerated from this file, never edited by hand",
      os.path.exists(os.path.join(os.path.dirname(os.path.dirname(SRC)), "build_gui_cython.py"))
      and os.path.exists(os.path.join(os.path.dirname(SRC), "yt_msd_gui.pyx")))
check("J15 a new search is the only thing that moves the reader back to the top",
      # One call site today: commit f661916 removed the hide-thumbnails paths that used to
      # redraw the list without resetting it, so the count this check used to insist on is gone.
      "def _on_search_results(self, res, is_playlist, reset_view=True):" in _source
      and _source.count("reset_view=False") >= 1
      and "if reset_view:" in _source[_source.index("def _on_search_results"):][:2200])

print("=" * 72)
print("K. the prefetch trigger measured against the player clock")
patch_resolve()
app = make_app(index=0, vid="vid0")
app.vlc_player = FakePlayer(mod.vlc.State.Playing, ms=80000, length=100000)  # 20 s left
RESOLVE_CALLS.clear()
app.update_player_ui()
check("K1 with 20 seconds left the successor is already being resolved",
      wait_for(lambda: "vid1" in RESOLVE_CALLS), RESOLVE_CALLS)
app = make_app(index=0, vid="vid0")
app.vlc_player = FakePlayer(mod.vlc.State.Playing, ms=70000, length=100000)  # exactly 30 s left
RESOLVE_CALLS.clear()
app.update_player_ui()
check("K3 the trigger is exactly 30 seconds before the end",
      wait_for(lambda: "vid1" in RESOLVE_CALLS), RESOLVE_CALLS)
app = make_app(index=0, vid="vid0")
app.vlc_player = FakePlayer(mod.vlc.State.Playing, ms=69999, length=100000)  # 30.001 s left
RESOLVE_CALLS.clear()
app.update_player_ui()
time.sleep(0.35)
check("K4 31 seconds before the end is still too early", RESOLVE_CALLS == [], RESOLVE_CALLS)
app = make_app(index=0, vid="vid0")
app.vlc_player = FakePlayer(mod.vlc.State.Playing, ms=99800, length=100000)  # 0.2 s left
RESOLVE_CALLS.clear()
app.update_player_ui()
check("K5 a track about to end still prefetches", wait_for(lambda: "vid1" in RESOLVE_CALLS), RESOLVE_CALLS)
app = make_app(index=0, vid="vid0")
app.vlc_player = FakePlayer(mod.vlc.State.Playing, ms=100000, length=0)  # length unknown
RESOLVE_CALLS.clear()
app.update_player_ui()
time.sleep(0.35)
check("K6 a track whose length is unknown prefetches nothing", RESOLVE_CALLS == [], RESOLVE_CALLS)
app = make_app(index=0, vid="vid0")
app.vlc_player = FakePlayer(mod.vlc.State.Stopped, ms=95000, length=100000)
RESOLVE_CALLS.clear()
app.update_player_ui()
time.sleep(0.35)
check("K7 a stopped track prefetches nothing", RESOLVE_CALLS == [], RESOLVE_CALLS)
RESOLVE_CALLS.clear()
app_paused = make_app(index=0, vid="vid0")
app_paused.vlc_player = FakePlayer(mod.vlc.State.Paused, ms=95000, length=100000)
app_paused.update_player_ui()
time.sleep(0.35)
check("K8 a paused track prefetches nothing", RESOLVE_CALLS == [], RESOLVE_CALLS)
RESOLVE_CALLS.clear()
app_last = make_app(index=4, vid="vid4")
app_last.vlc_player = FakePlayer(mod.vlc.State.Playing, ms=95000, length=100000)
app_last.update_player_ui()
time.sleep(0.35)
check("K9 the last track of a list prefetches nothing", RESOLVE_CALLS == [], RESOLVE_CALLS)

# K10 to K14: the walk a listener who never touches the player actually takes. K1 to K9 each
# ask about one track; this is a list gone through track by track, which is the case a report
# of "the read-ahead only works for the first one" is about. Every tick here is the real
# update_player_ui(), every changeover is the real play_next() into the real play_result(), and
# the only fake is the player clock and the yt-dlp run.
RESOLVE_CALLS.clear()
app_walk = make_app(index=0, vid="vid0", shadow_play=False)
_walk_reached = []
_walk_keys = []
for _step in (0, 1, 2):
    # A fresh media for the track this step is about to play, as a changeover is, and the
    # stream watchdog as it stands when nothing has been loaded yet.
    app_walk.vlc_player = FakePlayer(mod.vlc.State.Playing, ms=95000, length=100000)
    app_walk._loaded_stream = None
    app_walk._stream_seen_ms = -1
    app_walk._stream_dead = False
    app_walk._has_played_current = True
    app_walk._ended_trigger = False
    app_walk.update_player_ui()                    # the tick twenty seconds from the end
    _walk_keys.append(app_walk._prefetch_trigger_key)
    wait_for(lambda: f"vid{len(_walk_reached) + 1}" in app_walk._prefetched_streams)
    app_walk.vlc_player.state = mod.vlc.State.Ended
    app_walk.vlc_player.ms = 100000
    app_walk.update_player_ui()                    # the tick that finds the track finished
    _expected = len(_walk_reached) + 1
    wait_for(lambda: len(app_walk.playback_started_signal.calls) >= _expected)
    _walk_reached.append(app_walk.playback_started_signal.calls[-1][1])
    app_walk._on_playback_started(*app_walk.playback_started_signal.calls[-1])   # what __init__ connects
check("K10 three tracks in a row each start the track the list says is next",
      _walk_reached == ["vid1", "vid2", "vid3"], (_walk_reached, app_walk.playback_index))
check("K11 and each of them was resolved once, by the read-ahead, before it was needed",
      sorted(RESOLVE_CALLS) == ["vid1", "vid2", "vid3"], RESOLVE_CALLS)
check("K12 the stream each changeover handed the player is the one resolved ahead of it",
      len(app_walk.vlc_instance.medias) == 3
      and all(m.url == "https://example.test/prefetched" for m in app_walk.vlc_instance.medias),
      app_walk.vlc_instance.medias)
check("K13 the look-ahead is keyed to the track on the player and moves with it down the list",
      _walk_keys == ["vid0", "vid1", "vid2"] and app_walk.playback_index == 3,
      (_walk_keys, app_walk.playback_index))
check("K14 walking a list cannot grow the resolved-URL cache past its limit",
      len(app_walk._prefetched_streams) <= mod.PREFETCH_CACHE_LIMIT, app_walk._prefetched_streams)
unpatch()

print("L. the tray menu entry, built for real")
from PySide6.QtWidgets import QApplication, QMenu
qapp = QApplication.instance() or QApplication([])


class TrayHarness(mod.QWidget):
    _build_tray_menu = mod.MainApp._build_tray_menu
    _truncate_title = mod.MainApp._truncate_title
    cycle_stop_after_current = mod.MainApp.cycle_stop_after_current
    set_stop_after_current = mod.MainApp.set_stop_after_current
    _update_stop_after_ui = mod.MainApp._update_stop_after_ui

    def save_config(self):
        """No-op stand-in for the settings write a stop-after click now performs."""


def tray_harness(state=mod.STOP_AFTER_OFF):
    t = TrayHarness()
    t.stop_after_current = state
    t.stop_after_btn = None
    t.tray_menu = QMenu(t)
    t.current_playing_title = "Track 0"
    t.time_label = FakeLabel()
    t.time_label.setText("1:10 / 3:40")
    t.is_playing = True
    t.volume_val = 100
    t.statuses = []
    t._on_status_update = lambda text, playing, color: t.statuses.append((text, playing, color))
    t.toggle_playback = lambda: None
    t.play_previous = lambda: None
    t.play_next = lambda: None
    t._set_tray_volume = lambda val: None
    t._restore_from_tray = lambda: None
    t.close = lambda: None
    return t


def stop_entry(t):
    t._build_tray_menu()
    for act in t.tray_menu.actions():
        if act.text().startswith("Stop After Current"):
            return act
    return None


t = tray_harness()
act = stop_entry(t)
check("L1 the tray menu has a Stop After Current entry", act is not None,
      [a.text() for a in t.tray_menu.actions()])
check("L2 it names the state it is in", act.text() == "Stop After Current (Off)", act.text())
check("L3 it is unticked while off", act.isChecked() is False)
check("L4 the tray entry is a normal clickable action, not a submenu", act.menu() is None)
act.trigger()
check("L5 clicking it once arms 'stop after this track'", t.stop_after_current == mod.STOP_AFTER_ONCE)
act = stop_entry(t)
check("L6 the entry then reads Once", act.text() == "Stop After Current (Once)", act.text())
check("L7 and shows a tick", act.isChecked() is True)
act.trigger()
check("L8 clicking it a second time leaves it on", t.stop_after_current == mod.STOP_AFTER_ALWAYS)
act = stop_entry(t)
check("L9 the entry reads Always and is still ticked",
      act.text() == "Stop After Current (Always)" and act.isChecked() is True, act.text())
act.trigger()
check("L10 clicking it once more turns it off", t.stop_after_current == mod.STOP_AFTER_OFF)
act = stop_entry(t)
check("L11 the entry reads Off and the tick is gone",
      act.text() == "Stop After Current (Off)" and act.isChecked() is False, act.text())
_menu_texts = [a.text() for a in t.tray_menu.actions()]
_idx = _menu_texts.index(next(x for x in _menu_texts if x.startswith("Stop After Current")))
check("L12 the tray entry sits by the transport controls, ahead of the separator",
      _menu_texts[_idx - 1] == "Next Track" and _menu_texts[_idx + 1] == "", _menu_texts)
t2 = tray_harness(mod.STOP_AFTER_ALWAYS)
act2 = stop_entry(t2)
check("L13 a fresh menu opened later still reports the live state",
      act2.text() == "Stop After Current (Always)", act2.text())

# ---------------------------------------------------------------------------
# M. a new search lands the reader at the first row; a redraw of the same list
#    does not move them, and does not discard a prefetch decided for it.
# ---------------------------------------------------------------------------

class ReadingHarness:
    _on_search_results = mod.MainApp._on_search_results
    _reset_results_scroll = mod.MainApp._reset_results_scroll
    invalidate_next_track_prefetch = mod.MainApp.invalidate_next_track_prefetch
    _arm_stop_after_for_new_search = mod.MainApp._arm_stop_after_for_new_search
    _stream_track_in_progress = mod.MainApp._stream_track_in_progress
    set_stop_after_current = mod.MainApp.set_stop_after_current
    _update_stop_after_ui = mod.MainApp._update_stop_after_ui

    def _forget_playback_box(self):
        """No-op. The coloured-row pass was added to _on_search_results() after this
        harness was written, and the harness rows are not coloured by it here."""

    def _clear_thumb_hover(self):
        """No-op. The play-button pass was added to _on_search_results() after this harness was
        written, and none of the harness rows here is the row a pointer is on."""

    def save_config(self):
        """No-op stand-in for the settings write a stop-after click performs."""

r = ReadingHarness()
_r_area = mod.QScrollArea()
_r_container = mod.QWidget()
r.results_vbox = mod.QVBoxLayout(_r_container)
_r_area.setWidget(_r_container)
_r_area.setWidgetResizable(True)
# A scroll range exists only once the pane has been laid out for a real viewport, so the
# harness shows it - parked far off screen, where a probe should not be looked at.
_r_area.resize(320, 180)
_r_area.move(-32000, -32000)
_r_area.show()
r.results_area = _r_area
_r_videos = [{"id": f"vid{i}", "title": f"Track {i}", "duration": "3:40"} for i in range(40)]
r.search_btn = mod.QPushButton()
r.show_thumbnails = False
r.search_results = []
r.statuses = []
r._on_status_update = lambda *a, **k: r.statuses.append(a[0])
r.lazy_load_visible_results = lambda: None
r.update_queue_all_checkbox_state = lambda: None
r._prefetch_decision = None
r._prefetch_busy = set()
r._prefetch_lock = threading.Lock()
r._prefetch_trigger_key = None
r._prefetched_streams = {}
r._prefetch_threads = set()
# The stop-after state a new search may arm, plus everything the arming reads to
# decide whether a stream is in progress. Nothing is playing when M begins, so
# M1-M7 are unaffected by it.
r.stop_after_current = mod.STOP_AFTER_OFF
r._search_stop_after_track = None
r.current_video_id = None
r._is_loading_stream = False
r._pending_fetch_id = None
r.vlc_player = None
r.stop_after_btn = mod.QPushButton()
def _pump():
    # The scroll range follows the layout, and the layout settles over a couple of event
    # rounds - which is exactly why the app re-checks the pane after lazy loading.
    for _ in range(4):
        qapp.processEvents()

_pump()

r._on_search_results(_r_videos, False)
_r_bar = _r_area.verticalScrollBar()
_pump()
_r_bar.setValue(400)
_pump()
check("M1 the results pane can be scrolled at all", _r_bar.value() == 400,
      (_r_bar.minimum(), _r_bar.maximum()))

r._prefetch_decision = {"next_id": "vid1", "next_title": "Track 1", "url": "prefetched://vid1"}
r._prefetched_streams["vid1"] = ("prefetched://vid1", "UA", time.time())
r._on_search_results(_r_videos, False, reset_view=False)
_pump()
check("M2 a redraw keeps the reader where they were reading", _r_bar.value() == 400, _r_bar.value())
check("M3 a redraw keeps the prefetch decided for the same list",
      bool(r._prefetch_decision) and r._prefetch_decision["next_id"] == "vid1")

r._on_search_results(_r_videos, False)
_pump()
check("M4 a new search puts the reader back at the first row", _r_bar.value() == 0, _r_bar.value())
check("M5 a new search drops the successor decided for the list it replaced",
      r._prefetch_decision is None and "vid1" not in r._prefetched_streams)
check("M6 the rebuilt list is the one search produced", len(r.search_results) == 40)

_r_bar.setValue(250)
_pump()
r._on_search_results(r.search_results, False, reset_view=False)   # thumbnail-toggle path
_pump()
check("M7 a redraw leaves the reader on the row they were on",
      _r_bar.value() == 250, _r_bar.value())

# M8-M12: the same real _on_search_results, but with a stream on the player - which
# is the situation a new search now has to make a decision about.
r.current_video_id = "vid0"
r.vlc_player = FakePlayer(mod.vlc.State.Playing, ms=40000, length=100000)
r.stop_after_current = mod.STOP_AFTER_OFF
r._search_stop_after_track = None
r._on_search_results(_r_videos, False)
check("M8 a new search while a stream plays arms the one-shot stop",
      r.stop_after_current == mod.STOP_AFTER_ONCE, r.stop_after_current)
check("M9 the arming names the track that was playing",
      r._search_stop_after_track == "vid0", r._search_stop_after_track)
check("M10 the player-bar button reads once",
      r.stop_after_btn.property("stop_after_state") == "once",
      r.stop_after_btn.property("stop_after_state"))
check("M11 the status line says why the state changed",
      any("Stop after current" in s and "last one" in s for s in r.statuses), r.statuses[-3:])
r.stop_after_current = mod.STOP_AFTER_OFF
r._search_stop_after_track = None
r._on_search_results(r.search_results, False, reset_view=False)   # redraw with a stream still playing
_pump()
check("M12 a redraw of the same list arms nothing",
      r.stop_after_current == mod.STOP_AFTER_OFF and r._search_stop_after_track is None,
      (r.stop_after_current, r._search_stop_after_track))

# ---------------------------------------------------------------------------
# N. a new search lands while a stream is playing. Before this change the track
#    already playing carried its index into the new list, so finishing it dropped
#    the listener into the middle of the search they had just run.
# ---------------------------------------------------------------------------
print("=" * 72)
print("N. arming 'stop after current' when a search lands on a playing stream")
patch_resolve()

NEW_LIST = [{"id": f"new{i}", "title": f"New {i}"} for i in range(5)]


def live_app(mode=mod.STOP_AFTER_OFF, state=None, vid="vid0", loading=False,
             shadow_play=True):
    """A real MainApp instance with a stream on the player, ready for a search to land."""
    app = make_app(index=0, vid=vid, mode=mode, shadow_play=shadow_play)
    app._search_stop_after_track = None
    app._is_loading_stream = loading
    app.vlc_player = FakePlayer(state if state is not None else mod.vlc.State.Playing,
                                ms=40000, length=100000)
    return app


app = live_app()
armed = app._arm_stop_after_for_new_search()
check("N1 a search that lands on a playing stream arms 'once'",
      armed is True and app.stop_after_current == mod.STOP_AFTER_ONCE, app.stop_after_current)
check("N2 the arming belongs to the track that was playing",
      app._search_stop_after_track == "vid0", app._search_stop_after_track)
check("N3 the player-bar button reports it",
      app.stop_after_btn.props.get("stop_after_state") == "once", app.stop_after_btn.props)
check("N4 the status line reports it",
      any("once" in text.lower() for text, _p, _c in app.status_messages), app.status_messages)

app = live_app(state=mod.vlc.State.Paused)
check("N5 a paused stream is armed too - resumed, it advances just the same",
      app._arm_stop_after_for_new_search() is True and app.stop_after_current == mod.STOP_AFTER_ONCE)

app = live_app(state=mod.vlc.State.Opening, loading=True)
app._pending_fetch_id = "vid7"
check("N6 a stream still being resolved is armed for that stream",
      app._arm_stop_after_for_new_search() is True and app._search_stop_after_track == "vid7",
      app._search_stop_after_track)

app = live_app(vid="local")
check("N7 a local file is left alone - a search does not replace the folder list",
      app._arm_stop_after_for_new_search() is False and app.stop_after_current == mod.STOP_AFTER_OFF
      and app._search_stop_after_track is None)

_refused_states = {}
for _state in (mod.vlc.State.Stopped, mod.vlc.State.Ended):
    app = live_app(state=_state)
    _refused_states[_state] = (app._arm_stop_after_for_new_search() is False
                               and app.stop_after_current == mod.STOP_AFTER_OFF)
check("N8 a stopped track arms nothing, and so does the id left behind by a finished one",
      all(_refused_states.values()), _refused_states)

app = live_app(state=mod.vlc.State.NothingSpecial, vid=None)
check("N10 with nothing ever played nothing is armed",
      app._arm_stop_after_for_new_search() is False and app.stop_after_current == mod.STOP_AFTER_OFF)

app = live_app(mode=mod.STOP_AFTER_ALWAYS)
check("N11 a state the user chose by clicking is never overwritten",
      app._arm_stop_after_for_new_search() is False and app.stop_after_current == mod.STOP_AFTER_ALWAYS
      and app._search_stop_after_track is None)

app = live_app(mode=mod.STOP_AFTER_ONCE)
check("N12 the same for a 'once' the user chose himself",
      app._arm_stop_after_for_new_search() is False and app._search_stop_after_track is None)

# The reported bug itself: the list is replaced under the track that is playing.
app = live_app()
armed_now = app._arm_stop_after_for_new_search()
app.search_results = NEW_LIST       # what a new search does to the list
app.playback_index = 0              # still the row of the list the track came from
app.vlc_player = FakePlayer(mod.vlc.State.Ended, ms=100000, length=100000)
app.update_player_ui()
check("N13 the armed track ends as the last one of its own list",
      armed_now and app.started == [], app.started)
check("N14 nothing from the new search played",
      not any(video["id"].startswith("new") for video, _nav in app.started), app.started)
check("N15 the one-shot spent itself and the marker went with it",
      app.stop_after_current == mod.STOP_AFTER_OFF and app._search_stop_after_track is None,
      (app.stop_after_current, app._search_stop_after_track))

app = live_app()
app.search_results = NEW_LIST
app.playback_index = 0
app.vlc_player = FakePlayer(mod.vlc.State.Ended, ms=100000, length=100000)
app.update_player_ui()
check("N16 control - left unarmed the finished track walks into the new list",
      len(app.started) == 1 and app.started[0][0]["id"] == "new1", app.started)

app = live_app()
app._arm_stop_after_for_new_search()
RESOLVE_CALLS.clear()
app.vlc_player = FakePlayer(mod.vlc.State.Playing, ms=80000, length=100000)  # 20 s left
app.update_player_ui()
time.sleep(0.3)
check("N17 an armed track is read ahead for too - a listener who armed a stop still presses Next",
      wait_for(lambda: "vid1" in RESOLVE_CALLS) and app.stop_after_current == mod.STOP_AFTER_ONCE
      and app._search_stop_after_track == "vid0",
      (RESOLVE_CALLS, app.stop_after_current, app._search_stop_after_track))

app = live_app(shadow_play=False)
app._arm_stop_after_for_new_search()
app.search_results = NEW_LIST
app.play_result(NEW_LIST[2])        # the user picks a row of the new search
check("N18 picking a track spends an arming that was not about it",
      app.stop_after_current == mod.STOP_AFTER_OFF and app._search_stop_after_track is None,
      (app.stop_after_current, app._search_stop_after_track))
check("N19 the track he picked plays, and is free to advance afterwards",
      wait_for(lambda: app.playback_started_signal.calls != []), app.playback_started_signal.calls)

app = live_app(shadow_play=False)
app._arm_stop_after_for_new_search()
app.play_result({"id": "vid0", "title": "Track 0"})   # the armed track, started again
check("N20 starting the armed track itself keeps its arming",
      app.stop_after_current == mod.STOP_AFTER_ONCE and app._search_stop_after_track == "vid0",
      (app.stop_after_current, app._search_stop_after_track))

app = live_app(shadow_play=False)
app._arm_stop_after_for_new_search()
app.search_results = NEW_LIST
app.play_next()                     # a manual Next always advances
check("N21 a manual Next releases an arming it was never meant to stop",
      app.stop_after_current == mod.STOP_AFTER_OFF, app.stop_after_current)
check("N22 and the successor of the new list plays",
      wait_for(lambda: app.playback_started_signal.calls != []), app.playback_started_signal.calls)

LOCAL = [{"is_dir": False, "path": "C:/fake/one.mp3", "name": "one.mp3"}]
app = live_app(shadow_play=False)
app._arm_stop_after_for_new_search()
app.current_local_items = LOCAL
app._on_local_click(LOCAL[0])
check("N23 a file from the local pane is not the track the arming belonged to",
      app.stop_after_current == mod.STOP_AFTER_OFF and app._search_stop_after_track is None)
app = live_app(mode=mod.STOP_AFTER_ALWAYS, shadow_play=False)
app.current_local_items = LOCAL
app._on_local_click(LOCAL[0])
check("N24 a state the user set by hand survives a local start",
      app.stop_after_current == mod.STOP_AFTER_ALWAYS, app.stop_after_current)

app = live_app()
app._arm_stop_after_for_new_search()
app.cycle_stop_after_current()      # the search armed once; this click means always
check("N25 clicking the button after a search takes the state out of its hands",
      app.stop_after_current == mod.STOP_AFTER_ALWAYS and app._search_stop_after_track is None,
      (app.stop_after_current, app._search_stop_after_track))
app.search_results = NEW_LIST
app.play_result(NEW_LIST[0])
check("N26 and it stays armed when a new track starts",
      app.stop_after_current == mod.STOP_AFTER_ALWAYS, app.stop_after_current)
unpatch()

print("W. the wiring, read as source text")
_search_head = _source[_source.index("def _on_search_results"):][:2400]
check("W1 a new search arms the one-shot for the track playing",
      "_arm_stop_after_for_new_search()" in _search_head, _search_head[:400])
check("W2 only a search that was just run arms it - the call sits in the reset_view branch",
      "if reset_view:" in _search_head and "_arm_stop_after_for_new_search()" in _search_head
      and _search_head.index("if reset_view:") < _search_head.index("_arm_stop_after_for_new_search()"))
check("W3 picking a track releases an arming that is not its own",
      "self._release_search_stop_after(vid_id)" in _source[_source.index("def play_result"):][:1500])
check("W4 starting a local file releases it too",
      'self._release_search_stop_after("local")' in _source[_source.index("def _on_local_click"):][:2200])
check("W5 a finished track spends the arming whoever set it",
      "_search_stop_after_track = None" in _source[_source.index("def _finish_stop_after_current"):][:1700])
check("W6 clicking the button takes the state away from the search",
      "_search_stop_after_track = None" in _source[_source.index("def cycle_stop_after_current"):][:800])
check("W7 the arming is initialised with the rest of the player state",
      "_search_stop_after_track = None" in _source[_source.index("self.stop_after_current = STOP_AFTER_OFF"):][:900])
check("W8 a state the user chose is never overwritten",
      "!= STOP_AFTER_OFF:\n            return False" in _source[_source.index("def _arm_stop_after_for_new_search"):][:1800])
check("W9 local playback is never armed",
      'vid_id == "local"' in _source[_source.index("def _stream_track_in_progress"):][:1700])
check("W10 a paused stream counts as in progress",
      "vlc.State.Paused" in _source[_source.index("def _stream_track_in_progress"):][:1700])
check("W11 a stream still being resolved counts as in progress",
      "_is_loading_stream" in _source[_source.index("def _stream_track_in_progress"):][:1700])
# W12 was retired in the 3.5 modularisation. It asked that yt_msd_gui.pyx carry the .pyw
# text so a compiled build could not ship a stale .pyd. There is no compiled build any more:
# the program is now a package of plain modules, so the promise W12 guarded no longer exists
# to guard. The label is left out rather than re-used, per this suite's own rule.

# ---------------------------------------------------------------------------
# X. keeping one track playing when its stream URL stops answering
# ---------------------------------------------------------------------------
print("=" * 72)
print("X. a stream URL that stops answering is noticed, and reloaded as the same track")
patch_resolve()


def stream_app(vid="vid0", ms=40000, length=100000, state=None, url="https://example.test/loaded",
               age=0.0, moved=1.0, dead=False, attempts=0, renew_age=None, is_playing=True,
               mode=mod.STOP_AFTER_OFF, shadow_play=False, listened=True, resuming=False):
    """A track sitting on the player, loaded from a stream URL `age` seconds after it was
    resolved, whose reported position last moved `moved` seconds ago (None - never moved).

    Those two numbers are all the app has to work with: libVLC never says a URL expired.
    `listened` is whether anybody has ever heard this media advancing - which is the only case
    where the age of a URL is on its own a reason to re-resolve it - and `resuming` is a track
    the listener stopped and has not yet heard advancing again."""
    state = mod.vlc.State.Playing if state is None else state
    app = live_app(state=state, vid=vid, mode=mode, shadow_play=shadow_play)
    app.vlc_player = FakePlayer(state, ms=ms, length=length)
    app._loaded_stream = (vid, url, "probe-agent", 0.0)
    app._loaded_stream_at = time.monotonic() - age
    app._stream_moved_at = None if moved is None else (time.monotonic() - moved)
    app._stream_resuming = resuming
    app._stream_listened = listened
    app._stream_seen_ms = ms
    app._stream_dead = dead
    app._stream_refetch_attempts = attempts
    app._finished_track = False        # the MainApp these fixtures are built with __new__ would
    app._finished_track_armed_under = mod.STOP_AFTER_OFF   # have had these from __init__
    app._replay_in_flight = False
    app._stream_renew_started_at = None if renew_age is None else (time.monotonic() - renew_age)
    app.is_playing = is_playing
    app.advances = []
    app.play_next = lambda: app.advances.append(app.playback_index + 1)
    return app


check("X1 a stream is given half an hour before a scrub or a Play re-resolves it",
      mod.STREAM_URL_MAX_AGE == 30 * 60, mod.STREAM_URL_MAX_AGE)
check("X2 a position that has stood still for eight seconds counts as a dead stream",
      mod.STREAM_STALL_SECONDS == 8, mod.STREAM_STALL_SECONDS)
check("X3 a dead stream reloads itself three times at most, then waits for the listener",
      mod.STREAM_REFETCH_LIMIT == 3, mod.STREAM_REFETCH_LIMIT)
check("X4 a track ending 15 seconds short of its own length did not finish",
      mod.STREAM_END_SLACK_MS == 15000, mod.STREAM_END_SLACK_MS)

app = stream_app(age=120.0, moved=1.0)
check("X5 a track loaded a minute ago is not due for anything",
      app._stream_needs_renew() is False)
app = stream_app(age=3600.0, moved=1.0)
check("X6 an hour-old stream that is still advancing is left alone",
      app._stream_needs_renew() is False)
app = stream_app(age=3600.0, moved=None)
check("X7 an hour-old stream whose position has stopped moving is due",
      app._stream_needs_renew() is True)
RESOLVE_CALLS.clear()
app = stream_app(age=0.0, moved=mod.STREAM_STALL_SECONDS + 5, renew_age=1.0)
app.update_player_ui()
check("X8 a young stream whose position has stopped moving is noticed by the watchdog",
      app._stream_dead is True and RESOLVE_CALLS == [], (app._stream_dead, RESOLVE_CALLS))
check("X8a and once it is noticed dead, a scrub goes to the same decision",
      app._stream_needs_renew() is True)
app = stream_app(vid="local")
app._loaded_stream = None
check("X9 a file on disk is never re-fetched - nothing about it expires",
      app._stream_needs_renew() is False)
app = stream_app(age=3600.0, moved=None)
app._is_loading_stream = True
check("X10 nothing in this block acts while a track is still being fetched",
      app._stream_needs_renew() is False)

RESOLVE_CALLS.clear()
app = stream_app(age=60.0, moved=1.0)
app.on_seek(5000)
check("X11 scrubbing a healthy stream scrubs the media, as it always did",
      app.vlc_player.positions == [0.5] and RESOLVE_CALLS == [], (app.vlc_player.positions, RESOLVE_CALLS))
check("X12 and nothing is queued for it", app._pending_stream_seek_frac is None)

RESOLVE_CALLS.clear()
app = stream_app(age=3600.0, moved=None)
app.on_seek(7500)      # the listener drags the bar to three quarters
wait_for(lambda: app.stream_refreshed_signal.calls)
check("X13 scrubbing a dead stream re-resolves it instead of doing nothing",
      RESOLVE_CALLS == ["vid0"], RESOLVE_CALLS)
check("X14 the scrubbed-to position is queued for the fresh media",
      app._pending_stream_seek_frac == 0.75, app._pending_stream_seek_frac)
check("X15 the dying media is not asked for a scrub it cannot answer",
      app.vlc_player.positions == [], app.vlc_player.positions)
check("X16 the refresh is what the status line says",
      any("Re-fetching stream" in text for text, _p, _c in app.status_messages), app.status_messages)
check("X17 it finished and reported itself",
      wait_for(lambda: app.stream_refreshed_signal.calls) and app.stream_refreshed_signal.calls[0][0] is True,
      app.stream_refreshed_signal.calls)
check("X18 fresh media for the same video is what the player got",
      app.vlc_player.media.url == "https://example.test/prefetched", app.vlc_player.media.url)
app.update_player_ui()
check("X19 the scrub lands once the fresh media answers",
      app.vlc_player.positions == [0.75], app.vlc_player.positions)
check("X20 and only once", (app.update_player_ui(), app.vlc_player.positions == [0.75])[1])
check("X21 the queue empties itself", app._pending_stream_seek_frac is None)

RESOLVE_CALLS.clear()
app = stream_app(ms=523000, length=900000, age=3600.0,
                 moved=mod.STREAM_STALL_SECONDS + 3)   # 8:43 into a 15:00 track, and it froze
app.update_player_ui()
check("X22 a position that has stopped moving while the track is wanted playing is noticed",
      any("stopped responding" in text and "reloading" in text for text, _p, _c in app.status_messages),
      app.status_messages)
check("X23 and the same track is re-resolved on its own",
      wait_for(lambda: RESOLVE_CALLS) and RESOLVE_CALLS == ["vid0"], RESOLVE_CALLS)
check("X24 it finished", wait_for(lambda: app.stream_refreshed_signal.calls))
app.update_player_ui()
check("X25 the track resumes where it stopped rather than from the start",
      app.vlc_player.times == [523000], app.vlc_player.times)
check("X26 the same track is still the track - one long buffer, not the song started again",
      (app.current_video_id, app.playback_index) == ("vid0", 0))
RESOLVE_CALLS.clear()
app = stream_app(age=3600.0, moved=None)   # a media the watchdog has never seen move yet
app.update_player_ui()
check("X22b a media not yet seen moving is given its stall clock, not an instant verdict",
      app._stream_moved_at is not None and app._stream_dead is False and RESOLVE_CALLS == [],
      (app._stream_dead, RESOLVE_CALLS))

RESOLVE_CALLS.clear()
app = stream_app(age=3600.0, moved=None, is_playing=False, state=mod.vlc.State.Playing)
app.update_player_ui()
check("X27 a track left paused is not a dead stream and reloads nothing",
      RESOLVE_CALLS == [] and app._stream_dead is False, (RESOLVE_CALLS, app._stream_dead))

RESOLVE_CALLS.clear()
app = stream_app(age=3600.0, state=mod.vlc.State.Error)
app.update_player_ui()
check("X28 vlc.State.Error is noticed too - the other face of a dead URL",
      any("stopped responding" in text and "reloading" in text for text, _p, _c in app.status_messages),
      app.status_messages)
check("X28a and it is reloaded like any other dead stream",
      wait_for(lambda: RESOLVE_CALLS) and RESOLVE_CALLS == ["vid0"]
      and wait_for(lambda: app.stream_refreshed_signal.calls), (RESOLVE_CALLS,))
RESOLVE_CALLS.clear()
app = stream_app(age=30.0, state=mod.vlc.State.Error, renew_age=1.0)
app.update_player_ui()
check("X28b the Error state keeps marking it dead every tick it takes to get a fresh URL",
      app._stream_dead is True and RESOLVE_CALLS == [], (app._stream_dead, RESOLVE_CALLS))

RESOLVE_CALLS.clear()
app = stream_app(state=mod.vlc.State.Error)
app.update_player_ui()
wait_for(lambda: app.stream_refreshed_signal.calls)
app.vlc_player.state = mod.vlc.State.Playing
app.vlc_player.ms = 61000
app._stream_seen_ms = -1
app.update_player_ui()
check("X29 a stream that came back on its own is not held against it",
      app._stream_dead is False and app._stream_refetch_attempts == 0,
      (app._stream_dead, app._stream_refetch_attempts))

RESOLVE_CALLS.clear()
app = stream_app(age=3600.0, moved=None, renew_age=1.0)   # a re-fetch ran a second ago
app.on_seek(3000)
check("X30 a dragged seek bar does not become a fetch storm - the cooldown holds",
      RESOLVE_CALLS == [] and app.vlc_player.positions == [0.3], (RESOLVE_CALLS, app.vlc_player.positions))
check("X31 and the scrub itself is still honoured", app._pending_stream_seek_frac is None)

RESOLVE_CALLS.clear()
app = stream_app(age=3600.0, moved=None)
for _ in range(20):                      # one hundred sliderMoved signals is the realistic number
    app.on_seek(2000)
wait_for(lambda: app.stream_refreshed_signal.calls)
app.on_seek(4000)
check("X32 twenty drags across a dead stream cost one yt-dlp call",
      RESOLVE_CALLS == ["vid0"], RESOLVE_CALLS)

RESOLVE_CALLS.clear()
app = stream_app(age=0.0, moved=mod.STREAM_STALL_SECONDS + 5, attempts=mod.STREAM_REFETCH_LIMIT)
app.update_player_ui()
check("X33 a track that cannot be reloaded stops trying, rather than fetching forever",
      RESOLVE_CALLS == [], RESOLVE_CALLS)
check("X34 and says so plainly enough that the listener knows to pick it again",
      any("would not reload" in text and "pick the track" in text for text, _p, _c in app.status_messages),
      app.status_messages)
RESOLVE_CALLS.clear()
app = stream_app(age=3 * 3600, moved=None, is_playing=False)   # left paused for three hours
app.toggle_playback()
wait_for(lambda: RESOLVE_CALLS)
check("X35 a track left paused past the life of its URL is picked up by the play button",
      RESOLVE_CALLS == ["vid0"] and app.is_playing is True and app.play_btn.text == "\uE769",
      (RESOLVE_CALLS, app.is_playing, app.play_btn.text))
check("X35b a Play press is not held by the cooldown a dragged seek bar had to wait out",
      wait_for(lambda: app.stream_refreshed_signal.calls), app.stream_refreshed_signal.calls)

RESOLVE_CALLS.clear()
app = stream_app(ms=40000, length=900000, state=mod.vlc.State.Ended)   # died 14 minutes early
app.update_player_ui()
wait_for(lambda: RESOLVE_CALLS)
check("X36 a stream that gave out mid-track is not taken as a track that finished",
      RESOLVE_CALLS == ["vid0"] and app.advances == [], (RESOLVE_CALLS, app.advances))
check("X37 the playlist does not walk on while the listener was still hearing it",
      app.playback_index == 0 and app.current_video_id == "vid0", (app.playback_index, app.current_video_id))
RESOLVE_CALLS.clear()
app = stream_app(ms=900000, length=900000, state=mod.vlc.State.Ended)  # a real ending
app.update_player_ui()
check("X38 a track that genuinely finished still advances to the next one",
      app.advances == [1] and RESOLVE_CALLS == [], (app.advances, RESOLVE_CALLS))
RESOLVE_CALLS.clear()
app = stream_app(ms=120000, length=900000, state=mod.vlc.State.Ended)
app._loaded_stream = None               # a file on disk that stopped where it stopped
app.update_player_ui()
check("X39 a local file is never treated as a died stream",
      app.advances == [1] and RESOLVE_CALLS == [], (app.advances, RESOLVE_CALLS))

RESOLVE_CALLS.clear()
RESOLVE_HOLD[0] = 0.4          # keeps the self-heal in flight across the tick being checked
app = stream_app(age=3600.0, moved=mod.STREAM_STALL_SECONDS + 3, mode=mod.STOP_AFTER_ONCE)
app.is_shuffled = True
app.shuffle_history = [0, 2]
app._prefetch_decision = ("vid0", 3, {"id": "vid3"})
app.update_player_ui()
wait_for(lambda: app.stream_refreshed_signal.calls)
RESOLVE_HOLD[0] = 0.0
check("X40 a self-heal leaves the shuffle history where it was",
      app.shuffle_history == [0, 2], app.shuffle_history)
check("X41 leaves the stop-after state armed as the listener set it",
      app.stop_after_current == mod.STOP_AFTER_ONCE, app.stop_after_current)
check("X42 leaves the successor already decided for this track",
      app._prefetch_decision is not None and app._prefetch_decision[1] == 3, app._prefetch_decision)
check("X43 and holds the ending rather than spending it mid-swap",
      app._ended_trigger is True and app.advances == [], (app._ended_trigger, app.advances))

RESOLVE_CALLS.clear()
RESOLVE_HOLD[0] = 0.4
app = stream_app(age=3600.0, moved=None, is_playing=False)
app.toggle_playback()
wait_for(lambda: app._stream_refetching)
app.toggle_playback()          # pressed again while the re-fetch is still running
check("X44 a second Play during a re-fetch does not fight the dying media",
      app.vlc_player.paused is None and app.vlc_player.played == 0,
      (app.vlc_player.paused, app.vlc_player.played))
check("X45 it only means play it when it lands",
      app.is_playing is True and app._pending_stream_pause is False,
      (app.is_playing, app._pending_stream_pause))
wait_for(lambda: app.stream_refreshed_signal.calls)
RESOLVE_HOLD[0] = 0.0

patch_resolve(fail=True)
RESOLVE_CALLS.clear()
app = stream_app(age=3600.0, moved=None)
app.on_seek(5000)
check("X46 a re-fetch that itself fails is reported rather than swallowed",
      wait_for(lambda: app.stream_refreshed_signal.calls) and app.stream_refreshed_signal.calls[0][0] is False,
      app.stream_refreshed_signal.calls)
check("X47 the listener is told to pick the track",
      (app._on_stream_refreshed(False, "Track 0") or True)
      and any("Could not re-fetch" in text for text, _p, _c in app.status_messages), app.status_messages)
check("X48 the app is not left thinking a fetch is still running",
      app._stream_refetching is False and app._is_loading_stream is False,
      (app._stream_refetching, app._is_loading_stream))
check("X49 the queued position is not left to pounce minutes later",
      app._pending_stream_seek_frac is not None and app._pending_stream_seek_at is not None)
patch_resolve()

RESOLVE_CALLS.clear()
app = live_app(shadow_play=False)
app.play_result(app.search_results[1])
check("X50 starting a track records what the player was loaded with",
      wait_for(lambda: app.playback_started_signal.calls) and app._loaded_stream[0] == "vid1"
      and app._loaded_stream[1] == "https://example.test/prefetched"
      and app._loaded_stream[2] == "probe-agent", app._loaded_stream)
app._prefetched_streams["vid2"] = ("https://example.test/ahead", "probe-agent", time.monotonic() - 40)
app.play_result(app.search_results[2])
check("X51 a stream read ahead of time carries the age it already has",
      wait_for(lambda: len(app.playback_started_signal.calls) == 2) and app._loaded_stream[3] >= 40.0,
      app._loaded_stream)
app = live_app(shadow_play=False)
app.current_local_items = LOCAL
app._on_local_click(LOCAL[0])
check("X52 a local file leaves the watchdog watching nothing",
      app._loaded_stream is None, app._loaded_stream)
RESOLVE_CALLS.clear()
app.update_player_ui()
check("X53 so a file that is scrubbed is only ever scrubbed",
      RESOLVE_CALLS == [], RESOLVE_CALLS)

check("X54 the player timer is what runs the watchdog",
      "_watch_stream_liveness(state, ms)" in _source[_source.index("def update_player_ui"):][:1600])
check("X55 and a queued position lands from the same timer",
      "_apply_pending_stream_seek()" in _source[_source.index("def update_player_ui"):][:2400])
check("X56 an ending is read as an ending only after it is checked for being short",
      "_stream_ended_short(total_ms, ms)" in _source[_source.index("def update_player_ui"):][:2400])
check("X57 a scrub goes through the same decision",
      "_stream_needs_renew()" in _source[_source.index("def on_seek"):][:1400])
check("X58 a Play press goes through it too",
      "_renew_loaded_stream(force=True)" in _source[_source.index("def toggle_playback"):][:1800])
check("X59 the refresh runs on its own thread like every other yt-dlp call does",
      "threading.Thread(target=bg_renew" in _source)
check("X60 and only its result is reported to the window",
      "stream_refreshed_signal = Signal(bool, str)" in _source
      and "self.stream_refreshed_signal.connect(self._on_stream_refreshed)" in _source)
check("X61 the watchdog state is initialised with the rest of the player state",
      "self._loaded_stream = None" in _source[_source.index("self._prefetched_streams = {}"):][:1800])

# ---------------------------------------------------------------------------
# Y. a stream the listener paused used to be re-fetched the moment it was played again:
#    the stall clock had kept counting through the pause, so the first tick reporting
#    Playing convicted the track on the position it had left behind before the pause -
#    before the stream had had the chance to reconnect, and for a stream that was still
#    perfectly playable.
# ---------------------------------------------------------------------------
print("=" * 72)
print("Y. a pause is not a stall, and a stream that still answers is never re-fetched")
patch_resolve()
RESOLVE_HOLD[0] = 0.0

check("Y1 a resumed track gets a longer clock than one that has been running",
      mod.STREAM_RESUME_GRACE > mod.STREAM_STALL_SECONDS,
      (mod.STREAM_STALL_SECONDS, mod.STREAM_RESUME_GRACE))

RESOLVE_CALLS.clear()
app = stream_app(ms=40000, length=100000, age=60.0, moved=1.0)     # playing, and advancing
app.toggle_playback()                                              # the listener pauses it
check("Y2 the pause holds the stall clock and marks the track a resumed one",
      app._stream_moved_at is None and app._stream_resuming is True and app._stream_dead is False,
      (app._stream_moved_at, app._stream_resuming, app._stream_dead))
for _ in range(5):                    # thirty seconds of paused ticks, reporting no new position
    app.update_player_ui()
check("Y3 nothing is convicted while the listener has the track stopped",
      app._stream_dead is False and RESOLVE_CALLS == [], (app._stream_dead, RESOLVE_CALLS))
app.toggle_playback()                          # Play, thirty seconds on from the pause
app.vlc_player.state = mod.vlc.State.Playing   # libVLC reports Playing, still at 40000 ms: reconnecting
for _ in range(4):
    app.update_player_ui()
check("Y4 the resume is a play() and nothing else - no yt-dlp call and no new media",
      app.vlc_player.played == 1 and app.vlc_player.media is None and RESOLVE_CALLS == [],
      (app.vlc_player.played, app.vlc_player.media, RESOLVE_CALLS))
check("Y5 the resumed stream is not convicted on the position it left behind",
      app._stream_dead is False and app._stream_resuming is True,
      (app._stream_dead, app._stream_resuming))
check("Y6 the stall clock is armed again at the first tick worth watching",
      app._stream_moved_at is not None and (time.monotonic() - app._stream_moved_at) < 1.0,
      app._stream_moved_at)
app.vlc_player.ms = 45000             # the stream caught up, as it always could
app.update_player_ui()
check("Y7 the first moving position pays for the grace and the track is an ordinary one",
      app._stream_resuming is False and app._stream_seen_ms == 45000 and app._stream_dead is False,
      (app._stream_resuming, app._stream_seen_ms, app._stream_dead))

RESOLVE_CALLS.clear()
RESOLVE_HOLD[0] = 1.0        # keeps the self-heal in flight while the verdict is read
app = stream_app(ms=40000, length=100000, age=60.0,
                 moved=mod.STREAM_STALL_SECONDS + 4, resuming=True)   # resumed, still for 12 s
app.update_player_ui()
check("Y8 a resumed track inside its grace is not convicted",
      app._stream_dead is False and RESOLVE_CALLS == [], (app._stream_dead, RESOLVE_CALLS))
app._stream_moved_at = time.monotonic() - (mod.STREAM_RESUME_GRACE + 3)   # ...and still for 23 s
app.update_player_ui()
check("Y9 a resumed track still past its grace is convicted, and reloads itself",
      app._stream_dead is True and wait_for(lambda: RESOLVE_CALLS) and RESOLVE_CALLS == ["vid0"],
      (app._stream_dead, RESOLVE_CALLS))   # RESOLVE_HOLD keeps the self-heal in flight while this is read
check("Y10 and it is the same track on the player, not the playlist moved on",
      (app.current_video_id, app.playback_index) == ("vid0", 0))
wait_for(lambda: app.stream_refreshed_signal.calls)
RESOLVE_HOLD[0] = 0.0

RESOLVE_CALLS.clear()
RESOLVE_HOLD[0] = 1.0
app = stream_app(ms=40000, length=100000, age=60.0, moved=mod.STREAM_STALL_SECONDS + 3)  # never paused
app.update_player_ui()
check("Y11 a stream that stopped moving while it had been playing all along is still convicted at once",
      app._stream_dead is True and app._stream_resuming is False,
      (app._stream_dead, app._stream_resuming))
wait_for(lambda: app.stream_refreshed_signal.calls)
RESOLVE_HOLD[0] = 0.0

RESOLVE_CALLS.clear()
app = stream_app(ms=40000, length=100000, age=60.0, moved=None,
                 state=mod.vlc.State.Paused, is_playing=False)
app.on_seek(6000)
check("Y12 scrubbing a paused stream whose URL is still young scrubs the media, nothing else",
      app.vlc_player.positions == [0.6] and RESOLVE_CALLS == [],
      (app.vlc_player.positions, RESOLVE_CALLS))

RESOLVE_CALLS.clear()
app = stream_app(ms=40000, length=100000, age=90.0, moved=1.0)
app.toggle_playback()                 # pause it
for _ in range(5):
    app.update_player_ui()            # thirty seconds of paused ticks
app.on_seek(3000)                     # and the listener drags the bar while it is paused
app.toggle_playback()                 # then plays it again
app.vlc_player.state = mod.vlc.State.Playing
for _ in range(4):
    app.update_player_ui()
check("Y13 pause, scrub, resume: the stream on the player is left exactly where it is",
      RESOLVE_CALLS == [] and app._stream_dead is False and app.is_playing is True,
      (RESOLVE_CALLS, app._stream_dead, app.is_playing))

app = stream_app(age=3600.0, moved=100.0, dead=True)
app.vlc_player.ms = 61000     # not the position the watchdog last recorded: this media is advancing again
check("Y14 a stream that is measurably advancing is not due for a new URL, even an old one held dead",
      app._stream_is_playing_now() is True and app._stream_needs_renew() is False,
      (app._stream_is_playing_now(), app._stream_needs_renew(), app._stream_dead))
app = stream_app(age=3600.0, moved=1.0, state=mod.vlc.State.Paused, is_playing=False)
check("Y15 a paused stream is not a provably playing one", app._stream_is_playing_now() is False)
_opening = stream_app(age=3600.0, moved=1.0, state=mod.vlc.State.Opening)
app = stream_app(age=3600.0, moved=1.0, state=mod.vlc.State.Error)
check("Y16 neither a stream reporting vlc.State.Error nor one still opening counts as provably playing",
      app._stream_is_playing_now() is False and _opening._stream_is_playing_now() is False)
app = stream_app(vid="local")
app._loaded_stream = None
check("Y18 a file on disk is never asked", app._stream_is_playing_now() is False)
app = stream_app(age=3600.0, moved=1.0)
app._is_loading_stream = True
check("Y19 nor is a track whose fetch is already running", app._stream_is_playing_now() is False)
app = stream_app(age=3600.0, moved=None, listened=False)   # preloaded at start up and never played
check("Y20 an hour-old URL on a stream nobody has ever heard advancing is still not due",
      app._stream_needs_renew() is False, app._stream_needs_renew())

RESOLVE_CALLS.clear()
app = stream_app(age=30.0, state=mod.vlc.State.Error, is_playing=False)
app.update_player_ui()
check("Y21 an Error on a track the listener stopped says so without re-fetching anything",
      app._stream_dead is True and RESOLVE_CALLS == []
      and any("Play will reload it" in text for text, _p, _c in app.status_messages),
      (RESOLVE_CALLS, app.status_messages))
app.toggle_playback()
check("Y22 and the play button re-resolves that same track when it is asked for",
      wait_for(lambda: RESOLVE_CALLS) and RESOLVE_CALLS == ["vid0"]
      and app.current_video_id == "vid0" and app.is_playing is True,
      (RESOLVE_CALLS, app.current_video_id, app.is_playing))

check("Y23 the watchdog holds the clock while the listener has the track stopped",
      "self._stream_resuming = True" in _source[_source.index("def _watch_stream_liveness"):][:3000])
check("Y24 the play button holds it too, for a pause and a Play inside one timer tick",
      "self._stream_resuming = True" in _source[_source.index("def toggle_playback"):][:3200])
check("Y25 every re-resolution a listener asks for is refused by the playing check first",
      "if self._stream_is_playing_now():" in _source[_source.index("def _stream_needs_renew"):][:3200])
check("Y26 fresh media does not inherit a resumed track's grace",
      "self._stream_resuming = False" in _source[_source.index("def _note_loaded_stream"):][:2600])
check("Y27 the grace is a constant, in the same commented block as the window it replaces",
      "STREAM_RESUME_GRACE = 20" in _source
      and "STREAM_RESUME_GRACE" in _source[:_source.index("STREAM_SEEK_RESTORE_TIMEOUT")])

unpatch()

# ---------------------------------------------------------------------------
# Z. a track that runs to its end is held on the player, and both the button and a
#    scrubbed bar mean "this track again" - because a media libVLC has finished with
#    answers neither a seek nor a resume, and dragging the bar back after an ending used
#    to do nothing at all.
# ---------------------------------------------------------------------------
print("Z. a finished track is held, and the play button becomes the way to hear it again")
patch_resolve()
RESOLVE_HOLD[0] = 0.0

try:                                                     # a caption only counts if this machine's
    from PySide6.QtGui import QFont, QFontMetrics        # font can draw it, and the published
    from PySide6.QtWidgets import QApplication           # chart's "Replay" (U+E76A) provably
    QApplication.instance() or QApplication([])          # cannot - see the AI Readme gotcha
    _metrics = QFontMetrics(QFont("Segoe MDL2 Assets", 14))
    _replay_drawn = _metrics.inFontUcs4(ord(mod.REPLAY_GLYPH))
    _chart_replay_drawn = _metrics.inFontUcs4(0xE76A)
except Exception:
    _replay_drawn = _chart_replay_drawn = True

check("Z1 the replay caption is a glyph this machine's Segoe MDL2 Assets can draw",
      _replay_drawn, mod.REPLAY_GLYPH)
check("Z2 and it is not the chart's own 'Replay' codepoint, which this font has no glyph for",
      not _chart_replay_drawn and mod.REPLAY_GLYPH != chr(0xE76A), mod.REPLAY_GLYPH)
check("Z3 play, pause and replay are three different captions on the one button",
      len({mod.PLAY_GLYPH, mod.PAUSE_GLYPH, mod.REPLAY_GLYPH}) == 3)


def finished_app(mode=mod.STOP_AFTER_OFF, index=4, ms=100000, length=100000, age=60.0,
                 attempts=0, local=False, decision=None):
    """A track that has just run to the end of itself, `age` seconds after its URL was resolved,
    at `index` in a five-track list - the last row by default, which is the case where nothing
    can advance and the listener is left holding a finished track. It stopped at its own reported
    length, so this is a track that finished rather than a stream that gave up early (see
    _stream_ended_short), and `attempts` is how many self-healing reloads it spent getting here."""
    app = stream_app(ms=ms, length=length, age=age, moved=1.0, mode=mode, attempts=attempts,
                     state=mod.vlc.State.Ended)
    app.playback_index = index
    app.shuffle_history = [index]
    app._prefetch_decision = decision
    app._finished_track = False        # every real MainApp has this from __init__; this one is
    app._finished_track_armed_under = mod.STOP_AFTER_OFF   # built by __new__, so it is put here
    app._replay_in_flight = False
    if local:
        app._loaded_stream = None
    return app


app = finished_app(decision=("vid0", 9, {"id": "vid9"}))
app.update_player_ui()
check("Z4 a track that ends with nothing after it is held on the player",
      app._finished_track is True and app.advances == [], (app._finished_track, app.advances))
check("Z5 held means stopped: the button never claims a pause for a media that is not playing",
      app.is_playing is False and app.play_btn.text == mod.REPLAY_GLYPH,
      (app.is_playing, app.play_btn.text))
check("Z6 the button says what a press of it would now do",
      bool(app.play_btn.tooltips) and "Replay" in app.play_btn.tooltips[-1], app.play_btn.tooltips)
check("Z7 the same track is still the track: nothing about it moved",
      (app.current_video_id, app.playback_index) == ("vid0", 4),
      (app.current_video_id, app.playback_index))
check("Z8 the successor readied for the finished track is dropped", app._prefetch_decision is None)
for _ in range(4):
    app.update_player_ui()
check("Z9 the hold is not re-spent on every player tick, and holds no re-fetch",
      app._finished_track is True and app.advances == [] and app.is_playing is False)
app10 = finished_app(index=0)
app10.update_player_ui()
check("Z10 a track with a successor after it still advances and is never held",
      app10.advances == [1] and app10._finished_track is False, (app10.advances, app10._finished_track))
app11 = finished_app(mode=mod.STOP_AFTER_ONCE)
app11.update_player_ui()
check("Z11 'stop after current' holds the finished track as it always did, and holds a replay",
      app11._finished_track is True and app11.advances == []
      and app11.play_btn.text == mod.REPLAY_GLYPH, (app11.advances, app11.play_btn.text))
app12 = finished_app(mode=mod.STOP_AFTER_ALWAYS)
app12.update_player_ui()
check("Z12 'always' stays armed, and holds every track it stops",
      app12._finished_track is True and app12.stop_after_current == mod.STOP_AFTER_ALWAYS,
      (app12._finished_track, app12.stop_after_current))

RESOLVE_CALLS.clear()
app = finished_app(mode=mod.STOP_AFTER_ONCE)
app.update_player_ui()
media_before = app.vlc_player.media
app.toggle_playback()
check("Z13 the replay re-resolves the track rather than replaying the media it finished on, and that fresh stream is what the player is given",
      wait_for(lambda: RESOLVE_CALLS) and RESOLVE_CALLS == ["vid0"]
      and wait_for(lambda: app.vlc_player.media is not None)
      and app.vlc_player.media is not media_before
      and app.vlc_player.media.url == "https://example.test/prefetched",
      (RESOLVE_CALLS, app.vlc_player.media))
check("Z14 it is the same video on the same row: the playlist never moved",
      (app.current_video_id, app.playback_index) == ("vid0", 4) and app.advances == [],
      (app.current_video_id, app.playback_index, app.advances))
check("Z15 the hold is over, and the button is a pause button while the replay runs",
      app._finished_track is False and app.is_playing is True and app.play_btn.text == mod.PAUSE_GLYPH,
      (app._finished_track, app.is_playing, app.play_btn.text))
check("Z16 a replay asks for the top of the track, not for the end the finished media last reported",
      app._pending_stream_seek_frac == 0.0 and app._pending_stream_seek_ms is None,
      (app._pending_stream_seek_frac, app._pending_stream_seek_ms))
check("Z17 the replayed track is still the last one its listener said it was",
      app.stop_after_current == mod.STOP_AFTER_ONCE, app.stop_after_current)
plain = finished_app()
plain.update_player_ui()
check("Z18 a hold remembers the state it was made under, and an ordinary hold remembers none",
      app._finished_track_armed_under == mod.STOP_AFTER_ONCE
      and plain._finished_track_armed_under == mod.STOP_AFTER_OFF,
      (app._finished_track_armed_under, plain._finished_track_armed_under))
check("Z19 replaying under 'always' leaves it armed and puts nothing back",
      app12._replay_finished_track() is True and app12.stop_after_current == mod.STOP_AFTER_ALWAYS,
      app12.stop_after_current)
RESOLVE_CALLS.clear()
RESOLVE_HOLD[0] = 0.4            # keeps the re-fetch in flight while the allowance is read
app = finished_app(mode=mod.STOP_AFTER_ONCE, attempts=mod.STREAM_REFETCH_LIMIT)
app.update_player_ui()
check("Z20 a track that had used up its automatic reloads is not refused when it is asked for again",
      app._replay_finished_track() is True and app._stream_refetch_attempts == 1,
      app._stream_refetch_attempts)
check("Z20b the ask is what starts the re-fetch the watchdog would no longer have started",
      wait_for(lambda: RESOLVE_CALLS) and RESOLVE_CALLS == ["vid0"], RESOLVE_CALLS)
RESOLVE_HOLD[0] = 0.0
wait_for(lambda: app.stream_refreshed_signal.calls)
check("Z20c and the fresh media the listener is left with has its allowance clean",
      app._stream_refetch_attempts == 0, app._stream_refetch_attempts)
RESOLVE_CALLS.clear()

app = finished_app(mode=mod.STOP_AFTER_ONCE)
app.update_player_ui()
app.on_seek(2500)                              # the bar dragged back to a quarter of the way in
check("Z21 dragging the bar back after an ending re-resolves the track instead of doing nothing",
      wait_for(lambda: RESOLVE_CALLS) and RESOLVE_CALLS == ["vid0"], RESOLVE_CALLS)
check("Z22 the place the bar was dragged to is the place the fresh media is asked for",
      app._pending_stream_seek_frac == 0.25, app._pending_stream_seek_frac)
check("Z23 and the listener is playing again, with the hold gone",
      app.is_playing is True and app.play_btn.text == mod.PAUSE_GLYPH and app._finished_track is False,
      (app.is_playing, app.play_btn.text, app._finished_track))
wait_for(lambda: app.stream_refreshed_signal.calls)
app.vlc_player = FakePlayer(mod.vlc.State.Playing, ms=0, length=100000)
app.update_player_ui()
check("Z24 the fresh media lands at that position on the first tick that reports Playing",
      bool(app.vlc_player.positions) and app.vlc_player.positions[-1] == 0.25,
      app.vlc_player.positions)
RESOLVE_CALLS.clear()

app = finished_app(mode=mod.STOP_AFTER_ONCE, local=True)
app.update_player_ui()
played_before = app.vlc_player.played
check("Z25 a file on disk that finished is held the same way a stream is",
      app._finished_track is True and app.play_btn.text == mod.REPLAY_GLYPH)
app.toggle_playback()
check("Z26 and replaying it needs no re-fetch: libVLC is asked to restart the same media",
      RESOLVE_CALLS == [] and app.vlc_player.played == played_before + 1
      and app.is_playing is True, (RESOLVE_CALLS, app.vlc_player.played, app.is_playing))

patch_resolve(fail=True)
RESOLVE_CALLS.clear()
app = finished_app(mode=mod.STOP_AFTER_ONCE)
app.update_player_ui()
app.toggle_playback()
check("Z27 a replay whose re-fetch fails is reported rather than swallowed",
      wait_for(lambda: app.stream_refreshed_signal.calls)
      and app.stream_refreshed_signal.calls[0][0] is False, app.stream_refreshed_signal.calls)
app._on_stream_refreshed(False, "Track 0")
check("Z28 and the button goes back to being the replay it was",
      app._finished_track is True and app.play_btn.text == mod.REPLAY_GLYPH
      and app.is_playing is False, (app._finished_track, app.play_btn.text, app.is_playing))
check("Z29 it leaves nothing pretending a fetch is still running",
      app._stream_refetching is False and app._is_loading_stream is False)
patch_resolve()
RESOLVE_CALLS.clear()
RESOLVE_HOLD[0] = 0.0

app = finished_app(mode=mod.STOP_AFTER_ONCE)
app.update_player_ui()
app.play_result(app.search_results[1])      # the listener picks another row while the hold is armed
check("Z30 picking another track ends the hold the moment that track's media arrives",
      wait_for(lambda: app.playback_started_signal.calls) and app._finished_track is False
      and app.playback_started_signal.calls[0][1] == "vid1" and app._pending_fetch_id == "vid1",
      (app._finished_track, app.playback_started_signal.calls))

RESOLVE_CALLS.clear()
RESOLVE_HOLD[0] = 0.4
app = finished_app(mode=mod.STOP_AFTER_ONCE)
app.update_player_ui()
app.toggle_playback()
wait_for(lambda: app.stream_refreshed_signal.calls)
RESOLVE_HOLD[0] = 0.0
RESOLVE_CALLS.clear()
app.vlc_player = FakePlayer(mod.vlc.State.Ended, ms=100000, length=100000)
app._ended_trigger = False
app._has_played_current = True
app.is_playing = True
app.update_player_ui()                      # the replayed track has now run to its end as well
check("Z31 the replayed track is stopped after itself again, and held with a replay again",
      app.advances == [] and RESOLVE_CALLS == [] and app._finished_track is True
      and app.play_btn.text == mod.REPLAY_GLYPH, (app.advances, RESOLVE_CALLS, app.play_btn.text))
check("Z32 the one-shot spent itself back to off, with the hold still remembering it was made under one",
      app.stop_after_current == mod.STOP_AFTER_OFF
      and app._finished_track_armed_under == mod.STOP_AFTER_ONCE,
      (app.stop_after_current, app._finished_track_armed_under))
RESOLVE_CALLS.clear()
app.toggle_playback()
check("Z33 the replay keeps working every time it is pressed",
      wait_for(lambda: RESOLVE_CALLS) and RESOLVE_CALLS == ["vid0"] and app._finished_track is False,
      (RESOLVE_CALLS, app._finished_track))
RESOLVE_CALLS.clear()

check("Z34 the tray entry says what the player-bar button says",
      '"Replay Track"' in _source
      and "_finished_track" in _source[_source.index("# Play / Pause Action"):][:400])
check("Z35 a scrub goes through the finished-media verdict before libVLC is asked for anything",
      "_player_media_is_finished()" in _source[_source.index("def on_seek"):][:1400])
check("Z36 so does a Play press, and so does the Space key that reaches it",
      "_replay_finished_track()" in _source[_source.index("def toggle_playback"):][:900])
check("Z37 a replay re-resolves the loaded stream rather than rewinding the media it finished on",
      "_renew_loaded_stream(force=True)" in _source[_source.index("def _replay_finished_track"):][:3000])
_ended_branch = _source[_source.index("elif state == vlc.State.Ended"):][:2600]
check("Z38 the hold is armed by the same pass that decides not to advance, and that decision uses the read-ahead's own look-ahead",
      "_hold_finished_track(" in _ended_branch
      and "self._next_playback_preview() is None" in _ended_branch)
_note_block = _source[_source.index("def _note_loaded_stream"):][:3000]
_hold_block = _source[_source.index("def _hold_finished_track"):][:1600]
check("Z40 anything arriving on the player ends the hold, and arming a hold ends any replay still marked in flight",
      "self._finished_track = False" in _note_block and "self._replay_in_flight = False" in _note_block
      and "self._replay_in_flight = False" in _hold_block)
# "With the rest of the player state" means inside the same constructor, so the window this check
# reads is the constructor itself - from the `def` above the anchor to the `def` below it - rather
# than a fixed run of characters after one assignment. Wave 6 moved the constructor into
# yt_msd/ui/bootstrap.py, where what follows that assignment is not what followed it in the .pyw.
_init_at = _source.index("self._pending_stream_seek_at = None")
_init_block = _source[_source.rindex("\n    def ", 0, _init_at):_source.index("\n    def ", _init_at)]
check("Z41 and the hold state is initialised with the rest of the player state",
      "self._finished_track = False" in _init_block and "self._replay_in_flight = False" in _init_block)
check("Z42 the three captions are named constants in one block, one place sets that button, and nothing else captions it",
      all(name in _source[:_source.index("STOP_AFTER_OFF = 0")]
          for name in ("PLAY_GLYPH", "PAUSE_GLYPH", "REPLAY_GLYPH"))
      and _source.count("self.play_btn.setText(") == 0 and "btn.setText(REPLAY_GLYPH)" in _source
      and "btn.setText(PAUSE_GLYPH if getattr(self, 'is_playing', False) else PLAY_GLYPH)" in _source)
check("Z44 nothing in the replay block acts while a fetch or a refresh owns the player",
      "self._stream_is_switching()" in _source[_source.index("def _player_media_is_finished"):][:2000]
      and "self._stream_is_switching()" in _source[_source.index("def _replay_finished_track"):][:3000])

RESOLVE_CALLS.clear()
app = stream_app(ms=40000, length=900000, state=mod.vlc.State.Ended, age=3600.0, moved=None,
                 dead=True, attempts=mod.STREAM_REFETCH_LIMIT)      # died 14 minutes in, and the
app._has_played_current = False                                      # watchdog's reloads ran out
app._finished_track = False
app.update_player_ui()
check("Z45 a stream that gave out part-way through is not offered back as a replay, because the verdict is not taken from vlc.State.Ended on its own",
      app._finished_track is False and app.play_btn.text != mod.REPLAY_GLYPH
      and app.advances == [] and app._player_media_is_finished() is False,
      (app._finished_track, app.play_btn.text, app.advances, app._player_media_is_finished()))
RESOLVE_HOLD[0] = 0.4          # keeps the reload this press started in flight while it is read
app.toggle_playback()
check("Z47 the ask is what starts the reload the watchdog had given up on",
      app._stream_refetch_attempts == 1 and app.is_playing is True
      and app._stream_renew_started_at is not None,
      (app._stream_refetch_attempts, app.is_playing, app._stream_renew_started_at))
check("Z48 and it picks the track up where it stopped, not from 0:00",
      wait_for(lambda: RESOLVE_CALLS) and RESOLVE_CALLS == ["vid0"]
      and app._pending_stream_seek_ms == 40000 and app._pending_stream_seek_frac is None,
      (RESOLVE_CALLS, app._pending_stream_seek_ms, app._pending_stream_seek_frac))
RESOLVE_HOLD[0] = 0.0
wait_for(lambda: app.stream_refreshed_signal.calls)
check("Z48b the fresh media that arrives starts with a clean allowance again",
      app._stream_refetch_attempts == 0, app._stream_refetch_attempts)
RESOLVE_CALLS.clear()

app = stream_app(ms=40000, length=900000, state=mod.vlc.State.Ended, age=3600.0, moved=None,
                 dead=True, attempts=mod.STREAM_REFETCH_LIMIT)
app._has_played_current = True
app._finished_track = False
app.playback_index = 4
app.shuffle_history = [4]
app.update_player_ui()
check("Z49 a short-ended stream whose reloads ran out still advances, as it always did",
      app.advances == [5] and app._finished_track is False
      and app.play_btn.text != mod.REPLAY_GLYPH, (app.advances, app._finished_track, app.play_btn.text))
app50 = stream_app(ms=40000, length=900000, state=mod.vlc.State.Ended, age=3600.0, moved=None,
                   dead=True, attempts=mod.STREAM_REFETCH_LIMIT, mode=mod.STOP_AFTER_ONCE)
app50._has_played_current = True
app50._finished_track = False
app50.playback_index = 4
app50.update_player_ui()
check("Z50 the stop-after state is still spent on such a track, holds it, and holds no replay",
      app50.stop_after_current == mod.STOP_AFTER_OFF and app50._finished_track is False
      and app50.advances == [] and app50.is_playing is False
      and app50.play_btn.text != mod.REPLAY_GLYPH,
      (app50.stop_after_current, app50._finished_track, app50.advances, app50.play_btn.text))
check("Z51 only a media that genuinely reached its end can be held for replay",
      "finished = not self._stream_ended_short(total_ms, ms)" in _source
      and "elif finished and self._next_playback_preview() is None" in _source)

patch_resolve(fail=True)
RESOLVE_CALLS.clear()
app = stream_app(ms=40000, length=900000, state=mod.vlc.State.Ended, age=3600.0, moved=None,
                 dead=True, attempts=mod.STREAM_REFETCH_LIMIT - 1)
app._has_played_current = False
app._finished_track = False
app.update_player_ui()
app.toggle_playback()                                  # a Play press, so the reload is tried again
wait_for(lambda: app.stream_refreshed_signal.calls)
app._on_stream_refreshed(False, "Track 0")
check("Z53 a failed self-heal of a stream that died part-way through is not dressed up as a replay",
      app._finished_track is False and app._replay_in_flight is False
      and app.play_btn.text != mod.REPLAY_GLYPH,
      (app._finished_track, app._replay_in_flight, app.play_btn.text))
patch_resolve()
RESOLVE_CALLS.clear()
RESOLVE_HOLD[0] = 0.0

RESOLVE_CALLS.clear()
RESOLVE_HOLD[0] = 0.4
app = finished_app(mode=mod.STOP_AFTER_ONCE)
app.update_player_ui()
app.toggle_playback()
check("Z54 a replay is marked as in flight while its media is on the way",
      app._replay_in_flight is True and wait_for(lambda: app.stream_refreshed_signal.calls),
      app._replay_in_flight)
RESOLVE_HOLD[0] = 0.0
check("Z55 and the flag is gone with the media that arrives, leaving a replay that is replayable",
      app._replay_in_flight is False and app._finished_track is False
      and app._replay_finished_track() is True, (app._replay_in_flight, app._finished_track))
RESOLVE_HOLD[0] = 0.0
RESOLVE_CALLS.clear()

unpatch()

# ---------------------------------------------------------------------------
# AA. A stream URL fetch that a newer pick has made pointless is stopped rather than run out.
#     Only the yt-dlp process is faked here. The registry, the kill, and the error a killed
#     fetch raises are the real ones from the .pyw, and nothing here spawns a process or touches
#     the network.
# ---------------------------------------------------------------------------
print("AA. a superseded stream fetch is stopped")
_REAL_SUBPROCESS = seam.original("subprocess")
_REAL_FIND_YTDLP = seam.original("find_yt_dlp_executable")

SPAWNED = []          # every stand-in process this suite has been asked to produce


class FakeProc:
    """A yt-dlp run willing to be killed. communicate() stalls until something kills it, and
    reports how many stream resolutions were registered at the moment it was asked to run. It
    answers with the (stdout, stderr) pair a real Popen answers with."""

    def __init__(self, payload='{"url": "https://example.test/fetched",'
                              ' "http_headers": {"User-Agent": "probe-agent"}}', stall=1.2):
        self.payload = payload
        self.stall = stall
        self.kills = 0
        self.returncode = 0
        self.vid_id = ""
        self.registered_while_running = None

    def kill(self):
        self.kills += 1

    def communicate(self, timeout=None):
        self.registered_while_running = len(mod._stream_fetches)
        deadline = time.time() + self.stall
        while time.time() < deadline and not self.kills:
            time.sleep(0.01)
        return self.payload, ""


def fake_popen(args, **kwargs):
    proc = FakeProc()
    proc.vid_id = next((str(a).split("v=")[-1] for a in args if "watch?v=" in str(a)), "")
    SPAWNED.append(proc)
    return proc


# Only Popen is replaced, because Popen is the thing under test. Everything else a
# subprocess module offers - run, DEVNULL, PIPE, STARTUPINFO, TimeoutExpired - stays
# the genuine one. This matters more now than it did: the seam patches `subprocess`
# in every module that imports it, including the audio helpers, which call
# subprocess.run for real. A stand-in written for one yt-dlp function would break
# them, and the breakage would show up as a check about something else entirely.
FAKE_SUBPROCESS = seam.partial_module(_REAL_SUBPROCESS, Popen=fake_popen)

seam.patch("subprocess", FAKE_SUBPROCESS)
seam.patch("find_yt_dlp_executable", lambda: "fake-yt-dlp")



def attempt_resolve(vid_id):
    try:
        return ("resolved", _REAL_RESOLVE(vid_id))
    except BaseException as exc:
        return ("raised", type(exc).__name__)


SPAWNED.clear()
aa_single = attempt_resolve("vidSolo")
check("AA1 a stream resolution is registered while its yt-dlp is running",
      aa_single[0] == "resolved" and SPAWNED[-1].registered_while_running == 1,
      (aa_single, SPAWNED[-1].registered_while_running))
check("AA2 a resolution that has finished is not left in the registry",
      mod._stream_fetches == [], mod._stream_fetches)

SPAWNED.clear()
aa_threads = {}
for _tag, _vid in (("kept", "vidKeep"), ("dropped", "vidDrop")):
    threading.Thread(target=lambda t=_tag, v=_vid: aa_threads.__setitem__(t, attempt_resolve(v)),
                     daemon=True).start()
wait_for(lambda: len(mod._stream_fetches) == 2)
by_vid = {p.vid_id: p for p in SPAWNED}
aa_stopped = mod.cancel_stream_fetches(keep_vid_id="vidKeep")
check("AA3 a resolution for a track that has been superseded is stopped",
      aa_stopped == 1 and by_vid["vidDrop"].kills == 1, (aa_stopped, by_vid["vidDrop"].kills))
check("AA4 the resolution of the track that is still wanted is left to finish",
      by_vid["vidKeep"].kills == 0, by_vid["vidKeep"].kills)
_aa_dropped = wait_for(lambda: "dropped" in aa_threads)
check("AA5 the stopped resolution ends as superseded, not as a track that failed to resolve",
      _aa_dropped and aa_threads["dropped"] == ("raised", "StreamFetchSupersededError"), aa_threads)
check("AA6 and it is dropped from the registry while the kept one is still there",
      wait_for(lambda: [e["vid_id"] for e in mod._stream_fetches] == ["vidKeep"]),
      mod._stream_fetches)
by_vid["vidKeep"].kills = 1        # lets the keeper out of its stall without cancelling it
check("AA7 the kept resolution finishes with the URL it was asked for",
      wait_for(lambda: "kept" in aa_threads) and aa_threads["kept"][0] == "resolved"
      and aa_threads["kept"][1][0] == "https://example.test/fetched", aa_threads)
check("AA8 nothing is left registered once both resolutions are done",
      wait_for(lambda: mod._stream_fetches == []), mod._stream_fetches)

SPAWNED.clear()
mod.run_yt_dlp_json(["--flat-playlist", "--no-playlist", "ytsearch5:some artist"])
check("AA9 an extraction run - a search - is not cancellable as a stream fetch is",
      SPAWNED[-1].registered_while_running == 0 and mod._stream_fetches == [],
      (SPAWNED[-1].registered_while_running, mod._stream_fetches))
check("AA10 the stopping is asked for in one place, and keeps one named track",
      _source.count("def cancel_stream_fetches(keep_vid_id=None):") == 1
      and _source.count("def _cancel_superseded_stream_fetches(self, keep_vid_id=None):") == 1)

patch_resolve()
app = make_app(shadow_play=False)
obsolete = FakeProc(stall=0.0)
obsolete.vid_id = "vid9"
own_fetch = FakeProc(stall=0.0)
own_fetch.vid_id = "vid0"
mod._stream_fetches.extend([{"proc": obsolete, "vid_id": "vid9", "superseded": False},
                            {"proc": own_fetch, "vid_id": "vid0", "superseded": False}])
app._stream_refetching = True
app.play_result(app.search_results[0])
check("AA11 picking a track stops a stream fetch that belongs to another track",
      obsolete.kills == 1, obsolete.kills)
check("AA12 and leaves its own fetch - the one its prefetched URL may still arrive through - alone",
      own_fetch.kills == 0, own_fetch.kills)
check("AA13 and releases the refresh flag a stopped reload of the replaced track was holding",
      app._stream_refetching is False, app._stream_refetching)
mod._stream_fetches.clear()
unpatch()

app = make_app(shadow_play=False)
app._loaded_stream = ("vid0", "https://example.test/old", "probe-agent", time.monotonic())


def superseded_resolve(vid_id):
    time.sleep(0.3)     # long enough for the refresh to be seen in flight, then stopped
    raise mod.StreamFetchSupersededError("superseded by a newer pick")


seam.patch("resolve_stream_url", superseded_resolve)
app._renew_loaded_stream(force=True)
check("AA14 a reload of the track on the player is held as in flight while it runs",
      app._stream_refetching is True, app._stream_refetching)
check("AA15 a reload stopped by a newer pick releases that flag and reports no failure",
      wait_for(lambda: app._stream_refetching is False) and app.stream_refreshed_signal.calls == [],
      (app._stream_refetching, app.stream_refreshed_signal.calls))
unpatch()

_search_window = _source[_source.index("def perform_search"):][:1700]
_play_window = _source[_source.index("def play_result"):][:4000]
_dl_window = _source[_source.index("def download_single"):][:5000]
check("AA16 a new search is what stops the fetches it supersedes, keeping the playing track's",
      "keep = keep_fetch_vid_id or getattr(self, 'current_video_id', None)" in _search_window
      and "self._cancel_superseded_stream_fetches(keep_vid_id=keep)" in _search_window)
check("AA17 the search also lets go of the track the player was waiting on",
      "self._pending_fetch_id = None" in _search_window
      and "self._is_loading_stream = False" in _search_window)
check("AA18 a restore that fetches and re-searches back to back keeps its own fetch",
      "def perform_search(self, is_playlist=False, keep_fetch_vid_id=None):" in _source
      and "self.perform_search(is_playlist=is_pl, keep_fetch_vid_id=v_id)" in _source)
check("AA19 picking a track asks for the stopping, keeping its own resolution",
      "self._cancel_superseded_stream_fetches(keep_vid_id=vid_id)" in _play_window)
check("AA20 both the play path and the reload path read superseded as not a failure",
      _source.count("except StreamFetchSupersededError:") == 2,
      _source.count("except StreamFetchSupersededError:"))
check("AA21 a batch announces itself in the click that asked for it, before any yt-dlp answers",
      _source.count('self.dl_progress_signal.emit(f"(0/{self._batch_total_count}) Starting "') == 1
      and _source.index('self.dl_progress_signal.emit(f"(0/{self._batch_total_count}) Starting "')
      < _source.index("threading.Thread(target=bg_download"))
check("AA22 every track is reported as working when yt-dlp is handed it, not after yt-dlp answers",
      'self._dl_progress_percent(vid_id, "0%")' in _dl_window
      and _dl_window.index('self._dl_progress_percent(vid_id, "0%")')
      < _dl_window.index("run_yt_dlp_download("))
check("AA23 a press with nothing queued says so instead of looking like a slow start",
      '"Nothing in the queue to download."' in _source)

seam.restore("subprocess")
seam.restore("find_yt_dlp_executable")

# ---------------------------------------------------------------------------
# AB. The channel name a search row shows, and the search that asks again when
#     YouTube answers with no channels at all. Only yt-dlp is faked: entry_channel_name,
#     the retry loop and the row builder are the real ones read out of the .pyw. Nothing
#     here runs a process, touches the network or shows a window.
# ---------------------------------------------------------------------------
print("=" * 72)
print("AB. a search row's channel name, and a search that came back nameless")

check("AB1 yt-dlp's channel is preferred over its uploader",
      mod.entry_channel_name({"channel": "Mnet K-POP", "uploader": "Mnet"}) == "Mnet K-POP")
check("AB2 an entry that reports only an uploader still gets a channel",
      mod.entry_channel_name({"uploader": "zehitadeuva"}) == "zehitadeuva")
check("AB3 the shelf fields count when channel and uploader are both absent",
      mod.entry_channel_name({"artist": "AND2BLE", "byline": "ignored"}) == "AND2BLE")
check("AB4 a handle on its own is the name, without the at-sign",
      mod.entry_channel_name({"uploader_id": "@1theKOriginals"}) == "1theKOriginals")
check("AB5 the channel handle works the same when the uploader one is missing",
      mod.entry_channel_name({"channel_id": "@Mnet"}) == "Mnet")
check("AB6 so does the handle inside the channel link",
      mod.entry_channel_name({"channel_url": "https://www.youtube.com/@JXSBPOFFICIAL"}) == "JXSBPOFFICIAL")
check("AB7 a /channel/UC link is an id and is not dressed up as a name",
      mod.entry_channel_name({"channel_url": "https://www.youtube.com/channel/UCoe0BXYv01VCt0JRhX1zSug"}) == "")
check("AB8 blank and non-string fields are not names",
      mod.entry_channel_name({"channel": "   ", "uploader": 7}) == "")
check("AB9 the sparse entry YouTube really does serve gets nothing invented",
      mod.entry_channel_name({"id": "yKItFB_HPhE", "title": "OMG - NewJeans", "duration": 232,
                              "channel": None, "channel_url": None, "uploader": None,
                              "uploader_id": None, "uploader_url": None}) == "")

_ab_app = mod.MainApp.__new__(mod.MainApp)
_ab_app.accent_color_name = "Blue"
_ab_app._thumbnail_labels = {}
_ab_app._playback_box = None
_ab_app._fetch_thumbnail = lambda video: None


def _ab_row_for(video):
    row = mod.QWidget()
    row.setFixedHeight(54)
    _ab_app.build_result_ui(row, video, set())
    return row


def _ab_channel(row):
    return next((w for w in row.findChildren(mod.QLabel)
                 if w.objectName() == "channelLabel"), None)


_ab_full = _ab_row_for({"id": "rowFull", "title": "AND2BLE - Aura",
                        "channel": "Mnet K-POP", "duration": 200})
_ab_handle = _ab_row_for({"id": "rowHandle", "title": "AND2BLE _ Aura | 1theKILLPO",
                          "uploader_id": "@1theKOriginals", "duration": 205})
_ab_sparse = _ab_row_for({"id": "rowSparse", "title": "OMG - NewJeans [Music Bank]",
                          "duration": 232})
check("AB10 a row for a normal entry shows the channel it names",
      _ab_channel(_ab_full) is not None and _ab_channel(_ab_full).text() == "Mnet K-POP",
      _ab_channel(_ab_full))
check("AB11 a row for an entry that only names a handle still gets a channel",
      _ab_channel(_ab_handle) is not None and _ab_channel(_ab_handle).text() == "1theKOriginals",
      _ab_channel(_ab_handle))
check("AB12 an entry naming no owner gets no channel label and keeps the rest of its row",
      _ab_channel(_ab_sparse) is None
      and _ab_sparse.findChild(mod.QCheckBox) is not None
      and any(w.objectName() == "durationLabel" for w in _ab_sparse.findChildren(mod.QLabel)))
_ab_app._thumbnail_labels.clear()

_ab_calls = []
_ab_answer = []


def _ab_fake_search(args, **kwargs):
    _ab_calls.append(list(args))
    return _ab_answer[min(len(_ab_calls) - 1, len(_ab_answer) - 1)]


def use_search_answers(payloads):
    """run_yt_dlp_json replaced by a scripted set of answers, recording each run's arguments."""
    _ab_calls.clear()
    del _ab_answer[:]
    _ab_answer.extend(payloads)
    seam.patch("run_yt_dlp_json", _ab_fake_search)
    return _ab_calls


_ab_nameless = {"entries": [{"id": f"s{i}", "title": f"Sparse {i}", "duration": 200 + i,
                             "channel": None, "uploader": None, "uploader_id": None}
                            for i in range(15)]}
_ab_named = {"entries": [{"id": f"r{i}", "title": f"Rich {i}", "duration": 200 + i,
                          "channel": f"Channel {i}"} for i in range(15)]}

_ab_seen = []
_ab_calls = use_search_answers([_ab_nameless, _ab_named])
_ab_res = mod.run_yt_dlp_text_search("newjeans omg live", status_cb=_ab_seen.append)
check("AB13 a search whose results name no channel is asked again", len(_ab_calls) == 2, _ab_calls)
check("AB14 and its rows come from the answer that did name channels",
      len(_ab_res) == 15 and all(mod.entry_channel_name(e) for e in _ab_res), _ab_res[:1])
check("AB15 the retry is said out loud while it happens",
      _ab_seen == ["Searching... (results with no channels, asking again)"], _ab_seen)
check("AB16 it is the same search command every time",
      all(c[:3] == ["--flat-playlist", "-J", "ytsearch15:newjeans omg live"] for c in _ab_calls),
      _ab_calls)

_ab_seen = []
_ab_calls = use_search_answers([_ab_named])
_ab_res = mod.run_yt_dlp_text_search("aura and2ble", status_cb=_ab_seen.append)
check("AB17 a search that names channels is not asked again",
      len(_ab_calls) == 1 and _ab_seen == [], (_ab_calls, _ab_seen))

_ab_calls = use_search_answers([_ab_nameless,
                                {"entries": [{"id": "s0", "title": "One sparse", "duration": 10}]},
                                _ab_nameless])
_ab_res = mod.run_yt_dlp_text_search("lofi hip hop radio", status_cb=_ab_seen.append)
check("AB18 the asking again is bounded", len(_ab_calls) == mod.SEARCH_CHANNEL_RETRIES + 1,
      len(_ab_calls))
check("AB19 and the biggest nameless answer is kept rather than the last one",
      len(_ab_res) == 15, len(_ab_res))

_ab_calls = use_search_answers([{"entries": []}])
_ab_res = mod.run_yt_dlp_text_search("nothing matches this at all")
check("AB20 an answer with no results is not re-run",
      len(_ab_calls) == 1 and _ab_res == [], (_ab_calls, _ab_res))

_ab_calls = use_search_answers([{"entries": [None, {"title": "entry with no id"}]}])
_ab_res = mod.run_yt_dlp_text_search("strange answer")
check("AB21 an entry without an id is dropped, and that is not read as a nameless answer",
      _ab_res == [] and len(_ab_calls) == 1, (_ab_res, _ab_calls))

# AB31 to AB39: rows that are not videos at all. A search for a band's name answers with the
# band's own channel among its fifteen rows - measured on a live search, that row is
# id=UCV1YxS0AVPOrx_HDj9Pgt8Q, ie_key=YoutubeTab, duration=None, url=https://www.youtube.com/
# channel/UCV1YxS0AVPOrx_HDj9Pgt8Q - and it used to be built as a track: no duration to show,
# "This video is unavailable" when played, and an "Open on YouTube" button built as
# watch?v=UCV1YxS0AVPOrx_HDj9Pgt8Q, which is not a page YouTube has. Duration is not the test
# that keeps or drops a row, because a live stream is a video with no duration either.
_ab_is_video = seam.original("flat_entry_is_video")
_ab_channel_row = {"id": "UCV1YxS0AVPOrx_HDj9Pgt8Q", "title": "f5ve", "_type": "url",
                   "ie_key": "YoutubeTab", "duration": None,
                   "url": "https://www.youtube.com/channel/UCV1YxS0AVPOrx_HDj9Pgt8Q",
                   "channel": "f5ve", "uploader": "f5ve", "uploader_id": "@f5ve_official"}
_ab_uploads_row = {"id": "UU1YxS0AVPOrx_HDj9Pgt8Q", "title": "Uploads", "_type": "url",
                   "ie_key": "YoutubeTab", "duration": None,
                   "url": "https://www.youtube.com/channel/UCV1YxS0AVPOrx_HDj9Pgt8Q/videos"}
_ab_playlist_row = {"id": "PLukcNB9L3w6mQh8VXOyE0gQ", "title": "f5ve - Abstract EP",
                    "_type": "url", "ie_key": "YoutubeTab", "duration": None,
                    "url": "https://www.youtube.com/playlist?list=PLukcNB9L3w6mQh8VXOyE0gQ",
                    "channel": "f5ve"}
_ab_radio_row = {"id": "RDMMWL8OwB0ElJg", "title": "f5ve - I Choose You - Topic",
                 "_type": "url", "ie_key": "Youtube", "duration": 173,
                 "url": "https://www.youtube.com/watch?v=WL8OwB0ElJg&list=RDMMWL8OwB0ElJg"}
_ab_live_row = {"id": "jfKfPfyJRdk", "title": "lofi hip hop radio - beats to relax/study to",
                "_type": "url", "ie_key": "Youtube", "duration": None,
                "url": "https://www.youtube.com/watch?v=jfKfPfyJRdk", "channel": "Lofi Girl"}
_ab_short_row = {"id": "aB3dEfGhIjK", "title": "f5ve - Magic Clock (short)", "_type": "url",
                 "ie_key": "Youtube", "duration": 51,
                 "url": "https://www.youtube.com/shorts/aB3dEfGhIjK", "channel": "f5ve"}
_ab_sparse_row = {"id": "yKItFB_HPhE", "title": "OMG - NewJeans", "duration": None,
                  "ie_key": "Youtube", "channel": None, "uploader": None}
_ab_other_row = {"id": "123456789", "title": "a track on another site", "_type": "url",
                 "ie_key": "Soundcloud", "duration": 210,
                 "url": "https://soundcloud.com/someone/a-track-on-another-site"}
check("AB31 the channel a search is named for is not a video row",
      _ab_is_video(_ab_channel_row) is False, _ab_channel_row)
check("AB32 nor is a channel's uploads shelf", _ab_is_video(_ab_uploads_row) is False)
check("AB33 nor a playlist that came back among the tracks", _ab_is_video(_ab_playlist_row) is False)
check("AB34 a radio row is kept: its url is a watch url of a real track",
      _ab_is_video(_ab_radio_row) is True)
check("AB35 a live stream is kept even though it has no duration",
      _ab_is_video(_ab_live_row) is True)
check("AB36 so is a short", _ab_is_video(_ab_short_row) is True)
check("AB37 and so is the sparse answer's row, which names no url at all",
      _ab_is_video(_ab_sparse_row) is True)
check("AB38 another extractor's row is judged by nothing here",
      _ab_is_video(_ab_other_row) is True)
check("AB39 a row with no id is still not a row", _ab_is_video({"title": "no id"}) is False
      and _ab_is_video(None) is False)

_ab_mixed = {"entries": [_ab_channel_row,
                         {"id": "WL8OwB0ElJg", "title": "f5ve - I Choose You", "duration": 173,
                          "ie_key": "Youtube", "channel": "f5ve",
                          "url": "https://www.youtube.com/watch?v=WL8OwB0ElJg"},
                         _ab_live_row,
                         {"id": "xRdIYnRVrSU", "title": "f5ve - Magic Clock", "duration": 154,
                          "ie_key": "Youtube", "channel": "f5ve",
                          "url": "https://www.youtube.com/watch?v=xRdIYnRVrSU"}]}
_ab_calls = use_search_answers([_ab_mixed])
_ab_res = mod.run_yt_dlp_text_search("F5ve")
check("AB40 the channel row is out of the results the search hands the window",
      [e.get('id') for e in _ab_res] == ["WL8OwB0ElJg", "jfKfPfyJRdk", "xRdIYnRVrSU"], _ab_res)
check("AB41 dropping it is not read as a nameless answer - the search itself is asked once, and the"
      " second run is the fill from further down",
      len(_ab_calls) == 2 and _ab_calls[0][:3] == ["--flat-playlist", "-J", "ytsearch15:F5ve"]
      and _ab_calls[1][2:4] == ["--playlist-items", "16-30"], _ab_calls)

# AB44 to AB49: a row under a second long, and the rows that replace the ones refused.
_ab_is_row = seam.original("row_is_worth_showing")
check("AB44 a row under a second long is not a track",
      _ab_is_row({"id": "aB3dEfGhIjK", "duration": 0.4}) is False
      and _ab_is_row({"id": "aB3dEfGhIjK", "duration": 0}) is False)
check("AB45 a row of exactly a second is, and so is a duration carried as text",
      _ab_is_row({"id": "aB3dEfGhIjK", "duration": 1}) is True
      and _ab_is_row({"id": "aB3dEfGhIjK", "duration": "184"}) is True)
check("AB46 no duration at all is kept - a live row, and the sparse answer, are both real tracks",
      _ab_is_row({"id": "jfKfPfyJRdk", "duration": None}) is True
      and _ab_is_row({"id": "jfKfPfyJRdk"}) is True
      and _ab_is_row({"id": "jfKfPfyJRdk", "duration": "not a number"}) is True)


def _ab_video_rows(prefix, count, start=0):
    """Rows shaped like the ones a search really answers: an eleven-character id and a watch url."""
    def _vid(i):
        return f"{prefix}{i}abcdefghij"[:11]
    return [{"id": _vid(i), "title": f"{prefix} {i}", "duration": 180 + i,
             "ie_key": "Youtube", "channel": f"Channel {i}",
             "url": f"https://www.youtube.com/watch?v={_vid(i)}"}
            for i in range(start, start + count)]


_ab_seen = []
_ab_calls = use_search_answers([{"entries": [_ab_channel_row] + _ab_video_rows("near", 14)},
                                {"entries": _ab_video_rows("far", 20, start=15)}])
_ab_res = mod.run_yt_dlp_text_search("and2ble aura", status_cb=_ab_seen.append)
check("AB47 the rows a search loses are replaced from further down the same search",
      len(_ab_res) == 15 and _ab_res[0]["title"] == "near 0" and _ab_res[-1]["title"] == "far 15",
      [e.get('title') for e in _ab_res])
check("AB48 the filling is bounded by the fifteen rows a search shows, and no row appears twice",
      len(_ab_res) == 15 and len({e.get('id') for e in _ab_res}) == 15, len(_ab_res))
check("AB49 the filling says what it is doing, and only happens when rows were actually dropped",
      _ab_seen == ["Searching... (replacing the results that cannot be played)"], _ab_seen)
_ab_seen = []
_ab_calls = use_search_answers([{"entries": _ab_video_rows("full", 15)}])
_ab_res = mod.run_yt_dlp_text_search("bo burnham inside", status_cb=_ab_seen.append)
check("AB50 a search that filled its fifteen rows is not asked a second time",
      len(_ab_calls) == 1 and len(_ab_res) == 15 and _ab_seen == [], (_ab_calls, _ab_res))


def _ab_fill_gives_up(args, **kwargs):
    _ab_calls.append(list(args))
    if len(_ab_calls) == 1:
        return {"entries": [_ab_channel_row] + _ab_video_rows("half", 14)}
    raise RuntimeError("simulated yt-dlp giving up on the deeper half")


_ab_calls.clear()
_ab_seen = []
seam.patch("run_yt_dlp_json", _ab_fill_gives_up)
_ab_res = mod.run_yt_dlp_text_search("half of it playable", status_cb=_ab_seen.append)
check("AB51 a deeper half that fails keeps the rows already in hand",
      len(_ab_res) == 14 and len(_ab_calls) == 2, (len(_ab_res), len(_ab_calls)))
seam.restore("run_yt_dlp_json")

_ab_calls = use_search_answers([{"entries": [_ab_channel_row, _ab_playlist_row]}])
_ab_res = mod.run_yt_dlp_text_search("f5ve official")
check("AB42 a search that found only a channel and a playlist returns no rows",
      _ab_res == [] and len(_ab_calls) == 1, (_ab_res, _ab_calls))
check("AB43 the dropping happens in the search's own reader, not again in the window",
      open(SRC, encoding="utf-8").read().count("flat_entry_is_video") == 0
      and open(SRC, encoding="utf-8").read().count("row_is_worth_showing") == 0,
      open(SRC, encoding="utf-8").read().count("flat_entry_is_video"))
seam.restore("run_yt_dlp_json")


def _ab_retry_gives_up(args, **kwargs):
    _ab_calls.append(list(args))
    if len(_ab_calls) == 1:
        return _ab_nameless
    raise RuntimeError("simulated yt-dlp giving up on the retry")


_ab_calls.clear()
seam.patch("run_yt_dlp_json", _ab_retry_gives_up)
_ab_res = mod.run_yt_dlp_text_search("lofi hip hop radio", status_cb=_ab_seen.append)
check("AB26 a retry that gives up does not lose the search", len(_ab_res) == 15, len(_ab_res))
check("AB27 and it stops asking instead of throwing away the results it has",
      len(_ab_calls) == 2, len(_ab_calls))
seam.restore("run_yt_dlp_json")

_ab_timeouts = []


def _ab_record_timeout(args, **kwargs):
    _ab_timeouts.append(kwargs.get("timeout"))
    return _ab_nameless if len(_ab_timeouts) == 1 else _ab_named


seam.patch("run_yt_dlp_json", _ab_record_timeout)
_ab_res = mod.run_yt_dlp_text_search("lofi hip hop radio")
check("AB28 the search itself is still waited on for the full extraction timeout",
      _ab_timeouts[0] == mod.YTDLP_EXTRACT_TIMEOUT, _ab_timeouts)
check("AB29 a bonus attempt is cut off sooner than the search itself",
      _ab_timeouts[1] == mod.SEARCH_RETRY_TIMEOUT, _ab_timeouts)
_ab_timeouts.clear()
seam.patch("run_yt_dlp_json", lambda args, **kw: (_ab_timeouts.append(kw.get("timeout")), _ab_named)[1])
mod.run_yt_dlp_text_search("aura and2ble")
check("AB30 an answer that names channels is asked once, on the search's own timeout",
      _ab_timeouts == [mod.YTDLP_EXTRACT_TIMEOUT], _ab_timeouts)
seam.restore("run_yt_dlp_json")

_ab_search_window = _source[_source.index("def perform_search"):]
_ab_text_branch = _ab_search_window[_ab_search_window.index("                else:"):][:300]
check("AB22 the typed-in search goes through the retrying helper",
      "run_yt_dlp_text_search(" in _ab_text_branch and "ytsearch15:" not in _ab_text_branch,
      _ab_text_branch)
# Four readers of a channel name now, and all four through the one lookup: the definition, the
# search's retry test, the result row, and - new with the trace - yt-dlp's summary line, which
# counts how many entries named a channel because that is what a sparse search is judged on. The
# count is exact on purpose, and AB23b keeps the entry point's own half of it exact too.
check("AB23 the row reads its channel through the lookup the search also checks",
      _source.count("entry_channel_name(") == 4, _source.count("entry_channel_name("))
check("AB23b the entry point still reads a channel in exactly one place",
      open(SRC, encoding="utf-8").read().count("entry_channel_name(") == 1,
      open(SRC, encoding="utf-8").read().count("entry_channel_name("))
check("AB24 no search or row code pulls a channel out of an entry by hand any more",
      _source.count(".get('channel')") == 0, _source.count(".get('channel')"))
check("AB25 a pasted URL or playlist search is left exactly as it was",
      '"--flat-playlist", "-J", "--playlist-items", "1-100", query,' in _source)

# ============================================================================
# AC - the play button over a result thumbnail belongs to the pointer
# ============================================================================
# The button is meant to be up while the pointer is on that thumbnail and gone the moment it is
# not, and Qt's own enter and leave events are not a reliable enough account of "the moment it is
# not" to build it on alone: scrolling moves rows out from under a pointer that never moved and Qt
# sends no Leave for a pointer that never moved, a row that the same scroll builds lands under a
# pointer with no Enter, and a row torn down under the pointer is simply deleted. So the button is
# read off the pointer (ThumbnailWidget._pointer_on_tile), only one row at a time may hold it
# (MainApp._hover_tile), and while a row holds it the question is asked again on a timer
# (THUMB_HOVER_RECHECK_MS).
#
# What follows is a real ThumbnailWidget inside a real result row, in a real window parked where
# nobody will look at it, with QCursor replaced by a stand-in that says where the pointer is - the
# harness's own pointer, so a check can put it on a thumbnail without moving anybody's mouse, and
# take it back off again. Enter and Leave are the events Qt itself delivers on a hover, sent here
# the way the suite sends everything it drives. The same behaviours measured against a real cursor
# and Qt's own dispatch, including the case Qt sends no Leave for, are in the scratch probe
# .test_harness/probe_thumb_hover_fix.py.
from PySide6.QtCore import QEvent

_ac_app = QApplication.instance() or QApplication([])


def _ac_drain(times=12):
    for _ in range(times):
        _ac_app.processEvents()


def _ac_until(predicate, timeout=3.0):
    """Spin the event loop - timers and posted events included - until the button is in the state
    asked for, so a check waits for the behaviour rather than for a number of processEvents."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        _ac_app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def _ac_button(tile):
    """A tile's button state, tolerating a row that has already been deleted."""
    try:
        return tile.play_btn.isVisible()
    except RuntimeError:
        return False


class _HarnessPointer:
    """QCursor for the duration of this section: a position the harness says the pointer is at.
    Only pos() is asked of QCursor by the code under test."""

    def __init__(self, at):
        self.at = at

    def pos(self):
        return self.at


_pointer = _HarnessPointer(mod.QPoint(-1, -1))   # a point no row of this window can ever be at
seam.patch("QCursor", _pointer)

_ac_host = mod.MainApp.__new__(mod.MainApp)
_ac_host.accent_color_name = "Blue"
_ac_host._thumbnail_labels = {}
_ac_host._playback_box = None
_ac_host._fetch_thumbnail = lambda video: None
_ac_host._hover_tile = None
# Parentless, unlike the app's own: this MainApp was made with __new__ for the harness, and Shiboken
# refuses a half-built object as a timer's parent. The attribute below is what keeps it alive.
_ac_host._thumb_hover_timer = mod.QTimer()
_ac_host._thumb_hover_timer.setInterval(mod.THUMB_HOVER_RECHECK_MS)
_ac_host._thumb_hover_timer.timeout.connect(lambda: _ac_host._recheck_thumb_hover())

_ac_window = mod.QWidget()
_ac_window.resize(500, 400)
_ac_layout = mod.QVBoxLayout(_ac_window)
_ac_layout.setAlignment(mod.Qt.AlignTop)
_ac_window.move(-32000, -32000)       # shown, because a row is only under a pointer if it is on
_ac_window.show()                     # screen at all, but nowhere a probe should be looked at
_ac_drain()


def _ac_row(video_id):
    """A result row built the way the results pane builds one, with the thumbnail tile inside it."""
    placeholder = mod.QWidget()
    placeholder.setFixedHeight(54)
    _ac_host.build_result_ui(placeholder, {"id": video_id, "title": f"Track {video_id}",
                                           "channel": f"Channel {video_id}"}, set())
    _ac_layout.addWidget(placeholder)
    _ac_drain()
    return placeholder, placeholder.findChild(mod.ThumbnailWidget)


def _ac_point(tile, dx=0, dy=0):
    """A point over this tile, dx and dy away from its middle."""
    centre = tile.mapToGlobal(tile.rect().center())
    return mod.QPoint(centre.x() + dx, centre.y() + dy)


def _ac_hover(tile, dx=0, dy=0):
    """Put the pointer on that tile and hand the row the Enter Qt would have sent for it."""
    _pointer.at = _ac_point(tile, dx, dy)
    QApplication.sendEvent(tile, QEvent(QEvent.Type.Enter))
    _ac_drain()


def _ac_unhover(tile, dx=0, dy=0):
    """Move the pointer off that tile and hand the row the Leave Qt would have sent for it."""
    _pointer.at = _ac_point(tile, dx, dy)
    QApplication.sendEvent(tile, QEvent(QEvent.Type.Leave))
    _ac_drain()



_row_a, _tile_a = _ac_row("hoverOn")
_ac_hover(_tile_a)
check("AC1 the play button goes up when the pointer is put on the thumbnail",
      _ac_button(_tile_a))
check("AC2 that row is the one the app is tracking, and it is being re-checked while it holds it",
      _ac_host._hover_tile is _tile_a and _ac_host._thumb_hover_timer.isActive())

_ac_unhover(_tile_a, dx=150)                        # the same row, beside the thumbnail
check("AC3 the button goes away when the pointer is on the row but not on the thumbnail",
      not _ac_button(_tile_a) and not _tile_a._pointer_on_tile(), _tile_a.mapFromGlobal(_pointer.pos()))
check("AC4 and nothing is left tracking or re-checking that row",
      _ac_host._hover_tile is None and not _ac_host._thumb_hover_timer.isActive())

QApplication.sendEvent(_tile_a, QEvent(QEvent.Type.Enter))
_ac_drain()
check("AC5 an Enter the pointer did not cause does not put a button up",
      not _ac_button(_tile_a) and _ac_host._hover_tile is None)

# A row built while the pointer is already parked where that row ends up - the lazy build of a row
# scrolled back into view. No Enter is sent for it, because no pointer moved, and this is the case
# behind a row whose play button never appeared until the mouse was wiggled.
_pointer.at = _ac_point(_tile_a, dy=54)             # one row down, where the next row will sit
_ac_drain()
_row_b, _tile_b = _ac_row("builtUnderPointer")
check("AC6 a row built under a pointer that has not moved shows its button with no Enter at all",
      _ac_button(_tile_b), (_tile_b.rect(), _tile_b.mapFromGlobal(_pointer.pos())))

# One row at a time: the next row the pointer is genuinely on takes the button off the stale one.
_ac_hover(_tile_a)
check("AC7 only one row holds the button, so pointing at another row takes it off the first",
      _ac_button(_tile_a) and not _ac_button(_tile_b),
      (_ac_button(_tile_a), _ac_button(_tile_b)))
check("AC8 and the row being tracked is the row under the pointer",
      _ac_host._hover_tile is _tile_a)

# The row moved out from under a pointer that never moved - what a scroll does to a row - with the
# recheck held still so what Qt alone leaves behind can be seen on its own.
_ac_hover(_tile_b)
_ac_host._thumb_hover_timer.stop()
_ac_layout.takeAt(_ac_layout.indexOf(_row_b))
_row_b.move(0, 300)                                  # the row is nowhere near the pointer now
_ac_drain()
check("AC9 with nothing re-checking, that row keeps its button: no Leave ever reached it",
      _ac_button(_tile_b) and _ac_host._hover_tile is _tile_b
      and not _tile_b._pointer_on_tile(), _tile_b.mapFromGlobal(_pointer.pos()))
_ac_host._thumb_hover_timer.start()
check("AC10 the recheck takes it off, within the interval it is set to run on",
      _ac_until(lambda: not _ac_button(_tile_b),
                timeout=mod.THUMB_HOVER_RECHECK_MS / 1000.0 + 2.0),
      _ac_button(_tile_b))
check("AC11 and it stops re-checking a list nobody is pointing at",
      _ac_host._hover_tile is None and not _ac_host._thumb_hover_timer.isActive())



# The row going away under the pointer, which is what the results pane does in two places: the
# scroll tearing a row out of a placeholder, and a new search throwing the whole list away.
_ac_hover(_tile_a)                                  # the pointer is on it and its button is up
_tile_a.hide()                                      # the pane scrolls it out from under it
_ac_drain()
check("AC12 a row hidden under the pointer keeps no button - it is not under anything any more",
      not _ac_button(_tile_a) and _ac_host._hover_tile is None
      and not _ac_host._thumb_hover_timer.isActive())

_tile_a.show()
_ac_drain()
_ac_hover(_tile_a)
check("AC13 a row put back under the pointer takes its button back up", _ac_button(_tile_a))
_ac_host.clear_result_ui(_row_a)                    # the scroll tearing this row down
_ac_drain()
check("AC14 clear_result_ui settles the button before the row is deleted, and stops tracking it",
      not _ac_button(_tile_a) and _ac_host._hover_tile is None
      and not _ac_host._thumb_hover_timer.isActive())

_row_c, _tile_c = _ac_row("newSearch")
_ac_hover(_tile_c)
_ac_host._clear_thumb_hover()                       # a new search replacing every row
_ac_drain()
check("AC15 throwing the list away throws the row holding the button away with it",
      not _ac_button(_tile_c) and _ac_host._hover_tile is None
      and not _ac_host._thumb_hover_timer.isActive())
check("AC16 and not one row of the window is left showing a play button",
      not any(_ac_button(t) for t in _ac_window.findChildren(mod.ThumbnailWidget)))

seam.restore("QCursor")                           # the pointer the app reads is the real one again


# The wiring those checks ran through, checked in the source the checks are reading.
_ac_lookup = _source[_source.index("def _pointer_on_tile"): _source.index("def set_pointer_hover")]
_ac_enter = _source[_source.index("    def enterEvent"): _source.index("    def leaveEvent")]
_ac_events = _source[_source.index("    def leaveEvent"): _source.index("    def _box_style")]
_ac_lazy = _source[_source.index("def lazy_load_visible_results"): _source.index("def build_queue_item_ui")]
_ac_new_search = _source[_source.index("def _on_search_results"): _source.index("def _reset_results_scroll")]
_ac_teardown = _source[_source.index("def clear_result_ui"): _source.index("def lazy_load_visible_results")]
check("AC17 a row that is hidden - torn down, or scrolled out of the pane - can never claim the pointer",
      "if not self.isVisible():" in _ac_lookup)
check("AC18 an Enter puts a button up only after the pointer is asked where it is",
      "_pointer_on_tile()" in _ac_enter and "play_btn.show()" not in _ac_enter, _ac_enter)
check("AC19 a row being built re-reads the pointer, and a row going away drops the button",
      "QTimer.singleShot(0, self._refresh_after_layout)" in _ac_events
      and _ac_events.count("self.set_pointer_hover(False)") == 2, _ac_events)
check("AC20 scrolling the list re-checks the row holding the button",
      "self._recheck_thumb_hover()" in _ac_lazy)
check("AC21 tearing a row down settles its button before its widgets are deleted",
      "set_pointer_hover(False)" in _ac_teardown)
check("AC22 a new search drops the row that was holding the button",
      "self._clear_thumb_hover()" in _ac_new_search)
check("AC23 the button is shown in exactly one place, in the row's own hover claim",
      _source.count("play_btn.show()") == 1, _source.count("play_btn.show()"))
check("AC24 the recheck has one timer, on the interval the constant names",
      _source.count("self._thumb_hover_timer = QTimer(self)") == 1
      and "self._thumb_hover_timer.setInterval(THUMB_HOVER_RECHECK_MS)" in _source)
check("AC25 that interval is a delay a person would notice as soon as it stopped being needed",
      50 <= mod.THUMB_HOVER_RECHECK_MS <= 1000, mod.THUMB_HOVER_RECHECK_MS)






print("AD. the number on the volume slider is the number libVLC is told")

from PySide6.QtWidgets import QLabel, QSlider


class _AdVolumeHarness(mod.QWidget):
    on_volume_changed = mod.MainApp.on_volume_changed


def _ad_volume_harness():
    """A widget holding only what on_volume_changed touches, and a stand-in player that
    remembers every value it was handed instead of sending one to an audio output."""
    h = _AdVolumeHarness()
    h.volume_val = 100
    h.vol_slider = QSlider()
    h.vol_pct = QLabel()
    h.applied = []

    class _Recorder:
        def audio_set_volume(self, val):
            h.applied.append(val)

    h.vlc_player = _Recorder()
    return h


h = _ad_volume_harness()
for _ad_val in range(0, 151):
    h.on_volume_changed(_ad_val)
check("AD1 every slider position from 0 to 150 is handed to libVLC as itself",
      h.applied == list(range(0, 151)), h.applied)

h = _ad_volume_harness()
h.on_volume_changed(150)
check("AD2 the top of the slider is 1.5x amplitude, not the 2x it used to be doubled into",
      h.applied == [150] and h.vol_pct.text() == "150%", h.applied)

h = _ad_volume_harness()
h.on_volume_changed(100)
check("AD3 100% raises and lowers nothing - it is 0 dB in the audio output",
      h.applied == [100] and h.vol_pct.text() == "100%", h.applied)

h = _ad_volume_harness()
h.on_volume_changed(135)
check("AD4 the percentage the listener reads is the percentage the player was told",
      h.applied == [135] and h.vol_pct.text() == "135%", h.applied)

_ad_states = {}
for _ad_val in (0, 100, 105, 115, 116, 150):
    h = _ad_volume_harness()
    h.on_volume_changed(_ad_val)
    _ad_states[_ad_val] = h.vol_slider.property("volume_state")
check("AD5 the orange and red warnings keep the thresholds they have always had",
      _ad_states == {0: "normal", 100: "normal", 105: "orange", 115: "orange",
                     116: "red", 150: "red"}, _ad_states)

_ad_handler = _source[_source.index("    def on_volume_changed"):
                      _source.index("    def on_volume_typed")]
check("AD6 the handler rescales nothing any more",
      "vlc_vol" not in _ad_handler and "self.vlc_player.audio_set_volume(val)" in _ad_handler,
      _ad_handler)
check("AD7 no doubling of 101-150 onto 101-200 is left anywhere in the file",
      "(val - 100) * 2" not in _source and "vlc_vol" not in _source)
check("AD8 the slider still spans 0-150, so the honest top is the top the listener sees",
      _source.count("self.vol_slider.setRange(0, 150)") == 1)
check("AD9 the saved volume is applied the same way at start-up as on every slider move",
      _source.count("self.vlc_player.audio_set_volume(self.volume_val)") == 1
      and _source.count("self.vlc_player.audio_set_volume(val)") == 1)


print("=" * 72)
print("AE. the playback clocks are numbers the program itself holds")

# A constant that only the harness reads is a number the tests agree with and the player does not,
# which is exactly what a wave that moves a constant can leave behind. So each of these two is
# patched through the seam and the player's own decision is watched, rather than the value read
# back off the entry point.
RESOLVE_CALLS.clear()
patch_resolve()
seam.patch("PREFETCH_SECONDS_BEFORE_END", 0)
app = make_app(index=0, vid="vid0")
app.vlc_player = FakePlayer(mod.vlc.State.Playing, ms=80000, length=100000)  # 20 s left
app.update_player_ui()
time.sleep(0.35)
check("AE1 with the read-ahead trigger moved to zero seconds, the player stops reading ahead - the decision is made with the number the program holds",
      RESOLVE_CALLS == [], RESOLVE_CALLS)
seam.restore("PREFETCH_SECONDS_BEFORE_END")
RESOLVE_CALLS.clear()
app = make_app(index=0, vid="vid0")
app.vlc_player = FakePlayer(mod.vlc.State.Playing, ms=80000, length=100000)  # the same 20 s left
app.update_player_ui()
check("AE2 and the same track is read ahead again as soon as the program's own number is back",
      wait_for(lambda: "vid1" in RESOLVE_CALLS), RESOLVE_CALLS)
unpatch()

_STALL_AS_THE_PROGRAM_HAS = mod.STREAM_STALL_SECONDS
RESOLVE_CALLS.clear()
patch_resolve()
app = stream_app(age=0.0, moved=13.0, renew_age=1.0)   # a position still for thirteen seconds
app.update_player_ui()
check("AE3 a position that has stood still for thirteen seconds is convicted under the program's own eight-second rule",
      app._stream_dead is True and RESOLVE_CALLS == [], (app._stream_dead, RESOLVE_CALLS))
seam.patch("STREAM_STALL_SECONDS", 60)
RESOLVE_CALLS.clear()
app = stream_app(age=0.0, moved=13.0, renew_age=1.0)   # the same track, the same thirteen seconds
app.update_player_ui()
check("AE4 the same track is left alone when that threshold is moved to sixty seconds - the watchdog asks the program, not the suite",
      app._stream_dead is False and RESOLVE_CALLS == [], (app._stream_dead, RESOLVE_CALLS))
seam.restore("STREAM_STALL_SECONDS")
app = stream_app(age=0.0, moved=13.0, renew_age=1.0)
app.update_player_ui()
check("AE5 the eight-second rule is back and convicts it again",
      mod.STREAM_STALL_SECONDS == _STALL_AS_THE_PROGRAM_HAS and app._stream_dead is True,
      (mod.STREAM_STALL_SECONDS, app._stream_dead))
unpatch()

_playback_numbers = ("PREFETCH_SECONDS_BEFORE_END", "PREFETCH_URL_MAX_AGE", "PREFETCH_CACHE_LIMIT",
                     "STREAM_STALL_SECONDS", "STREAM_RESUME_GRACE", "STREAM_URL_MAX_AGE",
                     "STREAM_REFETCH_LIMIT", "STREAM_RENEW_COOLDOWN", "STREAM_END_SLACK_MS",
                     "STREAM_SEEK_RESTORE_TIMEOUT")
_number_holders = {_name: seam.owners(_name) for _name in _playback_numbers}
check("AE6 every one of these numbers is a single object wherever it is held, whichever module ends up holding it",
      all(len({getattr(_m, _name) for _m in _holders}) == 1 for _name, _holders in _number_holders.items()),
      {_name: seam.owned_by(_name) for _name, _holders in _number_holders.items()})


print("AF. a track picked while the player is still starting is held, and says so")
patch_resolve()
RESOLVE_CALLS.clear()
app = make_app(index=0, vid="vid0", shadow_play=False)
app._vlc_ready = False                       # exactly how the window starts: the thread has not finished
app.play_result(app.search_results[2])
check("AF1 nothing is fetched and nothing is handed to VLC while libVLC is still being started",
      RESOLVE_CALLS == [] and not app.vlc_instance.medias, (RESOLVE_CALLS, app.vlc_instance.medias))
check("AF2 the hold is announced - the difference between a wait and a dead click",
      any("Starting the player" in text for text, _p, _c in app.status_messages), app.status_messages)
check("AF3 announced once, not once per 200 ms retry", len(app.status_messages) == 1, app.status_messages)
for _ in range(23):
    app._note_waiting_for_player()
check("AF4 four and a half seconds of retries adds nothing", len(app.status_messages) == 1, app.status_messages)
app._note_waiting_for_player()               # the 25th retry: five seconds of waiting
check("AF5 and it is said again on the five-second mark", len(app.status_messages) == 2, app.status_messages)
check("AF6 the retries are counted on the window, so they can be thinned this way",
      app._vlc_ready_waits == 25, app._vlc_ready_waits)
app._vlc_ready = True
app.play_result(app.search_results[2])
check("AF7 the pick that was held runs as soon as the player exists",
      wait_for(lambda: app.vlc_instance.medias) and RESOLVE_CALLS == ["vid2"],
      (RESOLVE_CALLS, app.vlc_instance.medias))
check("AF8 the counting restarts, so a later wait would announce itself too",
      app._vlc_ready_waits == 0, app._vlc_ready_waits)
RESOLVE_CALLS.clear()
app_nowait = make_app(shadow_play=False)
app_nowait.play_result(app_nowait.search_results[1])
check("AF9 a pick made after the player was ready says nothing about waiting",
      RESOLVE_CALLS == ["vid1"]
      and not any("Starting the player" in text for text, _p, _c in app_nowait.status_messages),
      (RESOLVE_CALLS, app_nowait.status_messages))


class _CapturedStdout:
    """sys.stdout for two checks: what --trace would have printed for this wait."""
    def __init__(self):
        self.text = ""

    def write(self, text):
        self.text += text
        return len(text)

    def flush(self):
        pass


_trace_level_as_it_was = mod.trace.get_level()
_stdout_as_it_was, sys.stdout = sys.stdout, _CapturedStdout()
mod.trace.set_level(1)
app_traced = make_app(shadow_play=False)
app_traced._vlc_ready = False
app_traced._note_waiting_for_player()
mod.trace.set_level(0)
app_traced._note_waiting_for_player()        # the same wait again, with --trace off
_captured_wait = sys.stdout.text
sys.stdout = _stdout_as_it_was
mod.trace.set_level(_trace_level_as_it_was)
check("AF10 --trace records the pick it is holding and for how long",
      "holding the pick" in _captured_wait and "s so far" in _captured_wait, _captured_wait)
check("AF11 with the trace off the same wait prints not one character",
      _captured_wait.count("holding the pick") == 1, _captured_wait)
check("AF12 both ways of picking a track - a search row and a local file - hold it the same way",
      _source.count("self._note_waiting_for_player()") == 2,
      _source.count("self._note_waiting_for_player()"))
check("AF13 the player's own startup is timed where it happens, and only asks for the line when tracing",
      "trace.note(\"libVLC ready after" in _source
      and "_vlc_started_at = time.monotonic()" in _source)
check("AF14 and the wait is measured from the retry, not from a guess about how long VLC takes",
      "trace.note(\"holding the pick" in _source)
unpatch()


# ============================================================================
# AG. what a click is for: the caret a press anywhere else takes away, the number
# typed into the volume box, and the track a thumbnail starts
# ============================================================================
# Three things the pointer could not do until now. A row played only if the press landed on the
# 30 px button floating over its thumbnail. The volume could only be dragged along a 100 px slider.
# And a press that landed on anything that does not ask for focus - a caption, a result row's
# placeholder, the empty part of a pane, the plain widget behind the player bar - left the box that
# had the focus holding it, cursor still blinking, while the next keystroke went nowhere near it.
#
# All of it is measured with real widgets and real press events. QApplication.sendEvent is how the
# suite already drives events (section AC sends Enter and Leave with it) and it runs the
# application's own filters on the way in, which is the path MainApp is installed on as a filter of
# the whole QApplication. MainApp itself cannot be that filter here - a harness MainApp never ran
# __init__ and so has no Qt object behind it to install - so the click half of it is held by a real
# QWidget, and the wiring that puts it on the application is checked in the source below.
import textwrap

from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QLineEdit, QPushButton


def _ag_drain(times=12):
    for _ in range(times):
        QApplication.processEvents()


def _ag_press(widget, dx=0, dy=0, button=Qt.LeftButton):
    """A press delivered to this widget at dx, dy away from its middle - the press a click on that
    spot of it is, without anybody's mouse moving."""
    local = QPoint(widget.rect().center().x() + dx, widget.rect().center().y() + dy)
    QApplication.sendEvent(widget, QMouseEvent(QEvent.MouseButtonPress, QPointF(local),
                                               QPointF(widget.mapToGlobal(local)),
                                               button, button, Qt.NoModifier))
    _ag_drain()


def _ag_release(widget):
    centre = widget.rect().center()
    QApplication.sendEvent(widget, QMouseEvent(QEvent.MouseButtonRelease, QPointF(centre),
                                               QPointF(widget.mapToGlobal(centre)),
                                               Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
    _ag_drain()


def _ag_key(widget, key, text="", modifiers=Qt.NoModifier):
    """A keystroke delivered to this widget - the key a hand on the keyboard is."""
    QApplication.sendEvent(widget, QKeyEvent(QEvent.KeyPress, key, modifiers, text))
    _ag_drain()


class _AgClickFilter(mod.QWidget):
    """MainApp's answer to a click, on an object Qt will accept as an application filter.

    The shim cannot simply hold MainApp.eventFilter: that method ends in a bare super() call bound
    to MainApp itself, which refuses an object that is not one. So the shim makes the same call the
    real filter makes - MainApp's own click answer - and lets the press through, while the check
    below reads the wiring that puts that answer on the whole application."""
    def eventFilter(self, obj, event):
        if event.type() in (event.Type.MouseButtonPress, event.Type.MouseButtonDblClick):
            mod.MainApp._release_typing_focus(self, obj, event)
        return False


_ag_filter = _AgClickFilter()
QApplication.instance().installEventFilter(_ag_filter)

_ag_window = mod.QWidget()
_ag_window.resize(420, 300)
_ag_window.move(-32000, -32000)            # shown, because a press only lands on a widget that is
_ag_layout = mod.QVBoxLayout(_ag_window)   # on screen at all, but nowhere a probe is looked at
_ag_box = QLineEdit("search terms")
_ag_caption = mod.QLabel("Format:")
_ag_button = QPushButton("Search")
_ag_placeholder = mod.QWidget()            # a result row is one of these, with widgets built into it
_ag_placeholder.setFixedHeight(54)
for _ag_w in (_ag_box, _ag_caption, _ag_button, _ag_placeholder):
    _ag_layout.addWidget(_ag_w)
_ag_window.show()
_ag_drain()

_ag_box.setFocus()
_ag_drain()
check("AG1 the typable box holds the caret to begin with", QApplication.focusWidget() is _ag_box)
_ag_press(_ag_caption)
check("AG2 a press on something that cannot type takes the caret out of it",
      QApplication.focusWidget() is None)
_ag_box.setFocus()
_ag_drain()
_ag_press(_ag_box)
check("AG3 a press inside the box leaves the caret where it is", QApplication.focusWidget() is _ag_box)
_ag_box.setFocus()
_ag_drain()
_ag_press(_ag_button)
check("AG4 a press on a control that takes focus for itself is not the window asking for no caret",
      QApplication.focusWidget() is _ag_box)
_ag_box.setFocus()
_ag_drain()
_ag_press(_ag_placeholder)
check("AG5 a press on the empty part of a row or a pane takes the caret too",
      QApplication.focusWidget() is None)
_ag_button.setFocus()
_ag_drain()
_ag_press(_ag_caption)
check("AG6 and a press never strips focus off a control that already had it - the local list's "
      "Ctrl+A, Ctrl+C, Del and F2 are answered only while that focus holds",
      QApplication.focusWidget() is _ag_button)
_ag_filter_src = _source[_source.index("    def eventFilter"):
                         _source.index("    def open_search_on_youtube")]
check("AG7 the answer is wired into the filter MainApp installs on the whole application",
      "MouseButtonPress" in _ag_filter_src
      and "self._release_typing_focus(obj, event)" in _ag_filter_src, _ag_filter_src[:400])


class _AgVolumeBoxHarness(mod.QWidget):
    on_volume_changed = mod.MainApp.on_volume_changed
    on_volume_typed = mod.MainApp.on_volume_typed


def _ag_volume_box():
    """What a typed volume touches: the box, the slider wired to the handler a dragged volume uses,
    and a stand-in player remembering every number it was handed instead of sending one to an output."""
    h = _AgVolumeBoxHarness()
    h.volume_val = 100
    h.applied = []
    h.vol_slider = QSlider(Qt.Horizontal, h)
    h.vol_slider.setRange(0, 150)
    h.vol_slider.setValue(100)      # the slider starts where the saved volume is, as it does in the app
    h.vol_pct = QLineEdit("100%", h)
    h.vol_pct.setMaxLength(4)
    h.vol_slider.valueChanged.connect(h.on_volume_changed)

    class _Recorder:
        def audio_set_volume(self, val):
            h.applied.append(val)

    h.vlc_player = _Recorder()
    return h


_ag_h = _ag_volume_box()
_ag_h.vol_pct.setText("73")                     # what typing 7 then 3 leaves in the box
_ag_h.on_volume_typed()
check("AG8 typing 73 hands 73 to libVLC, to the slider and to the box",
      _ag_h.applied == [73] and _ag_h.vol_slider.value() == 73 and _ag_h.vol_pct.text() == "73%",
      (_ag_h.applied, _ag_h.vol_pct.text()))
_ag_h = _ag_volume_box()
_ag_h.vol_pct.setText("999")
_ag_h.on_volume_typed()
check("AG9 a number past the top of the slider is clamped to it, and the warning colour goes with it",
      _ag_h.applied == [150] and _ag_h.vol_pct.text() == "150%"
      and _ag_h.vol_slider.property("volume_state") == "red", _ag_h.applied)
_ag_h = _ag_volume_box()
_ag_h.vol_pct.setText("")
_ag_h.on_volume_typed()
check("AG10 a box emptied and committed applies nothing and shows the volume the player is holding",
      _ag_h.applied == [] and _ag_h.vol_pct.text() == "100%", _ag_h.applied)
_ag_h = _ag_volume_box()
_ag_h.vol_pct.setText("ab")
_ag_h.on_volume_typed()
check("AG11 a box with no number in it is not a volume",
      _ag_h.applied == [] and _ag_h.vol_pct.text() == "100%", _ag_h.applied)
_ag_h = _ag_volume_box()
_ag_h.vol_pct.setText("0")
_ag_h.on_volume_typed()
check("AG12 0 is reachable by typing, and it is the mute it has always been",
      _ag_h.applied == [0] and _ag_h.vol_slider.property("volume_state") == "normal", _ag_h.applied)
_ag_h = _ag_volume_box()
_ag_h.vol_pct.setText("73")
_ag_h.on_volume_typed()
_ag_h.vol_slider.setValue(60)                   # and then the slider is dragged
check("AG13 a typed number and a dragged one go through the same handler, so they cannot disagree",
      _ag_h.applied == [73, 60] and _ag_h.vol_pct.text() == "60%", _ag_h.applied)
check("AG14 the box commits on Enter and on losing focus, through that one handler",
      _source.count("self.vol_pct.returnPressed.connect(self.on_volume_typed)") == 1
      and _source.count("self.vol_pct.editingFinished.connect(self.on_volume_typed)") == 1
      and "self.vol_pct = VolBox(" in _source)
_ag_commit = _ag_volume_box()
_ag_commit.vol_pct.editingFinished.connect(_ag_commit.on_volume_typed)
_ag_commit.resize(240, 90)
_ag_commit.move(-32000, -32000)
_ag_commit.show()
_ag_drain()
_ag_commit.vol_pct.setFocus()
_ag_drain()
_ag_commit.vol_pct.setText("42")
_ag_press(_ag_commit, 0, 80)                    # the click that goes somewhere else in the window
check("AG15 the click that takes the caret is also the commit - Enter is not the only way out",
      _ag_commit.applied == [42] and _ag_commit.vol_pct.text() == "42%"
      and QApplication.focusWidget() is None, _ag_commit.applied)


_ag_pick_host = mod.MainApp.__new__(mod.MainApp)
_ag_pick_host.accent_color_name = "Blue"
_ag_pick_host._thumbnail_labels = {}
_ag_pick_host._playback_box = None
_ag_pick_host._fetch_thumbnail = lambda video: None
_ag_pick_host._hover_tile = None
_ag_pick_host.current_video_id = None
_ag_pick_host.picked = []
_ag_pick_host.toggles = []
_ag_pick_host.play_result = lambda video, paused_at_start=False, from_nav=False: \
    _ag_pick_host.picked.append(video.get('id'))
_ag_pick_host.toggle_playback = lambda: _ag_pick_host.toggles.append(True)

_ag_pick_window = mod.QWidget()
_ag_pick_window.resize(220, 120)
_ag_pick_window.move(-32000, -32000)
_ag_pick_layout = mod.QVBoxLayout(_ag_pick_window)
_ag_pick_layout.setAlignment(mod.Qt.AlignTop)
_ag_tile = mod.ThumbnailWidget({"id": "tilePress", "title": "Press Anywhere"}, _ag_pick_host)
_ag_pick_layout.addWidget(_ag_tile)
_ag_pick_window.show()
_ag_drain()

for _ag_at in ((0, 0), (-40, -18), (40, 18), (-42, 0)):
    _ag_press(_ag_tile, *_ag_at)                # the middle of the tile, and each side of it
check("AG16 a press anywhere on the thumbnail plays that track - middle and edges alike",
      _ag_pick_host.picked == ["tilePress"] * 4, _ag_pick_host.picked)
_ag_pick_host.picked.clear()
_ag_tile.play_btn.show()
_ag_press(_ag_tile.play_btn)
_ag_release(_ag_tile.play_btn)
check("AG17 the hover button is left in place and still plays its row",
      _ag_pick_host.picked == ["tilePress"], _ag_pick_host.picked)
_ag_pick_host.picked.clear()
_ag_press(_ag_tile, 0, 0, Qt.RightButton)
check("AG18 a right press is not a pick",
      _ag_pick_host.picked == [] and _ag_pick_host.toggles == [])
_ag_pick_host.current_video_id = "tilePress"    # the track on the player is the one under the pointer
_ag_press(_ag_tile)
check("AG19 the tile of the track already on the player is the pause the player bar's own button "
      "gives, not a fresh pick that re-resolves the stream behind a track being heard",
      _ag_pick_host.picked == [] and _ag_pick_host.toggles == [True],
      (_ag_pick_host.picked, _ag_pick_host.toggles))
_ag_pick_host.current_video_id = "someOtherTrack"
_ag_pick_host.toggles.clear()
_ag_press(_ag_tile)
check("AG20 and a tile that is not the loaded track is picked",
      _ag_pick_host.picked == ["tilePress"] and _ag_pick_host.toggles == [])
_ag_pick_host.picked.clear()
_ag_press(_ag_tile.thumb_label)                 # the picture is a label filling the tile, so a click on
check("AG21 a press on the picture reaches the tile through the label that carries it - and the label "
      "wears no focus policy of its own, which is what makes that same press the click away from a "
      "typable box",
      _ag_pick_host.picked == ["tilePress"]
      and not (_ag_tile.thumb_label.focusPolicy() & (Qt.ClickFocus | Qt.StrongFocus)),
      _ag_pick_host.picked)
_ag_pick_host.picked.clear()
_ag_press_src = _source[_source.index("Play this track on a press anywhere"):
                        _source.index("    def enterEvent",
                                      _source.index("Play this track on a press anywhere"))]
check("AG22 the whole tile answers the press, and only a left one, and the tile wears the cursor "
      "that says so",
      "if event.button() == Qt.LeftButton:" in _ag_press_src
      and "self.parent_app.play_result(self.video)" in _ag_press_src
      and _source.count("self.setCursor(Qt.PointingHandCursor)") == 1, _ag_press_src)

# The typed number is written by the class layout.py builds, so that class is lifted out of the
# file it lives in and driven here: what these checks measure is the widget the player bar gets.
_volbox_start = _source.index("        class VolBox(QLineEdit):")
_volbox_src = textwrap.dedent(_source[_volbox_start:
                                      _source.index("        self.vol_pct = VolBox(", _volbox_start)])
_volbox_ns = {"QLineEdit": QLineEdit, "Qt": Qt}      # what the class body reaches for
exec(compile(_volbox_src, "yt_msd/ui/layout.py:VolBox", "exec"), _volbox_ns)

_ag_typed = _ag_volume_box()                    # the same harness a dragged volume is measured on
_ag_typed.vol_pct = _volbox_ns["VolBox"]("73%")
_ag_typed.vol_pct.setObjectName("volPct")
_ag_typed.vol_pct.setFixedWidth(50)
_ag_typed.vol_pct.setMaxLength(4)
_ag_typed.vol_pct.returnPressed.connect(_ag_typed.on_volume_typed)
_ag_typed.vol_pct.editingFinished.connect(_ag_typed.on_volume_typed)
mod.QVBoxLayout(_ag_typed).addWidget(_ag_typed.vol_pct)
_ag_typed.resize(140, 40)
_ag_typed.move(-32000, -32000)
_ag_typed.show()
_ag_drain()
_ag_typed.vol_pct.setFocus()
_ag_drain()
check("AG23 the caret arriving from the keyboard picks the number out and leaves the sign out of it",
      _ag_typed.vol_pct.selectionStart() == 0 and _ag_typed.vol_pct.selectionLength() == 2,
      (_ag_typed.vol_pct.selectionStart(), _ag_typed.vol_pct.selectionLength()))
_ag_press(_ag_typed.vol_pct, 18, 0)             # a press to the right of the percent sign
check("AG24 a press past the sign puts the caret back on the number rather than after the read-out",
      _ag_typed.vol_pct.cursorPosition() <= 2 and _ag_typed.vol_pct.text() == "73%",
      _ag_typed.vol_pct.cursorPosition())
_ag_key(_ag_typed.vol_pct, Qt.Key_End)
check("AG25 and so does End", _ag_typed.vol_pct.cursorPosition() == 2,
      _ag_typed.vol_pct.cursorPosition())
_ag_key(_ag_typed.vol_pct, Qt.Key_5, "5")
check("AG26 which is why a digit typed there can only land inside the number",
      _ag_typed.vol_pct.text() == "735%", _ag_typed.vol_pct.text())
_ag_typed.vol_pct.clearFocus()                  # the click that goes elsewhere is the commit
_ag_drain()
check("AG27 a number typed past the top of the slider is clamped, and the caret it is rewritten "
      "with is back on the number",
      _ag_typed.applied == [150] and _ag_typed.vol_pct.text() == "150%"
      and _ag_typed.vol_pct.cursorPosition() <= len("150%") - 1,
      (_ag_typed.applied, _ag_typed.vol_pct.text(), _ag_typed.vol_pct.cursorPosition()))
_ag_typed.vol_pct.setText("73%")                  # and the read-out itself is not editable
_ag_drain()
_ag_typed.vol_pct.setFocus()                      # the commit above was a focus-out, so it is back
_ag_drain()
_ag_press(_ag_typed.vol_pct, 18, 0)               # caret on the number, nothing selected
_ag_key(_ag_typed.vol_pct, Qt.Key_Delete)
check("AG28 a forward delete stops at the sign rather than eating the read-out",
      _ag_typed.vol_pct.text() == "73%", _ag_typed.vol_pct.text())
_ag_key(_ag_typed.vol_pct, Qt.Key_A, "a", Qt.ControlModifier)   # Ctrl+A over the whole read-out
check("AG29 a select-all that reaches the sign selects the number and stops there",
      _ag_typed.vol_pct.selectionStart() == 0 and _ag_typed.vol_pct.selectionLength() == 2,
      (_ag_typed.vol_pct.selectionStart(), _ag_typed.vol_pct.selectionLength()))
check("AG30 the number wears none of the box every other QLineEdit in the app is given - the theme "
      "says so beside the slider's own colour rules",
      "QLineEdit#volPct {{ background: transparent; border: none; padding: 0px; }}" in _source)
check("AG31 it is the caption's own 50 px again, and the double click that put the volume back to "
      "100 survived the change",
      "self.vol_pct.setFixedWidth(50)" in _source
      and "def mouseDoubleClickEvent" in _volbox_src
      and "win.vol_slider.setValue(100)" in _volbox_src)

# Everything above hands the box the caret with setFocus(), which is the road the Tab key takes.
# A click is two events in Qt's own order - measured with QTest, which takes the focus step that
# QApplication.sendEvent skips: the focus arrives first and says the mouse brought it, and the
# press that follows it in the same click is answered by QLineEdit itself, which puts the caret
# where the pointer landed and loses whatever was picked out. The two steps are asked for here in
# that order, because a click on this box is a request to change the volume and the number has to
# still be picked out when the second of them is done.
_ag_typed.vol_pct.setText("73%")
_ag_typed.vol_pct.clearFocus()
_ag_drain()
check("AG32 the number is nobody's business while the caret is held elsewhere",
      not _ag_typed.vol_pct.hasFocus() and _ag_typed.vol_pct.selectionLength() == 0,
      (_ag_typed.vol_pct.hasFocus(), _ag_typed.vol_pct.selectionStart(),
       _ag_typed.vol_pct.selectionLength()))
_ag_typed.vol_pct.setFocus(Qt.MouseFocusReason)      # the first half of the click
_ag_drain()
check("AG33 that half picks the number out whole - 73 out of 73% - and leaves the sign alone",
      _ag_typed.vol_pct.hasFocus() and _ag_typed.vol_pct.selectionStart() == 0
      and _ag_typed.vol_pct.selectionLength() == 2,
      (_ag_typed.vol_pct.hasFocus(), _ag_typed.vol_pct.selectionStart(),
       _ag_typed.vol_pct.selectionLength()))
_ag_press(_ag_typed.vol_pct)                         # the press the same click delivers
check("AG34 and the press that lands on top of it leaves the number picked out all the same",
      _ag_typed.vol_pct.selectionStart() == 0 and _ag_typed.vol_pct.selectionLength() == 2
      and _ag_typed.vol_pct.text() == "73%",
      (_ag_typed.vol_pct.selectionStart(), _ag_typed.vol_pct.selectionLength(),
       _ag_typed.vol_pct.text()))
_ag_key(_ag_typed.vol_pct, Qt.Key_9, "9")
check("AG35 which is what one key straight after such a click is for: the whole number is replaced",
      _ag_typed.vol_pct.text() == "9%", _ag_typed.vol_pct.text())
_ag_press(_ag_typed.vol_pct)                         # the box already holds the caret now
check("AG36 a click on a box that already holds the caret is the click that puts the caret between "
      "the digits, and it picks nothing out",
      _ag_typed.vol_pct.selectionLength() == 0 and _ag_typed.vol_pct.text() == "9%",
      (_ag_typed.vol_pct.selectionStart(), _ag_typed.vol_pct.selectionLength(),
       _ag_typed.vol_pct.text()))
check("AG37 both roads in end at the same pick-out, and the click is remembered only long enough to "
      "outlast the press that came with it",
      "_pick_out_the_number" in _volbox_src
      and "self._focus_came_with_a_click = (e.reason() == Qt.MouseFocusReason)" in _volbox_src
      and _volbox_src.count("self._focus_came_with_a_click = False") == 2,
      _volbox_src[:400])

QApplication.instance().removeEventFilter(_ag_filter)

# ---------------------------------------------------------------------------
# AH. A row in the results list that has no stream. bg_fetch can fail on a track the player
#     walked into on its own - a removed upload, or a row a search page lists that YouTube will
#     not serve - and when it does, nothing else in the app can notice: the media still on the
#     player is the finished one whose Ended tick was already spent, and play_result() has just
#     cleared the two flags that branch waits on. These checks run the real play_result, the
#     real bg_fetch and the real handler, with only the yt-dlp run and the player clock faked.
#     A real Qt connection hands a failure raised on a worker thread to the GUI thread; the Sig
#     stand-in calls the slot back directly, which is the sequence and thread count here.
# ---------------------------------------------------------------------------
print("=" * 72)
print("AH. a row in the list that has no stream")

RESOLVE_HOLD[0] = 0.0


def app_that_walks(mode=mod.STOP_AFTER_OFF, index=0, vid="vid0", fail_for=()):
    """A list being walked with no hand on the player, wired as __init__ wires it."""
    patch_resolve(fail_for=fail_for)
    app = make_app(index=index, vid=vid, mode=mode, shadow_play=False)
    app._search_stop_after_track = None
    app._is_loading_stream = False
    app._finished_track = False
    app._replay_in_flight = False
    app.playback_started_signal.connect(app._on_playback_started)
    app.stream_fetch_failed_signal.connect(app._on_stream_fetch_failed)
    return app


RESOLVE_CALLS.clear()
app_ah = app_that_walks(fail_for={"vid1"})
app_ah.play_result(app_ah.search_results[0])
wait_for(lambda: len(app_ah.playback_started_signal.calls) >= 1)
RESOLVE_CALLS.clear()
app_ah.play_next()                        # the changeover the player timer makes on its own
wait_for(lambda: len(app_ah.playback_started_signal.calls) >= 2)
check("AH1 one row with no stream does not stop the list - the track after it starts",
      [c[1] for c in app_ah.playback_started_signal.calls] == ["vid0", "vid2"],
      app_ah.playback_started_signal.calls)
check("AH2 the dead row is tried once and no more", RESOLVE_CALLS == ["vid1", "vid2"], RESOLVE_CALLS)
check("AH3 the listener is told which row was skipped",
      any(text.startswith("Skipping Track 1") for text, _p, _c in app_ah.status_messages),
      app_ah.status_messages)
check("AH4 skipping does not rearrange the list the listener is looking at - the walk is by index",
      [v.get('id') for v in app_ah.search_results] == ["vid0", "vid1", "vid2", "vid3", "vid4"]
      and app_ah.playback_index == 2, (app_ah.search_results, app_ah.playback_index))
check("AH5 a track that does start pays the skipping allowance back",
      app_ah._stream_skip_streak == 0, app_ah._stream_skip_streak)

RESOLVE_CALLS.clear()
app_ah2 = app_that_walks(fail_for={"vid1"})
app_ah2.play_result(app_ah2.search_results[1])   # the listener clicked that row themselves
wait_for(lambda: app_ah2.search_failed_signal.calls)
time.sleep(0.3)
check("AH6 a track the listener picked is theirs to retry - nothing plays behind their click",
      app_ah2.playback_started_signal.calls == [] and app_ah2._stream_skip_streak == 0
      and app_ah2.playback_index == 1,
      (app_ah2.playback_started_signal.calls, app_ah2._stream_skip_streak, app_ah2.playback_index))


RESOLVE_CALLS.clear()
app_ah3 = app_that_walks(fail_for={"vid1", "vid2", "vid3", "vid4"})
app_ah3.play_result(app_ah3.search_results[0])
wait_for(lambda: len(app_ah3.playback_started_signal.calls) >= 1)
RESOLVE_CALLS.clear()
app_ah3.play_next()
time.sleep(1.2)
check("AH7 a list with nothing playable in it is tried a bounded number of times, then waits",
      [c[1] for c in app_ah3.playback_started_signal.calls] == ["vid0"]
      and app_ah3._stream_skip_streak == mod.STREAM_ADVANCE_SKIP_LIMIT
      and len(RESOLVE_CALLS) == mod.STREAM_ADVANCE_SKIP_LIMIT + 1,
      (app_ah3.playback_started_signal.calls, app_ah3._stream_skip_streak, RESOLVE_CALLS))

RESOLVE_CALLS.clear()
app_ah4 = app_that_walks(mode=mod.STOP_AFTER_ALWAYS, fail_for={"vid1"})
app_ah4.play_result(app_ah4.search_results[0])
wait_for(lambda: len(app_ah4.playback_started_signal.calls) >= 1)
RESOLVE_CALLS.clear()
app_ah4.play_next()
time.sleep(0.4)
check("AH8 an armed 'stop after current' is not walked past - the listener asked it to stop there",
      RESOLVE_CALLS == ["vid1"] and app_ah4._stream_skip_streak == 0
      and app_ah4.playback_index == 1, (RESOLVE_CALLS, app_ah4._stream_skip_streak))

RESOLVE_CALLS.clear()
app_ah5 = app_that_walks()
app_ah5.play_result(app_ah5.search_results[0])
wait_for(lambda: len(app_ah5.playback_started_signal.calls) >= 1)
RESOLVE_CALLS.clear()
app_ah5._pending_fetch_id = "vid8"               # a newer pick owns the player now
app_ah5.stream_fetch_failed_signal.emit("vid1", True)
time.sleep(0.3)
check("AH9 a failure the window has already moved on from starts nothing",
      RESOLVE_CALLS == [] and app_ah5._stream_skip_streak == 0,
      (RESOLVE_CALLS, app_ah5._stream_skip_streak))
app_ah5.search_results = []                      # a single track opened by url has no list
app_ah5.stream_fetch_failed_signal.emit("vid1", True)
check("AH10 and neither does it when there is no list to walk on through",
      RESOLVE_CALLS == [] and app_ah5._stream_skip_streak == 0,
      (RESOLVE_CALLS, app_ah5._stream_skip_streak))
app_ah5.search_results = results()
app_ah5._pending_fetch_id = "vid1"
app_ah5.stream_fetch_failed_signal.emit("vid1", False)   # a track the listener picked
check("AH11 the same failure raised by a manual pick starts nothing either",
      RESOLVE_CALLS == [] and app_ah5._stream_skip_streak == 0,
      (RESOLVE_CALLS, app_ah5._stream_skip_streak))

_ah_fetch = _source[_source.index("def bg_fetch"):][:3000]
_ah_handler = _source[_source.index("def _on_stream_fetch_failed"):][:2400]
check("AH12 bg_fetch reports a failed resolution to that handler, saying whether the player made the pick",
      "self.stream_fetch_failed_signal.emit(vid_id, bool(from_nav))" in _ah_fetch
      and "stream_fetch_failed_signal = Signal(str, bool)" in _source)
check("AH13 it is connected where every other signal is connected",
      "self.stream_fetch_failed_signal.connect(self._on_stream_fetch_failed)"
      in open(os.path.join(os.path.dirname(SRC), "yt_msd", "ui", "bootstrap.py"),
              encoding="utf-8").read())
check("AH14 the allowance is a constant the program holds, not a number only the harness reads",
      "STREAM_ADVANCE_SKIP_LIMIT = 3"
      in open(os.path.join(os.path.dirname(SRC), "yt_msd", "playback", "stream.py"),
              encoding="utf-8").read()
      and "STREAM_ADVANCE_SKIP_LIMIT" in _ah_handler)
check("AH15 a started track clears the allowance, so a later dead row gets the same three tries",
      "self._stream_skip_streak = 0"
      in _source[_source.index("def _on_playback_started"):][:900])
unpatch()


print(f"{CHECKS - len(FAILS)} / {CHECKS} checks passed")
if FAILS:
    print("FAILED: " + "; ".join(FAILS))
    raise SystemExit(1)

