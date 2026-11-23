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
# then sync, then the widgets and dialogs, then the app-level helpers. MainApp itself is
# deliberately last and is handled separately.

# Names a wave may move even though the GUI Test Suite writes mod.<name> against the entry
# point (see splitlib.harness_couplings). Every entry needs the reason and the harness change
# that makes it safe, because moving one without updating the suite does not turn a check red -
# it turns it into a check that passes while testing nothing.
HARNESS_EXEMPT = {
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
        ("yt_msd.ytdlp", [
            "YTDLP_WINGET_ID", "YTDLP_GITHUB_REPO", "YTDLP_UPDATE_CHECK_INTERVAL",
            "YTDLP_INSTALL_TIMEOUT", "YTDLP_EXTRACT_TIMEOUT",
            "YtDlpMissingError", "_yt_dlp_lookup_paths",
            "find_winget_executable", "run_winget", "latest_yt_dlp_release",
        ]),
    ],
}
