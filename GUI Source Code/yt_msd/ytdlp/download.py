# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.ytdlp.download).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
import os
import re
import time
import subprocess
from yt_msd.subproc import _child_utf8_env, _hidden_window_kwargs
from yt_msd.util import trace
from yt_msd.ytdlp.install import YtDlpMissingError
from yt_msd.ytdlp.runner import find_yt_dlp_executable



# The lines yt-dlp prints when it names the file it ended up with. Which of
# them appear, and whether the path is wrapped in quotes, depends on the
# yt-dlp version and on whether the audio needed converting: the "no conversion
# needed" message is quoted in some releases and bare in others, and newer
# releases dropped its [ExtractAudio] prefix. Every form is matched here and
# the quotes are taken off afterwards. Getting this wrong looked exactly like a
# song being skipped - the file was on disk, the GUI could not match it, and
# the track was quietly queued up again for the next pass.
_YTDLP_FINAL_PATH_PATTERNS = [
    re.compile(r'^\[ExtractAudio\] Destination:\s*(.+)$'),
    re.compile(r'^\[ExtractAudio\] Not converting audio\s+"(.+?)"\s*;'),
    re.compile(r'^Not converting audio\s+"(.+?)"\s*;'),
    re.compile(r'^\[ExtractAudio\] Not converting audio\s+(.+?);\s'),
    re.compile(r'^Not converting audio\s+(.+?);\s'),
    re.compile(r'^\[Merger\] Merging formats into "(.+?)"$'),
    re.compile(r'^\[download\] "(.+?)" has already been downloaded$'),
    re.compile(r'^\[download\] (.+?) has already been downloaded$'),
]

_YTDLP_STAGED_PATH_PATTERNS = [
    re.compile(r'^\[download\] Destination:\s*(.+)$'),
]



def _clean_reported_path(text):
    """Take off the quotes yt-dlp wraps around some of the paths it prints."""
    text = (text or '').strip()
    while len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1].strip()
    return text



def _match_reported_path(line):
    """('final'|'staged', path) for a yt-dlp line naming a file, else (None, '')."""
    # Fast reject: every path pattern anchors at a specific prefix. The vast
    # majority of yt-dlp output lines are progress updates ([download] 25%,
    # [info] ..., [hlsnative] ...) that can never match any pattern. Checking
    # the prefix first avoids trying 8 regexes on every line.
    if not line.startswith(('[ExtractAudio]', '[Merger]', '[download]', 'Not converting')):
        return None, ''
    for pattern in _YTDLP_FINAL_PATH_PATTERNS:
        match = pattern.match(line)
        if match:
            return 'final', _clean_reported_path(match.group(1))
    for pattern in _YTDLP_STAGED_PATH_PATTERNS:
        match = pattern.match(line)
        if match:
            return 'staged', _clean_reported_path(match.group(1))
    return None, ''



def run_yt_dlp_download(args, progress_cb=None, cancelled_cb=None, proc_cb=None):
    """Run a real yt-dlp download and report its progress while it runs.

    Returns the path of the finished file. Returning None does NOT mean the
    download failed - it means yt-dlp finished without naming a file this
    version recognises, and the caller has to look the file up itself.
    Raises when yt-dlp is missing, when the download failed, or when the user
    cancelled - the same contract the old progress hooks had.

    proc_cb: optional callable receiving the Popen object immediately after
    spawn, so the caller can kill the subprocess from outside if cancelled.
    """
    exe = find_yt_dlp_executable()
    if not exe:
        raise YtDlpMissingError("yt-dlp is not installed on this system")
    started = time.monotonic()
    trace.command("yt-dlp", [exe] + list(args))
    # stderr is folded into stdout: two pipes would let ffmpeg's chatter fill a
    # full buffer and stall the download.
    proc = subprocess.Popen([exe] + list(args), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
                            bufsize=1, env=_child_utf8_env(), **_hidden_window_kwargs())
    if proc_cb:
        proc_cb(proc)
    final_path = None
    staged_path = None
    errors = []
    cancelled = False
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        kind, reported = _match_reported_path(line)
        if kind == 'final':
            final_path = reported
        elif kind == 'staged':
            staged_path = reported
        elif line.startswith("[download]"):
            match = re.search(r"\[download\]\s+([0-9.]+%|N/A)", line)
            if match and progress_cb:
                progress_cb(match.group(1))
        elif line.startswith("ERROR:"):
            errors.append(line)
        if trace.enabled():
            # The line has just been sorted for the progress bar; the echo reads that same sort the
            # other way. A bare [download] percentage is the only kind worth thinning - everything
            # else names something that happened, and there are few enough of those.
            trace.child_line("yt-dlp", line, chatter=(kind is None and line.startswith("[download]")))
        if cancelled_cb and cancelled_cb():
            cancelled = True
            proc.kill()
            break
    try:
        proc.stdout.close()
    except Exception:
        pass
    try:
        proc.wait(timeout=30)
    except Exception:
        pass
    if cancelled:
        trace.result("cancelled after %.1fs" % (time.monotonic() - started))
        raise RuntimeError("Download cancelled by user")
    if proc.returncode != 0:
        trace.result("failed: %s" % (errors[-1] if errors else "exit code %d" % proc.returncode))
        raise RuntimeError(errors[-1] if errors else f"yt-dlp exited with code {proc.returncode}")
    # Return whichever path is really there: the converted file when there is
    # one, the plain download when the conversion message was never printed.
    # A half-parsed path is worse than no path at all.
    for candidate in (final_path, staged_path):
        if candidate and os.path.isfile(candidate):
            trace.result("finished: %s (%.1fs)" % (candidate, time.monotonic() - started))
            return candidate
    trace.result("finished without naming a file this version recognises (%.1fs)"
                 % (time.monotonic() - started))
    return final_path or staged_path



# A single track gets a few tries of its own before it is handed back to the
# queue-wide re-check. Retrying one track is far cheaper than re-running the
# whole queue, and the short waits between tries are what let a throttled
# request recover. The queue-wide passes stay on top of this as the safety net.
DOWNLOAD_ITEM_ATTEMPTS = 3


# yt-dlp complaints another request cannot fix, so they are not retried.
_PERMANENT_DOWNLOAD_ERROR_MARKERS = (
    "video unavailable",
    "private video",
    "this video is not available",
    "unsupported url",
    "is not a valid url",
    "requested format is not available",
)



def _is_permanent_download_error(message):
    """True for a failure that a retry could never turn into a download."""
    text = (message or '').lower()
    return any(marker in text for marker in _PERMANENT_DOWNLOAD_ERROR_MARKERS)
