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
        self.layout.addWidget(QLabel("\uE946 Manual override ignores GUI bitrate/format settings.", font=QFont("Segoe UI", 8)))
        
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
        self.reset_btn.setStyleSheet("background-color: transparent; border: 1px solid #555; font-weight: normal;")
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
        
        for m, b in self.mode_btns.items():
            if m == self.parent.appearance_mode:
                b.setStyleSheet(f"background-color: {accent}; color: white; border-radius: 4px;")
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
        open_btn.setStyleSheet(f"background-color: {accent}; color: white; border-radius: 4px; padding: 6px 12px; font-weight: bold;")
        cancel_btn.setStyleSheet("background-color: #555555; color: white; border-radius: 4px; padding: 6px 12px; font-weight: bold;")
        h.addWidget(cancel_btn)
        h.addWidget(open_btn)
        l.addLayout(h)

class MainApp(QMainWindow):
    status_signal = Signal(str, bool, str)
    search_results_signal = Signal(list, bool)
    search_failed_signal = Signal()
    thumbnails_loaded_signal = Signal(str, QPixmap)
    playback_started_signal = Signal(str, str)
    queue_update_signal = Signal()

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
        
        self.player_timer = QTimer(self)
        self.player_timer.timeout.connect(self.update_player_ui)
        self.player_timer.start(16)
        
        self.setup_tray()
        if self.local_current_path:
            self.load_local_folder(self.local_current_path)

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
            'minimize_to_tray': self.minimize_to_tray,
            'use_custom_args': self.use_custom_args,
            'custom_args': self.custom_args,
            'recent_playlists': self.recent_playlists,
            'splitter_sizes': self.splitter.sizes() if hasattr(self, 'splitter') else self.splitter_sizes,
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
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Upper Splitter
        class ResetHandle(QSplitterHandle):
            _last_click = 0
            def mousePressEvent(self, e):
                import time
                now = time.time()
                if now - ResetHandle._last_click < 0.35:
                    self.splitter().setSizes([300, 800, 300])
                    e.accept(); return
                ResetHandle._last_click = now
                super().mousePressEvent(e)
        class ResetSplitter(QSplitter):
            def createHandle(self):
                return ResetHandle(self.orientation(), self)
        self.splitter = ResetSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter, 1)
        
        self._setup_local_pane()
        self._setup_results_pane()
        self._setup_queue_pane()
        self.splitter.setSizes(getattr(self, 'splitter_sizes', [300, 800, 300]))

        # Controls UI
        controls_frame = QFrame()
        c_layout = QVBoxLayout(controls_frame)
        main_layout.addWidget(controls_frame)
        
        search_r = QHBoxLayout()
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("Search YouTube or Paste a Video Link")
        self.search_entry.returnPressed.connect(self.perform_search)
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.perform_search)
        self.playlist_btn = QPushButton("\uE142")
        self.playlist_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px; background-color: transparent; border: 1px solid #555;")
        self.playlist_btn.clicked.connect(self.open_playlist_dialog)
        
        search_r.addWidget(self.search_entry, 1)
        search_r.addWidget(self.search_btn)
        search_r.addWidget(self.playlist_btn)
        settings_btn = QPushButton("\uE713")
        settings_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px; background-color: transparent; border: 1px solid #555;")
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
        self.browse_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px; padding: 0px;")
        self.browse_btn.setFixedSize(36, 30)
        self.browse_btn.clicked.connect(self.browse_folder)
        set_r.addWidget(self.browse_btn)
        set_r.addSpacing(6)
        
        self.dl_btn = QPushButton("Download All")
        self.dl_btn.clicked.connect(self.start_batch_download)
        set_r.addWidget(self.dl_btn)
        c_layout.addLayout(set_r)
        
        self.status_label = QLabel("Ready")
        c_layout.addWidget(self.status_label)

        # Bottom Player
        player_frame = QFrame()
        p_layout = QVBoxLayout(player_frame)
        main_layout.addWidget(player_frame)
        
        c = QHBoxLayout()
        c.addWidget(QLabel("Volume"))
        
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
        
        self.vol_pct = QLabel(f"{self.volume_val}%")
        self.vol_pct.setFixedWidth(50)
        if self.volume_val > 100: self.vol_pct.setStyleSheet("color: #E31E24; font-weight: bold;")
        c.addWidget(self.vol_pct)
        
        c.addStretch(1)
        _btn_ss = "background: transparent; color: white; font-family: 'Segoe MDL2 Assets'; font-size: 14px; border-radius: 4px; padding: 2px 4px;"
        _btn_ss_hover = "background: transparent; color: white; font-family: 'Segoe MDL2 Assets'; font-size: 14px; border-radius: 4px; padding: 2px 4px;" + " /* hover set via stylesheet */"
        
        self.prev_btn = QPushButton("\uE892")
        self.prev_btn.clicked.connect(self.play_previous)
        self.prev_btn.setStyleSheet("QPushButton { background: transparent; color: white; font-family: 'Segoe MDL2 Assets'; font-size: 14px; border-radius: 4px; padding: 2px 6px; } QPushButton:hover { background: rgba(255,255,255,30); }")
        c.addWidget(self.prev_btn)
        
        self.play_btn = QPushButton("\uE768")
        self.play_btn.clicked.connect(self.toggle_playback)
        self.play_btn.setStyleSheet("QPushButton { background: transparent; color: white; font-family: 'Segoe MDL2 Assets'; font-size: 28px; border-radius: 6px; padding: 2px 6px; } QPushButton:hover { background: rgba(255,255,255,30); }")
        c.addWidget(self.play_btn)
        
        self.next_btn = QPushButton("\uE893")
        self.next_btn.clicked.connect(self.play_next)
        self.next_btn.setStyleSheet("QPushButton { background: transparent; color: white; font-family: 'Segoe MDL2 Assets'; font-size: 14px; border-radius: 4px; padding: 2px 6px; } QPushButton:hover { background: rgba(255,255,255,30); }")
        c.addWidget(self.next_btn)
        c.addStretch(1)
        
        self.time_label = QLabel("0:00 / 0:00")
        c.addWidget(self.time_label)
        p_layout.addLayout(c)
        
        self.progress_slider = QSlider(Qt.Horizontal)
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
                # If we have a stored index, we might want to load it (paused)
                if self.playback_index >= 0 and self.playback_index < len(self.search_results):
                    # We'll implement a 'load_only' flag for play_result or just trigger the start logic
                    # but set position to 0 and pause immediately.
                    # For now just set the index.
                    pass
            
            if sd.get('current_video_id') == "local" and sd.get('local_current_path'):
                self.local_playback_index = sd.get('local_playback_index', -1)
                # Display will be handled by standard local folder load
            
            # Restore playback state if item exists
            v_id = sd.get('current_video_id')
            if v_id and v_id != "local":
                # Find the video object in results if possible
                results = sd.get('search_results', [])
                idx = sd.get('playback_index', -1)
                if 0 <= idx < len(results):
                    video = results[idx]
                    self.play_result(video)
                    # Use a timer to ensure we pause after it starts loading
                    QTimer.singleShot(100, lambda: self.vlc_player.pause() if self.vlc_player else None)
                    QTimer.singleShot(150, lambda: self.vlc_player.set_position(0) if self.vlc_player else None)


    def _setup_local_pane(self):
        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(0,0,0,0)
        l.addWidget(QLabel("Local Folder"))
        
        h = QHBoxLayout()
        self.local_path_combo = QComboBox()
        self.local_path_combo.addItems(self.local_folders)
        h.addWidget(self.local_path_combo, 1)
        local_browse_btn = QPushButton("\uE8B7")
        local_browse_btn.setStyleSheet("font-family: 'Segoe MDL2 Assets'; font-size: 16px; padding: 0px;")
        local_browse_btn.setFixedSize(36, 30)
        local_browse_btn.clicked.connect(lambda: self.load_local_folder(QFileDialog.getExistingDirectory(self)))
        h.addWidget(local_browse_btn)
        h.addSpacing(6)
        l.addLayout(h)
        
        self.local_list = QScrollArea()
        self.local_list.setWidgetResizable(True)
        self.local_content = QWidget()
        self.local_vbox = QVBoxLayout(self.local_content)
        self.local_vbox.setAlignment(Qt.AlignTop)
        self.local_list.setWidget(self.local_content)
        l.addWidget(self.local_list, 1)
        self.splitter.addWidget(w)

    def _setup_results_pane(self):
        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(0,0,0,0)
        h = QHBoxLayout()
        h.addWidget(QLabel("Search Results"))
        h.addStretch()
        self.show_thumb_cb = QCheckBox("Show Thumbnails")
        self.show_thumb_cb.setChecked(self.show_thumbnails)
        self.show_thumb_cb.stateChanged.connect(self.toggle_thumbnails)
        self.show_thumb_cb.setContentsMargins(0, 0, 8, 0)
        h.addWidget(self.show_thumb_cb)
        l.addLayout(h)
        
        self.results_area = QScrollArea()
        self.results_area.setWidgetResizable(True)
        self.results_content = QWidget()
        self.results_vbox = QVBoxLayout(self.results_content)
        self.results_vbox.setAlignment(Qt.AlignTop)
        self.results_area.setWidget(self.results_content)
        l.addWidget(self.results_area, 1)
        self.splitter.addWidget(w)
        
    def _setup_queue_pane(self):
        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(0,0,0,0)
        h = QHBoxLayout()
        self.queue_label = QLabel("Download Queue (0)")
        h.addWidget(self.queue_label)
        h.addStretch()
        cb = QPushButton("Clear")
        cb.clicked.connect(self.clear_completed)
        h.addWidget(cb)
        l.addLayout(h)
        
        self.queue_area = QScrollArea()
        self.queue_area.setWidgetResizable(True)
        self.queue_content = QWidget()
        self.queue_vbox = QVBoxLayout(self.queue_content)
        self.queue_vbox.setAlignment(Qt.AlignTop)
        self.queue_area.setWidget(self.queue_content)
        l.addWidget(self.queue_area, 1)
        self.splitter.addWidget(w)

    def apply_theme(self):
        mode = self.appearance_mode
        if mode == "System": mode = get_system_appearance_mode()
        
        accent = get_accent_color(self.accent_color_name)
        
        if mode == "Light":
            bg = "#f3f3f3"
            fg = "#1a1a1a"
            frame_bg = "#ffffff"
            input_bg = "#e8e8e8"
            input_border = "#ccc"
            scroll_bg = "#fafafa"
            splitter_handle = "#ddd"
            slider_bg = "#ddd"
            hover_bg = "#000000"
            hover_fg = "#ffffff"
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

        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {bg}; }}
            QWidget {{ color: {fg}; font-family: 'Segoe UI'; font-size: 13px; }}
            QLabel {{ color: {fg}; }}
            QPushButton {{ 
                background-color: {accent}; 
                color: white; border: none; padding: 6px 12px; border-radius: 4px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {hover_bg}; color: {hover_fg}; }}
            QPushButton:disabled {{ background-color: #555555; color: #888888; }}
            QLineEdit, QComboBox {{ 
                background-color: {input_bg}; color: {fg}; border: 1px solid {input_border}; padding: 6px; border-radius: 4px;
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
            QCheckBox::indicator {{ width: 18px; height: 18px; border: 1px solid {accent}; border-radius: 3px; background: {frame_bg}; }}
            QCheckBox::indicator:checked {{ background: {accent}; image: url(none); }}
        """)

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
        for item in items:
            btn = QPushButton(f"{'📁' if item['is_dir'] else '🎵'}  {item['name']}")
            btn.setStyleSheet("QPushButton { text-align: left; background-color: transparent; color: white; padding: 4px; font-weight: normal; border-radius: 0px; } QPushButton:hover { background-color: #555555; color: white; }")
            btn.clicked.connect(lambda checked=False, i=item: self._on_local_click(i))
            self.local_vbox.addWidget(btn)

    def _on_local_click(self, item):
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
            self.vlc_player.play()
            self.playback_started_signal.emit(item['name'], "local")

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
                pbtn.setStyleSheet("background: transparent; color: white; font-family: 'Segoe MDL2 Assets'; font-size: 16px;")
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
            rm_btn.setStyleSheet("background: transparent; color: white; font-family: 'Segoe MDL2 Assets'; font-size: 14px; padding: 0px;")
            rm_btn.setFixedSize(26, 26)
            rm_btn.clicked.connect(lambda checked=False, i=idx: self.remove_from_queue(i))
            l.addWidget(rm_btn)
            
            w.setStyleSheet("QWidget { background-color: #333333; border-radius: 4px; margin-bottom: 2px;}" if q['status'] != "Finished" else "QWidget { background-color: #1a1a1a; border-radius: 4px; margin-bottom: 2px;}")
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

    # --- Player Logic ---
    def _on_status_update(self, text, is_playing, color):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};")
        if "Batch complete" in text:
            self._on_batch_complete()

    def play_result(self, video):
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
                    self.vlc_player.play()
                    self.playback_started_signal.emit(video.get('title', 'Unknown'), video['id'])
            except Exception:
                self.search_failed_signal.emit()
        threading.Thread(target=bg_fetch, daemon=True).start()

    def _on_playback_started(self, title, vid_id):
        self.current_playing_title = title
        self.current_video_id = vid_id
        self.is_playing = True
        self.play_btn.setText("\uE769")
        self._on_status_update(f"Playing: {title}", True, "gray")

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
                self.vol_pct.setStyleSheet("color: white; font-weight: normal;")
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