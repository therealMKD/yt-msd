#Open Source Software under the Apache License, Version 2.0
#This is the GUI version of yt-msd. It is the full-featured version of the project.
#Again, only partially vibe coded. I swear I know what I'm doing

import os
import sys
import json
import threading
import winreg
import yt_dlp
import webbrowser
import urllib.request
import io
import vlc
import shlex
import time
import customtkinter as ctk
from PIL import Image
from tkinter import filedialog, messagebox

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
    "White": ("#E0E0E0", "#BBBBBB")
}

class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Settings")
        
        # Proper Positioning
        w, h = 600, 480
        curr_x, curr_y = self.parent.winfo_x(), self.parent.winfo_y()
        self.geometry(f"{w}x{h}+{curr_x+50}+{curr_y+50}")
        self.attributes("-topmost", True); self.resizable(False, False)

        self.main_f = ctk.CTkFrame(self, fg_color="transparent")
        self.main_f.pack(fill="both", expand=True, padx=25, pady=25)

        # 1. Appearance Mode
        ctk.CTkLabel(self.main_f, text="APPEARANCE MODE", font=self.parent.header_font).pack(anchor="w", pady=(0, 5))
        self.mode_switch = ctk.CTkSegmentedButton(self.main_f, values=["System", "Light", "Dark"], command=self._change_mode)
        self.mode_switch.pack(fill="x", pady=(0, 20))
        self.mode_switch.set(self.parent.appearance_mode_var.get())

        # 2. Accent Color
        ctk.CTkLabel(self.main_f, text="ACCENT COLOR", font=self.parent.header_font).pack(anchor="w", pady=(0, 5))
        self.color_grid = ctk.CTkFrame(self.main_f, fg_color="transparent")
        self.color_grid.pack(fill="x", pady=(0, 20))
        
        colors_to_show = ["System"] + list(THEME_COLORS.keys())
        self.color_buttons = {}
        for i, color in enumerate(colors_to_show):
            r = i // 5; c = i % 5
            c_val = self.parent._get_system_accent_color() if color == "System" else THEME_COLORS[color][0]
            btn = ctk.CTkButton(self.color_grid, text="\uE771" if color == "System" else "", font=(self.parent.icon_font, 12), width=35, height=35, fg_color=c_val, hover_color=c_val, corner_radius=6, border_color=("#333333", "#ffffff"), command=lambda clr=color: self._change_accent(clr))
            btn.grid(row=r, column=c, padx=4, pady=4); self.color_buttons[color] = btn
        self._update_color_selection_visuals()

        # 3. Custom YT-DLP Arguments (Advanced)
        ctk.CTkLabel(self.main_f, text="CUSTOM YT-DLP ARGUMENTS (ADVANCED)", font=self.parent.header_font).pack(anchor="w", pady=(0, 5))
        self.arg_row = ctk.CTkFrame(self.main_f, fg_color="transparent")
        self.arg_row.pack(fill="x", pady=(0, 5))
        
        self.use_args_cb = ctk.CTkCheckBox(self.arg_row, text="", width=24, variable=self.parent.use_custom_args_var, command=self.parent._save_config)
        self.use_args_cb.pack(side="left", padx=(0, 8))
        
        self.arg_entry = ctk.CTkEntry(self.arg_row, placeholder_text="Arguments...", font=("Consolas", 11), height=32)
        self.arg_entry.pack(side="left", fill="x", expand=True)
        
        # Populate and bind
        cur_args = self.parent.custom_args_var.get()
        if not cur_args: cur_args = self.parent._get_current_args_string()
        self.arg_entry.insert(0, cur_args)
        self.arg_entry.bind("<KeyRelease>", lambda e: self.parent.custom_args_var.set(self.arg_entry.get()))
        self.arg_entry.bind("<FocusOut>", lambda e: self.parent._save_config())

        ctk.CTkLabel(self.main_f, text="\uE946 Manual override ignores GUI bitrate/format settings.", font=("Segoe UI", 10), text_color="gray").pack(anchor="w", padx=32)

        # 4. Reset Defaults
        self.reset_btn = ctk.CTkButton(self.main_f, text="Reset to Default Config", font=self.parent.main_font, height=32, fg_color="transparent", border_width=1, border_color=("#888888", "#444444"), text_color=("#555555", "#aaaaaa"), hover_color=("#dddddd", "#3d3d3d"), command=self._reset_defaults)
        self.reset_btn.pack(fill="x", side="bottom", pady=(10, 0))

        # 5. Footer - Right Aligned Close
        footer = ctk.CTkFrame(self.main_f, fg_color="transparent")
        footer.pack(fill="x", side="bottom", pady=(10, 0))
        self.close_btn = ctk.CTkButton(footer, text="Close", font=self.parent.main_font, width=100, height=32, fg_color=("#888888", "#444444"), hover_color=("#666666", "#555555"), command=self.destroy)
        self.close_btn.pack(side="right")

    def _reset_defaults(self):
        if messagebox.askyesno("Confirm Reset", "This will wipe your custom arguments, theme choices, and folder history. Continue?", parent=self):
            if os.path.exists(self.parent.config_path):
                os.remove(self.parent.config_path)
            # Re-init fresh
            self.parent.format_var.set("mp3")
            self.parent.bitrate_var.set("192")
            self.parent.appearance_mode_var.set("System")
            self.parent.accent_color_var.set("Blue")
            self.parent.use_custom_args_var.set(False)
            self.parent.custom_args_var.set(self.parent._get_current_args_string())
            self.parent.divider_percent.set(0.6)
            self.parent.recent_folders = [os.path.join(os.path.expanduser("~"), "Downloads")]
            self.parent.download_path_var.set(self.parent.recent_folders[0])
            
            # Apply
            ctk.set_appearance_mode("System")
            self.parent._apply_accent_color("Blue")
            self.parent._update_column_weights()
            self._update_color_selection_visuals()
            self.destroy()
            messagebox.showinfo("Reset", "Settings have been restored to defaults.", parent=self.parent)

    def _update_color_selection_visuals(self):
        current_color = self.parent.accent_color_var.get()
        for color, btn in self.color_buttons.items():
            btn.configure(border_width=2 if color == current_color else 0)

    def _change_mode(self, mode):
        self.parent.appearance_mode_var.set(mode); ctk.set_appearance_mode(mode); self.parent._save_config()

    def _change_accent(self, color):
        self.parent.accent_color_var.set(color); self.parent._apply_accent_color(color); self._update_color_selection_visuals(); self.parent._save_config()

class YtMsdGui(ctk.CTk):
    def __init__(self):
        super().__init__()
        width, height = 1400, 850
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{width}x{height}+{(screen_w-width)//2}+{(screen_h-height)//2}")
        self.title("yt-msd | YouTube Media Downloader")
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(0, weight=1)

        # Fonts & Misc
        self.icon_font = "Segoe MDL2 Assets"; self.main_font = ("Segoe UI", 12); self.header_font = ("Segoe UI Semibold", 15)
        self.config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui_config.json")
        self.current_accent_color = "#3B8ED0"

        # State variables
        self.search_results = []; self.queue_items = []
        self.download_path_var = ctk.StringVar(); self.format_var = ctk.StringVar(value="mp3"); self.bitrate_var = ctk.StringVar(value="192")
        self.result_count_var = ctk.StringVar(value="10"); self.appearance_mode_var = ctk.StringVar(value="System")
        self.accent_color_var = ctk.StringVar(value="Blue"); self.divider_percent = ctk.DoubleVar(value=0.6); self.recent_folders = []
        
        # Advanced Args vars
        self.show_thumbnails_var = ctk.BooleanVar(value=False)
        self.use_custom_args_var = ctk.BooleanVar(value=False)
        self.custom_args_var = ctk.StringVar(value="")
        self.volume_var = ctk.IntVar(value=100)
        self.thumbnail_cache = {}
        self.thumbnail_cache_size = 0

        # VLC Engine
        try:
            self.vlc_instance = vlc.Instance('--quiet', '--no-video')
            self.vlc_player = self.vlc_instance.media_player_new()
        except:
            self.vlc_instance = None; self.vlc_player = None

        self.is_playing = False
        self.current_video_id = None
        self.config_corrupted = False

        self._load_config()
        if self.vlc_player: self.vlc_player.audio_set_volume(self.volume_var.get())
        self.is_searching = False; self.is_downloading = False; self.divider_dragging = False
        self.current_playing_title = ""; self.current_status_text = "Ready"
        self._last_divider_update = 0; self._vol_save_id = None; self._last_v_applied = -1
        self._current_hover_btn = None; self._hover_hide_id = None
        self._is_muted = False
        self.drag_data = {"item": None, "original_index": -1, "proxy": None}
        self.config_corrupted = getattr(self, "config_corrupted", False) # Carry over from loader

        self._create_widgets()
        ctk.set_appearance_mode(self.appearance_mode_var.get()); self._apply_accent_color(self.accent_color_var.get())
        
        self.result_count_var.trace_add("write", lambda *args: self._on_count_changed())
        self.show_thumbnails_var.trace_add("write", lambda *args: self._on_count_changed())
        self.bind("<Map>", lambda e: self._on_window_restore())
        
        if self.config_corrupted:
            self.status_label.configure(text="Config file corrupted. Settings reset to defaults.", text_color="#e31e24")

    def _create_widgets(self):
        box_bg, ctrl_bg = ("#f0f0f0", "#1e1e1e"), ("#e0e0e0", "#333333")
        self.layout_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.layout_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=(15, 10))
        self.layout_frame.grid_rowconfigure(0, weight=1); self._update_column_weights()

        # 1. Results
        self.results_col = ctk.CTkFrame(self.layout_frame, fg_color="transparent")
        self.results_col.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.results_col.grid_columnconfigure(0, weight=1); self.results_col.grid_rowconfigure(1, weight=1)
        res_header = ctk.CTkFrame(self.results_col, fg_color="transparent"); res_header.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.res_label = ctk.CTkLabel(res_header, text="Search Results", font=self.header_font); self.res_label.grid(row=0, column=0, sticky="w")
        
        header_controls = ctk.CTkFrame(res_header, fg_color="transparent")
        header_controls.grid(row=0, column=1, sticky="e")
        res_header.grid_columnconfigure(0, weight=1) # Push controls to the right
        
        self.show_thumb_cb = ctk.CTkCheckBox(header_controls, text="Show Thumbnails", font=("Segoe UI", 11), variable=self.show_thumbnails_var, command=self._save_config)
        self.show_thumb_cb.grid(row=0, column=0, padx=(0, 15))
        
        ctk.CTkLabel(header_controls, text="Show:", font=self.main_font).grid(row=0, column=1, padx=5)
        self.count_menu = ctk.CTkComboBox(header_controls, values=["10", "20", "50", "100"], variable=self.result_count_var, width=70, height=28, state="readonly")
        self.count_menu.grid(row=0, column=2)
        self.results_frame = ctk.CTkScrollableFrame(self.results_col, fg_color=box_bg, corner_radius=10); self.results_frame.grid(row=1, column=0, sticky="nsew")

        # 2. Resizer Handle
        self.handle = ctk.CTkFrame(self.layout_frame, width=4, fg_color=ctrl_bg, cursor="sb_h_double_arrow")
        self.handle.grid(row=0, column=1, sticky="ns", padx=2)
        self.handle.bind("<Button-1>", lambda e: setattr(self, "divider_dragging", True))
        self.handle.bind("<B1-Motion>", self._on_divider_drag); self.handle.bind("<ButtonRelease-1>", self._stop_divider_drag)

        # 3. Queue
        self.queue_col = ctk.CTkFrame(self.layout_frame, fg_color="transparent")
        self.queue_col.grid(row=0, column=2, sticky="nsew", padx=(5, 0))
        self.queue_col.grid_columnconfigure(0, weight=1); self.queue_col.grid_rowconfigure(1, weight=1)
        q_header = ctk.CTkFrame(self.queue_col, fg_color="transparent"); q_header.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.queue_label = ctk.CTkLabel(q_header, text="Download Queue (0)", font=self.header_font); self.queue_label.pack(side="left")
        self.clear_comp_btn = ctk.CTkButton(q_header, text="Clear Completed", font=self.main_font, height=26, width=120, fg_color=ctrl_bg, hover_color=("#dddddd", "#444444"), text_color=("#1a1a1a", "#ffffff"), command=self._clear_completed); self.clear_comp_btn.pack(side="right")
        self.queue_frame = ctk.CTkScrollableFrame(self.queue_col, fg_color=box_bg, corner_radius=10); self.queue_frame.grid(row=1, column=0, sticky="nsew")

        # 4. Controls
        self.control_panel = ctk.CTkFrame(self, height=180, corner_radius=0, fg_color=ctrl_bg); self.control_panel.grid(row=1, column=0, sticky="ew")
        self.control_panel.grid_columnconfigure(0, weight=1)
        search_f = ctk.CTkFrame(self.control_panel, fg_color="transparent"); search_f.grid(row=0, column=0, sticky="ew", padx=20, pady=(15, 10))
        search_f.grid_columnconfigure(0, weight=1)
        self.search_entry = ctk.CTkEntry(search_f, placeholder_text="Search YouTube...", height=40, font=self.main_font, corner_radius=8); self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.search_entry.bind("<Return>", lambda e: self._start_search())
        self.search_button = ctk.CTkButton(search_f, text="\uE721", font=(self.icon_font, 16), width=50, height=40, command=self._start_search, corner_radius=8); self.search_button.grid(row=0, column=1)

        sets_f = ctk.CTkFrame(self.control_panel, fg_color="transparent"); sets_f.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10)); sets_f.grid_columnconfigure(5, weight=1)
        ctk.CTkLabel(sets_f, text="Format:", font=self.main_font).grid(row=0, column=0, padx=(0, 5))
        self.format_var.trace_add("write", lambda *a: self._update_arg_defaults()) # Sync args
        self.format_menu = ctk.CTkOptionMenu(sets_f, values=["mp3", "m4a", "flac", "wav", "aac", "opus", "ogg", "vorbis", "mka"], variable=self.format_var, width=80, height=28, command=lambda _: self._save_config()); self.format_menu.grid(row=0, column=1, padx=(0, 10))
        ctk.CTkLabel(sets_f, text="Bitrate:", font=self.main_font).grid(row=0, column=2, padx=(0, 5))
        self.bitrate_var.trace_add("write", lambda *a: self._update_arg_defaults()) # Sync args
        self.bitrate_menu = ctk.CTkComboBox(sets_f, values=["128", "192", "256", "320"], variable=self.bitrate_var, width=90, height=28, command=lambda _: self._save_config()); self.bitrate_menu.grid(row=0, column=3, padx=(0, 10))
        ctk.CTkLabel(sets_f, text="Save to:", font=self.main_font).grid(row=0, column=4, padx=(10, 5))
        self.path_menu = ctk.CTkComboBox(sets_f, values=self.recent_folders, variable=self.download_path_var, font=self.main_font, height=28, command=lambda _: self._save_config()); self.path_menu.grid(row=0, column=5, sticky="ew", padx=(0, 5))
        self.browse_button = ctk.CTkButton(sets_f, text="\uED25", font=(self.icon_font, 14), width=35, height=28, command=self._browse_folder); self.browse_button.grid(row=0, column=6, padx=(0, 10))
        self.download_button = ctk.CTkButton(sets_f, text="Download All", font=("Segoe UI Semibold", 13), height=35, width=140, command=self._start_batch_download); self.download_button.grid(row=0, column=7)

        status_r = ctk.CTkFrame(self.control_panel, fg_color="transparent"); status_r.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10)); status_r.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(status_r, text="Ready", font=("Segoe UI", 11), text_color="gray"); self.status_label.grid(row=0, column=0, sticky="w")
        self.settings_btn = ctk.CTkButton(status_r, text="\uE713", font=(self.icon_font, 16), width=40, height=30, fg_color="transparent", hover_color=("#dddddd", "#444444"), text_color=("#333333", "#ffffff"), command=lambda: SettingsWindow(self)); self.settings_btn.grid(row=0, column=1, sticky="e")

        # 5. Bottom Player Bar
        self.player_frame = ctk.CTkFrame(self, height=80, corner_radius=0, fg_color=ctrl_bg)
        self.player_frame.grid(row=2, column=0, sticky="ew")
        self.player_frame.grid_columnconfigure(1, weight=1)

        # 1. Controls Top
        vol_f = ctk.CTkFrame(self.player_frame, fg_color="transparent")
        vol_f.grid(row=0, column=0, sticky="w", padx=20, pady=(5, 0))
        self.vol_icon_label = ctk.CTkLabel(vol_f, text="\uE767", font=(self.icon_font, 14), cursor="hand2")
        self.vol_icon_label.pack(side="left", padx=(0, 5))
        self.vol_icon_label.bind("<Button-1>", lambda e: self._toggle_mute())
        self.vol_slider = ctk.CTkSlider(vol_f, from_=0, to=150, width=100, height=16, command=self._on_volume)
        self.vol_slider.pack(side="left")
        self.vol_slider.set(self.volume_var.get())
        self.vol_readout = ctk.CTkLabel(vol_f, text=f"{self.volume_var.get()}%", font=("Consolas", 11), width=45)
        self.vol_readout.pack(side="left", padx=(5, 0))
        
        # Bindings for Slider
        self.vol_slider.bind("<Button-1>", lambda e: self.vol_slider.focus_set())
        self.vol_slider.bind("<Key-Left>", self._on_vol_keydown)
        self.vol_slider.bind("<Key-Right>", self._on_vol_keydown)
        self.vol_slider.bind("<Key-Up>", self._on_vol_keydown)
        self.vol_slider.bind("<Key-Down>", self._on_vol_keydown)
        self.vol_slider.bind("<Double-Button-1>", self._reset_vol)

        trans_f = ctk.CTkFrame(self.player_frame, fg_color="transparent")
        trans_f.grid(row=0, column=1, sticky="n", pady=(5, 0))
        self.rew_btn = ctk.CTkButton(trans_f, text="\uE100", font=(self.icon_font, 14), width=35, height=35, fg_color="transparent", text_color=("#333333", "#ffffff"), command=lambda: self._seek_relative(-10))
        self.rew_btn.pack(side="left", padx=10)
        
        # Cleaner Play/Pause (No circle)
        accent = self._get_system_accent_color() if self.accent_color_var.get() == "System" else THEME_COLORS.get(self.accent_color_var.get(), THEME_COLORS["Blue"])[0]
        self.play_pause_btn = ctk.CTkButton(trans_f, text="\uE768", font=(self.icon_font, 28), width=50, height=50, fg_color="transparent", text_color=accent, hover_color=("#dddddd", "#3d3d3d"), command=self._toggle_playback)
        self.play_pause_btn.pack(side="left", padx=10)
        
        self.ff_btn = ctk.CTkButton(trans_f, text="\uE101", font=(self.icon_font, 14), width=35, height=35, fg_color="transparent", text_color=("#333333", "#ffffff"), command=lambda: self._seek_relative(10))
        self.ff_btn.pack(side="left", padx=10)

        r_f = ctk.CTkFrame(self.player_frame, fg_color="transparent")
        r_f.grid(row=0, column=2, sticky="e", padx=20, pady=(5, 0))
        
        self.time_label = ctk.CTkLabel(r_f, text="0:00 / 0:00", font=("Consolas", 11), width=100)
        self.time_label.pack(side="right")

        # 2. Progress Slider Bottom
        self.progress_slider = ctk.CTkSlider(self.player_frame, from_=0, to=100, height=12, command=self._on_seek)
        self.progress_slider.grid(row=1, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 10))
        self.progress_slider.set(0)

    # --- Advanced Args Logic ---
    def _get_current_args_string(self):
        f = self.format_var.get(); b = self.bitrate_var.get()
        return f"--format bestaudio/best --extract-audio --audio-format {f} --audio-quality {b}k"

    def _update_arg_defaults(self):
        # Only update if the user hasn't ticked "Force" yet, to keep it current
        if not self.use_custom_args_var.get():
            self.custom_args_var.set(self._get_current_args_string())

    # --- Theme & System ---
    def _apply_accent_color(self, color_name):
        if color_name == "System": accent = self._get_system_accent_color(); hover = accent
        else: accent, hover = THEME_COLORS.get(color_name, THEME_COLORS["Blue"])
        self.current_accent_color = accent
        t_c = "#000000" if color_name in ["White", "Yellow", "Grey"] else "#ffffff"
        wb = [self.search_button, self.download_button, self.format_menu, self.count_menu, self.browse_button, self.bitrate_menu, self.path_menu]
        for w in wb:
            if isinstance(w, ctk.CTkButton): w.configure(fg_color=accent, hover_color=hover, text_color=t_c)
            elif isinstance(w, ctk.CTkOptionMenu): w.configure(fg_color=accent, button_color=accent, button_hover_color=hover, text_color=t_c)
            elif isinstance(w, ctk.CTkComboBox): w.configure(button_color=accent, button_hover_color=hover, border_color=accent, text_color=("#1a1a1a", "#ffffff"))
        if hasattr(self, 'vol_slider'):
            is_red = self.volume_var.get() > 100
            self.vol_slider.configure(progress_color="#e31e24" if is_red else accent)
        
        # Update existing play buttons instantly
        if hasattr(self, 'play_pause_btn'): self.play_pause_btn.configure(text_color=accent)
        if hasattr(self, 'results_frame'):
            for item in self.results_frame.winfo_children():
                for c in item.winfo_children():
                    if isinstance(c, ctk.CTkFrame): # Search result thumb container
                        for sub in c.winfo_children():
                            if isinstance(sub, ctk.CTkButton) and sub.cget("text") == "\uE768":
                                sub.configure(text_color=accent)
                    if isinstance(c, ctk.CTkButton) and c.cget("text") == "\uE768":
                        c.configure(text_color=accent)
                    if isinstance(c, ctk.CTkCheckBox): c.configure(border_color=accent, checkmark_color=accent)
        if hasattr(self, 'vol_slider') and self.volume_var.get() <= 100:
            self.vol_slider.configure(progress_color=accent)

    def _get_system_accent_color(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM")
            val, _ = winreg.QueryValueEx(key, "AccentColor"); winreg.CloseKey(key)
            b = (val >> 16) & 0xFF; g = (val >> 8) & 0xFF; r = val & 0xFF
            return f"#{r:02x}{g:02x}{b:02x}"
        except: return "#0067c0"

    # --- Resizer & Logic Reused ---
    def _update_column_weights(self):
        w = self.divider_percent.get(); self.layout_frame.grid_columnconfigure(0, weight=int(w * 100)); self.layout_frame.grid_columnconfigure(2, weight=int((1-w)*100))
        self.update_idletasks()

    def _on_divider_drag(self, e):
        if not self.divider_dragging: return
        # Throttle layout updates to ~60fps (16ms)
        now = time.time()
        if now - self._last_divider_update < 0.016: return
        self._last_divider_update = now
        
        tot = self.layout_frame.winfo_width()
        if tot: self.divider_percent.set(max(0.2, min(0.8, (e.x_root - self.layout_frame.winfo_rootx())/tot))); self._update_column_weights()
    def _stop_divider_drag(self, e): self.divider_dragging = False; self._save_config()

    def _load_config(self):
        default_dl = os.path.join(os.path.expanduser("~"), "Downloads")
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    c = json.load(f)
                    self.format_var.set(c.get('format', 'mp3'))
                    self.bitrate_var.set(c.get('bitrate', '192'))
                    self.appearance_mode_var.set(c.get('mode', 'System'))
                    self.accent_color_var.set(c.get('accent', 'System'))
                    self.divider_percent.set(max(0.2, min(0.8, c.get('divider', 0.6))))
                    self.recent_folders = c.get('folders', [default_dl])
                    if not isinstance(self.recent_folders, list) or not self.recent_folders:
                        self.recent_folders = [default_dl]
                    self.show_thumbnails_var.set(c.get('show_thumbnails', False))
                    self.use_custom_args_var.set(c.get('use_custom_args', False))
                    self.custom_args_var.set(c.get('custom_args', ""))
                    self.volume_var.set(c.get('volume', 100))
                    self.download_path_var.set(self.recent_folders[0])
                    return
            except Exception:
                self.config_corrupted = True
                pass
        
        # Fallback for fresh/broken config
        self.recent_folders = [default_dl]
        self.download_path_var.set(default_dl)

    def _save_config(self):
        cur = self.download_path_var.get()
        if cur and cur not in self.recent_folders: self.recent_folders.insert(0, cur); self.recent_folders = self.recent_folders[:5]
        c = {'format': self.format_var.get(), 'bitrate': self.bitrate_var.get(), 'mode': self.appearance_mode_var.get(), 'accent': self.accent_color_var.get(), 
             'divider': self.divider_percent.get(), 'folders': self.recent_folders, 'use_custom_args': self.use_custom_args_var.get(), 'custom_args': self.custom_args_var.get(),
             'show_thumbnails': self.show_thumbnails_var.get(), 'volume': self.volume_var.get()}
        try:
            with open(self.config_path, 'w') as f: json.dump(c, f, indent=4)
            if hasattr(self, 'path_menu'): self.path_menu.configure(values=self.recent_folders)
        except: pass

    def _update_status(self, text=None, is_playing=False, color=None):
        if is_playing: self.current_playing_title = text if text else ""
        elif text: self.current_status_text = text
        
        full_text = self.current_status_text
        if self.current_playing_title: full_text += f" - Playing: {self.current_playing_title}"
            
        if hasattr(self, 'status_label'):
            self.status_label.configure(text=full_text)
            if color: self.status_label.configure(text_color=color)

    def _handle_error(self, msg):
        self._update_status(msg, color="#e31e24")

    def _browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.download_path_var.get())
        if folder: self.download_path_var.set(folder); self._save_config()

    def _on_count_changed(self):
        if self.search_results and not self.is_searching: self._update_results(self.search_results)

    def _start_search(self):
        if self.is_searching: return
        query = self.search_entry.get().strip()
        if not query: return
        self.is_searching = True
        self.res_label.configure(text=f"Search Results - [{query}]")
        self.search_entry.delete(0, 'end')
        self._update_status("Searching YouTube...", color="#0067c0")
        self.search_button.configure(state="disabled")
        for w in self.results_frame.winfo_children(): w.destroy()
        try: count = int(self.result_count_var.get())
        except: count = 10
        threading.Thread(target=self._perform_staged_search, args=(query, count), daemon=True).start()

    def _perform_staged_search(self, q, count):
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                info = ydl.extract_info(f"ytsearch{count}:{q}", download=False)
                res = [e for e in info['entries'] if e.get('id')]
            self.after(0, lambda: self._update_results(res))
            threading.Thread(target=self._background_fetch_full, args=(q, len(res)), daemon=True).start()
        except Exception as e:
            import traceback; traceback.print_exc()
            self.after(0, lambda: self._handle_error("Search failed"))

    def _background_fetch_full(self, q, f):
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl: info = ydl.extract_info(f"ytsearch110:{q}", download=False)
            self.search_results = [e for e in info['entries'] if e.get('id')]
            self.after(0, lambda: self._update_status(f"Loaded {len(self.search_results)} results", color="gray"))
        except: pass

    def _update_results(self, res):
        self.search_results = res; self.is_searching = False; self.search_button.configure(state="normal")
        for w in self.results_frame.winfo_children(): w.destroy()
        for v in res[:int(self.result_count_var.get())]: self._create_result_item(v)

    def _create_result_item(self, v):
        is_thumb = self.show_thumbnails_var.get()
        f = ctk.CTkFrame(self.results_frame, fg_color="transparent")
        f.pack(fill="x", padx=5, pady=6 if is_thumb else 1)
        accent = self.current_accent_color

        # 1. Play Button & Thumb (Left side)
        if is_thumb:
            c = ctk.CTkFrame(f, fg_color="transparent")
            c.pack(side="left", padx=(0, 10))
            
            t_l = ctk.CTkLabel(c, text="", width=90, height=50, fg_color=("#dbdbdb", "#2b2b2b"), corner_radius=4)
            t_l.pack()
            threading.Thread(target=self._fetch_thumbnail, args=(v, t_l), daemon=True).start()
            
            p_b = ctk.CTkButton(c, text="\uE768", font=(self.icon_font, 22), width=90, height=50, fg_color="transparent", hover_color=("#00000033", "#ffffff22"), text_color=accent, corner_radius=0, command=lambda video=v: self._on_play_click(video))
            p_b.place(relx=0.5, rely=0.5, anchor="center")
            p_b.place_forget()
            
            def _on_e(e, b=p_b):
                if self._hover_hide_id: self.after_cancel(self._hover_hide_id); self._hover_hide_id = None
                if self._current_hover_btn and self._current_hover_btn != b:
                    try: self._current_hover_btn.place_forget()
                    except: pass
                b.place(relx=0.5, rely=0.5, anchor="center")
                self._current_hover_btn = b
                
            def _on_l(e, b=p_b):
                if self._hover_hide_id: self.after_cancel(self._hover_hide_id)
                self._hover_hide_id = self.after(100, lambda: self._do_hide(b))
                    
            c.bind("<Enter>", _on_e); c.bind("<Leave>", _on_l)
            t_l.bind("<Enter>", _on_e); t_l.bind("<Leave>", _on_l)
            p_b.bind("<Enter>", _on_e); p_b.bind("<Leave>", _on_l)
        else:
            p_b = ctk.CTkButton(f, text="\uE768", font=(self.icon_font, 16), width=30, height=30, fg_color="transparent", hover_color=("#dddddd", "#3d3d3d"), text_color=accent, command=lambda video=v: self._on_play_click(video))
            p_b.pack(side="left", padx=(0, 10))

        # 2. Results Info
        title = v.get('title', 'Unknown')
        if len(title) > 55: title = title[:52] + "..."
        uploader = v.get('uploader', 'Unknown')
        if len(uploader) > 35: uploader = uploader[:32] + "..."
        cb = ctk.CTkCheckBox(f, text=f"{title}\n{uploader}" if is_thumb else f"{title} | {uploader}", font=self.main_font if not is_thumb else ("Segoe UI", 11), width=0, checkbox_width=18, checkbox_height=18, border_color=accent, checkmark_color=accent, command=lambda video=v: self._toggle_queue(video))
        cb.pack(side="left", fill="x", expand=True)
        if any(q['video']['id'] == v['id'] for q in self.queue_items): cb.select()
        v['checkbox'] = cb

        # 3. External Link Button
        link_btn = ctk.CTkButton(f, text="\uE8A7", font=(self.icon_font, 14), width=30, height=30, fg_color="transparent", hover_color=("#dddddd", "#3d3d3d"), text_color=("#333333", "#ffffff"), command=lambda: webbrowser.open(f"https://youtube.com/watch?v={v['id']}"))
        link_btn.pack(side="right", padx=2)

    def _do_hide(self, b):
        try:
            b.place_forget()
            if self._current_hover_btn == b: self._current_hover_btn = None
        except: pass
        self._hover_hide_id = None

    def _fetch_thumbnail(self, v, label):
        vid_id = v.get('id')
        if not vid_id: return
        if vid_id in self.thumbnail_cache:
            self.after(0, lambda: label.configure(image=self.thumbnail_cache[vid_id]))
            return

        try:
            url = f"https://i.ytimg.com/vi/{vid_id}/mqdefault.jpg"
            with urllib.request.urlopen(url) as req:
                data = req.read()
                if self.thumbnail_cache_size + len(data) > 256 * 1024 * 1024:
                    self.thumbnail_cache.clear(); self.thumbnail_cache_size = 0 # Simple flush
                
                img = Image.open(io.BytesIO(data))
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(90, 50))
                self.thumbnail_cache[vid_id] = ctk_img
                self.thumbnail_cache_size += len(data)
                self.after(0, lambda: label.configure(image=ctk_img))
        except: pass

    def _on_play_click(self, v):
        self._update_status(f"Fetching stream: {v['title'][:30]}...", color="#0067c0")
        threading.Thread(target=self._fetch_and_play, args=(v,), daemon=True).start()

    def _fetch_and_play(self, v):
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'format': 'bestaudio/best'}) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={v['id']}", download=False)
                url = info['url']
                self.after(0, lambda: self._play_media(url, v))
                self.after(0, lambda: self._update_status(v['title'][:50], is_playing=True, color="gray"))
        except Exception:
            self.after(0, lambda: self._update_status("Stream failed", color="#e31e24"))

    def _toggle_queue(self, v):
        if v['checkbox'].get():
            if not any(q['video']['id'] == v['id'] for q in self.queue_items): self.queue_items.append({'video': v, 'status': 'Pending'})
        else: self.queue_items = [q for q in self.queue_items if q['video']['id'] != v['id']]
        self._refresh_queue_display()

    def _refresh_queue_display(self):
        for w in self.queue_frame.winfo_children(): w.destroy()
        self.queue_label.configure(text=f"Download Queue ({len(self.queue_items)})")
        for i, q in enumerate(self.queue_items): self._create_queue_widget(q, i)

    def _create_queue_widget(self, q, idx):
        f = ctk.CTkFrame(self.queue_frame, fg_color=("#e0e0e0", "#2a2a2a" if q['status'] != "Finished" else "#1a1a1a"), corner_radius=5, height=40)
        f.pack(fill="x", padx=5, pady=2)
        st = "\uE73E " if q['status'] == "Finished" else ("\uE896 " if q['status'] == "Downloading" else "")
        t = q['video'].get('title', 'Unknown')
        if len(t) > 150: t = t[:147] + "..."
        ctk.CTkButton(f, text="\uE711", font=(self.icon_font,12), width=30, height=30, fg_color="transparent", hover_color=("#aaaaaa", "#444444"), command=lambda i=idx: self._remove_from_queue(i)).pack(side="right", padx=5)
        lbl = ctk.CTkLabel(f, text=f"{st}{t}", font=self.main_font, text_color=("#2a2a2a", "white"), anchor="w", cursor="fleur")
        lbl.pack(side="left", fill="x", expand=True, padx=10)
        for w in [f, lbl]:
            w.bind("<Button-1>", lambda e, i=idx, it=q: self._on_drag_start(e, i, it), add="+")
            w.bind("<B1-Motion>", self._on_drag_motion, add="+")
            w.bind("<ButtonRelease-1>", self._on_drag_stop, add="+")

    def _remove_from_queue(self, idx):
        v = self.queue_items.pop(idx)['video']
        for res in self.search_results:
            if res['id'] == v['id'] and 'checkbox' in res: res['checkbox'].deselect()
        self._refresh_queue_display()

    def _clear_completed(self): self.queue_items = [q for q in self.queue_items if q['status'] != "Finished"]; self._refresh_queue_display()

    def _on_drag_start(self, e, idx, q):
        self.drag_data = {"original_index": idx, "item": q, "proxy": ctk.CTkFrame(self, fg_color=("#ffffff", "#3a3a3a"), border_width=2, border_color="#0067c0", corner_radius=5, width=400, height=40)}
        ctk.CTkLabel(self.drag_data["proxy"], text=f"\uE76F {q['video']['title'][:50]}...", font=self.main_font).pack(padx=20, pady=8)
        self.drag_data["proxy"].place(x=e.x_root - self.winfo_rootx() - 200, y=e.y_root - self.winfo_rooty() - 20)
    def _on_drag_motion(self, e):
        if self.drag_data["proxy"]: self.drag_data["proxy"].place(x=e.x_root - self.winfo_rootx() - 200, y=e.y_root - self.winfo_rooty() - 20)
    def _on_drag_stop(self, e):
        if self.drag_data["proxy"]: self.drag_data["proxy"].destroy()
        if self.drag_data["item"]:
            y = e.y_root - self.queue_frame.winfo_rooty(); ni = max(0, min(len(self.queue_items)-1, int(y/44)))
            if ni != self.drag_data["original_index"]: it = self.queue_items.pop(self.drag_data["original_index"]); self.queue_items.insert(ni, it); self._refresh_queue_display()
        self.drag_data = {"item": None, "original_index": -1, "proxy": None}

    def _start_batch_download(self):
        if self.is_downloading: return
        self._save_config(); pending = [q for q in self.queue_items if q['status'] == "Pending"]
        if not pending: return messagebox.showinfo("Queue Empty", "No pending downloads.")
        self.is_downloading = True; self.download_button.configure(state="disabled", text="Downloading...")
        threading.Thread(target=self._process_queue, daemon=True).start()

    def _process_queue(self):
        folder = self.download_path_var.get()
        for q in self.queue_items:
            if q['status'] == "Pending":
                q['status'] = "Downloading"; self.after(0, self._refresh_queue_display)
                self._perform_single_download(f"https://www.youtube.com/watch?v={q['video']['id']}", q, folder)
                q['status'] = "Finished"; self.after(0, self._refresh_queue_display)
        self.is_downloading = False; self.after(0, lambda: self.download_button.configure(state="normal", text="Download All"))
        self.after(0, lambda: self._update_status(f"Batch Complete! Saved to: {folder}", color="#28a745"))

    def _perform_single_download(self, url, q, folder):
        try:
            if self.use_custom_args_var.get():
                # Parse custom string into a dict using yt-dlp's internal parser
                custom_str = self.custom_args_var.get()
                parser, _ = yt_dlp.parse_options(shlex.split(custom_str))
                ydl_opts = parser.params
            else:
                ydl_opts = {'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': self.format_var.get(), 'preferredquality': self.bitrate_var.get()}], 'quiet': True}
            
            # Inject mandatory app settings
            ydl_opts.update({'outtmpl': f"{folder}/%(title)s.%(ext)s"})
            if getattr(sys, 'frozen', False): ydl_opts['ffmpeg_location'] = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                
        except Exception as e:
            msg = f"Download failed: {q['video']['title'][:50]}..."
            if self.use_custom_args_var.get():
                msg += "\n\nCheck for errors in your custom arguments."
            self.after(0, lambda: self._update_status(msg, color="#e31e24"))

    def _play_media(self, url, v):
        self.current_video_id = v['id']
        media = self.vlc_instance.media_new(url)
        self.vlc_player.set_media(media)
        self.vlc_player.play()
        self.is_playing = True
        self.play_pause_btn.configure(text="\uE769" if self.is_playing else "\uE768")
        self._update_player_ui()

    def _on_window_restore(self):
        if self.is_playing:
            self._update_player_ui()

    def _toggle_playback(self):
        if not self.current_video_id: return
        if self.is_playing:
            self.vlc_player.pause()
            self.play_pause_btn.configure(text="\uE768")
        else:
            self.vlc_player.play()
            self.play_pause_btn.configure(text="\uE769")
        self.is_playing = not self.is_playing

    def _on_volume(self, val):
        if self._is_muted: self._toggle_mute() # Auto-unmute on volume change
        v = int(float(val))
        if self._last_v_applied == v: return # EXIT FAST: NO CHANGE
        self._last_v_applied = v
        
        # 1. Update Audio engine FIRST for zero perceived latency
        if self.vlc_player: self.vlc_player.audio_set_volume(v)
        
        # 2. Variable set for persistence
        self.volume_var.set(v)
        
        # 3. Optimized UI Updates
        if hasattr(self, 'vol_readout'): self.vol_readout.configure(text=f"{v}%")
        
        is_red = v > 100
        if not hasattr(self, '_vol_is_red') or self._vol_is_red != is_red:
            self._vol_is_red = is_red
            self.vol_slider.configure(progress_color="#e31e24" if is_red else self.current_accent_color)
        
        # 4. Debounce Config Save (Disk I/O is very slow)
        if self._vol_save_id: self.after_cancel(self._vol_save_id)
        self._vol_save_id = self.after(1000, self._save_config)

    def _toggle_mute(self):
        self._is_muted = not self._is_muted
        if self.vlc_player: self.vlc_player.audio_set_mute(self._is_muted)
        
        # UI Feedback
        self.vol_icon_label.configure(text="\uE74F" if self._is_muted else "\uE767")
        accent = self.current_accent_color
        self.vol_slider.configure(progress_color="gray" if self._is_muted else ("#e31e24" if self.volume_var.get() > 100 else accent))

    def _on_vol_keydown(self, event):
        step = 5
        curr = self.volume_var.get()
        if event.keysym in ["Left", "Down"]: new_v = max(0, curr - step)
        elif event.keysym in ["Right", "Up"]: new_v = min(150, curr + step)
        else: return
        self.vol_slider.set(new_v); self._on_volume(new_v)

    def _reset_vol(self, event=None):
        self.vol_slider.set(100); self._on_volume(100)

    def _on_seek(self, val):
        if self.vlc_player: self.vlc_player.set_position(float(val)/100.0)

    def _seek_relative(self, seconds):
        if not self.vlc_player: return
        cur_ms = self.vlc_player.get_time()
        self.vlc_player.set_time(cur_ms + (seconds * 1000))

    def _update_player_ui(self):
        if not self.vlc_player or not self.current_video_id: return
        
        pos = self.vlc_player.get_position() * 100
        ms = self.vlc_player.get_time()
        total_ms = self.vlc_player.get_length()
        
        if total_ms > 0:
            cur_str = f"{int(ms/60000)}:{int((ms%60000)/1000):02d}"
            tot_str = f"{int(total_ms/60000)}:{int((total_ms%60000)/1000):02d}"
            self.time_label.configure(text=f"{cur_str} / {tot_str}")
            self.progress_slider.set(pos)
            
        if self.is_playing or self.vlc_player.is_playing():
             self.after(100, self._update_player_ui)

if __name__ == "__main__": app = YtMsdGui(); app.mainloop()
