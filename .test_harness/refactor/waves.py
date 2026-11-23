# The wave plan for the yt-msd module split - this is the file a human reviews.
#
# WAVES[wave_name] = [(dotted module, [top-level names moved into it])]
#
# The rule that makes this safe: a module may only reach for names that are stdlib,
# third-party, or already moved into a module from THIS wave or an earlier one. A moved
# module must never need a name that is still sitting in the shrinking .pyw, because a
# package module cannot import the .pyw back. splitlib.py checks this and refuses the
# wave when an out-edge points at the .pyw.
#
# Order matters: leaves first (no Qt, no app state), then the external-process layer,
# then sync, then the widgets and dialogs, then the app-level helpers. WAVES runs to 5g and stops
# there: MainApp stays in the entry point, recorded in LEFT_BY_DECISION below, reported by
# analyze() as left by decision, and refused by check_wave() if a later wave tries to move it
# anyway. LIFTS below runs to 6, and it is a different kind of move: the class stays exactly where
# this decision puts it, and five of its methods do not.

# Names a wave may move even though the GUI Test Suite writes mod.<name> against the entry
# point (see splitlib.harness_couplings). Every entry needs the reason and the harness change
# that makes it safe, because moving one without updating the suite does not turn a check red -
# it turns it into a check that passes while testing nothing.
HARNESS_EXEMPT = {
}

# Blocks the plan closes out by deciding not to move them, with the reason on the same terms
# as everything else in this file. Two things read it: splitlib.analyze() reports these as left
# in the entry point by decision rather than as work the plan still owes, and splitlib.check_wave()
# refuses any wave that lists one. Reopening a decision is therefore an edit to this dict, not a
# wave written past it.
LEFT_BY_DECISION = {
    "MainApp": (
        "Kept in yt-msd-gui.pyw as one class - 4,887 lines and 183 methods since wave 6 lifted the "
        "five methods that had outgrown a screenful into the mixin modules the class now inherits. "
        "It is the last large piece the compiled build holds: build_gui_cython.py compiles the "
        "entry point into one .pyd while yt_msd travels as plain Python, so moving the class itself "
        "out costs the player, the window and every handler their compilation and buys nothing at "
        "run time. What had stopped it being reviewable was not the class but those five methods, "
        "and wave 6 removed that instead of the class: nothing written in the entry point now runs "
        "longer than 150 lines, and analyze() keeps that count at zero. Reopen the rest of it only "
        "as one move-whole wave, not a carving."
    ),
}

# Methods the class no longer holds, and the module each one went to:
#
#   LIFTS[wave] = [(dotted module, mixin class MainApp now inherits, [method names])]
#
# WAVES moves top-level blocks; LIFTS moves methods out of the one block WAVES closed out. They
# are kept apart on purpose: a lifted method is not a name the entry point can import back, so it
# must not appear in the wave plan that build_import_block() and check_wave() reason over.
#
# The rule is the 150-line one, and it is a rule about reviewability rather than about the split:
# a method you cannot read in one screen is a method nobody reviews. Five methods met it, and no
# method left in MainApp does - the longest now runs 132 lines - so analyze() reports the longest
# method left in the entry point the same way it reports dead imports: a number that has to stay
# at zero.
#
# Each lands as a mixin rather than as a function taking the app, for one reason: it is the only
# shape in which the move is a cut-and-paste. The body is dedented one level and otherwise untouched
# - `self` still means the window, a zero-argument `super()` still resolves, and the signals,
# attributes and Qt wiring that the class already relies on are untouched because the method is
# still written inside a class. A plain function would have needed every `self.` in 1,618 lines
# re-pointed at a parameter, and every one of those a human checking.
LIFTS = {
    "6": [
        ("yt_msd.ui.bootstrap", "BootstrapMixin", ["__init__"]),
        ("yt_msd.ui.layout", "LayoutMixin", ["setup_ui"]),
        ("yt_msd.ui.stylesheet", "StylesheetMixin", ["apply_theme"]),
        ("yt_msd.ui.settings_reset", "SettingsResetMixin", ["reset_to_defaults"]),
        ("yt_msd.ytdlp.batch", "BatchDownloadMixin", ["start_batch_download"]),
    ],
}

WAVES = {

    # Wave 1: the leaf layer. No Qt widgets, no application state, nothing that can call
    # back into the program. Pure text, versions, timing and the guard imports.
    "1": [
        ("yt_msd.deps", [
            "winreg", "vlc", "_VLC_MODULE_AVAILABLE", "_VLC_IMPORT_ERROR",
            "Observer", "FileSystemEventHandler", "_WATCHDOG_AVAILABLE",
        ]),
        ("yt_msd.paths", [
            "_app_icon_path", "app_icon", "is_packaged_build",
        ]),
        ("yt_msd.constants", [
            "APP_VERSION", "UPDATE_REPO", "INSTALLER_ASSET", "SOURCE_ASSET",
            "UPDATE_MODE_INSTALLER", "UPDATE_MODE_REPLACE", "UPDATE_MODE_SWAP",
            "DOWNLOAD_FORMATS", "DEFAULT_DOWNLOAD_FORMAT", "TAGGABLE_EXTENSIONS",
            "AUDIO_EXTENSIONS", "MUTAGEN_TAGGABLE_EXTENSIONS",
            "PLAY_GLYPH", "PAUSE_GLYPH", "REPLAY_GLYPH",
            "STOP_AFTER_OFF", "STOP_AFTER_ONCE", "STOP_AFTER_ALWAYS",
            "STOP_AFTER_STATE_NAMES", "STOP_AFTER_LABELS", "STOP_AFTER_TOOLTIPS",
        ]),
        ("yt_msd.util.console", [
            "Colors", "_print_lock", "_safe_print",
        ]),
        ("yt_msd.util.text", [
            "_is_romanized", "clean_youtube_title", "_title_match_key",
            "_title_matches_filename", "_sanitize_filename", "_split_artist_title",
        ]),
        ("yt_msd.util.version", [
            "_release_asset_file", "select_release_asset",
            "_extract_version_number", "_version_is_newer",
        ]),
        ("yt_msd.util.timefmt", [
            "_format_audio_duration",
        ]),
        ("yt_msd.util.yaml", [
            "_yaml_scalar_repr", "yaml_dump", "_yaml_dump_list",
            "_yaml_scalar_parse", "yaml_load",
        ]),
    ],
    # Wave 2a: the settings seam. DONE.
    #
    # Wave 2 as first planned was refused, and it was refused for a good reason. Four of the
    # names it wanted to move as constants - SILENCE_TRIM, SILENCE_PAD_DUR, MAX_WORKERS and
    # CUSTOM_NORM_CMD - are settings: eight places rewrote them with `global` (the renamer CLI,
    # four SettingsDialog handlers, MainApp.__init__, MainApp.reset_to_defaults and
    # _apply_imported_config) while the normalizer read them. Moving them as constants would
    # have left every `global` updating the copy in the module that function ended up in and
    # every reader reading a copy imported once - a setting that silently stops doing anything,
    # with no error and no failed check. cross_module_globals refused it before anything was
    # written.
    #
    # So the seam came first, on its own, with nothing else moving: the loudness numbers and
    # one Tuning object went into yt_msd/audio/tuning.py, every read in the entry point was
    # qualified through TUNING, every `global` write became an attribute write or a call into
    # the object, and GUI Test Suite/probe_tuning_seam.py was written to prove the seam works -
    # these four settings had no coverage at all before that, which is how their duplication
    # survived. The entry point now holds no copy of any of them, so wave 2b can move the
    # readers freely.
    #
    # from_settings() also collapsed a decision that was written out three times - whether a
    # custom override counts - into the one method that makes it.
    "2a": [
        ("yt_msd.audio.tuning", [
            "_available_threads", "TARGET_LUFS", "TRUE_PEAK", "LOUDNESS_RANGE", "BITRATE",
            "SILENCE_THRESHOLD", "SILENCE_DURATION", "SILENCE_KEEP", "TUNING",
        ]),
    ],
    # Wave 2b: the two subprocess helpers every external-program path needs. This wave exists
    # because the guard found it: with the audio layer alone, analyze reported exactly two
    # out-edges - yt_msd.audio.probe and yt_msd.audio.normalize both reach for
    # _hidden_window_kwargs, which was still sitting in the entry point. Two modules that keep
    # helper programs from flashing a console window, and neither can belong to the module that
    # only probes, because the yt-dlp runner needs them too. They are ordered ahead of the
    # audio move rather than letting one module lend a helper to another.
    "2b": [
        ("yt_msd.subproc", [
            "_hidden_window_kwargs", "_child_utf8_env",
        ]),
    ],
    # Wave 2c: the audio layer - tagging, ffprobe, the ffmpeg -af chain, and the renamer CLI.
    # Unblockable now that the settings live in one object both sides reach through and the
    # subprocess helpers have a home of their own. The renamer CLI's writes go with it, into
    # the same subpackage as the object they write.
    "2c": [
        ("yt_msd.audio.tags", [
            "EasyID3", "ID3", "COMM", "ID3NoHeaderError", "EasyMP4", "MutagenFile",
            "read_metadata_tags", "write_metadata_tags",
            "_add_placeholder_tag", "_remove_placeholder_tag",
        ]),
        ("yt_msd.audio.probe", [
            "check_ffmpeg_available", "measure_loudness", "_ffprobe_binary", "_ffmpeg_binary",
            "_probe_format_block", "_get_audio_duration",
        ]),
        ("yt_msd.audio.normalize", [
            "_silence_trim_filters", "build_af_chain", "normalize_file",
            "run_loudness_normalization",
        ]),
        ("yt_msd.audio.renamer", [
            "_print_renamer_banner", "_select_renamer_folder",
            "clean_and_tag_files", "run_integrated_renamer_cli",
        ]),
        ("yt_msd.audio.localmeta", [
            "_LOCAL_META_CACHE_CAP", "_local_meta_cache", "_local_meta_cache_put",
            "_read_local_audio_meta", "_ffprobe_audio_meta", "_local_display_name",
        ]),
    ],
    # Wave 3: the yt-dlp install-and-update layer - where a copy of yt-dlp is looked for, how
    # winget is driven, and what GitHub says the newest release is. Deliberately kept apart
    # from the yt-dlp *runner* (run_yt_dlp_json, run_yt_dlp_text_search, run_yt_dlp_download,
    # resolve_stream_url, stream_cli_args, entry_channel_name) and from the stream-fetch
    # registry, for a reason the guard discovered rather than one invented here: the GUI Test
    # Suite drives the program through the entry point's own namespace - it writes
    # mod.run_yt_dlp_json, mod.subprocess, mod.find_yt_dlp_executable and mod._stream_fetches,
    # then calls into it. A name that has moved into a package module stops being reachable by
    # those writes, and the caller in the package starts calling its own copy: the check stays
    # green and stops testing anything. find_yt_dlp_executable is patched directly and
    # get_yt_dlp_version calls it, so both stay. Moving the runner is a harness job first -
    # re-aim those patches at the module that will own them - not a splitter job.
    "3": [
        ("yt_msd.ytdlp.install", [
            "YTDLP_WINGET_ID", "YTDLP_GITHUB_REPO", "YTDLP_UPDATE_CHECK_INTERVAL",
            "YTDLP_INSTALL_TIMEOUT", "YTDLP_EXTRACT_TIMEOUT",
            "YtDlpMissingError", "_yt_dlp_lookup_paths",
            "find_winget_executable", "run_winget", "latest_yt_dlp_release",
        ]),
    ],
    # Wave 3b: driving yt-dlp for a video - as opposed to installing it - and the runs that
    # can be stopped while they are still running.
    #
    # This wave was held back by the harness rather than by the graph, and the harness is what
    # made it worth waiting for. The suite injects a fake yt-dlp (`run_yt_dlp_json`), a fake
    # process (`subprocess.Popen`), a fake executable path (`find_yt_dlp_executable`) and reads
    # the live fetch registry (`_stream_fetches`) through the entry point's namespace. Once a
    # name lives in a package module, an injection made there stops reaching the caller that
    # uses it - the check stays green and tests nothing. GUI Test Suite/harness_seam.py now
    # injects into every module holding a name, so the injection follows the name here.
    #
    # `run_yt_dlp_json` and the fetch registry belong together for a reason that is in the code:
    # the runner is the only thing that registers a run (note_stream_fetch_process) and the only
    # thing that asks whether its own run was cancelled (stream_fetch_was_superseded). Separating
    # the two would put the question on one side of a boundary and the answer on the other.
    # Nothing here is redesigned - the registry, its lock and its thread-local owner move exactly
    # as they are, because 446 checks read them through the entry point and re-export keeps
    # them the same objects.
    "3b": [
        ("yt_msd.ytdlp.runner", [
            "_ytdlp_exe_cache", "_ytdlp_exe_cache_lock", "find_yt_dlp_executable",
            "get_yt_dlp_version",
            "_stream_fetches_lock", "_stream_fetches", "_stream_fetch_owner",
            "StreamFetchSupersededError", "begin_stream_fetch", "end_stream_fetch",
            "stream_fetch_vid_for_this_thread", "note_stream_fetch_process",
            "stream_fetch_was_superseded", "cancel_stream_fetches",
            "run_yt_dlp_json", "SEARCH_CHANNEL_RETRIES", "SEARCH_RETRY_TIMEOUT",
            "entry_channel_name", "run_yt_dlp_text_search",
            "stream_cli_args", "resolve_stream_url",
        ]),
        ("yt_msd.ytdlp.download", [
            "_YTDLP_FINAL_PATH_PATTERNS", "_YTDLP_STAGED_PATH_PATTERNS",
            "_clean_reported_path", "_match_reported_path", "run_yt_dlp_download",
            "DOWNLOAD_ITEM_ATTEMPTS", "_PERMANENT_DOWNLOAD_ERROR_MARKERS",
            "_is_permanent_download_error",
        ]),
    ],
    # Wave 4: sync chains - the host end, the client end, and the removable-media end of them.
    #
    # This wave was held back by coverage rather than by the graph: not one of these classes had
    # a check against it. GUI Test Suite/probe_sync.py (119 checks, SY-A..SY-L) was written first
    # so the move has something to preserve: the TAG.yaml marker a chain leaves on a drive and how
    # it reads back, the two forms last_synced takes and the clock grace between them, the drive
    # scan, chain persistence inside the config file MainApp also writes, the length-prefixed
    # socket protocol, the host's answers, the client's download and delete decisions, the
    # removable worker, and the failsafe that refuses to roll a newer drive back to an older copy.
    #
    # The dialogs stay in the .pyw (wave 5). They are the half of the sync layer that only exists
    # to be looked at, and SyncManagerDialog is 747 lines of layout that wants the engine beneath
    # it settled first.
    #
    # Where things went: `lan` is what this machine knows about the network it is on; `transfer`
    # is the framing and hashing every link is built out of; `discovery` is how a client finds a
    # host; `host` and `client` are the two ends of a chain over TCP; `tags` is the marker file
    # that lets a drive carry a chain without the app; `config` is persistence; `removable` is the
    # worker that writes a chain onto a stick, and `startup` is the Run-key entry the sync window
    # offers. Nothing here is redesigned - every class moved exactly as it was.
    "4": [
        ("yt_msd.sync.lan", [
            "SYNC_PORT_START", "SYNC_PORT_END", "UDP_BEACON_PORT", "SYNC_SOCKET_TIMEOUT",
            "SYNC_CHUNK_SIZE", "get_current_wifi_ssid", "_CACHED_LOCAL_IP",
            "_CACHED_LOCAL_IP_TIME", "get_local_ip", "get_broadcast_addresses",
        ]),
        ("yt_msd.sync.startup", [
            "is_run_on_startup_enabled", "set_run_on_startup",
        ]),
        ("yt_msd.sync.transfer", [
            "compute_file_sha256", "filter_audio_files", "_DRIVE_IO_LOCKS",
            "_DRIVE_IO_LOCKS_GUARD", "get_drive_io_lock", "make_throttled_progress_cb",
            "send_json_msg", "recv_json_msg", "_recv_all", "stream_file_to_socket",
            "recv_file_from_socket",
        ]),
        ("yt_msd.sync.discovery", [
            "UDPBeaconBroadcaster", "discover_hosts_on_lan", "discover_host_on_lan",
            "send_lan_update_notification",
        ]),
        ("yt_msd.sync.host", [
            "HostFolderWatcher", "SyncHostServer",
        ]),
        ("yt_msd.sync.client", [
            "SyncClientWorker", "ClientSyncThread",
        ]),
        ("yt_msd.sync.tags", [
            "SYNC_TAG_FILENAME", "write_sync_tag_file", "read_sync_tag_file",
            "SYNC_TAG_TIME_FORMATS", "SYNC_RETROGRADE_GRACE_SECONDS", "parse_sync_timestamp",
            "format_sync_timestamp", "drive_last_synced_timestamp",
            "find_tagged_sync_folders_on_drive", "make_removable_chain_id",
        ]),
        ("yt_msd.sync.config", [
            "is_client_chain_paused", "_CONFIG_WRITE_LOCK", "DEFAULT_SYNC_SETTINGS",
            "SyncConfigManager",
        ]),
        ("yt_msd.sync.removable", [
            "SyncRemovableWorker", "RemovableSyncThread", "RemovableInitThread",
        ]),
    ],
    # Wave 5: what the program paints with - the theme it reads off Windows, and the small
    # custom widgets its window is built out of.
    #
    # The theme goes in the same wave as the widgets because the widgets need it: ThumbnailWidget
    # asks get_accent_color which colour its box wears, and get_accent_color is the only reader of
    # THEME_COLORS. Widgets without the theme would be a package module reaching back into the
    # .pyw, which is the one thing this split cannot do.
    #
    # The coverage here is not new, which is why this wave needs no new checks: `AC` in
    # probe_playback drives a real ThumbnailWidget inside a real result row - the hover tile, the
    # play button it grows, the timer that re-checks a pointer that never moved,
    # THUMB_HOVER_RECHECK_MS itself - and check_glyphs measures what the captions on those buttons
    # actually paint.
    #
    # The chunked-rendering constants (LOCAL_RENDER_*) stay: they tune how MainApp fills a folder,
    # and nothing else reads them. Taking them now would be moving a name to a module that only
    # exists to hold it.
    "5": [
        ("yt_msd.ui.theme", [
            "THEME_COLORS", "get_system_accent_color", "get_system_appearance_mode",
            "get_accent_color",
        ]),
        ("yt_msd.ui.widgets", [
            "pil_to_qpixmap", "ClickableSlider", "DoubleClickButton", "_ElideTextFilter",
            "DraggableQueueWidget", "cover_thumbnail", "ThumbnailWidget",
            "THUMB_TILE_W", "THUMB_TILE_H", "THUMB_BOX_INSET", "THUMB_BOX_W", "THUMB_BOX_H",
            "THUMB_BOX_RADIUS", "THUMB_IMG_RADIUS", "THUMB_BOX_PLAIN", "THUMB_BOX_PLAYING",
            "THUMB_BOX_PAUSED", "THUMB_BOX_COLORS", "THUMB_HOVER_RECHECK_MS",
        ]),
    ],
    # Wave 5b: the export package - one .zip carrying the settings, the chains and copies of the
    # music folders, plus the window that asks for it.
    #
    # These travel together because they are one promise told twice: build_exported_config decides
    # what settings may leave, build_export_manifest_text writes the manifest that describes them,
    # read_import_package reads that manifest back, extract_package_music puts the music where the
    # manifest says it belongs, and ExportDialog is the only thing that calls them in order.
    # Separating the helpers from the window would leave the window reaching back into the .pyw.
    #
    # Nothing in this group had a check before it moved, so GUI Test Suite/probe_export.py was
    # written first: what a package contains and what it must not contain (chain keys stay in
    # unless they are asked for), the manifest round trip through the hand-written YAML helpers,
    # the folder walk that skips the system directories, and a package built by one copy of the
    # program being unpacked by another.
    "5b": [
        ("yt_msd.export", [
            "EXPORT_MANIFEST_NAME", "EXPORT_CONFIG_ENTRY", "EXPORT_SYNC_ENTRY",
            "EXPORT_FORMAT_VERSION", "SYNC_ONLY_CONFIG_KEYS", "EXPORT_SKIP_DIRS",
            "default_export_config", "build_exported_config", "build_export_manifest_text",
            "sanitize_archive_name", "unique_music_archive_name", "iter_folder_files",
            "zip_folder_into", "read_import_package", "music_import_destination",
            "extract_package_music", "ExportDialog",
        ]),
    ],

    # Wave 5c: the four windows that build a chain, join one, and run one.
    #
    # They belong with the sync subpackage rather than with the other dialogs because every
    # decision they make is already the sync engine's: a hosted chain is a folder plus a code
    # (CreateHostChainDialog), a client chain is a host found on the LAN (ConnectClientChainDialog),
    # a removable chain is a stick and an id (ConnectRemovableMediaDialog), and SyncManagerDialog is
    # the panel that starts and stops all three. The graph says the same thing plainly: their only
    # out-edges point at wave 4 names - SyncConfigManager, ClientSyncThread, make_removable_chain_id,
    # send_lan_update_notification - and none of them names MainApp, only the object it was handed.
    #
    # probe_sync holds the engines these windows drive (SY-E persistence, SY-G the host's answers,
    # SY-H the client's decisions, SY-J the failsafe against rolling a newer drive back), and
    # section AD of probe_playback builds each of these windows for real and checks what they hand
    # back.
    "5c": [
        ("yt_msd.sync.dialogs", [
            "CreateHostChainDialog", "ConnectClientChainDialog",
            "ConnectRemovableMediaDialog", "SyncManagerDialog",
        ]),
    ],
    # Wave 5d: the windows that are not about chains - the settings, the playlist picker, the tray
    # progress bubble, the three update windows, and the tag-renaming window.
    #
    # SettingsDialog is why this wave comes after 5 and 5b: it writes through the TUNING seam
    # (wave 2a), reads the theme and the accent lookup (wave 5), and opens ExportDialog (5b). It is
    # also the only window in the program that changes how audio is made, which is what
    # probe_tuning_seam holds - that a write made from the entry point is visible to the module that
    # reads it.
    #
    # The three update windows move as a set because they are one flow's three states: an update is
    # available, an update is ready to apply, yt-dlp itself wants updating. They read nothing but
    # wave 1 constants.
    "5d": [
        ("yt_msd.ui.dialogs", [
            "SettingsDialog", "PlaylistDialog", "TrayProgressPopup",
            "UpdateAvailableDialog", "UpdateReadyDialog", "YtDlpUpdateDialog",
            "MetadataRenameDialog",
        ]),
    ],

    # Wave 5e: the two pieces of plumbing that exist before any window does - the name that keeps a
    # second copy from starting, and the reporting that catches what nothing else caught.
    #
    # They are apart from each other on purpose. `instance` answers "is another copy of me already
    # running, and can I ask it to come forward"; `crash` answers "something failed that no part of
    # this program caught, and this build has no console to say it in". The only thing they share is
    # that both run before MainApp exists.
    #
    # `install_crash_reporting` is the only `global` statement left anywhere in the entry point, and
    # it is why this wave is listed on its own: it rebinds `_crash_reporter`, so the function and
    # the name must land in the same module or the re-export would leave the .pyw holding the value
    # from before the rebinding. cross_module_globals refuses the wave when they are split, and
    # here they are not.
    #
    # GUI Test Suite/probe_shell.py was written first: which folders the log may live in, what an
    # entry says, how the log is kept from growing without bound, the throttle that logs a
    # repeating fault instead of dialoguing it, the guards that stop a dialog being raised when
    # there is no window to raise it in, and a second copy finding the first.
    #
    # Two things this wave had to fix rather than carry over, both found by probe_shell.py when it
    # ran against the moved code:
    #   - `_crash_reporter` is not re-exported back into the entry point. The wave keeps it beside
    #     `install_crash_reporting` so the `global` has one home; forwarding a copy anyway would
    #     leave the .pyw holding `None` for the life of the process, which is the hazard this wave
    #     was separated out to avoid. `names_not_to_forward` in splitlib.py now leaves out any name
    #     a moved function rebinds with `global` that nothing left in the entry point reads.
    #   - `crash_log_folders()` took the folder to write the log into from its own `__file__`,
    #     which was the .pyw when this code sat in the .pyw and is `yt_msd/crash.py` after the
    #     move. The log would have moved into the package instead of staying beside the program and
    #     its gui_config.json, so the folder now comes from `program_folder()` in yt_msd.paths,
    #     which answers "which file was this program started as" wherever the asking code lives.
    #     `_app_icon_path()` in the same module had the same problem from wave 1 - icon-256x256.ico
    #     sits beside the program, not inside the package - and uses the same helper now.
    "5e": [
        ("yt_msd.instance", [
            "SINGLE_INSTANCE_NAME", "ask_running_instance_to_show",
            "take_single_instance_name", "accept_instance_request",
        ]),
        ("yt_msd.crash", [
            "CRASH_LOG_NAME", "CRASH_LOG_MAX", "MAX_CRASH_DIALOGS_PER_MINUTE",
            "_crash_state", "_crash_reporter", "traceback_text", "crash_log_folders",
            "trim_crash_log", "crash_log_entry", "write_crash_log", "CrashReporter",
            "crash_dialog_allowed", "open_crash_log", "show_crash_dialog", "report_crash",
            "handle_unhandled_error", "handle_thread_error", "handle_unraisable_error",
            "install_crash_reporting", "silence_crash_dialogs",
        ]),
    ],

    # Wave 5f: the two clocks the player runs on - how far ahead of the current track it reads, and
    # how long a track it is hearing gets before it counts as dead.
    #
    # They are the first residents of the playback subpackage, which is where the rest of the
    # player's rules go. The two groups are apart because they answer different questions -
    # "is the next track ready" and "is this track still answering" - and nothing in either group is
    # used by the other. Every one of them is read by MainApp alone, and none of them is a setting:
    # no `global` anywhere in the program writes them, which is why wave 2a had to carry its four
    # settings as a Tuning object and these can move as plain constants.
    #
    # GUI Test Suite/probe_playback.py held this wave before it ran: A1-A3 and X1-X4 already assert
    # every value, and sections C, K, X and Y drive the two clocks for real. Written for the wave is
    # section AE, which patches a number through the seam and watches the player's own decision
    # change and then change back. That is the check this kind of wave needs: a moved constant the
    # harness reads while the player reads a stale copy still lets every older check pass.
    "5f": [
        ("yt_msd.playback.prefetch", [
            "PREFETCH_SECONDS_BEFORE_END", "PREFETCH_URL_MAX_AGE", "PREFETCH_CACHE_LIMIT",
        ]),
        ("yt_msd.playback.stream", [
            "STREAM_STALL_SECONDS", "STREAM_RESUME_GRACE", "STREAM_URL_MAX_AGE",
            "STREAM_REFETCH_LIMIT", "STREAM_RENEW_COOLDOWN", "STREAM_END_SLACK_MS",
            "STREAM_SEEK_RESTORE_TIMEOUT",
        ]),
    ],

    # Wave 5g: how a folder arrives on the screen - the pacing of the chunked fill of the local pane.
    #
    # Five numbers, one promise: a folder is filled in chunks, the first chunk is the rows the user
    # switched folders to look at, and every chunk after it is as big as this machine can build, lay
    # out and paint inside about a frame - floored so an expensive folder is not dribbled out a row
    # at a time, capped so the GUI thread is never held longer than that. None of them is a setting
    # and no `global` writes any of them, so they move as they are. They belong with the ui
    # subpackage rather than with playback because they are the pane's policy, not the player's.
    #
    # GUI Test Suite/probe_local_pane.py was written for this wave and did not exist before it -
    # nothing in the suite touched the local pane at all. It drives `_local_screenful_rows` and
    # `_fill_local_chunk` against a stand-in pane that holds nothing but a viewport height and a
    # minimum height it was told, and it checks each of the five by moving it and watching the next
    # chunk change size. That is the only check worth having here: the failure mode of a moved
    # constant is a number the suite reads and the program does not.
    "5g": [
        ("yt_msd.ui.render", [
            "LOCAL_RENDER_FIRST_CHUNK_ROWS", "LOCAL_RENDER_ROW_HEIGHT_GUESS",
            "LOCAL_RENDER_CHUNK_MIN_ROWS", "LOCAL_RENDER_CHUNK_MAX_ROWS",
            "LOCAL_RENDER_CHUNK_BUDGET_S",
        ]),
    ],

    # Wave 5h moved nothing; it removed text. The .pyw had imported back every name a wave moved
    # out, on the promise that the entry point and the suite keep reaching names by name. With the
    # split closed, 117 of those 354 bindings were read by nobody - not by the file that imported
    # them, not as mod.<name> in the suite's syntax, and not in any string the suite contains
    # (harness_seam.patch(mod, "name") and getattr(mod, "name") reach a name by text, and a name
    # only ever mentioned that way is still load-bearing). prune_reexports.py removes exactly that
    # set and nothing else: it keeps each statement's own layout, never touches a comment, and is a
    # no-op when re-run. It also re-homed the thirteen wave banners, every one of which still
    # promised a final wave that is not coming. 6,995 lines became 6,882.
    #
    # The rule is permanent rather than a one-off sweep: splitlib.import_layer_status() labels every
    # binding the entry point creates from an import as read-here, suite-mod, suite-string or
    # unread; analyze() prints the count; and that is the same function the prune reads. A later
    # wave that moves code out and leaves the import behind shows up as a number on a screen.
    #
    # WAVES ends here. What remains in the entry point is MainApp - 4,887 lines, 183 methods, the
    # longest 132 lines - and the 365 lines of imports and entry-block glue around it. The class is
    # deliberately not listed as a wave: the decision is that it stays, recorded in LEFT_BY_DECISION
    # at the top of this file, where analyze() reports it as left by decision and check_wave()
    # refuses a wave that lists it.
    #
    # Wave 6, in LIFTS above, is the move this comment could only imagine doing whole. It did not
    # need to: what had outgrown reviewability was five methods, not the class. 1,618 lines went into
    # five modules the class inherits, every body cut and pasted at the same indent so verify.py
    # still finds no changed line in any of them, and no method left in the entry point runs over 150
    # lines - a number analyze() prints, for the same reason it prints dead imports.
    #
    # What it cost, said plainly. Those 1,618 lines are no longer compiled: the .pyd holds 5,252
    # lines against yt_msd's 9,646. And three checks had to be re-aimed because they named a place
    # rather than a behaviour. Two were text windows pinned to a location - probe_playback's Z41, and
    # probe_local_pane's LP9, which is LP9 and LP9b now. The third found a defect: probe_windows' G9
    # refuses a module under yt_msd that reads its own __file__ for a location, and the moved
    # constructor did exactly that to decide where gui_config.json lives. It reads program_folder()
    # now, the answer wave 5e established for the crash log and the window icon. Wave 6 also left 18
    # imports nothing read behind, which analyze() reported and prune_reexports.py removed.
    #
    # Measured against the rule this file exists to enforce, the class itself could still move today:
    # every name it reads is an import or already sits in a moved module, so check_wave finds no
    # out-edge still pointing at the .pyw; it holds no `global` statement - and neither does anything
    # else in the entry point - so cross_module_globals has nothing to refuse; and no check in the
    # suite writes mod.MainApp.
    #
    # What decides it is the build. The shipped program is one compiled module plus a plain-Python
    # package: build_gui_cython.py writes GUI Source Code/yt_msd_gui.pyx as the .pyw's text byte for
    # byte, build_gui_exe.py compiles that single module with MSVC into yt_msd_gui.pyd, and
    # PyInstaller carries yt_msd as ordinary Python in the archive. Whatever leaves the entry point
    # stops being compiled, and MainApp is the last large piece that still is - 4,887 of the 5,252
    # lines the compiled module holds. Carving the class itself into several modules moves the same
    # code and more, and a class split across modules runs exactly as the one class does: where the
    # time goes is VLC, ffmpeg and the network, not attribute lookup. A further split would be tidier
    # and no faster.
    #
    # The deal, then: one class, compiled, for as long as it reads as one piece - and a method that
    # stops fitting on a screen lifts out on wave 6's rule the moment it stops fitting. If the class
    # itself ever outgrows that, the way back is a single move-whole wave - MainApp into one module,
    # the .pyw down to its imports and the entry block - with the suite's source-text anchors
    # re-pointed as a change of their own. Deleting LEFT_BY_DECISION["MainApp"] is the edit that
    # reopens it; the guard is there so it is reopened on purpose.

}
