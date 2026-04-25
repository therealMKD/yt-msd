# Open Source Software under the Apache License, Version 2.0
# PySide6 version of yt-msd

import os
import sys
import json
import threading
try:
    import winreg
except ImportError:
    winreg = None
import yt_dlp
import webbrowser
import urllib.request
import io
import vlc
import shlex
import time
import random
from PIL import Image

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QPushButton, QLineEdit, 
                               QComboBox, QCheckBox, QSlider, QScrollArea, 
                               QSplitter, QSplitterHandle, QFileDialog, QMessageBox, QDialog,
                               QSystemTrayIcon, QMenu, QFrame, QGridLayout,
                               QSizePolicy)
from PySide6.QtCore import Qt, Signal, QTimer, Slot, QPoint, QRect, QMargins
from PySide6.QtGui import QIcon, QPixmap, QImage, QAction, QColor, QPalette, QPainter, QBrush, QFont

# Theme Mapping for custom colors
THEME_COLORS = {
    "Blue": ("#3B8ED0", "#1F6AA5"),
    "Green": ("#1abd33", "#148024"),
    "Red": ("#E31E24", "#C42B1C"),
    "Purple": ("#9146FF", "#6441A5"),
    "Pink": ("#FF4B8B", "#D12D69"),
    "Yellow": ("#FFD700", "#FFC800"),
    "Orange": ("#FF8C00", "#FF7B00"),
    "Grey": ("#808080", "#555555"),
    "White": ("#FFFFFF", "#E5E5E5")
}

AUDIO_EXTENSIONS = {'.mp3', '.flac', '.wav', '.m4a', '.ogg', '.opus', '.aac', '.wma', '.mka', '.aiff', '.alac', '.ape', '.wv'}

def get_system_accent_color():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM")
        val, _ = winreg.QueryValueEx(key, "AccentColor")
        winreg.CloseKey(key)
        b = (val >> 16) & 0xFF
        g = (val >> 8) & 0xFF
        r = val & 0xFF
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return "#0067c0"

def get_system_appearance_mode():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return "Light" if val == 1 else "Dark"
    except Exception:
        return "Dark"

def get_accent_color(color_name):
    if color_name == "System": return get_system_accent_color()
    return THEME_COLORS.get(color_name, THEME_COLORS["Blue"])[0]

def pil_to_qpixmap(pil_image):
    if pil_image is None: return QPixmap()
    img = pil_image.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg)

class ThumbnailWidget(QWidget):
    def __init__(self, video, parent_app, parent=None):
        super().__init__(parent)
        self.setFixedSize(90, 50)
        self.video = video
        self.parent_app = parent_app
        
        self.thumb_label = QLabel(self)
        self.thumb_label.setFixedSize(90, 50)
        self.thumb_label.setStyleSheet("background-color: #2b2b2b;")
        self.thumb_label.setAlignment(Qt.AlignCenter)
        
        accent = get_accent_color(parent_app.accent_color_name)
        self.play_btn = QPushButton("\uE768", self)
        self.play_btn.setFixedSize(30, 30)
        self.play_btn.move(30, 10)
        self.play_btn.setStyleSheet(f"background: rgba(0,0,0,180); color: {accent}; border-radius: 15px; font-weight: bold; font-family: 'Segoe MDL2 Assets'; font-size: 14px; padding: 0px;")
        self.play_btn.clicked.connect(self.on_play)
        self.play_btn.hide()
        
    def on_play(self, checked=False):
        self.parent_app.play_result(self.video)
        
    def enterEvent(self, event):
        self.play_btn.show()
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        self.play_btn.hide()
        super().leaveEvent(event)

class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("Settings")
        self.setMinimumWidth(500)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(25, 25, 25, 25)
        self.layout.setSpacing(15)
        
        # APPEARANCE MODE
        self.layout.addWidget(QLabel("APPEARANCE MODE", font=QFont("Segoe UI Semibold", 10)))
        mode_layout = QHBoxLayout()
        self.mode_btns = {}
        for mode in ["System", "Light", "Dark"]:
            btn = QPushButton(mode)
            btn.setCheckable(True)
            if parent.appearance_mode == mode: btn.setChecked(True)
            btn.clicked.connect(lambda checked=False, m=mode: self._change_mode(m))
            mode_layout.addWidget(btn)
            self.mode_btns[mode] = btn
        self.layout.addLayout(mode_layout)
        
        # ACCENT COLOR
        self.layout.addWidget(QLabel("ACCENT COLOR", font=QFont("Segoe UI Semibold", 10)))
        grid = QGridLayout()
        grid.setSpacing(8)
        colors = ["System"] + list(THEME_COLORS.keys())
        self.accent_btns = {}
        for i, color in enumerate(colors):
            r, c = i // 5, i % 5
            btn = QPushButton()
            btn.setFixedSize(35, 35)
            c_val = get_system_accent_color() if color == "System" else THEME_COLORS[color][0]
            btn.setStyleSheet(f"background-color: {c_val}; border-radius: 6px; border: {'2px solid white' if parent.accent_color_name == color else 'none'};")
            if color == "System": btn.setText("\uE771"); btn.setFont(QFont("Segoe MDL2 Assets", 12))
            btn.clicked.connect(lambda checked=False, clr=color: self._change_accent(clr))
            grid.addWidget(btn, r, c)
            self.accent_btns[color] = btn
        self.layout.addLayout(grid)
        
        # ADVANCED
        self.layout.addWidget(QLabel("CUSTOM YT-DLP ARGUMENTS (ADVANCED)", font=QFont("Segoe UI Semibold", 10)))
        arg_h = QHBoxLayout()
        self.args_cb = QCheckBox()
        self.args_cb.setChecked(parent.use_custom_args)
        self.args_cb.toggled.connect(self._toggle_args)
        arg_h.addWidget(self.args_cb)
        self.args_edit = QLineEdit(parent.custom_args)
        self.args_edit.setPlaceholderText("Arguments...")
        self.args_edit.setEnabled(parent.use_custom_args)
        self.args_edit.textChanged.connect(self._update_args)
        arg_h.addWidget(self.args_edit, 1)
        self.layout.addLayout(arg_h)
        self.layout.addWidget(QLabel("Manual override ignores GUI bitrate/format settings.", font=QFont("Segoe UI", 8)))
        
        # OPTIONS
        self.tray_cb = QCheckBox("Minimize to System Tray")
        self.tray_cb.setChecked(parent.minimize_to_tray)
        self.tray_cb.toggled.connect(self._toggle_tray)
        self.layout.addWidget(self.tray_cb)
        
        self.session_cb = QCheckBox("Restore Last Session on Startup")
        self.session_cb.setChecked(getattr(parent, 'save_place', False))
        self.session_cb.toggled.connect(self._toggle_session)
        self.layout.addWidget(self.session_cb)
        
        self.layout.addStretch()
        
        # RESET
        self.reset_btn = QPushButton("Reset to Default Config")
        self.reset_btn.setObjectName("topIconBtn")
        self.reset_btn.clicked.connect(self._reset_defaults)
        self.layout.addWidget(self.reset_btn)
        
        # FOOTER
        footer = QHBoxLayout()
        footer.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setFixedWidth(100)
        ok_btn.clicked.connect(self.accept)
        footer.addWidget(ok_btn)
        self.layout.addLayout(footer)
        
        self.update_styles()

    def update_styles(self):
        accent = get_accent_color(self.parent.accent_color_name)
        mode = self.parent.appearance_mode
        if mode == "System": mode = get_system_appearance_mode()
        is_light = mode == "Light"
        
        r = int(accent[1:3], 16)
        g = int(accent[3:5], 16)
        b = int(accent[5:7], 16)
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        accent_fg = "black" if brightness > 150 else "white"
        
        for m, b in self.mode_btns.items():
            if m == self.parent.appearance_mode:
                b.setStyleSheet(f"background-color: {accent}; color: {accent_fg}; border-radius: 4px;")
            else:
                b.setStyleSheet(f"background-color: {'#ddd' if is_light else '#444'}; color: {'black' if is_light else 'white'}; border-radius: 4px;")
        
        for color, btn in self.accent_btns.items():
            c_val = get_system_accent_color() if color == "System" else THEME_COLORS[color][0]
            border = f"2px solid {'black' if is_light else 'white'}" if self.parent.accent_color_name == color else "none"
            btn.setStyleSheet(f"background-color: {c_val}; border-radius: 6px; border: {border};")

    def _change_mode(self, mode):
        self.parent.appearance_mode = mode
        self.parent.apply_theme()
        self.update_styles()
        self.parent.save_config()

    def _change_accent(self, color):
        self.parent.accent_color_name = color
        self.parent.apply_theme()
        self.update_styles()
        self.parent.save_config()
        
    def _toggle_args(self, state):
        self.parent.use_custom_args = state
        self.args_edit.setEnabled(state)
        self.parent.save_config()
        
    def _update_args(self, text):
        self.parent.custom_args = text
        self.parent.save_config()
        
    def _toggle_tray(self, state):
        self.parent.minimize_to_tray = state
        self.parent.save_config()
        
    def _toggle_session(self, state):
        self.parent.save_place = state
        self.parent.save_config()
        
    def _reset_defaults(self):
        if QMessageBox.question(self, "Confirm Reset", "This will wipe your config and recent data. Continue?") == QMessageBox.Yes:
            self.parent.reset_to_defaults()
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
        cancel_btn.clicked.connect(self.reject)
        open_btn = QPushButton("Open Playlist")
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

class MainApp(QMainWindow):
    status_signal = Signal(str, bool, str)
    search_results_signal = Signal(list, bool)
    search_failed_signal = Signal()
    thumbnails_loaded_signal = Signal(str, QPixmap)
    playback_started_signal = Signal(str, str, bool)
    queue_update_signal = Signal()
    dl_progress_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("yt-msd | YouTube Media Downloader")
        self.resize(1640, 850)
        
        # State Arrays
        self.search_results = []
        self.queue_items = []
        self.local_folders = []
        self.recent_folders = []
        self.recent_playlists = []
        self.splitter_sizes = [300, 800, 300]
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
        self.show_thumbnails = False
        self.minimize_to_tray = False
        self.save_place = False
        self.last_session = {}
        self.last_search = ""
        
        # Player Flags
        self.is_playing = False
        self.is_downloading = False
        self.current_video_id = None
        self.current_playing_title = ""
        self.playback_index = -1
        self.is_shuffled = False
        self.shuffle_order = []
        self.is_muted = False
        
        if getattr(sys, 'frozen', False):
            self.config_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            self.config_dir = os.path.dirname(os.path.abspath(__file__))
            
        self.config_path = os.path.join(self.config_dir, "gui_config.json")
        self.load_config()
        
        try:
            self.vlc_instance = vlc.Instance('--quiet', '--no-video')
            self.vlc_player = self.vlc_instance.media_player_new()
            if self.vlc_player: self.vlc_player.audio_set_volume(self.volume_val)
        except:
            self.vlc_instance = None; self.vlc_player = None

        self.setup_ui()
        self.apply_theme()
        
        self.status_signal.connect(self._on_status_update)
        self.search_results_signal.connect(self._on_search_results)
        self.search_failed_signal.connect(self._on_search_failed)
        self.playback_started_signal.connect(self._on_playback_started)
        self.queue_update_signal.connect(self._refresh_queue_display)
        self.thumbnails_loaded_signal.connect(self._on_thumbnail_loaded)
        self.dl_progress_signal.connect(lambda txt: self.dl_progress_label.setText(txt))
        
        self.player_timer = QTimer(self)
        self.player_timer.timeout.connect(self.update_player_ui)
        self.player_timer.start(16)
        
        self.setup_tray()
        if self.local_current_path:
            self.load_local_folder(self.local_current_path)
            
        if getattr(self, 'save_place', False) and hasattr(self, 'session_data'):
            sd = self.session_data
            if sd.get('current_video_id') == "local" and sd.get('local_current_path'):
                idx = sd.get('local_playback_index', -1)
                audio_files = [x for x in getattr(self, 'current_local_items', []) if x.get('is_dir') is False]
                if 0 <= idx < len(audio_files):
                    self._on_local_click(audio_files[idx], paused_at_start=True)

        QApplication.instance().installEventFilter(self)

    def load_config(self):
        default_dl = os.path.join(os.path.expanduser("~"), "Downloads")
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    c = json.load(f)
                    self.format_var = c.get('format', 'mp3')
                    self.bitrate_var = c.get('bitrate', '192')
                    self.recent_folders = c.get('folders', [default_dl])
                    self.download_path = self.recent_folders[0] if self.recent_folders else default_dl
                    self.accent_color_name = c.get('accent', 'System')
                    self.appearance_mode = c.get('mode', 'Dark')
                    self.volume_val = c.get('volume', 100)
                    self.local_folders = c.get('local_folders', [])
                    self.local_current_path = c.get('local_current_path', "")
                    self.show_thumbnails = c.get('show_thumbnails', False)
                    self.show_local_metadata = c.get('show_local_metadata', False)
                    self.minimize_to_tray = c.get('minimize_to_tray', False)
                    self.recent_playlists = c.get('recent_playlists', [])
                    self.splitter_sizes = c.get('splitter_sizes', [300, 800, 300])
                    self.use_custom_args = c.get('use_custom_args', False)
                    self.custom_args = c.get('custom_args', '')
                    self.appearance_mode = c.get('mode', 'Dark')
                    self.last_search = c.get('last_search', '')
                    self.save_place = c.get('save_place', False)
                    if self.save_place:
                        self.session_data = c.get('session_data', {})
        except Exception: pass
        if not self.recent_folders:
            self.recent_folders = [default_dl]; self.download_path = default_dl

    def save_config(self):
        c = {
            'format': self.format_combo.currentText(),
            'bitrate': self.bitrate_combo.currentText(),
            'mode': self.appearance_mode,
            'accent': self.accent_color_name,
            'folders': self.recent_folders,
            'local_folders': self.local_folders,
            'local_current_path': self.local_current_path,
            'volume': self.volume_val,
            'show_thumbnails': self.show_thumbnails,
            'show_local_metadata': getattr(self, 'show_local_metadata', False),
            'minimize_to_tray': self.minimize_to_tray,
            'use_custom_args': self.use_custom_args,
            'custom_args': self.custom_args,
            'recent_playlists': self.recent_playlists,
            'splitter_sizes': [self.main_splitter.sizes()[0]] + self.content_splitter.sizes() if hasattr(self, 'main_splitter') else self.splitter_sizes,
            'last_search': self.search_entry.text() if hasattr(self, 'search_entry') else self.last_search,
            'save_place': self.save_place,
            'session_data': {
                'search_results': self.search_results,
                'playback_index': self.playback_index,
                'current_video_id': self.current_video_id,
                'local_current_path': self.local_current_path,
                'local_playback_index': getattr(self, 'local_playback_index', -1)
            }
        }
        try:
            with open(self.config_path, 'w') as f: json.dump(c, f, indent=4)
        except: pass

    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        
        # Generate Icon safely
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor("transparent"))
        painter = QPainter(pixmap)
        painter.setBrush(QColor(get_accent_color(self.accent_color_name)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(8, 8, 48, 48)
        painter.end()
        self.tray_icon.setIcon(QIcon(pixmap))
        
        menu = QMenu(self)
        restore_action = menu.addAction("Restore")
        restore_action.triggered.connect(self.showNormal)
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(QApplication.quit)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def changeEvent(self, event):
        if event.type() == event.Type.WindowStateChange:
            if self.isMinimized() and self.minimize_to_tray:
                self.hide()
        super().changeEvent(event)

    def closeEvent(self, event):
        self.save_config()
        if self.vlc_player: self.vlc_player.stop()
        super().closeEvent(event)

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
        self.show_thumbnails = False
        self.minimize_to_tray = False
        self.splitter_sizes = [300, 800, 300]
        
        # Apply changes
        self.apply_theme()
        if hasattr(self, 'splitter'):
            self.splitter.setSizes(self.splitter_sizes)
        if hasattr(self, 'vol_slider'):
            self.vol_slider.setValue(100)
        self.save_config()
        self._on_status_update("Settings reset to defaults.", False, "#3B8ED0")

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
                import time
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

        # Controls UI
        controls_frame = QFrame()
        c_layout = QVBoxLayout(controls_frame)
        c_layout.setContentsMargins(5, 5, 5, 5)
        c_layout.setSpacing(5)
        self.right_layout.addWidget(controls_frame)
        
        search_r = QHBoxLayout()
        self.toggle_pane_btn = QPushButton("\uE8A0")
        self.toggle_pane_btn.setObjectName("topIconBtn")
        self.toggle_pane_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px;")
        self.toggle_pane_btn.setToolTip("Toggle File Browser")
        self.toggle_pane_btn.clicked.connect(self.toggle_local_pane)
        search_r.addWidget(self.toggle_pane_btn)
        
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("Search YouTube or Paste a Video Link")
        self.search_entry.returnPressed.connect(self.perform_search)
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.perform_search)
        self.playlist_btn = QPushButton("\uE142")
        self.playlist_btn.setObjectName("topIconBtn")
        self.playlist_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px;")
        self.playlist_btn.clicked.connect(self.open_playlist_dialog)
        
        search_r.addWidget(self.search_entry, 1)
        search_r.addWidget(self.search_btn)
        search_r.addWidget(self.playlist_btn)
        settings_btn = QPushButton("\uE713")
        settings_btn.setObjectName("topIconBtn")
        settings_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px;")
        settings_btn.clicked.connect(self.open_settings_dialog)
        search_r.addWidget(settings_btn)
        c_layout.addLayout(search_r)
        
        set_r = QHBoxLayout()
        set_r.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["mp3", "m4a", "flac", "wav", "aac"])
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
        self.path_combo = QComboBox()
        self.path_combo.addItems(self.recent_folders)
        if self.download_path not in self.recent_folders:
            self.path_combo.addItem(self.download_path)
            self.path_combo.setCurrentText(self.download_path)
        set_r.addWidget(self.path_combo, 1)
        
        self.browse_btn = QPushButton("\uE8B7")
        self.browse_btn.setObjectName("topIconBtn")
        self.browse_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px; padding: 0px;")
        self.browse_btn.setFixedSize(36, 30)
        self.browse_btn.clicked.connect(self.browse_folder)
        set_r.addWidget(self.browse_btn)
        set_r.addSpacing(6)
        c_layout.addLayout(set_r)
        
        status_bar = QHBoxLayout()
        self.playing_label = QLabel("")
        self.playing_label.setStyleSheet("font-size: 11px; margin-top: -2px;")
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("font-size: 11px; margin-top: -2px;")
        self.dl_progress_label = QLabel("")
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
        self.prev_btn.clicked.connect(self.play_previous)
        self.prev_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 13px;")
        c.addWidget(self.prev_btn)
        
        self.play_btn = QPushButton("\uE768")
        self.play_btn.setObjectName("playerPlayBtn")
        self.play_btn.clicked.connect(self.toggle_playback)
        self.play_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 24px;")
        c.addWidget(self.play_btn)
        
        self.next_btn = QPushButton("\uE893")
        self.next_btn.setObjectName("playerBtn")
        self.next_btn.clicked.connect(self.play_next)
        self.next_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 13px;")
        c.addWidget(self.next_btn)
        c.addStretch(1)
        
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setStyleSheet("font-size: 11px;")
        c.addWidget(self.time_label)
        p_layout.addLayout(c)
        
        self.progress_slider = QSlider(Qt.Horizontal)
        self.progress_slider.setFixedHeight(12)
        self.progress_slider.setRange(0, 10000)
        self.progress_slider.valueChanged.connect(self.on_seek)
        p_layout.addWidget(self.progress_slider)

        # Restore last search
        if getattr(self, 'last_search', ''):
            self.search_entry.setText(self.last_search)
        
        # Restore session
        if self.save_place and hasattr(self, 'session_data'):
            sd = self.session_data
            if sd.get('search_results'):
                self._on_search_results(sd['search_results'], False)
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
            self.perform_search(is_playlist=is_pl)


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
        self.local_path_combo = QComboBox()
        self.local_path_combo.addItems(self.local_folders)
        h.addWidget(self.local_path_combo, 1)
        local_browse_btn = QPushButton("\uE8B7")
        local_browse_btn.setObjectName("topIconBtn")
        local_browse_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px; padding: 0px;")
        local_browse_btn.setFixedSize(36, 30)
        local_browse_btn.clicked.connect(lambda: self.load_local_folder(QFileDialog.getExistingDirectory(self)))
        h.addWidget(local_browse_btn)
        h.addSpacing(6)
        l.addLayout(h)
        
        self.local_meta_cb = QCheckBox("Show Metadata")
        self.local_meta_cb.setChecked(getattr(self, 'show_local_metadata', False))
        self.local_meta_cb.stateChanged.connect(self.toggle_local_metadata)
        l.addWidget(self.local_meta_cb)
        
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
        self.show_thumb_cb = QCheckBox("Show Thumbnails")
        self.show_thumb_cb.setChecked(self.show_thumbnails)
        self.show_thumb_cb.stateChanged.connect(self.toggle_thumbnails)
        h.addWidget(self.show_thumb_cb)
        
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
        self.dl_btn.clicked.connect(self.start_batch_download)
        h.addWidget(self.dl_btn)
        cb = QPushButton("Clear")
        cb.clicked.connect(self.clear_completed)
        h.addWidget(cb)
        l.addLayout(h)
        
        self.queue_area = QScrollArea()
        self.queue_area.setWidgetResizable(True)
        self.queue_content = QWidget()
        self.queue_content.setObjectName("scrollContent")
        self.queue_vbox = QVBoxLayout(self.queue_content)
        self.queue_vbox.setAlignment(Qt.AlignTop)
        self.queue_area.setWidget(self.queue_content)
        l.addWidget(self.queue_area, 1)
        self.content_splitter.addWidget(w)

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
        import tempfile, os as _os
        checkmark_svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{accent_fg}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
        if not hasattr(self, '_checkmark_svg_path') or not _os.path.exists(self._checkmark_svg_path):
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
        if not hasattr(self, '_downarrow_svg_path') or not _os.path.exists(self._downarrow_svg_path):
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

        self.setStyleSheet("""
            QMainWindow, QDialog {{ background-color: {bg}; }}
            QWidget {{ color: {fg}; font-family: 'Segoe UI'; font-size: 13px; }}
            QWidget#scrollContent {{ background-color: {scroll_bg}; }}
            QWidget#queueItemPending {{ background-color: {queue_item_bg}; border-radius: 4px; margin-bottom: 2px; }}
            QWidget#queueItemFinished {{ background-color: {queue_item_bg_finished}; border-radius: 4px; margin-bottom: 2px; }}
            QLabel {{ color: {fg}; }}
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
            QSlider::groove:horizontal {{ border: none; height: 3px; background: {slider_bg}; border-radius: 1px; }}
            QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 1px; }}
            QSlider::handle:horizontal {{ background: {accent}; width: 14px; height: 14px; margin-top: -6px; margin-bottom: -5px; border-radius: 7px; }}
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
            QPushButton#iconBtn {{
                background-color: transparent;
                color: {fg};
                font-weight: normal;
                padding: 0px;
            }}
            QPushButton#iconBtn:hover {{
                background-color: {btn_hover};
            }}
            QPushButton#topIconBtn {{
                background-color: transparent;
                color: {fg};
                font-weight: normal;
                border: 1px solid {input_border};
                border-radius: 4px;
                padding: 6px 12px;
            }}
            QPushButton#topIconBtn:hover {{
                background-color: {btn_hover};
            }}
            QPushButton#playerBtn {{
                background-color: transparent;
                color: {fg};
                font-weight: normal;
                border-radius: 4px;
                padding: 0px 4px;
            }}
            QPushButton#playerBtn:hover {{
                background-color: {btn_hover};
            }}
            QPushButton#playerPlayBtn {{
                background-color: transparent;
                color: {fg};
                font-weight: normal;
                border-radius: 6px;
                padding: 0px 4px;
            }}
            QPushButton#playerPlayBtn:hover {{
                background-color: {btn_hover};
            }}
        """.format(
            bg=bg, fg=fg, frame_bg=frame_bg, input_bg=input_bg, input_border=input_border,
            scroll_bg=scroll_bg, splitter_handle=splitter_handle, slider_bg=slider_bg,
            hover_bg=hover_bg, hover_fg=hover_fg, accent=accent, accent_fg=accent_fg,
            queue_item_bg=queue_item_bg, queue_item_bg_finished=queue_item_bg_finished,
            btn_hover=btn_hover, checkmark_path=checkmark_path, downarrow_path=downarrow_path,
            main_btn_border=main_btn_border
        ))

    # --- Local Folder Logic ---
    def load_local_folder(self, path):
        if not path or not os.path.exists(path): return
        path = os.path.abspath(path)
        self.local_current_path = path
        
        if path not in self.local_folders:
            self.local_folders.insert(0, path)
            self.local_folders = self.local_folders[:5]
            self.local_path_combo.clear()
            self.local_path_combo.addItems(self.local_folders)
            
        self.local_path_combo.setCurrentText(path)
        self.save_config()
        self.refresh_local_list()

    def toggle_local_metadata(self, state):
        self.show_local_metadata = (state == Qt.Checked.value)
        self.save_config()
        self.refresh_local_list()

    def refresh_local_list(self):
        while self.local_vbox.count():
            item = self.local_vbox.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        if not self.local_current_path or not os.path.exists(self.local_current_path): return
        
        items = []
        try:
            parent = os.path.dirname(self.local_current_path)
            if parent and parent != self.local_current_path:
                items.append({'name': ".. (Back)", 'path': parent, 'is_dir': True})
            with os.scandir(self.local_current_path) as current_dir:
                for entry in current_dir:
                    if entry.is_dir():
                        items.append({'name': entry.name, 'path': entry.path, 'is_dir': True})
                    elif entry.is_file():
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in AUDIO_EXTENSIONS:
                            items.append({'name': entry.name, 'path': entry.path, 'is_dir': False})
        except: pass
        
        items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        self.current_local_items = items
        
        self.local_btns = []
        for item in items:
            text = f"{'📁' if item['is_dir'] else '🎵'}  {item.get('meta_name', item['name']) if getattr(self, 'show_local_metadata', False) else item['name']}"
            btn = QPushButton(text)
            btn.setObjectName("transparentBtn")
            btn.clicked.connect(lambda checked=False, i=item: self._on_local_click(i))
            self.local_vbox.addWidget(btn)
            if not item['is_dir']:
                self.local_btns.append((btn, item))
                
        if getattr(self, 'show_local_metadata', False) and self.local_btns:
            self._fetch_local_metadata_bg()
            
    def _fetch_local_metadata_bg(self):
        btns_to_process = list(self.local_btns)
        def bg_task():
            for btn, item in btns_to_process:
                if not getattr(self, 'show_local_metadata', False): break
                if 'meta_name' not in item:
                    try:
                        media = self.vlc_instance.media_new(item['path'])
                        media.parse()
                        title = media.get_meta(vlc.Meta.Title)
                        artist = media.get_meta(vlc.Meta.Artist)
                        if title:
                            item['meta_name'] = f"{artist} - {title}" if artist else title
                        else:
                            item['meta_name'] = item['name']
                    except:
                        item['meta_name'] = item['name']
                # Update UI safely
                QTimer.singleShot(0, lambda b=btn, i=item: b.setText(f"🎵  {i['meta_name']}"))
        threading.Thread(target=bg_task, daemon=True).start()

    def _on_local_click(self, item, paused_at_start=False):
        if item['is_dir']: 
            self.load_local_folder(item['path'])
        else:
            self._on_status_update(f"Playing Local: {item['name']}", False, "#3B8ED0")
            url = item['path'].replace("\\", "/")
            if not url.startswith("file:///"): url = "file:///" + url
            self.current_video_id = "local"
            
            audio_files = [x for x in getattr(self, 'current_local_items', []) if x.get('is_dir') is False]
            for i, af in enumerate(audio_files):
                if af.get('path') == item.get('path'):
                    self.local_playback_index = i
                    break
                    
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
            self.playback_started_signal.emit(item['name'], "local", paused_at_start)

    def toggle_thumbnails(self, state):
        self.show_thumbnails = state == Qt.Checked.value
        self.save_config()
        if self.search_results:
            self._on_search_results(self.search_results, False)

    def open_settings_dialog(self):
        d = SettingsDialog(self)
        d.exec()

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

    def perform_search(self, is_playlist=False):
        query = self.search_entry.text()
        if not query: return
        self._on_status_update("Searching...", False, "#3B8ED0")
        self.search_btn.setEnabled(False)
        
        def bg_search():
            try:
                with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                    if "youtube.com" in query or "youtu.be" in query or "http" in query:
                        info = ydl.extract_info(query, download=False)
                        if 'entries' in info: res = info['entries']
                        else: res = [info]
                    else:
                        info = ydl.extract_info(f"ytsearch15:{query}", download=False)
                        res = [e for e in info['entries'] if e.get('id')]
                        
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
            except Exception:
                self.search_failed_signal.emit()
                
        threading.Thread(target=bg_search, daemon=True).start()

    def _on_search_results(self, res, is_playlist):
        self.search_btn.setEnabled(True)
        self.search_results = res
        self._thumbnail_labels = getattr(self, '_thumbnail_labels', {})
        self._thumbnail_labels.clear()
        
        while self.results_vbox.count():
            item = self.results_vbox.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        for video in res[:30]:
            w = QWidget()
            l = QHBoxLayout(w)
            l.setContentsMargins(2,2,2,2)
            
            if self.show_thumbnails:
                tw = ThumbnailWidget(video, self)
                l.addWidget(tw)
                self._thumbnail_labels[video['id']] = tw.thumb_label
                threading.Thread(target=self._fetch_thumbnail, args=(video,), daemon=True).start()
            else:
                pbtn = QPushButton("\uE768")
                pbtn.setFixedWidth(40)
                pbtn.setObjectName("iconBtn")
                pbtn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px;")
                pbtn.clicked.connect(lambda checked=False, v=video: self.play_result(v))
                l.addWidget(pbtn)
                
            title = video.get('title', 'Unknown')
            if len(title) > 55: title = title[:52] + "..."
            cb = QCheckBox(f"{title}")
            
            # Persist checked state
            if any(q['video']['id'] == video['id'] for q in self.queue_items):
                cb.setChecked(True)
                
            cb.stateChanged.connect(lambda state, v=video: self.toggle_queue(v, state))
            l.addWidget(cb, 1)
            
            # Open on YouTube button
            yt_btn = QPushButton("")
            yt_btn.setObjectName("iconBtn")
            yt_btn.setToolTip("Open on YouTube")
            yt_btn.setFixedSize(28, 28)
            yt_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 13px;")
            vid_id = video.get('id', '')
            yt_btn.clicked.connect(lambda checked=False, vid=vid_id: __import__('webbrowser').open(f'https://www.youtube.com/watch?v={vid}'))
            l.addWidget(yt_btn)
            
            self.results_vbox.addWidget(w)
            
        self._on_status_update(f"Found {len(res)} results.", False, "white")

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

    def _refresh_queue_display(self):
        while self.queue_vbox.count():
            item = self.queue_vbox.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        self.queue_label.setText(f"Download Queue ({len(self.queue_items)})")
        
        for idx, q in enumerate(self.queue_items):
            w = QWidget()
            l = QHBoxLayout(w)
            l.setContentsMargins(5,5,5,5)
            
            st = "\uE73E " if q['status'] == "Finished" else ("\uE896 " if q['status'] == "Downloading" else "")
            t = q['video'].get('title', 'Unknown')
            if len(t) > 40: t = t[:37] + "..."
            
            l.addWidget(QLabel(f"<span style='font-family: \"Segoe MDL2 Assets\";'>{st}</span> {t}"), 1)
            
            rm_btn = QPushButton("\uE711")
            rm_btn.setObjectName("iconBtn")
            rm_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 14px;")
            rm_btn.setFixedSize(26, 26)
            rm_btn.clicked.connect(lambda checked=False, i=idx: self.remove_from_queue(i))
            l.addWidget(rm_btn)
            
            w.setObjectName("queueItemFinished" if q['status'] == "Finished" else "queueItemPending")
            self.queue_vbox.addWidget(w)

    def remove_from_queue(self, idx):
        if idx < len(self.queue_items):
            self.queue_items.pop(idx)
            self.queue_update_signal.emit()

    def clear_completed(self, checked=False):
        self.queue_items = [q for q in self.queue_items if q['status'] != "Finished"]
        self.queue_update_signal.emit()

    def start_batch_download(self):
        if self.is_downloading: return
        pending = [q for q in self.queue_items if q['status'] == "Pending"]
        if not pending: return
        
        self.is_downloading = True
        self.dl_btn.setEnabled(False)
        self.dl_btn.setText("Downloading...")
        self.save_config()
        folder = self.path_combo.currentText()
        
        def bg_download():
            for q in self.queue_items:
                if q['status'] == "Pending":
                    q['status'] = "Downloading"
                    self.queue_update_signal.emit()
                    try:
                        ydl_opts = {
                            'format': 'bestaudio/best',
                            'outtmpl': f"{folder}/%(title)s.%(ext)s",
                            'postprocessors': [{
                                'key': 'FFmpegExtractAudio',
                                'preferredcodec': self.format_combo.currentText(),
                                'preferredquality': self.bitrate_combo.currentText(),
                            }],
                            'progress_hooks': [self._dl_progress_hook],
                            'quiet': True
                        }
                        if getattr(sys, 'frozen', False):
                            ydl_opts['ffmpeg_location'] = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
                            
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            ydl.download([f"https://www.youtube.com/watch?v={q['video']['id']}"])
                    except Exception: pass
                    q['status'] = "Finished"
                    self.queue_update_signal.emit()
            
            # Hacky callback to main thread
            self.status_signal.emit("Batch complete!", False, "#1abd33")
            
        threading.Thread(target=bg_download, daemon=True).start()
        
    def _on_batch_complete(self):
        self.is_downloading = False
        self.dl_btn.setEnabled(True)
        self.dl_btn.setText("Download All")

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

    def _dl_progress_hook(self, d):
        if d['status'] == 'downloading':
            p = d.get('_percent_str', '').strip()
            if p:
                self.dl_progress_signal.emit(f"Downloading: {p}")
        elif d['status'] == 'finished':
            self.dl_progress_signal.emit("Processing...")

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
        if "Batch complete" in text:
            self.dl_progress_signal.emit("")
            self._on_batch_complete()

    def play_result(self, video, paused_at_start=False):
        self._on_status_update(f"Fetching stream: {video.get('title', 'Unknown')}...", False, "#3B8ED0")
        
        # update index
        self.playback_index = -1
        for i, res in enumerate(self.search_results):
            if res['id'] == video['id']:
                self.playback_index = i; break
                
        def bg_fetch():
            try:
                with yt_dlp.YoutubeDL({'quiet': True, 'format': 'bestaudio/best'}) as ydl:
                    info = ydl.extract_info(f"https://www.youtube.com/watch?v={video['id']}", download=False)
                    url = info['url']
                    media = self.vlc_instance.media_new(url)
                    self.vlc_player.set_media(media)
                    if paused_at_start:
                        self.vlc_player.audio_set_mute(True)
                        self.vlc_player.play()
                        import time
                        time.sleep(0.25)
                        self.vlc_player.set_pause(1)
                        self.vlc_player.set_position(0)
                        self.vlc_player.audio_set_mute(False)
                    else:
                        self.vlc_player.play()
                    self.playback_started_signal.emit(video.get('title', 'Unknown'), video['id'], paused_at_start)
            except Exception:
                self.search_failed_signal.emit()
        threading.Thread(target=bg_fetch, daemon=True).start()

    def _on_playback_started(self, title, vid_id, paused_at_start=False):
        self.current_playing_title = title
        self.current_video_id = vid_id
        if paused_at_start:
            self.is_playing = False
            self.play_btn.setText("\uE768")
            self._on_status_update(f"Ready: {title}", False, "gray")
        else:
            self.is_playing = True
            self.play_btn.setText("\uE769")
            self._on_status_update(f"Playing: {title}", True, "gray")

    def eventFilter(self, obj, event):
        if event.type() == event.Type.KeyPress and event.key() == Qt.Key_Space:
            fw = QApplication.focusWidget()
            if not isinstance(fw, QLineEdit):
                self.toggle_playback()
                return True
        return super().eventFilter(obj, event)

    def open_search_on_youtube(self):
        import webbrowser, urllib.parse
        query = self.search_entry.text().strip()
        if not query: return
        if 'youtube.com' in query or 'youtu.be' in query:
            webbrowser.open(query)
        else:
            webbrowser.open(f'https://www.youtube.com/results?search_query={urllib.parse.quote(query)}')

    def toggle_playback(self):
        if not self.vlc_player: return
        if self.vlc_player.is_playing():
            self.vlc_player.pause()
            self.play_btn.setText("\uE768")
            self.is_playing = False
        else:
            self.vlc_player.play()
            self.play_btn.setText("\uE769")
            self.is_playing = True
            
    def play_previous(self):
        if self.current_video_id == "local" and hasattr(self, 'local_playback_index'):
            audio_files = [x for x in getattr(self, 'current_local_items', []) if x.get('is_dir') is False]
            if self.local_playback_index > 0:
                self.local_playback_index -= 1
                self._on_local_click(audio_files[self.local_playback_index])
            return
            
        if self.playback_index > 0:
            self.playback_index -= 1
            self.play_result(self.search_results[self.playback_index])
            
    def play_next(self):
        if self.current_video_id == "local" and hasattr(self, 'local_playback_index'):
            audio_files = [x for x in getattr(self, 'current_local_items', []) if x.get('is_dir') is False]
            if self.local_playback_index + 1 < len(audio_files):
                self.local_playback_index += 1
                self._on_local_click(audio_files[self.local_playback_index])
            return
            
        if self.playback_index + 1 < len(self.search_results):
            self.playback_index += 1
            self.play_result(self.search_results[self.playback_index])

    def on_seek(self, val):
        # Ignore programmatic updates triggering seek
        if not self.progress_slider.isSliderDown(): return
        if self.vlc_player:
            self.vlc_player.set_position(float(val)/10000.0)

    def on_volume_changed(self, val):
        self.volume_val = val
        if self.vlc_player:
            # VLC uses 0-200 (100=normal). Map slider 0-100 → vlc 0-100, 101-150 → vlc 101-200
            vlc_vol = val if val <= 100 else int(100 + (val - 100) * 2)
            self.vlc_player.audio_set_volume(vlc_vol)
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
        if not self.vlc_player or not self.current_video_id: return
        
        # Check ended
        if self.vlc_player.get_state() == vlc.State.Ended:
            if not getattr(self, '_ended_trigger', False):
                self._ended_trigger = True
                self.play_next()
        else:
            self._ended_trigger = False
            
        pos = self.vlc_player.get_position() * 10000
        ms = self.vlc_player.get_time()
        total_ms = self.vlc_player.get_length()
        if total_ms > 0:
            cur_str = f"{int(ms/60000)}:{int((ms%60000)/1000):02d}"
            tot_str = f"{int(total_ms/60000)}:{int((total_ms%60000)/1000):02d}"
            self.time_label.setText(f"{cur_str} / {tot_str}")
            if not self.progress_slider.isSliderDown():
                self.progress_slider.blockSignals(True)
                self.progress_slider.setValue(int(pos))
                self.progress_slider.blockSignals(False)

    def _on_thumbnail_loaded(self, vid_id, pixmap):
        if hasattr(self, '_thumbnail_labels') and vid_id in self._thumbnail_labels:
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(90, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self._thumbnail_labels[vid_id].setPixmap(scaled_pixmap)

    def _fetch_thumbnail(self, v):
        vid_id = v.get('id')
        if not vid_id: return
        if vid_id in self.thumbnail_cache:
            self.thumbnails_loaded_signal.emit(vid_id, self.thumbnail_cache[vid_id])
            return

        try:
            url = f"https://i.ytimg.com/vi/{vid_id}/mqdefault.jpg"
            with urllib.request.urlopen(url) as req:
                data = req.read()
                if self.thumbnail_cache_size + len(data) > 256 * 1024 * 1024:
                    self.thumbnail_cache.clear(); self.thumbnail_cache_size = 0
                
                img = Image.open(io.BytesIO(data))
                qpixmap = pil_to_qpixmap(img)
                self.thumbnail_cache[vid_id] = qpixmap
                self.thumbnail_cache_size += len(data)
                self.thumbnails_loaded_signal.emit(vid_id, qpixmap)
        except: pass

if __name__ == "__main__":
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    app = QApplication(sys.argv)
    window = MainApp()
    window.show()
    sys.exit(app.exec())