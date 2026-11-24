# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.audio.probe).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
import os
import re
import sys
import json
import subprocess
from yt_msd.audio.tuning import TARGET_LUFS, TRUE_PEAK
from yt_msd.subproc import _hidden_window_kwargs
from yt_msd.util import trace


def check_ffmpeg_available():
    try:
        trace.command("ffmpeg", [_ffmpeg_binary(), "-version"])
        subprocess.run([_ffmpeg_binary(), "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, check=True, **_hidden_window_kwargs())
        return True
    except Exception:
        trace.result("no ffmpeg on this system, so no loudness or silence-trim pass can run")
        return False



def measure_loudness(filepath):
    command = [
        _ffmpeg_binary(),
        "-nostdin",
        "-y",
        "-i", str(filepath),
        "-af", f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:print_format=json",
        "-f", "null",
        "-"
    ]
    trace.command("ffmpeg", command)
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='ignore',
            **_hidden_window_kwargs()
        )
        if result.returncode != 0:
            trace.result("ffmpeg exited with code %d: %s"
                         % (result.returncode, trace.tail(result.stderr)))
            return None, None, f"FFmpeg exited with code {result.returncode}"
            
        stderr_output = result.stderr
        json_match = re.search(r'\{\s*"input_i".*?\}', stderr_output, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            input_i = float(data.get("input_i", TARGET_LUFS))
            input_tp = float(data.get("input_tp", TRUE_PEAK))
            trace.result("measured %+.2f LUFS, true peak %+.2f dB" % (input_i, input_tp))
            return input_i, input_tp, None
        else:
            trace.result("no loudnorm JSON block came back")
            return None, None, "Could not find loudnorm JSON block in FFmpeg output"
    except Exception as e:
        trace.result("loudness measurement failed: %s" % e)
        return None, None, str(e)


def _ffprobe_binary():
    """The ffprobe to run: the one bundled with the frozen exe when this program is
    packaged, otherwise whatever is on PATH."""
    if getattr(sys, 'frozen', False):
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        bundled = os.path.join(base_dir, 'ffprobe.exe')
        if os.path.exists(bundled):
            return bundled
    return 'ffprobe'



def _ffmpeg_binary():
    """The ffmpeg to run: the one bundled with the frozen exe when this program is
    packaged, otherwise whatever is on PATH. yt-dlp is already pointed at that copy
    with --ffmpeg-location, but the loudness and silence-trim passes call ffmpeg
    directly and had no equivalent, so a packaged build that carries ffmpeg.exe and
    does not have it on PATH reported ffmpeg as unavailable and never normalized or
    trimmed anything."""
    if getattr(sys, 'frozen', False):
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        bundled = os.path.join(base_dir, 'ffmpeg.exe')
        if os.path.exists(bundled):
            return bundled
    return 'ffmpeg'



def _probe_format_block(filepath):
    """Run ffprobe over one file and return the "format" block of its JSON output,
    or None when ffprobe could not read it.

    '-nostdin' is deliberately not used: this build of ffprobe treats it as an option
    that takes a value, so every call that had it failed with "Failed to set value
    '-v' for option 'nostdin'" and no duration was ever returned. Closing stdin with
    DEVNULL, as this does, is what that switch was for."""
    try:
        cmd = [_ffprobe_binary(), "-v", "quiet", "-print_format", "json", "-show_format", str(filepath)]
        # Level 2 (--trace=all) only. This is called once per local file while a library folder is
        # listed (yt_msd.audio.localmeta), so plain --trace would spend a thousand lines answering
        # a question nobody asked. --trace=all is for when that question is the one in trouble.
        if trace.tracing_all():
            trace.command("ffprobe", cmd)
        result = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding='utf-8', errors='ignore',
                                **_hidden_window_kwargs())
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            return data.get('format') or None
    except Exception:
        pass
    return None



def _get_audio_duration(filepath):
    """Return duration in seconds via ffprobe, or None on failure."""
    fmt = _probe_format_block(filepath)
    if not fmt:
        return None
    try:
        return float(fmt.get('duration'))
    except (TypeError, ValueError):
        return None
