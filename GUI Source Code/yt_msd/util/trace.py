# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.util.trace).
#
# A running account, on the console, of what this program asks other programs to do: the yt-dlp
# command lines behind a search, a stream URL and a download; the ffmpeg commands behind the
# renamer's loudness pass and its silence trim; winget installing yt-dlp; the second copy of this
# program that runs the renamer; the script a finished batch is handed; the helper that swaps a
# new version in. Added for 3.5 rather than extracted from the .pyw - there was nothing like it
# in the program before.
#
# Written for the two questions that are hardest to answer from a bug report. "The search returned
# nothing" is easy to pass to someone else once the exact yt-dlp command that returned nothing is
# on screen. The renamer is the harder one: it builds an ffmpeg -af chain out of four settings a
# user changes (yt_msd.audio.tuning), and until now the only way to know which chain was built for
# a given file was to read the code while knowing what that user had set.
#
# OFF UNLESS ASKED FOR, WHICH IS WHAT MAKES IT FREE
# -----------------------------------------------------------------------------------------
# Nothing here does anything unless --trace (or -v) was on the command line. Every call site asks
# for a line and this file answers with one comparison and a return. A whole session is one yt-dlp
# run per search, one per track played and one per file downloaded, so the cost when tracing is off
# is a few dozen comparisons. The alternative - buffering lines in case someone wants them - pays
# in copying and memory on every run to serve nobody.
#
# When it is on, the cost is the console rather than the formatting: Windows console writes are
# syscalls, and a big download makes yt-dlp print a progress line every few milliseconds - the one
# volume in this program that could measurably slow the thing it is watching. So the echo is not a
# mirror. Lines that name what happened (a destination, a conversion, a merger, an error) always
# pass; progress chatter is thinned to one line per PROGRESS_MIN_SECONDS. Nothing is accumulated
# and dumped at the end.
#
# TWO LEVELS
#   --trace / -v    the programs that do work: yt-dlp, ffmpeg, winget, the renamer copy, a
#                   post-download script, the update swap helper.
#   --trace=all     also the programs that only ask a question per file. ffprobe is called once per
#                   local file while a library folder is listed (yt_msd.audio.localmeta), so a
#                   folder of a few thousand songs is a few thousand lines answering nobody's
#                   question.
#
# WHAT NEVER APPEARS
#   A resolved stream URL. It is a signed googlevideo link - a kilobyte of tokens with an expiry on
#   it - and trace output is something people paste into an issue report the way they paste
#   yt-msd-crash.log today. url_host() turns one into "https://soutub...googlevideo.com" and
#   nothing else from it is ever printed.
#
# WHERE THE LINES GO
#   sys.stdout, when there is a usable one. Run from a terminal the .pyw has one. The exe is
#   windowed and has none, which is what --console is for, and --trace now asks for the same
#   console (see attach_console in the launcher build_gui_exe.py writes). With no console the line
#   is dropped: this does not open a window, and it writes no file - a log written on every run is
#   exactly the performance hit this file exists to avoid.
# -----------------------------------------------------------------------------------------

import re
import sys
import threading
import time

WORK_LEVEL = 1
ALL_LEVEL = 2

# The gate, in a one-item list so a worker thread reads the value the entry block set and a probe
# can put it back exactly as it found it.
_level = [0]

_lock = threading.Lock()        # background threads ask for lines at the same moment
_progress_at = [0.0]            # when progress chatter was last echoed

PROGRESS_MIN_SECONDS = 0.4      # how often progress chatter may be echoed
WRAP_AT = 100                   # command lines wrap here, continued under the first argument


def parse_flags(argv):
    """Read --trace / -v / --trace=all out of a command line and set the level.

    Returns argv without those flags, because Qt is handed the arguments it recognises and so is
    the renamer's argparse. Called from the entry block and from the renamer's own entry, which
    together are every way a copy of this program starts.
    """
    level = _level[0]
    kept = []
    for arg in list(argv):
        if arg in ("--trace", "-v"):
            level = max(level, WORK_LEVEL)
        elif arg.startswith("--trace="):
            wanted = arg.split("=", 1)[1].strip().lower()
            level = {"off": 0, "work": WORK_LEVEL,
                     "all": ALL_LEVEL}.get(wanted, max(level, WORK_LEVEL))
        else:
            kept.append(arg)
    _level[0] = level
    return kept


def get_level():
    return _level[0]


def set_level(value):
    """Set the level directly. The suite uses this to restore the gate after changing it."""
    _level[0] = int(value)


def enabled():
    """Worth printing? A call site that builds a string before asking this has already paid."""
    return _level[0] >= WORK_LEVEL


def tracing_all():
    """True for --trace=all: the per-file questions are printed too."""
    return _level[0] >= ALL_LEVEL


def _sink():
    stream = getattr(sys, "stdout", None)
    if stream is None or not hasattr(stream, "write"):
        return None             # windowed exe, no --console: the line is dropped, not queued
    return stream


def _write(text):
    stream = _sink()
    if stream is None:
        return
    try:
        stream.write(text + "\n")
        if hasattr(stream, "flush"):
            stream.flush()
    except UnicodeEncodeError:
        # A console that is not in UTF-8. Losing a box-drawing character beats losing the line.
        try:
            stream.write(text.encode("ascii", "replace").decode("ascii") + "\n")
            if hasattr(stream, "flush"):
                stream.flush()
        except Exception:
            pass
    except Exception:
        pass


def _quoted(arg):
    """One argument as it would have to be written in a terminal to mean the same thing."""
    text = str(arg)
    if not text:
        return '""'
    return '"%s"' % text if any(c.isspace() for c in text) else text


def _emit(prefix, tokens):
    """prefix + tokens, wrapped at token boundaries.

    Wrapping happens between whole arguments: an ffmpeg -af chain or a path containing spaces is
    one token and is never broken in half, and no token is dropped. The wrapping is presentation,
    and the line is what it looks like to run it.
    """
    indent = " " * (len(prefix) + 1)
    line = prefix
    for token in tokens:
        if len(line) > len(prefix) and len(line) + 1 + len(token) > WRAP_AT:
            _write(line)
            line = indent + token
        else:
            line = line + " " + token
    _write(line)


def command(label, argv):
    """The command about to be run, with the full path of the program being run."""
    if _level[0] < WORK_LEVEL:
        return
    with _lock:
        _emit("  [%s]" % label, [_quoted(a) for a in argv])


def result(text):
    """What that command brought back."""
    if _level[0] < WORK_LEVEL:
        return
    with _lock:
        _write("      -> %s" % text)


def note(text):
    """A line that is not about one command - which yt-dlp was found, say."""
    if _level[0] < WORK_LEVEL:
        return
    with _lock:
        _write("  %s" % text)


def child_line(label, line, chatter=False):
    """One line a helper program printed. chatter=True is the thinning-eligible kind."""
    if _level[0] < WORK_LEVEL:
        return
    line = (line or "").strip()
    if not line:
        return
    if chatter:
        now = time.monotonic()
        if now - _progress_at[0] < PROGRESS_MIN_SECONDS:
            return
        _progress_at[0] = now
    with _lock:
        _write("      | %s" % line)


def url_host(url):
    """scheme://host of a URL and nothing else from it - see WHAT NEVER APPEARS above."""
    if not isinstance(url, str):
        return ""
    found = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://[^/?#]+", url)
    return found.group(0) if found else ""


def tail(text, limit=3):
    """The last few non-empty lines of a program's output, which is where its complaint lives."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return " | ".join(lines[-limit:]) if lines else ""
