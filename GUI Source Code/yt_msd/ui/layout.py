# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.ui.layout).
#
# A mixin, not a standalone module: MainApp inherits from this class, so what is written here
# are ordinary methods and `self` is the MainApp instance. They were lifted out of the class
# body in wave 6 with their text unchanged - only the imports needed to reach the rest of the
# program were added, and the inside of a multi-line string kept the indentation it was written
# with, because changing it would change what the program shows rather than where it is kept.

import time
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QComboBox, QCheckBox, QSlider, QSplitter, QSplitterHandle, QFrame, QSizePolicy
from PySide6.QtCore import Qt
from yt_msd.constants import DOWNLOAD_FORMATS, STOP_AFTER_STATE_NAMES, STOP_AFTER_TOOLTIPS
from yt_msd.ui.widgets import ClickableSlider

class LayoutMixin:
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
        
        # The percentage is typed as well as dragged. The number is what everything else in the
        # program works in - the tray presets, the saved config, libVLC itself - so a listener who
        # wants exactly 73% should be able to say 73 instead of hunting for it along a 100 px
        # slider. What is written is still the read-out it always was, only writable: it keeps the
        # caption's 50 px and it wears no frame, because the app's QLineEdit rule (background,
        # border, 6 px of padding) is taken off it by the QLineEdit#volPct line in apply_theme.
        # The percent sign is a read-out and not part of the number, so nothing is ever edited
        # around it: whichever way the caret arrives - a click or the Tab key - the number is
        # picked out whole so the first digit typed replaces it rather than landing inside it, and
        # a click or an End key that lands past the sign pulls the caret back onto the number.
        # Picking it out on a click needs doing twice, because Qt hands that click as two events:
        # the focus arrives first and picks out the number, then the press arrives and QLineEdit
        # answers it by putting the caret where the pointer landed, selection gone. A click on this
        # box is a request to change the volume, so the number is picked out again after that
        # caret - while a click on a box that already has the caret is left alone, because that is
        # the click that means "put the caret between the digits". It commits on Enter
        # or the moment the click goes anywhere else in the window - the same moment its caret goes,
        # because that click is the focus-out that MainApp._release_typing_focus answers with - and
        # keeps the double click the caption had, which put the volume back to 100.
        class VolBox(QLineEdit):
            def __init__(self, text):
                super().__init__(text)
                # A number arriving from the slider is written here with the caret wherever Qt
                # happens to put it - setText puts it past the sign - and the sign is not a place a
                # caret belongs, so both the writing and the caret it leaves are pulled back onto
                # the number.
                self.textChanged.connect(lambda _text: self._keep_caret_on_the_number())
                self.cursorPositionChanged.connect(lambda _position: self._keep_caret_on_the_number())
                # Set by the focus that a click brought, and answered by the press that follows it
                # in the same click. See the pick-out in mousePressEvent below.
                self._focus_came_with_a_click = False

            def _number_end(self):
                text = self.text()
                return len(text) - 1 if text.endswith("%") else len(text)

            def _keep_caret_on_the_number(self):
                end = self._number_end()
                start, length = self.selectionStart(), self.selectionLength()
                if length and start + length > end:
                    # A selection that reached the sign - a select-all does - keeps the part that is
                    # the number and loses the sign, rather than being thrown away with the caret.
                    self.setSelection(start, max(0, end - start))
                if self.cursorPosition() > end:
                    self.setCursorPosition(end)      # clearing the selection with it is the point

            def _pick_out_the_number(self):
                self.setSelection(0, self._number_end())   # typing replaces the number, the sign stays

            def focusInEvent(self, e):
                self._pick_out_the_number()
                # A click is remembered as such because the press that came with it is about to
                # arrive and undo this; a caret arriving from the Tab key has no press coming, and
                # its number stays picked out.
                self._focus_came_with_a_click = (e.reason() == Qt.MouseFocusReason)
                super().focusInEvent(e)

            def mousePressEvent(self, e):
                super().mousePressEvent(e)
                if self._focus_came_with_a_click:
                    self._focus_came_with_a_click = False
                    self._pick_out_the_number()   # the click that brought the focus means "change it"
                else:
                    self._keep_caret_on_the_number()

            def keyPressEvent(self, e):
                if (e.key() == Qt.Key_Delete and not self.selectionLength()
                        and self.text().endswith("%") and self.cursorPosition() == self._number_end()):
                    e.accept()        # forward delete stops at the sign - it is not part of the number
                    return
                super().keyPressEvent(e)
                self._keep_caret_on_the_number()

            def mouseDoubleClickEvent(self, e):
                win = self.window()
                if hasattr(win, 'vol_slider'):
                    win.vol_slider.setValue(100)
                e.accept()

        self.vol_pct = VolBox(f"{self.volume_val}%")
        self.vol_pct.setObjectName("volPct")
        self.vol_pct.setFixedWidth(50)      # the width the caption had: "150%" is 32 px of text and
                                            # the box now adds nothing around it
        self.vol_pct.setAlignment(Qt.AlignCenter)
        self.vol_pct.setMaxLength(4)      # 0 to 150 and the percent sign it is shown with
        self.vol_pct.setToolTip("Type a volume from 0 to 150 and press Enter")
        self.vol_pct.returnPressed.connect(self.on_volume_typed)
        self.vol_pct.editingFinished.connect(self.on_volume_typed)
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
        #
        # `v_id` is bound here, not only inside the branch below, because the re-search that
        # follows hands it to `perform_search` whatever the start looked like. A start with the
        # "remember my place" option off - which is how it ships, `save_place` defaults to False -
        # or one with nothing saved never reaches the line that used to be the only assignment,
        # and the re-search then read a local that had never been given a value: the window died
        # in setup_ui with an UnboundLocalError before it was drawn. None is what perform_search
        # asks for when there is no fetch to keep, so that is what a start with no session says.
        v_id = None
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
