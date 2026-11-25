# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.ui.dialogs).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
import os
from pathlib import Path
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QComboBox, QCheckBox, QScrollArea, QFileDialog, QMessageBox, QDialog, QFrame, QGridLayout
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QFontMetrics
from yt_msd.audio.tags import read_metadata_tags, write_metadata_tags
from yt_msd.audio.tuning import LOUDNESS_RANGE, SILENCE_DURATION, SILENCE_KEEP, SILENCE_THRESHOLD, TARGET_LUFS, TRUE_PEAK, TUNING
from yt_msd.constants import APP_VERSION, INSTALLER_ASSET, SOURCE_ASSET, UPDATE_MODE_INSTALLER, UPDATE_MODE_REPLACE, UPDATE_MODE_SWAP
from yt_msd.export import ExportDialog
from yt_msd.paths import is_packaged_build
from yt_msd.sync.startup import is_run_on_startup_enabled, set_run_on_startup
from yt_msd.ui.theme import THEME_COLORS, get_accent_color, get_system_accent_color, get_system_appearance_mode
from yt_msd.util.text import _sanitize_filename, _split_artist_title
from yt_msd.util.version import release_notes_url



class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        # The window that opened this dialog, held under a name that is not 'parent'.
        # It used to be self.parent, and that meant the name of a Qt method this dialog
        # inherits: QDialog.parent() is how Qt hands back the widget a dialog sits inside,
        # and an instance attribute of the same name replaces it for Python callers.
        # MainApp installs itself as an application-wide event filter, and every key press
        # makes it walk up from the focused control asking each widget for its parent -
        # so while this dialog was open, a key typed into any box of it reached the
        # MainApp window through self.parent and asked the window to be called as a
        # method. That is the "TypeError: 'MainApp' object is not callable" the installed
        # exe logged on every keystroke in Settings, and why only typing was affected and
        # not the spin-box arrows, which are clicks and not key presses.
        self.main_app = parent
        self.setWindowTitle("Settings")
        self.setMinimumWidth(820)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # 2-Column Horizontal Container
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(20)
        
        # ── LEFT COLUMN ──
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        
        # APPEARANCE MODE
        left_layout.addWidget(QLabel("APPEARANCE MODE", font=QFont("Segoe UI Semibold", 10)))
        mode_layout = QHBoxLayout()
        self.mode_btns = {}
        for mode in ["System", "Light", "Dark"]:
            btn = QPushButton(mode)
            btn.setToolTip(f"Switch to {mode.lower()} appearance")
            btn.setCheckable(True)
            if parent.appearance_mode == mode: btn.setChecked(True)
            btn.clicked.connect(lambda checked=False, m=mode: self._change_mode(m))
            mode_layout.addWidget(btn)
            self.mode_btns[mode] = btn
        left_layout.addLayout(mode_layout)
        
        # ACCENT COLOR
        left_layout.addWidget(QLabel("ACCENT COLOR", font=QFont("Segoe UI Semibold", 10)))
        grid = QGridLayout()
        grid.setSpacing(6)
        colors = ["System"] + list(THEME_COLORS.keys())
        self.accent_btns = {}
        for i, color in enumerate(colors):
            r, c = i // 5, i % 5
            btn = QPushButton()
            btn.setFixedSize(32, 32)
            c_val = get_system_accent_color() if color == "System" else THEME_COLORS[color][0]
            btn.setStyleSheet(f"background-color: {c_val}; border-radius: 6px; border: {'2px solid white' if parent.accent_color_name == color else 'none'};")
            # The System chip is a plain swatch of the live Windows accent colour, exactly like the
            # THEME_COLORS chips. It used to paint a glyph (U+E771) in Segoe MDL2 Assets on top of the
            # swatch, but that codepoint has no glyph in the font here, so the chip showed a tofu box.
            # The background colour alone already says "system", so the chip carries no text at all.
            btn.clicked.connect(lambda checked=False, clr=color: self._change_accent(clr))
            grid.addWidget(btn, r, c)
            self.accent_btns[color] = btn
        left_layout.addLayout(grid)
        
        # ADVANCED YT-DLP
        left_layout.addWidget(QLabel("CUSTOM YT-DLP ARGUMENTS (ADVANCED)", font=QFont("Segoe UI Semibold", 10)))
        arg_h = QHBoxLayout()
        self.args_cb = QCheckBox()
        self.args_cb.setChecked(parent.use_custom_args)
        self.args_cb.toggled.connect(self._toggle_args)
        arg_h.addWidget(self.args_cb)
        _fmt = parent.format_combo.currentText() if hasattr(parent, 'format_combo') else getattr(parent, 'audio_format', 'mp3')
        _brate = parent.bitrate_combo.currentText() if hasattr(parent, 'bitrate_combo') else getattr(parent, 'bitrate', '320')
        _default_args = f"--format bestaudio/best --audio-format {_fmt} --audio-quality {_brate} --retries 15 --fragment-retries 15"
        _initial_args = parent.custom_args if parent.custom_args else _default_args
        self.args_edit = QLineEdit(_initial_args)
        self.args_edit.setPlaceholderText("e.g. --format bestaudio/best --audio-format mp3 --audio-quality 320")
        self.args_edit.setEnabled(parent.use_custom_args)
        self.args_edit.textChanged.connect(self._update_args)
        arg_h.addWidget(self.args_edit, 1)
        left_layout.addLayout(arg_h)
        left_layout.addWidget(QLabel("Manual override ignores GUI bitrate/format settings.", font=QFont("Segoe UI", 8)))
        
        # OPTIONS
        self.startup_cb = QCheckBox("Run yt-msd on Windows Startup")
        self.startup_cb.setChecked(is_run_on_startup_enabled())
        self.startup_cb.toggled.connect(self._toggle_startup)
        left_layout.addWidget(self.startup_cb)

        self.tray_cb = QCheckBox("Minimize to System Tray")
        self.tray_cb.setChecked(parent.minimize_to_tray)
        self.tray_cb.toggled.connect(self._toggle_tray)
        left_layout.addWidget(self.tray_cb)
        
        self.session_cb = QCheckBox("Restore Last Session on Startup")
        self.session_cb.setChecked(getattr(parent, 'save_place', False))
        self.session_cb.toggled.connect(self._toggle_session)
        left_layout.addWidget(self.session_cb)
        
        # Parallel downloads option
        dl_threads_h = QHBoxLayout()
        dl_threads_h.addWidget(QLabel("Parallel download threads:"))
        self.dl_threads_edit = QLineEdit(str(parent.download_threads))
        self.dl_threads_edit.setFixedWidth(50)
        self.dl_threads_edit.setPlaceholderText("e.g. 3")
        self.dl_threads_edit.textChanged.connect(self._update_dl_threads)
        dl_threads_h.addWidget(self.dl_threads_edit)
        dl_threads_h.addStretch()
        left_layout.addLayout(dl_threads_h)
        left_layout.addWidget(QLabel("Disclaimer: Too many parallel downloads may cause your internet\n"
                                     "to throttle or YouTube to rate-limit requests.", font=QFont("Segoe UI", 8)))
        
        # Local folder auto-rescan interval
        rescan_h = QHBoxLayout()
        rescan_h.addWidget(QLabel("Local folder auto-rescan:"))
        self.rescan_combo = QComboBox()
        self.rescan_options = [
            ("Disabled", 0),
            ("15 minutes", 15),
            ("30 minutes", 30),
            ("1 hour (Default)", 60),
            ("2 hours", 120),
            ("4 hours", 240),
            ("12 hours", 720),
            ("24 hours", 1440)
        ]
        for label, mins in self.rescan_options:
            self.rescan_combo.addItem(label, mins)

        current_mins = getattr(parent, 'local_rescan_interval', 60)
        idx = self.rescan_combo.findData(current_mins)
        if idx >= 0:
            self.rescan_combo.setCurrentIndex(idx)
        else:
            self.rescan_combo.setCurrentIndex(3)  # 1 hour default

        self.rescan_combo.currentIndexChanged.connect(self._update_rescan_interval)
        rescan_h.addWidget(self.rescan_combo)
        rescan_h.addStretch()
        left_layout.addLayout(rescan_h)
        left_layout.addStretch()
        
        # Vertical Divider Frame
        divider = QFrame()
        divider.setFrameShape(QFrame.VLine)
        divider.setFrameShadow(QFrame.Sunken)
        
        # ── RIGHT COLUMN ──
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)
        
        # MP3 RENAMER
        right_layout.addWidget(QLabel("MP3 RENAMER & NORMALIZER", font=QFont("Segoe UI Semibold", 10)))

        # Normalization mode
        norm_h = QHBoxLayout()
        norm_h.addWidget(QLabel("Normalization after download:"))
        self.norm_btns = {}
        for mode, label in [("on", "ON"), ("off", "OFF"), ("ask", "ASK")]:
            btn = QPushButton(label)
            btn.setToolTip({"on": "Always normalize after download", "off": "Never normalize after download", "ask": "Ask before normalizing each download"}[mode])
            btn.setCheckable(True)
            btn.setChecked(parent.normalization_mode == mode)
            btn.clicked.connect(lambda checked=False, m=mode: self._set_norm_mode(m))
            norm_h.addWidget(btn)
            self.norm_btns[mode] = btn
        norm_h.addStretch()
        right_layout.addLayout(norm_h)
        right_layout.addWidget(QLabel("ON = always normalize  |  OFF = always skip  |  ASK = prompt each time",
                                      font=QFont("Segoe UI", 8)))

        # Auto-rename
        self.auto_rename_cb = QCheckBox("Auto-rename without prompts (auto-accept predictions)")
        self.auto_rename_cb.setChecked(parent.auto_rename)
        self.auto_rename_cb.toggled.connect(self._toggle_auto_rename)
        right_layout.addWidget(self.auto_rename_cb)

        # The channel name the download already knows, applied to the file it produced.
        # This one runs in the download itself, not in the renamer window, so it is the only
        # naming decision on this side that happens without a prompt - which is why it gets its
        # own box and its own worked example instead of hiding under the auto-rename one.
        self.channel_prefix_cb = QCheckBox("Add the channel name when a title has no artist")
        self.channel_prefix_cb.setToolTip(
            "A video named 'Looks Can Kill' from the channel 'IVE' is downloaded as "
            "'IVE - Looks Can Kill'.\nOnly when the title carries no artist of its own: "
            "'IVE - Looks Can Kill (Official Audio)' is left exactly as it is.\nThe file is "
            "renamed only - the tags are still written by the renamer, so normalization still runs.")
        self.channel_prefix_cb.setChecked(getattr(parent, 'channel_prefix_rename', True))
        self.channel_prefix_cb.toggled.connect(self._toggle_channel_prefix)
        right_layout.addWidget(self.channel_prefix_cb)
        right_layout.addWidget(QLabel("Names it for you when the title alone has no artist  |  "
                                      "untagged, so the renamer and the volume pass still take it",
                                      font=QFont("Segoe UI", 8)))

        # Silence pad duration
        pad_h = QHBoxLayout()
        pad_h.addWidget(QLabel("Silence padded at end of file (seconds):"))
        self.silence_pad_edit = QLineEdit(str(parent.silence_pad_dur))
        self.silence_pad_edit.setFixedWidth(70)
        self.silence_pad_edit.setPlaceholderText("e.g. 2.0")
        self.silence_pad_edit.textChanged.connect(self._update_silence_pad)
        pad_h.addWidget(self.silence_pad_edit)
        pad_h.addStretch()
        right_layout.addLayout(pad_h)
        
        # Normalization threads
        from PySide6.QtWidgets import QSpinBox
        norm_threads_h = QHBoxLayout()
        norm_threads_h.addWidget(QLabel("Normalization threads:"))
        self.norm_threads_spin = QSpinBox()
        self.norm_threads_spin.setRange(1, max(1, os.cpu_count() - 1))
        self.norm_threads_spin.setValue(parent.normalization_threads)
        self.norm_threads_spin.valueChanged.connect(self._update_norm_threads)
        norm_threads_h.addWidget(self.norm_threads_spin)
        norm_threads_h.addStretch()
        right_layout.addLayout(norm_threads_h)

        # Silence trimming on/off. This is its own part of the filter chain and is
        # completely independent of the loudnorm/EQ override below.
        self.silence_trim_cb = QCheckBox("Trim silence from the start and end of the file")
        self.silence_trim_cb.setToolTip(
            f"Removes leading and trailing silence during normalization.\n"
            f"Built-in filter (unchanged): silenceremove=start_periods=1:\n"
            f"start_duration={SILENCE_DURATION}:start_threshold={SILENCE_THRESHOLD}:\n"
            f"start_silence={SILENCE_KEEP}:stop_silence={SILENCE_KEEP}, applied forwards and reversed.\n"
            f"Turning this off does NOT change the loudnorm/EQ override,\n"
            f"and using a loudnorm/EQ override does NOT change this filter.")
        self.silence_trim_cb.setChecked(parent.silence_trim)
        self.silence_trim_cb.toggled.connect(self._toggle_silence_trim)
        right_layout.addWidget(self.silence_trim_cb)

        # Custom loudnorm/EQ override (replaces only the loudnorm filter, never the silence trim)
        right_layout.addWidget(QLabel("LOUDNORM/EQ OVERRIDE (ADVANCED)", font=QFont("Segoe UI Semibold", 10)))
        norm_cmd_h = QHBoxLayout()
        self.norm_cmd_cb = QCheckBox()
        self.norm_cmd_cb.setToolTip("Replace the built-in whole-track gain with your own loudnorm/EQ filter")
        self.norm_cmd_cb.setChecked(parent.use_custom_norm_cmd)
        self.norm_cmd_cb.toggled.connect(self._toggle_norm_cmd)
        norm_cmd_h.addWidget(self.norm_cmd_cb)
        _default_loudnorm = f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA={LOUDNESS_RANGE}"
        initial_norm = parent.custom_norm_cmd if parent.custom_norm_cmd else _default_loudnorm
        self.norm_cmd_edit = QLineEdit(initial_norm)
        self.norm_cmd_edit.setPlaceholderText(_default_loudnorm)
        self.norm_cmd_edit.setEnabled(parent.use_custom_norm_cmd)
        self.norm_cmd_edit.textChanged.connect(self._update_norm_cmd)
        norm_cmd_h.addWidget(self.norm_cmd_edit, 1)
        norm_cmd_h.addWidget(self._make_info_btn(
            f"Replaces ONLY the loudnorm part of the ffmpeg filter chain.\n"
            f"The silence trim and the end-of-file pad are still applied around it.\n"
            f"Exact loudnorm values used by default: I={TARGET_LUFS} LUFS | TP={TRUE_PEAK} dB | LRA={LOUDNESS_RANGE}.\n"
            f"Want EQ too? Append it after the loudnorm part in this same box, e.g.\n"
            f"{_default_loudnorm},equalizer=f=100:width_type=o:width=2:g=-3"))
        right_layout.addLayout(norm_cmd_h)

        # Run a custom file after a download batch finishes
        right_layout.addWidget(QLabel("CUSTOM SCRIPT ON DOWNLOAD FINISH", font=QFont("Segoe UI Semibold", 10)))
        cs_h = QHBoxLayout()
        self.custom_script_cb = QCheckBox()
        self.custom_script_cb.setToolTip("Run a chosen script or executable after each download batch finishes")
        self.custom_script_cb.setChecked(parent.run_custom_script)
        self.custom_script_cb.toggled.connect(self._toggle_custom_script)
        cs_h.addWidget(self.custom_script_cb)
        self.custom_script_edit = QLineEdit(parent.custom_script_path)
        self.custom_script_edit.setPlaceholderText("Path to a script or executable to run after downloads")
        self.custom_script_edit.textChanged.connect(self._update_custom_script)
        cs_h.addWidget(self.custom_script_edit, 1)
        self.custom_script_browse_btn = QPushButton("\uE8B7")
        self.custom_script_browse_btn.setObjectName("topIconBtn")
        self.custom_script_browse_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px; padding: 0px;")
        self.custom_script_browse_btn.setFixedSize(36, 30)
        self.custom_script_browse_btn.setToolTip("Browse for the file to run")
        self.custom_script_browse_btn.clicked.connect(self._browse_custom_script)
        cs_h.addWidget(self.custom_script_browse_btn)
        cs_h.addWidget(self._make_info_btn(
            "Runs one file after a download batch finishes.\n"
            "Supports .py, .exe, .bat/.cmd, .ps1, and any file type Windows can open.\n"
            "It receives the download folder as its first argument,\n"
            "then the path of each downloaded file."))
        right_layout.addLayout(cs_h)

        # SYSTEM YT-DLP
        right_layout.addWidget(QLabel("YT-DLP (ON THIS SYSTEM)", font=QFont("Segoe UI Semibold", 10)))
        ytdlp_h = QHBoxLayout()
        known_version = getattr(parent, 'ytdlp_version', '')
        self.ytdlp_version_lbl = QLabel(f"Version: {known_version}" if known_version else "Version: checking...")
        self.ytdlp_version_lbl.setFont(QFont("Segoe UI", 9))
        ytdlp_h.addWidget(self.ytdlp_version_lbl)
        ytdlp_h.addStretch()
        self.ytdlp_update_btn = QPushButton("Update with winget")
        self.ytdlp_update_btn.setObjectName("topIconBtn")
        self.ytdlp_update_btn.setToolTip("Run: winget upgrade --id yt-dlp.yt-dlp")
        self.ytdlp_update_btn.clicked.connect(self._update_yt_dlp)
        ytdlp_h.addWidget(self.ytdlp_update_btn)
        ytdlp_h.addWidget(self._make_info_btn(
            "yt-msd searches and downloads with the yt-dlp installed on this system,\n"
            "not a copy bundled inside yt-msd, so yt-dlp can be kept current without\n"
            "a new yt-msd build. This button runs winget, which ships with Windows 10\n"
            "and 11. yt-msd also asks GitHub once a week whether a newer yt-dlp exists."))
        right_layout.addLayout(ytdlp_h)

        self.ytdlp_never_cb = QCheckBox("Never notify me about yt-dlp updates")
        self.ytdlp_never_cb.setToolTip("Stop the weekly yt-dlp version check (yt-msd updates are not affected)")
        self.ytdlp_never_cb.setChecked(getattr(parent, 'disable_ytdlp_updates', False))
        self.ytdlp_never_cb.toggled.connect(self._toggle_ytdlp_updates)
        right_layout.addWidget(self.ytdlp_never_cb)

        if not known_version:
            # The startup lookup may still be running; ask for the version again so
            # this row is never left showing "checking...".
            parent.refresh_yt_dlp_version()

        right_layout.addSpacing(10)
        version_lbl = QLabel(APP_VERSION)
        version_lbl.setFont(QFont("Segoe UI", 8))
        version_lbl.setAlignment(Qt.AlignRight)
        version_lbl.setStyleSheet("background: transparent; border: none;")
        right_layout.addWidget(version_lbl)
        right_layout.addStretch()
        
        columns_layout.addWidget(left_widget, 1)
        columns_layout.addWidget(divider)
        columns_layout.addWidget(right_widget, 1)
        
        main_layout.addLayout(columns_layout)
        
        # FOOTER / RESET & SYNC
        footer = QHBoxLayout()
        self.reset_btn = QPushButton("Reset to Default Config")
        self.reset_btn.setObjectName("topIconBtn")
        self.reset_btn.setToolTip("Reset all settings to their defaults")
        self.reset_btn.clicked.connect(self._reset_defaults)
        footer.addWidget(self.reset_btn)

        self.sync_btn = QPushButton("Sync Chains Manager")
        self.sync_btn.setToolTip("Open the Sync Chains Manager")
        self.sync_btn.clicked.connect(self._open_sync_manager)
        footer.addWidget(self.sync_btn)

        self.export_btn = QPushButton("Export...")
        self.export_btn.setToolTip("Pack your config, sync chains, and music into a single .zip file")
        self.export_btn.clicked.connect(self._open_export_dialog)
        footer.addWidget(self.export_btn)

        self.import_btn = QPushButton("Import...")
        self.import_btn.setToolTip("Restore a yt-msd export package from a .zip file")
        self.import_btn.clicked.connect(self._open_import_package)
        footer.addWidget(self.import_btn)

        footer.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setFixedWidth(100)
        ok_btn.setToolTip("Close settings")
        ok_btn.clicked.connect(self.accept)
        footer.addWidget(ok_btn)
        
        main_layout.addLayout(footer)
        self.update_styles()

    def update_styles(self):
        accent = get_accent_color(self.main_app.accent_color_name)
        mode = self.main_app.appearance_mode
        if mode == "System": mode = get_system_appearance_mode()
        is_light = mode == "Light"
        
        r = int(accent[1:3], 16)
        g = int(accent[3:5], 16)
        b = int(accent[5:7], 16)
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        accent_fg = "black" if brightness > 150 else "white"
        
        for m, b in self.mode_btns.items():
            if m == self.main_app.appearance_mode:
                b.setStyleSheet(f"background-color: {accent}; color: {accent_fg}; border-radius: 4px;")
            else:
                b.setStyleSheet(f"background-color: {'#ddd' if is_light else '#444'}; color: {'black' if is_light else 'white'}; border-radius: 4px;")
        
        for color, btn in self.accent_btns.items():
            c_val = get_system_accent_color() if color == "System" else THEME_COLORS[color][0]
            border = f"2px solid {'black' if is_light else 'white'}" if self.main_app.accent_color_name == color else "none"
            btn.setStyleSheet(f"background-color: {c_val}; border-radius: 6px; border: {border};")

        for m, btn in self.norm_btns.items():
            if m == self.main_app.normalization_mode:
                btn.setStyleSheet(f"background-color: {accent}; color: {accent_fg}; border-radius: 4px;")
            else:
                btn.setStyleSheet(f"background-color: {'#ddd' if is_light else '#444'}; color: {'black' if is_light else 'white'}; border-radius: 4px;")

    def _change_mode(self, mode):
        self.main_app.appearance_mode = mode
        self.main_app.apply_theme()
        self.update_styles()
        self.main_app.save_config()

    def _change_accent(self, color):
        self.main_app.accent_color_name = color
        self.main_app.apply_theme()
        self.update_styles()
        self.main_app.save_config()
        
    def _toggle_args(self, state):
        self.main_app.use_custom_args = state
        self.args_edit.setEnabled(state)
        self.main_app.save_config()
        
    def _update_args(self, text):
        self.main_app.custom_args = text
        self.main_app.save_config()
        
    def set_ytdlp_version(self, version):
        """Show the yt-dlp version found by a background thread in the main window."""
        if version and hasattr(self, 'ytdlp_version_lbl'):
            self.ytdlp_version_lbl.setText(f"Version: {version}")

    def _update_yt_dlp(self):
        """Ask the main window to run the winget upgrade for yt-dlp."""
        self.main_app.update_yt_dlp_now()

    def _toggle_ytdlp_updates(self, state):
        self.main_app.disable_ytdlp_updates = state
        self.main_app.save_config()
        
    def _toggle_startup(self, state):
        set_run_on_startup(bool(state))

    def _toggle_tray(self, state):
        self.main_app.minimize_to_tray = state
        self.main_app.save_config()
        
    def _toggle_session(self, state):
        self.main_app.save_place = state
        self.main_app.save_config()

    # --- MP3 Renamer settings ---
    def _set_norm_mode(self, mode):
        self.main_app.normalization_mode = mode
        for m, btn in self.norm_btns.items():
            btn.setChecked(m == mode)
        self.main_app.save_config()
        self.update_styles()

    def _toggle_auto_rename(self, state):
        self.main_app.auto_rename = state
        self.main_app.save_config()

    def _toggle_channel_prefix(self, state):
        self.main_app.channel_prefix_rename = state
        self.main_app.save_config()

    def _update_silence_pad(self, text):
        try:
            val = float(text)
            if val >= 0:
                self.main_app.silence_pad_dur = val
                TUNING.silence_pad_dur = val
                self.main_app.save_config()
        except ValueError:
            pass

    def _update_dl_threads(self, text):
        try:
            val = int(text)
            if val > 0:
                self.main_app.download_threads = val
                self.main_app.save_config()
        except ValueError:
            pass

    def _update_rescan_interval(self, index):
        mins = self.rescan_combo.itemData(index)
        if mins is not None:
            self.main_app.local_rescan_interval = mins
            self.main_app._update_local_rescan_timer()
            self.main_app.save_config()

    def _update_norm_threads(self, val):
        self.main_app.normalization_threads = val
        self.main_app.save_config()

    def _toggle_silence_trim(self, state):
        self.main_app.silence_trim = state
        TUNING.silence_trim = state
        self.main_app.save_config()

    def _toggle_norm_cmd(self, state):
        self.main_app.use_custom_norm_cmd = state
        self.norm_cmd_edit.setEnabled(state)
        if state and not self.norm_cmd_edit.text().strip():
            self.norm_cmd_edit.setText(f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA={LOUDNESS_RANGE}")
        TUNING.custom_norm_cmd = self.main_app.custom_norm_cmd if state else ""
        self.main_app.save_config()

    def _update_norm_cmd(self, text):
        self.main_app.custom_norm_cmd = text
        if self.main_app.use_custom_norm_cmd:
            TUNING.custom_norm_cmd = text
        self.main_app.save_config()

    def _toggle_custom_script(self, state):
        # The checkbox only gates whether the script runs after a download; the
        # path field and browse button stay usable so a path can always be set.
        self.main_app.run_custom_script = state
        self.main_app.save_config()

    def _update_custom_script(self, text):
        self.main_app.custom_script_path = text.strip()
        self.main_app.save_config()

    def _browse_custom_script(self):
        start = self.custom_script_edit.text().strip() or ""
        f, _ = QFileDialog.getOpenFileName(
            self, "Select File To Run After Download", start,
            "All files (*);;Python (*.py);;Executable (*.exe);;Batch (*.bat *.cmd);;PowerShell (*.ps1)"
        )
        if f:
            self.custom_script_edit.setText(f)
            self.main_app.custom_script_path = f
            self.main_app.save_config()

    def _make_info_btn(self, text):
        """Small 'i' info button; the description is shown as a hover tooltip."""
        mode = self.main_app.appearance_mode
        if mode == "System":
            mode = get_system_appearance_mode()
        is_light = (mode == "Light")
        fg = "#1a1a1a" if is_light else "#ffffff"
        border = "#ccc" if is_light else "#555"
        accent = get_accent_color(self.main_app.accent_color_name)
        btn = QPushButton("i")
        btn.setObjectName("infoBtn")
        btn.setFixedSize(24, 24)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(text)
        btn.setStyleSheet(
            f"QPushButton#infoBtn {{ background: transparent; color: {fg}; "
            f"border: 1px solid {border}; border-radius: 12px; "
            f"font-family: 'Segoe UI'; font-weight: bold; font-size: 13px; padding: 0px; }}"
            f"QPushButton#infoBtn:hover {{ border-color: {accent}; color: {accent}; }}"
            "QToolTip { font-size: 11px; }"
        )
        return btn

    def _open_export_dialog(self):
        """Pack the selected pieces into a .zip export package."""
        dialog = ExportDialog(self.main_app)
        dialog.exec()

    def _open_import_package(self):
        """Pick a .zip export package and restore it."""
        self.main_app.open_import_dialog()

    def _open_sync_manager(self):
        # Leave the settings dialog open in the background, open sync manager in foreground
        self.main_app.open_sync_manager(parent_dialog=self)

    def _reset_defaults(self):
        # Wording that matches what reset_to_defaults() actually clears: every stored setting and
        # history entry, plus the hosted and client chains. A drive that has been initialised keeps
        # its own TAG.yaml marker on the device, so its card reappears while it is plugged in - but
        # with the hosted/client chains gone there is nothing left for it to sync against. Music
        # files themselves are never touched, on this machine or on a drive.
        warning = ("This wipes everything yt-msd remembers: every setting, your download and local "
                   "folder history, your playlist history, and every hosted and client sync chain. "
                   "An initialised drive keeps its marker on the device, so its card comes back "
                   "while it is plugged in. Your music files are not touched. Continue?")
        if QMessageBox.question(self, "Confirm Reset", warning) == QMessageBox.Yes:
            self.main_app.reset_to_defaults()
            self.accept()


class PlaylistDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Open Playlist")
        self.setFixedSize(420, 200)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)
        l = QVBoxLayout(self)
        l.setContentsMargins(20, 20, 20, 20)
        l.addWidget(QLabel("Enter URL or select from history:"))
        self.url_cb = QComboBox()
        self.url_cb.setEditable(True)
        self.url_cb.setMinimumHeight(32)
        if parent and hasattr(parent, 'recent_playlists'):
            display_values = []
            for p in parent.recent_playlists:
                if isinstance(p, dict): display_values.append(p.get("name", "Unknown Playlist"))
                else: display_values.append(str(p))
            self.url_cb.addItems(display_values)
        l.addWidget(self.url_cb)
        l.addStretch()
        h = QHBoxLayout()
        h.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip("Cancel")
        cancel_btn.clicked.connect(self.reject)
        open_btn = QPushButton("Open Playlist")
        open_btn.setToolTip("Open the selected playlist")
        open_btn.clicked.connect(self.accept)
        # Assuming app aesthetic injection
        accent = get_accent_color(parent.accent_color_name if parent else "Blue")
        r = int(accent[1:3], 16); g = int(accent[3:5], 16); b = int(accent[5:7], 16)
        accent_fg = "black" if (r * 299 + g * 587 + b * 114) / 1000 > 150 else "white"
        open_btn.setStyleSheet(f"background-color: {accent}; color: {accent_fg}; border-radius: 4px; padding: 6px 12px; font-weight: bold;")
        cancel_btn.setStyleSheet("background-color: #555555; color: white; border-radius: 4px; padding: 6px 12px; font-weight: bold;")
        h.addWidget(cancel_btn)
        h.addWidget(open_btn)
        l.addLayout(h)


class TrayProgressPopup(QWidget):
    """Custom frameless floating popup near system tray displaying current track and playback progress."""
    def __init__(self, parent=None):
        super().__init__(parent, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SubWindow)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.frame = QFrame()
        self.frame.setObjectName("trayPopupFrame")
        self.frame.setStyleSheet("""
            QFrame#trayPopupFrame {
                background-color: #1e1e1e;
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 8px;
            }
        """)
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(14, 12, 14, 12)
        frame_layout.setSpacing(6)

        # Header row
        header_h = QHBoxLayout()
        header_h.setContentsMargins(0, 0, 0, 0)
        header_lbl = QLabel("NOW PLAYING")
        header_lbl.setStyleSheet("color: #3B8ED0; font-weight: bold; font-size: 11px; letter-spacing: 0.5px;")
        header_h.addWidget(header_lbl)
        header_h.addStretch()
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(18, 18)
        close_btn.setToolTip("Close")
        close_btn.setStyleSheet("background: transparent; color: #888; font-size: 11px; border: none; font-weight: bold;")
        close_btn.clicked.connect(self.hide)
        header_h.addWidget(close_btn)
        frame_layout.addLayout(header_h)

        # Song Title
        self.title_lbl = QLabel("No track currently playing")
        self.title_lbl.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: bold;")
        self.title_lbl.setWordWrap(True)
        frame_layout.addWidget(self.title_lbl)

        # Progress info
        self.progress_lbl = QLabel("")
        self.progress_lbl.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        frame_layout.addWidget(self.progress_lbl)

        main_layout.addWidget(self.frame)
        self.setFixedWidth(320)

    def mousePressEvent(self, event):
        self.hide()

    def show_track_info(self, title: str, progress_txt: str):
        if not title:
            self.title_lbl.setText("No track currently playing")
            self.progress_lbl.setText("")
        else:
            self.title_lbl.setText(title)
            if progress_txt and progress_txt != "0:00 / 0:00":
                self.progress_lbl.setText(progress_txt)
            else:
                self.progress_lbl.setText("Playing")

        self.adjustSize()
        
        # Position in bottom right above taskbar
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.right() - self.width() - 16
        y = screen.bottom() - self.height() - 16
        self.move(x, y)
        self.show()
        self.raise_()
        self.hide_timer.start(3500)



class VersionNotesDialog(QDialog):
    """Tells the user, once, that this copy of yt-msd has just become a new version.

    Nothing is being offered here. The update has already happened - by the in-app updater, by the
    swap helper, by the setup program run by hand, or by whoever replaced the source file - and what
    this box carries is the link to the notes for the version now running. Which version this copy
    has already reported is kept in this machine's own settings file and written the moment the box
    is shown, which is why the same version never says it twice and why an update nobody made through
    this program is still noticed.
    """
    def __init__(self, parent_window, current_version, previous_version=""):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.current_version = str(current_version or "").strip()
        self.previous_version = str(previous_version or "").strip()
        # The page is worked out from the version this copy carries rather than fetched, because
        # a machine that has just been updated is not guaranteed to reach GitHub at the moment it
        # first starts, and a box whose link is missing is a worse box than one that points at the
        # general releases page.
        self.notes_url = release_notes_url(self.current_version)
        self.notes_opened = False
        self.setWindowTitle("Updated - yt-msd")
        self.setFixedWidth(430)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title_lbl = QLabel(f"YOU'RE NOW ON VERSION {self.current_version}" if self.current_version
                           else "YOU'RE NOW ON A NEW VERSION")
        title_lbl.setFont(QFont("Segoe UI Semibold", 11))
        layout.addWidget(title_lbl)

        if self.previous_version and self.previous_version != self.current_version:
            desc_lbl = QLabel(
                f"yt-msd was updated from {self.previous_version} to {self.current_version}.\n"
                "Your download folders, playlists, sync chains and settings are exactly where they "
                "were before the update."
            )
        else:
            desc_lbl = QLabel(f"This is yt-msd {self.current_version}.")
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(desc_lbl)

        self.link_lbl = QLabel(
            f'<a href="{self.notes_url}">Read the changelog for {self.current_version}</a>'
            if self.current_version else f'<a href="{self.notes_url}">Read the changelog</a>'
        )
        self.link_lbl.setOpenExternalLinks(True)
        self.link_lbl.linkActivated.connect(self._on_notes_opened)
        layout.addWidget(self.link_lbl)

        where_lbl = QLabel("The same page lists every release of yt-msd, and it is the page this "
                           "program downloads its updates from.")
        where_lbl.setWordWrap(True)
        where_lbl.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(where_lbl)

        layout.addStretch()

        btn_h = QHBoxLayout()
        btn_h.addStretch()
        ok_btn = QPushButton("Got it")
        ok_btn.clicked.connect(self.accept)
        btn_h.addWidget(ok_btn)
        layout.addLayout(btn_h)

    def _on_notes_opened(self, _link=""):
        # The link itself opens in the browser the desktop uses. This only records that it was
        # followed, which is the difference between a box that was read and a box that was closed.
        self.notes_opened = True


class UpdateAvailableDialog(QDialog):
    """Notifies the user that a newer yt-msd release is available and offers to download it."""
    def __init__(self, parent_window, latest_tag, release_name, current_version, asset_name=""):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.never_notify = False
        # Whether this copy is the installed program or a copy started from the
        # source decides which file of the release is offered, and what downloading
        # it does to this folder.
        self.packaged = is_packaged_build()
        self.wanted_asset = INSTALLER_ASSET if self.packaged else SOURCE_ASSET
        self.asset_name = (asset_name or "").strip()
        self.setWindowTitle("Update Available - yt-msd")
        self.setFixedWidth(470)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title_lbl = QLabel("A NEW UPDATE IS AVAILABLE")
        title_lbl.setFont(QFont("Segoe UI Semibold", 11))
        layout.addWidget(title_lbl)

        desc = QLabel(
            f"A newer version of yt-msd ({latest_tag}) is available.\n"
            f"You are currently running {current_version}."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(desc)

        if release_name and release_name != latest_tag:
            name_lbl = QLabel(f"Release: {release_name}")
            name_lbl.setWordWrap(True)
            name_lbl.setStyleSheet("color: #888; font-size: 11px;")
            layout.addWidget(name_lbl)

        self.never_cb = QCheckBox("Never notify me again about updates")
        self.never_cb.setToolTip("Stop checking for updates entirely")
        layout.addWidget(self.never_cb)

        if self.asset_name:
            what_lbl = QLabel(
                f"Download: {self.asset_name}\n"
                + ("This copy of yt-msd is the installed program, so the setup program is downloaded "
                   "and the whole yt-msd folder is replaced once it has run."
                   if self.packaged else
                   "This copy of yt-msd is running from its source file, so the new source file is "
                   "downloaded over the file you are running.")
            )
        elif self.packaged:
            what_lbl = QLabel(f"This release has no {INSTALLER_ASSET} setup program to download.")
        else:
            what_lbl = QLabel(f"This release has no {SOURCE_ASSET} source file to download.")
        what_lbl.setWordWrap(True)
        what_lbl.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(what_lbl)

        layout.addStretch()

        btn_h = QHBoxLayout()
        btn_h.addStretch()

        ignore_btn = QPushButton("Ignore")
        ignore_btn.setToolTip("Skip this update until the next check")
        ignore_btn.clicked.connect(self._on_ignore)
        btn_h.addWidget(ignore_btn)

        dl_btn = QPushButton("Download update")
        if self.packaged:
            dl_btn.setToolTip("Download the setup program into the folder yt-msd is running from")
        else:
            dl_btn.setToolTip(f"Download the new {SOURCE_ASSET} over the file yt-msd is running from")
        dl_btn.clicked.connect(self._on_download)
        btn_h.addWidget(dl_btn)
        layout.addLayout(btn_h)

    def _on_download(self):
        self.never_notify = self.never_cb.isChecked()
        self.accept()

    def _on_ignore(self):
        self.never_notify = self.never_cb.isChecked()
        self.reject()



class UpdateReadyDialog(QDialog):
    """Shown after a successful download; asks whether to close this version and move to the new one."""
    def __init__(self, parent_window, new_path, old_path, tag, mode=UPDATE_MODE_SWAP):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.setWindowTitle("Launch Update? - yt-msd")
        self.setFixedWidth(520)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title_lbl = QLabel("UPDATE DOWNLOADED")
        title_lbl.setFont(QFont("Segoe UI Semibold", 11))
        layout.addWidget(title_lbl)

        self.mode = mode
        if mode == UPDATE_MODE_INSTALLER:
            # The download is a setup program, not another copy of this program: it
            # replaces the whole yt-msd folder, so this file is not the thing that
            # gets removed.
            desc = QLabel(
                f"The new version ({tag}) has been downloaded to:\n{new_path}\n\n"
                "Would you like to close this version and run that installer? It replaces "
                "the whole yt-msd folder, so this file is left where it is until the "
                "installer has finished. Choosing Cancel leaves both untouched."
            )
            ok_tip = "Close this version and run the setup program"
            cancel_tip = "Keep both files; run the setup program yourself"
        elif mode == UPDATE_MODE_REPLACE:
            # The download was written over the file this program was started from,
            # so the update is already on disk and only a restart is missing.
            desc = QLabel(
                f"The new version ({tag}) has been downloaded over the yt-msd file you are running:\n{new_path}\n\n"
                "Would you like to close this version and launch that file? Choosing Cancel leaves "
                "the updated file where it is and keeps this version running until you close it."
            )
            ok_tip = "Close this version and launch the updated file"
            cancel_tip = "Keep this version running; restart it yourself later"
        else:
            desc = QLabel(
                f"The new version ({tag}) has been downloaded to:\n{new_path}\n\n"
                "Would you like to automatically close this version, delete the old file, and launch the new version? "
                "Choosing Cancel keeps both files so you can swap them yourself."
            )
            ok_tip = "Close this version, delete the old file, and launch the new version"
            cancel_tip = "Keep both files; swap them manually"
        desc.setWordWrap(True)
        layout.addWidget(desc)

        if mode == UPDATE_MODE_SWAP:
            old_lbl = QLabel(f"Old version file that would be removed: {old_path}")
            old_lbl.setWordWrap(True)
            old_lbl.setStyleSheet("color: #888; font-size: 11px;")
            layout.addWidget(old_lbl)

        layout.addStretch()

        btn_h = QHBoxLayout()
        btn_h.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip(cancel_tip)
        cancel_btn.clicked.connect(self.reject)
        btn_h.addWidget(cancel_btn)

        ok_btn = QPushButton("OK")
        ok_btn.setToolTip(ok_tip)
        ok_btn.clicked.connect(self.accept)
        btn_h.addWidget(ok_btn)
        layout.addLayout(btn_h)



class YtDlpUpdateDialog(QDialog):
    """Notifies the user that the system yt-dlp is behind and offers to update it."""
    def __init__(self, parent_window, installed_version, latest_version):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.never_notify = False
        self.setWindowTitle("yt-dlp Update Available - yt-msd")
        self.setFixedWidth(470)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title_lbl = QLabel("A NEW YT-DLP VERSION IS AVAILABLE")
        title_lbl.setFont(QFont("Segoe UI Semibold", 11))
        layout.addWidget(title_lbl)

        desc = QLabel(
            f"yt-msd searches and downloads with the yt-dlp installed on this system.\n"
            f"Installed: {installed_version}    Newest: {latest_version}\n"
            "yt-msd can run winget to bring it up to date."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(desc)

        self.never_cb = QCheckBox("Never notify me about yt-dlp updates")
        self.never_cb.setToolTip("Stop checking for yt-dlp updates (yt-msd updates are not affected)")
        layout.addWidget(self.never_cb)

        layout.addStretch()

        btn_h = QHBoxLayout()
        btn_h.addStretch()

        ignore_btn = QPushButton("Ignore")
        ignore_btn.setToolTip("Keep the current yt-dlp until the next check")
        ignore_btn.clicked.connect(self._on_ignore)
        btn_h.addWidget(ignore_btn)

        update_btn = QPushButton("Update with winget")
        update_btn.setToolTip("Run: winget upgrade --id yt-dlp.yt-dlp")
        update_btn.clicked.connect(self._on_update)
        btn_h.addWidget(update_btn)
        layout.addLayout(btn_h)

    def _on_update(self):
        self.never_notify = self.never_cb.isChecked()
        self.accept()

    def _on_ignore(self):
        self.never_notify = self.never_cb.isChecked()
        self.reject()



class MetadataRenameDialog(QDialog):
    """Metadata renamer used by the local file editor.

    Reads the artist/title tags embedded in each selected track, lets the user
    correct them inline, then renames every file to 'Artist - Title' from that
    metadata. The (possibly edited) tags can also be written back into the file.
    """

    def __init__(self, parent_window, file_paths):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.file_paths = list(file_paths)
        self.results = []
        self.rows = []
        self.setWindowTitle("Rename From Metadata")
        self.setWindowFlags(self.windowFlags() | Qt.Tool)

        row_h = 30
        max_visible_rows = 8

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        title_lbl = QLabel(f"RENAME {len(self.file_paths)} FILE(S) FROM METADATA")
        title_lbl.setFont(QFont("Segoe UI Semibold", 10))
        title_lbl.setToolTip("Artist and title are read from each file's tags. Correct them here and the "
                            "file is renamed to 'Artist - Title'.")
        layout.addWidget(title_lbl)

        # One compact line per file: current name, editable artist, editable
        # title, and the resulting 'Artist - Title' name.
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(3)
        grid.setColumnMinimumWidth(0, 168)
        grid.setColumnMinimumWidth(3, 168)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        for col, header in enumerate(("Current File", "Artist", "Title", "New Name")):
            head = QLabel(header)
            head.setFont(QFont("Segoe UI Semibold", 8))
            head.setStyleSheet("color: #888; font-size: 10px;")
            grid.addWidget(head, 0, col)

        for row_idx, path in enumerate(self.file_paths, start=1):
            p = Path(path)
            artist, title = read_metadata_tags(p)
            if not title:
                guess_artist, guess_title = _split_artist_title(p.stem)
                artist = artist or guess_artist
                title = title or guess_title
            artist_edit = QLineEdit(artist or "")
            title_edit = QLineEdit(title or "")
            # The app-wide line edit style uses generous padding, which clips the
            # text inside a one-line-tall row; trim it and give the row enough
            # height for the full glyph height of the UI font.
            for edit in (artist_edit, title_edit):
                edit.setObjectName("renameField")
                edit.setStyleSheet("padding: 2px 4px;")
                edit.setFixedHeight(row_h)
            old_lbl = QLabel(self._elide(p.name, 164))
            old_lbl.setToolTip(path)
            new_lbl = QLabel("")
            new_lbl.setObjectName("durationLabel")
            row = {'path': str(p), 'artist_edit': artist_edit, 'title_edit': title_edit, 'new_lbl': new_lbl}
            artist_edit.textChanged.connect(lambda _, r=row: self._update_preview(r))
            title_edit.textChanged.connect(lambda _, r=row: self._update_preview(r))
            self._update_preview(row)
            grid.addWidget(old_lbl, row_idx, 0)
            grid.addWidget(artist_edit, row_idx, 1)
            grid.addWidget(title_edit, row_idx, 2)
            grid.addWidget(new_lbl, row_idx, 3)
            self.rows.append(row)

        # Only very large selections scroll, and even then the dialog stays short.
        if len(self.rows) > max_visible_rows:
            body = QWidget()
            body.setLayout(grid)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidget(body)
            layout.addWidget(scroll, 1)
        else:
            layout.addLayout(grid)
        self.resize(700, 108 + min(len(self.rows), max_visible_rows) * (row_h + 3))

        self.write_tags_cb = QCheckBox("Write tags back into the file (MP3, M4A)")
        self.write_tags_cb.setChecked(True)
        self.write_tags_cb.setToolTip("Update the embedded tags so they match the new file name")
        self.write_tags_cb.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.write_tags_cb)

        btn_h = QHBoxLayout()
        btn_h.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip("Close without renaming anything")
        cancel_btn.clicked.connect(self.reject)
        rename_btn = QPushButton("Rename")
        rename_btn.setToolTip("Rename the selected files to 'Artist - Title'")
        rename_btn.clicked.connect(self._apply_renames)
        accent = get_accent_color(parent_window.accent_color_name if parent_window else "Blue")
        r = int(accent[1:3], 16); g = int(accent[3:5], 16); b = int(accent[5:7], 16)
        accent_fg = "black" if (r * 299 + g * 587 + b * 114) / 1000 > 150 else "white"
        rename_btn.setStyleSheet(f"background-color: {accent}; color: {accent_fg}; border-radius: 4px; padding: 4px 10px; font-weight: bold;")
        cancel_btn.setStyleSheet("background-color: #555555; color: white; border-radius: 4px; padding: 4px 10px; font-weight: bold;")
        btn_h.addWidget(cancel_btn)
        btn_h.addWidget(rename_btn)
        layout.addLayout(btn_h)
        if self.rows:
            self.rows[0]['title_edit'].setFocus()

    def _elide(self, text: str, width: int) -> str:
        fm = QFontMetrics(QFont("Segoe UI", 10))
        return fm.elidedText(text, Qt.ElideRight, width)

    def _new_stem_for(self, row) -> str:
        artist = row['artist_edit'].text().strip()
        title = row['title_edit'].text().strip()
        combined = f"{artist} - {title}" if artist and title else (title or artist)
        return _sanitize_filename(combined)

    def _update_preview(self, row):
        stem = self._new_stem_for(row)
        suffix = Path(row['path']).suffix
        text = f"{stem}{suffix}" if stem else "(enter an artist or a title)"
        row['new_lbl'].setText(self._elide(text, 164))
        row['new_lbl'].setToolTip(text)

    def _apply_renames(self):
        write_tags = self.write_tags_cb.isChecked()
        for row in self.rows:
            old = Path(row['path'])
            artist = row['artist_edit'].text().strip()
            title = row['title_edit'].text().strip()
            if not old.exists():
                self.results.append({'old': str(old), 'new': str(old), 'name': old.name,
                                     'status': 'missing', 'message': 'File no longer exists'})
                continue
            stem = self._new_stem_for(row)
            if not stem:
                self.results.append({'old': str(old), 'new': str(old), 'name': old.name,
                                     'status': 'skipped', 'message': 'Artist and title are both empty'})
                continue
            new_path = old.with_name(f"{stem}{old.suffix}")
            if new_path == old:
                status = 'unchanged'
            elif new_path.exists():
                self.results.append({'old': str(old), 'new': str(new_path), 'name': old.name,
                                     'status': 'conflict', 'message': f"'{new_path.name}' already exists"})
                continue
            try:
                old.rename(new_path)
                status = 'renamed'
            except Exception as e:
                self.results.append({'old': str(old), 'new': str(old), 'name': old.name,
                                     'status': 'failed', 'message': str(e)})
                continue
            if write_tags and artist and title:
                write_metadata_tags(new_path, artist, title)
            self.results.append({'old': str(old), 'new': str(new_path), 'name': old.name,
                                 'status': status, 'message': new_path.name})
        self.accept()
