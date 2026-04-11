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
                               QSplitter, QFileDialog, QMessageBox, QDialog,
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

def get_accent_color(color_name):
    if color_name == "System": return get_system_accent_color()
    return THEME_COLORS.get(color_name, THEME_COLORS["Blue"])[0]

def pil_to_qpixmap(pil_image):
    if pil_image is None: return QPixmap()
    img = pil_image.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg)

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
        self.player_timer.start(100)
        
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
            'custom_args': self.custom_args
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

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Upper Splitter
        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter, 1)
        
        self._setup_local_pane()
        self._setup_results_pane()
        self._setup_queue_pane()
        self.splitter.setSizes([300, 800, 300])

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
        search_r.addWidget(self.search_entry, 1)
        search_r.addWidget(self.search_btn)
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
        set_r.addWidget(self.path_combo)
        
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self.browse_folder)
        set_r.addWidget(self.browse_btn)
        
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
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 150); self.vol_slider.setValue(self.volume_val)
        self.vol_slider.setFixedWidth(100)
        self.vol_slider.valueChanged.connect(self.on_volume_changed)
        c.addWidget(self.vol_slider)
        
        c.addStretch(1)
        self.prev_btn = QPushButton("\uE892")
        self.prev_btn.clicked.connect(self.play_previous)
        self.prev_btn.setStyleSheet("background: transparent; color: white; font-family: 'Segoe MDL2 Assets'; font-size: 14px;")
        c.addWidget(self.prev_btn)
        
        self.play_btn = QPushButton("\uE768")
        self.play_btn.clicked.connect(self.toggle_playback)
        self.play_btn.setStyleSheet("background: transparent; color: white; font-family: 'Segoe MDL2 Assets'; font-size: 28px;")
        c.addWidget(self.play_btn)
        
        self.next_btn = QPushButton("\uE893")
        self.next_btn.clicked.connect(self.play_next)
        self.next_btn.setStyleSheet("background: transparent; color: white; font-family: 'Segoe MDL2 Assets'; font-size: 14px;")
        c.addWidget(self.next_btn)
        c.addStretch(1)
        
        self.time_label = QLabel("0:00 / 0:00")
        c.addWidget(self.time_label)
        p_layout.addLayout(c)
        
        self.progress_slider = QSlider(Qt.Horizontal)
        self.progress_slider.setRange(0, 100)
        self.progress_slider.valueChanged.connect(self.on_seek)
        p_layout.addWidget(self.progress_slider)

    def _setup_local_pane(self):
        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(0,0,0,0)
        l.addWidget(QLabel("Local Folder"))
        
        h = QHBoxLayout()
        self.local_path_combo = QComboBox()
        self.local_path_combo.addItems(self.local_folders)
        h.addWidget(self.local_path_combo, 1)
        btn = QPushButton("Browse")
        btn.clicked.connect(lambda: self.load_local_folder(QFileDialog.getExistingDirectory(self)))
        h.addWidget(btn)
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
        l.addWidget(QLabel("Search Results"))
        
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
        accent = get_accent_color(self.accent_color_name)
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; }
            QWidget { color: #ffffff; font-family: 'Segoe UI'; font-size: 13px; }
            QLabel { color: #ffffff; }
            QPushButton { 
                background-color: %s; 
                color: white; border: none; padding: 6px 12px; border-radius: 4px; font-weight: bold;
            }
            QPushButton:hover { background-color: #dddddd; color: #1a1a1a; }
            QPushButton:disabled { background-color: #555555; color: #888888; }
            QLineEdit, QComboBox { 
                background-color: #333333; color: white; border: 1px solid #555; padding: 6px; border-radius: 4px;
            }
            QScrollArea { border: none; background-color: #1a1a1a; border-radius: 6px;}
            QFrame { background-color: #2a2a2a; border-radius: 6px; padding: 5px;}
            QSplitter::handle { background-color: #333333; width: 4px; margin: 0px 4px; }
            QSlider::groove:horizontal { border: 1px solid #444; height: 6px; background: #333; border-radius: 3px; }
            QSlider::handle:horizontal { background: %s; width: 14px; margin-top: -4px; margin-bottom: -4px; border-radius: 7px; }
        """ % (accent, accent))

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
        for item in items:
            btn = QPushButton(f"{'📁' if item['is_dir'] else '🎵'}  {item['name']}")
            btn.setStyleSheet("text-align: left; background-color: transparent; padding: 4px; font-weight: normal; border-radius: 0px;")
            btn.clicked.connect(lambda checked=False, i=item: self._on_local_click(i))
            self.local_vbox.addWidget(btn)

    def _on_local_click(self, item):
        if item['is_dir']: 
            self.load_local_folder(item['path'])
        else:
            self._update_status(f"Playing Local: {item['name']}", False, "#3B8ED0")
            url = item['path'].replace("\\", "/")
            if not url.startswith("file:///"): url = "file:///" + url
            media = self.vlc_instance.media_new(url)
            self.vlc_player.set_media(media)
            self.vlc_player.play()
            self.current_video_id = "local"
            self.playback_started_signal.emit(item['name'], "local")

    # --- Search & Download ---
    def perform_search(self):
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
                self.search_results_signal.emit(res, False)
            except Exception:
                self.search_failed_signal.emit()
                
        threading.Thread(target=bg_search, daemon=True).start()

    def _on_search_results(self, res, is_playlist):
        self.search_btn.setEnabled(True)
        self.search_results = res
        while self.results_vbox.count():
            item = self.results_vbox.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        for video in res[:30]:
            w = QWidget()
            l = QHBoxLayout(w)
            l.setContentsMargins(2,2,2,2)
            
            pbtn = QPushButton("▶")
            pbtn.setFixedWidth(40)
            pbtn.clicked.connect(lambda checked=False, v=video: self.play_result(v))
            l.addWidget(pbtn)
            
            title = video.get('title', 'Unknown')
            if len(title) > 60: title = title[:57] + "..."
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
            
            st = "✅ " if q['status'] == "Finished" else ("⬇️ " if q['status'] == "Downloading" else "⏳ ")
            t = q['video'].get('title', 'Unknown')
            if len(t) > 40: t = t[:37] + "..."
            
            l.addWidget(QLabel(f"{st}{t}"), 1)
            
            rm_btn = QPushButton("❌")
            rm_btn.setFixedWidth(30)
            rm_btn.clicked.connect(lambda checked=False, i=idx: self.remove_from_queue(i))
            l.addWidget(rm_btn)
            
            w.setStyleSheet("QWidget { background-color: #333333; border-radius: 4px; margin-bottom: 2px;}" if q['status'] != "Finished" else "QWidget { background-color: #1a1a1a; border-radius: 4px; margin-bottom: 2px;}")
            self.queue_vbox.addWidget(w)

    def remove_from_queue(self, idx):
        if idx < len(self.queue_items):
            self.queue_items.pop(idx)
            self.queue_update_signal.emit()

    def clear_completed(self):
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
        if self.playback_index > 0:
            self.playback_index -= 1
            self.play_result(self.search_results[self.playback_index])
            
    def play_next(self):
        if self.playback_index + 1 < len(self.search_results):
            self.playback_index += 1
            self.play_result(self.search_results[self.playback_index])

    def on_seek(self, val):
        # Ignore programmatic updates triggering seek
        if not self.progress_slider.isSliderDown(): return
        if self.vlc_player:
            self.vlc_player.set_position(float(val)/100.0)

    def on_volume_changed(self, val):
        self.volume_val = val
        if self.vlc_player:
            self.vlc_player.audio_set_volume(val)
        self.save_config()

    def update_player_ui(self):
        if not self.vlc_player or not self.current_video_id: return
        
        # Check ended
        if self.vlc_player.get_state() == vlc.State.Ended:
            if not getattr(self, '_ended_trigger', False):
                self._ended_trigger = True
                self.play_next()
        else:
            self._ended_trigger = False
            
        pos = self.vlc_player.get_position() * 100
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
        pass # Optimization skip for this phase

if __name__ == "__main__":
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    app = QApplication(sys.argv)
    window = MainApp()
    window.show()
    sys.exit(app.exec())
