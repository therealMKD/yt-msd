r"""The trace: what this program asked other programs to do, and what they answered.

yt_msd.util.trace prints, on the console, the command line behind every yt-dlp extraction, every
download, every ffmpeg loudness and silence-trim command the renamer builds, every ffprobe
duration, winget installs, the second copy of the program that runs the renamer, the script a
finished batch is handed, and the helper that swaps a new version in. It is what answers "what is
running in the renamer right now" and "which yt-dlp command returned nothing", which is the reason
it was asked for.

Nothing in it runs unless --trace (or -v, or --trace=all) was on the command line, and this file is
mostly about that gate being real, because a trace that is always on is a cost paid by everyone to
benefit nobody. Three things are checked hard:

  * Off means silent. A yt-dlp run, a download and a loudness measurement each produce no output at
    all, and no line is buffered waiting for someone to ask for it.
  * The gate is not allowed to change what the traced call does. Same returned paths, same
    progress-callback counts, same exceptions - with the trace on and with it off.
  * What is printed. A resolved stream URL is a signed link with a kilobyte of tokens in it, and
    trace output gets pasted into issue reports the way yt-msd-crash.log is, so the host is printed
    and the signed part never is. Long ffmpeg -af chains wrap, and wrapping must not drop a filter.

Fake yt-dlp, ffmpeg, ffprobe and winget stand in for the real programs (written into this folder's
copy/trace_fixtures) so the command lines and output shapes are exercised without a network request,
without touching real audio, without needing ffmpeg installed and without installing anything. The
`.pyw` is imported by the importlib recipe from AI Readme section 20 for the source-level checks:
that the flags are gone before Qt sees them, that the renamer copy is asked to trace too, and that
the launcher written by build_gui_exe.py gives a --trace run the console those lines need.

    python "GUI Source Code\GUI Test Suite\probe_trace.py"
"""
import contextlib
import io
import os
import pathlib
import shutil
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))               # .../GUI Source Code/GUI Test Suite
SRC = os.path.join(os.path.dirname(HERE), "yt-msd-gui.pyw")     # the master copy, one folder up
SRC_DIR = os.path.dirname(SRC)                                  # GUI Source Code, which holds yt_msd
REPO = os.path.dirname(SRC_DIR)                                  # repo root, which holds build_gui_exe.py
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
COPY_DIR = os.path.join(HERE, "copy")
os.makedirs(COPY_DIR, exist_ok=True)
FIX = os.path.join(COPY_DIR, "trace_fixtures")
shutil.rmtree(FIX, ignore_errors=True)
os.makedirs(FIX, exist_ok=True)

CHECKS = 0
FAILS = []


def check(label, cond, detail=""):
    global CHECKS
    CHECKS += 1
    print(f"{'ok  ' if cond else 'FAIL'} {label}" + ("" if cond else f"   [{detail}]"))
    if not cond:
        FAILS.append(label)


def write(name, text):
    path = os.path.join(FIX, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


# A .cmd wrapper is what subprocess.Popen can spawn directly, and it passes every argument through
# unchanged - which matters, because the point is that these are the arguments a real yt-dlp or
# ffmpeg would have been given.
HELPER = '@echo off\r\n"%s" "%s" %%*\r\n'

FAKE_YTDLP_PY = write("fake_ytdlp.py", r'''
import json, os, sys

args = sys.argv[1:]
here = os.path.dirname(os.path.abspath(__file__))
signed = ("https://soutub.getvideo.example/stream.mp4/sig"
          "?signature=SECRETSIGNATURE&sparams=expire,ip&ip=203.0.113.9&len=4194304")

if "--make-me-fail" in args:
    sys.stderr.write("WARNING: falling back to the web client\n")
    sys.stderr.write("ERROR: unable to extract: The requested format is not available\n")
    sys.exit(1)
elif "--version" in args:
    print("2026.11.01")
elif "--flat-playlist" in args:
    print(json.dumps({"entries": [
        {"id": "vid1", "title": "Song One", "channel": "Artist A", "duration": 201},
        {"id": "vid2", "title": "Song Two", "duration": 187},
        {"id": "vid3", "title": "Song Three", "uploader": "Artist B", "duration": 240},
    ]}))
elif "-J" in args:
    print(json.dumps({
        "id": "vid1", "title": "Artist A - Song One [Official Audio]",
        "url": signed,
        "formats": [
            {"ext": "webm", "acodec": "opus", "abr": 160, "tbr": 170,
             "filesize": 4194304, "url": signed},
            {"ext": "m4a", "acodec": "mp4a.40.5", "abr": 129, "tbr": 130,
             "filesize": 3612672, "url": signed},
        ],
        "http_headers": {"User-Agent": "com.google.android.youtube/19.29.37"},
    }))
else:
    print("[download] Destination: " + os.path.join(here, "Artist A - Song One.m4a"))
    for step in range(1, 61):
        print("[download] %5.1f%% of  3.44MiB at  1.00MiB/s ETA 00:0%d" % (step * 1.65, 9 - step // 8))
    print("[ExtractAudio] Destination: " + os.path.join(here, "Artist A - Song One.m4a"))
    print("[ExtractAudio] Not converting audio; file is already in target format m4a")
''')

FAKE_FFMPEG_PY = write("fake_ffmpeg.py", r'''
import sys

args = sys.argv[1:]
if "-f" in args and "null" in args:
    sys.stderr.write('[ffmpeg] fake measurement pass\n')
    sys.stderr.write("""
{
    "input_i" : "-14.20",
    "input_tp" : "-2.40",
    "input_lra" : "8.10",
    "input_thresh" : "-25.10",
    "output_i" : "-16.00"
}
""")
elif "-version" in args:
    sys.stdout.write("ffmpeg version fake-6.1 Copyright (c) the FFmpeg developers\n")
else:
    sys.stderr.write("[ffmpeg] fake processing pass finished\n")
''')

FAKE_FFPROBE_PY = write("fake_ffprobe.py", r'''
import json

print(json.dumps({"format": {"duration": "201.4", "bit_rate": "130000"}}))
''')

FAKE_YTDLP = write("fake_ytdlp.cmd", HELPER % (sys.executable, FAKE_YTDLP_PY))
FAKE_FFMPEG = write("fake_ffmpeg.cmd", HELPER % (sys.executable, FAKE_FFMPEG_PY))
FAKE_FFPROBE = write("fake_ffprobe.cmd", HELPER % (sys.executable, FAKE_FFPROBE_PY))

from yt_msd.audio import normalize as normalize_mod
from yt_msd.audio import probe as probe_mod
from yt_msd.util import trace
from yt_msd.ytdlp import download as download_mod
from yt_msd.ytdlp import install as install_mod
from yt_msd.ytdlp import runner as runner_mod

# The fakes stand in for the three programs through the same seams the program uses to find them -
# including the one normalize.py took as its own copy of _ffmpeg_binary at import time.
runner_mod.find_yt_dlp_executable = lambda refresh=False: FAKE_YTDLP
download_mod.find_yt_dlp_executable = lambda refresh=False: FAKE_YTDLP
probe_mod._ffmpeg_binary = lambda: FAKE_FFMPEG
probe_mod._ffprobe_binary = lambda: FAKE_FFPROBE
normalize_mod._ffmpeg_binary = lambda: FAKE_FFMPEG


def run_captured(level, call):
    """Run call() with the gate at level and return (what was printed, what came back).

    An exception is returned rather than raised: several checks are about what a failing run
    prints, and the exception is what a later check looks at.
    """
    before = trace.get_level()
    trace.set_level(level)
    buf = io.StringIO()
    outcome = None
    try:
        with contextlib.redirect_stdout(buf):
            outcome = call()
    except Exception as exc:
        outcome = exc
    finally:
        trace.set_level(before)
    return buf.getvalue(), outcome


FIXED_TRACK = os.path.join(FIX, "Artist A - Song One.m4a")
write("Artist A - Song One.m4a", "not really audio, and nothing reads it\n")

SEARCH_ARGS = ["--flat-playlist", "-J", "ytsearch15:artist a"]
STREAM_ARGS = runner_mod.stream_cli_args() + ["https://www.youtube.com/watch?v=vid1"]
DOWNLOAD_ARGS = ["-f", "bestaudio/best", "--extract-audio", "--audio-format", "m4a",
                 "-o", os.path.join(FIX, "%(title)s.%(ext)s"),
                 "https://www.youtube.com/watch?v=vid1"]

# ------------------------------------------------------------------ the flag itself
ARGV_BEFORE = ["yt-msd-gui.pyw", "--trace", "C:\\Music"]
ARGV_AFTER = trace.parse_flags(ARGV_BEFORE)
check("TR1 --trace turns the gate on and comes out of the arguments it was read from",
      trace.get_level() == trace.WORK_LEVEL and ARGV_AFTER == ["yt-msd-gui.pyw", "C:\\Music"],
      "argv=%r level=%d" % (ARGV_AFTER, trace.get_level()))
check("TR2 -v is the same switch, --trace=all is the second level, --trace=off closes it",
      (trace.parse_flags(["x", "-v"]) == ["x"] and trace.get_level() == trace.WORK_LEVEL
       and trace.parse_flags(["x", "--trace=all"]) == ["x"] and trace.get_level() == trace.ALL_LEVEL
       and trace.parse_flags(["x", "--trace=off"]) == ["x"] and trace.get_level() == 0),
      "level=%d" % trace.get_level())
trace.set_level(0)

# ------------------------------------------------------------------ off means silent
out, info = run_captured(0, lambda: runner_mod.run_yt_dlp_json(SEARCH_ARGS))
check("TR3 an untraced extraction prints not one character", out == "", repr(out))
check("TR4 and it still brings back the same answer",
      isinstance(info, dict) and len(info.get("entries") or []) == 3, repr(info)[:120])

out, measured = run_captured(0, lambda: probe_mod.measure_loudness(FIXED_TRACK))
check("TR5 an untraced loudness measurement prints nothing and still measures",
      out == "" and isinstance(measured, tuple) and measured[0] == -14.20, repr(out))

progress_quiet = []
out, quiet_path = run_captured(0, lambda: download_mod.run_yt_dlp_download(
    DOWNLOAD_ARGS, progress_cb=progress_quiet.append))
check("TR6 an untraced download prints nothing, and thins nothing on the way",
      out == "", repr(out)[:160])

# ------------------------------------------------------------------ what level 1 prints
out, info = run_captured(trace.WORK_LEVEL, lambda: runner_mod.run_yt_dlp_json(SEARCH_ARGS))
check("TR7 a search names the yt-dlp being run and every argument it was given",
      FAKE_YTDLP in out and "--flat-playlist" in out and "ytsearch15:artist a" in out, repr(out))
check("TR8 and what came back, counted in entries and channels instead of URLs",
      any("3 entries" in line and "2 of them naming a channel" in line
          for line in out.splitlines()), repr(out))
check("TR9 a search trace carries no URL at all", "http" not in out, repr(out))
path_lines = [line for line in out.splitlines() if FAKE_YTDLP in line]
check("TR7b an argument containing a space is quoted and never wrapped in half",
      len(path_lines) == 1 and ('"%s"' % FAKE_YTDLP) in path_lines[0], repr(out)[:220])

out, played = run_captured(trace.WORK_LEVEL, lambda: runner_mod.resolve_stream_url("vid1"))
check("TR10 a stream resolution prints the command that produced the answer",
      "-J" in out and "--format bestaudio/best" in out and "watch?v=vid1" in out, repr(out))
check("TR11 it prints which formats were offered, and never the signed link",
      "2 formats" in out and "m4a" in out
      and "SECRETSIGNATURE" not in out and "signature=" not in out and "sparams" not in out,
      repr(out))
check("TR12 the host is printed, because that is the half worth reading",
      "soutub.getvideo.example" in out, repr(out))
check("TR13 the URL the player needs is still handed back whole",
      isinstance(played, tuple) and "signature=SECRETSIGNATURE" in played[0], repr(played)[:120])

out, failed = run_captured(trace.WORK_LEVEL, lambda: runner_mod.run_yt_dlp_json(
    SEARCH_ARGS[:1] + ["-J", "--make-me-fail"]))
check("TR14 a failed extraction prints yt-dlp's own complaint, and still raises it",
      "requested format is not available" in out and isinstance(failed, RuntimeError), repr(out))

# ------------------------------------------------------------------ a download in progress
progress_loud = []
out, path = run_captured(trace.WORK_LEVEL, lambda: download_mod.run_yt_dlp_download(
    DOWNLOAD_ARGS, progress_cb=progress_loud.append))
chatter = [line for line in out.splitlines() if "3.44MiB" in line]
check("TR15 the download command is printed whole, output template included",
      "--audio-format" in out and "watch?v=vid1" in out and "%(title)s.%(ext)s" in out,
      repr(out)[:200])
check("TR16 yt-dlp's sixty progress lines are echoed as chatter, not mirrored",
      1 <= len(chatter) <= 3, "%d progress lines echoed" % len(chatter))
check("TR17 the lines that name what happened are never thinned",
      any("Destination" in line for line in out.splitlines())
      and any("finished" in line for line in out.splitlines()), repr(out)[-240:])
check("TR18 the progress bar is untouched: every percentage still reaches its callback",
      len(progress_loud) == 60, "%d callbacks" % len(progress_loud))
check("TR19 the download still returns the file yt-dlp named", path == FIXED_TRACK, repr(path))
check("TR20 tracing changed nothing about the download it watched",
      quiet_path == path and len(progress_quiet) == len(progress_loud),
      "%r vs %r" % (quiet_path, path))

# ------------------------------------------------------------------ the renamer's own commands
mp3 = os.path.join(FIX, "Artist A - Song One.mp3")
shutil.copyfile(FIXED_TRACK, mp3)
out, outcome = run_captured(trace.WORK_LEVEL, lambda: normalize_mod.normalize_file(
    1, 1, pathlib.Path(mp3)))
joined = " ".join(out.split())
check("TR21 the renamer prints the ffmpeg command it built, silence trim included",
      "[ffmpeg]" in out and "silenceremove=start_periods=1" in joined
      and "areverse" in joined and "apad=pad_dur=" in joined and "volume=" in joined,
      repr(out)[:300])
check("TR22 the codec chosen for this suffix is on the same account",
      "libmp3lame" in out and "320k" in out, repr(out)[-220:])
check("TR23 wrapping a long -af chain drops no filter and no argument",
      "silenceremove=start_periods=1:start_duration=0.5:start_threshold=-60dB:"
      "start_silence=0.5:stop_silence=0.5" in joined, repr(out)[:300])
check("TR24 and the normalizer's own answer is unchanged by being watched",
      isinstance(outcome, tuple) and outcome[0] is True, repr(outcome)[:200])
check("TR25 the per-file ffprobe call inside that pass stays out of level 1",
      "[ffprobe]" not in out, repr(out)[:200])

out, _ = run_captured(trace.WORK_LEVEL, lambda: probe_mod.measure_loudness(FIXED_TRACK))
check("TR26 the loudnorm measurement is level 1 work, and its numbers are printed with it",
      "[ffmpeg]" in out and "loudnorm=I=-16:TP=-1.5:print_format=json" in out
      and "-14.20 LUFS" in out, repr(out)[:300])

out_quiet, dur_quiet = run_captured(trace.WORK_LEVEL, lambda: probe_mod._get_audio_duration(mp3))
out_all, dur_all = run_captured(trace.ALL_LEVEL, lambda: probe_mod._get_audio_duration(mp3))
check("TR27 the per-file duration question is quiet at level 1", out_quiet == "", repr(out_quiet))
check("TR28 --trace=all prints it, and answers it the same either way",
      "[ffprobe]" in out_all and dur_quiet == dur_all == 201.4,
      "%r / %r" % (out_all[:120], dur_all))

# ------------------------------------------------------------------ installing yt-dlp
# winget is the one program here that must never be run by a check, so the lookup that finds it is
# stood in for: one line that prints and exits, and a lookup that finds nothing at all.
FAKE_WINGET = write("fake_winget.cmd", HELPER % (sys.executable, write("fake_winget.py", r'''
import sys

print("Found yt-dlp [yt-dlp.yt-dlp] Version 2026.11.01")
print("Successfully installed")
''')))

install_mod.find_winget_executable = lambda: FAKE_WINGET
out, outcome = run_captured(trace.WORK_LEVEL, lambda: install_mod.run_winget(
    ["install", "--id", "yt-dlp.yt-dlp", "--accept-package-agreements"]))
check("TR28b an update attempt prints the winget command and the last thing winget said",
      "[winget]" in out and "--accept-package-agreements" in out
      and "Successfully installed" in out, repr(out)[:220])
check("TR28c and the answer run_winget hands back is the whole of it",
      isinstance(outcome, tuple) and outcome[0] == 0 and "Successfully installed" in outcome[1],
      repr(outcome)[:160])
install_mod.find_winget_executable = lambda: None
out, outcome = run_captured(trace.WORK_LEVEL, lambda: install_mod.run_winget(["install"]))
check("TR28d a machine with no winget says so on the trace as well as in the message",
      "no winget" in out and outcome[2] != "", repr(out)[:160])

# ------------------------------------------------------------------ where the lines can go
raised = None
trace.set_level(trace.WORK_LEVEL)
try:
    with contextlib.redirect_stdout(None):        # a windowed exe with no --console
        trace.command("yt-dlp", ["yt-dlp", "-J", "https://www.youtube.com/watch?v=vid1"])
        trace.result("this one has nowhere to go")
except Exception as exc:
    raised = exc
finally:
    trace.set_level(0)
check("TR29 with no console the line is dropped, and nothing is kept for later",
      raised is None, repr(raised))


class _StrictConsole(io.StringIO):
    """A console that refuses the box-drawing characters and the tick the renamer draws."""

    def write(self, text):
        text.encode("ascii")
        return super().write(text)


strict = _StrictConsole()
trace.set_level(trace.WORK_LEVEL)
try:
    with contextlib.redirect_stdout(strict):
        trace.note("├─ silence trim ✓ on")
except Exception as exc:
    strict.write("RAISED %r" % exc)
finally:
    trace.set_level(0)
check("TR30 a console that cannot take those characters keeps the line and loses the character",
      "silence trim" in strict.getvalue() and "RAISED" not in strict.getvalue(),
      repr(strict.getvalue()))


def _eight_threads():
    threads = [threading.Thread(target=trace.command,
                                args=("worker", ["--thread-%d" % i, "one", "two", "three"]))
               for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


out, _ = run_captured(trace.WORK_LEVEL, _eight_threads)
lines = [line for line in out.splitlines() if line.strip()]
whole = [line for line in lines if line.count("[worker]") == 1 and line.rstrip().endswith("three")]
check("TR31 eight background threads print eight whole commands, not one interleaved mess",
      len(whole) == 8 and len(lines) >= 8, "%d whole lines from %d" % (len(whole), len(lines)))

# ------------------------------------------------------------------ the flag reaching every start
pyw = open(SRC, encoding="utf-8").read()
entry_start = pyw.rindex('if __name__ == "__main__":')
flag_read = pyw.index("trace.parse_flags(sys.argv)")
check("TR32 the flags are read inside the entry block, so importing the program leaves the gate alone",
      flag_read > entry_start and pyw.count("trace.parse_flags(sys.argv)") == 1,
      "entry at %d, flag read at %d" % (entry_start, flag_read))
check("TR33 and they are gone before Qt is handed sys.argv",
      flag_read < pyw.index("QApplication(sys.argv)"),
      "flag at %d, QApplication at %d" % (flag_read, pyw.index("QApplication(sys.argv)")))

launch = pyw.split("def run_mp3_renamer")[1].split("def _console_python")[0]
check("TR34 the renamer copy the window starts is asked to trace the same level",
      'args.append("--trace"' in launch and "trace.enabled()" in launch
      and "--trace=all" in launch, launch[:200])
check("TR35 and the command that starts that copy is itself on the account",
      'trace.command("renamer", args)' in launch, launch[:200])

renamer_src = open(os.path.join(SRC_DIR, "yt_msd", "audio", "renamer.py"), encoding="utf-8").read()
check("TR36 the renamer strips the flags before argparse could read one as the folder",
      "trace.parse_flags(sys.argv)" in renamer_src
      and renamer_src.index("trace.parse_flags(sys.argv)") < renamer_src.index("argparse.ArgumentParser"),
      "")

launcher_src = open(os.path.join(REPO, "build_gui_exe.py"), encoding="utf-8").read()
check("TR37 the launcher build_gui_exe.py writes gives a --trace run the console it needs",
      '"--console", "--trace", "-v"' in launcher_src
      and 'arg.startswith("--trace=")' in launcher_src, "")

trace_src = open(os.path.join(SRC_DIR, "yt_msd", "util", "trace.py"), encoding="utf-8").read()
check("TR38 the trace opens no file, holds nothing back and touches no Qt object",
      "open(" not in trace_src and "PySide6" not in trace_src
      and "QApplication" not in trace_src and "deque" not in trace_src, "")

print()
print("%d/%d checks passed" % (CHECKS - len(FAILS), CHECKS))
if FAILS:
    print("FAILED:")
    for label in FAILS:
        print("  " + label)
    sys.exit(1)
