# Open Source Software under the Apache License, Version 2.0
# PySide6 version of yt-msd - Cython source for the compiled GUI build
#
# Everything after the END OF CYTHON HEADER line below is the text of
# "GUI Source Code/yt-msd-gui.pyw" copied byte-for-byte, so the compiled program behaves
# exactly like the script. Edit the .pyw, then run:
#     python build_gui_cython.py sync      (rewrites this file from the .pyw)
#     python build_gui_cython.py verify    (checks the two are still identical)
#
# The directives are all set to keep Python semantics unchanged:
#   language_level=3         Python 3 rules for division, print, str/bytes, comparisons.
#   annotation_typing=False  "def f(x: int) -> Optional[str]" hints stay documentation, so no
#                            argument or return value is type-checked or converted at call time.
#   infer_types=False        no variable is given a C int/float type, so large integers, None
#                            handling and error messages stay exactly Python's own.
#   binding=True             closures and nested functions capture names the way Python does.
# cython: language_level=3
# cython: annotation_typing=False
# cython: infer_types=False
# cython: binding=True
#
# ---- END OF CYTHON HEADER - the unchanged yt-msd-gui.pyw source follows ----
# Open Source Software under the Apache License, Version 2.0
# PySide6 version of yt-msd
# Programmed with Qwen, if you don't like it, don't use it.
# This file is the entry point only. The program is the yt_msd package beside it; it stopped
# being one file in 3.5, and the parts moved out a wave at a time with the GUI Test Suite
# green after every single wave.

import os
import re
import sys
import json
import threading
import tempfile
import subprocess
import zipfile
import shutil
from pathlib import Path
# ThreadPoolExecutor is not defined in concurrent.futures - Python 3.15 hands it over with
# a "lazy from" (concurrent/futures/__init__.py: lazy from .thread import ThreadPoolExecutor),
# and that deferred binding is an object of its own called lazy_import, which is not callable.
# Running this file as a script never notices: Python resolves the binding the moment the name
# is used. The compiled build does notice, because it stores whatever the name held at import
# time, and in the installed exe that is the unresolved binding - which is the
# "TypeError: 'lazy_import' object is not callable" that fired on every local-library metadata
# pass. Importing from the module that really defines the class skips the lazy re-export.
from concurrent.futures.thread import ThreadPoolExecutor
from concurrent.futures import as_completed  # a plain re-export, already resolved at import
# These names moved out of this file during the 3.5 modularisation (wave 1) and are
# re-exported here so the entry point keeps every name it has always had while the
# split proceeds. The final wave replaces this with the package's own entry point.
from yt_msd.constants import (
    APP_VERSION,
    AUDIO_EXTENSIONS,
    DEFAULT_DOWNLOAD_FORMAT,
    DOWNLOAD_FORMATS,
    INSTALLER_ASSET,
    MUTAGEN_TAGGABLE_EXTENSIONS,
    PAUSE_GLYPH,
    PLAY_GLYPH,
    REPLAY_GLYPH,
    SOURCE_ASSET,
    STOP_AFTER_ALWAYS,
    STOP_AFTER_LABELS,
    STOP_AFTER_OFF,
    STOP_AFTER_ONCE,
    STOP_AFTER_STATE_NAMES,
    STOP_AFTER_TOOLTIPS,
    TAGGABLE_EXTENSIONS,
    UPDATE_MODE_INSTALLER,
    UPDATE_MODE_REPLACE,
    UPDATE_MODE_SWAP,
    UPDATE_REPO,
)
from yt_msd.deps import (
    FileSystemEventHandler,
    Observer,
    _VLC_MODULE_AVAILABLE,
    _WATCHDOG_AVAILABLE,
    vlc,
    winreg,
)
from yt_msd import deps as _deps_mod
# _VLC_IMPORT_ERROR only ever exists on a machine where the guarded import above failed,
# and the program reads it with getattr(..., default) for exactly that
# reason, so it is forwarded the same way rather than demanded here.
if hasattr(_deps_mod, '_VLC_IMPORT_ERROR'):
    _VLC_IMPORT_ERROR = _deps_mod._VLC_IMPORT_ERROR
from yt_msd.paths import (
    _app_icon_path,
    app_icon,
    is_packaged_build,
)
from yt_msd.util.console import (
    Colors,
    _print_lock,
    _safe_print,
)
from yt_msd.util.text import (
    _is_romanized,
    _sanitize_filename,
    _split_artist_title,
    _title_match_key,
    _title_matches_filename,
    clean_youtube_title,
)
from yt_msd.util.timefmt import (
    _format_audio_duration,
)
from yt_msd.util.version import (
    _extract_version_number,
    _release_asset_file,
    _version_is_newer,
    select_release_asset,
)
from yt_msd.util.yaml import (
    _yaml_dump_list,
    _yaml_scalar_parse,
    _yaml_scalar_repr,
    yaml_dump,
    yaml_load,
)
import webbrowser
import urllib.request
import urllib.parse
import html
import io
import shlex
import time
import random
import socket
import struct
import hashlib
import traceback
from typing import Dict, List, Optional, Tuple, Callable, Union
from PIL import Image

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QPushButton, QLineEdit, 
                               QComboBox, QCheckBox, QSlider, QScrollArea, 
                               QSplitter, QSplitterHandle, QFileDialog, QMessageBox, QDialog,
                               QSystemTrayIcon, QMenu, QFrame, QGridLayout,
                               QSizePolicy, QStyle, QToolTip, QStyleOption, QSpinBox, QProgressBar, QInputDialog)
from PySide6.QtCore import Qt, Signal, QTimer, Slot, QPoint, QRect, QMargins, QThread, QEvent, QObject, QByteArray
from PySide6.QtGui import QIcon, QPixmap, QImage, QAction, QColor, QPalette, QPainter, QPainterPath, QBrush, QFont, QDrag, QFontMetrics, QCursor
from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtNetwork import QLocalServer, QLocalSocket

# The loudness numbers and the four settings the ffmpeg -af chain is built from now live in
# the package. The fixed numbers are imported directly; the settings a user changes are
# reached through one object so a write cannot miss a reader.
from yt_msd.audio.tuning import (
    _available_threads,
    TARGET_LUFS,
    TRUE_PEAK,
    LOUDNESS_RANGE,
    BITRATE,
    SILENCE_THRESHOLD,
    SILENCE_DURATION,
    SILENCE_KEEP,
)
from yt_msd.audio.tuning import TUNING
# These names moved out of this file during the 3.5 modularisation (wave 2c) and are
# re-exported here so the entry point keeps every name it has always had while the
# split proceeds. The final wave replaces this with the package's own entry point.
from yt_msd.audio.localmeta import (
    _LOCAL_META_CACHE_CAP,
    _ffprobe_audio_meta,
    _local_display_name,
    _local_meta_cache,
    _local_meta_cache_put,
    _read_local_audio_meta,
)
from yt_msd.audio.normalize import (
    _silence_trim_filters,
    build_af_chain,
    normalize_file,
    run_loudness_normalization,
)
from yt_msd.audio.probe import (
    _ffmpeg_binary,
    _ffprobe_binary,
    _get_audio_duration,
    _probe_format_block,
    check_ffmpeg_available,
    measure_loudness,
)
from yt_msd.audio.renamer import (
    _print_renamer_banner,
    _select_renamer_folder,
    clean_and_tag_files,
    run_integrated_renamer_cli,
)
from yt_msd.audio.tags import (
    COMM,
    EasyID3,
    EasyMP4,
    ID3,
    ID3NoHeaderError,
    MutagenFile,
    _add_placeholder_tag,
    _remove_placeholder_tag,
    read_metadata_tags,
    write_metadata_tags,
)
# These names moved out of this file during the 3.5 modularisation (wave 3) and are
# re-exported here so the entry point keeps every name it has always had while the
# split proceeds. The final wave replaces this with the package's own entry point.
from yt_msd.ytdlp.install import (
    YTDLP_EXTRACT_TIMEOUT,
    YTDLP_GITHUB_REPO,
    YTDLP_INSTALL_TIMEOUT,
    YTDLP_UPDATE_CHECK_INTERVAL,
    YTDLP_WINGET_ID,
    YtDlpMissingError,
    _yt_dlp_lookup_paths,
    find_winget_executable,
    latest_yt_dlp_release,
    run_winget,
)
# These names moved out of this file during the 3.5 modularisation (wave 5f) and are
# re-exported here so the entry point keeps every name it has always had while the
# split proceeds. The final wave replaces this with the package's own entry point.
from yt_msd.playback.prefetch import (
    PREFETCH_CACHE_LIMIT,
    PREFETCH_SECONDS_BEFORE_END,
    PREFETCH_URL_MAX_AGE,
)
from yt_msd.playback.stream import (
    STREAM_END_SLACK_MS,
    STREAM_REFETCH_LIMIT,
    STREAM_RENEW_COOLDOWN,
    STREAM_RESUME_GRACE,
    STREAM_SEEK_RESTORE_TIMEOUT,
    STREAM_STALL_SECONDS,
    STREAM_URL_MAX_AGE,
)
# These names moved out of this file during the 3.5 modularisation (wave 3b) and are
# re-exported here so the entry point keeps every name it has always had while the
# split proceeds. The final wave replaces this with the package's own entry point.
from yt_msd.ytdlp.download import (
    DOWNLOAD_ITEM_ATTEMPTS,
    _PERMANENT_DOWNLOAD_ERROR_MARKERS,
    _YTDLP_FINAL_PATH_PATTERNS,
    _YTDLP_STAGED_PATH_PATTERNS,
    _clean_reported_path,
    _is_permanent_download_error,
    _match_reported_path,
    run_yt_dlp_download,
)
from yt_msd.ytdlp.runner import (
    SEARCH_CHANNEL_RETRIES,
    SEARCH_RETRY_TIMEOUT,
    StreamFetchSupersededError,
    _stream_fetch_owner,
    _stream_fetches,
    _stream_fetches_lock,
    _ytdlp_exe_cache,
    _ytdlp_exe_cache_lock,
    begin_stream_fetch,
    cancel_stream_fetches,
    end_stream_fetch,
    entry_channel_name,
    find_yt_dlp_executable,
    get_yt_dlp_version,
    note_stream_fetch_process,
    resolve_stream_url,
    run_yt_dlp_json,
    run_yt_dlp_text_search,
    stream_cli_args,
    stream_fetch_vid_for_this_thread,
    stream_fetch_was_superseded,
)
# These names moved out of this file during the 3.5 modularisation (wave 2b) and are
# re-exported here so the entry point keeps every name it has always had while the
# split proceeds. The final wave replaces this with the package's own entry point.
from yt_msd.subproc import (
    _child_utf8_env,
    _hidden_window_kwargs,
)
# These names moved out of this file during the 3.5 modularisation (wave 5) and are
# re-exported here so the entry point keeps every name it has always had while the
# split proceeds. The final wave replaces this with the package's own entry point.
from yt_msd.ui.theme import (
    THEME_COLORS,
    get_accent_color,
    get_system_accent_color,
    get_system_appearance_mode,
)
from yt_msd.ui.widgets import (
    ClickableSlider,
    DoubleClickButton,
    DraggableQueueWidget,
    THUMB_BOX_COLORS,
    THUMB_BOX_H,
    THUMB_BOX_INSET,
    THUMB_BOX_PAUSED,
    THUMB_BOX_PLAIN,
    THUMB_BOX_PLAYING,
    THUMB_BOX_RADIUS,
    THUMB_BOX_W,
    THUMB_HOVER_RECHECK_MS,
    THUMB_IMG_RADIUS,
    THUMB_TILE_H,
    THUMB_TILE_W,
    ThumbnailWidget,
    _ElideTextFilter,
    cover_thumbnail,
    pil_to_qpixmap,
)
# These names moved out of this file during the 3.5 modularisation (wave 5g) and are
# re-exported here so the entry point keeps every name it has always had while the
# split proceeds. The final wave replaces this with the package's own entry point.
from yt_msd.ui.render import (
    LOCAL_RENDER_CHUNK_BUDGET_S,
    LOCAL_RENDER_CHUNK_MAX_ROWS,
    LOCAL_RENDER_CHUNK_MIN_ROWS,
    LOCAL_RENDER_FIRST_CHUNK_ROWS,
    LOCAL_RENDER_ROW_HEIGHT_GUESS,
)
# These names moved out of this file during the 3.5 modularisation (wave 4) and are
# re-exported here so the entry point keeps every name it has always had while the
# split proceeds. The final wave replaces this with the package's own entry point.
from yt_msd.sync.client import (
    ClientSyncThread,
    SyncClientWorker,
)
from yt_msd.sync.config import (
    DEFAULT_SYNC_SETTINGS,
    SyncConfigManager,
    _CONFIG_WRITE_LOCK,
    is_client_chain_paused,
)
from yt_msd.sync.discovery import (
    UDPBeaconBroadcaster,
    discover_host_on_lan,
    discover_hosts_on_lan,
    send_lan_update_notification,
)
from yt_msd.sync.host import (
    HostFolderWatcher,
    SyncHostServer,
)
from yt_msd.sync.lan import (
    SYNC_CHUNK_SIZE,
    SYNC_PORT_END,
    SYNC_PORT_START,
    SYNC_SOCKET_TIMEOUT,
    UDP_BEACON_PORT,
    _CACHED_LOCAL_IP,
    _CACHED_LOCAL_IP_TIME,
    get_broadcast_addresses,
    get_current_wifi_ssid,
    get_local_ip,
)
from yt_msd.sync.removable import (
    RemovableInitThread,
    RemovableSyncThread,
    SyncRemovableWorker,
)
from yt_msd.sync.startup import (
    is_run_on_startup_enabled,
    set_run_on_startup,
)
from yt_msd.sync.tags import (
    SYNC_RETROGRADE_GRACE_SECONDS,
    SYNC_TAG_FILENAME,
    SYNC_TAG_TIME_FORMATS,
    drive_last_synced_timestamp,
    find_tagged_sync_folders_on_drive,
    format_sync_timestamp,
    make_removable_chain_id,
    parse_sync_timestamp,
    read_sync_tag_file,
    write_sync_tag_file,
)
from yt_msd.sync.transfer import (
    _DRIVE_IO_LOCKS,
    _DRIVE_IO_LOCKS_GUARD,
    _recv_all,
    compute_file_sha256,
    filter_audio_files,
    get_drive_io_lock,
    make_throttled_progress_cb,
    recv_file_from_socket,
    recv_json_msg,
    send_json_msg,
    stream_file_to_socket,
)
# These names moved out of this file during the 3.5 modularisation (wave 5c) and are
# re-exported here so the entry point keeps every name it has always had while the
# split proceeds. The final wave replaces this with the package's own entry point.
from yt_msd.sync.dialogs import (
    ConnectClientChainDialog,
    ConnectRemovableMediaDialog,
    CreateHostChainDialog,
    SyncManagerDialog,
)
# These names moved out of this file during the 3.5 modularisation (wave 5b) and are
# re-exported here so the entry point keeps every name it has always had while the
# split proceeds. The final wave replaces this with the package's own entry point.
from yt_msd.export import (
    EXPORT_CONFIG_ENTRY,
    EXPORT_FORMAT_VERSION,
    EXPORT_MANIFEST_NAME,
    EXPORT_SKIP_DIRS,
    EXPORT_SYNC_ENTRY,
    ExportDialog,
    SYNC_ONLY_CONFIG_KEYS,
    build_export_manifest_text,
    build_exported_config,
    default_export_config,
    extract_package_music,
    iter_folder_files,
    music_import_destination,
    read_import_package,
    sanitize_archive_name,
    unique_music_archive_name,
    zip_folder_into,
)
# These names moved out of this file during the 3.5 modularisation (wave 5d) and are
# re-exported here so the entry point keeps every name it has always had while the
# split proceeds. The final wave replaces this with the package's own entry point.
from yt_msd.ui.dialogs import (
    MetadataRenameDialog,
    PlaylistDialog,
    SettingsDialog,
    TrayProgressPopup,
    UpdateAvailableDialog,
    UpdateReadyDialog,
    YtDlpUpdateDialog,
)

class MainApp(QMainWindow):
    status_signal = Signal(str, bool, str)
    search_results_signal = Signal(list, bool)
    search_failed_signal = Signal()
    thumbnails_loaded_signal = Signal(str, QPixmap)
    playback_started_signal = Signal(str, str, bool)
    queue_update_signal = Signal()
    queue_status_changed_signal = Signal(int)
    dl_progress_signal = Signal(str)
    renamer_finished_signal = Signal()
    host_activity_signal = Signal(str, str, str)
    _probe_results_signal = Signal(dict)  # cached drive/chain state from the drive probe thread
    local_list_refresh_signal = Signal()  # ask for a non-blocking local folder rescan
    _local_listing_signal = Signal(object)  # (render_id, folder_path, items) from the folder scan thread
    update_available_signal = Signal(str, str, str, str)  # tag, release_name, download_url, asset_name
    update_downloaded_signal = Signal(str, str, str)  # new_file_path, tag, how it is applied (emitted from the download bg thread)
    missing_deps_signal = Signal(str)  # html fragment of missing dependencies (emitted from the VLC init thread)
    import_finished_signal = Signal(object)  # prepared export package, read on the import thread
    import_failed_signal = Signal(str)  # import problem, reported from the import thread
    ytdlp_missing_signal = Signal(str)  # yt-dlp absent or not installable (from a bg thread)
    ytdlp_update_signal = Signal(str, str)  # installed yt-dlp version, newest yt-dlp version
    ytdlp_version_signal = Signal(str)  # yt-dlp version found by a bg thread, shown on the GUI thread
    stream_refreshed_signal = Signal(bool, str)  # (re-resolved ok, track title) from the stream-refresh thread

    def __init__(self):
        super().__init__()
        self.setWindowTitle("yt-msd | YouTube Media Downloader")
        # Started by the MusicBee plugin (it passes --from-musicbee, see
        # MusicBee Plugin/Plugin.cs): open compact, and come back at whatever size
        # and position it was last closed at. Started normally, nothing changes.
        self.launched_by_host = "--from-musicbee" in sys.argv
        if self.launched_by_host:
            self.resize(1100, 700)
        else:
            self.resize(1804, 935)
        
        # State Arrays
        self.search_results = []
        self.queue_items = []
        self.local_folders = []
        self.recent_folders = []
        self.recent_playlists = []
        # Local file editor state: File Explorer style multi-selection.
        self.local_selected_paths = set()
        self.local_rows = []
        self.local_row_by_path = {}
        self.local_btns = []
        # Every folder switch gets its own id. Rows produced by a scan of a folder that
        # has already been replaced are dropped by it instead of landing on the folder
        # that is on screen now.
        self._local_render_id = 0
        # The listing of the folder currently filling the pane, less the rows that have
        # already been drawn, plus what the last chunk cost the GUI thread. A fill that is
        # still running is abandoned by the next folder switch.
        self._local_render_pending = None
        self._local_render_pending_id = 0
        self._local_render_pending_path = None
        self._local_render_step = 0
        self._local_render_chunk_end = None
        self._local_render_chunk_cost = 0.0
        self._local_render_chunk_rows = 0
        self._local_render_row_cost = 0.0
        self._local_render_row_height = LOCAL_RENDER_ROW_HEIGHT_GUESS
        # How many rows the folder on screen is going to have, and the height already handed to
        # the pane for them. See _reserve_local_extent.
        self._local_render_total_rows = 0
        self._local_render_extent_height = 0
        # Chunk N+1 is queued on a zero timer, which Qt runs after it has already laid out
        # and polished chunk N - the reason a folder fills in instead of arriving at once.
        self._local_render_timer = QTimer()
        self._local_render_timer.setSingleShot(True)
        self._local_render_timer.timeout.connect(self._fill_local_chunk)
        self.local_selection_anchor = None
        self.current_local_file_path = ""
        self.splitter_sizes = [300, 800, 300]
        # Qt's own serialisation of the window frame, kept only for windows that
        # were opened from MusicBee. See _apply_host_window_geometry.
        self.host_window_geometry = ""
        self.thumbnail_cache = {}
        self.thumbnail_cache_size = 0
        
        # Config Map
        self.format_var = "mp3"
        self.bitrate_var = "192"
        self.download_path = ""
        self.local_current_path = ""
        self.appearance_mode = "Dark" 
        self.accent_color_name = "Blue"
        self.volume_val = 100
        self.use_custom_args = False
        self.custom_args = ""
        self.minimize_to_tray = False
        self.save_place = False
        self.last_session = {}
        self.last_search = ""
        self.run_renamer = False
        self.renamer_path = ""
        self.run_custom_script = False
        self.custom_script_path = ""
        self._last_downloaded_files = []
        self.normalization_mode = "ask"  # "on" | "off" | "ask"
        self.auto_rename = False
        self.silence_pad_dur = 2.0
        self.silence_trim = True
        self.use_custom_norm_cmd = False
        self.custom_norm_cmd = ""
        self.download_threads = 3
        self.normalization_threads = max(1, os.cpu_count() // 2)
        self.local_rescan_interval = 60  # minutes (default 1 hour)
        self.disable_update_checks = False  # True once the user opts out of update notifications
        self._update_check_running = False  # guards against overlapping network update checks
        self._downloaded_update_tag = None  # tag already downloaded this session (avoid re-prompting)
        self.ytdlp_version = ""  # version the system yt-dlp reported, "" until it is known
        self.disable_ytdlp_updates = False  # True once the user opts out of yt-dlp update prompts
        self.ytdlp_last_update_check = 0.0  # epoch seconds of the last yt-dlp version check
        self._ytdlp_update_check_running = False  # guards against overlapping yt-dlp checks
        self.local_rescan_timer = QTimer(self)
        self.local_rescan_timer.timeout.connect(self._auto_rescan_local_folder)
        
        # Player Flags
        self.is_playing = False
        self.is_downloading = False
        self.cancel_download = False
        self.current_video_id = None
        self.current_playing_title = ""
        self.playback_index = -1
        # The row currently carrying the playing/paused colour: (pane, key, state), or None.
        # Compared against on every player tick so the colour moves only when it has to.
        self._playback_box = None
        # Which thumbnail row is holding its play button, and the timer that keeps asking the
        # pointer whether that row is still the one it is on. The timer only runs while a row is
        # holding the button, so nothing is polled while nobody is pointing at the list - see
        # THUMB_HOVER_RECHECK_MS and _recheck_thumb_hover.
        self._hover_tile = None
        self._thumb_hover_timer = QTimer(self)
        self._thumb_hover_timer.setInterval(THUMB_HOVER_RECHECK_MS)
        self._thumb_hover_timer.timeout.connect(self._recheck_thumb_hover)
        self.is_shuffled = False
        self.shuffle_history = []
        self.shuffle_order = []
        # "Stop after current": off / once / always, cycled by the player-bar button
        # and the tray entry (see the prefetch and stop-after block near play_result).
        # "always" is kept in gui_config.json and read back by load_config() so the next
        # window opens still stopping after every track; "once" is never restored, because
        # the track it was armed for does not exist in a new session.
        self.stop_after_current = STOP_AFTER_OFF
        # Which track an automatic "once" belongs to. A new search arms one for the
        # stream that is playing (see _arm_stop_after_for_new_search), and this id is
        # what lets that arming be forgotten again when a different track starts.
        # None means the armed state, if there is one, is the user's own.
        self._search_stop_after_track = None
        # Streams resolved seconds ahead of time: video id -> (url, user agent, epoch).
        # Written only by the prefetch thread, read once by the play path; the lock is
        # what keeps those two from tripping over the same dictionary.
        self._prefetched_streams = {}
        self._prefetch_lock = threading.Lock()
        self._prefetch_busy = set()     # video ids currently being resolved
        self._prefetch_decision = None  # (video id, next index, next video) decided ahead
        self._prefetch_trigger_key = None  # the track the decision was made for
        # The stream the player is actually loaded with: (video id, url, user agent, how old
        # that URL already was when it was resolved). This is what a dead stream is re-resolved
        # from, and it is None while a local file is playing or nothing has been played - a
        # file on disk is not a link with an expiry, so every question in the stream-liveness
        # block (see the block before "Stop after current") starts by asking whether this is set.
        # The rest is the watchdog for it: the last position libVLC reported and the moment it
        # last moved, whether the stream has been noticed dead, whether it is being re-resolved
        # right now, how many times this track has already reloaded itself, whether anybody has
        # ever heard this media advancing, and a position the user asked for that has to wait
        # until the fresh media answers.
        self._loaded_stream = None
        self._loaded_stream_at = None
        self._stream_seen_ms = -1
        self._stream_moved_at = None
        # Whether the media on the player is one the listener stopped and has not yet been heard
        # advancing again. While it is true the stall clock does not run, and the track gets
        # STREAM_RESUME_GRACE once it is playing again instead of the ordinary STREAM_STALL_SECONDS
        # verdict. See _watch_stream_liveness.
        self._stream_resuming = False
        self._stream_dead = False
        # Only a stream that has been heard advancing can count as having gone idle, which is the
        # only case where the age of its URL is on its own a reason to re-resolve it. A track the
        # session restore preloads at start up starts here as False and stays that way until
        # somebody plays it. See _stream_needs_renew.
        self._stream_listened = False
        self._stream_refetching = False
        self._stream_refetch_attempts = 0
        self._stream_renew_started_at = None
        self._pending_stream_seek_frac = None
        self._pending_stream_seek_ms = None
        self._pending_stream_pause = False
        self._pending_stream_seek_at = None
        # A track that ran to its end and was left on the player rather than advanced. libVLC is
        # done with that media: it answers neither a scrub nor a resume any more, which is why
        # dragging the bar back after a track finished did nothing at all. While this is set the
        # play button is a replay button and a scrub is a replay to the place the bar was put,
        # both through _replay_finished_track. Armed by _hold_finished_track, and cleared by
        # _note_loaded_stream - that is, by any new media reaching the player.
        self._finished_track = False
        # The "stop after current" state the hold happened under, remembered so that replaying
        # the track a "once" was spent on re-arms it: hearing that track again should not end
        # with the player moving on to a track nobody picked. See _replay_finished_track.
        self._finished_track_armed_under = STOP_AFTER_OFF
        # True between a replay asking for fresh media and that media arriving. It is what tells a
        # failed re-fetch apart from a failed self-heal: only the first has been promised the track
        # from its top, so only the first puts the replay button back. See _on_stream_refreshed.
        self._replay_in_flight = False
        self.is_muted = False
        self.active_downloads = {}
        self.active_downloads_lock = threading.Lock()
        # yt-dlp subprocess handles so cancel_batch_download can kill them
        # immediately instead of waiting for a readline() to return a line.
        self._active_ytdlp_procs = []
        self._active_ytdlp_procs_lock = threading.Lock()
        self.sync_manager_dialog = None
        self.last_wifi_ssid = get_current_wifi_ssid()
        # Persistent sync thread registry - lives at MainApp level so it survives dialog close/reopen
        self.sync_threads = {}  # chain_id -> QThread
        self.sync_progress_state = {}  # chain_id -> {'status': str, 'progress': str}
        # Runtime-only registry of currently connected removable drives (not persisted)
        self.active_removable_drives: dict = {}  # folder_path_str -> rc dict
        # Cached answers about the filesystem. Only the background probe thread
        # ever touches a drive; the GUI reads these instead, so a slow USB stick
        # or MP3 player can never stall the interface.
        self.known_connected_drives: set = set()  # drive roots seen by the last probe
        self.mount_state: dict = {}  # folder_path_str -> bool (mounted?)
        self.chain_track_counts: dict = {}  # chain_id -> audio file count
        self._drive_probe_lock = threading.Lock()
        self._drive_probe_busy = False
        self._drive_probe_pending = False
        # Only one import or export at a time: both do heavy filesystem work.
        self._export_import_busy = False
        # Guards the cached drive/chain state above: the probe thread reads it,
        # the GUI thread writes it.
        self._runtime_state_lock = threading.RLock()
        
        if getattr(sys, 'frozen', False):
            self.config_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            self.config_dir = os.path.dirname(os.path.abspath(__file__))
            
        self.config_path = os.path.join(self.config_dir, "gui_config.json")
        self.load_config()

        # Apply the normalization settings from the loaded config immediately
        TUNING.from_settings(self.silence_trim, self.silence_pad_dur,
                             self.use_custom_norm_cmd, self.custom_norm_cmd)

        # Placeholder so UI code can check readiness before VLC is initialized
        self.vlc_instance = None
        self.vlc_player = None
        self._vlc_ready = False

        self.setup_ui()
        self.apply_theme()

        self.status_signal.connect(self._on_status_update)
        self.search_results_signal.connect(self._on_search_results)
        self.search_failed_signal.connect(self._on_search_failed)
        self.playback_started_signal.connect(self._on_playback_started)
        self.stream_refreshed_signal.connect(self._on_stream_refreshed)
        self.queue_update_signal.connect(self._refresh_queue_display)
        self.queue_status_changed_signal.connect(self._on_queue_status_changed)
        self.thumbnails_loaded_signal.connect(self._on_thumbnail_loaded)
        self.dl_progress_signal.connect(lambda txt: self.dl_progress_label.setText(txt))
        self.renamer_finished_signal.connect(self._on_renamer_finished)
        self.host_activity_signal.connect(self._on_host_activity)
        self._probe_results_signal.connect(self._apply_probe_results)
        self.local_list_refresh_signal.connect(self._refresh_local_list_async)
        self._local_listing_signal.connect(self._on_local_listing)
        self.update_available_signal.connect(self._show_update_dialog)
        self.update_downloaded_signal.connect(self._prompt_swap_dialog)
        self.missing_deps_signal.connect(self._show_missing_dependencies)
        self.import_finished_signal.connect(self._apply_import_results)
        self.import_failed_signal.connect(self._on_import_failed)
        self.ytdlp_missing_signal.connect(self._show_ytdlp_missing_dialog)
        self.ytdlp_update_signal.connect(self._show_ytdlp_update_dialog)
        self.ytdlp_version_signal.connect(self._apply_ytdlp_version)

        self.player_timer = QTimer(self)
        self.player_timer.timeout.connect(self.update_player_ui)
        self.player_timer.start(16)

        self.setup_tray()
        self._update_local_rescan_timer()

        # Wi-Fi network change monitor timer (checks every 15s)
        self.wifi_monitor_timer = QTimer(self)
        self.wifi_monitor_timer.timeout.connect(self._check_wifi_network_change)
        self.wifi_monitor_timer.start(15000)

        # Removable drive auto-detect timer (checks every 3s for plugged drives with TAG.yaml).
        # The very first probe is deferred: enumerating drives at startup would
        # stat every root on the UI thread, including a slow player that happens
        # to be plugged in.
        self.drive_monitor_timer = QTimer(self)
        self.drive_monitor_timer.timeout.connect(self._check_removable_drives_change)
        self.drive_monitor_timer.start(3000)
        QTimer.singleShot(600, self._check_removable_drives_change)

        # Startup dependency validation runs inside the VLC init thread below,
        # so it never blocks the UI thread while the window is appearing.

        # Update check on startup (runs again with every local-folder rescan)
        QTimer.singleShot(1500, self._check_for_updates)

        # Initialize VLC in a background thread (plugin scanning can take seconds)
        threading.Thread(target=self._init_vlc_background, daemon=True).start()

        # yt-dlp lives outside the executable: find it, and install it with winget
        # on the first run. This stays in a background thread so the window still
        # appears exactly as fast as before.
        threading.Thread(target=self._ensure_yt_dlp_background, daemon=True).start()

        # Defer local folder load until after the window is shown
        if self.local_current_path:
            QTimer.singleShot(0, lambda: self.load_local_folder(self.local_current_path))

        if getattr(self, 'save_place', False) and hasattr(self, 'session_data'):
            sd = self.session_data
            if sd.get('current_video_id') == "local" and sd.get('local_current_path'):
                idx = sd.get('local_playback_index', -1)
                # The folder opened above has only just started streaming its rows, so
                # the track to resume on is remembered here and looked up by
                # _finish_local_render, which runs when that list is actually complete.
                # The folder it belongs to is remembered with it, because a folder that
                # cannot be opened - or one the user switches away from before the rows
                # land - must not have a track of another folder resumed in it.
                self._pending_local_restore_index = idx
                self._pending_local_restore_path = sd.get('local_current_path')

        # --- Local Network Sync Chains Subsystem ---
        self.sync_config_manager = SyncConfigManager(self.config_dir)
        self.sync_host_server = SyncHostServer(
            lambda: self.sync_config_manager.hosted_chains,
            on_client_activity_cb=self.host_activity_signal.emit
        )
        self.udp_beacon = UDPBeaconBroadcaster(
            lambda: self.sync_config_manager.hosted_chains,
            lambda: self.sync_host_server.active_port,
            on_chain_updated_cb=self._on_lan_chain_updated
        )
        self.host_watcher = HostFolderWatcher(self._on_hosted_folder_changed)

        # Client Auto-Sync Periodic Timer
        self.sync_timer = QTimer(self)
        self.sync_timer.timeout.connect(self._auto_sync_client_chains)

        # Start host server, UDP beacon, folder watchers, and client check on a background thread
        def _deferred_sync_startup():
            def _bg_init():
                try:
                    self.sync_host_server.start()
                    self.udp_beacon.start()
                    self.refresh_sync_watchers()
                except Exception:
                    pass
            threading.Thread(target=_bg_init, daemon=True).start()
            self._update_sync_timer()
            QTimer.singleShot(2500, self._auto_sync_client_chains)

        QTimer.singleShot(150, _deferred_sync_startup)

        if self.launched_by_host:
            self._apply_host_window_geometry()

        QApplication.instance().installEventFilter(self)

    def _on_host_activity(self, sync_code: str, client_ip: str, activity: str):
        """Called when a client connects or pulls files from our hosted sync chain."""
        chain_name = "Playlist"
        if hasattr(self, 'sync_config_manager'):
            for c in self.sync_config_manager.hosted_chains:
                if str(c.get('sync_code')) == str(sync_code):
                    chain_name = c.get('name', 'Playlist')
                    break
        msg = f"[Sync Host: {chain_name}] {activity} ({client_ip})"
        if hasattr(self, 'dl_progress_signal'):
            self.dl_progress_signal.emit(msg)
            def _clear_prog():
                try:
                    if self.dl_progress_label.text() == msg:
                        self.dl_progress_signal.emit("")
                except Exception:
                    pass
            QTimer.singleShot(4000, _clear_prog)
        if hasattr(self, 'sync_manager_dialog') and self.sync_manager_dialog and self.sync_manager_dialog.isVisible():
            self.sync_manager_dialog._on_host_activity_received(sync_code, client_ip, activity)

    def _on_renamer_finished(self):
        self._on_status_update("MP3 Renamer finished execution.", False, "#1abd33")
        self.refresh_local_list()

    def _update_local_rescan_timer(self):
        mins = getattr(self, 'local_rescan_interval', 60)
        if mins > 0:
            self.local_rescan_timer.start(mins * 60 * 1000)
        else:
            self.local_rescan_timer.stop()

    def _auto_rescan_local_folder(self):
        # Hourly auto-rescan: the folder scan runs on a worker thread so a slow
        # drive cannot freeze the window when the timer fires.
        self._refresh_local_list_async()
        # Every local-folder scan (startup + the hourly auto-rescan) also checks for updates.
        self._check_for_updates()
        # ... and the same pass checks whether the yt-dlp on this system is out of
        # date (that check throttles itself, so it is not a network call every hour).
        self._check_yt_dlp_updates()

    def refresh_sync_watchers(self):
        """Registers all hosted sync chains with the watchdog monitor in a background thread."""
        if hasattr(self, 'host_watcher') and hasattr(self, 'sync_config_manager'):
            def _bg():
                try:
                    self.host_watcher.stop_all()
                    for hc in list(self.sync_config_manager.hosted_chains):
                        cid = hc.get('id')
                        folder = hc.get('folder_path')
                        code = hc.get('sync_code')
                        delay = hc.get('notify_delay_mins', 5)
                        if cid and folder and code:
                            self.host_watcher.add_or_update_chain(cid, folder, code, delay)
                except Exception:
                    pass
            threading.Thread(target=_bg, daemon=True).start()

    def _on_hosted_folder_changed(self, sync_code: str):
        """Called from the folder watcher's debounce thread when a hosted folder changes."""
        port = self.sync_host_server.active_port if hasattr(self, 'sync_host_server') else 63350
        send_lan_update_notification(sync_code, port)
        # Emitted, not called directly: this runs on a watcher thread.
        self.status_signal.emit(f"Sync Chain (Code {sync_code}) updated. Notified clients on LAN.", False, "#1abd33")

    def _update_sync_timer(self):
        if hasattr(self, 'sync_config_manager') and hasattr(self, 'sync_timer'):
            mins = self.sync_config_manager.settings.get('auto_sync_interval_mins', 30)
            if mins > 0:
                self.sync_timer.start(mins * 60 * 1000)
            else:
                self.sync_timer.stop()

    def _auto_sync_client_chains(self):
        """Background routine that runs sync checks for all client sync chains with live progress reporting."""
        if not hasattr(self, 'sync_config_manager') or not self.sync_config_manager.client_chains:
            return

        def _bg():
            # Asked for here rather than before the thread starts: this is a
            # subprocess call and it has no business running on the UI thread.
            curr_wifi = get_current_wifi_ssid()
            for cc in list(self.sync_config_manager.client_chains):
                # Respect pause duration
                paused, _ = is_client_chain_paused(cc)
                if paused:
                    continue

                # Respect Wi-Fi binding if set
                req_wifi = cc.get('wifi_ssid', '').strip()
                if req_wifi and curr_wifi and req_wifi.lower() != curr_wifi.lower():
                    continue

                chain_name = cc.get('name', 'Sync')
                def _status(t):
                    if hasattr(self, 'dl_progress_signal'):
                        self.dl_progress_signal.emit(f"[Sync: {chain_name}] {t}")

                def _prog(done, total, fname, idx, total_items):
                    pct = int(done / total * 100) if total > 0 else 0
                    if hasattr(self, 'dl_progress_signal'):
                        self.dl_progress_signal.emit(f"[Sync: {chain_name}] [{idx}/{total_items}] ({pct}%) {fname}")

                ok, msg, transferred, deleted = SyncClientWorker.sync_chain(
                    cc,
                    status_cb=_status,
                    progress_cb=_prog
                )
                if hasattr(self, 'dl_progress_signal'):
                    self.dl_progress_signal.emit("")
                if ok:
                    cc['last_synced'] = time.time()
                    cc['status'] = "Up to date"
                    if transferred > 0 or deleted > 0:
                        self.status_signal.emit(f"Sync Chain '{cc.get('name')}': {transferred} updated, {deleted} removed.", False, "#1abd33")
                        if self.local_current_path == cc.get('folder_path'):
                            self.local_list_refresh_signal.emit()
                else:
                    cc['status'] = f"Host Offline"
            self.sync_config_manager.save()

        threading.Thread(target=_bg, daemon=True).start()

    def _on_lan_chain_updated(self, sync_code: str):
        """Called from the UDP beacon thread when a host announces an update."""
        if not hasattr(self, 'sync_config_manager') or not self.sync_config_manager.client_chains:
            return
        matching = [cc for cc in self.sync_config_manager.client_chains if str(cc.get('sync_code')) == str(sync_code)]
        if not matching:
            return

        for cc in matching:
            def _bg(c=cc):
                # Pause checks, the Wi-Fi lookup and the status line all belong
                # in the worker: this callback arrives on the beacon thread.
                paused, _ = is_client_chain_paused(c)
                if paused:
                    return
                req_wifi = c.get('wifi_ssid', '').strip()
                if req_wifi:
                    curr_wifi = get_current_wifi_ssid()
                    if curr_wifi and req_wifi.lower() != curr_wifi.lower():
                        return

                self.status_signal.emit(
                    f"Sync Chain '{c.get('name', 'Sync')}': Push notification received from host. Syncing...",
                    False, "#3B8ED0")

                ok, msg, transferred, deleted = SyncClientWorker.sync_chain(
                    c,
                    status_cb=lambda t: self.dl_progress_signal.emit(f"[Sync: {c.get('name', 'Sync')}] {t}") if hasattr(self, 'dl_progress_signal') else None,
                    progress_cb=lambda done, total, fname, idx, total_items: self.dl_progress_signal.emit(
                        f"[Sync: {c.get('name', 'Sync')}] [{idx}/{total_items}] ({int(done/total*100) if total > 0 else 0}%) {fname}"
                    ) if hasattr(self, 'dl_progress_signal') else None
                )
                if hasattr(self, 'dl_progress_signal'):
                    self.dl_progress_signal.emit("")
                if ok:
                    c['last_synced'] = time.time()
                    c['status'] = "Up to date"
                    if transferred > 0 or deleted > 0:
                        self.status_signal.emit(f"Sync Chain '{c.get('name')}': {transferred} updated, {deleted} removed.", False, "#1abd33")
                        if self.local_current_path == c.get('folder_path'):
                            self.local_list_refresh_signal.emit()
                self.sync_config_manager.save()
            threading.Thread(target=_bg, daemon=True).start()

    def _check_wifi_network_change(self):
        """Monitors for Wi-Fi SSID changes and triggers auto-sync for bound sync chains."""
        def _bg():
            curr = get_current_wifi_ssid()
            if not curr:
                return
            last = getattr(self, 'last_wifi_ssid', None)
            if curr != last:
                self.last_wifi_ssid = curr
                if hasattr(self, 'sync_config_manager') and self.sync_config_manager.client_chains:
                    bound = [
                        cc for cc in self.sync_config_manager.client_chains
                        if cc.get('wifi_ssid', '').strip().lower() == curr.lower() and not is_client_chain_paused(cc)[0]
                    ]
                    if bound:
                        self.status_signal.emit(f"Connected to Wi-Fi '{curr}': Auto-syncing bound sync chain(s)...", False, "#1abd33")
                        self._auto_sync_client_chains()
        threading.Thread(target=_bg, daemon=True).start()

    def _get_current_system_drives(self) -> set:
        drives = set()
        _skip_drives = {'C:\\'}  # Never scan the system drive
        if sys.platform == 'win32':
            try:
                import ctypes
                bitmask = ctypes.windll.kernel32.GetLogicalDrives()
                for i in range(26):
                    if bitmask & (1 << i):
                        drive = f"{chr(65 + i)}:\\"
                        if drive.upper() in _skip_drives:
                            continue
                        if os.path.exists(drive):
                            drives.add(drive)
            except Exception:
                import string
                for letter in string.ascii_uppercase:
                    drive = f"{letter}:\\"
                    if drive.upper() in _skip_drives:
                        continue
                    if os.path.exists(drive):
                        drives.add(drive)
        return drives

    def _check_removable_drives_change(self):
        """Starts a drive probe. Performs no filesystem work on the GUI thread."""
        if not hasattr(self, 'sync_config_manager'):
            return
        with self._drive_probe_lock:
            if self._drive_probe_busy:
                # A slow device can keep a probe busy for a while. Instead of
                # stacking threads on top of the same busy drive, ask the one
                # that is already running to do one more pass when it finishes.
                self._drive_probe_pending = True
                return
            self._drive_probe_busy = True
            # Whether the sync manager is open is decided here, on the GUI
            # thread, so the probe thread never has to ask a widget anything.
            collect_counts = bool(self.sync_manager_dialog and self.sync_manager_dialog.isVisible())
        threading.Thread(target=self._probe_drives_background, args=(collect_counts,), daemon=True).start()

    def _probe_drives_background(self, collect_counts: bool = False):
        """Every drive touch the sync monitor makes happens here, off the UI thread."""
        try:
            while True:
                with self._drive_probe_lock:
                    self._drive_probe_pending = False

                payload = {'drives': set(), 'mount_updates': {}, 'removed': [],
                           'scanned': [], 'counts': {}}
                try:
                    current_drives = self._get_current_system_drives()
                except Exception:
                    current_drives = set()
                payload['drives'] = current_drives

                # Mount state for the removable chains already registered
                with self._runtime_state_lock:
                    registered_paths = list(self.active_removable_drives.keys())
                for fp in registered_paths:
                    try:
                        mounted = os.path.exists(fp)
                    except Exception:
                        mounted = False
                    payload['mount_updates'][fp] = mounted
                    if not mounted:
                        payload['removed'].append(fp)

                # Look for TAG.yaml folders on the remaining drives
                busy_roots = self._busy_drive_roots()
                _skip = {'C:\\'}
                for drive in sorted(current_drives):
                    if drive.upper() in _skip:
                        continue
                    if str(Path(drive).anchor) in busy_roots:
                        # A sync is mid-transfer on this device; its contents
                        # are already known, so do not interrupt it with a scan.
                        continue
                    try:
                        tagged_folders = find_tagged_sync_folders_on_drive(drive)
                    except Exception:
                        continue
                    for folder_path, tag_data in tagged_folders:
                        sync_code = str(tag_data.get('sync_code', '')).strip()
                        if not sync_code:
                            continue
                        f_str = str(folder_path)
                        del_mode = tag_data.get('deletion_mode', 'mirror')
                        chain_name = (tag_data.get('chain_name', '') or
                                      folder_path.name or
                                      f"Drive ({drive[0]}:)")
                        cid = make_removable_chain_id(sync_code, f_str)
                        rc = {
                            'id': cid,
                            'sync_code': sync_code,
                            'name': chain_name,
                            'folder_path': f_str,
                            'deletion_mode': del_mode,
                            'last_synced': tag_data.get('last_synced', ''),
                            'status': 'Ready',
                            'drive_root': drive,
                        }
                        payload['scanned'].append(rc)
                        payload['mount_updates'][f_str] = True

                payload['counts'] = self._collect_chain_track_counts(collect_counts)
                # Deliver the cached results to the main thread
                self._probe_results_signal.emit(payload)

                with self._drive_probe_lock:
                    if not self._drive_probe_pending:
                        break
        finally:
            with self._drive_probe_lock:
                self._drive_probe_busy = False

    def _busy_drive_roots(self) -> set:
        """Drive roots that a sync thread is currently working on."""
        roots = set()
        with self._runtime_state_lock:
            running = list(self.sync_threads.values())
        for thread in running:
            try:
                if not thread.isRunning():
                    continue
            except (RuntimeError, AttributeError):
                continue
            cfg = getattr(thread, 'removable_config', None) or getattr(thread, 'chain_config', None)
            if not cfg:
                continue
            try:
                roots.add(str(Path(cfg.get('folder_path', '')).anchor))
            except Exception:
                pass
        return roots

    def _collect_chain_track_counts(self, collect_counts: bool = False) -> dict:
        """Track counts for the hosted cards, computed off the UI thread and only
        while the sync manager is actually open (the caller decides that on the
        GUI thread and passes the answer in)."""
        counts = {}
        if not collect_counts:
            return counts
        try:
            for hc in list(self.sync_config_manager.hosted_chains):
                cid = hc.get('id')
                folder = hc.get('folder_path', '')
                if not cid or not folder:
                    continue
                counts[cid] = len(filter_audio_files(Path(folder)))
        except Exception:
            pass
        return counts

    def _apply_probe_results(self, payload: dict):
        """Main-thread slot. Reads cached results only - never touches a drive."""
        if not isinstance(payload, dict):
            return
        new_chains = []
        with self._runtime_state_lock:
            self.known_connected_drives = payload.get('drives') or set()
            for fp, mounted in (payload.get('mount_updates') or {}).items():
                self.mount_state[fp] = bool(mounted)
            for fp in payload.get('removed') or []:
                self.active_removable_drives.pop(fp, None)
                self.mount_state.pop(fp, None)
            self.chain_track_counts = payload.get('counts') or {}

            for rc in payload.get('scanned') or []:
                f_str = rc['folder_path']
                sync_code = rc['sync_code']
                is_hosted = any(str(hc.get('sync_code', '')).strip() == sync_code
                                for hc in self.sync_config_manager.hosted_chains)
                is_client = any(str(cc.get('sync_code', '')).strip() == sync_code
                                for cc in self.sync_config_manager.client_chains)
                if f_str not in self.active_removable_drives:
                    self.active_removable_drives[f_str] = rc
                    self.mount_state[f_str] = True
                    if is_hosted or is_client:
                        new_chains.append(rc)
                else:
                    self.active_removable_drives[f_str]['name'] = rc['name']
                    self.active_removable_drives[f_str]['drive_root'] = rc['drive_root']

        for rc in new_chains:
            self._auto_sync_removable_chain(rc)

        # refresh_cards() skips the rebuild itself when nothing about the chains
        # changed, so this stays cheap even though the monitor runs every 3s.
        if self.sync_manager_dialog and self.sync_manager_dialog.isVisible():
            try:
                self.sync_manager_dialog.refresh_cards()
            except RuntimeError:
                pass

    def _auto_sync_removable_chain(self, rc: dict):
        """Launch a background removable chain sync via RemovableSyncThread so it shows in the sync manager."""
        cid = rc.get('id', '')
        # Don't start if already in progress
        existing = self.sync_threads.get(cid)
        if existing and existing.isRunning():
            return

        chain_name = rc.get('name', 'Removable Media')
        rc['status'] = 'Syncing...'
        self.sync_progress_state[cid] = {'status': 'Status: Syncing...  |  Last Synced: Syncing...', 'progress': ''}
        self.status_signal.emit(f"Removable media detected for '{chain_name}'. Starting auto-sync...", False, "#3B8ED0")
        if self.sync_manager_dialog and self.sync_manager_dialog.isVisible():
            try:
                self.sync_manager_dialog.refresh_cards()
            except RuntimeError:
                pass

        thread = RemovableSyncThread(rc, self.sync_config_manager)
        self.sync_threads[cid] = thread
        # The worker may stop short of overwriting a drive that holds a newer
        # version of the chain. Asking about that belongs on the GUI thread, so
        # the worker parks until this app answers it.
        thread.confirm_enabled = True
        thread.confirm_signal.connect(self._on_retrograde_sync_confirm)

        def _on_status(txt):
            status_text = f"Status: {txt}  |  Last Synced: Syncing..."
            self.sync_progress_state.setdefault(cid, {})['status'] = status_text
            if hasattr(self, 'dl_progress_signal'):
                self.dl_progress_signal.emit(f"[USB Sync: {chain_name}] {txt}")
            if self.sync_manager_dialog and self.sync_manager_dialog.isVisible():
                self.sync_manager_dialog._update_client_card_label(cid, "status_lbl", status_text)

        def _on_progress(done, total, fname, idx, total_items):
            pct = int(done / total * 100) if total > 0 else 0
            prog_txt = f"[{idx}/{total_items}] ({pct}%) {fname}"
            self.sync_progress_state.setdefault(cid, {})['progress'] = prog_txt
            if hasattr(self, 'dl_progress_signal'):
                self.dl_progress_signal.emit(f"[USB Sync: {chain_name}] {prog_txt}")
            if self.sync_manager_dialog and self.sync_manager_dialog.isVisible():
                self.sync_manager_dialog._update_client_card_label(cid, "progress_lbl", prog_txt)

        def _on_finish(ok, msg, transferred, deleted):
            # A skipped retrograde sync is a decision, not a fault, so it is
            # reported as such instead of as a failed sync.
            skipped = (not ok) and str(msg).startswith("Sync skipped")
            if ok:
                rc['status'] = "Up to date"
            elif skipped:
                rc['status'] = str(msg)
            else:
                rc['status'] = f"Sync Failed: {msg}"
            if ok:
                rc['last_synced'] = time.time()
            self.sync_progress_state.pop(cid, None)
            if hasattr(self, 'dl_progress_signal'):
                self.dl_progress_signal.emit("")
            if ok:
                self.status_signal.emit(f"Removable media '{chain_name}' sync complete: {transferred} updated, {deleted} removed.", False, "#1abd33")
            elif skipped:
                self.status_signal.emit(f"Removable media '{chain_name}' was left as it is: {msg}", False, "#FF8C00")
            else:
                self.status_signal.emit(f"Removable media '{chain_name}' sync failed: {msg}", False, "#E31E24")
            if self.sync_manager_dialog:
                try:
                    QTimer.singleShot(0, self.sync_manager_dialog.refresh_cards)
                except RuntimeError:
                    pass

        thread.status_signal.connect(_on_status)
        thread.progress_signal.connect(_on_progress)
        thread.finished_signal.connect(_on_finish)
        thread.start()

    def _on_retrograde_sync_confirm(self, chain_id: str, question: str):
        """Main-thread slot for a removable sync that stopped short of rolling a
        newer drive back to an older copy. The worker parks until this answers, so
        the question is asked on the GUI thread and defaulting to No keeps the
        drive exactly as it is."""
        thread = self.sync_threads.get(chain_id)
        if thread is None or not hasattr(thread, 'answer_confirm'):
            return
        parent = None
        try:
            if self.sync_manager_dialog is not None and self.sync_manager_dialog.isVisible():
                parent = self.sync_manager_dialog
        except RuntimeError:
            parent = None
        try:
            answer = QMessageBox.question(parent, "Removable Drive Holds a Newer Version", question,
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            proceed = (answer == QMessageBox.Yes)
        except Exception:
            proceed = False
        try:
            thread.answer_confirm(proceed)
        except RuntimeError:
            pass

    def open_sync_manager(self, parent_dialog=None):
        """Opens or brings the Sync Chains Manager to the foreground directly with Main < Settings < Sync stacking."""
        if self.sync_manager_dialog is not None:
            try:
                self.sync_manager_dialog.refresh_cards()
            except RuntimeError:
                self.sync_manager_dialog = None

        if self.sync_manager_dialog is None:
            dlg = SyncManagerDialog(self)
            self.sync_manager_dialog = dlg
            dlg.setWindowModality(Qt.NonModal)
            dlg.setAttribute(Qt.WA_DeleteOnClose, False)

        # Enforce stacking: Main window < Settings window < Sync window
        self.raise_()
        if parent_dialog and parent_dialog.isVisible():
            parent_dialog.raise_()
        elif hasattr(self, 'settings_dialog') and self.settings_dialog and self.settings_dialog.isVisible():
            self.settings_dialog.raise_()

        self.sync_manager_dialog.show()
        self.sync_manager_dialog.raise_()
        self.sync_manager_dialog.activateWindow()

    def _show_missing_dependencies(self, missing_html: str):
        """Show the startup dependency warning. Runs on the GUI thread; the probing
        itself happens in the background VLC-init thread (see _init_vlc_background)."""
        msg = QMessageBox(self)
        msg.setWindowTitle("Missing Required Dependencies - yt-msd")
        msg.setIcon(QMessageBox.Warning)
        msg.setTextFormat(Qt.RichText)
        msg.setText(
            "<h3>Required Dependencies Missing</h3>"
            "yt-msd detected that the following components are not installed or could not be found:<br><br>"
            + missing_html
            + "<br><br>Some features (music playback, audio conversion, normalization) will not function until installed."
        )
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()

    def _check_for_updates(self):
        """Query the GitHub releases page and notify the user if the newest release is newer than this build."""
        if getattr(self, 'disable_update_checks', False):
            return
        if getattr(self, '_update_check_running', False):
            return
        self._update_check_running = True

        def _bg():
            try:
                api_url = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
                req = urllib.request.Request(api_url, headers={"User-Agent": "yt-msd-updater"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                tag = (data.get("tag_name") or "").strip()
                release_name = (data.get("name") or tag).strip()
                assets = data.get("assets") or []
                # Which file is wanted depends on what kind of yt-msd this is, and it
                # is looked up by name: a release page lists its files in the order
                # they were uploaded, so the setup program is not always the first one.
                wanted_asset = INSTALLER_ASSET if is_packaged_build() else SOURCE_ASSET
                asset_name, download_url = select_release_asset(assets, wanted_asset)
                if not tag:
                    return
                if tag == getattr(self, '_downloaded_update_tag', None):
                    return  # already downloaded this session; don't nag again
                if _version_is_newer(_extract_version_number(tag), _extract_version_number(APP_VERSION)):
                    self.update_available_signal.emit(tag, release_name, download_url, asset_name)
            except Exception:
                pass
            finally:
                self._update_check_running = False

        threading.Thread(target=_bg, daemon=True).start()

    def _show_update_dialog(self, tag, release_name, download_url, asset_name):
        """Show the update dialog on the GUI thread and act on the user's choice."""
        dlg = UpdateAvailableDialog(self, tag, release_name, APP_VERSION, asset_name)
        choice = dlg.exec()
        if dlg.never_notify:
            self.disable_update_checks = True
            self.save_config()
        if choice != QDialog.Accepted:
            return
        if not download_url or not asset_name:
            wanted = INSTALLER_ASSET if is_packaged_build() else SOURCE_ASSET
            self.status_signal.emit(
                f"Release {tag} has no {wanted} file this copy of yt-msd can download.",
                False, "#E31E24"
            )
            return
        self._download_update(download_url, asset_name, tag)

    def _download_update(self, url, filename, tag):
        """Download the release file this kind of yt-msd needs, into the folder it runs from."""
        if not url:
            self.status_signal.emit("Update has no downloadable file to fetch.", False, "#E31E24")
            return
        running_path = self._current_executable_path()
        running_name = os.path.basename(running_path).lower()
        if is_packaged_build():
            # The installed program is updated by its setup program, which replaces the
            # whole yt-msd folder around this exe. Only a download carrying this exe's
            # own name is a file-for-file replacement of the running file.
            base_dir = self.config_dir
            if os.path.basename(filename).lower() == running_name:
                mode = UPDATE_MODE_SWAP
            else:
                mode = UPDATE_MODE_INSTALLER
        else:
            # A copy started from the source is updated by writing the new source file
            # over the very file that is being run, whatever the release page calls it.
            base_dir = os.path.dirname(running_path)
            filename = os.path.basename(running_path)
            mode = UPDATE_MODE_REPLACE
        dest_path = os.path.join(base_dir, filename)
        self.status_signal.emit(f"Downloading update {tag}...", False, "#3B8ED0")

        def _bg():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "yt-msd-updater"})
                with urllib.request.urlopen(req, timeout=120) as resp:
                    payload = resp.read()
                # The whole file is in memory before anything is written, so a failed
                # download never leaves a half-written file where yt-msd runs from.
                with open(dest_path, "wb") as out:
                    out.write(payload)
                self._downloaded_update_tag = tag
                self.status_signal.emit(f"Update {tag} downloaded to: {dest_path}", False, "#1abd33")
                self.update_downloaded_signal.emit(dest_path, tag, mode)
            except Exception as e:
                self.status_signal.emit(f"Update download failed: {e}", False, "#E31E24")

        threading.Thread(target=_bg, daemon=True).start()

    def _current_executable_path(self):
        """Absolute path of the file this instance is currently running from."""
        if is_packaged_build():
            return os.path.abspath(sys.executable)
        return os.path.abspath(__file__)

    def _prompt_swap_dialog(self, new_path, tag, mode=UPDATE_MODE_SWAP):
        """After a successful download, offer to close this version and move on to the new one."""
        old_path = self._current_executable_path()
        if mode == UPDATE_MODE_REPLACE:
            # The new source file was written over the file this program was started
            # from, so it already sits exactly where the old one was.
            new_path = old_path
        dlg = UpdateReadyDialog(self, new_path, old_path, tag, mode)
        choice = dlg.exec()
        if choice == QDialog.Accepted:
            # Only a drop-in update deletes the file this program was started from: an
            # installer overwrites the whole folder itself, and a replaced source file
            # is already in place.
            self._launch_swap_helper(new_path, old_path, delete_old=(mode == UPDATE_MODE_SWAP))
            # closeEvent() saves the settings, hides the tray, and ends the event
            # loop, which brings the process down a moment later - exactly what
            # the swap helper started above is waiting for.
            self.close()
        elif mode == UPDATE_MODE_INSTALLER:
            self.status_signal.emit(
                f"Update ready. Run {new_path} when you want to update yt-msd; this version is left as it is.",
                False, "#FF8C00"
            )
        elif mode == UPDATE_MODE_REPLACE:
            self.status_signal.emit(
                f"Update ready. {new_path} is already the new version; restart yt-msd to run it.",
                False, "#FF8C00"
            )
        else:
            self.status_signal.emit(
                f"Update ready. New file: {new_path} (old file kept: {old_path}). Swap them manually to finish.",
                False, "#FF8C00"
            )

    def _launch_swap_helper(self, new_path, old_path, delete_old=True):
        """Write a temporary helper script that waits for this process to exit, deletes the old file,
        launches the new version, then deletes itself."""
        pid = os.getpid()
        if is_packaged_build():
            launch_cmd = f'"{new_path}"'
        else:
            interp = os.path.abspath(sys.executable)
            # Prefer the windowless interpreter so the relaunched app doesn't open a console.
            if os.path.basename(interp).lower() == "python.exe":
                candidate = os.path.join(os.path.dirname(interp), "pythonw.exe")
                if os.path.exists(candidate):
                    interp = candidate
            launch_cmd = f'"{interp}" "{new_path}"'

        swap_path = os.path.join(tempfile.gettempdir(), f"ytmsd_swap_{pid}.bat")
        # UPDATE_MODE_INSTALLER leaves this file alone and lets the setup program
        # overwrite the whole yt-msd folder. UPDATE_MODE_REPLACE has already written the
        # new source file over this one, so there is nothing to delete. UPDATE_MODE_SWAP
        # is a drop-in update: the file this program was started from goes first.
        drop_old = (
            'if not "%OLD%"=="%NEW%" (\r\n'
            '  if exist "%OLD%" del /F /Q "%OLD%"\r\n'
            ')\r\n'
        ) if delete_old else ""
        bat = (
            "@echo off\r\n"
            f'set "PID={pid}"\r\n'
            f'set "OLD={old_path}"\r\n'
            f'set "NEW={new_path}"\r\n'
            'powershell -NoProfile -Command "while (Get-Process -Id %PID% -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 300 }"\r\n'
            + drop_old +
            f'start "" {launch_cmd}\r\n'
            'del /F /Q "%~f0"\r\n'
        )
        try:
            with open(swap_path, "w", encoding="utf-8") as f:
                f.write(bat)
        except Exception:
            return
        try:
            # CREATE_NO_WINDOW (0x08000000) keeps the helper itself invisible.
            subprocess.Popen(["cmd.exe", "/c", swap_path], creationflags=0x08000000)
        except Exception:
            pass

    def _ensure_yt_dlp_background(self):
        """First-run setup for yt-dlp: use the copy on this system, or install it.

        yt-dlp is not inside the yt-msd executable, so the first run has to put it
        on the machine. winget ships with Windows 10/11, so it is asked for the
        official yt-dlp package: nothing is installed into the yt-msd folder and
        nothing is installed through pip.
        """
        exe = find_yt_dlp_executable()
        version = get_yt_dlp_version(exe) if exe else ""
        if version:
            self.ytdlp_version_signal.emit(version)
            return

        self.status_signal.emit("yt-dlp not found - installing it with winget...", False, "#3B8ED0")
        rc, out, err = run_winget(["install", "--id", YTDLP_WINGET_ID, "-e",
                                   "--accept-package-agreements", "--accept-source-agreements",
                                   "--disable-interactivity"])
        exe = find_yt_dlp_executable(refresh=True)
        version = get_yt_dlp_version(exe) if exe else ""
        if version:
            self.ytdlp_version_signal.emit(version)
            self.status_signal.emit(f"yt-dlp {version} installed with winget.", False, "#1abd33")
            return

        lines = [line for line in (err or out or "").strip().splitlines() if line.strip()]
        self.ytdlp_missing_signal.emit(
            "yt-msd could not install yt-dlp automatically."
            + (f"<br><br>winget said: <code>{lines[-1]}</code>" if lines else "")
        )

    def _check_yt_dlp_updates(self):
        """Ask GitHub whether the yt-dlp on this system is behind, at most once per interval."""
        if getattr(self, 'disable_update_checks', False) or getattr(self, 'disable_ytdlp_updates', False):
            return
        if getattr(self, '_ytdlp_update_check_running', False):
            return
        last_check = float(getattr(self, 'ytdlp_last_update_check', 0.0) or 0.0)
        if last_check and (time.time() - last_check) < YTDLP_UPDATE_CHECK_INTERVAL:
            return
        self._ytdlp_update_check_running = True

        def _bg():
            try:
                installed = getattr(self, 'ytdlp_version', '') or get_yt_dlp_version()
                if not installed:
                    return
                self.ytdlp_version_signal.emit(installed)
                latest = latest_yt_dlp_release()
                # Remembered so the hourly rescan does not ask GitHub again for a week.
                self.ytdlp_last_update_check = time.time()
                if not latest:
                    return
                if _version_is_newer(_extract_version_number(latest), _extract_version_number(installed)):
                    self.ytdlp_update_signal.emit(installed, latest)
            except Exception:
                pass
            finally:
                self._ytdlp_update_check_running = False

        threading.Thread(target=_bg, daemon=True).start()

    def _show_ytdlp_missing_dialog(self, reason):
        """Explain how to get yt-dlp when it is missing and could not be installed."""
        msg = QMessageBox(self)
        msg.setWindowTitle("yt-dlp Not Installed - yt-msd")
        msg.setIcon(QMessageBox.Warning)
        msg.setTextFormat(Qt.RichText)
        msg.setText(
            "<h3>yt-dlp Is Not Installed</h3>"
            + reason
            + "<br><br>yt-msd drives yt-dlp as a separate program so it can be kept current "
            "without rebuilding yt-msd. Install it with:<br><br>"
            "<code>winget install --id yt-dlp.yt-dlp -e</code><br><br>"
            "If winget is unavailable, download <code>yt-dlp.exe</code> from "
            "<a href='https://github.com/yt-dlp/yt-dlp/releases/latest'>github.com/yt-dlp/yt-dlp</a> "
            "and put it in the yt-msd folder or anywhere on your PATH. Then restart yt-msd."
        )
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()

    def _show_ytdlp_update_dialog(self, installed, latest):
        """Show the yt-dlp update dialog on the GUI thread and act on the choice."""
        dlg = YtDlpUpdateDialog(self, installed, latest)
        choice = dlg.exec()
        if dlg.never_notify:
            self.disable_ytdlp_updates = True
            self.save_config()
        if choice == QDialog.Accepted:
            self.update_yt_dlp_now()

    def update_yt_dlp_now(self):
        """Update the yt-dlp installed on this system, in place, with winget.

        Used both by the yt-dlp update dialog and by the Settings dialog button. If
        winget does not manage this copy of yt-dlp (it was placed in the folder by
        hand, for example), it is installed properly instead, so the next update is
        an ordinary winget upgrade.
        """
        self.status_signal.emit("Updating yt-dlp with winget...", False, "#3B8ED0")

        def _bg():
            winget_args = ["--id", YTDLP_WINGET_ID, "-e",
                           "--accept-package-agreements", "--accept-source-agreements",
                           "--disable-interactivity"]
            rc, out, err = run_winget(["upgrade"] + winget_args)
            if rc is None:
                self.ytdlp_missing_signal.emit("winget is not available, so yt-msd cannot update yt-dlp for you.")
                return
            if rc != 0:
                rc, out, err = run_winget(["install"] + winget_args)
            exe = find_yt_dlp_executable(refresh=True)
            version = get_yt_dlp_version(exe) if exe else ""
            if version:
                self.ytdlp_version_signal.emit(version)
                self.status_signal.emit(f"yt-dlp is now at {version}.", False, "#1abd33")
                return
            lines = [line for line in (err or out or "").strip().splitlines() if line.strip()]
            detail = lines[-1] if lines else "winget could not complete the update."
            self.status_signal.emit(f"yt-dlp update failed: {detail}", False, "#E31E24")

        threading.Thread(target=_bg, daemon=True).start()

    def _apply_ytdlp_version(self, version):
        """Store a yt-dlp version found in a background thread, and show it in Settings."""
        if not version:
            return
        self.ytdlp_version = version
        settings_dialog = getattr(self, 'settings_dialog', None)
        if settings_dialog is not None and hasattr(settings_dialog, 'set_ytdlp_version'):
            settings_dialog.set_ytdlp_version(version)

    def refresh_yt_dlp_version(self):
        """Look for yt-dlp again on a worker thread (the Settings dialog asks for it)."""
        def _bg():
            exe = find_yt_dlp_executable(refresh=True)
            version = get_yt_dlp_version(exe) if exe else ""
            if version:
                self.ytdlp_version_signal.emit(version)
            else:
                self.ytdlp_missing_signal.emit("No yt-dlp was found on this system.")
        threading.Thread(target=_bg, daemon=True).start()

    def _init_vlc_background(self):
        """Initialize libVLC in a background thread to avoid blocking the UI during plugin scanning.
        The startup dependency check rides along here: it reuses this libvlc instance instead of
        creating a second one, and it never touches the UI thread."""
        vlc_error = ""
        if not _VLC_MODULE_AVAILABLE or vlc is None:
            self.vlc_instance = None
            self.vlc_player = None
            self._vlc_ready = True
            vlc_error = getattr(sys.modules[__name__], '_VLC_IMPORT_ERROR', 'python-vlc not available')
        else:
            try:
                instance = vlc.Instance('--quiet', '--no-video')
                player = instance.media_player_new() if instance else None
                # Switch to main-thread ownership safely
                self.vlc_instance = instance
                self.vlc_player = player
                if self.vlc_player:
                    self.vlc_player.audio_set_volume(self.volume_val)
                self._vlc_ready = True
                if player is None:
                    vlc_error = "libvlc.dll not found."
            except Exception as e:
                self.vlc_instance = None
                self.vlc_player = None
                self._vlc_ready = True  # Still mark ready so playback attempts don't hang
                vlc_error = str(e)

        missing = []
        if vlc_error:
            missing.append(
                "• <b>VLC Media Player (libvlc.dll)</b><br>"
                "Audio playback requires VLC Media Player (64-bit).<br>"
                "Please download and install 64-bit VLC from: <a href='https://www.videolan.org/vlc/'>https://www.videolan.org/vlc/</a>"
            )
        if not check_ffmpeg_available():
            missing.append(
                "• <b>FFmpeg (ffmpeg.exe)</b><br>"
                "Audio extraction, conversion, and loudness normalization require FFmpeg.<br>"
                "Please install FFmpeg and make sure <code>ffmpeg.exe</code> is in your system PATH or placed in the application folder."
            )
        if missing:
            self.missing_deps_signal.emit("<br><br>".join(missing))


    def load_config(self):
        default_dl = os.path.join(os.path.expanduser("~"), "Downloads")
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    c = json.load(f)
                    self.format_var = c.get('format', DEFAULT_DOWNLOAD_FORMAT)
                    # A format that is no longer offered must not survive in a config
                    # written by an older version. aac, flac and wav were all dropped
                    # because the tagger cannot write artist/title into any of them, and
                    # setCurrentText with a value the combo does not contain leaves the
                    # combo showing the default while format_var still holds the dead
                    # name - the next download would then go out with an --audio-format
                    # the app no longer supports. Fall back to the default instead.
                    if self.format_var not in DOWNLOAD_FORMATS:
                        self.format_var = DEFAULT_DOWNLOAD_FORMAT
                    self.bitrate_var = c.get('bitrate', '192')
                    self.recent_folders = c.get('folders', [default_dl])
                    self.download_path = self.recent_folders[0] if self.recent_folders else default_dl
                    self.accent_color_name = c.get('accent', 'System')
                    self.appearance_mode = c.get('mode', 'Dark')
                    self.volume_val = c.get('volume', 100)
                    self.local_folders = c.get('local_folders', [])
                    self.local_current_path = c.get('local_current_path', "")
                    self.show_local_metadata = c.get('show_local_metadata', False)
                    self.minimize_to_tray = c.get('minimize_to_tray', False)
                    self.recent_playlists = c.get('recent_playlists', [])
                    self.splitter_sizes = c.get('splitter_sizes', [300, 800, 300])
                    self.host_window_geometry = c.get('host_window_geometry', '')
                    self.use_custom_args = c.get('use_custom_args', False)
                    self.custom_args = c.get('custom_args', '')
                    self.appearance_mode = c.get('mode', 'Dark')
                    self.last_search = c.get('last_search', '')
                    self.save_place = c.get('save_place', False)
                    self.run_renamer = c.get('run_renamer', False)
                    self.renamer_path = c.get('renamer_path', '')
                    self.run_custom_script = c.get('run_custom_script', False)
                    self.custom_script_path = c.get('custom_script_path', '')
                    self.normalization_mode = c.get('normalization_mode', 'ask')
                    self.auto_rename = c.get('auto_rename', False)
                    self.silence_pad_dur = c.get('silence_pad_dur', 2.0)
                    self.silence_trim = bool(c.get('silence_trim', True))
                    self.use_custom_norm_cmd = c.get('use_custom_norm_cmd', False)
                    self.custom_norm_cmd = c.get('custom_norm_cmd', '')
                    self.download_threads = c.get('download_threads', 3)
                    self.normalization_threads = c.get('normalization_threads', max(1, os.cpu_count() // 2))
                    self.local_rescan_interval = c.get('local_rescan_interval', 60)
                    self.disable_update_checks = c.get('disable_update_checks', False)
                    self.disable_ytdlp_updates = c.get('disable_ytdlp_updates', False)
                    self.ytdlp_last_update_check = float(c.get('ytdlp_last_update_check', 0.0) or 0.0)
                    # "Stop after current" is the one playback choice that outlives the window it was
                    # made in, and only when it is "always": that state is a standing instruction the
                    # user takes back himself by clicking the button again, so a window coming back
                    # with it off would have him re-arming it before every track. "once" is not a
                    # preference at all but a promise about one track - the one that was playing when
                    # it was armed - and that track is not part of the new session, so an armed "once"
                    # left in the file is spent here instead of being kept to stop the first track the
                    # user starts after launch. The marker naming the track a search armed it for
                    # belongs to that dropped promise and goes with it; a restored "always" is the
                    # user's own choice, so nothing is armed for it. A value that is none of the three
                    # states - a hand-edit gone wrong, a number written by a future version - falls
                    # back to off the way a format the app no longer offers does.
                    persisted_stop_after = c.get('stop_after_current', STOP_AFTER_OFF)
                    try:
                        persisted_stop_after = int(persisted_stop_after)
                    except (TypeError, ValueError):
                        persisted_stop_after = STOP_AFTER_OFF
                    if persisted_stop_after not in (STOP_AFTER_OFF, STOP_AFTER_ONCE, STOP_AFTER_ALWAYS):
                        persisted_stop_after = STOP_AFTER_OFF
                    if persisted_stop_after == STOP_AFTER_ONCE:
                        persisted_stop_after = STOP_AFTER_OFF
                    self.stop_after_current = persisted_stop_after
                    self._search_stop_after_track = None
                    if hasattr(self, 'local_rescan_timer'):
                        self._update_local_rescan_timer()
                    if self.save_place:
                        self.session_data = c.get('session_data', {})
        except Exception: pass
        if not self.recent_folders:
            self.recent_folders = [default_dl]; self.download_path = default_dl

    def save_config(self):
        # Merge into the existing file instead of overwriting it, so keys owned by
        # other subsystems (hosted_chains / client_chains / sync_settings written by
        # SyncConfigManager.save) are preserved. The whole read-modify-write runs
        # under a shared lock so it never interleaves with SyncConfigManager.save().
        with _CONFIG_WRITE_LOCK:
            c = {}
            try:
                if os.path.exists(self.config_path):
                    with open(self.config_path, 'r') as f:
                        c = json.load(f)
            except Exception:
                c = {}
            c.update({
            'format': self.format_combo.currentText(),
            'bitrate': self.bitrate_combo.currentText(),
            'mode': self.appearance_mode,
            'accent': self.accent_color_name,
            'folders': self.recent_folders,
            'local_folders': self.local_folders,
            'local_current_path': self.local_current_path,
            'volume': self.volume_val,
            'show_local_metadata': getattr(self, 'show_local_metadata', False),
            'minimize_to_tray': self.minimize_to_tray,
            'use_custom_args': self.use_custom_args,
            'custom_args': self.custom_args,
            'recent_playlists': self.recent_playlists,
            'splitter_sizes': [self.main_splitter.sizes()[0]] + self.content_splitter.sizes() if hasattr(self, 'main_splitter') else self.splitter_sizes,
            'last_search': self.search_entry.text() if hasattr(self, 'search_entry') else self.last_search,
            'save_place': self.save_place,
            'run_renamer': self.run_renamer_cb.isChecked() if hasattr(self, 'run_renamer_cb') else self.run_renamer,
            'renamer_path': getattr(self, 'renamer_path', ''),
            'run_custom_script': getattr(self, 'run_custom_script', False),
            'custom_script_path': getattr(self, 'custom_script_path', ''),
            'normalization_mode': self.normalization_mode,
            'auto_rename': self.auto_rename,
            'silence_pad_dur': self.silence_pad_dur,
            'silence_trim': self.silence_trim,
            'use_custom_norm_cmd': self.use_custom_norm_cmd,
            'custom_norm_cmd': self.custom_norm_cmd,
            'download_threads': self.download_threads,
            'normalization_threads': self.normalization_threads,
            'local_rescan_interval': getattr(self, 'local_rescan_interval', 60),
            'disable_update_checks': getattr(self, 'disable_update_checks', False),
            'disable_ytdlp_updates': getattr(self, 'disable_ytdlp_updates', False),
            'ytdlp_last_update_check': getattr(self, 'ytdlp_last_update_check', 0.0),
            # The state as it stands when the window closes. "always" is read straight back by
            # load_config(); a "once" that was still armed is spent on the way in rather than
            # carried into a session where the track it was armed for no longer exists.
            'stop_after_current': getattr(self, 'stop_after_current', STOP_AFTER_OFF),
            'session_data': {
                'search_results': self.search_results,
                'playback_index': self.playback_index,
                'current_video_id': self.current_video_id,
                'local_current_path': self.local_current_path,
                'local_playback_index': getattr(self, 'local_playback_index', -1)
            }
            })
            if getattr(self, 'launched_by_host', False):
                # Only a window opened from MusicBee keeps its own size; a normal
                # launch still opens at its fixed default. Leaving the key out here
                # means the read-modify-write above does not clear a saved value.
                try:
                    c['host_window_geometry'] = bytes(self.saveGeometry().toBase64()).decode('ascii')
                except Exception:
                    pass
            try:
                with open(self.config_path, 'w') as f: json.dump(c, f, indent=4)
            except: pass

    def _apply_host_window_geometry(self):
        # Opened from MusicBee: come back at the size and place it was closed at,
        # or at the compact default if this is the first time. restoreGeometry is
        # given exactly what saveGeometry wrote, base64-encoded for the JSON file.
        if not getattr(self, 'launched_by_host', False) or not self.host_window_geometry:
            return
        try:
            geometry = QByteArray.fromBase64(self.host_window_geometry.encode('ascii'))
            if geometry.isEmpty():
                return
            self.restoreGeometry(geometry)
            # A size remembered on a monitor that has since been unplugged would come
            # back off-screen and impossible to grab, so a window that lands outside
            # every screen falls back to the compact default, centred.
            desktop = QApplication.primaryScreen().virtualGeometry()
            if not self.geometry().intersects(desktop):
                available = QApplication.primaryScreen().availableGeometry()
                self.resize(1100, 700)
                centre = available.center()
                self.move(centre.x() - 550, centre.y() - 350)
        except Exception:
            pass

    def setup_tray(self):
        self.tray_popup = TrayProgressPopup()
        self.tray_click_timer = QTimer(self)
        self.tray_click_timer.setSingleShot(True)
        self.tray_click_timer.setInterval(250)
        self.tray_click_timer.timeout.connect(self._show_tray_progress_popup)

        self.tray_icon = QSystemTrayIcon(self)
        
        # The program icon, or the drawn circle if icon-256x256.ico is not available
        tray_qicon = app_icon()
        if tray_qicon is None:
            pixmap = QPixmap(64, 64)
            pixmap.fill(QColor("transparent"))
            painter = QPainter(pixmap)
            painter.setBrush(QColor(get_accent_color(self.accent_color_name)))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(8, 8, 48, 48)
            painter.end()
            tray_qicon = QIcon(pixmap)
        self.tray_icon.setIcon(tray_qicon)
        self.tray_icon.setToolTip("yt-msd")
        
        self.tray_menu = QMenu(self)
        self.tray_menu.aboutToShow.connect(self._build_tray_menu)
        self._build_tray_menu()
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()

    def _truncate_title(self, title: str, max_chars: int = 24) -> str:
        title = title.strip()
        if len(title) > max_chars:
            return title[:max_chars - 3].rstrip() + "..."
        return title

    def _build_tray_menu(self):
        self.tray_menu.clear()
        
        # Current song header (compact, truncated title)
        title = getattr(self, 'current_playing_title', '').strip()
        time_txt = self.time_label.text().strip() if hasattr(self, 'time_label') else ""
        if title:
            trunc_t = self._truncate_title(title, 24)
            if time_txt and time_txt != "0:00 / 0:00":
                header_text = f"{trunc_t} | {time_txt}"
            else:
                header_text = trunc_t
        else:
            header_text = "No Track Playing"
        
        self.tray_header_action = self.tray_menu.addAction(header_text)
        self.tray_header_action.setEnabled(False)
        self.tray_menu.addSeparator()

        # Play / Pause Action. A track left finished on the player is neither playing nor paused,
        # and the only press that does anything with it starts it again - which is what this entry
        # says, and what the button on the player bar shows (see _update_play_button).
        is_playing = getattr(self, 'is_playing', False)
        if getattr(self, '_finished_track', False):
            play_label = "Replay Track"
        else:
            play_label = "Pause" if is_playing else "Play"
        play_action = self.tray_menu.addAction(play_label)
        play_action.triggered.connect(self.toggle_playback)

        # Prev / Next Track Actions
        prev_action = self.tray_menu.addAction("Previous Track")
        prev_action.triggered.connect(self.play_previous)
        next_action = self.tray_menu.addAction("Next Track")
        next_action.triggered.connect(self.play_next)

        # Stop After Current - the same control as the player-bar button: one entry,
        # three states, one click each (off -> once -> always -> off). The menu is
        # rebuilt every time it opens, so the label and the tick always match.
        stop_mode = getattr(self, 'stop_after_current', STOP_AFTER_OFF)
        stop_act = self.tray_menu.addAction(f"Stop After Current ({STOP_AFTER_LABELS[stop_mode]})")
        stop_act.setCheckable(True)
        stop_act.setChecked(stop_mode != STOP_AFTER_OFF)
        stop_act.setToolTip(STOP_AFTER_TOOLTIPS[stop_mode])
        stop_act.triggered.connect(lambda checked=False: self.cycle_stop_after_current())

        self.tray_menu.addSeparator()

        # Volume Controls Submenu
        vol_menu = self.tray_menu.addMenu(f"Volume ({self.volume_val}%)")
        
        vol_up = vol_menu.addAction("Volume Up (+10%)")
        vol_up.triggered.connect(lambda: self._set_tray_volume(self.volume_val + 10))
        
        vol_down = vol_menu.addAction("Volume Down (-10%)")
        vol_down.triggered.connect(lambda: self._set_tray_volume(self.volume_val - 10))
        
        mute_act = vol_menu.addAction("Mute (0%)")
        mute_act.triggered.connect(lambda: self._set_tray_volume(0))
        
        vol_menu.addSeparator()
        for p in [25, 50, 75, 100, 125, 150]:
            p_act = vol_menu.addAction(f"{p}%")
            if self.volume_val == p:
                p_act.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))
            p_act.triggered.connect(lambda checked=False, val=p: self._set_tray_volume(val))

        self.tray_menu.addSeparator()
        
        restore_action = self.tray_menu.addAction("Restore Window")
        restore_action.triggered.connect(self._restore_from_tray)
        
        exit_action = self.tray_menu.addAction("Exit")
        exit_action.triggered.connect(self.close)

    def _set_tray_volume(self, val: int):
        clamped = max(0, min(150, val))
        if hasattr(self, 'vol_slider'):
            self.vol_slider.setValue(clamped)
        else:
            self.on_volume_changed(clamped)

    def _restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _show_tray_progress_popup(self):
        title = getattr(self, 'current_playing_title', '').strip()
        time_txt = self.time_label.text().strip() if hasattr(self, 'time_label') else ""
        if hasattr(self, 'tray_popup') and self.tray_popup:
            self.tray_popup.show_track_info(title, time_txt)

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            if hasattr(self, 'tray_click_timer'):
                self.tray_click_timer.stop()
            if hasattr(self, 'tray_popup') and self.tray_popup and self.tray_popup.isVisible():
                self.tray_popup.hide()
            self._restore_from_tray()
        elif reason == QSystemTrayIcon.Trigger:
            if hasattr(self, 'tray_click_timer'):
                self.tray_click_timer.start()

    def changeEvent(self, event):
        if event.type() == event.Type.WindowStateChange:
            if self.isMinimized() and self.minimize_to_tray:
                self.hide()
        super().changeEvent(event)

    def request_attention(self):
        """Come forward because a second copy of yt-msd was started.

        The second copy exits itself (see ask_running_instance_to_show); this is
        the answer it asked for, and it is the only thing that happens.
        """
        try:
            if not self.isVisible():
                self.show()
            if self.isMinimized():
                self.showNormal()
            self.raise_()
            self.activateWindow()
            self._on_status_update("yt-msd is already running - this is that window.",
                                   False, "white")
        except Exception:
            pass

    def closeEvent(self, event):
        """Save settings, stop the background work, and end the Qt event loop.

        The process itself is exited by the entry block at the bottom of this
        file. Ending it here instead - os._exit() called from inside a Qt
        virtual override - tears the process down while shiboken is still
        unwinding the close event and while the sync, folder-watcher and
        subprocess threads are mid-call. That faults in shiboken6.abi3.dll, and
        the window and its Task Manager entry then stay where they are for the
        seconds Windows Error Reporting takes to write the crash dump.
        """
        self.shutdown_for_exit()
        event.accept()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def shutdown_for_exit(self):
        """One-shot shutdown, ordered so that nothing reaches this window again
        once it is on its way out. Safe to call twice."""
        if getattr(self, '_shutdown_done', False):
            return
        self._shutdown_done = True

        # A dialog raised on the way out would hold the process open until someone
        # dismissed it, so from here a failure is written to yt-msd-crash.log and not
        # shown. silence_crash_dialogs() stops only the dialogs.
        silence_crash_dialogs()

        # A background thread that is still working when this window goes away
        # reaches for a signal on an object Qt has already deleted. The hard
        # exit used to cut those threads off before they could say so; now the
        # interpreter outlives them long enough to print a traceback for each.
        # That one race is quieted below; nothing else is.
        previous_thread_excepthook = threading.excepthook

        def _thread_excepthook(args):
            # Only the one race Qt can lose here, and only as a RuntimeError:
            # shiboken's "Internal C++ object ... already deleted" and Qt's own
            # "Signal source has been deleted". Anything else a thread raises
            # still reports itself, as it did before.
            if args.exc_type is RuntimeError:
                text = str(args.exc_value)
                if 'has been deleted' in text or 'already deleted' in text:
                    return
            try:
                previous_thread_excepthook(args)
            except Exception:
                pass

        threading.excepthook = _thread_excepthook

        try:
            self.save_config()
        except Exception:
            pass

        try:
            if hasattr(self, 'sync_config_manager') and self.sync_config_manager:
                self.sync_config_manager.save()
        except Exception:
            pass

        # Timers first: the 16 ms player tick is the likeliest thing to still
        # reach the window after this point.
        for timer_name in ('player_timer', 'wifi_monitor_timer', 'drive_monitor_timer',
                           'local_rescan_timer', 'sync_timer', 'tray_click_timer'):
            timer = getattr(self, timer_name, None)
            if timer is not None:
                try:
                    timer.stop()
                except Exception:
                    pass

        # Sync workers: ask them to stop and give each a moment, so they are not
        # emitting signals into a window that is going away.
        for thread in list(getattr(self, 'sync_threads', {}).values()):
            try:
                thread.requestInterruption()
                thread.quit()
                thread.wait(1000)
            except Exception:
                pass

        # The LAN services: their threads call back into this window.
        for service_name in ('udp_beacon', 'sync_host_server'):
            service = getattr(self, service_name, None)
            if service is not None:
                try:
                    service.stop()
                except Exception:
                    pass

        # The folder watchers are stopped off the UI thread. Each observer is
        # bounded - remove_chain() joins it with a 0.3 s timeout - but a chain
        # whose handler is mid-callback still holds the stop up, and this window
        # should not wait for that. Measured here: 30+ seconds.
        try:
            if getattr(self, 'host_watcher', None) is not None:
                threading.Thread(target=self.host_watcher.stop_all, daemon=True).start()
        except Exception:
            pass

        try:
            if getattr(self, 'vlc_player', None) is not None:
                self.vlc_player.stop()
        except Exception:
            pass

        # This window installed itself as an application-wide event filter (the
        # Space key shortcut); nothing should reach it after this point.
        try:
            app = QApplication.instance()
            if app is not None:
                app.removeEventFilter(self)
        except Exception:
            pass

        try:
            if hasattr(self, 'tray_popup') and self.tray_popup:
                self.tray_popup.hide()
        except Exception:
            pass

        try:
            if hasattr(self, 'tray_icon') and self.tray_icon:
                self.tray_icon.hide()
        except Exception:
            pass

    def reset_to_defaults(self):
        if os.path.exists(self.config_path):
            try: os.remove(self.config_path)
            except: pass
        
        # Reset variables
        self.appearance_mode = "Dark"
        self.accent_color_name = "Blue"
        self.volume_val = 100
        self.save_place = False
        self.use_custom_args = False
        self.custom_args = ""
        self.last_search = ""
        self.minimize_to_tray = False
        self.run_renamer = False
        self.renamer_path = ""
        self.run_custom_script = False
        self.custom_script_path = ""
        self._last_downloaded_files = []
        self.normalization_mode = "ask"
        self.auto_rename = False
        self.silence_pad_dur = 2.0
        self.silence_trim = True
        self.use_custom_norm_cmd = False
        self.custom_norm_cmd = ""
        self.disable_update_checks = False
        self.disable_ytdlp_updates = False
        # These two opt-outs live on MainApp only, never in the settings list save_config() writes
        # from scratch, so without this they survived a "factory reset": save_config() writes
        # whatever the attributes hold and load_config() reads it back on the next launch, so the
        # user stayed opted out of app-update and yt-dlp-update prompts through a reset that claimed
        # to put everything back to default.
        TUNING.reset()
        # The renamer half is a second copy of this program launched in a console, and it reads
        # the tuning settings above rather than the MainApp attributes. Resetting only the
        # attributes left every renamer this window launched running with the pre-reset trim /
        # pad / override until the app was restarted. load_config() and _apply_imported_config()
        # push the settings for the same reason; a reset has to do it too.
        self.download_threads = 3
        self.normalization_threads = max(1, os.cpu_count() // 2)
        self.local_rescan_interval = 60
        # Everything else gui_config.json stores. The file is deleted at the top of this method, but
        # save_config() at the bottom writes a fresh one out of whatever these attributes and widgets
        # hold, so anything not cleared here was straight back in the file the reset had just removed.
        # These are the parts a user would call "my recent data": the download folders and the
        # destination the top bar shows, the local folders and the folder open in the tree pane, the
        # playlist history, the format and bitrate the two top-bar combos are set to, the metadata tick
        # on the local pane, and the window geometry kept for MusicBee launches. session_data needs
        # nothing: save_config() rebuilds it from the live window on every save, and load_config() only
        # reads it back when "save place" is on, which this reset turns off. ytdlp_last_update_check is
        # cleared as well so the next launch behaves like a first run and looks for a newer yt-dlp
        # instead of trusting a timestamp left over from before the reset.
        default_dl = os.path.join(os.path.expanduser("~"), "Downloads")
        self.format_var = "mp3"
        self.bitrate_var = "192"
        self.recent_folders = [default_dl]
        self.download_path = default_dl
        self.local_folders = []
        self.local_current_path = ""
        self.recent_playlists = []
        self.show_local_metadata = False
        self.host_window_geometry = ""
        self.ytdlp_last_update_check = 0.0
        # "Stop after current" is now in the list save_config() writes, so leaving the attribute as
        # it was would have put an "always" straight back into the file this reset had just removed -
        # the same way the two update opt-outs survived the reset before they were cleared here. The
        # search arming goes with it, and apply_theme() below repaints the button through
        # _update_stop_after_ui().
        self.stop_after_current = STOP_AFTER_OFF
        self._search_stop_after_track = None
        # ...and the widgets that display those values, because save_config() reads the format, the
        # bitrate and the download folder straight off them. Left where they were, they would put the
        # old values back into the new file on the next save. Signals are blocked so no handler runs
        # against a value that has already been changed underneath it.
        if hasattr(self, 'format_combo'):
            self.format_combo.blockSignals(True)
            self.format_combo.setCurrentText(self.format_var)
            self.format_combo.blockSignals(False)
        if hasattr(self, 'bitrate_combo'):
            self.bitrate_combo.blockSignals(True)
            self.bitrate_combo.setCurrentText(self.bitrate_var)
            self.bitrate_combo.blockSignals(False)
        if hasattr(self, 'path_combo'):
            self.path_combo.blockSignals(True)
            self.path_combo.clear()
            self.path_combo.addItems([str(folder) for folder in self.recent_folders])
            self.path_combo.setCurrentText(self.download_path)
            self.path_combo.blockSignals(False)
        if hasattr(self, 'local_meta_cb'):
            self.local_meta_cb.blockSignals(True)
            self.local_meta_cb.setChecked(False)
            self.local_meta_cb.blockSignals(False)
        if hasattr(self, 'local_path_combo'):
            # Rebuilds the address bar from the now-empty recent list without firing
            # load_local_folder, which would try to scan a folder this reset has just forgotten.
            self.set_local_explorer_address("")
        # local_current_path is empty, so the scan returns None and the pane is cleared instead of
        # continuing to list the files of a folder that is no longer set anywhere.
        self.refresh_local_list()
        if hasattr(self, 'local_rescan_timer'):
            self._update_local_rescan_timer()
        if hasattr(self, 'run_renamer_cb'):
            self.run_renamer_cb.blockSignals(True)
            self.run_renamer_cb.setChecked(False)
            self.run_renamer_cb.blockSignals(False)
        self.splitter_sizes = [300, 800, 300]
        
        # Apply changes
        self.apply_theme()
        # The old form of this read self.splitter, which MainApp never creates: the two real
        # splitters are main_splitter (local pane | everything else) and content_splitter
        # (results | queue), and save_config() stores three sizes by reading both of them. The
        # hasattr() was therefore always false, so the panel widths survived the reset and were
        # written straight back into the new file. Same split the startup code applies.
        if hasattr(self, 'main_splitter') and hasattr(self, 'content_splitter'):
            self.main_splitter.setSizes([self.splitter_sizes[0], self.splitter_sizes[1] + self.splitter_sizes[2]])
            self.content_splitter.setSizes([self.splitter_sizes[1], self.splitter_sizes[2]])
            # Clear what each splitter kept as the user's own arrangement, or the next double-click
            # on a handle restores the pre-reset widths instead of the default pair.
            for splitter in (self.main_splitter, self.content_splitter):
                splitter._last_custom_sizes = []
        if hasattr(self, 'vol_slider'):
            self.vol_slider.setValue(100)
        # The Settings dialog is cached on MainApp and reused, and it reads the MainApp attributes
        # only when it is first built. Resetting without dropping it left the very dialog the user
        # just clicked "reset" in showing the old tick marks and the old pad value - and the next
        # toggle would have written those stale values straight back. _apply_imported_config()
        # throws the cached dialog away for the same reason; do the same here. The caller closes
        # this dialog right after the reset, so closing it from here is safe.
        settings_dialog = getattr(self, 'settings_dialog', None)
        if settings_dialog is not None:
            try:
                settings_dialog.close()
            except Exception:
                pass
            self.settings_dialog = None
        # Sync chains and sync settings live in the same file this method deletes, but
        # SyncConfigManager holds live copies of all three - hosted_chains, client_chains and
        # settings - and the Sync dialog, the export dialog and the removable-drive path all read
        # that manager rather than the file. Clearing only the file therefore left every chain in
        # memory, and the next save() - on close, or from any chain operation - wrote them back into
        # a brand-new file, so no chain was ever actually removed. That write-back is worth keeping
        # for the case where the file is deleted by hand while the app is running: the manager still
        # re-creates it on exit. It must not survive an explicit reset, so the manager is emptied
        # here too.
        # A mirror sync works on the drive it is copying to for its whole run. Stopping the chains
        # first while one is mid-flight would leave it adding and deleting files against a chain
        # definition that no longer exists, so the threads are asked to stop before the chains go.
        for thread in list(getattr(self, 'sync_threads', {}).values()):
            try:
                thread.requestInterruption()
                thread.quit()
                thread.wait(1000)
            except Exception:
                pass
        sync_threads = getattr(self, 'sync_threads', None)
        if sync_threads is not None:
            sync_threads.clear()  # in place again: SyncManagerDialog aliases this same dict
        # The per-chain "Syncing... / [3/40] (7%)" lines the cards show are keyed by chain id.
        # Left behind they describe chains this reset has just removed, and a card for a new chain
        # with the same sync code would inherit the old progress text.
        progress_state = getattr(self, 'sync_progress_state', None)
        if progress_state is not None:
            progress_state.clear()
        sync_manager = getattr(self, 'sync_config_manager', None)
        if sync_manager is not None:
            # Emptied in place. The open Sync dialog keeps references to these very objects, so
            # rebinding them to new lists would leave that window showing chains that are gone.
            sync_manager.hosted_chains.clear()
            sync_manager.client_chains.clear()
            sync_manager.settings.clear()
            sync_manager.settings.update(DEFAULT_SYNC_SETTINGS)
        watcher = getattr(self, 'host_watcher', None)
        if watcher is not None:
            try:
                watcher.stop_all()
            except Exception:
                pass
        if hasattr(self, 'sync_timer'):
            # Re-arms the client auto-sync timer on the default interval. With no client chains the
            # callback returns immediately, but it should not keep running on an interval the user
            # picked before the reset.
            self._update_sync_timer()
        sync_dialog = getattr(self, 'sync_manager_dialog', None)
        if sync_dialog is not None:
            try:
                sync_dialog.refresh_cards(force=True)
            except Exception:
                pass
        self.save_config()
        self._on_status_update("Settings, recent data and sync chains reset to defaults.", False, "#3B8ED0")

    # ── EXPORT / IMPORT PACKAGES ──────────────────────────────────────────────
    def start_export(self, options: dict):
        """Build the .zip package on a worker thread: copying music or reading a
        config off a slow drive must never block the window."""
        if self._export_import_busy:
            self._on_status_update("Please wait: an import or export is already running.", False, "#d9822b")
            return
        self._export_import_busy = True
        threading.Thread(target=self._export_worker, args=(dict(options),), daemon=True).start()
        self._on_status_update("Exporting package...", False, "#3B8ED0")

    def _export_worker(self, options: dict):
        zip_path = str(options.get('zip_path') or "")
        include_config = bool(options.get('include_config'))
        include_chains = bool(options.get('include_chains'))
        include_music = bool(options.get('include_music'))
        file_count = 0
        try:
            if not zip_path:
                raise ValueError("no destination file was chosen")
            parent_dir = os.path.dirname(os.path.abspath(zip_path))
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)

            # Read the config under the shared lock: MainApp.save_config and
            # SyncConfigManager.save both write this file.
            with _CONFIG_WRITE_LOCK:
                current_config = {}
                if os.path.exists(self.config_path):
                    with open(self.config_path, 'r', encoding='utf-8') as config_file:
                        current_config = json.load(config_file)

            sync_payload: dict = {}
            if include_chains:
                manager = self.sync_config_manager
                sync_payload = {
                    'sync_settings': dict(manager.settings),
                    'hosted_chains': [dict(chain) for chain in manager.hosted_chains],
                    'client_chains': [dict(chain) for chain in manager.client_chains],
                }

            exported_config = build_exported_config(current_config, include_config, include_chains, sync_payload)
            music_entries: List[dict] = []

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(EXPORT_CONFIG_ENTRY, json.dumps(exported_config, indent=4))
                file_count += 1
                if include_chains:
                    archive.writestr(EXPORT_SYNC_ENTRY, json.dumps(sync_payload, indent=4))
                    file_count += 1
                if include_music:
                    used_names: set = set()
                    for entry in options.get('music_folders') or []:
                        folder = str((entry or {}).get('path') or "").strip()
                        if not folder or not os.path.isdir(folder):
                            continue
                        archive_path, folder_name = unique_music_archive_name(folder, used_names)
                        self.status_signal.emit(f"Exporting music: {folder_name}...", False, "#3B8ED0")
                        with_subfolders = bool((entry or {}).get('subfolders'))
                        written = zip_folder_into(archive, folder, archive_path, with_subfolders)
                        music_entries.append({
                            'name': folder_name,
                            'archive_path': archive_path,
                            'source_path': os.path.abspath(folder),
                            'subfolders': with_subfolders,
                            'files': written,
                        })
                        file_count += written
                archive.writestr(EXPORT_MANIFEST_NAME, build_export_manifest_text(
                    include_config, include_chains, include_music, music_entries))
        except Exception as exc:
            self._export_import_busy = False
            self.status_signal.emit(f"Export failed: {exc}", False, "#d9822b")
            return

        self._export_import_busy = False
        self.status_signal.emit(f"Exported {file_count} files to {zip_path}", False, "#1abd33")

    def open_import_dialog(self):
        """Pick a .zip export package; everything else follows export.yaml."""
        if self._export_import_busy:
            self._on_status_update("Please wait: an import or export is already running.", False, "#d9822b")
            return
        start_dir = getattr(self, 'download_path', '') or os.path.expanduser("~")
        zip_path, _ = QFileDialog.getOpenFileName(self, "Import yt-msd Package", start_dir,
                                                  "yt-msd Package (*.zip);;All Files (*)")
        if not zip_path:
            return
        self._export_import_busy = True
        self._on_status_update("Importing package...", False, "#3B8ED0")
        threading.Thread(target=self._import_worker, args=(zip_path,), daemon=True).start()

    def _import_worker(self, zip_path: str):
        """Read the manifest and unpack any music off the GUI thread."""
        try:
            package = read_import_package(zip_path)
        except Exception as exc:
            self.import_failed_signal.emit(f"Could not read {os.path.basename(zip_path)}: {exc}")
            return

        manifest = package.get('manifest') if isinstance(package.get('manifest'), dict) else {}
        includes = manifest.get('includes') if isinstance(manifest.get('includes'), dict) else {}
        music_results: List[dict] = []
        try:
            if includes.get('music'):
                with zipfile.ZipFile(zip_path, 'r') as archive:
                    music_results = extract_package_music(
                        archive, manifest,
                        status_cb=lambda text: self.status_signal.emit(text, False, "#3B8ED0"))
        except Exception as exc:
            self.import_failed_signal.emit(f"Import failed while unpacking: {exc}")
            return

        self.import_finished_signal.emit({
            'config': package.get('config') if includes.get('config') else None,
            'sync': package.get('sync') if includes.get('sync_chains') else None,
            'music': music_results,
        })

    def _on_import_failed(self, message: str):
        self._export_import_busy = False
        self._on_status_update(message, False, "#d9822b")

    def _apply_import_results(self, plan: dict):
        """Restore an imported package on the GUI thread: settings, chains, music."""
        plan = plan if isinstance(plan, dict) else {}
        summary: List[str] = []

        config_payload = plan.get('config')
        needs_local_rescan = False
        if isinstance(config_payload, dict) and config_payload:
            needs_local_rescan = bool(self._apply_imported_config(config_payload))
            summary.append("settings")

        sync_payload = plan.get('sync')
        if isinstance(sync_payload, dict) and sync_payload:
            hosted_count, client_count = self._apply_imported_sync_chains(sync_payload)
            summary.append(f"{hosted_count} hosted / {client_count} client chains")

        music_results = [result for result in (plan.get('music') or []) if isinstance(result, dict)]
        if music_results:
            restored_files = sum(int(result.get('files') or 0) for result in music_results)
            summary.append(f"{restored_files} music files")
            for result in music_results:
                if result.get('error'):
                    self._on_status_update(f"Could not fully restore {result.get('name')}: {result['error']}",
                                           False, "#d9822b")

        # Refresh the local list last: files restored by this same import have to
        # be on disk before the folder is scanned. The scan itself runs on a
        # worker thread, not here.
        if needs_local_rescan:
            self.local_list_refresh_signal.emit()

        self._export_import_busy = False
        if summary:
            self._on_status_update("Imported package: " + ", ".join(summary), False, "#1abd33")
        else:
            self._on_status_update("Imported package: nothing in it to restore.", False, "#d9822b")

    def _apply_imported_sync_chains(self, payload: dict) -> Tuple[int, int]:
        """Add imported chains, skipping any chain this machine already has."""
        manager = self.sync_config_manager
        settings = payload.get('sync_settings')
        if isinstance(settings, dict) and settings:
            merged = dict(manager.settings)
            merged.update(settings)
            manager.settings = merged

        hosted_ids = {str(chain.get('id')) for chain in manager.hosted_chains}
        hosted_codes = {str(chain.get('sync_code')) for chain in manager.hosted_chains}
        client_ids = {str(chain.get('id')) for chain in manager.client_chains}
        client_codes = {str(chain.get('sync_code')) for chain in manager.client_chains}
        added_hosted = 0
        added_clients = 0

        for chain in payload.get('hosted_chains') or []:
            if not isinstance(chain, dict):
                continue
            if str(chain.get('id')) in hosted_ids or str(chain.get('sync_code')) in hosted_codes:
                continue
            manager.hosted_chains.append(dict(chain))
            hosted_ids.add(str(chain.get('id')))
            hosted_codes.add(str(chain.get('sync_code')))
            added_hosted += 1

        for chain in payload.get('client_chains') or []:
            if not isinstance(chain, dict):
                continue
            if str(chain.get('id')) in client_ids or str(chain.get('sync_code')) in client_codes:
                continue
            manager.client_chains.append(dict(chain))
            client_ids.add(str(chain.get('id')))
            client_codes.add(str(chain.get('sync_code')))
            added_clients += 1

        manager.save()
        self._update_sync_timer()
        self.refresh_sync_watchers()
        dialog = getattr(self, 'sync_manager_dialog', None)
        if dialog is not None and dialog.isVisible():
            dialog.refresh_cards(force=True)
        return added_hosted, added_clients

    def _apply_imported_config(self, cfg: dict):
        """Apply an imported config payload to the running app, then save it.
        Anything the package does not mention is left exactly as it was.
        Returns True when the package changed the local folder, so the caller
        knows the local file list has to be rescanned."""
        if 'format' in cfg and hasattr(self, 'format_combo'):
            _imported_format = str(cfg.get('format')).strip().lower()
            # Same rule as load_config(): an imported package that still names a
            # format this build no longer offers would otherwise put the combo into a
            # no-current-item state, and the next download would go out with a blank
            # --audio-format. Unknown formats are ignored and the current pick stands.
            if _imported_format in DOWNLOAD_FORMATS:
                self.format_combo.setCurrentText(_imported_format)
        if 'bitrate' in cfg and hasattr(self, 'bitrate_combo'):
            self.bitrate_combo.setCurrentText(str(cfg.get('bitrate')))
        if 'mode' in cfg:
            self.appearance_mode = str(cfg.get('mode'))
        if 'accent' in cfg:
            self.accent_color_name = str(cfg.get('accent'))
        if 'volume' in cfg:
            try:
                self.volume_val = int(cfg.get('volume'))
            except (TypeError, ValueError):
                self.volume_val = 100
            if hasattr(self, 'vol_slider'):
                self.vol_slider.setValue(self.volume_val)
        if isinstance(cfg.get('folders'), list) and cfg.get('folders'):
            self.recent_folders = [str(folder) for folder in cfg['folders']]
            self.download_path = self.recent_folders[0]
        touched_local = isinstance(cfg.get('local_folders'), list) or 'local_current_path' in cfg
        if isinstance(cfg.get('local_folders'), list):
            self.local_folders = [str(folder) for folder in cfg['local_folders']]
        if 'local_current_path' in cfg:
            self.local_current_path = str(cfg.get('local_current_path') or "")
        if touched_local:
            # The address bar is filled once at startup, so an imported folder
            # list has to be pushed into it here or it stays stale until relaunch.
            self.set_local_explorer_address(self.local_current_path,
                                           add_to_recent=os.path.isdir(self.local_current_path or ""))
        if 'show_local_metadata' in cfg:
            self.show_local_metadata = bool(cfg.get('show_local_metadata'))
        if 'minimize_to_tray' in cfg:
            self.minimize_to_tray = bool(cfg.get('minimize_to_tray'))
        if 'use_custom_args' in cfg:
            self.use_custom_args = bool(cfg.get('use_custom_args'))
        if 'custom_args' in cfg:
            self.custom_args = str(cfg.get('custom_args') or "")
        if isinstance(cfg.get('recent_playlists'), list):
            self.recent_playlists = [entry for entry in cfg['recent_playlists']
                                     if isinstance(entry, dict)][:5]
        if 'last_search' in cfg and hasattr(self, 'search_entry'):
            self.last_search = str(cfg.get('last_search') or "")
            self.search_entry.setText(self.last_search)
        if isinstance(cfg.get('splitter_sizes'), list) and len(cfg.get('splitter_sizes')) == 3:
            try:
                sizes = [int(value) for value in cfg['splitter_sizes']]
            except (TypeError, ValueError):
                sizes = [300, 800, 300]
            self.splitter_sizes = sizes
            if hasattr(self, 'main_splitter'):
                self.main_splitter.setSizes([sizes[0], sizes[1] + sizes[2]])
            if hasattr(self, 'content_splitter'):
                self.content_splitter.setSizes([sizes[1], sizes[2]])

        if 'save_place' in cfg:
            self.save_place = bool(cfg.get('save_place'))
        if isinstance(cfg.get('session_data'), dict):
            self.session_data = cfg['session_data']
        if 'run_renamer' in cfg:
            self.run_renamer = bool(cfg.get('run_renamer'))
            if hasattr(self, 'run_renamer_cb'):
                self.run_renamer_cb.blockSignals(True)
                self.run_renamer_cb.setChecked(self.run_renamer)
                self.run_renamer_cb.blockSignals(False)
        if 'renamer_path' in cfg:
            self.renamer_path = str(cfg.get('renamer_path') or "")
        if 'run_custom_script' in cfg:
            self.run_custom_script = bool(cfg.get('run_custom_script'))
        if 'custom_script_path' in cfg:
            self.custom_script_path = str(cfg.get('custom_script_path') or "")
        if cfg.get('normalization_mode') in ("on", "off", "ask"):
            self.normalization_mode = str(cfg.get('normalization_mode'))
        if 'auto_rename' in cfg:
            self.auto_rename = bool(cfg.get('auto_rename'))
        if 'silence_pad_dur' in cfg:
            try:
                self.silence_pad_dur = float(cfg.get('silence_pad_dur'))
            except (TypeError, ValueError):
                self.silence_pad_dur = 2.0
        if 'silence_trim' in cfg:
            self.silence_trim = bool(cfg.get('silence_trim'))
        if 'use_custom_norm_cmd' in cfg:
            self.use_custom_norm_cmd = bool(cfg.get('use_custom_norm_cmd'))
        if 'custom_norm_cmd' in cfg:
            self.custom_norm_cmd = str(cfg.get('custom_norm_cmd') or "")
        TUNING.from_settings(self.silence_trim, self.silence_pad_dur,
                             self.use_custom_norm_cmd, self.custom_norm_cmd)
        if 'download_threads' in cfg:
            try:
                self.download_threads = max(1, int(cfg.get('download_threads')))
            except (TypeError, ValueError):
                self.download_threads = 3
        if 'normalization_threads' in cfg:
            try:
                self.normalization_threads = max(1, int(cfg.get('normalization_threads')))
            except (TypeError, ValueError):
                self.normalization_threads = max(1, os.cpu_count() // 2)
        if 'local_rescan_interval' in cfg:
            try:
                self.local_rescan_interval = int(cfg.get('local_rescan_interval'))
            except (TypeError, ValueError):
                self.local_rescan_interval = 60
            self._update_local_rescan_timer()
        if 'disable_update_checks' in cfg:
            self.disable_update_checks = bool(cfg.get('disable_update_checks'))
        if 'disable_ytdlp_updates' in cfg:
            self.disable_ytdlp_updates = bool(cfg.get('disable_ytdlp_updates'))

        self.apply_theme()
        # The settings dialog reads these values when it is built, so the cached
        # one is dropped: reopening it shows the imported settings.
        settings_dialog = getattr(self, 'settings_dialog', None)
        if settings_dialog is not None:
            try:
                settings_dialog.close()
            except Exception:
                pass
            self.settings_dialog = None
        self.save_config()
        # The caller refreshes the local list once everything the package carries
        # has been restored, so the scan sees the imported files too.
        return touched_local and os.path.isdir(self.local_current_path or "")

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main Layout (Horizontal)
        self.main_layout = QHBoxLayout(central_widget)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(0)
        
        # Splitter Logic
        class ResetHandle(QSplitterHandle):
            _last_click = 0
            def mousePressEvent(self, e):
                now = time.time()
                if now - ResetHandle._last_click < 0.35:
                    sp = self.splitter()
                    if sp.orientation() == Qt.Horizontal:
                        current_sizes = sp.sizes()
                        is_main = (sp == getattr(self.window(), 'main_splitter', None))
                        target_idx = 0 if is_main else 1
                        
                        if current_sizes[target_idx] > 0:
                            sp._last_custom_sizes = current_sizes
                            if is_main:
                                sp.setSizes([0, sum(current_sizes)])
                            else:
                                sp.setSizes([sum(current_sizes), 0])
                        else:
                            if hasattr(sp, '_last_custom_sizes') and sp._last_custom_sizes and sp._last_custom_sizes[target_idx] > 0:
                                sp.setSizes(sp._last_custom_sizes)
                            else:
                                if is_main:
                                    sp.setSizes([300, max(0, sum(current_sizes)-300)])
                                else:
                                    sp.setSizes([max(0, sum(current_sizes)-300), 300])
                    e.accept(); return
                ResetHandle._last_click = now
                super().mousePressEvent(e)

        class ResetSplitter(QSplitter):
            def createHandle(self):
                return ResetHandle(self.orientation(), self)

        # Main Splitter (Horizontal: Local | Content)
        self.main_splitter = ResetSplitter(Qt.Horizontal)
        self.main_layout.addWidget(self.main_splitter, 1)
        
        self._setup_local_pane()
        
        # Right Content Area
        self.right_content = QWidget()
        self.right_layout = QVBoxLayout(self.right_content)
        self.right_layout.setContentsMargins(5, 0, 0, 0)
        self.right_layout.setSpacing(5)
        self.main_splitter.addWidget(self.right_content)
        
        # Content Splitter (Horizontal: Results | Queue)
        self.content_splitter = ResetSplitter(Qt.Horizontal)
        self.right_layout.addWidget(self.content_splitter, 1)
        
        self._setup_results_pane()
        self._setup_queue_pane()
        
        # Initial Sizes
        sz = getattr(self, 'splitter_sizes', [300, 800, 300])
        if len(sz) == 3:
            self.main_splitter.setSizes([sz[0], sz[1] + sz[2]])
            self.content_splitter.setSizes([sz[1], sz[2]])
        else:
            self.main_splitter.setSizes([300, 1340])
            self.content_splitter.setSizes([1000, 300])

        # Where the two dividers sit is the user's choice, and nothing else. Every pane on the
        # right of the local column gets an ignored horizontal size policy, which stops a pane
        # from asking the splitter for width when its own contents grow - a longer "Playing:" or
        # "Found N results" line, a download progress line naming five tracks, the queue label
        # counting a thousand items, the first vertical scrollbar eating 16px of the results
        # pane. Left as they were, each of those raised the pane's minimum width and QSplitter
        # answered by moving the divider, so a search moved the local column out from under the
        # user and the right pane was pushed past the edge of the window. With the policy ignored
        # the panes keep whatever width they were given and the layout inside them absorbs the
        # change instead: too much text is clipped by its own pane rather than shoveled into the
        # neighbour's. The columns still resize with the window; only dragging a handle,
        # double-clicking one, or toggling the local pane can move a divider now.
        for _fixed_pane in (self.right_content,
                            self.content_splitter.widget(0), self.content_splitter.widget(1)):
            _pane_policy = _fixed_pane.sizePolicy()
            _pane_policy.setHorizontalPolicy(QSizePolicy.Ignored)
            _fixed_pane.setSizePolicy(_pane_policy)

        # Controls UI
        controls_frame = QFrame()
        c_layout = QVBoxLayout(controls_frame)
        c_layout.setContentsMargins(5, 5, 5, 5)
        c_layout.setSpacing(5)
        self.right_layout.addWidget(controls_frame)
        
        search_r = QHBoxLayout()
        self.toggle_pane_btn = QPushButton("\uE8A0")
        self.toggle_pane_btn.setObjectName("topIconBtn")
        self.toggle_pane_btn.setFixedSize(36, 30)
        self.toggle_pane_btn.setToolTip("Toggle File Browser")
        self.toggle_pane_btn.clicked.connect(self.toggle_local_pane)
        search_r.addWidget(self.toggle_pane_btn)
        
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("Search YouTube or Paste a Video Link")
        self.search_entry.returnPressed.connect(self.perform_search)
        self.search_btn = QPushButton("Search")
        self.search_btn.setToolTip("Search YouTube for songs or playlists")
        self.search_btn.clicked.connect(self.perform_search)
        self.playlist_btn = QPushButton("\uE142")
        self.playlist_btn.setObjectName("topIconBtn")
        self.playlist_btn.setFixedSize(36, 30)
        self.playlist_btn.setToolTip("Recent Playlists")
        self.playlist_btn.clicked.connect(self.open_playlist_dialog)
        
        search_r.addWidget(self.search_entry, 1)
        search_r.addWidget(self.search_btn)
        search_r.addWidget(self.playlist_btn)
        settings_btn = QPushButton("\uE713")
        settings_btn.setObjectName("topIconBtn")
        settings_btn.setFixedSize(36, 30)
        settings_btn.setToolTip("Settings")
        settings_btn.clicked.connect(self.open_settings_dialog)
        search_r.addWidget(settings_btn)
        c_layout.addLayout(search_r)
        
        set_r = QHBoxLayout()
        set_r.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(list(DOWNLOAD_FORMATS))
        self.format_combo.setCurrentText(self.format_var)
        self.format_combo.currentTextChanged.connect(self.save_config)
        set_r.addWidget(self.format_combo)
        
        set_r.addWidget(QLabel("Bitrate:"))
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.addItems(["128", "192", "256", "320"])
        self.bitrate_combo.setCurrentText(self.bitrate_var)
        self.bitrate_combo.currentTextChanged.connect(self.save_config)
        set_r.addWidget(self.bitrate_combo)
        
        set_r.addWidget(QLabel("Save to:"))
        
        self.open_folder_btn = QPushButton("\uE8DA")
        self.open_folder_btn.setObjectName("topIconBtn")
        self.open_folder_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px; padding: 0px;")
        self.open_folder_btn.setFixedSize(36, 30)
        self.open_folder_btn.setToolTip("Open Folder in File Explorer")
        self.open_folder_btn.clicked.connect(self.open_current_download_folder)
        set_r.addWidget(self.open_folder_btn)
        
        self.path_combo = QComboBox()
        self.path_combo.addItems(self.recent_folders)
        if self.download_path not in self.recent_folders:
            self.path_combo.addItem(self.download_path)
        self.path_combo.setCurrentText(self.download_path)
        self.path_combo.currentTextChanged.connect(self.on_path_changed)
        set_r.addWidget(self.path_combo, 1)
        
        self.browse_btn = QPushButton("\uE8B7")
        self.browse_btn.setObjectName("topIconBtn")
        self.browse_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px; padding: 0px;")
        self.browse_btn.setFixedSize(36, 30)
        self.browse_btn.setToolTip("Browse destination folder")
        self.browse_btn.clicked.connect(self.browse_folder)
        set_r.addWidget(self.browse_btn)
        set_r.addSpacing(6)
        c_layout.addLayout(set_r)
        
        option_r = QHBoxLayout()
        self.run_renamer_cb = QCheckBox("Run MP3 Renamer after download")
        self.run_renamer_cb.setChecked(self.run_renamer)
        self.run_renamer_cb.toggled.connect(self.on_run_renamer_toggled)
        option_r.addWidget(self.run_renamer_cb)
        option_r.addStretch()
        c_layout.addLayout(option_r)
        
        status_bar = QHBoxLayout()
        self.playing_label = QLabel("")
        self.playing_label.setTextFormat(Qt.PlainText)
        self.playing_label.setStyleSheet("font-size: 11px; margin-top: -2px;")
        self.status_label = QLabel("Ready")
        self.status_label.setTextFormat(Qt.PlainText)
        self.status_label.setStyleSheet("font-size: 11px; margin-top: -2px;")
        self.dl_progress_label = QLabel("")
        self.dl_progress_label.setTextFormat(Qt.PlainText)
        self.dl_progress_label.setStyleSheet("font-size: 11px; margin-top: -2px; color: #888;")
        self.dl_progress_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        status_bar.addWidget(self.playing_label)
        status_bar.addWidget(self.status_label)
        status_bar.addStretch()
        status_bar.addWidget(self.dl_progress_label)
        c_layout.addLayout(status_bar)

        # Bottom Player
        player_frame = QFrame()
        p_layout = QVBoxLayout(player_frame)
        p_layout.setContentsMargins(8, 4, 8, 4)
        p_layout.setSpacing(0)
        self.right_layout.addWidget(player_frame)
        
        class VolLabel(QLabel):
            def mouseDoubleClickEvent(self, e):
                win = self.window()
                if hasattr(win, 'vol_slider'):
                    win.vol_slider.setValue(100)
                e.accept()

        c = QHBoxLayout()
        c.addWidget(VolLabel("Volume"))
        
        class VolSlider(QSlider):
            def mouseDoubleClickEvent(self, e):
                self.setValue(100)
                e.accept()
                
        self.vol_slider = VolSlider(Qt.Horizontal)
        self.vol_slider.setObjectName("volSlider")
        _init_state = "red" if self.volume_val > 115 else ("orange" if self.volume_val > 100 else "normal")
        self.vol_slider.setProperty("volume_state", _init_state)
        self.vol_slider.setRange(0, 150); self.vol_slider.setValue(self.volume_val)
        self.vol_slider.setFixedWidth(100)
        self.vol_slider.valueChanged.connect(self.on_volume_changed)
        c.addWidget(self.vol_slider)
        
        self.vol_pct = VolLabel(f"{self.volume_val}%")
        self.vol_pct.setFixedWidth(50)
        if self.volume_val > 115:
            self.vol_pct.setStyleSheet("color: #E31E24; font-weight: bold;")
        elif self.volume_val > 100:
            self.vol_pct.setStyleSheet("color: #FF8C00; font-weight: bold;")
        c.addWidget(self.vol_pct)
        
        c.addStretch(1)
        _btn_ss = "background: transparent; color: white; font-family: 'Segoe MDL2 Assets'; font-size: 14px; border-radius: 4px; padding: 2px 4px;"
        _btn_ss_hover = "background: transparent; color: white; font-family: 'Segoe MDL2 Assets'; font-size: 14px; border-radius: 4px; padding: 2px 4px;" + " /* hover set via stylesheet */"
        
        self.prev_btn = QPushButton("\uE892")
        self.prev_btn.setObjectName("playerBtn")
        self.prev_btn.setFixedSize(36, 36)
        self.prev_btn.setToolTip("Previous track")
        self.prev_btn.clicked.connect(self.play_previous)
        c.addWidget(self.prev_btn)
        
        self.play_btn = QPushButton("\uE768")
        self.play_btn.setObjectName("playerPlayBtn")
        self.play_btn.setFixedSize(44, 44)
        self.play_btn.setToolTip("Play / Pause")
        self.play_btn.clicked.connect(self.toggle_playback)
        c.addWidget(self.play_btn)
        
        self.next_btn = QPushButton("\uE893")
        self.next_btn.setObjectName("playerBtn")
        self.next_btn.setFixedSize(36, 36)
        self.next_btn.setToolTip("Next track")
        self.next_btn.clicked.connect(self.play_next)
        c.addWidget(self.next_btn)

        self.shuffle_btn = QPushButton("\uE8B1")
        self.shuffle_btn.setObjectName("playerBtn")
        self.shuffle_btn.setFixedSize(36, 36)
        self.shuffle_btn.setToolTip("Shuffle Playback (Toggle)")
        self.shuffle_btn.clicked.connect(self.toggle_shuffle)
        c.addWidget(self.shuffle_btn)

        # Stop After Current: one button, three states (off -> once -> always).
        # U+25A0 BLACK SQUARE rather than a Segoe MDL2 Assets private-use codepoint:
        # the previous caption (U+E76A "Replay") is not in this machine's MDL2 font, so
        # Qt fell back to the .notdef glyph and the button drew an empty box. U+25A0 is a
        # normal text glyph that Segoe MDL2 Assets (the family the #stopAfterBtn rule
        # asks for), Segoe UI and the fallback fonts all have, so it paints as a filled
        # square whichever font the rule resolves to.
        #
        # 24 rather than the 36 the neighbouring controls use, measured rather than guessed:
        # this caption's ink is 10x9 px at the 20px the rule asks for, so a 36px box was a wide
        # coloured field with the square a speck in the middle of it. 24 leaves ~7px of colour on
        # every side, which is the margin the other controls give their own glyphs. The
        # #stopAfterBtn rule also carries 6px of bottom padding for the same reason: the ink sits
        # low in its own line box (17px of colour above it, 10px below at 36px), and without that
        # padding the square looks parked at the bottom of whatever box draws it.
        self.stop_after_btn = QPushButton("\u25A0")
        self.stop_after_btn.setObjectName("stopAfterBtn")
        self.stop_after_btn.setFixedSize(24, 24)
        self.stop_after_btn.setProperty("stop_after_state", STOP_AFTER_STATE_NAMES[self.stop_after_current])
        self.stop_after_btn.setToolTip(STOP_AFTER_TOOLTIPS[self.stop_after_current])
        self.stop_after_btn.clicked.connect(self.cycle_stop_after_current)
        c.addWidget(self.stop_after_btn)
        c.addStretch(1)
        
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setStyleSheet("font-size: 11px;")
        c.addWidget(self.time_label)
        p_layout.addLayout(c)
        
        self.progress_slider = ClickableSlider(Qt.Horizontal)
        self.progress_slider.setFixedHeight(20)
        self.progress_slider.setRange(0, 10000)
        self.progress_slider.sliderMoved.connect(self.on_seek)
        p_layout.addWidget(self.progress_slider)

        # Restore last search
        if getattr(self, 'last_search', ''):
            self.search_entry.setText(self.last_search)
        
        # Restore session
        if self.save_place and hasattr(self, 'session_data'):
            sd = self.session_data
            if sd.get('search_results'):
                self._on_search_results(sd['search_results'], False, reset_view=False)
                self.playback_index = sd.get('playback_index', -1)
            
            # Restore playback state if item exists
            v_id = sd.get('current_video_id')
            if v_id and v_id != "local":
                # Find the video object in results if possible
                results = sd.get('search_results', [])
                idx = sd.get('playback_index', -1)
                if 0 <= idx < len(results):
                    video = results[idx]
                    self.play_result(video, paused_at_start=True)

        # Re-search in background to update cache
        if getattr(self, 'last_search', ''):
            is_pl = False
            for p in self.recent_playlists:
                if isinstance(p, dict) and p.get("url") == self.last_search: is_pl = True; break
                elif p == self.last_search: is_pl = True; break
            self.perform_search(is_playlist=is_pl, keep_fetch_vid_id=v_id)


    def toggle_local_pane(self):
        sizes = self.main_splitter.sizes()
        if sizes[0] > 0:
            self.main_splitter._last_custom_sizes = sizes
            self.main_splitter.setSizes([0, sizes[0] + sizes[1]])
        else:
            if hasattr(self.main_splitter, '_last_custom_sizes') and self.main_splitter._last_custom_sizes and self.main_splitter._last_custom_sizes[0] > 0:
                self.main_splitter.setSizes(self.main_splitter._last_custom_sizes)
            else:
                self.main_splitter.setSizes([300, max(0, sum(sizes) - 300)])

    def _setup_local_pane(self):
        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(0,0,0,0)
        l.addWidget(QLabel("Local Folder"))
        
        h = QHBoxLayout()
        
        self.open_local_folder_btn = QPushButton("\uE8DA")
        self.open_local_folder_btn.setObjectName("topIconBtn")
        self.open_local_folder_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px; padding: 0px;")
        self.open_local_folder_btn.setFixedSize(36, 30)
        self.open_local_folder_btn.setToolTip("Open Local Folder in File Explorer")
        self.open_local_folder_btn.clicked.connect(self.open_current_local_folder)
        h.addWidget(self.open_local_folder_btn)
        
        self.local_path_combo = QComboBox()
        self.local_path_combo.addItems(self.local_folders)
        self.local_path_combo.currentTextChanged.connect(self.load_local_folder)
        h.addWidget(self.local_path_combo, 1)
        local_browse_btn = QPushButton("\uE8B7")
        local_browse_btn.setObjectName("topIconBtn")
        local_browse_btn.setToolTip("Browse for a local folder")
        local_browse_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px; padding: 0px;")
        local_browse_btn.setFixedSize(36, 30)
        local_browse_btn.clicked.connect(lambda: self.load_local_folder(QFileDialog.getExistingDirectory(self)))
        h.addWidget(local_browse_btn)
        h.addSpacing(6)
        l.addLayout(h)
        
        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(8)
        self.local_meta_cb = QCheckBox("Show Metadata")
        self.local_meta_cb.setChecked(getattr(self, 'show_local_metadata', False))
        self.local_meta_cb.stateChanged.connect(self.toggle_local_metadata)
        meta_row.addWidget(self.local_meta_cb)
        meta_row.addStretch()
        self.local_sel_label = QLabel("")
        self.local_sel_label.setStyleSheet("border: none; background: transparent; font-size: 11px; font-weight: bold;")
        meta_row.addWidget(self.local_sel_label)
        l.addLayout(meta_row)
        
        # Rename / copy / delete actions live in the right-click menu on a row.
        
        self.local_list = QScrollArea()
        self.local_list.setWidgetResizable(True)
        self.local_content = QWidget()
        self.local_content.setObjectName("scrollContent")
        self.local_vbox = QVBoxLayout(self.local_content)
        self.local_vbox.setAlignment(Qt.AlignTop)
        self.local_list.setWidget(self.local_content)
        l.addWidget(self.local_list, 1)
        self.main_splitter.addWidget(w)

    def _setup_results_pane(self):
        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(0,0,0,0)
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 16, 0)
        h.addWidget(QLabel("Search Results"))
        h.addStretch()
        
        self.queue_all_cb = QCheckBox("Queue All")
        self.queue_all_cb.setChecked(False)
        self.queue_all_cb.stateChanged.connect(self.toggle_queue_all)
        h.addWidget(self.queue_all_cb)
        
        self.header_divider = QLabel("  |  ")
        self.header_divider.setStyleSheet("color: #888888; font-weight: bold;")
        h.addWidget(self.header_divider)
        
        self.open_yt_btn = QPushButton("")
        self.open_yt_btn.setObjectName("topIconBtn")
        self.open_yt_btn.setToolTip("Open search / playlist on YouTube")
        self.open_yt_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 14px; padding: 2px 6px;")
        self.open_yt_btn.setFixedSize(30, 26)
        self.open_yt_btn.clicked.connect(self.open_search_on_youtube)
        h.addWidget(self.open_yt_btn)
        l.addLayout(h)
        
        self.results_area = QScrollArea()
        self.results_area.setWidgetResizable(True)
        self.results_content = QWidget()
        self.results_content.setObjectName("scrollContent")
        self.results_vbox = QVBoxLayout(self.results_content)
        self.results_vbox.setAlignment(Qt.AlignTop)
        self.results_area.setWidget(self.results_content)
        self.results_area.verticalScrollBar().valueChanged.connect(self.lazy_load_visible_results)
        l.addWidget(self.results_area, 1)
        self.content_splitter.addWidget(w)
        
    def _setup_queue_pane(self):
        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(0,0,0,0)
        h = QHBoxLayout()
        self.queue_label = QLabel("Download Queue (0)")
        h.addWidget(self.queue_label)
        h.addStretch()
        self.dl_btn = QPushButton("Download All")
        self.dl_btn.setToolTip("Download all pending tracks in queue")
        self.dl_btn.clicked.connect(self.start_batch_download)
        h.addWidget(self.dl_btn)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setToolTip("Cancel ongoing download")
        self.cancel_btn.clicked.connect(self.cancel_batch_download)
        self.cancel_btn.setVisible(False)
        h.addWidget(self.cancel_btn)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setToolTip("Clear finished items from queue")
        self.clear_btn.clicked.connect(self.clear_completed)
        h.addWidget(self.clear_btn)
        l.addLayout(h)
        
        self.queue_area = QScrollArea()
        self.queue_area.setWidgetResizable(True)
        self.queue_content = DraggableQueueWidget()
        self.queue_content.setObjectName("scrollContent")
        self.queue_vbox = QVBoxLayout(self.queue_content)
        self.queue_vbox.setAlignment(Qt.AlignTop)
        self.queue_area.setWidget(self.queue_content)
        self.queue_area.verticalScrollBar().valueChanged.connect(self.lazy_load_visible_queue)
        self.queue_content.order_changed.connect(self._on_queue_order_changed)
        l.addWidget(self.queue_area, 1)
        self.content_splitter.addWidget(w)

    def _on_queue_order_changed(self):
        if hasattr(self.queue_content, '_pending_reorder'):
            src_idx, dst_idx = self.queue_content._pending_reorder
            if 0 <= src_idx < len(self.queue_items) and 0 <= dst_idx < len(self.queue_items):
                src_item = self.queue_items[src_idx]
                dst_item = self.queue_items[dst_idx]
                if src_item.get('status') == 'Pending' and dst_item.get('status') == 'Pending':
                    item = self.queue_items.pop(src_idx)
                    self.queue_items.insert(dst_idx, item)
                    self.queue_update_signal.emit()

    def apply_theme(self):
        mode = self.appearance_mode
        if mode == "System": mode = get_system_appearance_mode()
        
        accent = get_accent_color(self.accent_color_name)
        
        r = int(accent[1:3], 16)
        g = int(accent[3:5], 16)
        b = int(accent[5:7], 16)
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        accent_fg = "#000000" if brightness > 150 else "#ffffff"
        
        # Write checkmark SVG to a temp file
        checkmark_svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{accent_fg}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
        if not hasattr(self, '_checkmark_svg_path') or not os.path.exists(self._checkmark_svg_path):
            tmp = tempfile.NamedTemporaryFile(suffix='.svg', delete=False, mode='w', encoding='utf-8')
            tmp.write(checkmark_svg)
            tmp.close()
            self._checkmark_svg_path = tmp.name.replace('\\', '/')
        else:
            with open(self._checkmark_svg_path, 'w', encoding='utf-8') as f:
                f.write(checkmark_svg)
        checkmark_path = self._checkmark_svg_path
        
        # Write downarrow SVG to a temp file
        downarrow_svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{accent_fg}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>'
        if not hasattr(self, '_downarrow_svg_path') or not os.path.exists(self._downarrow_svg_path):
            tmp = tempfile.NamedTemporaryFile(suffix='.svg', delete=False, mode='w', encoding='utf-8')
            tmp.write(downarrow_svg)
            tmp.close()
            self._downarrow_svg_path = tmp.name.replace('\\', '/')
        else:
            with open(self._downarrow_svg_path, 'w', encoding='utf-8') as f:
                f.write(downarrow_svg)
        downarrow_path = self._downarrow_svg_path
        
        if mode == "Light":
            bg = "#f3f3f3"
            fg = "#1a1a1a"
            frame_bg = "#ffffff"
            input_bg = "#e8e8e8"
            input_border = "#ccc"
            scroll_bg = "#ffffff"
            splitter_handle = "#ddd"
            slider_bg = "#ddd"
            hover_bg = "#000000"
            hover_fg = "#ffffff"
            queue_item_bg = "#e8e8e8"
            queue_item_bg_finished = "#ffffff"
            btn_hover = "rgba(0, 0, 0, 0.1)"
            if self.accent_color_name == "White" or accent.upper() == "#FFFFFF":
                main_btn_border = "1px solid #ccc"
            else:
                main_btn_border = "none"
        else:
            bg = "#1e1e1e"
            fg = "#ffffff"
            frame_bg = "#2a2a2a"
            input_bg = "#333333"
            input_border = "#555"
            scroll_bg = "#1a1a1a"
            splitter_handle = "#333333"
            slider_bg = "#333"
            hover_bg = "#dddddd"
            hover_fg = "#1a1a1a"
            queue_item_bg = "#333333"
            queue_item_bg_finished = "#1a1a1a"
            btn_hover = "rgba(255, 255, 255, 0.1)"
            main_btn_border = "none"

        secondary_fg = "#777777" if mode == "Light" else "#999999"

        # Canonical tooltip style. Applied to the whole application (see below) so
        # every window — the main window and all dialogs — shows identical tooltips
        # with the same font size and appearance as the playback controls.
        tooltip_css = (
            "QToolTip {"
            f" background-color: {frame_bg};"
            f" color: {fg};"
            f" border: 1px solid {input_border};"
            " padding: 2px 6px;"
            " border-radius: 4px;"
            " font-family: 'Segoe UI';"
            " font-size: 10px;"
            " font-weight: normal;"
            " show-delay: 4000ms;"
            " }"
        )

        full_css = """
            QMainWindow, QDialog {{ background-color: {bg}; }}
            QWidget {{ color: {fg}; font-family: 'Segoe UI'; font-size: 13px; }}
            QWidget#scrollContent, DraggableQueueWidget#scrollContent {{ background-color: {scroll_bg}; }}
            QWidget#queueItemPending {{ background-color: {queue_item_bg}; border-radius: 4px; margin-bottom: 2px; }}
            QWidget#queueItemFinished {{ background-color: {queue_item_bg_finished}; border-radius: 4px; margin-bottom: 2px; }}
            QLabel {{ color: {fg}; }}
            QLabel#durationLabel {{ color: {secondary_fg}; font-size: 11px; background: transparent; border: none; }}
            QLabel#channelLabel {{ color: {secondary_fg}; font-size: 11px; background: transparent; border: none; }}
            QPushButton {{ 
                background-color: {accent}; 
                color: {accent_fg}; border: {main_btn_border}; padding: 6px 12px; border-radius: 4px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {hover_bg}; color: {hover_fg}; }}
            QPushButton:disabled {{ background-color: #555555; color: #888888; }}
            QLineEdit {{ 
                background-color: {input_bg}; color: {fg}; border: 1px solid {input_border}; padding: 6px; border-radius: 4px;
            }}
            QComboBox {{ 
                background-color: {input_bg}; color: {fg}; border: 1px solid {input_border}; padding: 6px; border-radius: 4px;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border-left: 1px solid {input_border};
                background-color: {accent};
                border-top-right-radius: 3px;
                border-bottom-right-radius: 3px;
            }}
            QComboBox::down-arrow {{
                image: url("{downarrow_path}");
                width: 16px; height: 16px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {input_bg};
                color: {fg};
                selection-background-color: {accent};
                selection-color: {accent_fg};
                border: 1px solid {input_border};
            }}
            QScrollArea {{ border: none; background-color: {scroll_bg}; border-radius: 6px;}}
            QFrame {{ background-color: {frame_bg}; border-radius: 6px; padding: 5px;}}
            QSplitter::handle {{ background-color: {splitter_handle}; width: 6px; margin: 0px 2px; }}
            QSlider::groove:horizontal {{ border: none; height: 4px; background: {slider_bg}; border-radius: 2px; }}
            QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: {accent}; width: 16px; height: 16px; margin-top: -6px; margin-bottom: -6px; border-radius: 8px; }}
            QSlider#volSlider[volume_state="normal"]::sub-page:horizontal {{ background: {accent}; }}
            QSlider#volSlider[volume_state="normal"]::handle:horizontal {{ background: {accent}; }}
            QSlider#volSlider[volume_state="orange"]::sub-page:horizontal {{ background: #FF8C00; }}
            QSlider#volSlider[volume_state="orange"]::handle:horizontal {{ background: #FF8C00; }}
            QSlider#volSlider[volume_state="red"]::sub-page:horizontal {{ background: #E31E24; }}
            QSlider#volSlider[volume_state="red"]::handle:horizontal {{ background: #E31E24; }}
            QSlider#volSlider::sub-page:horizontal {{ border-radius: 1px; }}
            
            QCheckBox {{ color: {fg}; spacing: 8px; }}
            QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {accent}; border-radius: 3px; background: {frame_bg}; }}
            QCheckBox::indicator:checked {{ background: {accent}; image: url("{checkmark_path}"); }}
            
            QPushButton#transparentBtn {{
                background-color: transparent;
                color: {fg};
                font-weight: normal;
                border-radius: 0px;
                padding: 4px;
                text-align: left;
            }}
            QPushButton#transparentBtn:hover {{
                background-color: {btn_hover};
            }}
            QWidget#localRow {{
                background-color: transparent;
                border-radius: 4px;
            }}
            QWidget#localRow[selected="true"] {{
                background-color: {accent};
            }}
            /* The row that is the track the player is holding wears the colour of that
               state - green while it runs, orange while it is held - and it is written
               after the selection rule so that a row which is both selected and playing
               says the thing the listener is looking at the folder list to find out. */
            QWidget#localRow[play_state="playing"] {{
                background-color: {THUMB_BOX_PLAYING};
            }}
            QWidget#localRow[play_state="paused"] {{
                background-color: {THUMB_BOX_PAUSED};
            }}
            /* A green and an orange row both carry saturated colour behind the text, so
               the text on them is fixed rather than left to the theme's own foreground,
               which is chosen to sit on the dark panes and not on these. */
            QWidget#localRow[play_state="playing"] QPushButton#transparentBtn,
            QWidget#localRow[play_state="paused"] QPushButton#transparentBtn,
            QWidget#localRow[play_state="playing"] QLabel#durationLabel,
            QWidget#localRow[play_state="paused"] QLabel#durationLabel {{
                color: #1a1a1a;
                font-weight: bold;
            }}
            QPushButton#transparentBtn[selected="true"] {{
                background-color: transparent;
                color: {accent_fg};
            }}
            QPushButton#transparentBtn[selected="true"]:hover {{
                background-color: {btn_hover};
            }}
            QLabel#durationLabel[selected="true"] {{ color: {accent_fg}; }}
            /* The duration sits just off the right edge of a local row. Saying it once
               here instead of styling every row separately keeps the row build cheap,
               and it is scoped to the local pane, where that 6px gap was designed. */
            QWidget#localRow QLabel#durationLabel {{ padding-right: 6px; }}
            QMenu#localContextMenu {{
                background-color: {frame_bg};
                color: {fg};
                border: 1px solid {input_border};
                border-radius: 4px;
                padding: 4px;
            }}
            QMenu#localContextMenu::item {{
                padding: 6px 28px 6px 12px;
                border-radius: 3px;
            }}
            QMenu#localContextMenu::item:selected {{
                background-color: {accent};
                color: {accent_fg};
            }}
            QMenu#localContextMenu::item:disabled {{ color: {secondary_fg}; }}
            QMenu#localContextMenu::separator {{
                height: 1px;
                background: {input_border};
                margin: 4px 6px;
            }}
            QPushButton#iconBtn {{
                background-color: transparent;
                color: {fg};
                font-weight: normal;
                padding: 0px;
            }}
            QPushButton#topIconBtn {{
                background-color: transparent;
                color: {fg};
                font-family: 'Segoe MDL2 Assets';
                font-size: 15px;
                font-weight: normal;
                border: 1px solid {input_border};
                border-radius: 4px;
                padding: 0px;
            }}
            QPushButton#topIconBtn:hover {{
                background-color: {btn_hover};
            }}
            QPushButton#playerBtn {{
                background-color: transparent;
                color: {fg};
                font-family: 'Segoe MDL2 Assets';
                font-size: 20px;
                font-weight: normal;
                border-radius: 6px;
                padding: 0px;
            }}
            QPushButton#playerBtn:hover {{
                background-color: {btn_hover};
            }}
            QPushButton#playerBtn[active="true"] {{
                background-color: {accent};
                color: {accent_fg};
                font-weight: bold;
            }}
            QPushButton#playerBtn[active="true"]:hover {{
                background-color: {hover_bg};
                color: {hover_fg};
            }}
            QPushButton#playerPlayBtn {{
                background-color: transparent;
                color: {fg};
                font-family: 'Segoe MDL2 Assets';
                font-size: 30px;
                font-weight: normal;
                border-radius: 8px;
                padding: 0px;
            }}
            QPushButton#playerPlayBtn:hover {{
                background-color: {btn_hover};
            }}
            QPushButton#stopAfterBtn {{
                background-color: transparent;
                color: {secondary_fg};
                font-family: 'Segoe MDL2 Assets';
                font-size: 20px;
                font-weight: normal;
                border-radius: 6px;
                padding: 0px 0px 6px 0px;
            }}
            QPushButton#stopAfterBtn:hover {{
                background-color: {btn_hover};
                color: {fg};
            }}
            QPushButton#stopAfterBtn[stop_after_state="once"] {{
                background-color: {accent};
                color: {accent_fg};
                font-weight: bold;
            }}
            QPushButton#stopAfterBtn[stop_after_state="always"] {{
                background-color: #E31E24;
                color: white;
                font-weight: bold;
            }}
            {tooltip_css}
        """.format(
            bg=bg, fg=fg, frame_bg=frame_bg, input_bg=input_bg, input_border=input_border,
            scroll_bg=scroll_bg, splitter_handle=splitter_handle, slider_bg=slider_bg,
            hover_bg=hover_bg, hover_fg=hover_fg, accent=accent, accent_fg=accent_fg,
            queue_item_bg=queue_item_bg, queue_item_bg_finished=queue_item_bg_finished,
            btn_hover=btn_hover, checkmark_path=checkmark_path, downarrow_path=downarrow_path,
            main_btn_border=main_btn_border, secondary_fg=secondary_fg,
            # The colours a row wears when it is the track the player is holding, shared with
            # the thumbnail box of a search row so both panes say the same thing in the same
            # green and the same orange.
            THUMB_BOX_PLAYING=THUMB_BOX_PLAYING, THUMB_BOX_PAUSED=THUMB_BOX_PAUSED,
            tooltip_css=tooltip_css
        )
        # Apply the theme at the widget level (as in 2.3). A single
        # self.setStyleSheet re-polishes only this window's subtree; routing it
        # through QApplication.setStyleSheet instead re-polishes every widget in
        # every top-level window, which is what made theme switching laggy. The
        # tooltip rules are embedded in full_css above and propagate to child
        # dialogs through this stylesheet, so no app-level call is required.
        self.setStyleSheet(full_css)
        self.update_shuffle_btn_style()
        self._update_stop_after_ui()

    # --- Local Folder Logic ---
    def set_local_explorer_address(self, path: str = "", add_to_recent: bool = False):
        """Show a folder in the local file explorer's address bar. This only
        rebuilds the address bar and its recent list; scanning the folder is a
        separate step, so a slow drive never holds the GUI thread hostage."""
        if not hasattr(self, 'local_path_combo'):
            return
        path = os.path.abspath(path) if path else ""
        if add_to_recent and path and path not in self.local_folders:
            self.local_folders.insert(0, path)
            self.local_folders = self.local_folders[:5]
        # The whole list is rebuilt rather than just appended to, because an
        # imported config can bring a different set of recent folders with it.
        self.local_path_combo.blockSignals(True)
        self.local_path_combo.clear()
        self.local_path_combo.addItems([str(folder) for folder in self.local_folders])
        if path:
            self.local_path_combo.setCurrentText(path)
        self.local_path_combo.blockSignals(False)

    def load_local_folder(self, path):
        if not path or not os.path.exists(path): return
        path = os.path.abspath(path)
        self.local_current_path = path

        self.set_local_explorer_address(path, add_to_recent=True)
        self.save_config()
        self.refresh_local_list()

    def toggle_local_metadata(self, state):
        self.show_local_metadata = (state == Qt.Checked.value)
        self.save_config()
        self.refresh_local_list()

    def refresh_local_list(self):
        """Re-render the open folder. The switch itself is instant and the rows then fill
        in a screenful at a time - see _start_local_render - so a folder holding hundreds
        of files no longer delays the screen change the user asked for."""
        self._start_local_render(self.local_current_path)

    def _refresh_local_list_async(self):
        """Rescan the open folder for every refresh that was not caused by the user
        directly (a sync finishing, the hourly auto-rescan). _start_local_render already
        does its scanning off the GUI thread, so this is the same path under the name the
        callers that must not block use."""
        self._start_local_render(self.local_current_path)

    def _start_local_render(self, path):
        """Show `path` now, and let its rows come in afterwards.

        The rows of the folder being replaced are torn down and the scan starts on a
        worker thread before this returns, so nothing about the screen change is waiting
        on the folder: the view is cleared to the new folder in the time it takes to drop
        the old rows, and the first rows land as soon as the listing is known. The
        listing itself is the cheap part - scandir hands over the name, size and timestamp
        of every entry as it walks the folder, so 500 files list in a few milliseconds -
        and it is sorted before the first batch because the batch order is the order the
        rows appear in, and File Explorer order is what the user expects to land on.

        Each render has its own id. The scan thread checks it before handing the listing
        over and the GUI thread checks it again before every chunk of rows it builds, so
        the rows of a folder that has already been left behind - or of a drive pulled out
        mid-listing - cannot arrive on the folder that is on screen instead."""
        self._local_render_id = getattr(self, '_local_render_id', 0) + 1
        render_id = self._local_render_id
        # A fill still under way belongs to the folder being replaced.
        self._local_render_timer.stop()
        self._local_render_pending = None
        # The metadata reads of the folder being replaced are cancelled here rather than
        # per chunk, because the chunks of one folder have to keep reading under the same
        # pass. See _fetch_local_metadata_bg.
        self._local_meta_pass = getattr(self, '_local_meta_pass', 0) + 1
        self._reset_local_rows()

        def _list_and_feed():
            items = self._scan_local_items(path)
            if render_id != getattr(self, '_local_render_id', 0):
                return  # a newer folder is on screen now; this listing is stale
            # The whole listing crosses to the GUI thread in one go, because how big a
            # chunk of rows should be depends on what building and painting them costs on
            # this machine, and only the GUI thread can know that. A folder that cannot be
            # listed comes back as None and is reported as an empty render, so the pane
            # stays clear for it instead of keeping rows from a drive that is gone.
            self._emit_local_listing(render_id, path, items)

        threading.Thread(target=_list_and_feed, daemon=True).start()

    def _emit_local_listing(self, render_id, path, items):
        """Hand the finished listing to the GUI thread, which does the chunking. Returning
        False means the signal is gone - the window is being torn down."""
        try:
            self._local_listing_signal.emit((render_id, path, items))
            return True
        except RuntimeError:
            return False

    def _on_local_listing(self, payload):
        """The GUI-thread half of a render: the new folder is on screen and its listing is
        known, so the pane starts filling with it - one screenful of rows first, everything
        after that behind it. A listing whose render id is not the current one belongs to a
        folder the user has already moved on from and is dropped."""
        render_id, path, items = payload
        if render_id != getattr(self, '_local_render_id', 0):
            return  # this listing was listed for a folder that has since been replaced
        if path != self.local_current_path:
            return  # and so was this one
        if not items:
            # A folder with nothing in it has no chunks to fill, but the render still has to
            # be closed out: the selection, and any track left paused when the window was
            # closed, are settled against a list that is now known to be empty.
            self._local_render_pending = None
            self._finish_local_render()
            return
        self._local_render_pending = items
        self._local_render_pending_id = render_id
        self._local_render_pending_path = path
        self._local_render_total_rows = len(items)
        self._local_render_step = self._local_screenful_rows()
        self._local_render_chunk_end = None
        self._local_render_chunk_cost = 0.0
        self._local_render_chunk_rows = 0
        self._local_render_row_cost = 0.0
        self._fill_local_chunk()

    def _local_screenful_rows(self):
        """How many rows the pane can show at once, which is the size of the first chunk:
        the rows the user switched folders to look at are the rows built first, and a folder
        smaller than a screen is built in one go, exactly as fast as it always was."""
        pane = getattr(self, 'local_list', None)
        height = pane.viewport().height() if pane is not None else 0
        fits = int(height // max(1.0, self._local_render_row_height)) if height > 0 else 0
        return max(fits, LOCAL_RENDER_FIRST_CHUNK_ROWS)

    def _fill_local_chunk(self):
        """Create the rows of the next chunk and hand control back. The event loop lays
        those rows out and polishes them before the zero timer runs this again, which is
        what makes a big folder fill in on screen instead of arriving all at once.

        The gap between one chunk ending and the next starting is what that chunk cost, its
        painting included, so it is divided by the rows that chunk produced to get what a row
        costs on this machine, and the next chunk is made as big as that cost allows within
        the budget. A folder of rows that are expensive - long titles, tags that have to be
        read - fills in smaller chunks than a folder of cheap ones, and both stay answerable."""
        pending = getattr(self, '_local_render_pending', None)
        if not pending:
            self._local_render_pending = None
            return
        if (self._local_render_pending_id != getattr(self, '_local_render_id', 0)
                or self._local_render_pending_path != self.local_current_path):
            self._local_render_pending = None
            return  # the user moved on while this folder was still filling in

        now = time.perf_counter()
        if self._local_render_chunk_end is not None:
            spent = (now - self._local_render_chunk_end) + self._local_render_chunk_cost
            cost_per_row = spent / max(1, self._local_render_chunk_rows)
            previous = self._local_render_row_cost
            # Smoothed, so one chunk that happened to land on a slow stretch - a folder
            # whose tags still have to be read, a window being dragged - does not decide
            # the size of every chunk after it.
            self._local_render_row_cost = (previous * 0.4 + cost_per_row * 0.6) \
                if previous > 0.0 else cost_per_row
            budget = max(0.001, LOCAL_RENDER_CHUNK_BUDGET_S)
            self._local_render_step = int(min(LOCAL_RENDER_CHUNK_MAX_ROWS,
                                              max(LOCAL_RENDER_CHUNK_MIN_ROWS,
                                                  budget / max(self._local_render_row_cost,
                                                              1e-6))))

        step = max(1, self._local_render_step)
        self._local_render_pending = pending[step:] or None
        rows_before = len(self.local_rows)
        try:
            self._append_local_rows(pending[:step])
        except RuntimeError:
            self._local_render_pending = None
            return  # the pane is being taken down around us
        self._local_render_chunk_cost = time.perf_counter() - now
        self._local_render_chunk_end = time.perf_counter()
        rows_added = len(self.local_rows) - rows_before
        self._local_render_chunk_rows = rows_added
        if rows_added:
            self._measure_local_row_pitch(rows_before)
            # The listing has always said how many rows there are going to be, and the fill knows
            # what a row of this folder costs the list, so the height of the finished folder is
            # known here - before any of these rows have been painted - and the pane is given it.
            # Everything the fill does after this point happens inside a pane that is already the
            # size it is going to end up.
            self._reserve_local_extent()
        if self._local_render_pending:
            self._local_render_timer.start(0)
        else:
            self._finish_local_render()

    def _measure_local_row_pitch(self, rows_before):
        """What one row of this folder costs the list, read off the rows already on screen.

        The height the pane's content reports lags a fill like this one: a row container has only
        just been created, so it has nothing to report about its own height until the event loop
        has polished it and laid it out. Measuring a row from that number is measuring the rows of
        the chunk before last, and an estimate built from it is a little different at every chunk -
        which makes the pane a slightly different size at every chunk, the thing the reservation
        below exists to prevent. The rows the previous chunk built have been laid out by now, and
        where the first and last of them ended up says exactly what a row costs: the row itself and
        the spacing the list puts between rows.
        """
        if rows_before < 2:
            return  # nothing has been laid out yet, so the guess stands
        first_row = self.local_rows[0][0]
        settled_row = self.local_rows[rows_before - 1][0]
        span = settled_row.y() - first_row.y()
        if span <= 0:
            return  # and this chunk got its turn before those rows were laid out
        self._local_render_row_height = span / (rows_before - 1)

    def _reserve_local_extent(self):
        """Hand the pane the height the finished folder is going to take up.

        The listing has said how many rows the folder has since before the first row existed, and
        the fill knows what a row of this folder costs the list, so the height the finished folder
        is going to occupy is worked out here - before any of its rows have been painted - and the
        content widget is given it as its own minimum. From here on the fill happens inside a pane
        that is already the size it is going to end up: the rows already drawn do not move, the
        scrollbar spans the whole folder before its last row exists, and each chunk after the first
        is built into room that is already there instead of making the folder taller under the user
        a batch at a time. That is the cheaper shape as well - a content widget whose own height
        has changed makes Qt lay out every row it already has again, and doing that twenty-odd
        times is most of what a streamed fill costs.

        The estimate is reworked at every chunk and only worth acting on when it has moved by more
        than a row, so the pane is sized once, early, and left alone.
        """
        pane = getattr(self, 'local_list', None)
        content = getattr(self, 'local_content', None)
        total = getattr(self, '_local_render_total_rows', 0)
        if pane is None or content is None or total <= 0:
            return
        row_pitch = max(1.0, self._local_render_row_height)
        # The space the list leaves above its first row and below its last. The rows carry the
        # top one in their own position on screen; the bottom one is the same margin.
        top_margin = 0
        if self.local_rows:
            top_margin = max(0, self.local_rows[0][0].y())
        height = int(total * row_pitch + 2 * top_margin + 0.5)
        height = max(height, pane.viewport().height())
        applied = getattr(self, '_local_render_extent_height', 0)
        if applied and abs(height - applied) <= row_pitch:
            return  # the pane already has room for the whole folder
        self._local_render_extent_height = height
        content.setMinimumHeight(height)

    def _release_local_extent(self):
        """Take back the height reserved for a folder that is no longer filling in.

        Two moments want it. At the end of a fill the rows themselves are the better answer for
        how tall the pane's content is than the estimate the fill was working to, and dropping
        the estimate is what keeps a folder whose rows came out a little shorter than expected
        from leaving a strip of blank pane under it. And when a folder is being replaced, the
        reserved height belongs to a listing that is going away; the incoming folder reserves its
        own as soon as its first chunk has landed.
        """
        self._local_render_total_rows = 0
        self._local_render_extent_height = 0
        content = getattr(self, 'local_content', None)
        if content is not None:
            content.setMinimumHeight(0)

    def _scan_local_items(self, folder_path: str):
        """All filesystem work for the local file list. Returns None when the
        folder is unavailable, otherwise the rows that should be displayed."""
        if not folder_path or not os.path.exists(folder_path):
            return None
        items = []
        try:
            parent = os.path.dirname(folder_path)
            if parent and parent != folder_path:
                items.append({'name': ".. (Back)", 'path': parent, 'is_dir': True, 'selectable': False})
            with os.scandir(folder_path) as current_dir:
                for entry in current_dir:
                    if entry.is_dir():
                        items.append({'name': entry.name, 'path': entry.path, 'is_dir': True, 'selectable': True})
                    elif entry.is_file():
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in AUDIO_EXTENSIONS:
                            item = {'name': entry.name, 'path': entry.path, 'is_dir': False, 'selectable': True}
                            # Anything this session has already read for this file comes
                            # straight out of the cache, so a folder that has been opened
                            # before renders with its durations already written and no
                            # reading at all. DirEntry.stat() costs nothing extra here:
                            # Windows already hands the size and the timestamp over
                            # inside the directory listing scandir is walking.
                            cached = None
                            try:
                                st = entry.stat()
                                cached = _local_meta_cache.get((entry.path, st.st_mtime_ns, st.st_size))
                            except OSError:
                                cached = None
                            if cached is not None:
                                title, artist, duration, tags_resolved = cached
                                # Tags only count as known when they were actually read:
                                # "Show artist/title" switched on later has to be able to
                                # ask for the ones that were skipped while it was off.
                                if tags_resolved or not getattr(self, 'show_local_metadata', False):
                                    item['meta_name'] = _local_display_name(item['name'], title, artist)
                                    item['duration_str'] = _format_audio_duration(duration)
                            items.append(item)
        except Exception:
            pass
        items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        return items

    def _reset_local_rows(self):
        """Tear down the rows of the folder being replaced. What was selected survives,
        so a refresh of the folder already on screen - a sync landing new files - does not
        quietly drop the user's selection. The row the shift-ranges were anchored to does
        not survive, and the count beside the metadata checkbox waits until the new rows
        exist rather than reporting the selection of rows that are no longer there."""
        while self.local_vbox.count():
            item = self.local_vbox.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        self.local_rows = []
        self.local_row_by_path = {}
        self.local_btns = []
        # These rows are gone, and with them the row this app was colouring.
        self._forget_playback_box()
        self.current_local_items = []
        self.local_selection_anchor = None
        self._update_local_selection_ui()
        # The height handed to the pane for the rows of the folder being replaced goes with
        # them; the incoming folder reserves its own once its first chunk has landed.
        self._release_local_extent()

    def _append_local_rows(self, items):
        """Create the widgets for one batch of rows. Numbering continues from the rows
        already on screen, so selection ranges and the right-click menu keep working
        while a folder is still being filled in. The metadata reads for this batch start
        here rather than at the end of the folder, so a duration appears on a row the
        user can already see."""
        base_index = len(self.local_rows)
        prev_btns = len(self.local_btns)

        for offset, item in enumerate(items):
            idx = base_index + offset
            raw_title = item.get('meta_name', item['name']) if getattr(self, 'show_local_metadata', False) else item['name']
            escaped_title = raw_title.replace('&', '&&')

            # Every row is wrapped in a styled container so a selection can be
            # highlighted across the whole row, the way File Explorer does it.
            row_w = QWidget()
            row_w.setObjectName("localRow")
            row_w.setAttribute(Qt.WA_StyledBackground, True)
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(2, 1, 2, 1)
            row_l.setSpacing(4)

            if item['is_dir']:
                full_title = f"📁  {escaped_title}"
                btn = DoubleClickButton(full_title)
                btn.setObjectName("transparentBtn")
                btn.setToolTip("Click to select | Double-click to open folder")
                btn._elide = _ElideTextFilter(full_title, reserve=12).attach(btn)
                if item.get('selectable', True):
                    btn.singleClicked.connect(lambda i=item, k=idx: self._on_local_select(i, k))
                else:
                    btn.singleClicked.connect(lambda i=item: self._on_local_click(i))
                btn.doubleClicked.connect(lambda i=item: self._on_local_click(i))
                dur_lbl = None
            else:
                full_title = f"🎵  {escaped_title}"
                btn = DoubleClickButton(full_title)
                btn.setObjectName("transparentBtn")
                btn.setToolTip("Click to select | Double-click to play")
                btn.doubleClicked.connect(lambda i=item: self._on_local_click(i))
                btn.singleClicked.connect(lambda i=item, k=idx: self._on_local_select(i, k))
                btn._elide = _ElideTextFilter(full_title, reserve=12).attach(btn)

                # Nothing styled per row here: QLabel#durationLabel in the app
                # stylesheet already carries the colour, the size and the spacing.
                # Parsing a style string for every row is work the pane does on the
                # GUI thread while it should be laying the folder out.
                dur_lbl = QLabel(item.get('duration_str', ''))
                dur_lbl.setObjectName("durationLabel")

            row_l.addWidget(btn, 1)
            if dur_lbl is not None:
                row_l.addWidget(dur_lbl)
            self.local_vbox.addWidget(row_w)

            # Right-click menu on the row, the way File Explorer does it.
            for menu_target in (row_w, btn):
                menu_target.setContextMenuPolicy(Qt.CustomContextMenu)
                menu_target.customContextMenuRequested.connect(
                    lambda pos, w=menu_target, i=item, k=idx: self._show_local_context_menu(w, pos, i, k))

            self.local_rows.append((row_w, btn, dur_lbl, item, idx))
            self.local_row_by_path[item['path']] = len(self.local_rows) - 1
            if not item['is_dir']:
                self.local_btns.append((btn, dur_lbl, item))

        self.current_local_items.extend(items)
        # A selection that survived a refresh of the folder has to pick up the rows built
        # after it. When nothing is selected there is nothing to pick up: a fresh row
        # carries no 'selected' property at all and the stylesheet only styles
        # selected="true", so skipping this pass is what keeps a 500-file folder from
        # re-polishing every row it has already drawn, batch after batch.
        if getattr(self, 'local_selected_paths', ()):
            self._apply_local_selection_styles()
        # The play state is not part of the selection, so it is put onto the new rows on its
        # own: a folder refreshed under a playing file rebuilds the row for that file, and
        # that row has to come back carrying the colour it had before it was replaced.
        self._reapply_playback_box_after_rebuild()
        self._fetch_local_metadata_bg(self.local_btns[prev_btns:])

    def _finish_local_render(self):
        """The last batch of this render has landed. Only now is it known whether a
        selection that survived the refresh still points at something in the folder, and
        a local track the session was closed on can be resumed against a list that is
        finally complete."""
        self._release_local_extent()
        previous_selection = set(getattr(self, 'local_selected_paths', ()))
        self.local_selected_paths = {p for p in previous_selection if p in self.local_row_by_path}
        self._apply_local_selection_styles()
        self._update_local_selection_ui()

        resume_index = getattr(self, '_pending_local_restore_index', None)
        if resume_index is None:
            return
        resume_path = getattr(self, '_pending_local_restore_path', None)
        if resume_path is not None and os.path.abspath(resume_path) != self.local_current_path:
            return  # this folder is not the one that track was left on
        self._pending_local_restore_index = None
        audio_files = [x for x in self.current_local_items if not x.get('is_dir')]
        if 0 <= resume_index < len(audio_files):
            QTimer.singleShot(100, lambda: self._on_local_click(audio_files[resume_index], paused_at_start=True))
            
    def _fetch_local_metadata_bg(self, rows=None):
        """Fill in the durations and the artist/title of the rows handed to it - the
        batch of rows that just landed, or every row of the folder when called without
        any. mutagen reads them inside this process; ffprobe is only reached for the
        files mutagen cannot open or cannot tag. A row whose values were already answered
        from the cache while the folder was scanned is not touched at all, and each row
        that does need reading is written back on its own instead of the whole list being
        rebuilt around it."""
        from PySide6.QtCore import QObject, Signal

        class MetaWorker(QObject):
            meta_done = Signal(object, object, object)

        if getattr(self, '_meta_worker', None) is None:
            self._meta_worker = MetaWorker()
            self._meta_worker.meta_done.connect(self._apply_local_row_meta)

        # The pass belongs to the render, not to this call. Every batch of the folder on
        # screen reads under the same pass, so a batch landing a second into a 500-file
        # folder cannot cancel the reads of the batches before it. Switching folders bumps
        # the pass in _start_local_render, and that is what stops the reads of the folder
        # that has been replaced - a backlog that was a large part of what made the next
        # folder slow to fill in.
        this_pass = getattr(self, '_local_meta_pass', 0)

        source = self.local_btns if rows is None else rows
        pending = [(btn, d_lbl, item) for (btn, d_lbl, item) in source
                   if 'duration_str' not in item]
        if not pending:
            return

        want_tags = getattr(self, 'show_local_metadata', False)
        workers = max(1, min(4, os.cpu_count() or 1))

        # One reader pool per render rather than one per batch: the batches of a streamed
        # folder arrive every few milliseconds, and each with its own pool of readers would
        # pile threads onto the disk the folder is being read from.
        pool = getattr(self, '_meta_pool', None)
        if pool is None or getattr(self, '_meta_pool_pass', None) != this_pass:
            old_pool = pool
            pool = ThreadPoolExecutor(max_workers=workers)
            self._meta_pool = pool
            self._meta_pool_pass = this_pass
            if old_pool is not None:
                try:
                    # Reads queued for the folder that has just been replaced are pointless.
                    old_pool.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass

        def read_row(btn, d_lbl, item):
            if self._local_meta_pass != this_pass:
                return  # a newer folder is on screen; this row is gone
            path = item['path']
            ext = os.path.splitext(path)[1].lower()
            # What the file IS, taken before anything is read from it. The read and the
            # cache entry are pinned to this same identity, so a file that is being
            # written right now cannot have one version's values filed under another's.
            try:
                st_before = os.stat(path)
                cache_key = (path, st_before.st_mtime_ns, st_before.st_size)
            except OSError:
                cache_key = None
            read = _read_local_audio_meta(path)
            if read is None:
                title, artist, duration = None, None, None
                tags_unknown = True   # mutagen will not open this format at all
            else:
                title, artist, duration = read
                # mutagen read the tag system in this container and found no title, so
                # there is no title to find. Where it has no tag API at all (wav, aiff)
                # or cannot open the file (mka, ape), the tags stay unknown until
                # either ffprobe has answered or the pane stops asking for tags.
                tags_unknown = not title and ext not in MUTAGEN_TAGGABLE_EXTENSIONS

            if duration is None or (tags_unknown and want_tags):
                ff_title, ff_artist, ff_duration = _ffprobe_audio_meta(path)
                if duration is None:
                    duration = ff_duration
                if tags_unknown:
                    title, artist = ff_title, ff_artist
                tags_resolved = True
            else:
                tags_resolved = not tags_unknown

            item['meta_name'] = _local_display_name(item['name'], title, artist)
            item['duration_str'] = _format_audio_duration(duration)
            if cache_key is not None:
                try:
                    st_after = os.stat(path)
                except OSError:
                    st_after = None
                # Worth remembering only if the file is still the one that was read.
                if st_after is not None and (st_after.st_mtime_ns, st_after.st_size) == cache_key[1:]:
                    _local_meta_cache_put(cache_key, title, artist, duration, tags_resolved)
            if self._local_meta_pass != this_pass:
                return  # superseded while the read was running: there is no row to write onto
            self._meta_worker.meta_done.emit(btn, d_lbl, item)

        # The rows are queued on the render's own pool. submit() is what starts the reader
        # threads and it costs microseconds, so the GUI thread is back at the event loop
        # building the next batch of rows while these reads run.
        for btn, d_lbl, item in pending:
            try:
                pool.submit(read_row, btn, d_lbl, item)
            except Exception:
                break  # this pool was already closed by a newer render

    def _apply_local_row_meta(self, btn, d_lbl, item):
        """Write the values a background read produced onto that one row: the name
        through the elide filter, so the row keeps its trimming behaviour, and the
        duration straight into its own label. Nothing else in the list is touched."""
        row_index = getattr(self, 'local_row_by_path', {}).get(item['path'])
        if row_index is None or row_index >= len(self.local_rows) or self.local_rows[row_index][1] is not btn:
            return  # a newer rebuild has since replaced this row
        try:
            raw_title = item.get('meta_name', item['name']) if getattr(self, 'show_local_metadata', False) else item['name']
            btn._elide.set_full_text(f"🎵  {raw_title.replace('&', '&&')}")
            if d_lbl is not None:
                d_lbl.setText(item.get('duration_str', ''))
        except RuntimeError:
            pass  # a newer rebuild has already torn this row down

    def _on_local_click(self, item, paused_at_start=False, from_nav=False):
        if item['is_dir']: 
            self.load_local_folder(item['path'])
        else:
            # If VLC is still initializing in background, retry after a short delay
            if not getattr(self, '_vlc_ready', False):
                QTimer.singleShot(200, lambda: self._on_local_click(item, paused_at_start, from_nav))
                return
            if self.vlc_instance is None or self.vlc_player is None:
                self._on_status_update("Playback unavailable: VLC Media Player is not installed.", False, "#E31E24")
                return

            display_name = item.get('meta_name', item['name']) if getattr(self, 'show_local_metadata', False) else item['name']
            self._on_status_update(f"Playing Local: {display_name}", False, "#3B8ED0")
            url = item['path'].replace("\\", "/")
            if not url.startswith("file:///"): url = "file:///" + url
            self.current_video_id = "local"
            # A file from the local pane is not the track a search armed its one-shot
            # for, and it steps through the folder list, which a search does not touch.
            self._release_search_stop_after("local")
            self.current_local_file_path = item['path']
            
            audio_files = [x for x in getattr(self, 'current_local_items', []) if x.get('is_dir') is False]
            for i, af in enumerate(audio_files):
                if af.get('path') == item.get('path'):
                    self.local_playback_index = i
                    break

            if not from_nav:
                # User manually selected a track: reset shuffle history with this track
                self.shuffle_history = [getattr(self, 'local_playback_index', 0)]
                    
            media = self.vlc_instance.media_new(url)
            self.vlc_player.set_media(media)
            if paused_at_start:
                self.vlc_player.audio_set_mute(True)
                self.vlc_player.play()
                def delay_pause():
                    self.vlc_player.set_pause(1)
                    self.vlc_player.set_position(0)
                    self.vlc_player.audio_set_mute(False)
                QTimer.singleShot(250, delay_pause)
            else:
                self.vlc_player.play()
            # A file on disk is not a signed link with a lifetime, so there is nothing here that
            # can expire: the stream watchdog is told to watch nothing on this track.
            self._note_loaded_stream(None)
            self.playback_started_signal.emit(display_name, "local", paused_at_start)

    # --- Local file editor: selection, delete, rename ---
    def _on_local_select(self, item, index):
        """Single-click selection for a local list row, mirroring File Explorer:
        a plain click selects only that row, Ctrl+click toggles rows in and out
        of the selection, and Shift+click selects everything between the row that
        was selected before and this one."""
        if not item.get('selectable', True):
            self._on_local_click(item)
            return
        mods = QApplication.keyboardModifiers()
        ctrl = bool(mods & (Qt.ControlModifier | Qt.MetaModifier))
        shift = bool(mods & Qt.ShiftModifier)
        path = item['path']

        if shift and getattr(self, 'local_selection_anchor', None) is not None:
            lo, hi = sorted((self.local_selection_anchor, index))
            for _, _, _, row_item, row_idx in self.local_rows:
                if lo <= row_idx <= hi and row_item.get('selectable', True):
                    self.local_selected_paths.add(row_item['path'])
        elif ctrl:
            if path in self.local_selected_paths:
                self.local_selected_paths.discard(path)
            else:
                self.local_selected_paths.add(path)
            self.local_selection_anchor = index
        else:
            self.local_selected_paths = {path}
            self.local_selection_anchor = index

        self._apply_local_selection_styles()
        self._update_local_selection_ui()

    def _selected_local_items(self):
        return [row_item for _, _, _, row_item, _ in getattr(self, 'local_rows', [])
                if row_item.get('selectable', True) and row_item['path'] in self.local_selected_paths]

    def select_all_local_files(self):
        if not getattr(self, 'local_rows', []):
            return
        self.local_selected_paths = {row_item['path'] for _, _, _, row_item, _ in self.local_rows
                                     if row_item.get('selectable', True)}
        self._apply_local_selection_styles()
        self._update_local_selection_ui()

    def clear_local_selection(self):
        self.local_selected_paths = set()
        self.local_selection_anchor = None
        self._apply_local_selection_styles()
        self._update_local_selection_ui()

    def _open_local_selection(self):
        items = self._selected_local_items()
        if len(items) == 1:
            self._on_local_click(items[0])

    def _focus_is_in_local_pane(self, widget=None) -> bool:
        """True when that widget - or the one holding focus when none is given - sits
        inside the local file list.

        The walk goes through parentWidget and not parent, because two of this
        program's dialogs keep the window that opened them in an attribute named parent,
        which replaces the Qt method of the same name on those instances. Walking with
        parent() from a control inside such a dialog therefore ends up calling the
        MainApp window itself, which is what raised
        "TypeError: 'MainApp' object is not callable" out of eventFilter on every key
        typed into Settings. parentWidget is a name the dialogs here never reassign.
        """
        w = widget if widget is not None else QApplication.focusWidget()
        if w is None or not hasattr(self, 'local_list'):
            return False
        while w is not None:
            if w is self.local_list or w is self.local_content:
                return True
            w = w.parentWidget()
        return False

    # ------------------------------------------------------------------
    # Which row the player is holding, in colour
    # ------------------------------------------------------------------
    # A search row already has a grey box around its thumbnail and a local row already
    # takes a background when it is selected, so the play state is not a new widget to
    # draw - it is one more thing those existing surfaces can say.
    #
    # The colour comes from what libVLC reports rather than from is_playing, because
    # is_playing is what the listener last asked for and not what the media is doing: a
    # stream whose URL has given out is neither playing nor held, and the box should say
    # that about it too. Opening and Buffering are left uncoloured for the same reason -
    # a track still on its way is not a track the player has got hold of yet.
    def _playback_box_state(self):
        """The play-state token for the state the player is in, or None when it holds
        nothing it could be playing."""
        if not self.vlc_player:
            return None
        try:
            state = self.vlc_player.get_state()
        except Exception:
            return None
        if state == vlc.State.Playing:
            return "playing"
        if state == vlc.State.Paused:
            return "paused"
        return None

    def _playback_box_key(self):
        """(where, which, state) for the row that carries the play state right now, or
        None when no row should. 'where' picks the pane and 'which' is the video id of a
        search row or the path of a local one - the same keys those panes already index
        their rows by."""
        state = self._playback_box_state()
        if state is None:
            return None
        vid_id = self.current_video_id
        if vid_id == "local":
            path = getattr(self, 'current_local_file_path', '')
            if not path:
                return None
            return ("local", path, state)
        if not vid_id:
            return None
        return ("search", vid_id, state)

    def _refresh_playback_highlights(self):
        """Move the coloured row to whichever track the player is holding, when that has
        changed since the last look.

        This runs from the player's own tick, which is already asking libVLC for the state,
        so a play, a pause, a resume, an automatic advance, prev/next, a local file and a
        stream that had to be re-resolved all land here without anything else having to
        remember to say so. A tick where nothing changed - which is nearly every tick -
        stops at this comparison, so a pane full of rows is not repolished sixty times a
        second while a track runs."""
        key = self._playback_box_key()
        previous = getattr(self, '_playback_box', None)
        if key == previous:
            return
        if previous is not None and key is not None and previous[:2] == key[:2]:
            # The same row changing colour - play into pause and back again - only has to
            # be repainted once, rather than cleared and painted again.
            self._apply_playback_box(key)
        else:
            if previous is not None:
                self._apply_playback_box((previous[0], previous[1], None))
            self._apply_playback_box(key)
        self._playback_box = key

    def _apply_playback_box(self, key):
        """Write a play state onto the row that key names. A state of None puts that row
        back to the plain look it has when it is not the loaded track."""
        if key is None:
            return
        where, target, state = key
        if where == "local":
            self._set_local_row_play_state(target, state)
        elif where == "search":
            self._set_search_row_box(target, state)

    def _forget_playback_box(self):
        """The row this app coloured is no longer there to uncolour. Dropping the record of
        it is what lets the next highlight reach the row that exists now instead of being
        skipped as already done - a new search and a rebuilt folder each replace every row
        the pane had, and a row that is rebuilt starts plain."""
        self._playback_box = None

    def _set_search_row_box(self, vid_id, state):
        label = getattr(self, '_thumbnail_labels', {}).get(vid_id)
        if label is None:
            return  # this row is scrolled out of view, so it has no thumbnail box to colour
        tile = label.parentWidget()
        if tile is None or not hasattr(tile, 'set_highlight'):
            return
        try:
            tile.set_highlight(state)
        except RuntimeError:
            pass  # the row was torn down between the lookup and the colouring

    def _set_local_row_play_state(self, path, state):
        index = getattr(self, 'local_row_by_path', {}).get(path)
        if index is None or index >= len(self.local_rows):
            return  # this file is not a row of the folder currently on screen
        row_w = self.local_rows[index][0]
        # An empty token matches no rule of the stylesheet, which is how the row gets its
        # plain background back. Local rows are coloured through the stylesheet rather than
        # per row so that filling a folder does not parse a style string for every file in it.
        token = state or ""
        try:
            if row_w.property('play_state') == token:
                return
            row_w.setProperty('play_state', token)
            row_w.style().unpolish(row_w)
            row_w.style().polish(row_w)
            row_w.update()
        except RuntimeError:
            pass  # a newer rebuild has already torn this row down

    def _reapply_playback_box_after_rebuild(self):
        """Put the play state back onto the rows that have just been created, when the track
        they contain is the one the player is holding."""
        box = getattr(self, '_playback_box', None)
        if box is None:
            return
        self._apply_playback_box(box)

    def _note_thumb_hover(self, tile):
        """Record that this thumbnail row is showing its play button, and take the button off
        whichever row had it before.

        One row at a time owns the button, which is what puts a limit on the departures Qt does
        not report (see THUMB_HOVER_RECHECK_MS): a row left holding its button up by a scroll, a
        teardown or a flick that produced no Leave loses it as soon as the pointer is genuinely
        on another row. The recheck timer runs only while a row is holding the button, so a list
        nobody is pointing at costs nothing.
        """
        previous = getattr(self, '_hover_tile', None)
        if previous is not None and previous is not tile:
            try:
                previous.play_btn.hide()
            except RuntimeError:
                pass  # that row has already been torn down
        self._hover_tile = tile
        timer = getattr(self, '_thumb_hover_timer', None)
        if timer is not None and not timer.isActive():
            timer.start()

    def _forget_thumb_hover(self, tile=None):
        """Take the button off the row holding it, and stop asking after it.

        Called by a row that is no longer being pointed at, is going away, or is being torn down.
        A row that was not the one holding the button has nothing to clear - its button is already
        hidden - and it must not switch off the recheck belonging to the row that is. With no tile
        named, it is the whole list going away.
        """
        tracked = getattr(self, '_hover_tile', None)
        if tracked is None or (tile is not None and tracked is not tile):
            return
        try:
            tracked.play_btn.hide()
        except RuntimeError:
            pass  # the row was torn down before it could be let go
        self._hover_tile = None
        timer = getattr(self, '_thumb_hover_timer', None)
        if timer is not None:
            timer.stop()

    def _recheck_thumb_hover(self):
        """Ask the pointer again whether the row holding the play button is still the row it is
        on - the catch for the ways Qt fails to say so, any of the ones named by
        THUMB_HOVER_RECHECK_MS: a scroll moves a row out from under a pointer that never moved,
        a row is torn down under it, a row is built under it without an Enter ever arriving.
        Cheap by construction: there is only ever one row to ask about, and only while a button
        is showing.
        """
        tracked = getattr(self, '_hover_tile', None)
        if tracked is None:
            return  # no row is holding a button, which is the case a moment to spare
        try:
            on_it = tracked._pointer_on_tile()
        except RuntimeError:
            on_it = False  # the row holding the button has already been torn down
        if not on_it:
            self._forget_thumb_hover(tracked)

    def _clear_thumb_hover(self):
        """The results list is being thrown away wholesale, so the row holding the play button goes
        with it. A button left on a row that has been deleted is exactly the stuck one a user
        sees, and there is nothing left here worth rechecking."""
        self._forget_thumb_hover()

    def _apply_local_selection_styles(self):
        selected_paths = getattr(self, 'local_selected_paths', set())
        for row_w, btn, dur_lbl, row_item, _ in getattr(self, 'local_rows', []):
            selected = row_item.get('selectable', True) and row_item['path'] in selected_paths
            targets = [row_w, btn] + ([dur_lbl] if dur_lbl is not None else [])
            for w in targets:
                if w.property('selected') == selected:
                    continue
                w.setProperty('selected', selected)
                try:
                    w.style().unpolish(w)
                    w.style().polish(w)
                except Exception:
                    pass
                w.update()

    def _update_local_selection_ui(self):
        count = len(self._selected_local_items())
        if hasattr(self, 'local_sel_label'):
            self.local_sel_label.setText(f"{count} selected" if count else "")

    def _show_local_context_menu(self, source_widget, pos, item, index):
        """Right-click menu for a row of the local file list, like File Explorer.
        Right-clicking a row that is not part of the selection selects it first."""
        if not item.get('selectable', True):
            menu = QMenu(self)
            menu.setObjectName("localContextMenu")
            open_act = menu.addAction("Open")
            open_act.triggered.connect(lambda checked=False, i=item: self._on_local_click(i))
            menu.exec(source_widget.mapToGlobal(pos))
            menu.deleteLater()
            return

        if item['path'] not in getattr(self, 'local_selected_paths', set()):
            self._on_local_select(item, index)

        # Keep the keyboard shortcuts (Ctrl+C, Del, F2) live after a right-click.
        try:
            self.local_rows[self.local_row_by_path[item['path']]][1].setFocus()
        except Exception:
            pass

        selected = self._selected_local_items()
        files = [i for i in selected if not i['is_dir']]

        menu = QMenu(self)
        menu.setObjectName("localContextMenu")
        if len(selected) == 1:
            only = selected[0]
            open_act = menu.addAction("Play" if not only['is_dir'] else "Open")
            open_act.setToolTip("Open this folder" if only['is_dir'] else "Play this file")
            open_act.triggered.connect(lambda checked=False, i=only: self._on_local_click(i))
        rename_act = menu.addAction("Rename from metadata\tF2")
        rename_act.setToolTip("Rename the selected files from their artist / title tags")
        rename_act.setEnabled(bool(files))
        rename_act.triggered.connect(lambda checked=False: self.rename_local_selected())
        copy_act = menu.addAction("Copy\tCtrl+C")
        copy_act.setToolTip("Copy the selected files so they can be pasted into File Explorer")
        copy_act.setEnabled(bool(selected))
        copy_act.triggered.connect(lambda checked=False: self.copy_local_selected())
        menu.addSeparator()
        delete_act = menu.addAction("Delete\tDel")
        delete_act.setToolTip("Delete the selected files")
        delete_act.setEnabled(bool(selected))
        delete_act.triggered.connect(lambda checked=False: self.delete_local_selected())
        menu.exec(source_widget.mapToGlobal(pos))
        menu.deleteLater()

    def copy_local_selected(self):
        """Copy the selected files to the clipboard as real file references, so
        they can be pasted into File Explorer or any other file-aware target."""
        items = self._selected_local_items()
        if not items:
            self._on_status_update("Nothing selected to copy.", False, "#E31E24")
            return
        paths = [i['path'] for i in items]
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        mime.setText("\n".join(paths))
        QApplication.clipboard().setMimeData(mime)
        label = Path(paths[0]).name if len(paths) == 1 else f"{len(paths)} files"
        self._on_status_update(f"Copied {label} to the clipboard.", False, "#3B8ED0")

    def delete_local_selected(self):
        """Delete the selected files (and empty folders) after a confirmation."""
        items = self._selected_local_items()
        if not items:
            self._on_status_update("Nothing selected to delete.", False, "#E31E24")
            return
        names = [i['name'] for i in items]
        preview = "\n".join(names[:10]) + ("\n..." if len(names) > 10 else "")
        answer = QMessageBox.question(
            self, "Delete Selected",
            f"Permanently delete {len(items)} item(s)?\n\n{preview}\n\n"
            "Folders are only deleted when they are empty.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        deleted_files = 0
        deleted_folders = 0
        problems = []
        playing = getattr(self, 'current_local_file_path', '')
        for it in items:
            target = it['path']
            try:
                if it['is_dir']:
                    if os.listdir(target):
                        problems.append(f"{it['name']} (folder not empty)")
                        continue
                    os.rmdir(target)
                    deleted_folders += 1
                else:
                    os.remove(target)
                    deleted_files += 1
            except Exception as e:
                problems.append(f"{it['name']} ({e})")
                continue
            if playing and os.path.abspath(target) == os.path.abspath(playing):
                player = getattr(self, 'vlc_player', None)
                if player is not None:
                    try:
                        player.stop()
                    except Exception:
                        pass
                self.current_local_file_path = ""
        self.clear_local_selection()
        self.refresh_local_list()
        msg = f"Deleted {deleted_files} file(s)"
        if deleted_folders:
            msg += f" and {deleted_folders} folder(s)"
        if problems:
            msg += ". Skipped: " + ", ".join(problems[:4])
        self._on_status_update(msg, False, "#1abd33" if not problems else "#E31E24")

    def rename_local_selected(self):
        """Open the metadata renamer for the selected tracks, then rename every
        one of them to 'Artist - Title' built from the tags they carry."""
        files = [i for i in self._selected_local_items() if not i['is_dir']]
        if not files:
            self._on_status_update("Rename: select at least one audio file.", False, "#E31E24")
            return
        dlg = MetadataRenameDialog(self, [i['path'] for i in files])
        results = dlg.results if dlg.exec() == QDialog.Accepted else []
        renamed = [r for r in results if r['status'] == 'renamed']
        skipped = [r for r in results if r['status'] in ('conflict', 'failed')]
        playing = getattr(self, 'current_local_file_path', '')
        for r in renamed:
            if playing and os.path.abspath(r['old']) == os.path.abspath(playing):
                self.current_local_file_path = r['new']
                break
        self.clear_local_selection()
        self.refresh_local_list()
        if not results:
            return
        msg = f"Renamed {len(renamed)} file(s) to 'Artist - Title' from metadata."
        if skipped:
            msg += f" Skipped {len(skipped)}: " + ", ".join(s['message'] for s in skipped[:3])
        self._on_status_update(msg, False, "#1abd33" if not skipped else "#E31E24")

    def open_settings_dialog(self):
        if not hasattr(self, 'settings_dialog') or self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(self)
            self.settings_dialog.setWindowModality(Qt.NonModal)
            self.settings_dialog.setAttribute(Qt.WA_DeleteOnClose, False)
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def open_playlist_dialog(self):
        d = PlaylistDialog(self)
        if d.exec() == QDialog.Accepted and d.url_cb.currentText():
            val = d.url_cb.currentText()
            url = val
            for p in self.recent_playlists:
                if isinstance(p, dict) and p.get("name") == val:
                    url = p.get("url")
                    break
            self.search_entry.setText(url)
            self.perform_search(is_playlist=True)

    def perform_search(self, is_playlist=False, keep_fetch_vid_id=None):
        query = self.search_entry.text()
        if not query: return
        # A new search is read from its first row, not from wherever the last one was left
        self._reset_results_scroll()
        # A stream URL still being resolved is a request for the track the listener had just
        # picked, and this search is what they want now: the read-ahead's successor and any
        # earlier click are stopped rather than left to finish and be discarded. The resolution
        # for the track still on the player is kept - that track is still playing, and if its
        # URL died the watchdog is midway through reloading it. keep_fetch_vid_id covers the one
        # caller that starts a fetch and a search back to back on purpose (the session restore
        # preload), where nothing has been overridden and the fetch must be left alone.
        keep = keep_fetch_vid_id or getattr(self, 'current_video_id', None)
        self._cancel_superseded_stream_fetches(keep_vid_id=keep)
        # Nothing is waiting on the player any more, so nothing owns it either.
        self._pending_fetch_id = None
        self._is_loading_stream = False
        self._on_status_update("Searching...", False, "#3B8ED0")
        self.search_btn.setEnabled(False)
        
        def bg_search():
            try:
                if "youtube.com" in query or "youtu.be" in query or "http" in query:
                    info = run_yt_dlp_json([
                        "--flat-playlist", "-J", "--playlist-items", "1-100", query,
                    ])
                    
                    if info and 'entries' in info:
                        res = [e for e in info['entries'] if e]
                        if len(info['entries']) >= 100:
                            start_idx = 101
                            chunk_size = 100
                            while True:
                                self.status_signal.emit(f"Searching... (Retrieved {len(res)} items)", False, "#3B8ED0")
                                chunk_info = run_yt_dlp_json([
                                    "--flat-playlist", "-J",
                                    "--playlist-items", f"{start_idx}-{start_idx + chunk_size - 1}",
                                    query,
                                ])
                                if not chunk_info or 'entries' not in chunk_info:
                                    break
                                entries = [e for e in chunk_info['entries'] if e]
                                if not entries:
                                    break
                                res.extend(entries)
                                if len(chunk_info['entries']) < chunk_size:
                                    break
                                start_idx += chunk_size
                    else:
                        res = [info] if info else []
                else:
                    res = run_yt_dlp_text_search(
                        query, status_cb=lambda text: self.status_signal.emit(text, False, "#3B8ED0"))
                        
                if is_playlist and ('youtube.com' in query or 'youtu.be' in query):
                    title = info.get('title', query) if isinstance(info, dict) else query
                    updated = False
                    for i, rp in enumerate(self.recent_playlists):
                        if isinstance(rp, dict) and rp.get("url") == query:
                            self.recent_playlists[i]["name"] = title
                            updated = True; break
                        elif rp == query:
                            self.recent_playlists[i] = {"name": title, "url": query}
                            updated = True; break
                    if not updated:
                        self.recent_playlists.insert(0, {"name": title, "url": query})
                        self.recent_playlists = self.recent_playlists[:5]
                    
                self.search_results_signal.emit(res, False)
            except Exception as exc:
                self.search_failed_signal.emit()
                if isinstance(exc, YtDlpMissingError):
                    self.ytdlp_missing_signal.emit("Searching and downloading both need yt-dlp.")
                
        threading.Thread(target=bg_search, daemon=True).start()

    def _on_search_results(self, res, is_playlist, reset_view=True):
        self.search_btn.setEnabled(True)
        self.search_results = res
        self._thumbnail_labels = getattr(self, '_thumbnail_labels', {})
        self._thumbnail_labels.clear()
        # Every row these results had is about to be deleted, so the row this app was
        # colouring goes with them and cannot be coloured back to plain later.
        self._forget_playback_box()
        
        # Every row these results had is going away, and with them the play button whichever one
        # of them was holding. A button left on a row that is being thrown away is the stuck one.
        self._clear_thumb_hover()

        while self.results_vbox.count():
            item = self.results_vbox.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        height = 54
        for video in res:
            placeholder = QWidget()
            placeholder.setFixedHeight(height)
            placeholder.setProperty("video", video)
            placeholder.setProperty("has_ui", False)
            self.results_vbox.addWidget(placeholder)
            
        # reset_view is True when these are results from a search that was just run, and
        # False when the same list is only being redrawn (settings
        # import, session restore). A new search is read from its first row, and the
        # successor decided for the list being replaced is no longer part of the playlist
        # playback is stepping through; a redraw of the same list is neither.
        # A search replaces the list playback is stepping through, so the track that
        # is playing when it lands is armed with a one-shot stop instead of being
        # followed by whatever row happens to sit at its index in the new list.
        search_armed_stop_after = False
        if reset_view:
            self.invalidate_next_track_prefetch()
            self._reset_results_scroll()
            search_armed_stop_after = self._arm_stop_after_for_new_search()
        if search_armed_stop_after:
            self._on_status_update(f"Found {len(res)} results - Stop after current", False, "#FF8C00")
        else:
            self._on_status_update(f"Found {len(res)} results.", False, "white")
        QTimer.singleShot(0, self.lazy_load_visible_results)
        # Lazy loading re-expands rows as they are built; land at the top again after it.
        if reset_view:
            QTimer.singleShot(0, self._reset_results_scroll)
        self.update_queue_all_checkbox_state()

    def _reset_results_scroll(self):
        """Scroll the results pane back to its top."""
        if getattr(self, 'results_area', None):
            self.results_area.verticalScrollBar().setValue(0)

    def _on_search_failed(self):
        self.search_btn.setEnabled(True)
        self._on_status_update("Search failed. Check your connection or URL.", False, "red")

    def toggle_queue(self, video, state):
        checked = state == Qt.Checked.value
        in_queue = any(q['video']['id'] == video['id'] for q in self.queue_items)
        if checked and not in_queue:
            self.queue_items.append({'video': video, 'status': 'Pending'})
        elif not checked and in_queue:
            self.queue_items = [q for q in self.queue_items if q['video']['id'] != video['id']]
        self.queue_update_signal.emit()

    def toggle_queue_all(self, state):
        checked = state == Qt.Checked.value
        if not self.search_results:
            return
            
        # Quick set for O(1) membership lookups to check if search results already exist in queue
        search_ids = {v['id'] for v in self.search_results if 'id' in v}
        
        # Modify queue in-place in bulk
        if checked:
            existing_queue_ids = {q['video']['id'] for q in self.queue_items if 'video' in q and 'id' in q['video']}
            new_items = []
            for video in self.search_results:
                if 'id' in video and video['id'] not in existing_queue_ids:
                    new_items.append({'video': video, 'status': 'Pending'})
            if new_items:
                self.queue_items.extend(new_items)
        else:
            self.queue_items = [q for q in self.queue_items if 'video' not in q or q['video'].get('id') not in search_ids]
            
        # Bulk-update checking of all currently visible result checkboxes to avoid individual trigger overhead
        for i in range(self.results_vbox.count()):
            layout_item = self.results_vbox.itemAt(i)
            if layout_item and layout_item.widget():
                widget = layout_item.widget()
                checkboxes = widget.findChildren(QCheckBox)
                for cb in checkboxes:
                    cb.blockSignals(True)
                    cb.setChecked(checked)
                    cb.blockSignals(False)
                    
        self.queue_update_signal.emit()

    def update_queue_all_checkbox_state(self):
        if not hasattr(self, 'queue_all_cb') or not self.search_results:
            return
            
        # Highly-optimized O(N + M) set-based comparison to prevent slowness/lag
        queue_ids = {q['video']['id'] for q in self.queue_items if 'video' in q and 'id' in q['video']}
        all_in_queue = True
        for video in self.search_results:
            if 'id' in video:
                if video['id'] not in queue_ids:
                    all_in_queue = False
                    break
                    
        self.queue_all_cb.blockSignals(True)
        self.queue_all_cb.setChecked(all_in_queue)
        self.queue_all_cb.blockSignals(False)

    def build_result_ui(self, placeholder, video, queue_ids):
        l = QHBoxLayout(placeholder)
        l.setContentsMargins(2,2,2,2)
        
        tw = ThumbnailWidget(video, self)
        l.addWidget(tw)
        self._thumbnail_labels[video['id']] = tw.thumb_label
        # A row that has just been built starts with the plain box, so the state it is in -
        # this row is the track that is running, held, or neither - has to be put on it now.
        box = getattr(self, '_playback_box', None)
        if box is not None and box[0] == "search" and box[1] == video.get('id', ''):
            tw.set_highlight(box[2])
        threading.Thread(target=self._fetch_thumbnail, args=(video,), daemon=True).start()
            
        title = video.get('title', 'Unknown')
        cb = QCheckBox(f"{title.replace('&', '&&')}")
        cb.setProperty("video_id", video.get('id', ''))
        
        # Persist checked state
        cb.setChecked(video.get('id') in queue_ids)
            
        cb.stateChanged.connect(lambda state, v=video: self.toggle_queue(v, state))
        cb._elide = _ElideTextFilter(f"{title.replace('&', '&&')}", reserve=28).attach(cb)
        l.addWidget(cb, 1)
        
        # Channel name (to the left of duration/timestamp)
        channel = entry_channel_name(video)
        if channel:
            if len(channel) > 25:
                channel = channel[:23] + '…'
            ch_lbl = QLabel(channel)
            ch_lbl.setObjectName("channelLabel")
            ch_lbl.setStyleSheet("border: none; background: transparent; padding-right: 6px;")
            l.addWidget(ch_lbl)

        # Duration/timestamp
        dur = video.get('duration_string')
        if not dur and video.get('duration'):
            try:
                d = float(video['duration'])
                if d >= 3600:
                    dur = f"{int(d//3600)}:{int((d%3600)//60):02d}:{int(d%60):02d}"
                else:
                    dur = f"{int(d//60)}:{int(d%60):02d}"
            except:
                dur = ""
        if dur:
            dur_lbl = QLabel(dur)
            dur_lbl.setObjectName("durationLabel")
            dur_lbl.setStyleSheet("border: none; background: transparent; padding-right: 4px;")
            l.addWidget(dur_lbl)
        
        # Open on YouTube button
        yt_btn = QPushButton("")
        yt_btn.setObjectName("iconBtn")
        yt_btn.setToolTip("Open on YouTube")
        yt_btn.setFixedSize(28, 28)
        yt_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 13px;")
        vid_id = video.get('id', '')
        yt_btn.clicked.connect(lambda checked=False, vid=vid_id: __import__('webbrowser').open(f'https://www.youtube.com/watch?v={vid}'))
        l.addWidget(yt_btn)
        
        placeholder.setProperty("has_ui", True)

    def clear_result_ui(self, placeholder):
        video = placeholder.property("video")
        if video and 'id' in video and video['id'] in self._thumbnail_labels:
            try:
                del self._thumbnail_labels[video['id']]
            except KeyError:
                pass

        # The row is going away under whichever pointer happens to be on it - this is the scroll
        # taking rows out of the pane - and its widgets stay visible until their deleteLater lands.
        # Settle the play button first, so the button of a row that no longer exists is never left
        # sitting on top of the rows that did.
        for tile in placeholder.findChildren(ThumbnailWidget):
            tile.set_pointer_hover(False)
            
        layout = placeholder.layout()
        if layout:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            placeholder.setLayout(None)
            layout.deleteLater()
            
        placeholder.setProperty("has_ui", False)

    def lazy_load_visible_results(self):
        if not self.search_results or not hasattr(self, 'results_area'):
            return
            
        scrollbar = self.results_area.verticalScrollBar()
        scroll_val = scrollbar.value()
        viewport_height = self.results_area.viewport().height()
        
        # Buffer of 200px to ensure smooth scrolling
        buffer = 200
        load_top = scroll_val - buffer
        load_bottom = scroll_val + viewport_height + buffer
        
        queue_ids = {q['video']['id'] for q in self.queue_items if 'video' in q and 'id' in q['video']}
        
        for i in range(self.results_vbox.count()):
            layout_item = self.results_vbox.itemAt(i)
            if layout_item and layout_item.widget():
                placeholder = layout_item.widget()
                video = placeholder.property("video")
                if not video:
                    continue
                    
                y = placeholder.y()
                h = placeholder.height()
                
                is_visible = (y + h >= load_top and y <= load_bottom)
                has_ui = placeholder.property("has_ui")
                
                if is_visible:
                    if not has_ui:
                        self.build_result_ui(placeholder, video, queue_ids)
                else:
                    if has_ui:
                        self.clear_result_ui(placeholder)

        # A scroll moves rows around under a pointer that never moved, and Qt sends no Leave for a
        # pointer that never moved - which is the row that keeps a play button nobody is pointing
        # at. This is where that row finds out. Cheap by construction: one row gets asked, and no
        # row gets asked when no button is showing.
        self._recheck_thumb_hover()

    def build_queue_item_ui(self, placeholder, q, idx):
        l = QHBoxLayout(placeholder)
        l.setContentsMargins(5,5,5,5)
        
        st = "\uE73E " if q['status'] == "Finished" else ("\uE896 " if q['status'] == "Downloading" else "")
        t = q['video'].get('title', 'Unknown')
        if len(t) > 40: t = t[:37] + "..."
        t_escaped = html.escape(t)
        
        lbl = QLabel(f"<span style='font-family: \"Segoe MDL2 Assets\";'>{st}</span> {t_escaped}")
        l.addWidget(lbl, 1)
        
        rm_btn = QPushButton("\uE711")
        rm_btn.setObjectName("iconBtn")
        rm_btn.setToolTip("Remove from queue")
        rm_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 14px;")
        rm_btn.setFixedSize(26, 26)
        rm_btn.clicked.connect(lambda checked=False, i=idx: self.remove_from_queue(i))
        l.addWidget(rm_btn)
        
        placeholder.setObjectName("queueItemFinished" if q['status'] == "Finished" else "queueItemPending")
        placeholder.style().unpolish(placeholder)
        placeholder.style().polish(placeholder)
        
        placeholder.setProperty("has_ui", True)

    def _on_queue_status_changed(self, idx):
        """Update only the status icon/color of a single queue item in-place, no full rebuild."""
        if idx >= len(self.queue_items) or idx >= self.queue_vbox.count():
            return
        layout_item = self.queue_vbox.itemAt(idx)
        if not layout_item or not layout_item.widget():
            return
        placeholder = layout_item.widget()
        q = self.queue_items[idx]
        # Keep the stored property up to date
        placeholder.setProperty("queue_item", q)
        # If widget is already rendered, patch its label in-place
        if placeholder.property("has_ui"):
            labels = placeholder.findChildren(QLabel)
            if labels:
                st = "\uE73E " if q['status'] == "Finished" else ("\uE896 " if q['status'] == "Downloading" else "")
                t = q['video'].get('title', 'Unknown')
                if len(t) > 40: t = t[:37] + "..."
                labels[0].setText(f"<span style='font-family: \"Segoe MDL2 Assets\";'>{st}</span> {html.escape(t)}")
            new_name = "queueItemFinished" if q['status'] == "Finished" else "queueItemPending"
            if placeholder.objectName() != new_name:
                placeholder.setObjectName(new_name)
                placeholder.style().unpolish(placeholder)
                placeholder.style().polish(placeholder)

    def clear_queue_item_ui(self, placeholder):
        layout = placeholder.layout()
        if layout:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            placeholder.setLayout(None)
            layout.deleteLater()
        placeholder.setProperty("has_ui", False)

    def lazy_load_visible_queue(self):
        if not self.queue_items or not hasattr(self, 'queue_area'):
            return
            
        scrollbar = self.queue_area.verticalScrollBar()
        scroll_val = scrollbar.value()
        viewport_height = self.queue_area.viewport().height()
        
        buffer = 200
        load_top = scroll_val - buffer
        load_bottom = scroll_val + viewport_height + buffer
        
        for i in range(self.queue_vbox.count()):
            layout_item = self.queue_vbox.itemAt(i)
            if layout_item and layout_item.widget():
                placeholder = layout_item.widget()
                q = placeholder.property("queue_item")
                idx = placeholder.property("queue_index")
                if q is None or idx is None:
                    continue
                    
                y = placeholder.y()
                h = placeholder.height()
                
                is_visible = (y + h >= load_top and y <= load_bottom)
                has_ui = placeholder.property("has_ui")
                
                if is_visible:
                    if not has_ui:
                        self.build_queue_item_ui(placeholder, q, idx)
                else:
                    if has_ui:
                        self.clear_queue_item_ui(placeholder)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.lazy_load_visible_results)
        QTimer.singleShot(0, self.lazy_load_visible_queue)

    def _refresh_queue_display(self):
        while self.queue_vbox.count():
            item = self.queue_vbox.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        self.queue_label.setText(f"Download Queue ({len(self.queue_items)})")
        
        for idx, q in enumerate(self.queue_items):
            placeholder = QWidget()
            placeholder.setFixedHeight(36)
            placeholder.setProperty("queue_item", q)
            placeholder.setProperty("queue_index", idx)
            placeholder.setProperty("has_ui", False)
            self.queue_vbox.addWidget(placeholder)
            
        QTimer.singleShot(0, self.lazy_load_visible_queue)
            
        # Synchronize search result checkboxes with current queue state in a highly-optimized manner
        queue_ids = {q['video']['id'] for q in self.queue_items if 'video' in q and 'id' in q['video']}
        for i in range(self.results_vbox.count()):
            layout_item = self.results_vbox.itemAt(i)
            if layout_item and layout_item.widget():
                widget = layout_item.widget()
                checkboxes = widget.findChildren(QCheckBox)
                for cb in checkboxes:
                    vid_id = cb.property("video_id")
                    if vid_id:
                        cb.blockSignals(True)
                        cb.setChecked(vid_id in queue_ids)
                        cb.blockSignals(False)
                        
        self.update_queue_all_checkbox_state()

    def remove_from_queue(self, idx):
        if idx < len(self.queue_items):
            self.queue_items.pop(idx)
            self.queue_update_signal.emit()

    def clear_completed(self, checked=False):
        has_finished = any(q['status'] == "Finished" for q in self.queue_items)
        if has_finished:
            # Default: remove only finished items
            self.queue_items = [q for q in self.queue_items if q['status'] != "Finished"]
        else:
            # No finished items — remove all pending (un-downloaded) items
            self.queue_items = [q for q in self.queue_items if q['status'] not in ("Pending",)]
        # Defer the expensive layout rebuild to avoid UI freeze while download thread is active
        QTimer.singleShot(0, self._refresh_queue_display)

    def cancel_batch_download(self, checked=False):
        self.cancel_download = True
        self.cancel_btn.setText("Cancelling...")
        self.cancel_btn.setEnabled(False)
        # Kill all running yt-dlp subprocesses immediately. Without this, a
        # download thread stuck in proc.stdout.readline() (waiting for yt-dlp
        # to finish its extraction retries) would not notice the cancel until
        # the subprocess eventually outputs a line — which can be 30-60s with
        # --retries 15. Killing the process gives readline an EOF right away.
        with self._active_ytdlp_procs_lock:
            for proc in list(self._active_ytdlp_procs):
                try:
                    proc.kill()
                except Exception:
                    pass

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
        
    def _on_batch_complete(self):
        self.is_downloading = False
        self.cancel_download = False
        self.dl_btn.setEnabled(True)
        self.dl_btn.setText("Download All")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.setText("Cancel")
        self.cancel_btn.setEnabled(True)
        if hasattr(self, 'run_renamer_cb') and self.run_renamer_cb.isChecked():
            self.run_mp3_renamer()
        if getattr(self, 'run_custom_script', False):
            self._run_custom_post_download_script()

    def on_run_renamer_toggled(self, checked):
        self.run_renamer = checked
        self.save_config()

    def on_path_changed(self, path):
        self.download_path = path
        self.save_config()

    def run_mp3_renamer(self):
        """Launches the integrated MP3 renamer interactive CLI in a new console window."""
        folder = self.path_combo.currentText()
        if not folder or not os.path.exists(folder):
            self._on_status_update("Renamer: Download folder path does not exist.", False, "red")
            return

        # The renamer is an interactive console program: it prints a banner and
        # colours and asks questions with input(). Packaged, the exe is windowed
        # and has no console of its own, so the renamer runs as a second copy of
        # this same exe with --renamer: the launcher inside the exe sees that
        # flag, allocates a console window for the copy and runs the CLI in it.
        # Run from source, it is this file re-run under python.exe with
        # --renamer: never pythonw.exe, which has no console to print into.
        if getattr(sys, 'frozen', False):
            args = [sys.executable, "--renamer", folder]
        else:
            args = [self._console_python(), os.path.abspath(__file__), "--renamer", folder]

        args.append(f'--norm={self.normalization_mode}')
        if self.auto_rename:
            args.append('--auto')
        args.append(f'--silence-pad={str(self.silence_pad_dur)}')
        args.append(f'--norm-threads={self.normalization_threads}')
        args.append(f'--silence-trim={"on" if self.silence_trim else "off"}')
        if self.use_custom_norm_cmd and self.custom_norm_cmd.strip():
            args.append(f'--custom-norm-cmd={self.custom_norm_cmd.strip()}')

        try:
            creationflags = 0x00000010 if sys.platform == "win32" else 0
            proc = subprocess.Popen(args, creationflags=creationflags)
            self._on_status_update("Launched MP3 Renamer in a new console window.", False, "#1abd33")

            def _wait_renamer():
                proc.wait()
                self.renamer_finished_signal.emit()

            threading.Thread(target=_wait_renamer, daemon=True).start()
        except Exception as e:
            self._on_status_update(f"Failed to launch MP3 Renamer: {str(e)}", False, "red")

    def _console_python(self):
        """Return a console-capable python executable (python.exe) so scripts can print/interact."""
        exe = sys.executable
        if getattr(sys, 'frozen', False):
            return "python"
        idx = exe.lower().rfind("pythonw")
        if idx != -1:
            exe = exe[:idx] + "python" + exe[idx + 7:]
        return exe

    def _run_custom_post_download_script(self):
        """Run the user-chosen file after a download batch finishes.
        Supports .py, .exe, .bat/.cmd, .ps1, and any file type Windows can open.
        The file receives the download folder as its first argument (when available),
        followed by the path of each downloaded file."""
        script = getattr(self, 'custom_script_path', '').strip()
        if not script:
            return
        if not os.path.isfile(script):
            self._on_status_update(f"Custom script not found: {script}", False, "#E31E24")
            return

        script = os.path.abspath(script)
        ext = os.path.splitext(script)[1].lower()
        folder = self.path_combo.currentText() if hasattr(self, 'path_combo') else ""
        if not folder or not os.path.isdir(folder):
            folder = ""
        files = [f for f in getattr(self, '_last_downloaded_files', []) if os.path.exists(f)]
        payload = ([folder] if folder else []) + files
        cwd = folder or os.path.dirname(script)

        interp_map = {
            '.py': [self._console_python()],
            '.bat': ['cmd.exe', '/c'],
            '.cmd': ['cmd.exe', '/c'],
            '.ps1': ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File'],
        }

        try:
            if ext in interp_map:
                cmd = interp_map[ext] + [script] + payload
                flags = 0x00000010 if sys.platform == "win32" else 0  # CREATE_NEW_CONSOLE
                subprocess.Popen(cmd, cwd=cwd, creationflags=flags)
            elif ext == '.exe':
                subprocess.Popen([script] + payload, cwd=cwd)
            else:
                # Unknown type: let Windows resolve it through its file associations.
                quoted = ' '.join(f'"{a}"' for a in payload)
                subprocess.Popen(f'"{script}" {quoted}'.strip(), shell=True, cwd=cwd)
            self._on_status_update(f"Ran custom script: {os.path.basename(script)}", False, "#1abd33")
        except Exception as e:
            self._on_status_update(f"Failed to run custom script: {e}", False, "#E31E24")

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Download Folder", self.path_combo.currentText() or "")
        if folder:
            if folder not in self.recent_folders:
                self.recent_folders.insert(0, folder)
                self.recent_folders = self.recent_folders[:5]
                self.path_combo.clear()
                self.path_combo.addItems(self.recent_folders)
            self.path_combo.setCurrentText(folder)
            self.save_config()

    def open_current_download_folder(self):
        path = self.path_combo.currentText()
        if path and os.path.exists(path):
            os.startfile(path)
        else:
            self._on_status_update("Download folder path does not exist.", False, "red")

    def open_current_local_folder(self):
        path = self.local_path_combo.currentText()
        if path and os.path.exists(path):
            os.startfile(path)
        else:
            self._on_status_update("Local folder path does not exist.", False, "red")

    def _dl_progress_percent(self, vid_id, percent):
        """Push one yt-dlp percentage onto the queue progress line."""
        if not vid_id or not percent:
            return

        finished_cnt = getattr(self, '_dl_finished_count', 0)
        total_cnt = getattr(self, '_batch_total_count', len(getattr(self, 'queue_items', [])))
        prog_prefix = f"({finished_cnt}/{total_cnt}) " if total_cnt > 0 else ""

        with self.active_downloads_lock:
            self.active_downloads[vid_id] = percent
            vals = list(self.active_downloads.values())
            if len(vals) > 5:
                self.dl_progress_signal.emit(f"{prog_prefix}Downloading: {', '.join(vals[:5])} (+{len(vals)-5} more)")
            else:
                self.dl_progress_signal.emit(f"{prog_prefix}Downloading: {', '.join(vals)}")

    # --- Player Logic ---
    def _on_status_update(self, text, is_playing, color):
        if is_playing:
            self.playing_label.setText(text)
        else:
            self.status_label.setText(f"   |   {text}" if self.playing_label.text() else text)
            if color == "white":
                self.status_label.setStyleSheet("font-size: 11px; margin-top: -2px;")
            else:
                self.status_label.setStyleSheet(f"color: {color}; font-size: 11px; margin-top: -2px;")
        if "Batch complete" in text or "Download cancelled" in text:
            self.dl_progress_signal.emit("")
            self._on_batch_complete()

    # ------------------------------------------------------------------
    # Next-track prefetch (section 8 of the AI Readme)
    # ------------------------------------------------------------------
    # Once the current track has PREFETCH_SECONDS_BEFORE_END seconds left, the track
    # that comes after it is resolved with yt-dlp on its own thread and its stream
    # URL is held ready. The GUI thread only decides which track that is; everything
    # slow happens in the prefetch thread, so the track playing now keeps playing
    # untouched. play_result() then finds the URL already there.

    def _playback_source_items(self):
        """(the list playback is stepping through, is it the local pane)."""
        if getattr(self, 'current_video_id', None) == "local":
            items = [x for x in getattr(self, 'current_local_items', []) if x.get('is_dir') is False]
            return items, True
        return (self.search_results or []), False

    def _next_playback_preview(self):
        """(index, video) for the track that would play next, changing nothing.

        This mirrors play_next()'s rules - local or searched, shuffled or in order -
        but mutates no state. With shuffle on, the random pick is made here and
        remembered in _prefetch_decision, because the prefetch has to fetch the same
        track the player will actually advance to. None means nothing follows.
        """
        items, is_local = self._playback_source_items()
        if not items:
            return None
        current_idx = getattr(self, 'local_playback_index', -1) if is_local else self.playback_index
        if getattr(self, 'is_shuffled', False):
            history = list(getattr(self, 'shuffle_history', []))
            unplayed = [i for i in range(len(items)) if i not in history]
            if not unplayed:
                unplayed = [i for i in range(len(items)) if i != current_idx]
            if not unplayed:
                return None
            next_idx = random.choice(unplayed)
        else:
            next_idx = current_idx + 1
            if not (0 <= next_idx < len(items)):
                return None
        video = items[next_idx]
        if not isinstance(video, dict):
            return None
        return next_idx, video

    def _prefetch_decision_for(self, vid_id):
        """(next index, next video) decided seconds ago for this track, or None if stale."""
        decision = getattr(self, '_prefetch_decision', None)
        if decision and vid_id and decision[0] == vid_id:
            return decision[1], decision[2]
        return None

    def _take_prefetched_stream(self, vid_id):
        """The stream URL resolved ahead of time for this track, consumed once, as
        (url, user agent, how old the URL already was in seconds). The age comes along because
        reading a URL ahead spends that much of its life before the player ever sees it, and
        the stream-liveness watchdog counts a loaded stream from when its URL was resolved.
        """
        with self._prefetch_lock:
            entry = self._prefetched_streams.pop(vid_id, None)
        if not entry:
            return None
        url, user_agent, resolved_at = entry
        age = time.monotonic() - resolved_at
        # A wall-clock stamp would be wrong whenever Windows corrects the clock, so the
        # age is measured with the monotonic clock - the same clock the stamp was taken
        # from in _prefetch_stream_worker().
        if age > PREFETCH_URL_MAX_AGE:
            return None
        return url, user_agent, age

    def _maybe_prefetch_next_track(self):
        """Called from the player timer once the current track is nearing its end.

        Everything done here is cheap: one preview, one remembered decision, and the
        start of a thread. The yt-dlp call itself never runs on the GUI thread.
        """
        if not getattr(self, 'search_results', None):
            return
        # Local files need no resolving, and a track that will not be followed
        # automatically needs nothing ready.
        if getattr(self, 'current_video_id', None) in (None, "", "local"):
            return
        if getattr(self, 'stop_after_current', STOP_AFTER_OFF):
            return
        current_id = self.current_video_id
        # One decision per track: the player timer fires every 16 ms and must not
        # re-decide (or re-fetch) the same track sixty times a second.
        if getattr(self, '_prefetch_trigger_key', None) == current_id:
            return
        preview = self._next_playback_preview()
        self._prefetch_trigger_key = current_id
        if not preview:
            self._prefetch_decision = None
            return
        next_idx, video = preview
        self._prefetch_decision = (current_id, next_idx, video)
        next_id = video.get('id')
        if not next_id:
            return
        with self._prefetch_lock:
            if next_id in self._prefetch_busy or next_id in self._prefetched_streams:
                return
            self._prefetch_busy.add(next_id)
        threading.Thread(target=self._prefetch_stream_worker, args=(next_id,), daemon=True).start()

    def _prefetch_stream_worker(self, vid_id):
        """Resolve one stream URL off the GUI thread. Failures stay silent: the normal
        play path resolves that track again when it is actually started."""
        try:
            url, user_agent = resolve_stream_url(vid_id)
            resolved = (url, user_agent, time.monotonic())
        except Exception:
            resolved = None
        finally:
            with self._prefetch_lock:
                self._prefetch_busy.discard(vid_id)
        if not resolved:
            return
        with self._prefetch_lock:
            self._prefetched_streams[vid_id] = resolved
            while len(self._prefetched_streams) > PREFETCH_CACHE_LIMIT:
                oldest = min(self._prefetched_streams, key=lambda k: self._prefetched_streams[k][2])
                self._prefetched_streams.pop(oldest, None)

    def invalidate_next_track_prefetch(self):
        """Forget a decided successor and any URL already resolved for it, so an
        outdated successor cannot be played as though it came from the new list."""
        self._prefetch_decision = None
        self._prefetch_trigger_key = None
        with self._prefetch_lock:
            self._prefetched_streams.clear()

    def _cancel_superseded_stream_fetches(self, keep_vid_id=None):
        """Stop the yt-dlp runs resolving stream URLs for tracks the listener no longer wants.

        Forgetting a URL that was already resolved is one thing (invalidate_next_track_prefetch);
        this is the other half - a resolution that is still running. Its answer is going to be
        discarded, it spends the seconds and the bandwidth a newer pick needs, and until now it
        ran to completion regardless. keep_vid_id is the track whose answer is still wanted:
        the one just clicked, or the one still on the player when a search is what superseded it.
        A killed run raises StreamFetchSupersededError in its own thread, which is how that
        thread knows to stay quiet rather than report the track as unplayable.
        """
        return cancel_stream_fetches(keep_vid_id=keep_vid_id)

    # ------------------------------------------------------------------
    # Keeping one track playing - a stream URL that stops answering
    # ------------------------------------------------------------------
    # The constants above STREAM_STALL_SECONDS explain why this exists. The rule the whole
    # block follows: only the media is replaced, never the track. Everything the listener is
    # relying on - the highlighted row, playback_index, shuffle_history, the stop-after state,
    # the decided successor - stays exactly where it is, and only the URL libVLC is reading is
    # swapped for a freshly resolved one of the same video.

    def _note_loaded_stream(self, vid_id, url=None, user_agent=None, url_age=0.0,
                            keep_pending_seek=False):
        """Record what the player has just been handed, and start the watchdog over.

        Called by the two paths that put media on the player: play_result()'s fetch thread,
        with the URL it resolved and how old that URL already was (one read ahead of the play
        by the prefetch thread is that much of the URL's life already spent), and
        _on_local_click(), with no id at all - which is how a file says "there is nothing here
        that can expire". keep_pending_seek is the refresh path's exception: a re-resolve has
        already decided where the listener should end up, and that has to survive the reset.
        """
        # Whatever the media before this one left behind - a finished track held for replay,
        # including the "stop after current" state that hold was made under, and a replay still
        # waiting for its media - ends with media arriving. The arming is kept rather than cleared,
        # so holding the new track again is still able to say what it was armed under. See
        # _hold_finished_track.
        self._finished_track = False
        self._replay_in_flight = False
        self._loaded_stream = (vid_id, url, user_agent, url_age) if vid_id and vid_id != "local" else None
        self._loaded_stream_at = time.monotonic() if self._loaded_stream else None
        self._stream_seen_ms = -1
        # None rather than "now": the stall clock for a fresh media starts the first time the
        # player actually reports Playing, so a stream that takes a while to open is not
        # judged for taking a while to open. Fresh media has not been stopped by the listener
        # either, so it is not a resumed one and does not get the longer clock one of those gets.
        self._stream_moved_at = None
        self._stream_resuming = False
        self._stream_dead = False
        self._stream_refetch_attempts = 0
        # Whether anybody has heard this particular media advancing. A refresh of a stream that
        # gave out mid-listen is the same listening carried onto new media, so it carries over;
        # anything else - including the track the session restore preloads paused at start up -
        # has not been listened to at all yet, and is not a stream that can have gone idle.
        # _stream_needs_renew uses this to keep age from reloading a track nobody has played.
        self._stream_listened = bool(keep_pending_seek and getattr(self, '_stream_listened', False))
        if not keep_pending_seek:
            self._pending_stream_seek_frac = None
            self._pending_stream_seek_ms = None
            self._pending_stream_pause = False
            self._pending_stream_seek_at = None
            self._stream_renew_started_at = None  # a different track starts with a clean allowance

    def _loaded_stream_age(self):
        """How long ago the URL the media on the player was built from was resolved."""
        stream = getattr(self, '_loaded_stream', None)
        started = getattr(self, '_loaded_stream_at', None)
        if not stream or started is None:
            return 0.0
        return (time.monotonic() - started) + float(stream[3] or 0.0)

    def _stream_is_moving(self):
        """Whether libVLC reported a position that was moving, recently.

        A stream that is measurably advancing is a stream that is working, whatever its age:
        a URL forty minutes old carrying a long mix is not swapped out from under somebody who
        is listening to it without a single problem.
        """
        moved_at = getattr(self, '_stream_moved_at', None)
        return moved_at is not None and (time.monotonic() - moved_at) <= STREAM_STALL_SECONDS

    def _stream_is_playing_now(self):
        """Whether the media on the player is, at this moment, a stream that is answering.

        The question every re-resolution is turned down by before anything else is weighed,
        because re-resolving a stream that is carrying the music replaces media that is working
        with a fetch that costs the listener time for nothing. libVLC answers it two ways: the
        state it reports, and the position it reports. Playing plus a position that has moved
        since the watchdog last looked is a stream that is working. Playing with a position that
        last moved further back than STREAM_STALL_SECONDS, a media that is paused or opening or
        buffering or ended, and a player that will not answer at all, are each a stream that
        cannot be *shown* to be working - which is not the same as a verdict that it is dead, and
        is why this only ever refuses a re-resolution rather than deciding anything.
        """
        if not getattr(self, '_loaded_stream', None) or self._stream_is_switching():
            return False
        player = getattr(self, 'vlc_player', None)
        if player is None:
            return False
        try:
            state = player.get_state()
            ms = player.get_time()
        except Exception:
            return False  # a player that will not answer is not one that is provably playing
        advanced = ms is not None and int(ms or 0) != int(getattr(self, '_stream_seen_ms', -1))
        if state == vlc.State.Playing and advanced:
            return True  # the position has moved since the watchdog last looked at it
        if state != vlc.State.Playing:
            return False
        return self._stream_is_moving()

    def _stream_is_switching(self):
        """True while the player is already being handed something else: a track still being
        fetched, or a dead stream already being re-resolved. Nothing in this block acts during
        either, because the media still on the player belongs to the previous track and acting
        on it would hijack a fetch the user started."""
        return bool(getattr(self, '_is_loading_stream', False) or getattr(self, '_stream_refetching', False))

    def _stream_needs_renew(self):
        """Whether the stream on the player should be re-resolved before it is asked for anything.

        Asked and answered first, every time: is this media playing right now? A stream libVLC
        reports as advancing is left exactly where it is, because a Play press and a scrub are both
        things a working stream answers, and swapping out the media that is carrying the music is
        the one thing this block must never do. Only a stream that cannot be shown to be advancing
        gets as far as the two answers below.

        Those two answers are yes: it was noticed dead - a position that stopped moving, or
        vlc.State.Error - and it is a stream the listener has actually been hearing whose URL has
        outlived STREAM_URL_MAX_AGE while the player is not advancing on it, which is the track
        left running into a link that has since died, or left idle on the player for longer than
        a YouTube URL lasts. Never for a local file, and never while a fetch or a refresh is
        already under way.

        The age of the URL only means something for a stream that has been listened to and has
        then stopped. A track preloaded at start up by the session restore, or one paused within
        the life of its URL, is media nobody is currently hearing: its URL grows old on the
        player without anything going wrong, and re-resolving it there lands the listener back at
        the top of the track, which reads as the track restarting itself. What that track needs is
        the URL it already has being tried, and the watchdog noticing within a few seconds whether
        it still answers - the same rule that already leaves a working stream alone however old
        its URL is.
        """
        if not getattr(self, '_loaded_stream', None) or self._stream_is_switching():
            return False
        if self._stream_is_playing_now():
            return False  # a stream that is answering is not a stream that is due for a new URL
        if getattr(self, '_stream_dead', False):
            return True
        if self._loaded_stream_age() <= STREAM_URL_MAX_AGE or self._stream_is_moving():
            return False
        return bool(getattr(self, '_stream_listened', False))

    def _mark_stream_dead(self):
        """Say once, in the status line, that the loaded stream has stopped delivering audio."""
        if getattr(self, '_stream_dead', False):
            return
        self._stream_dead = True
        title = (getattr(self, 'current_playing_title', '') or 'this track')
        if not getattr(self, 'is_playing', False):
            # Nothing reloads itself while the listener has the track stopped - the self-heal is
            # only for a stream he never asked to stop - so what this one needs is the play button,
            # which goes through the same verdict the watchdog just made.
            self._on_status_update(f"Stream stopped responding - Play will reload it: {title}", False, "#FF8C00")
        elif getattr(self, '_stream_refetch_attempts', 0) < STREAM_REFETCH_LIMIT:
            self._on_status_update(f"Stream stopped responding - reloading it: {title}", False, "#FF8C00")
        else:
            self._on_status_update(
                f"Stream stopped responding and would not reload - pick the track to start it again: {title}",
                False, "#E31E24")

    def _watch_stream_liveness(self, state, ms):
        """Run the loaded stream through the watchdog, once per player-timer tick.

        libVLC never reports "this URL died". A stream that stops answering either falls to
        vlc.State.Error or goes on claiming Playing with a position that has stopped moving,
        and those are the two things this can see. A position that moves is remembered, and if
        the stream had been marked dead it clears that and its allowance of self-healing
        attempts - a stream that dropped for a moment is not punished for it.

        What is not evidence of anything is a track the listener stopped. While the app does not
        want the audio - or libVLC reports the media Paused, Stopped or nothing at all - nothing
        here is expected to advance, so the stall clock is emptied rather than left running: a
        resume is judged on what the media does after it, never on the position it left behind.
        Read off a clock that kept counting through the pause, a track paused for longer than
        STREAM_STALL_SECONDS was convicted on the first tick after Play, before it had had the
        chance to reconnect and catch up, which re-fetched a stream that was still perfectly
        playable. A resumed track gets STREAM_RESUME_GRACE for the same reason. A dead stream the
        listener never asked to stop is reloaded on its own.
        """
        if not getattr(self, '_loaded_stream', None) or self._stream_is_switching():
            return
        if state == vlc.State.Error:
            self._mark_stream_dead()
            self._recover_stream_if_possible()
            return
        listener_stopped = (not getattr(self, 'is_playing', False)
                            or state in (vlc.State.Paused, vlc.State.Stopped, vlc.State.NothingSpecial))
        if listener_stopped:
            # A still position by request is not a stall, and the track is a resumed one from
            # here on: the clock starts again the first time the player is worth watching.
            self._stream_moved_at = None
            self._stream_resuming = True
            return
        if state != vlc.State.Playing:
            # Opening or Buffering: this media has not been given the chance to report a moving
            # position yet, so the clock is armed if nothing has armed it and nothing is judged
            # off it. A stream that takes a while to open is not judged for taking a while to open.
            if getattr(self, '_stream_moved_at', None) is None:
                self._stream_moved_at = time.monotonic()  # first tick this media has been worth watching
            return
        if getattr(self, '_stream_moved_at', None) is None:
            self._stream_moved_at = time.monotonic()  # first tick this media has been worth watching
        if ms is not None and ms != getattr(self, '_stream_seen_ms', -1):
            self._stream_seen_ms = ms
            self._stream_moved_at = time.monotonic()
            self._stream_resuming = False  # heard advancing: the grace a resumed track gets is paid for
            if getattr(self, 'is_playing', False) and int(ms or 0) > 0:
                # Somebody is hearing this media: from here on it is a stream that can go idle on
                # the listener's hands, which is the only kind the age of its URL is a reason to
                # reload. A media that has merely been loaded and left paused never gets here.
                self._stream_listened = True
            if getattr(self, '_stream_dead', False):
                self._stream_dead = False
                self._stream_refetch_attempts = 0
            return
        if getattr(self, '_stream_dead', False):
            return
        still_for = time.monotonic() - self._stream_moved_at
        allowed = STREAM_RESUME_GRACE if getattr(self, '_stream_resuming', False) else STREAM_STALL_SECONDS
        if still_for > allowed:
            self._stream_resuming = False  # the verdict is made; what follows is judged as ordinary playback
            self._mark_stream_dead()
            self._recover_stream_if_possible()

    def _recover_stream_if_possible(self):
        """Reload a dead stream by itself, and only while the listener never asked it to stop.

        STREAM_REFETCH_LIMIT is what keeps a genuinely unplayable track - one yt-dlp can no
        longer resolve at all - from turning into a fetch that retries itself forever.
        """
        if not getattr(self, 'is_playing', False):
            return False
        if getattr(self, '_stream_refetch_attempts', 0) >= STREAM_REFETCH_LIMIT:
            return False
        return self._renew_loaded_stream()

    def _stream_ended_short(self, total_ms, ms):
        """Whether the media that just reported vlc.State.Ended was a stream that gave up
        before its own length, rather than a track that finished.

        An expired URL ends the media exactly the way the end of a track does, and the only
        thing telling them apart is where the position stopped: a real ending stops a second or
        two short of the reported length, a dead stream stops well short of it. A length the
        media never reported is treated as a finished track, because there is nothing it could
        be short of, and a local file is the whole file - it is never short.
        """
        if not getattr(self, '_loaded_stream', None):
            return False
        if not total_ms or total_ms <= 0:
            return False
        return (int(total_ms) - int(ms)) > STREAM_END_SLACK_MS

    def _renew_loaded_stream(self, force=False):
        """Resolve the track already on the player all over again, and hand libVLC fresh media
        for it.

        This is not the track started again. The position it stopped at - or the row the user
        scrubbed to, or the point a Play press was meant to resume from - is held until the new
        media answers and then applied by the player timer (see _apply_pending_stream_seek), so
        it reads as one long buffer rather than as the song starting over. Nothing else moves:
        playback_index, the row in the list, shuffle_history, the stop-after state and the
        next-track read-ahead are all left exactly as they were, and _pending_fetch_id is the
        same guard play_result() uses, so a track the user picks during the refresh wins the
        player. _ended_trigger is held up for the duration so the dying media cannot spend
        itself as an "ended" track and move the playlist on mid-swap.

        The yt-dlp call runs on its own thread exactly as play_result()'s bg_fetch does, and it
        is that thread - not the GUI thread - that calls set_media and play: the thread that
        fetches a stream is the one that owns handing it to the player, which is the exception
        the play path already makes to the rule that a background thread stays out of VLC (that
        rule is about the *prefetch* thread, which must not touch the player at all). Everything
        that touches a Qt widget goes through stream_refreshed_signal instead. Returns True when
        a refresh is running or has just been started. force is for the listener asking for it
        directly - a Play press - which is rate limited by a thumb rather than by a dragged seek
        bar, and so does not have to wait out the cooldown.
        """
        stream = getattr(self, '_loaded_stream', None)
        if not stream or not getattr(self, 'vlc_instance', None) or not getattr(self, 'vlc_player', None):
            return False
        if getattr(self, '_stream_refetching', False):
            return True  # one refresh in flight per dead stream; a second scrub only adds a position
        vid_id = stream[0]
        if getattr(self, '_stream_refetch_attempts', 0) >= STREAM_REFETCH_LIMIT:
            return False  # _mark_stream_dead has already said so in the status line
        last_try = getattr(self, '_stream_renew_started_at', None)
        if not force and last_try is not None and (time.monotonic() - last_try) < STREAM_RENEW_COOLDOWN:
            # One yt-dlp call per track per cooldown, and no more. A dead stream is worth
            # reloading, but a seek bar being dragged across it is a hundred sliderMoved
            # signals, and each one would otherwise start its own fetch.
            return False
        player = self.vlc_player
        try:
            hold_ms = max(int(player.get_time() or 0), 0)
        except Exception:
            hold_ms = 0
        if hold_ms == 0:
            # A stream that has given up stops reporting a position altogether, and taking that at
            # its word lands the listener back at the top of the track - which is what makes a
            # reload read as the track starting over. The last position this media did report is
            # where the listener actually was, so that is the position held for the fresh media.
            hold_ms = max(int(getattr(self, '_stream_seen_ms', -1) or 0), 0)
        # Where to land: a scrub the user just asked for beats whatever the dead media thinks
        # its own position is, and only one of the two is ever left pending.
        if hold_ms > 0 and getattr(self, '_pending_stream_seek_frac', None) is None:
            self._pending_stream_seek_ms = hold_ms
        self._pending_stream_pause = not bool(getattr(self, 'is_playing', False))
        self._pending_stream_seek_at = time.monotonic()
        self._stream_renew_started_at = time.monotonic()
        self._stream_refetch_attempts += 1
        self._stream_refetching = True
        self._pending_fetch_id = vid_id
        self._is_loading_stream = True
        self._ended_trigger = True
        title = (getattr(self, 'current_playing_title', '') or vid_id)
        self._on_status_update(f"Re-fetching stream: {title}...", False, "#3B8ED0")

        def bg_renew():
            try:
                url, user_agent = resolve_stream_url(vid_id)
            except StreamFetchSupersededError:
                # Another track was picked while this reload was running, and its own fetch owns
                # the player now. The in-flight flag has to come off here: it is what lets the
                # watchdog reload the next dead stream, and this refresh is never finishing.
                self._stream_refetching = False
                return
            except Exception as e:
                print(f"Stream refresh error: {e}")
                self._stream_refetching = False
                if getattr(self, '_pending_fetch_id', None) == vid_id:
                    self._is_loading_stream = False
                self.stream_refreshed_signal.emit(False, title)
                return
            if getattr(self, '_pending_fetch_id', None) != vid_id:
                return  # another track was started during the refresh; that one owns the player now
            media = self.vlc_instance.media_new(url)
            media.add_option(f':http-user-agent={user_agent}')
            self.vlc_player.set_media(media)
            self.vlc_player.play()
            self._note_loaded_stream(vid_id, url, user_agent, 0.0, keep_pending_seek=True)
            self._stream_refetching = False
            self._is_loading_stream = False
            self.stream_refreshed_signal.emit(True, title)
        threading.Thread(target=bg_renew, daemon=True).start()
        return True

    def _apply_pending_stream_seek(self):
        """Put the listener where they were - or where they asked to be - on freshly resolved media.

        Neither a restored position nor a scrubbed-to one can be set on a media that has not
        opened yet: libVLC says nothing about a stream it has not read, and that is the other
        half of why a dead stream looked unresponsive. Both wait here until the player reports
        Playing, then are applied once. A scrub is held as a fraction of the track for the same
        reason - a media that is not open again reports no length to turn it into milliseconds.
        A request nothing accepted within STREAM_SEEK_RESTORE_TIMEOUT seconds is dropped rather
        than left to pounce on the track minutes later.
        """
        player = getattr(self, 'vlc_player', None)
        if player is None:
            return
        asked_frac = getattr(self, '_pending_stream_seek_frac', None)
        asked_ms = getattr(self, '_pending_stream_seek_ms', None)
        asked_pause = bool(getattr(self, '_pending_stream_pause', False))
        if asked_frac is None and asked_ms is None and not asked_pause:
            return
        started_at = getattr(self, '_pending_stream_seek_at', None)
        if started_at is not None and (time.monotonic() - started_at) > STREAM_SEEK_RESTORE_TIMEOUT:
            self._pending_stream_seek_frac = None
            self._pending_stream_seek_ms = None
            self._pending_stream_pause = False
            return
        if asked_frac is not None:
            if player.set_position(asked_frac) not in (0, None):
                return
            self._pending_stream_seek_frac = None
        elif asked_ms is not None:
            if player.set_time(int(asked_ms)) not in (0, None):
                return
            self._pending_stream_seek_ms = None
        if asked_pause:
            player.set_pause(1)
            self._pending_stream_pause = False

    def _on_stream_refreshed(self, ok, title):
        """The GUI-thread half of a stream refresh, reported from the thread that ran it."""
        if ok:
            self._update_play_button()
            if getattr(self, 'is_playing', False):
                self._on_status_update(f"Playing: {title}", True, "gray")
            else:
                self._on_status_update(f"Ready: {title}", True, "gray")
        else:
            self._on_status_update(f"Could not re-fetch the stream for {title} - pick the track to try again.",
                                   False, "#E31E24")
            if getattr(self, '_replay_in_flight', False):
                # A replay started this re-fetch, and the media it was meant to replace is still
                # the finished one. Nothing about that media changed, so the press that failed
                # leaves the button as the one thing it can still do with it: ask again, from the
                # beginning. A failed self-heal of a stream that gave out part-way through is not
                # that, and is left as it has always been left - the next Play press goes through
                # _stream_needs_renew() and picks the track up where it stopped.
                self._hold_finished_track()

    # ------------------------------------------------------------------
    # "Stop after current" - three states, one click each
    # ------------------------------------------------------------------
    # Off    : a track ending advances to the next one, exactly as it always did.
    # Once   : the current track is the last one; when it ends the state resets to Off
    #          and the track stays stopped where it is.
    # Always : every track stops when it ends and stays stopped, until clicked again.
    # One click walks the cycle Off -> Once -> Always -> Off, from the player-bar
    # button or from the tray menu. A manual "Next Track" always advances regardless.

    def cycle_stop_after_current(self):
        """Move to the next state in the off -> once -> always -> off cycle."""
        current = getattr(self, 'stop_after_current', STOP_AFTER_OFF)
        # A click is the user taking the state in hand, so an arming a search left
        # behind is no longer what he wants and goes with it.
        self._search_stop_after_track = None
        self.set_stop_after_current((int(current) + 1) % 3)
        # A click is the only way this state is ever chosen, so this is where the choice
        # is written out - the same as every control in the Settings dialog, and before
        # the close: a crash, a killed process or a Windows shutdown never reach
        # closeEvent(), and "always" is a standing instruction the user expects to still
        # be there when the window comes back. The automatic handlings deliberately do
        # not write: a "once" armed by a new search, released by another track or spent by
        # a finished one is not something the user chose, and load_config() never restores
        # it anyway.
        self.save_config()

    def set_stop_after_current(self, state):
        try:
            state = int(state)
        except (TypeError, ValueError):
            state = STOP_AFTER_OFF
        if state not in (STOP_AFTER_OFF, STOP_AFTER_ONCE, STOP_AFTER_ALWAYS):
            state = STOP_AFTER_OFF
        self.stop_after_current = state
        self._update_stop_after_ui()
        if state == STOP_AFTER_OFF:
            self._on_status_update("Stop after current: off - playback will advance to the next track.", False, "white")
        elif state == STOP_AFTER_ONCE:
            self._on_status_update("Stop after current: once - this track is the last one.", False, "#FF8C00")
        else:
            self._on_status_update("Stop after current: always - every track stops when it ends.", False, "#E31E24")

    def _update_stop_after_ui(self):
        """Reflect the state in the player-bar button. The tray menu is rebuilt every
        time it opens (_build_tray_menu), so it needs no live update."""
        btn = getattr(self, 'stop_after_btn', None)
        if btn is None:
            return
        state = getattr(self, 'stop_after_current', STOP_AFTER_OFF)
        btn.setProperty("stop_after_state", STOP_AFTER_STATE_NAMES[state])
        btn.setToolTip(STOP_AFTER_TOOLTIPS[state])
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def _finish_stop_after_current(self):
        """A track ended while "stop after current" was armed: hold here instead of
        advancing, and spend the one-shot state back to off."""
        self.is_playing = False
        self._update_play_button()
        # The successor readied seconds ago is not wanted now; its resolved URL stays
        # in the cache in case the user presses Next themselves. The trigger key goes
        # too, so a track the user starts again by hand reads ahead once more.
        self._prefetch_decision = None
        self._prefetch_trigger_key = None
        # Whichever way the arming was set - the button or a new search - it has now
        # been spent on the track that just finished.
        self._search_stop_after_track = None
        if getattr(self, 'stop_after_current', STOP_AFTER_OFF) == STOP_AFTER_ONCE:
            self.set_stop_after_current(STOP_AFTER_OFF)
            self._on_status_update("Stopped after the current track.", False, "gray")
        else:
            self._on_status_update("Stopped after the current track - Stop after current is still on.", False, "gray")

    def _update_play_button(self):
        """Redraw the player-bar button to say what pressing it would do right now: start a
        stopped track, pause a playing one, or start a finished one again from the beginning.

        Every path that changes what that button means goes through here rather than setting a
        caption itself, because the three states share one 44-pixel button. A replay caption that
        is only a different picture is the same as no caption at all, so the tooltip travels with
        the glyph.
        """
        btn = getattr(self, 'play_btn', None)
        if btn is None:
            return  # the state is right; the player bar has simply not been built yet
        if getattr(self, '_finished_track', False):
            btn.setText(REPLAY_GLYPH)
            btn.setToolTip("Replay - play this track again from the beginning")
            return
        btn.setText(PAUSE_GLYPH if getattr(self, 'is_playing', False) else PLAY_GLYPH)
        btn.setToolTip("Play / Pause")

    def _player_media_is_finished(self):
        """Whether a press of the play button can only mean "this track all over again".

        The armed hold is the app's own verdict on a track it chose to keep. The vlc.State.Ended half
        catches the same media in a state no hold was armed for - a track that reached its end while
        the listener had it stopped, so the auto-advance gate skipped it and nothing ever offered the
        ending as anything - instead of leaving them pressing against a media libVLC has finished
        with. Nothing answers while a fetch or a refresh is already under way: that media belongs to
        a track the user started, and a replay would take the player out from under it.
        """
        if self._stream_is_switching():
            return False
        if getattr(self, '_finished_track', False):
            return True
        player = getattr(self, 'vlc_player', None)
        if player is None:
            return False
        try:
            if player.get_state() != vlc.State.Ended:
                return False
            ms = player.get_time()
            total_ms = player.get_length()
        except Exception:
            return False
        # An Ended that is really a stream whose URL gave out part-way through is not a finished
        # track, and the promise attached to it is the other one: pick up where it stopped. That
        # is what _stream_needs_renew() answers for a track whose automatic reloads ran out, and a
        # replay here would answer it from 0:00 instead - the listener's place thrown away because
        # the media happened to report the same state a real ending does.
        if self._stream_ended_short(total_ms, ms):
            return False
        return True

    def _hold_finished_track(self, armed_under=None):
        """Leave a finished track sitting on the player, with the way back to it on the button.

        The media is over and libVLC is done with it - it answers no seek, no pause and no
        resume - so the only press that does anything is the one that starts the track again. The
        listener keeps a track they can hear again from the player bar instead of one they have
        to pick back out of the list. Nothing about the track itself moves: the row,
        playback_index, shuffle_history and the stop-after state all stay where they were, so a
        replay is the same track and a Next is still the track after it.

        armed_under is the "stop after current" state this hold was made under, remembered so a
        replay of this same track can put that state back (see _replay_finished_track). Left out,
        the hold keeps whatever mode the previous hold recorded.
        """
        if armed_under is not None:
            self._finished_track_armed_under = int(armed_under)
        self._finished_track = True
        self._replay_in_flight = False  # nothing is mid-flight any more; the hold is the verdict
        self.is_playing = False  # nothing is playing, and the button must not pretend otherwise
        # The successor readied seconds ago is not wanted by a hold, and a track the user starts
        # again from here reads its own successor ahead once the hold is lifted.
        self._prefetch_decision = None
        self._prefetch_trigger_key = None
        self._update_play_button()

    def _replay_finished_track(self, at_frac=None):
        """Hear the finished track all over again - from the top, or from wherever the scrubber
        was put. Returns True when the replay is under way.

        For a stream this is a re-fetch rather than a rewind, and for one reason: the media on the
        player has finished, and the signed URL it was built from was played out with it. The
        video id, the row, playback_index and shuffle_history are untouched, so the fresh media is
        the same track, and the position asked for rides along as a pending seek for
        _apply_pending_stream_seek to land on the first tick that reports Playing. The top of the
        track counts as a position asked for: left to itself, _renew_loaded_stream holds the
        position the finished media last reported, and on a track that finished that is its own end
        - the fresh media would open where the old one stopped and finish again at once.

        The allowance of self-healing re-resolutions is handed back in full, exactly as a Play
        press on a dead stream hands it back: this is the listener asking for the music, and a
        track that spent its reloads on the way here has not been asked for since.
        """
        player = getattr(self, 'vlc_player', None)
        if player is None or self._stream_is_switching():
            return False
        armed_under = int(getattr(self, '_finished_track_armed_under', STOP_AFTER_OFF))
        self._finished_track = False
        self.is_playing = True
        self._stream_dead = False
        self._stream_refetch_attempts = 0
        # A "once" spent on the track that finished was spent on this very track, and a replay is
        # that track heard again. Letting the replayed one advance would drop the listener onto a
        # track they never picked - the thing "stop after current" exists to prevent - so the state
        # is put back, and the button says so. An "always" is still armed as it was, and a hold no
        # state caused has nothing to put back.
        if armed_under == STOP_AFTER_ONCE and getattr(self, 'stop_after_current', STOP_AFTER_OFF) == STOP_AFTER_OFF:
            self.set_stop_after_current(STOP_AFTER_ONCE)
        self._update_play_button()  # a pause button again: the replay is what is playing now
        frac = 0.0 if at_frac is None else max(0.0, min(1.0, float(at_frac)))
        if getattr(self, '_loaded_stream', None):
            self._pending_stream_seek_frac = frac
            self._pending_stream_seek_ms = None
            self._pending_stream_pause = False
            self._pending_stream_seek_at = time.monotonic()
            self._replay_in_flight = True
            if self._renew_loaded_stream(force=True):
                return True
            # Nothing left to re-resolve, or a refresh this press joined on the way to: the
            # position asked for still stands, and it is the media itself that gets restarted.
            self._replay_in_flight = False
        self._pending_stream_seek_frac = frac if frac > 0.0 else None
        self._pending_stream_seek_ms = None
        self._pending_stream_seek_at = time.monotonic() if frac > 0.0 else None
        self._pending_stream_pause = False
        player.play()
        title = (getattr(self, 'current_playing_title', '') or 'this track')
        self._on_status_update(f"Replaying: {title}", True, "gray")
        return True

    def _stream_track_in_progress(self):
        """The video id of the stream the player is committed to, or None when there
        is no stream for a new search to interrupt.

        "Committed" covers a stream playing, paused, or still being resolved by
        yt-dlp: a paused track resumes and then advances exactly like one that was
        playing, and a track being fetched starts on its own the moment yt-dlp
        answers. Local files are left out on purpose - a search replaces
        search_results, which is the list a searched track steps through, and it
        leaves the folder list a local file steps through untouched.
        """
        if getattr(self, '_is_loading_stream', False):
            return getattr(self, '_pending_fetch_id', None) or None
        vid_id = getattr(self, 'current_video_id', None)
        if not vid_id or vid_id == "local":
            return None
        player = getattr(self, 'vlc_player', None)
        if player is None:
            return None
        if player.get_state() not in (vlc.State.Playing, vlc.State.Paused):
            return None
        return vid_id

    def _arm_stop_after_for_new_search(self):
        """Arm "stop after current: once" for the track playing when a new search lands.

        play_next() steps through search_results by index, and a new search replaces
        search_results underneath the track that is already playing. That track is
        still a track of the previous list, but its index now counts into the new
        one, so when it finished the listener was dropped into the middle of the
        search they had just run - which looked like the player moving on to some
        video at random. The one-shot state makes the track already playing the last
        one of the list it came from, and leaves the new search to be started by
        hand. Returns True only when it armed: a state the user chose by clicking is
        never overwritten, and a search with no stream in progress arms nothing.
        """
        if getattr(self, 'stop_after_current', STOP_AFTER_OFF) != STOP_AFTER_OFF:
            return False
        vid_id = self._stream_track_in_progress()
        if not vid_id:
            return False
        self._search_stop_after_track = vid_id
        self.set_stop_after_current(STOP_AFTER_ONCE)
        return True

    def _release_search_stop_after(self, new_vid_id=None):
        """Forget a "once" that a search armed, as opposed to one the user clicked.

        Such an arming belongs to one track only. Once a different track starts - a
        row clicked in the new list, a manual Next or Previous, a file from the local
        pane - it has nothing left to protect, and leaving it armed would have
        stopped the track the user just chose after it finished. The same track
        started again keeps its arming, because it still came from the old list.
        """
        armed_for = getattr(self, '_search_stop_after_track', None)
        if not armed_for:
            return
        if new_vid_id and new_vid_id == armed_for:
            return
        self._search_stop_after_track = None
        if getattr(self, 'stop_after_current', STOP_AFTER_OFF) == STOP_AFTER_ONCE:
            self.set_stop_after_current(STOP_AFTER_OFF)

    def play_result(self, video, paused_at_start=False, from_nav=False):
        # If VLC is still initializing in background, defer and retry
        if not getattr(self, '_vlc_ready', False):
            QTimer.singleShot(200, lambda: self.play_result(video, paused_at_start, from_nav))
            return
        if self.vlc_instance is None or self.vlc_player is None:
            self._on_status_update("Playback unavailable: VLC Media Player is not installed.", False, "#E31E24")
            return

        self._on_status_update(f"Fetching stream: {video.get('title', 'Unknown')}...", False, "#3B8ED0")
        
        # Track pending fetch ID and loading state
        vid_id = video.get('id', '')
        # The one-shot a search armed belongs to the track that was playing when that
        # search ran. The track the user has just picked is not it, so the arming is
        # dropped here instead of stopping this track after it ends.
        self._release_search_stop_after(vid_id)
        self._pending_fetch_id = vid_id
        # This track now owns the player, so every stream URL still being resolved for another
        # one - the read-ahead's pick, an earlier click, a reload of the track just replaced -
        # is stopped instead of running to completion for an answer that is about to be thrown
        # away. The resolution belonging to this track is left alone, including the prefetched
        # URL that bg_fetch below may be about to pick up.
        if self._cancel_superseded_stream_fetches(keep_vid_id=vid_id):
            # A reload of the track just replaced was the only thing holding the "a refresh is
            # in flight" flag, and that refresh can never finish now. Left set, it would make
            # _renew_loaded_stream refuse to reload any later stream either.
            self._stream_refetching = False
        self._is_loading_stream = True
        self._has_played_current = False
        self._ended_trigger = True
        
        # update index
        self.playback_index = -1
        for i, res in enumerate(self.search_results):
            if res.get('id') == vid_id:
                self.playback_index = i; break

        if not from_nav:
            # User manually clicked a track: reset shuffle history with this track
            self.shuffle_history = [self.playback_index] if self.playback_index >= 0 else []
                
        def bg_fetch():
            try:
                # Resolved seconds ago by the prefetch thread? Use that and skip yt-dlp
                # entirely - this is what removes the gap at a changeover.
                prefetched = self._take_prefetched_stream(vid_id)
                if prefetched:
                    url, user_agent, url_age = prefetched
                else:
                    url, user_agent = resolve_stream_url(vid_id)
                    url_age = 0.0

                # If another stream request started while fetching, ignore this one
                if getattr(self, '_pending_fetch_id', None) != vid_id:
                    return

                media = self.vlc_instance.media_new(url)
                media.add_option(f':http-user-agent={user_agent}')
                self.vlc_player.set_media(media)
                if paused_at_start:
                    self.vlc_player.audio_set_mute(True)
                    self.vlc_player.play()
                    time.sleep(0.25)
                    self.vlc_player.set_pause(1)
                    self.vlc_player.set_position(0)
                    self.vlc_player.audio_set_mute(False)
                else:
                    self.vlc_player.play()
                self._is_loading_stream = False
                # Remember what the player is now loaded with, so that a stream which stops
                # answering later can be re-resolved without this track being picked out of the
                # list again - and so that a track left paused past the life of its URL can be
                # picked up where it stopped.
                self._note_loaded_stream(vid_id, url, user_agent, url_age)
                self.playback_started_signal.emit(video.get('title', 'Unknown'), vid_id, paused_at_start)
            except StreamFetchSupersededError:
                # Stopped on purpose by a newer pick. That pick reports its own state, so this
                # track is not a failure and the status line is not touched by it.
                return
            except Exception as e:
                print(f"Stream error: {e}")
                if getattr(self, '_pending_fetch_id', None) == vid_id:
                    self._is_loading_stream = False
                self.search_failed_signal.emit()
        threading.Thread(target=bg_fetch, daemon=True).start()

    def _on_playback_started(self, title, vid_id, paused_at_start=False):
        self.current_playing_title = title
        self.current_video_id = vid_id
        if paused_at_start:
            self.is_playing = False
            self._update_play_button()
            self._on_status_update(f"Ready: {title}", True, "gray")
        else:
            self.is_playing = True
            self._update_play_button()
            self._on_status_update(f"Playing: {title}", True, "gray")

    def eventFilter(self, obj, event):
        if event.type() == event.Type.KeyPress:
            fw = QApplication.focusWidget()
            if event.key() == Qt.Key_Space and not isinstance(fw, QLineEdit):
                self.toggle_playback()
                return True
            # File Explorer style keys, but only while the local file list has focus.
            if self._focus_is_in_local_pane(fw):
                if event.key() == Qt.Key_Escape:
                    self.clear_local_selection()
                    return True
                if not isinstance(fw, (QLineEdit, QComboBox)):
                    if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                        self.delete_local_selected()
                        return True
                    if event.key() == Qt.Key_F2:
                        self.rename_local_selected()
                        return True
                    if event.key() == Qt.Key_A and event.modifiers() & Qt.ControlModifier:
                        self.select_all_local_files()
                        return True
                    if event.key() == Qt.Key_C and event.modifiers() & Qt.ControlModifier:
                        self.copy_local_selected()
                        return True
                    if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                        self._open_local_selection()
                        return True
        return super().eventFilter(obj, event)

    def open_search_on_youtube(self):
        query = self.search_entry.text().strip()
        if not query: return
        if 'youtube.com' in query or 'youtu.be' in query:
            webbrowser.open(query)
        else:
            webbrowser.open(f'https://www.youtube.com/results?search_query={urllib.parse.quote(query)}')

    def toggle_playback(self):
        if not self.vlc_player: return
        if self._player_media_is_finished():
            # The media on the player has finished and nothing was started after it, so this press
            # is not a resume - there is nothing left to resume. It is a replay: the same track
            # started again from the top, which is what the button now says it does. For a stream
            # "started again" means on freshly resolved media, because the URL the finished one was
            # built from has been played out (see _replay_finished_track).
            if self._replay_finished_track():
                return
        if self._stream_needs_renew():
            # Pressing play on a stream that has stopped answering is the listener asking for the
            # music, not for the media that happens to be loaded: a dead media answers neither a
            # play nor a seek, which is exactly what made this look like a play button that does
            # nothing. Re-resolve this same track and pick up where it stopped - a play the user
            # asked for gets the whole allowance back, is not held by the seek cooldown, and
            # leaves the app wanting the track playing even if the cooldown still has this one
            # waiting, because the next press of the button goes through.
            self.is_playing = True
            self._update_play_button()
            self._stream_refetch_attempts = 0
            self._renew_loaded_stream(force=True)
            return
        if getattr(self, '_loaded_stream', None) and getattr(self, '_stream_refetching', False):
            # Play pressed while the re-resolution the previous press started is still running:
            # the fresh media is already on its way, so all this means is "play it when it lands"
            # - the queued position stops asking for a pause, and the dying media is not paused
            # and unpaused behind a fetch that is about to replace it.
            self.is_playing = True
            self._update_play_button()
            self._pending_stream_pause = False
            self._pending_stream_seek_at = time.monotonic()
            return
        if self.vlc_player.is_playing():
            # The stall clock stops with the pause instead of running through it, so a track
            # resumed later is judged on what it does after the resume and never on the position it
            # left behind (see _watch_stream_liveness). The watchdog holds it tick by tick as well;
            # this is what covers a pause and a Play that fall inside one 16 ms tick.
            self._stream_moved_at = None
            self._stream_resuming = True
            self.vlc_player.pause()
            self.is_playing = False
            self._update_play_button()
        else:
            self.vlc_player.play()
            self.is_playing = True
            self._update_play_button()

    def toggle_shuffle(self):
        self.is_shuffled = not self.is_shuffled
        self.update_shuffle_btn_style()
        if self.is_shuffled:
            if self.current_video_id == "local" and hasattr(self, 'local_playback_index') and self.local_playback_index >= 0:
                self.shuffle_history = [self.local_playback_index]
            elif self.playback_index >= 0:
                self.shuffle_history = [self.playback_index]
            else:
                self.shuffle_history = []
        else:
            self.shuffle_history = []

    def update_shuffle_btn_style(self):
        if hasattr(self, 'shuffle_btn'):
            self.shuffle_btn.setProperty("active", "true" if getattr(self, 'is_shuffled', False) else "false")
            self.shuffle_btn.style().unpolish(self.shuffle_btn)
            self.shuffle_btn.style().polish(self.shuffle_btn)

    def play_previous(self):
        if self.current_video_id == "local" and hasattr(self, 'local_playback_index'):
            audio_files = [x for x in getattr(self, 'current_local_items', []) if x.get('is_dir') is False]
            if not audio_files: return
            if getattr(self, 'is_shuffled', False):
                hist = getattr(self, 'shuffle_history', [])
                if len(hist) > 1:
                    hist.pop()  # remove current
                    prev_idx = hist[-1]
                    if 0 <= prev_idx < len(audio_files):
                        self.local_playback_index = prev_idx
                        self._on_local_click(audio_files[prev_idx], from_nav=True)
                        return
            if self.local_playback_index > 0:
                self.local_playback_index -= 1
                self._on_local_click(audio_files[self.local_playback_index], from_nav=True)
            return
            
        if not self.search_results: return
        if getattr(self, 'is_shuffled', False):
            hist = getattr(self, 'shuffle_history', [])
            if len(hist) > 1:
                hist.pop()  # remove current
                prev_idx = hist[-1]
                if 0 <= prev_idx < len(self.search_results):
                    self.playback_index = prev_idx
                    self.play_result(self.search_results[prev_idx], from_nav=True)
                    return
        if self.playback_index > 0:
            self.playback_index -= 1
            self.play_result(self.search_results[self.playback_index], from_nav=True)
            
    def play_next(self):
        if self.current_video_id == "local" and hasattr(self, 'local_playback_index'):
            audio_files = [x for x in getattr(self, 'current_local_items', []) if x.get('is_dir') is False]
            if not audio_files: return
            if getattr(self, 'is_shuffled', False):
                if not hasattr(self, 'shuffle_history'):
                    self.shuffle_history = []
                unplayed = [i for i in range(len(audio_files)) if i not in self.shuffle_history]
                if not unplayed:
                    self.shuffle_history = [self.local_playback_index] if hasattr(self, 'local_playback_index') else []
                    unplayed = [i for i in range(len(audio_files)) if i != getattr(self, 'local_playback_index', -1)]
                if unplayed:
                    next_idx = random.choice(unplayed)
                    self.shuffle_history.append(next_idx)
                    self.local_playback_index = next_idx
                    self._on_local_click(audio_files[next_idx], from_nav=True)
                    return
                elif len(audio_files) == 1:
                    self._on_local_click(audio_files[0], from_nav=True)
                    return
            if self.local_playback_index + 1 < len(audio_files):
                self.local_playback_index += 1
                self._on_local_click(audio_files[self.local_playback_index], from_nav=True)
            return
            
        if not self.search_results: return

        # A successor decided seconds ago (see _maybe_prefetch_next_track) is honoured
        # first, so the stream that was already resolved is the stream that plays.
        decided = self._prefetch_decision_for(getattr(self, 'current_video_id', ''))
        if decided is not None:
            self._prefetch_decision = None
            next_idx, next_video = decided
            if (next_video is not None and 0 <= next_idx < len(self.search_results)
                    and self.search_results[next_idx].get('id') == next_video.get('id')):
                if getattr(self, 'is_shuffled', False):
                    self.shuffle_history.append(next_idx)
                self.playback_index = next_idx
                self.play_result(next_video, from_nav=True)
                return

        if getattr(self, 'is_shuffled', False):
            if not hasattr(self, 'shuffle_history'):
                self.shuffle_history = []
            unplayed = [i for i in range(len(self.search_results)) if i not in self.shuffle_history]
            if not unplayed:
                self.shuffle_history = [self.playback_index] if self.playback_index >= 0 else []
                unplayed = [i for i in range(len(self.search_results)) if i != self.playback_index]
            if unplayed:
                next_idx = random.choice(unplayed)
                self.shuffle_history.append(next_idx)
                self.playback_index = next_idx
                self.play_result(self.search_results[next_idx], from_nav=True)
                return
            elif len(self.search_results) == 1:
                self.play_result(self.search_results[0], from_nav=True)
                return
        if self.playback_index + 1 < len(self.search_results):
            self.playback_index += 1
            self.play_result(self.search_results[self.playback_index], from_nav=True)

    def on_seek(self, val):
        if not self.vlc_player:
            return
        frac = float(val) / 10000.0
        if self._player_media_is_finished():
            # The media on the player has run to its end, and a media libVLC is done with answers
            # no seek at all: the bar moved and nothing else did, which is how dragging back after
            # a track finished used to do nothing whatsoever. What the bar is asking for here is
            # the track again from where it was put, so the scrub goes down as a replay and the
            # position rides along to whatever media answers it.
            if self._replay_finished_track(at_frac=frac):
                return
        if self._stream_needs_renew() or getattr(self, '_stream_refetching', False):
            # Scrubbing a stream that has stopped answering does nothing at all, and that is how
            # the whole problem hid: the slider moved and libVLC ignored it. Keep the position
            # they asked for - as a fraction, because a media that is not open again reports no
            # length to convert it - and re-resolve this same track; _apply_pending_stream_seek
            # puts them there once the fresh media answers. A drag that keeps moving only ever
            # queues the last position asked for, because one refresh is enough for one dead
            # stream and STREAM_RENEW_COOLDOWN keeps a dragged bar from becoming a fetch storm.
            self._pending_stream_seek_frac = frac
            self._pending_stream_seek_ms = None
            if self._renew_loaded_stream():
                return
            # Nothing worth re-resolving - the cooldown is still running, or this track has used
            # up its attempts. That is no reason to ignore the scrub itself, so ask the media the
            # ordinary way and let the listener drag the bar as they always could.
            self._pending_stream_seek_frac = None
        self.vlc_player.set_position(frac)

    def on_volume_changed(self, val):
        self.volume_val = val
        if self.vlc_player:
            # libVLC's volume is a percentage of amplitude with 100 = 0 dB, so the number the slider
            # shows is the number the player is told: 150 is 1.5x, about +3.5 dB. It used to be
            # doubled onto 200, which made 150% on the label mean 2x (+6 dB) in the audio output.
            self.vlc_player.audio_set_volume(val)
        if hasattr(self, 'vol_pct'):
            self.vol_pct.setText(f"{val}%")
            if val > 115:
                self.vol_pct.setStyleSheet("color: #E31E24; font-weight: bold;")
                self.vol_slider.setProperty("volume_state", "red")
            elif val > 100:
                self.vol_pct.setStyleSheet("color: #FF8C00; font-weight: bold;")
                self.vol_slider.setProperty("volume_state", "orange")
            else:
                self.vol_pct.setStyleSheet("")
                self.vol_slider.setProperty("volume_state", "normal")
            self.vol_slider.style().unpolish(self.vol_slider)
            self.vol_slider.style().polish(self.vol_slider)

    def update_player_ui(self):
        # The tick that already asks libVLC what the media is doing is the one place in
        # this app that knows the play state, so it is the one place that colours the row
        # of the track that state belongs to.
        self._refresh_playback_highlights()
        title = getattr(self, 'current_playing_title', '').strip()
        time_txt = ""

        if self.vlc_player and self.current_video_id:
            state = self.vlc_player.get_state()
            pos = self.vlc_player.get_position() * 10000
            ms = self.vlc_player.get_time()
            total_ms = self.vlc_player.get_length()
            # This timer is also what notices that a stream has stopped answering, because
            # libVLC never reports it itself - see the stream-liveness block above "Stop after
            # current". The position it reports is the only evidence there is.
            self._watch_stream_liveness(state, ms)
            if state == vlc.State.Playing:
                self._has_played_current = True
                if not getattr(self, '_stream_refetching', False):
                    # A refresh in flight means this Playing still belongs to the dying media: its
                    # ending is being held by _renew_loaded_stream, and a position queued for the
                    # fresh media must not be spent on the media that is about to be replaced. The
                    # fresh media reporting Playing both clears the held ending and lands the
                    # position, which is what makes the whole thing read as one continuous buffer.
                    self._ended_trigger = False
                    self._apply_pending_stream_seek()
            elif state == vlc.State.Ended:
                # ONLY trigger auto-advance if this track actually played and hasn't triggered ended yet
                if getattr(self, '_has_played_current', False) and not getattr(self, '_ended_trigger', False) and getattr(self, 'is_playing', False):
                    if self._stream_ended_short(total_ms, ms) and self._recover_stream_if_possible():
                        # A stream whose URL gave out mid-track reports the same Ending as a track
                        # that finished, so this one is held rather than advanced: the track the
                        # listener was hearing is the one worth saving. The fresh media reporting
                        # Playing puts both of these flags back on its own. A reload that has
                        # already used up its attempts gets here as False, and the track is taken
                        # as finished by the rules below.
                        self._ended_trigger = True
                        self._has_played_current = False
                    else:
                        self._ended_trigger = True
                        self._has_played_current = False
                        # A media that stopped well short of its own reported length is a stream
                        # that gave out rather than a track that finished - the same call the
                        # branch above just made, and its answer only reaches here when that branch
                        # declined to reload it. Such a track keeps the promise it has always had:
                        # a Play press or a scrub goes through _stream_needs_renew() and picks it up
                        # where it stopped. Only a media that genuinely reached its end can be held
                        # with a replay button.
                        finished = not self._stream_ended_short(total_ms, ms)
                        # "Stop after current" armed: hold on this track instead of advancing.
                        stop_mode = int(getattr(self, 'stop_after_current', STOP_AFTER_OFF))
                        if stop_mode:
                            self._finish_stop_after_current()
                            if finished:
                                # Held on purpose, so the button that can do something with a
                                # finished media - start it again - is the one the listener sees.
                                self._hold_finished_track(stop_mode)
                        elif finished and self._next_playback_preview() is None:
                            # _next_playback_preview is the same look-ahead the read-ahead uses to
                            # decide whether a successor is worth resolving. Nothing follows this
                            # track, so there is nothing to advance to: the finished track is what
                            # the listener is left sitting on, and the replay button is the way to
                            # hear it again. Something does follow - or this is a stream that gave
                            # out - so it advances as it always did.
                            self._hold_finished_track()
                        else:
                            self.play_next()
                
            if total_ms > 0:
                cur_str = f"{int(ms/60000)}:{int((ms%60000)/1000):02d}"
                tot_str = f"{int(total_ms/60000)}:{int((total_ms%60000)/1000):02d}"
                time_txt = f"{cur_str} / {tot_str}"
                self.time_label.setText(time_txt)
                if not self.progress_slider.isSliderDown():
                    self.progress_slider.blockSignals(True)
                    self.progress_slider.setValue(int(pos))
                    self.progress_slider.blockSignals(False)

            # Nearing the end? Have the next track's stream resolved already, on its own
            # thread, so the changeover does not stall on yt-dlp.
            if state == vlc.State.Playing and total_ms and total_ms > 0:
                if (total_ms - ms) <= PREFETCH_SECONDS_BEFORE_END * 1000:
                    self._maybe_prefetch_next_track()

        # Update hover tooltip continuously
        if hasattr(self, 'tray_icon') and self.tray_icon:
            if title:
                if not time_txt and hasattr(self, 'time_label'):
                    time_txt = self.time_label.text().strip()
                if time_txt and time_txt != "0:00 / 0:00":
                    self.tray_icon.setToolTip(f"yt-msd - {title} | {time_txt}")
                else:
                    self.tray_icon.setToolTip(f"yt-msd - {title}")
            else:
                self.tray_icon.setToolTip("yt-msd")

        # Dynamic right-click tray menu track progress
        if hasattr(self, 'tray_menu') and self.tray_menu and self.tray_menu.isVisible():
            if hasattr(self, 'tray_header_action') and self.tray_header_action:
                if title:
                    if not time_txt and hasattr(self, 'time_label'):
                        time_txt = self.time_label.text().strip()
                    trunc_t = self._truncate_title(title, 24)
                    if time_txt and time_txt != "0:00 / 0:00":
                        hdr = f"{trunc_t} | {time_txt}"
                    else:
                        hdr = trunc_t
                    self.tray_header_action.setText(hdr)
                else:
                    self.tray_header_action.setText("No Track Playing")

    def _on_thumbnail_loaded(self, vid_id, pixmap):
        if hasattr(self, '_thumbnail_labels') and vid_id in self._thumbnail_labels:
            if not pixmap.isNull():
                # Covering the box and cutting back to it, so the box is the same width on
                # all four sides of the picture whatever shape the thumbnail arrived in.
                self._thumbnail_labels[vid_id].setPixmap(cover_thumbnail(pixmap))

    def _fetch_thumbnail(self, v):
        vid_id = v.get('id')
        if not vid_id: return
        if vid_id in self.thumbnail_cache:
            self.thumbnails_loaded_signal.emit(vid_id, self.thumbnail_cache[vid_id])
            return

        try:
            url = f"https://i.ytimg.com/vi/{vid_id}/mqdefault.jpg"
            with urllib.request.urlopen(url, timeout=10) as req:
                data = req.read()
                if self.thumbnail_cache_size + len(data) > 256 * 1024 * 1024:
                    self.thumbnail_cache.clear(); self.thumbnail_cache_size = 0
                
                img = Image.open(io.BytesIO(data))
                qpixmap = pil_to_qpixmap(img)
                self.thumbnail_cache[vid_id] = qpixmap
                self.thumbnail_cache_size += len(data)
                self.thumbnails_loaded_signal.emit(vid_id, qpixmap)
        except: pass
# These names moved out of this file during the 3.5 modularisation (wave 5e) and are
# re-exported here so the entry point keeps every name it has always had while the
# split proceeds. The final wave replaces this with the package's own entry point.
from yt_msd.crash import (
    CRASH_LOG_MAX,
    CRASH_LOG_NAME,
    CrashReporter,
    MAX_CRASH_DIALOGS_PER_MINUTE,
    _crash_state,
    crash_dialog_allowed,
    crash_log_entry,
    crash_log_folders,
    handle_thread_error,
    handle_unhandled_error,
    handle_unraisable_error,
    install_crash_reporting,
    open_crash_log,
    report_crash,
    show_crash_dialog,
    silence_crash_dialogs,
    traceback_text,
    trim_crash_log,
    write_crash_log,
)
# _crash_reporter is deliberately not re-exported: install_crash_reporting() moved with it and
# rebinds it with `global`, so a copy in this file would keep the value from before that
# rebinding - and nothing left in this file reads it to begin with.
from yt_msd.instance import (
    SINGLE_INSTANCE_NAME,
    accept_instance_request,
    ask_running_instance_to_show,
    take_single_instance_name,
)


if __name__ == "__main__":
    # "--console" means "this copy needs somewhere to print errors". For the installed
    # exe the launcher answers that by giving the copy a console (see attach_console
    # in the launcher); for the .pyw the terminal is already there. Either way the
    # flag is dropped here, so Qt is not handed an option that is ours, not Qt's.
    sys.argv = [a for a in sys.argv if a != "--console"]
    if len(sys.argv) > 1 and ("--renamer" in sys.argv or "-r" in sys.argv):
        sys.argv = [a for a in sys.argv if a not in ("--renamer", "-r")]
        install_crash_reporting()
        run_integrated_renamer_cli()
    else:
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        app = QApplication(sys.argv)
        install_crash_reporting()
        # Title bar + taskbar icon for every window of the app (Qt uses the
        # application icon for any window that does not set its own).
        _window_icon = app_icon()
        if _window_icon is not None:
            app.setWindowIcon(_window_icon)
        # One copy at a time. A second copy asks the first to come forward and
        # exits before it can open a second set of watchers, LAN services or
        # settings file. If the name cannot be claimed at all the copy carries on
        # - a machine where this fails is not a reason to not open the program.
        if ask_running_instance_to_show():
            sys.exit(0)
        instance_server = take_single_instance_name()
        window = MainApp()
        window.show()
        if instance_server is not None:
            instance_server.newConnection.connect(
                lambda: accept_instance_request(instance_server, window))
        ret = app.exec()
        # closeEvent() has already saved the settings and stopped the background
        # work; this only covers an exit that did not come through it. Then the
        # interpreter finishes on its own terms. A hard os._exit() here faults
        # in shiboken whenever a worker thread is still mid-call, and that is
        # what kept the window on screen for seconds after the tray icon was
        # already gone: Windows spends that long writing the crash dump.
        window.shutdown_for_exit()
        sys.exit(ret)
