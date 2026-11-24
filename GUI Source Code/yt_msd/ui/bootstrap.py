# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.ui.bootstrap).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
#
# A mixin, not a standalone module: MainApp inherits from this class, so what is written here
# are ordinary methods and `self` is the MainApp instance. They were lifted out of the class
# body in wave 6 with their text unchanged - only the imports needed to reach the rest of the
# program were added, and the inside of a multi-line string kept the indentation it was written
# with, because changing it would change what the program shows rather than where it is kept.

import os
import sys
import threading
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from yt_msd.audio.tuning import TUNING
from yt_msd.constants import STOP_AFTER_OFF
from yt_msd.paths import program_folder
from yt_msd.sync.config import SyncConfigManager
from yt_msd.sync.discovery import UDPBeaconBroadcaster
from yt_msd.sync.host import HostFolderWatcher, SyncHostServer
from yt_msd.sync.lan import get_current_wifi_ssid
from yt_msd.ui.render import LOCAL_RENDER_ROW_HEIGHT_GUESS
from yt_msd.ui.widgets import THUMB_HOVER_RECHECK_MS

class BootstrapMixin:
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
        # Read before the first batch is built, so it has to exist here the way the two
        # settings beside it do: the download path asks for it with getattr(..., False).
        self.channel_prefix_rename = True
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
        # How many automatic changeovers in a row have landed on a row with no stream. Each one
        # steps past that row and says so; the allowance is whole again as soon as a track
        # starts. See _on_stream_fetch_failed.
        self._stream_skip_streak = 0
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
        
        # gui_config.json lives beside the program. Until wave 6 this constructor was written in
        # the entry point, where __file__ was the program's own file; written here it names a
        # module inside the package, so the folder comes from program_folder() instead - the answer
        # yt_msd.paths already gives the crash log and the window icon, and the mistake
        # probe_windows' G9 check exists to refuse.
        self.config_dir = program_folder()
            
        self.config_path = os.path.join(self.config_dir, "gui_config.json")
        self.load_config()

        # Apply the normalization settings from the loaded config immediately
        TUNING.from_settings(self.silence_trim, self.silence_pad_dur,
                             self.use_custom_norm_cmd, self.custom_norm_cmd)

        # Placeholder so UI code can check readiness before VLC is initialized
        self.vlc_instance = None
        self.vlc_player = None
        self._vlc_ready = False
        # How many 200 ms retries one pick has waited for the thread below. Only used to thin what
        # the window says while it waits - see _note_waiting_for_player.
        self._vlc_ready_waits = 0

        self.setup_ui()
        self.apply_theme()

        self.status_signal.connect(self._on_status_update)
        self.search_results_signal.connect(self._on_search_results)
        self.search_failed_signal.connect(self._on_search_failed)
        self.playback_started_signal.connect(self._on_playback_started)
        self.stream_refreshed_signal.connect(self._on_stream_refreshed)
        self.stream_fetch_failed_signal.connect(self._on_stream_fetch_failed)
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
