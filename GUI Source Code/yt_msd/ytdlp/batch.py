# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.ytdlp.batch).
#
# A mixin, not a standalone module: MainApp inherits from this class, so what is written here
# are ordinary methods and `self` is the MainApp instance. They were lifted out of the class
# body in wave 6 with their text unchanged - only the imports needed to reach the rest of the
# program were added, and the inside of a multi-line string kept the indentation it was written
# with, because changing it would change what the program shows rather than where it is kept.

import os
import sys
import threading
import shlex
import time
from yt_msd.audio.tags import _add_placeholder_tag, _remove_placeholder_tag
from yt_msd.constants import TAGGABLE_EXTENSIONS
from yt_msd.util import trace
from yt_msd.util.text import _title_match_key, _title_matches_filename, channel_prefixed_stem
from yt_msd.ytdlp.download import DOWNLOAD_ITEM_ATTEMPTS, _is_permanent_download_error, run_yt_dlp_download
from yt_msd.ytdlp.runner import entry_channel_name

class BatchDownloadMixin:
    def start_batch_download(self):
        if self.is_downloading: return
        pending = [q for q in self.queue_items if q['status'] == "Pending"]
        if not pending:
            # Said out loud on purpose: a press that changed nothing used to look exactly like
            # a download that was taking its time to start.
            self._on_status_update("Nothing in the queue to download.", False, "#FF8C00")
            return

        self.is_downloading = True
        self.cancel_download = False
        self._batch_total_count = len(pending)
        self.dl_btn.setEnabled(False)
        self.dl_btn.setText("Downloading...")
        self.cancel_btn.setText("Cancel")
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setVisible(True)
        # Everything read from a widget is read here, on the GUI thread. Qt
        # objects belong to the thread that created them, and reading the
        # settings once also stops a mid-batch change of format, bitrate or
        # folder from splitting one queue across two different targets.
        folder = self.path_combo.currentText()
        target_format = self.format_combo.currentText().lower()
        audio_quality = str(self.bitrate_combo.currentText())
        ffmpeg_location = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable)) if getattr(sys, 'frozen', False) else None
        extra_args = shlex.split(self.custom_args) if (getattr(self, 'use_custom_args', False) and getattr(self, 'custom_args', '')) else []

        def bg_download():
            try:
                _run_batch()
            except Exception as e:
                # Nothing here may end a batch without a final status line:
                # that line is what re-enables the Download button, so one
                # unhandled error used to leave the queue stuck on
                # "Downloading..." with the rest of the list never attempted.
                print(f"Batch download error: {e}")
                self.status_signal.emit(f"Batch complete (stopped early: {e}).", False, "#E31E24")

        def _run_batch():
            from concurrent.futures.thread import ThreadPoolExecutor  # see the note at the top

            with self.active_downloads_lock:
                self.active_downloads.clear()

            threads_count = max(1, int(getattr(self, 'download_threads', 3)))
            self._dl_finished_count = 0
            downloaded_filepaths = []
            downloaded_lock = threading.Lock()
            # id(queue item) -> the file that item produced. Kept out of the
            # queue dicts so the verification pass can check each track on its
            # own instead of guessing from counts.
            produced_files = {}
            # Two queue entries can be different videos that share a title, and
            # yt-dlp names its output after the title. Left alone, two threads
            # write the same .part file at the same moment and one of them
            # fails or writes garbage - which is why the skipping used to get
            # worse with every extra thread. Same-title tracks are downloaded
            # one at a time instead.
            title_locks = {}
            title_locks_guard = threading.Lock()
            start_slot_guard = threading.Lock()
            start_slot = [0]
            # Lightweight counter for the progress prefix. Incremented once per
            # download completion (inside download_single) instead of rescanning
            # all queue_items on every yt-dlp progress line.
            finished_counter = [0]
            finished_counter_guard = threading.Lock()

            def title_lock_for(title):
                key = _title_match_key(title) or title
                with title_locks_guard:
                    lock = title_locks.get(key)
                    if lock is None:
                        lock = threading.Lock()
                        title_locks[key] = lock
                    return lock

            def reset_start_slots():
                with start_slot_guard:
                    start_slot[0] = 0

            def take_start_slot():
                with start_slot_guard:
                    slot = start_slot[0]
                    start_slot[0] += 1
                return slot

            def repaint(q):
                """Repaint one queue row, looking up where that item is now.

                The index a worker was handed goes stale the moment the queue is
                reordered or something is taken out of it, and painting the wrong
                row is part of how a finished track kept showing as pending.
                """
                for i, item in enumerate(getattr(self, 'queue_items', [])):
                    if item is q:
                        self.queue_status_changed_signal.emit(i)
                        return

            def find_downloaded_file(title, not_before=0.0):
                """Find the file a successful yt-dlp run left behind, by its title."""
                try:
                    entries = list(os.scandir(folder))
                except OSError:
                    return None
                best = None
                for entry in entries:
                    try:
                        if not entry.is_file():
                            continue
                        if not _title_matches_filename(title, entry.name):
                            continue
                        info = entry.stat()
                    except OSError:
                        continue
                    if info.st_size <= 1024 or info.st_mtime < not_before - 5:
                        continue
                    if best is None or info.st_mtime > best[1]:
                        best = (entry.path, info.st_mtime)
                return best[0] if best else None

            def download_single(item):
                _, q = item
                vid_id = q['video'].get('id', '')
                if not vid_id: return
                title = q['video'].get('title', '') or ''
                q.pop('permanent_failure', None)
                if getattr(self, 'cancel_download', False):
                    q['status'] = "Pending"
                    repaint(q)
                    return
                q['status'] = "Downloading"
                repaint(q)

                # The options the Python API used, written as yt-dlp CLI flags.
                cli_args = [
                    "--newline",
                    "--format", "bestaudio/best",
                    "--extract-audio",
                    "--audio-format", target_format,
                    "--audio-quality", audio_quality,
                    "--retries", "15",
                    "--fragment-retries", "15",
                    "--file-access-retries", "10",
                    "--output", f"{folder}/%(title)s.%(ext)s",
                ]
                if ffmpeg_location:
                    cli_args.extend(["--ffmpeg-location", ffmpeg_location])
                if extra_args:
                    # Appended last, so the advanced field wins over the GUI picks
                    # exactly like the Settings dialog says it should.
                    cli_args.extend(extra_args)
                # The track itself: yt-dlp takes URLs positionally, so it goes
                # after every option. Without it yt-dlp exits with
                # "You must provide at least one URL" and nothing downloads.
                cli_args.append(f"https://www.youtube.com/watch?v={vid_id}")

                # Stagger the first starts of a pass. Every thread asking
                # YouTube for a stream in the same instant is what gets the
                # requests throttled, and a throttled request is what used to
                # come back as a song that "skipped".
                #
                # Only the first max_workers items start simultaneously and
                # need staggering. Items beyond that wait for a previous
                # download to finish (~20-30s), which is already a far larger
                # gap than any stagger we could add — an extra 2s sleep on
                # those items was pure dead time.
                slot = take_start_slot()
                if 0 < slot < max_workers:
                    time.sleep(0.4 * slot)

                # Say this track has been asked for, now. yt-dlp still has to reach YouTube and
                # find the stream before a single byte arrives - a few seconds on a good day,
                # longer when a track has to be retried - and every line the status bar showed
                # until then came from that resolution. A batch that had already started looked
                # like it had not started at all, so the queue is reported as working from the
                # moment each thread hands its track to yt-dlp.
                self._dl_progress_percent(vid_id, "0%")

                downloaded_file = None
                failure = None
                with title_lock_for(title):
                    for attempt in range(1, DOWNLOAD_ITEM_ATTEMPTS + 1):
                        if getattr(self, 'cancel_download', False):
                            break
                        attempt_started = time.time()
                        failure = None
                        try:
                            def _register_proc(p, _self=self):
                                with _self._active_ytdlp_procs_lock:
                                    _self._active_ytdlp_procs.append(p)

                            def _unregister_proc(p, _self=self):
                                with _self._active_ytdlp_procs_lock:
                                    try:
                                        _self._active_ytdlp_procs.remove(p)
                                    except ValueError:
                                        pass

                            downloaded_file = None
                            _proc_ref = [None]  # so unregister can find it after

                            def _proc_and_track(p, _reg=_register_proc, _ref=_proc_ref):
                                _reg(p)
                                _ref[0] = p

                            try:
                                downloaded_file = run_yt_dlp_download(
                                    cli_args,
                                    progress_cb=lambda pct: self._dl_progress_percent(vid_id, pct),
                                    cancelled_cb=lambda: getattr(self, 'cancel_download', False),
                                    proc_cb=_proc_and_track,
                                )
                            finally:
                                if _proc_ref[0] is not None:
                                    _unregister_proc(_proc_ref[0])
                            # run_yt_dlp_download raises for anything that truly
                            # failed, so getting here means the track is on
                            # disk. Only its name is uncertain.
                            if not downloaded_file or not os.path.isfile(downloaded_file):
                                downloaded_file = find_downloaded_file(title, attempt_started)
                            break
                        except Exception as e:
                            failure = str(e)
                            downloaded_file = None
                            print(f"Download attempt {attempt}/{DOWNLOAD_ITEM_ATTEMPTS} failed for {vid_id}: {failure}")
                            if getattr(self, 'cancel_download', False):
                                break
                            if _is_permanent_download_error(failure):
                                # The video itself is gone, so a later pass of
                                # the queue would only fail it all over again.
                                q['permanent_failure'] = True
                                break
                            if attempt < DOWNLOAD_ITEM_ATTEMPTS:
                                time.sleep(min(1.5 * attempt, 5.0))

                with self.active_downloads_lock:
                    if vid_id in self.active_downloads:
                        del self.active_downloads[vid_id]

                # A clean yt-dlp exit means the track downloaded, even when no
                # usable path came out of its output. Treating "no path" as a
                # failure is what turned finished downloads into skipped songs.
                if failure is None:
                    if downloaded_file:
                        _add_placeholder_tag(downloaded_file)
                        with downloaded_lock:
                            downloaded_filepaths.append(downloaded_file)
                        produced_files[id(q)] = downloaded_file
                    q['status'] = "Finished"
                    with finished_counter_guard:
                        finished_counter[0] += 1
                    self._dl_finished_count = finished_counter[0]
                else:
                    q['status'] = "Pending"

                if getattr(self, 'cancel_download', False):
                    q['status'] = "Pending"
                repaint(q)

                with finished_counter_guard:
                    finished_cnt = finished_counter[0]
                total_cnt = getattr(self, '_batch_total_count', len(getattr(self, 'queue_items', [])))
                prog_prefix = f"({finished_cnt}/{total_cnt}) " if total_cnt > 0 else ""
                with self.active_downloads_lock:
                    if self.active_downloads:
                        vals = list(self.active_downloads.values())
                        if len(vals) > 5:
                            self.dl_progress_signal.emit(f"{prog_prefix}Downloading: {', '.join(vals[:5])} (+{len(vals)-5} more)")
                        else:
                            self.dl_progress_signal.emit(f"{prog_prefix}Downloading: {', '.join(vals)}")
                    else:
                        self.dl_progress_signal.emit(f"{prog_prefix}Processing...")

            max_passes = 4
            for pass_num in range(1, max_passes + 1):
                # Always check UP (from top / index 0) for undownloaded tracks before checking down
                pending_items = sorted(
                    [(idx, q) for idx, q in enumerate(self.queue_items)
                     if q['status'] == "Pending" and not q.get('permanent_failure')],
                    key=lambda x: x[0]
                )
                if not pending_items or getattr(self, 'cancel_download', False):
                    break

                if pass_num > 1:
                    self.status_signal.emit(
                        f"Re-checking queue (Pass {pass_num}: retrying {len(pending_items)} pending downloads)...",
                        False, "#FF8C00"
                    )
                    time.sleep(min(1.0 * pass_num, 4.0))

                max_workers = min(threads_count, len(pending_items))
                reset_start_slots()
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = []
                    for item in pending_items:
                        if getattr(self, 'cancel_download', False):
                            break
                        futures.append(executor.submit(download_single, item))
                    for fut in futures:
                        try:
                            fut.result()
                        except Exception as e:
                            # One track blowing up must not take the rest of the
                            # queue down with it.
                            print(f"Unexpected error while downloading: {e}")

            # --- Verification Pass with Placeholder Tag & Title Matching ---
            if not getattr(self, 'cancel_download', False):
                # Check every finished track against the file it actually
                # produced. The old check compared a file count against a queue
                # count and matched raw titles against sanitized filenames, so
                # any title holding a ':' or a '/' looked missing and was
                # downloaded all over again for no reason.
                #
                # Build a single file-entry list once (one scandir) instead of
                # re-scanning the folder for each finished item that needs a
                # lookup. This is the difference between N × folder-scan syscalls
                # and 1 scan + N in-memory matches.
                _verify_entries = None  # lazily built: [(match_key, path, mtime)]

                def _ensure_verify_entries():
                    nonlocal _verify_entries
                    if _verify_entries is not None:
                        return _verify_entries
                    try:
                        raw = list(os.scandir(folder))
                    except OSError:
                        _verify_entries = []
                        return _verify_entries
                    entries = []
                    for entry in raw:
                        try:
                            if not entry.is_file():
                                continue
                            info = entry.stat()
                            if info.st_size <= 1024:
                                continue
                            mk = _title_match_key(os.path.splitext(entry.name)[0])
                            if mk:
                                entries.append((mk, entry.path, info.st_mtime))
                        except OSError:
                            continue
                    _verify_entries = entries
                    return _verify_entries

                def _find_from_verify_entries(title, not_before=0.0):
                    """Match a title against the pre-scanned folder entries."""
                    wanted = _title_match_key(title)
                    if not wanted:
                        return None
                    best = None
                    for mk, path, mtime in _ensure_verify_entries():
                        if mtime < not_before - 5:
                            continue
                        if mk == wanted or (len(wanted) >= 12 and mk.startswith(wanted)) or (len(mk) >= 12 and wanted.startswith(mk)):
                            if best is None or mtime > best[1]:
                                best = (path, mtime)
                    return best[0] if best else None

                missing_items = []
                for idx, q in enumerate(list(self.queue_items)):
                    if q['status'] != "Finished":
                        continue
                    path = produced_files.get(id(q))
                    if path and os.path.isfile(path) and os.path.getsize(path) > 1024:
                        continue
                    path = _find_from_verify_entries(q['video'].get('title', ''))
                    if path:
                        produced_files[id(q)] = path
                        continue
                    q['status'] = "Pending"
                    missing_items.append((idx, q))
                    repaint(q)

                if missing_items:
                    missing_items.sort(key=lambda x: x[0])
                    self.status_signal.emit(
                        f"Verification: {len(missing_items)} files missing on disk. Redownloading missing tracks...",
                        False, "#FF8C00"
                    )
                    # Sync the lightweight counter with reality: verification
                    # reset some items back to Pending, so the counter is now
                    # inflated by however many were demoted.
                    with finished_counter_guard:
                        finished_counter[0] -= len(missing_items)
                        self._dl_finished_count = finished_counter[0]
                    reset_start_slots()
                    with ThreadPoolExecutor(max_workers=min(threads_count, len(missing_items))) as executor:
                        futures = [executor.submit(download_single, item) for item in missing_items]
                        for fut in futures:
                            try:
                                fut.result()
                            except Exception as e:
                                print(f"Unexpected error while redownloading: {e}")

                # Strip placeholder verification tag from all confirmed files
                for f in list(dict.fromkeys(downloaded_filepaths + list(produced_files.values()))):
                    if os.path.exists(f):
                        _remove_placeholder_tag(f)

            # The renamer's own artist/title check, run here on the file each track produced.
            # A YouTube title with no artist in it is exactly the state the renamer's "No artist
            # found" prompt exists for, and what that prompt asks the user to type is the channel
            # name the result row already showed him - so it is filled in now instead of leaving
            # every bare title for a console question. It runs after every match against a title
            # has been made: the verification pass looks for the file a title produced, and a name
            # that already carries the channel does not match that title any more.
            #
            # Rename only, deliberately. Writing artist/title into the file here would make it read
            # as hand-tagged, and the same test that keeps a hand-tagged file from being renamed
            # keeps it out of the normalization pass - every auto-named song would have skipped the
            # volume work. Left untagged, the renamer reads the pair out of the new name, tags it,
            # and normalizes it exactly as it does today.
            if getattr(self, 'channel_prefix_rename', False) and not getattr(self, 'cancel_download', False):
                def channel_prefix_for(q, produced_path):
                    """Rename one finished track to 'Channel - Title', or leave it where it is."""
                    if not produced_path or not os.path.isfile(produced_path):
                        return None
                    suffix = os.path.splitext(produced_path)[1].lower()
                    if suffix not in TAGGABLE_EXTENSIONS:
                        return None
                    new_stem = channel_prefixed_stem(
                        os.path.splitext(os.path.basename(produced_path))[0],
                        entry_channel_name(q.get('video') or {}))
                    if not new_stem:
                        return None
                    new_path = os.path.join(os.path.dirname(produced_path), new_stem + suffix)
                    if new_path == produced_path or os.path.exists(new_path):
                        # Nothing in this program numbers a name: a target that is taken leaves
                        # the file where it is, same as the console renamer and the rename dialog.
                        return None
                    try:
                        os.rename(produced_path, new_path)
                    except OSError as exc:
                        trace.note("channel prefix skipped for %s: %s"
                                   % (os.path.basename(produced_path), exc))
                        return None
                    trace.note("channel prefix: %s -> %s"
                               % (os.path.basename(produced_path), os.path.basename(new_path)))
                    return new_path

                # One map of old path -> new path, because the two lists that still name the old
                # file have to be rewritten through the same answer: produced_files and
                # downloaded_filepaths hold the same path for one track, and a queue entry whose
                # file was already renamed by the entry ahead of it (two uploads of one title)
                # finds no file where its own file used to be and is left alone.
                prefixed_paths = {}
                for q in list(self.queue_items):
                    produced_path = produced_files.get(id(q))
                    new_path = channel_prefix_for(q, produced_path)
                    if new_path:
                        prefixed_paths[produced_path] = new_path
                        produced_files[id(q)] = new_path
                if prefixed_paths:
                    # Read through the map, every entry that names a moved file - not only the
                    # ones that moved. An entry whose file was renamed by the entry ahead of it
                    # is left alone, but its recorded path still points at a name that no longer
                    # exists, and produced_files is one of the two lists this batch hands on.
                    for key, value in list(produced_files.items()):
                        produced_files[key] = prefixed_paths.get(value, value)
                    downloaded_filepaths[:] = [prefixed_paths.get(p, p) for p in downloaded_filepaths]
                    count = len(prefixed_paths)
                    self.status_signal.emit(
                        f"Added the channel name to {count} download"
                        f"{'s' if count != 1 else ''} with no artist in the title.",
                        False, "#1abd33")

            self._last_downloaded_files = list(dict.fromkeys(
                downloaded_filepaths + [p for p in produced_files.values() if p]
            ))

            if getattr(self, 'cancel_download', False):
                self.status_signal.emit("Download cancelled.", False, "#E31E24")
            else:
                remaining = [q for q in self.queue_items if q['status'] == "Pending"]
                if remaining:
                    unavailable = len([q for q in remaining if q.get('permanent_failure')])
                    if unavailable:
                        self.status_signal.emit(
                            f"Batch completed ({len(remaining)} failed, {unavailable} unavailable).",
                            False, "#FF8C00"
                        )
                    else:
                        self.status_signal.emit(f"Batch completed ({len(remaining)} failed).", False, "#FF8C00")
                else:
                    self.status_signal.emit("Batch complete!", False, "#1abd33")

        # The button already reads "Downloading..." and the first queue rows have flipped, but
        # the first thing the status bar could say about the work itself used to come from yt-dlp
        # reporting a percentage - seconds after this, once an in-flight track had been resolved
        # and had bytes moving. Nothing in between looked like a start, so the batch announces
        # itself here, on the GUI thread, in the same click that asked for it.
        self.dl_progress_signal.emit(f"(0/{self._batch_total_count}) Starting "
                                     f"{self._batch_total_count} download"
                                     f"{'s' if self._batch_total_count != 1 else ''}...")

        threading.Thread(target=bg_download, daemon=True).start()
        # Config save deferred until after the download thread is launched:
        # the thread already has its own captured settings, so this write
        # (which serialises search_results) overlapping with yt-dlp startup
        # means it no longer delays the first download attempt.
        self.save_config()
