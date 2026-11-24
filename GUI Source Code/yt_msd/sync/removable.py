# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.sync.removable).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
import threading
import shutil
from pathlib import Path
import time
from typing import Optional, Tuple, Callable
from PySide6.QtCore import Signal, QThread
from yt_msd.sync.client import SyncClientWorker
from yt_msd.sync.config import SyncConfigManager
from yt_msd.sync.tags import SYNC_RETROGRADE_GRACE_SECONDS, drive_last_synced_timestamp, format_sync_timestamp, parse_sync_timestamp, write_sync_tag_file
from yt_msd.sync.transfer import filter_audio_files, get_drive_io_lock, make_throttled_progress_cb



class SyncRemovableWorker:
    """Synchronizes audio files between local master folders and removable storage devices."""
    @staticmethod
    def sync_local_folders(src_dir: Path, dest_dir: Path, deletion_mode: str = 'mirror',
                           status_cb: Optional[Callable[[str], None]] = None,
                           progress_cb: Optional[Callable[[int, int, str, int, int], None]] = None) -> Tuple[bool, str, int, int]:
        progress_cb = make_throttled_progress_cb(progress_cb)
        if not src_dir.is_dir():
            return False, f"Source directory '{src_dir}' does not exist.", 0, 0
        dest_dir.mkdir(parents=True, exist_ok=True)

        src_files = filter_audio_files(src_dir)
        src_map = {f.name: f for f in src_files}
        dest_files = filter_audio_files(dest_dir)
        dest_map = {f.name: f for f in dest_files}

        transferred = 0
        deleted = 0

        # Mirror deletion
        if deletion_mode == 'mirror':
            for local_name, local_path in list(dest_map.items()):
                if local_name not in src_map:
                    try:
                        local_path.unlink()
                        deleted += 1
                        if status_cb:
                            status_cb(f"Removed deleted track: {local_name}")
                    except Exception:
                        pass

        total_items = len(src_files)
        for idx, (name, src_file) in enumerate(src_map.items(), 1):
            dest_file = dest_dir / name
            needs_copy = False

            if not dest_file.exists():
                needs_copy = True
            else:
                try:
                    s_stat = src_file.stat()
                    d_stat = dest_file.stat()
                    # If size differs or source is newer by > 2s, copy
                    if s_stat.st_size != d_stat.st_size or s_stat.st_mtime > d_stat.st_mtime + 2.0:
                        needs_copy = True
                except Exception:
                    needs_copy = True

            if needs_copy:
                if status_cb:
                    status_cb(f"Copying [{idx}/{total_items}]: {name}")
                try:
                    # High-speed unthrottled copy using 4MB streaming buffer
                    BUF_SIZE = 4 * 1024 * 1024
                    file_size = max(1, src_file.stat().st_size)
                    copied_bytes = 0
                    if progress_cb:
                        progress_cb(0, file_size, name, idx, total_items)
                    with open(src_file, 'rb') as sf, open(dest_file, 'wb') as df:
                        while True:
                            buf = sf.read(BUF_SIZE)
                            if not buf:
                                break
                            df.write(buf)
                            copied_bytes += len(buf)
                            if progress_cb:
                                progress_cb(copied_bytes, file_size, name, idx, total_items)
                    shutil.copystat(src_file, dest_file)
                    transferred += 1
                    if progress_cb:
                        progress_cb(file_size, file_size, name, idx, total_items)
                except Exception as e:
                    print(f"Error copying {name} to {dest_file}: {e}")

        return True, f"Synced {transferred} files ({deleted} removed).", transferred, deleted

    @staticmethod
    def sync_removable_chain(removable_chain: dict, config_manager: SyncConfigManager,
                             status_cb: Optional[Callable[[str], None]] = None,
                             progress_cb: Optional[Callable[[int, int, str, int, int], None]] = None,
                             confirm_cb: Optional[Callable[[str], bool]] = None) -> Tuple[bool, str, int, int]:
        sync_code = str(removable_chain.get('sync_code', ''))
        dest_path = Path(removable_chain.get('folder_path', ''))
        del_mode = removable_chain.get('deletion_mode', 'mirror')
        chain_name = removable_chain.get('name', 'Removable Media')

        # Find the chain that supplies the source files. Its folder lives on a
        # second drive that also gets worked over, so take every drive lock this
        # chain may touch in a fixed (sorted) order - that way two chains that
        # point at each other's drives cannot deadlock. The inner worker
        # re-acquires the same locks reentrantly.
        matching_hc = next((hc for hc in config_manager.hosted_chains if str(hc.get('sync_code')) == sync_code), None)
        matching_cc = next((cc for cc in config_manager.client_chains if str(cc.get('sync_code')) == sync_code), None)
        src_chain = matching_hc or matching_cc or {}
        anchors = set()
        for p in (dest_path, Path(src_chain.get('folder_path', ''))):
            try:
                anchor = str(p.anchor)
            except Exception:
                anchor = ''
            if anchor:
                anchors.add(anchor)
        drive_locks = [get_drive_io_lock(a) for a in sorted(anchors)]
        for lock in drive_locks:
            lock.acquire()
        try:
            return SyncRemovableWorker._sync_removable_chain_locked(
                sync_code, dest_path, del_mode, chain_name, config_manager, status_cb, progress_cb,
                matching_hc, matching_cc, confirm_cb)
        finally:
            for lock in reversed(drive_locks):
                lock.release()

    @staticmethod
    def _sync_removable_chain_locked(sync_code: str, dest_path: Path, del_mode: str,
                                     chain_name: str, config_manager: SyncConfigManager,
                                     status_cb: Optional[Callable[[str], None]],
                                     progress_cb: Optional[Callable[[int, int, str, int, int], None]],
                                     matching_hc: Optional[dict] = None,
                                     matching_cc: Optional[dict] = None,
                                     confirm_cb: Optional[Callable[[str], bool]] = None) -> Tuple[bool, str, int, int]:
        # Find matching hosted chain or client chain (the wrapper normally passes
        # these in already; the lookup is only a fallback for direct callers)
        if matching_hc is None and matching_cc is None:
            matching_hc = next((hc for hc in config_manager.hosted_chains if str(hc.get('sync_code')) == sync_code), None)
            matching_cc = next((cc for cc in config_manager.client_chains if str(cc.get('sync_code')) == sync_code), None)

        if matching_hc:
            src_dir = Path(matching_hc.get('folder_path', ''))
            if status_cb:
                status_cb(f"[USB Sync: {chain_name}] Syncing from hosted master folder '{src_dir.name}'...")
            ok, msg, transferred, deleted = SyncRemovableWorker.sync_local_folders(src_dir, dest_path, del_mode, status_cb, progress_cb)
            if ok:
                write_sync_tag_file(
                    dest_path,
                    sync_code=sync_code,
                    chain_name=chain_name,
                    sync_style='Mirror' if del_mode == 'mirror' else 'Additive',
                    last_synced_by='Host',
                    parent_sync_folder=str(src_dir)
                )
            return ok, msg, transferred, deleted

        elif matching_cc:
            src_dir = Path(matching_cc.get('folder_path', ''))

            # Retrograde failsafe. The drive carries its own last_synced in its
            # TAG.yaml. If this PC's client copy has not been refreshed since that,
            # writing it to the drive rolls the drive back to an older version of
            # the chain - and in Mirror mode deletes tracks the drive still has.
            # Such a client has to hear from its host first.
            drive_ts = drive_last_synced_timestamp(dest_path)
            client_ts = parse_sync_timestamp(matching_cc.get('last_synced'))
            try:
                drive_tracks = filter_audio_files(dest_path)
            except Exception:
                drive_tracks = []
            # A drive with nothing on it has nothing to lose, and a client with no
            # recorded sync is assumed stale rather than trusted.
            is_retrograde = bool(drive_tracks) and drive_ts is not None and (
                client_ts is None or client_ts < drive_ts - SYNC_RETROGRADE_GRACE_SECONDS)

            # 1. Sync client from host first over network
            if status_cb:
                if is_retrograde:
                    status_cb(f"[USB Sync: {chain_name}] This PC's copy is older than the drive's; "
                              f"refreshing from host before writing...")
                status_cb(f"[USB Sync: {chain_name}] Step 1/2: Updating client chain from host...")
            # No confirm_cb here on purpose: this is the removable half, and the deletion guard is
            # a LAN-chain rule. A sync that has to stop and ask about files never does that on the
            # way onto or off a USB drive.
            ok, msg, t, d = SyncClientWorker.sync_chain(matching_cc, status_cb=status_cb, progress_cb=progress_cb)
            if ok:
                # This copy genuinely did just come off the host, so say so. Without
                # the stamp the drive would look newer than this PC after every
                # successful USB sync, and the question would come back on the next
                # plug-in.
                matching_cc['last_synced'] = time.time()
                try:
                    config_manager.save()
                except Exception:
                    pass
            if not ok:
                if is_retrograde:
                    # The host is out of reach, so the only copy this PC can offer
                    # is older than what the drive already holds. Rolling a newer
                    # drive back is the user's call, not the sync's.
                    if status_cb:
                        status_cb(f"[USB Sync: {chain_name}] Drive holds a newer version and the host is "
                                  f"unreachable - asking before overwriting...")
                    question = (
                        f"Syncing '{chain_name}' would replace the copy on '{dest_path}' with an older one.\n\n"
                        f"Drive last synced: {format_sync_timestamp(drive_ts)} "
                        f"({len(drive_tracks)} track(s) on it)\n"
                        f"This PC last synced: {format_sync_timestamp(client_ts)}\n\n"
                        f"The host for Sync Code {sync_code} could not be reached:\n{msg}\n\n"
                        "Sync an older version of the chain onto the drive anyway?"
                    )
                    if confirm_cb is None or not confirm_cb(question):
                        return False, ("Sync skipped: the drive holds a newer version of this chain and the host "
                                       "could not be reached, so this PC's older copy was not written to the drive."), 0, 0
                if status_cb:
                    status_cb(f"[USB Sync: {chain_name}] Host offline, syncing with local client cache...")

            if status_cb:
                status_cb(f"[USB Sync: {chain_name}] Step 2/2: Syncing local files to removable device...")
            ok2, msg2, transferred, deleted = SyncRemovableWorker.sync_local_folders(src_dir, dest_path, del_mode, status_cb, progress_cb)
            if ok2:
                write_sync_tag_file(
                    dest_path,
                    sync_code=sync_code,
                    chain_name=chain_name,
                    sync_style='Mirror' if del_mode == 'mirror' else 'Additive',
                    last_synced_by='Client',
                    parent_sync_folder=str(matching_cc.get('folder_path', ''))
                )
            return ok2, msg2, transferred, deleted

        else:
            return False, f"No hosted or client sync chain with Sync Code {sync_code} found on this PC.", 0, 0



class RemovableSyncThread(QThread):
    status_signal = Signal(str)
    progress_signal = Signal(int, int, str, int, int)
    finished_signal = Signal(bool, str, int, int)
    confirm_signal = Signal(str, str)  # (chain id, question) - parked until answer_confirm()

    def __init__(self, removable_config: dict, config_manager: SyncConfigManager):
        super().__init__()
        self.removable_config = removable_config
        self.config_manager = config_manager
        # Only MainApp turns this on, and only because it can put the question on
        # screen. Left off, a sync that needs asking simply proceeds.
        self.confirm_enabled = False
        self._confirm_event = threading.Event()
        self._confirm_answer = True

    def answer_confirm(self, proceed: bool):
        """The GUI thread's reply to a confirm_signal this thread emitted."""
        self._confirm_answer = bool(proceed)
        self._confirm_event.set()

    def run(self):
        chain_id = str(self.removable_config.get('id', ''))

        def _status(txt):
            self.status_signal.emit(txt)

        def _progress(done, total, filename, idx, total_items):
            self.progress_signal.emit(done, total, filename, idx, total_items)

        def _confirm(message: str) -> bool:
            """Ask the user on the GUI thread and wait here for the answer."""
            if not self.confirm_enabled:
                return True
            self._confirm_event.clear()
            self._confirm_answer = True
            self.confirm_signal.emit(chain_id, message)
            while not self._confirm_event.wait(timeout=0.5):
                if self.isInterruptionRequested():
                    return False
            return bool(self._confirm_answer)

        ok, msg, transferred, deleted = SyncRemovableWorker.sync_removable_chain(
            self.removable_config,
            self.config_manager,
            status_cb=_status,
            progress_cb=_progress,
            confirm_cb=_confirm
        )
        self.finished_signal.emit(ok, msg, transferred, deleted)



class RemovableInitThread(QThread):
    """Creates the target folder and writes the initial TAG.yaml off the GUI thread."""
    done_signal = Signal(bool, str, str)  # ok, error message, folder path

    def __init__(self, dest_path: Path, sync_code: str, chain_name: str,
                 del_mode: str, last_synced_by: str, parent_folder: str):
        super().__init__()
        self.dest_path = dest_path
        self.sync_code = sync_code
        self.chain_name = chain_name
        self.del_mode = del_mode
        self.last_synced_by = last_synced_by
        self.parent_folder = parent_folder

    def run(self):
        drive_lock = get_drive_io_lock(self.dest_path)
        drive_lock.acquire()
        try:
            try:
                self.dest_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                self.done_signal.emit(False, f"Could not create folder on drive:\n{e}", "")
                return

            # Write the initial TAG.yaml (all config lives here, not in local config)
            ok = write_sync_tag_file(
                self.dest_path,
                sync_code=self.sync_code,
                chain_name=self.chain_name,
                sync_style='Mirror' if self.del_mode == 'mirror' else 'Additive',
                last_synced_by=self.last_synced_by,
                parent_sync_folder=self.parent_folder
            )
            if ok:
                self.done_signal.emit(True, "", str(self.dest_path))
            else:
                self.done_signal.emit(False, f"Failed to write TAG.yaml file to {self.dest_path}.", "")
        finally:
            drive_lock.release()
