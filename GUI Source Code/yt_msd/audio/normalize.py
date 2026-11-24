# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.audio.normalize).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
import os
import tempfile
import subprocess
from concurrent.futures.thread import ThreadPoolExecutor
from concurrent.futures import as_completed
from yt_msd.audio.probe import _ffmpeg_binary, _get_audio_duration, check_ffmpeg_available, measure_loudness
from yt_msd.audio.tags import read_metadata_tags, write_metadata_tags
from yt_msd.audio.tuning import BITRATE, SILENCE_DURATION, SILENCE_KEEP, SILENCE_THRESHOLD, TARGET_LUFS, TRUE_PEAK, TUNING
from yt_msd.constants import TAGGABLE_EXTENSIONS
from yt_msd.subproc import _hidden_window_kwargs
from yt_msd.util import trace
from yt_msd.util.console import Colors, _safe_print


def _silence_trim_filters():
    """
    The built-in silence-trim filters, exactly as they have always been built:
    one pass for the front of the track, then the same filter over a reversed
    stream so the trailing silence is trimmed too, then reversed back.
    """
    single = (
        f"silenceremove=start_periods=1:start_duration={SILENCE_DURATION}:"
        f"start_threshold={SILENCE_THRESHOLD}:start_silence={SILENCE_KEEP}:stop_silence={SILENCE_KEEP}"
    )
    return f"{single},areverse,{single},areverse"



def build_af_chain(loudnorm_filter=None, include_silence_trim=None, include_pad=True):
    """
    Assemble the ffmpeg -af chain from its three independent parts:

      1. silence trim    - _silence_trim_filters(), gated by the TUNING.silence_trim setting
      2. loudnorm        - the built-in whole-track gain, or the loudnorm/EQ override
      3. end-of-file pad - apad, gated by TUNING.silence_pad_dur

    A loudnorm override only replaces part 2. Silence trimming is never overridden
    by it, and turning silence trimming off never touches the loudnorm part.
    """
    trim_on = TUNING.silence_trim if include_silence_trim is None else include_silence_trim
    parts = []
    if trim_on:
        parts.append(_silence_trim_filters())
    if loudnorm_filter:
        parts.append(loudnorm_filter)
    if include_pad and TUNING.silence_pad_dur > 0:
        parts.append(f"apad=pad_dur={TUNING.silence_pad_dur}")
    return ",".join(parts)



def normalize_file(index, total, filepath, custom_norm_cmd=None):
    suffix = filepath.suffix.lower()
    artist, title = read_metadata_tags(filepath)

    # Measure original duration only when silence-trim reporting needs it (saves a
    # ffprobe subprocess per file when trimming is off).
    orig_duration = _get_audio_duration(filepath) if TUNING.silence_trim else None
    
    input_i, input_tp, err = measure_loudness(filepath)
    if err:
        return False, filepath.name, f"Loudness measurement failed: {err}"
        
    target_lufs = float(TARGET_LUFS)
    true_peak_limit = float(TRUE_PEAK)
    
    gain = target_lufs - input_i
    max_gain = true_peak_limit - input_tp
    final_gain = min(gain, max_gain)
    
    limit_str = " (Peak Limited)" if final_gain < gain else ""
    _effective_norm_cmd = (custom_norm_cmd or TUNING.custom_norm_cmd or "").strip()
    gain_line = (
        f"  └─ Loudnorm/EQ override: {_effective_norm_cmd}" if _effective_norm_cmd
        else f"  └─ Applying Whole-Track Gain: {final_gain:+.2f} dB{limit_str} (Target: {target_lufs} LUFS)"
    )
    _safe_print(
        f"[{index}/{total}] {Colors.CYAN}Processing:{Colors.END} {filepath.name}...\n"
        f"  ├─ Measured: {input_i:+.2f} LUFS | True Peak: {input_tp:+.2f} dB\n"
        f"{gain_line}"
    )
    
    try:
        temp_fd, temp_path = tempfile.mkstemp(suffix=suffix)
        os.close(temp_fd)
    except Exception as e:
        return False, filepath.name, f"Failed to create temp file: {e}"
        
    # The three parts of the chain are independent: silence trimming, the loudnorm
    # filter and the end-of-file pad. A loudnorm override replaces ONLY the loudnorm
    # filter and can never replace the silence trimming command.
    loudnorm_filter = _effective_norm_cmd or f"volume={final_gain:.2f}dB"
    af_chain = build_af_chain(loudnorm_filter)

    command = [_ffmpeg_binary(), "-nostdin", "-y", "-i", str(filepath), "-af", af_chain]
    
    if suffix == ".mp3":
        command += ["-codec:a", "libmp3lame", "-b:a", BITRATE]
    elif suffix == ".m4a":
        command += ["-codec:a", "aac", "-b:a", BITRATE]
    else:
        command += ["-b:a", BITRATE]
        
    command += ["-map_metadata", "0"]
    if suffix == ".m4a":
        command += ["-movflags", "+faststart"]
        
    command.append(temp_path)
    # The whole ffmpeg command, filters included. This is the line that answers "what did it
    # actually do to my file" - the -af chain is built from four settings the user changed, and
    # until now the only way to see the result was to read build_af_chain() and guess.
    trace.command("ffmpeg", command)
    
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            **_hidden_window_kwargs()
        )
    except Exception as e:
        try: os.remove(temp_path)
        except: pass
        trace.result("could not run ffmpeg: %s" % e)
        return False, filepath.name, f"FFmpeg execution failed: {e}"
        
    if result.returncode != 0:
        try: os.remove(temp_path)
        except: pass
        trace.result("ffmpeg exited with code %d: %s"
                     % (result.returncode, trace.tail(result.stderr)))
        return False, filepath.name, result.stderr
        
    try:
        os.replace(temp_path, str(filepath))
    except Exception as e:
        return False, filepath.name, f"Failed to replace original file with temp: {e}"
    
    # Report silence removal stats (only meaningful when the trim filters ran)
    new_duration = _get_audio_duration(filepath) if TUNING.silence_trim else None
    if TUNING.silence_trim and orig_duration is not None and new_duration is not None:
        total_removed = orig_duration - new_duration
        pad_added = TUNING.silence_pad_dur if TUNING.silence_pad_dur > 0 else 0.0
        net_removed = total_removed + pad_added  # silence removed before pad was added
        front_est = net_removed / 2.0
        back_est = net_removed / 2.0
        _safe_print(
            f"  {Colors.DIM}├─ Original duration: {orig_duration:.2f}s  →  New: {new_duration:.2f}s{Colors.END}\n"
            f"  {Colors.DIM}└─ Silence removed: ~{front_est:.2f}s front, ~{back_est:.2f}s back (total: {net_removed:.2f}s){Colors.END}"
        )
        
    if (artist or title):
        write_metadata_tags(filepath, artist, title)
        
    return True, filepath.name, None



def run_loudness_normalization(folder_path, skip_files=None):
    print(f"\n{Colors.CYAN}{Colors.BOLD}========================================{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}=== TWO-PASS VOLUME ADJUSTMENT PASS ===={Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}========================================{Colors.END}\n")
    
    if not check_ffmpeg_available():
        print(f"{Colors.YELLOW}[!] FFmpeg was not found in your system's PATH.{Colors.END}")
        print(f"{Colors.DIM}    Loudness normalization requires FFmpeg to process files.{Colors.END}")
        print(f"{Colors.DIM}    Skipping volume adjustment pass.{Colors.END}\n")
        return 0, 0
        
    extensions = TAGGABLE_EXTENSIONS
    files = sorted([f for f in folder_path.iterdir() if f.is_file() and f.suffix.lower() in extensions])

    # Filter out files that were already tagged before the renaming pass started
    if skip_files:
        pre_skip_count = len([f for f in files if f in skip_files])
        files = [f for f in files if f not in skip_files]
        if pre_skip_count:
            print(f"{Colors.DIM}Skipping {pre_skip_count} already-tagged file(s) from normalization.{Colors.END}")

    if not files:
        print(f"{Colors.YELLOW}No MP3 or M4A files found to adjust.{Colors.END}\n")
        return 0, 0
        
    print(f"{Colors.GREEN}Starting static volume adjustment on {len(files)} files with {TUNING.max_workers} worker threads...{Colors.END}")
    print(f"{Colors.DIM}Settings: Target Loudness={TARGET_LUFS} LUFS | Max Peak={TRUE_PEAK} dB | Output Bitrate={BITRATE}{Colors.END}")
    print(f"{Colors.DIM}Silence trim: {'ON' if TUNING.silence_trim else 'OFF'} | End pad: {TUNING.silence_pad_dur}s | Loudnorm: {TUNING.custom_norm_cmd or 'built-in whole-track gain'}{Colors.END}\n")
    
    completed = 0
    failed = 0
    
    with ThreadPoolExecutor(max_workers=TUNING.max_workers) as executor:
        futures = []
        for idx, file in enumerate(files, 1):
            futures.append(executor.submit(normalize_file, idx, len(files), file))
            
        for future in as_completed(futures):
            success, filename, error = future.result()
            if success:
                completed += 1
                _safe_print(f"  {Colors.GREEN}✔ Adjusted Volume:{Colors.END} {filename}\n")
            else:
                failed += 1
                _safe_print(f"\n  {Colors.RED}✘ Failed to adjust volume {filename}:{Colors.END}")
                _safe_print(f"{Colors.DIM}{error}{Colors.END}\n")
                
    print(f"\n{Colors.CYAN}{Colors.BOLD}Volume Adjustment Complete!{Colors.END}")
    print(f"  {Colors.GREEN}Success: {completed}{Colors.END} | {Colors.RED}Failed: {failed}{Colors.END}\n")
    return completed, failed
