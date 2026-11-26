# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.ytdlp.runner).
import os
import re
import sys
import json
import time
import threading
import subprocess
import shutil
from yt_msd.subproc import _child_utf8_env, _hidden_window_kwargs
from yt_msd.util import trace
from yt_msd.ytdlp.install import YTDLP_EXTRACT_TIMEOUT, YtDlpMissingError, _yt_dlp_lookup_paths


_ytdlp_exe_cache = None

_ytdlp_exe_cache_lock = threading.Lock()



def find_yt_dlp_executable(refresh=False):
    """Path of the yt-dlp to use, or None. Resolved once and cached."""
    global _ytdlp_exe_cache
    with _ytdlp_exe_cache_lock:
        cached = _ytdlp_exe_cache
        if cached and not refresh and os.path.isfile(cached):
            return cached
        found = None
        for candidate in _yt_dlp_lookup_paths():
            if candidate and os.path.isfile(candidate):
                found = candidate
                break
        if not found:
            for name in ("yt-dlp", "yt-dlp.exe"):
                candidate = shutil.which(name)
                if candidate:
                    found = candidate
                    break
        _ytdlp_exe_cache = found
        return found



def get_yt_dlp_version(exe_path=None):
    """The version yt-dlp reports (e.g. '2026.08.19'), or '' when unavailable."""
    exe = exe_path or find_yt_dlp_executable()
    if not exe:
        return ""
    # Which yt-dlp this copy resolved to is the first thing a report about a failed extraction
    # needs, and it is not something the caller can guess at: there are three places it looks.
    trace.command("yt-dlp", [exe, "--version"])
    try:
        result = subprocess.run([exe, "--version"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, encoding="utf-8", errors="replace",
                                timeout=30, env=_child_utf8_env(), **_hidden_window_kwargs())
        text = (result.stdout or "").strip()
        return text.splitlines()[0] if text else ""
    except Exception:
        return ""



# ---------------------------------------------------------------------------
# Stream URL fetches that can be stopped mid-flight
# ---------------------------------------------------------------------------
# Resolving one track's stream URL is a yt-dlp run that takes seconds of network
# time. It is worth stopping that run when something newer makes its answer
# pointless - the listener clicked a different track, or started a new search -
# because the URL is going to be thrown away either way, and a request that is no
# longer wanted is still competing for the same network with the one that now
# matters. Every yt-dlp run that resolves a stream URL registers itself here while
# it runs, tagged with the track it is resolving and with the thread that started
# it. resolve_stream_url() is the only caller that registers: search extraction and
# downloading ask different questions and are not superseded this way.
_stream_fetches_lock = threading.Lock()

_stream_fetches = []                      # live stream URL resolutions

_stream_fetch_owner = threading.local()   # .vid_id / .entries for the thread doing the resolving



class StreamFetchSupersededError(RuntimeError):
    """The stream URL fetch was stopped because a newer pick made its answer pointless.

    Distinct from a track that failed to resolve: nothing went wrong with the track, the
    listener simply stopped wanting it, and the caller must not report it as a failure.
    """



def begin_stream_fetch(vid_id):
    """Open a cancellable window for this thread's resolution of vid_id's stream URL."""
    _stream_fetch_owner.vid_id = vid_id
    _stream_fetch_owner.entries = []



def end_stream_fetch():
    """Close it: a resolution that has finished cannot be cancelled and is not tracked."""
    entries = getattr(_stream_fetch_owner, "entries", None)
    _stream_fetch_owner.vid_id = None
    _stream_fetch_owner.entries = None
    if not entries:
        return
    with _stream_fetches_lock:
        for entry in entries:
            try:
                _stream_fetches.remove(entry)
            except ValueError:
                pass



def stream_fetch_vid_for_this_thread():
    """The track this thread is resolving a URL for, or None for any other yt-dlp run."""
    return getattr(_stream_fetch_owner, "vid_id", None)



def note_stream_fetch_process(proc, vid_id):
    """Called by run_yt_dlp_json for the process it just spawned on a stream URL resolution."""
    if vid_id is None:
        return
    entry = {"proc": proc, "vid_id": vid_id, "superseded": False}
    with _stream_fetches_lock:
        _stream_fetches.append(entry)
    entries = getattr(_stream_fetch_owner, "entries", None)
    if entries is not None:
        entries.append(entry)



def stream_fetch_was_superseded():
    """True when this thread's resolution was cancelled while its yt-dlp was still running."""
    return any(entry["superseded"] for entry in (getattr(_stream_fetch_owner, "entries", None) or []))



def cancel_stream_fetches(keep_vid_id=None):
    """Kill the yt-dlp runs resolving stream URLs right now, and return how many were stopped.

    keep_vid_id is the track that still owns an answer worth having - the one the user has just
    picked, or the one still on the player - and its resolution is left to finish.
    """
    stopped = 0
    with _stream_fetches_lock:
        for entry in list(_stream_fetches):
            if keep_vid_id is not None and entry["vid_id"] == keep_vid_id:
                continue
            # Marked before the kill so the waiting thread can tell its own cancellation apart
            # from a yt-dlp failure, and does not report the track as unplayable.
            entry["superseded"] = True
            try:
                entry["proc"].kill()
                stopped += 1
            except Exception:
                pass
    return stopped



def run_yt_dlp_json(args, timeout=YTDLP_EXTRACT_TIMEOUT):
    """Run yt-dlp with -J and return the info dictionary it prints."""
    exe = find_yt_dlp_executable()
    if not exe:
        raise YtDlpMissingError("yt-dlp is not installed on this system")
    started = time.monotonic()
    # The whole command line, including which yt-dlp was resolved: this is the line a search or a
    # stream resolution is decided by, and it is the thing a report is most useful with.
    trace.command("yt-dlp", [exe] + list(args))
    # Popen rather than subprocess.run: a stream URL resolution is cancellable, and cancelling
    # needs the handle to the process while it runs (see cancel_stream_fetches).
    proc = subprocess.Popen([exe] + list(args), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, encoding="utf-8", errors="replace",
                            env=_child_utf8_env(), **_hidden_window_kwargs())
    note_stream_fetch_process(proc, stream_fetch_vid_for_this_thread())
    try:
        result_stdout, result_stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.communicate()
        except Exception:
            pass
        trace.result("no answer within %ds, killed" % timeout)
        raise
    if stream_fetch_was_superseded():
        # The kill came from in here, not from yt-dlp giving up on the track.
        trace.result("stopped: a newer pick made this answer pointless (%.1fs)"
                     % (time.monotonic() - started))
        raise StreamFetchSupersededError("Stream URL fetch superseded by a newer pick")
    if proc.returncode != 0:
        tail = [line for line in (result_stderr or "").splitlines() if line.strip()]
        trace.result("failed: %s" % (tail[-1] if tail else "exit code %d" % proc.returncode))
        raise RuntimeError(tail[-1] if tail else f"yt-dlp exited with code {proc.returncode}")
    info = json.loads(result_stdout or "")
    trace.result(_extracted_summary(info, time.monotonic() - started))
    return info


def _extracted_summary(info, seconds):
    """One line saying what an extraction actually brought back.

    Never the URL. For a stream request the answer is a signed googlevideo link - a kilobyte of
    tokens with an expiry stamped on it - and trace output gets pasted into issue reports the way
    yt-msd-crash.log is. What is worth pasting is which formats were offered, which one is at the
    top of the list, how big it is and which host it comes from.
    """
    if not isinstance(info, dict):
        return "nothing back (%.1fs)" % seconds
    entries = info.get("entries")
    if isinstance(entries, list):
        named = sum(1 for e in entries if isinstance(e, dict) and entry_channel_name(e))
        return "%d entries, %d of them naming a channel (%.1fs)" % (len(entries), named, seconds)
    formats = info.get("formats") or []
    title = info.get("title") or info.get("id") or "no title"
    if not formats:
        return "%s - no formats offered (%.1fs)" % (title, seconds)
    chosen = formats[-1]
    bitrate = chosen.get("abr") or chosen.get("tbr")
    facts = ["%d formats" % len(formats),
             str(chosen.get("ext") or "?"),
             str(chosen.get("acodec") or "no audio"),
             ("%sk" % bitrate) if bitrate else "?k"]
    size = chosen.get("filesize") or chosen.get("filesize_approx")
    if size:
        facts.append("%.1f MB" % (size / 1048576.0))
    host = trace.url_host(chosen.get("url") or "")
    if host:
        facts.append(host)
    return "%s - %s (%.1fs)" % (title, " | ".join(facts), seconds)



# A result row's channel name is read out of the search entry, and a flat search entry
# carries only what YouTube's search response happened to include. Asked the same query
# twice in a row, yt-dlp has answered with channel names on all fifteen entries and with
# none at all - the entry reduced to id / title / url / duration, with channel,
# channel_url, uploader and uploader_id all null. Which of the two shapes YouTube serves
# is not something the GUI can decide: pinning youtube:player_client on the search
# changed nothing, every client following whatever that run was already going to be. A
# search is therefore retried when it comes back nameless, and a row reads whichever
# field the entry did manage to carry.
SEARCH_CHANNEL_RETRIES = 2

# A retry is a bonus on top of the search that already answered, so it is not waited on
# as long as the search itself is.
SEARCH_RETRY_TIMEOUT = 90



def entry_channel_name(video):
    """The channel a search entry names for its row, or '' when the entry names none."""
    for key in ('channel', 'uploader', 'artist', 'byline'):
        value = video.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    # The responses that name an owner without spelling it out still give the handle.
    for key in ('uploader_id', 'channel_id'):
        value = video.get(key)
        handle = value.strip() if isinstance(value, str) else ""
        if handle.startswith("@") and len(handle) > 1:
            return handle[1:]
    for key in ('uploader_url', 'channel_url'):
        if isinstance(video.get(key), str):
            found = re.search(r"/@([^/?#]+)", video[key])
            if found:
                return found.group(1)
    # A /channel/UC... link is an id, not a name, and is not used as one.
    return ""



def entry_display_title(video, fallback='Unknown'):
    """The words a search row is drawn with, which must never be nothing.

    `.get('title', 'Unknown')` only supplies its default when the key is *missing*, and yt-dlp
    answers some rows with the key present and nothing in it: the withdrawn upload a playlist
    still lists, a video whose title this client was not allowed to read, and the sparse search
    answer that strips a row down to its id. That None travels with the row into every checkbox,
    queue label and status line built from it, and it is what killed a results window while it was
    drawing a row - `AttributeError: 'NoneType' object has no attribute 'replace'`.

    The row itself is kept: it is a row of the search the listener asked for, and dropping the
    nameless ones would lose a track in silence. What changes is what it is called by - whatever
    the row does name becomes its label, in the order the row is worth reading: its own title,
    then the channel it belongs to, then its id, then the caller's word for it.
    """
    if not isinstance(video, dict):
        return fallback
    for key in ('title', 'fulltitle'):
        value = video.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    channel = entry_channel_name(video)
    if channel:
        return channel
    vid_id = video.get('id')
    if isinstance(vid_id, str) and vid_id.strip():
        return vid_id.strip()
    return fallback



# A search page lists more than tracks. Among the fifteen rows yt-dlp hands back can be the
# channel itself, a playlist, or a shelf of that channel's uploads, and a flat entry for one
# of those looks like any other entry - id, title, url, the channel's own name - except that
# its id is a channel id (UC…), a playlist id (PL… / UU…) or a radio id (RD…), its url is
# /channel/…, /playlist?list=… or /videos, and it carries no duration. Those rows used to
# reach the results list and read as a track that had gone missing: it has no duration to
# show, playing it spends a yt-dlp run on watch?v=<channel id>, which answers "This video is
# unavailable", and its "Open on YouTube" button opens the page YouTube says does not exist.
# A row is kept only when it points at a watchable video. Rows of any other extractor are
# kept exactly as they were - nothing here knows their id shapes and nothing used to judge them.
_YOUTUBE_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")

_YOUTUBE_WATCH_URL = re.compile(r"youtube\.com/(?:watch\?v=|shorts/|live/)[A-Za-z0-9_-]{11}")


def flat_entry_is_video(entry):
    """Whether a flat-playlist row points at a video this app can play and download.

    Duration is deliberately not the test: a live stream is a video and has no duration, and
    the sparse answer YouTube serves sometimes carries no duration for a real track either.
    What tells the two kinds of row apart is the url the row points at, and - when the row
    names no url worth reading - the shape of the id itself.
    """
    if not isinstance(entry, dict):
        return False
    vid_id = entry.get('id')
    if not isinstance(vid_id, str) or not vid_id.strip():
        return False
    url = entry.get('url') if isinstance(entry.get('url'), str) else ""
    ie_key = entry.get('ie_key') if isinstance(entry.get('ie_key'), str) else ""
    if not ('youtube.com' in url or 'youtu.be' in url
            or ie_key in ('Youtube', 'YoutubeTab', 'YoutubeMusic')):
        return True
    if _YOUTUBE_WATCH_URL.search(url):
        # A mix or radio row carries the watch url of the track it is seeded with, and
        # watch?v= with --no-playlist is that track - the row is worth keeping.
        return True
    return bool(_YOUTUBE_VIDEO_ID.fullmatch(vid_id))


# A video shorter than this is not a track. It is what a search page hands back for a video
# it cannot serve - a removed upload, an upload with no stream left - and in the results list
# it is a row that plays as a click that does nothing and downloads as a failure.
MIN_ROW_SECONDS = 1

# The rows a typed-in search shows (ytsearch15:<query>), and how far down the same search is
# read when some of those rows are refused: one extra search, asked only when rows were
# actually dropped, so one row YouTube will not serve does not leave the window a row short.
SEARCH_ROW_LIMIT = 15
SEARCH_FILL_BATCH = 30


def row_is_worth_showing(entry):
    """Whether a row that is a video is long enough to be a track.

    A row that names no duration is kept, because the two answers that carry none are the
    two worth keeping: a live stream, which is a real track with no length, and the sparse
    answer YouTube serves, which strips durations off ordinary tracks too.
    """
    if not isinstance(entry, dict):
        return False
    duration = entry.get('duration')
    if duration is None:
        return True
    try:
        return float(duration) >= MIN_ROW_SECONDS
    except (TypeError, ValueError):
        return True


def search_rows(payload):
    """The rows of one search answer that belong in the results list, in the order given."""
    return [e for e in ((payload or {}).get('entries') or [])
            if flat_entry_is_video(e) and row_is_worth_showing(e)]


def rows_from_further_down(query, kept, status_cb=None):
    """Fill a search's rows out of the rows below its own limit.

    Asked only when the answer lost rows to `flat_entry_is_video` or `row_is_worth_showing`,
    so a search that dropped a channel row still shows the fifteen rows a search usually
    shows. It asks for the deeper half of a bigger search - rows 16 to 30 of
    `ytsearch30:<query>` - because the rows already in hand are the better matches, and it
    deduplicates by id, keeps the batch to the search's own limit, and is silent about a
    deeper search that fails: the rows already in hand are the answer.
    """
    if len(kept) >= SEARCH_ROW_LIMIT:
        return kept
    if status_cb is not None:
        status_cb("Searching... (replacing the results that cannot be played)")
    seen = {e.get('id') for e in kept}
    try:
        info = run_yt_dlp_json(["--flat-playlist", "-J",
                                "--playlist-items", f"16-{SEARCH_FILL_BATCH}",
                                f"ytsearch{SEARCH_FILL_BATCH}:{query}"],
                               timeout=SEARCH_RETRY_TIMEOUT)
    except Exception:
        return kept
    for entry in search_rows(info):
        if len(kept) >= SEARCH_ROW_LIMIT:
            break
        if entry.get('id') in seen:
            continue
        seen.add(entry.get('id'))
        kept.append(entry)
    return kept


def run_yt_dlp_text_search(query, status_cb=None, retries=SEARCH_CHANNEL_RETRIES,
                           retry_timeout=SEARCH_RETRY_TIMEOUT):
    """The flat entries of a typed-in search, retried while no entry names a channel.

    Rows that are not videos - the channel the search is named for, a playlist, a shelf of
    uploads - are dropped here, in the one place a typed-in search's rows are read, and so is
    a video under a second long, which is what a search page hands back for an upload YouTube
    will not serve. Whatever the fifteen rows lose is replaced from further down the same
    search (see `rows_from_further_down`), so the window is not left short by a row that
    cannot play and cannot download.

    Retrying costs a search only in the case worth paying for: an answer where not one
    entry has an owner, which is the answer that strips a channel name and usually a
    duration off every row it produced, and which a second request often answers rich
    instead of sparse. An answer with a channel somewhere is taken as it stands - a row
    without a channel next to nine with one is a track YouTube really does list without
    an owner, and asking again cannot change that.
    """
    best = []
    for attempt in range(1, retries + 2):
        # Only the answer the search is waiting for is waited on patiently. A retry is a
        # bonus, and a retry that is slow or gives up must not cost the results already in
        # hand - which is why the first attempt's errors still fly as they always did.
        try:
            info = run_yt_dlp_json(["--flat-playlist", "-J", f"ytsearch15:{query}"],
                                   timeout=YTDLP_EXTRACT_TIMEOUT if attempt == 1
                                   else retry_timeout)
        except Exception:
            if attempt == 1:
                raise
            break
        entries = search_rows(info)
        if not entries:
            return best or entries
        if any(entry_channel_name(entry) for entry in entries):
            # Rows this file refused are replaced from further down the same search, so one
            # row YouTube will not serve does not leave the window a row short.
            return rows_from_further_down(query, entries, status_cb)
        if len(entries) > len(best):
            best = entries
        if attempt <= retries and status_cb is not None:
            status_cb("Searching... (results with no channels, asking again)")
    return rows_from_further_down(query, best, status_cb)


def stream_cli_args():
    """The yt-dlp arguments that turn one video id into a playable stream URL.

    Shared by the play path and by the prefetch thread so the two never resolve a
    track differently - the prefetched URL is the URL the player would have found.
    """
    cli_args = [
        "-J",
        "--format", "bestaudio/best",
        "--extractor-args", "youtube:player_client=android",
        "--no-playlist",
    ]
    if getattr(sys, 'frozen', False):
        cli_args.extend(["--ffmpeg-location", getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))])
    return cli_args



def resolve_stream_url(vid_id):
    """(stream url, user agent) for a video id, or raises when there is no stream.

    The yt-dlp run is registered while it runs so that picking another track or starting a new
    search can stop it; that raises StreamFetchSupersededError instead of handing back a URL
    nobody is going to play.
    """
    begin_stream_fetch(vid_id)
    try:
        info = run_yt_dlp_json(stream_cli_args() + [f"https://www.youtube.com/watch?v={vid_id}"])
    finally:
        end_stream_fetch()
    url = info.get('url') if info else None
    if not url and info and 'formats' in info:
        for f in reversed(info['formats']):
            if f.get('url') and (f.get('acodec') != 'none' or f.get('vcodec') == 'none'):
                url = f['url']
                break
        if not url and info['formats']:
            url = info['formats'][-1].get('url')
    if not url:
        trace.result("no playable audio stream URL found")
        raise RuntimeError("No playable audio stream URL found")
    headers = info.get('http_headers', {}) if info else {}
    user_agent = headers.get('User-Agent', 'com.google.android.youtube/19.29.37 (Linux; U; Android 11)')
    trace.result("the stream the player gets comes from %s" % (trace.url_host(url) or "an unnamed host"))
    return url, user_agent
