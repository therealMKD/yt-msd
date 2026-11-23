"""Where the time at a track change actually goes.

Not part of the regression harness - this one deliberately touches the network,
because the question being asked is "how long does each stage of a changeover
take on a real machine?". Nothing here writes to the repo or to the music
library; the only file involved is the yt-msd source, imported read-only.

Stages measured, in the order the play path runs them:

  1. resolve_stream_url()  - the yt-dlp subprocess call. This is the ONLY stage
     the prefetch can move off the changeover, so its cost is the ceiling on
     how much faster prefetching can possibly make anything.
  2. media_new() + play() + libVLC opening the URL until the state turns
     Playing. Prefetch does not touch this at all.
  3. vlc_player.get_length() once Playing - the trigger in update_player_ui()
     needs total_ms > 0, so if a stream reports no length the prefetch never
     fires and there is no speed-up to be seen.
"""
import importlib.machinery
import importlib.util
import os
import statistics
import sys
import time

GUI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # GUI Source Code, one folder up
SOURCE = os.path.join(GUI_DIR, "yt-msd-gui.pyw")

# Set YTMSD_IDS to a comma separated list to keep a single run short.
VIDEO_IDS = [v for v in (os.environ.get("YTMSD_IDS") or "jNQXAC9IVRw").split(",") if v.strip()]
CLIENTS = [c for c in (os.environ.get("YTMSD_CLIENTS") or "android").split("|") if c.strip()]
SKIP_VLC = bool(os.environ.get("YTMSD_SKIP_VLC"))
VLC_OPEN_TIMEOUT_MS = 20000

checks = []


def check(label, ok, detail=""):
    checks.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" - {detail}" if detail else ""))


def load_source():
    loader = importlib.machinery.SourceFileLoader("yt_msd_gui_under_test", SOURCE)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def timed(fn):
    t0 = time.perf_counter()
    value = fn()
    return (time.perf_counter() - t0) * 1000.0, value


def main():
    old_argv0 = sys.argv[0]
    sys.argv[0] = SOURCE          # so the module finds icon.ico beside the source
    mod = load_source()
    sys.argv[0] = old_argv0

    exe = mod.find_yt_dlp_executable()
    print(f"yt-dlp executable: {exe}")
    if not exe:
        check("yt-dlp is locatable", False)
        return 1
    t, ver = timed(lambda: mod.get_yt_dlp_version(exe))
    print(f"yt-dlp version: {ver} (report took {t:.0f} ms)")

    # ---- stage 1: what the prefetch removes ---------------------------------
    resolved = {}
    for vid in VIDEO_IDS:
        for client in CLIENTS:
            args = ["-J", "--format", "bestaudio/best",
                    "--extractor-args", f"youtube:player_client={client}",
                    "--no-playlist", f"https://www.youtube.com/watch?v={vid}"]
            try:
                ms, info = timed(lambda args=args: mod.run_yt_dlp_json(args))
            except Exception as exc:
                check(f"resolve {vid} via {client}", False, str(exc)[:160])
                continue
            url = info.get('url') or ""
            resolved.setdefault(vid, (url, info.get('http_headers', {})))
            print(f"resolve {vid} client={client}: {ms:.0f} ms "
                  f"(format={info.get('format_id')} ext={info.get('ext')} "
                  f"url_len={len(url)})")

    for vid in VIDEO_IDS:
        try:
            ms, pair = timed(lambda vid=vid: mod.resolve_stream_url(vid))
            resolved.setdefault(vid, (pair[0], {}))
            print(f"resolve_stream_url({vid}) as the play path calls it: {ms:.0f} ms")
        except Exception as exc:
            check(f"resolve_stream_url {vid}", False, str(exc)[:160])

    if not any(resolved.values()):
        check("at least one stream resolved", False, "no stream URL came back; VLC stage skipped")
        summarize()
        return 0

    # ---- stage 2: what the prefetch cannot remove ---------------------------
    if SKIP_VLC:
        print("libVLC stage skipped (YTMSD_SKIP_VLC set)")
        summarize()
        return 0
    try:
        import vlc
    except Exception as exc:
        check("python-vlc importable", False, str(exc))
        summarize()
        return 0

    instance = vlc.Instance("--quiet", "--no-video")
    for vid, (url, headers) in resolved.items():
        if not url:
            continue
        player = instance.media_player_new()
        media = instance.media_new(url)
        ua = (headers.get("User-Agent")
              or "com.google.android.youtube/19.29.37 (Linux; U; Android 11)")
        media.add_option(f":http-user-agent={ua}")
        player.set_media(media)

        t0 = time.perf_counter()
        player.play()
        opened_ms = None
        length_ms = 0
        while (time.perf_counter() - t0) * 1000.0 < VLC_OPEN_TIMEOUT_MS:
            if player.get_state() == vlc.State.Playing:
                opened_ms = (time.perf_counter() - t0) * 1000.0
                length_ms = player.get_length()
                break
            time.sleep(0.02)
        position = player.get_time()
        player.stop()
        player.release()

        print(f"libVLC open {vid}: {opened_ms} ms to Playing, "
              f"get_length()={length_ms} ms, get_time()={position} ms")
        check(f"libVLC reached Playing for {vid}", opened_ms is not None)
        check(f"get_length() is known for {vid} (needed by the 30 s trigger)",
              bool(length_ms and length_ms > 0), f"length_ms={length_ms}")

    summarize()
    return 0


def summarize():
    print(f"\nchecks: {sum(checks)}/{len(checks)} passed")


if __name__ == "__main__":
    raise SystemExit(main())
