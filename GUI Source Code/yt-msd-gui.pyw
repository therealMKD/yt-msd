#Open Source Software under the Apache License, Version 2.0
#This is the GUI version of yt-msd. It is the full-featured version of the project.
#Again, only partially vibe coded. I swear I know what I'm doing

import os
import sys
import json
import threading
import winreg
import yt_dlp
import customtkinter as ctk
from tkinter import filedialog, messagebox

# Theme Mapping for custom colors
THEME_COLORS = {
    "Blue": ("#3B8ED0", "#1F6AA5"),
    "Green": ("#2CC985", "#2FA572"),
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
        
        # Position Settings window in the upper left of the main window
        p_x = self.parent.winfo_x()
        p_y = self.parent.winfo_y()
        self.geometry(f"380x300+{p_x+20}+{p_y+20}")
        
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        
        # 1. Appearance Mode Header
        ctk.CTkLabel(self.main_frame, text="Appearance Mode", font=self.parent.header_font).pack(anchor="w", pady=(0, 5))
        self.mode_switch = ctk.CTkSegmentedButton(self.main_frame, values=["System", "Light", "Dark"], command=self._change_mode)
        self.mode_switch.pack(fill="x", pady=(0, 15))
        self.mode_switch.set(self.parent.appearance_mode_var.get())

        # 2. Accent Color Header
        ctk.CTkLabel(self.main_frame, text="Accent Color", font=self.parent.header_font).pack(anchor="w", pady=(0, 5))
        self.color_grid = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.color_grid.pack(fill="x")
        
        colors_to_show = ["System"] + list(THEME_COLORS.keys())
        self.color_buttons = {}
        
        for i, color in enumerate(colors_to_show):
            row = i // 5
            col = i % 5
            actual_color = self.parent._get_system_accent_color() if color == "System" else THEME_COLORS[color][0]
            btn_text = "\uE771" if color == "System" else ""
                
            btn = ctk.CTkButton(self.color_grid, text=btn_text, font=(self.parent.icon_font, 12), width=25, height=25, fg_color=actual_color, hover_color=actual_color, corner_radius=4, command=lambda c=color: self._change_accent(c))
            btn.grid(row=row, column=col, padx=4, pady=4)
            self.color_buttons[color] = btn
            
        self._update_color_selection_visuals()

        # Small Close button at bottom-right
        self.close_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.close_frame.pack(side="bottom", fill="x", pady=(20, 0))
        self.close_btn = ctk.CTkButton(self.close_frame, text="Close", font=self.parent.main_font, height=28, width=80, fg_color=("#888888", "#444444"), hover_color=("#aaaaaa", "#555555"), command=self.destroy)
        self.close_btn.pack(side="right")

    def _update_color_selection_visuals(self):
        current_color = self.parent.accent_color_var.get()
        for color, btn in self.color_buttons.items():
            if color == current_color:
                btn.configure(border_width=2, border_color=("#333333", "#ffffff"))
            else:
                btn.configure(border_width=0)

    def _change_mode(self, mode):
        self.parent.appearance_mode_var.set(mode)
        ctk.set_appearance_mode(mode)
        self.parent._save_config()

    def _change_accent(self, color):
        self.parent.accent_color_var.set(color)
        self.parent._apply_accent_color(color)
        self._update_color_selection_visuals()
        self.parent._save_config()

class YtMsdGui(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window configuration - Centered on screen
        width, height = 1400, 850
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = (screen_w // 2) - (width // 2)
        y = (screen_h // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        
        self.title("yt-msd | YouTube Media Downloader")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Fonts
        self.icon_font = "Segoe MDL2 Assets"
        self.main_font = ("Segoe UI", 12)
        self.header_font = ("Segoe UI Semibold", 15)

        self.config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui_config.json")

        # State variables
        self.search_results = []
        self.queue_items = []
        self.download_path_var = ctk.StringVar()
        self.format_var = ctk.StringVar(value="mp3")
        self.bitrate_var = ctk.StringVar(value="192")
        self.result_count_var = ctk.StringVar(value="10")
        self.appearance_mode_var = ctk.StringVar(value="System")
        self.accent_color_var = ctk.StringVar(value="Blue")
        self.divider_percent = ctk.DoubleVar(value=0.6)
        self.recent_folders = []

        self._load_config()
        self.is_searching = False
        self.is_downloading = False
        self.drag_data = {"item": None, "original_index": -1, "proxy": None}
        self.divider_dragging = False

        self._create_widgets()
        
        # Apply initial theme after widgets are created
        ctk.set_appearance_mode(self.appearance_mode_var.get())
        self._apply_accent_color(self.accent_color_var.get())
        self.result_count_var.trace_add("write", lambda *args: self._on_count_changed())

    def _create_widgets(self):
        # Adaptive backgrounds for frame consistency
        box_bg = ("#f0f0f0", "#1e1e1e")
        ctrl_bg = ("#e0e0e0", "#333333")

        # --- Main Layout Container ---
        self.layout_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.layout_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=(15, 10))
        self.layout_frame.grid_rowconfigure(0, weight=1)
        self._update_column_weights()

        # 1. Search Results Column
        self.results_col = ctk.CTkFrame(self.layout_frame, fg_color="transparent")
        self.results_col.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.results_col.grid_columnconfigure(0, weight=1)
        self.results_col.grid_rowconfigure(1, weight=1)

        self.res_header = ctk.CTkFrame(self.results_col, fg_color="transparent")
        self.res_header.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.results_label = ctk.CTkLabel(self.res_header, text="Search Results", font=self.header_font)
        self.results_label.pack(side="left")
        
        self.count_menu = ctk.CTkOptionMenu(self.res_header, values=["10", "20", "50", "100"], variable=self.result_count_var, width=70, height=26)
        self.count_menu.pack(side="right")
        ctk.CTkLabel(self.res_header, text="Show:", font=self.main_font).pack(side="right", padx=5)

        self.results_frame = ctk.CTkScrollableFrame(self.results_col, fg_color=box_bg, corner_radius=10)
        self.results_frame.grid(row=1, column=0, sticky="nsew")

        # 2. Resizable Handle
        self.handle = ctk.CTkFrame(self.layout_frame, width=4, fg_color=ctrl_bg, cursor="sb_h_double_arrow")
        self.handle.grid(row=0, column=1, sticky="ns", padx=2)
        self.handle.bind("<Button-1>", lambda e: setattr(self, "divider_dragging", True))
        self.handle.bind("<B1-Motion>", self._on_divider_drag)
        self.handle.bind("<ButtonRelease-1>", self._stop_divider_drag)

        # 3. Download Queue Column
        self.queue_col = ctk.CTkFrame(self.layout_frame, fg_color="transparent")
        self.queue_col.grid(row=0, column=2, sticky="nsew", padx=(5, 0))
        self.queue_col.grid_columnconfigure(0, weight=1)
        self.queue_col.grid_rowconfigure(1, weight=1)

        self.queue_header = ctk.CTkFrame(self.queue_col, fg_color="transparent")
        self.queue_header.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.queue_label = ctk.CTkLabel(self.queue_header, text="Download Queue (0)", font=self.header_font)
        self.queue_label.pack(side="left")
        
        self.clear_comp_btn = ctk.CTkButton(self.queue_header, text="Clear Completed", font=self.main_font, height=26, width=120, fg_color=ctrl_bg, hover_color=("#dddddd", "#444444"), text_color=("#1a1a1a", "#ffffff"), command=self._clear_completed)
        self.clear_comp_btn.pack(side="right")

        self.queue_frame = ctk.CTkScrollableFrame(self.queue_col, fg_color=box_bg, corner_radius=10)
        self.queue_frame.grid(row=1, column=0, sticky="nsew")

        # 4. Global Control Panel
        self.control_panel = ctk.CTkFrame(self, height=180, corner_radius=0, fg_color=ctrl_bg)
        self.control_panel.grid(row=1, column=0, sticky="ew")
        self.control_panel.grid_columnconfigure(0, weight=1)

        self.search_bar_frame = ctk.CTkFrame(self.control_panel, fg_color="transparent")
        self.search_bar_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(15, 10))
        self.search_bar_frame.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(self.search_bar_frame, placeholder_text="Search YouTube...", height=40, font=self.main_font, corner_radius=8)
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.search_entry.bind("<Return>", lambda e: self._start_search())

        self.search_button = ctk.CTkButton(self.search_bar_frame, text="\uE721", font=(self.icon_font, 16), width=50, height=40, command=self._start_search, corner_radius=8)
        self.search_button.grid(row=0, column=1)

        self.settings_frame = ctk.CTkFrame(self.control_panel, fg_color="transparent")
        self.settings_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.settings_frame.grid_columnconfigure(5, weight=1)

        ctk.CTkLabel(self.settings_frame, text="Format:", font=self.main_font).grid(row=0, column=0, padx=(0, 5))
        self.format_menu = ctk.CTkOptionMenu(self.settings_frame, values=["mp3", "m4a", "flac", "wav", "aac", "opus", "ogg", "vorbis", "mka"], variable=self.format_var, width=80, height=28, command=lambda _: self._save_config())
        self.format_menu.grid(row=0, column=1, padx=(0, 10))

        ctk.CTkLabel(self.settings_frame, text="Bitrate:", font=self.main_font).grid(row=0, column=2, padx=(0, 5))
        self.bitrate_menu = ctk.CTkComboBox(self.settings_frame, values=["128", "192", "256", "320"], variable=self.bitrate_var, width=90, height=28, command=lambda _: self._save_config())
        self.bitrate_menu.grid(row=0, column=3, padx=(0, 10))

        ctk.CTkLabel(self.settings_frame, text="Save to:", font=self.main_font).grid(row=0, column=4, padx=(10, 5))
        self.path_menu = ctk.CTkComboBox(self.settings_frame, values=self.recent_folders, variable=self.download_path_var, font=self.main_font, height=28, command=lambda _: self._save_config())
        self.path_menu.grid(row=0, column=5, sticky="ew", padx=(0, 5))
        
        self.browse_button = ctk.CTkButton(self.settings_frame, text="\uED25", font=(self.icon_font, 14), width=35, height=28, command=self._browse_folder)
        self.browse_button.grid(row=0, column=6, padx=(0, 10))

        self.download_button = ctk.CTkButton(self.settings_frame, text="Download All", font=("Segoe UI Semibold", 13), height=35, width=140, command=self._start_batch_download)
        self.download_button.grid(row=0, column=7)

        # Status row
        self.status_row = ctk.CTkFrame(self.control_panel, fg_color="transparent")
        self.status_row.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.status_row.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(self.status_row, text="Ready", font=("Segoe UI", 11), text_color="gray")
        self.status_label.grid(row=0, column=0, sticky="w")
        
        self.settings_btn = ctk.CTkButton(self.status_row, text="\uE713", font=(self.icon_font, 16), width=40, height=30, fg_color="transparent", hover_color=("#dddddd", "#444444"), text_color=("#333333", "#ffffff"), command=self._open_settings)
        self.settings_btn.grid(row=0, column=1, sticky="e")

    # --- Theme & Settings ---
    def _apply_accent_color(self, color_name):
        if color_name == "System":
            accent = self._get_system_accent_color()
            hover = accent
        else:
            accent, hover = THEME_COLORS.get(color_name, THEME_COLORS["Blue"])
        
        # Ensure contrast: White/Yellow use black text
        txt_color = "#000000" if color_name in ["White", "Yellow", "Grey"] else "#ffffff"
        
        # Comprehensive Accent Application
        widgets_to_accent = [
            self.search_button, 
            self.download_button,
            self.format_menu,
            self.count_menu,
            self.browse_button,
            self.bitrate_menu,
            self.path_menu
        ]
        
        for w in widgets_to_accent:
            if isinstance(w, ctk.CTkButton):
                w.configure(fg_color=accent, hover_color=hover, text_color=txt_color)
            elif isinstance(w, ctk.CTkOptionMenu):
                w.configure(fg_color=accent, button_color=accent, button_hover_color=hover, text_color=txt_color)
            elif isinstance(w, ctk.CTkComboBox):
                w.configure(button_color=accent, button_hover_color=hover, border_color=accent, text_color=("#1a1a1a", "#ffffff"))

        # Update lists checkbox colors
        for widget in list(self.results_frame.winfo_children()):
             for child in widget.winfo_children():
                if isinstance(child, ctk.CTkCheckBox):
                    child.configure(border_color=accent, checkmark_color=accent)

    def _get_system_accent_color(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM")
            val, _ = winreg.QueryValueEx(key, "AccentColor")
            winreg.CloseKey(key)
            b = (val >> 16) & 0xFF
            g = (val >> 8) & 0xFF
            r = val & 0xFF
            return f"#{r:02x}{g:02x}{b:02x}"
        except: return "#0067c0"

    def _open_settings(self): SettingsWindow(self)

    # --- Resizer Handle ---
    def _update_column_weights(self):
        w = self.divider_percent.get()
        self.layout_frame.grid_columnconfigure(0, weight=int(w * 100))
        self.layout_frame.grid_columnconfigure(1, weight=0)
        self.layout_frame.grid_columnconfigure(2, weight=int((1 - w) * 100))

    def _on_divider_drag(self, event):
        if not self.divider_dragging: return
        tot = self.layout_frame.winfo_width()
        if tot == 0: return
        percent = max(0.2, min(0.8, (event.x_root - self.layout_frame.winfo_rootx()) / tot))
        self.divider_percent.set(percent)
        self._update_column_weights()

    def _stop_divider_drag(self, event):
        self.divider_dragging = False
        self._save_config()

    # --- Persistence ---
    def _load_config(self):
        default_dl = os.path.join(os.path.expanduser("~"), "Downloads")
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    cfg = json.load(f)
                    self.format_var.set(cfg.get('format', 'mp3'))
                    self.bitrate_var.set(cfg.get('bitrate', '192'))
                    self.appearance_mode_var.set(cfg.get('appearance_mode', 'System'))
                    self.accent_color_var.set(cfg.get('accent_color', 'System'))
                    self.divider_percent.set(cfg.get('divider_percent', 0.6))
                    self.recent_folders = cfg.get('recent_folders', [default_dl])
                    self.download_path_var.set(self.recent_folders[0])
                    return
            except: pass
        self.recent_folders = [default_dl]
        self.download_path_var.set(default_dl)

    def _save_config(self):
        cur = self.download_path_var.get()
        if cur and cur not in self.recent_folders:
            self.recent_folders.insert(0, cur)
            self.recent_folders = self.recent_folders[:5]
        cfg = {'format': self.format_var.get(), 'bitrate': self.bitrate_var.get(), 'appearance_mode': self.appearance_mode_var.get(), 'accent_color': self.accent_color_var.get(), 'divider_percent': self.divider_percent.get(), 'recent_folders': self.recent_folders}
        try:
            with open(self.config_path, 'w') as f: json.dump(cfg, f, indent=4)
            if hasattr(self, 'path_menu'): self.path_menu.configure(values=self.recent_folders)
        except: pass

    # --- Core Logic Reused ---
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
        self.results_label.configure(text=f"Search Results - [{query}]")
        self.search_entry.delete(0, 'end')
        self.status_label.configure(text="Searching YouTube...", text_color="#0067c0")
        self.search_button.configure(state="disabled")
        for widget in self.results_frame.winfo_children(): widget.destroy()
        threading.Thread(target=self._perform_staged_search, args=(query,), daemon=True).start()

    def _perform_staged_search(self, query):
        try:
            initial = int(self.result_count_var.get())
            ydl_opts = {'quiet': True, 'extract_flat': True, 'skip_download': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch{initial}:{query}", download=False)
                results = [e for e in info['entries'] if e.get('_type') == 'url' or e.get('ie_key') == 'Youtube' or e.get('id')]
            self.after(0, lambda: self._update_results(results))
            threading.Thread(target=self._background_fetch_full, args=(query, len(results)), daemon=True).start()
        except: self.after(0, lambda: self._handle_error("Search failed"))

    def _background_fetch_full(self, query, fetched):
        try:
            ydl_opts = {'quiet': True, 'extract_flat': True, 'skip_download': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch110:{query}", download=False)
            self.search_results = [e for e in info['entries'] if e.get('_type') == 'url' or e.get('ie_key') == 'Youtube' or e.get('id')]
            self.after(0, lambda: self.status_label.configure(text=f"Loaded {len(self.search_results)} results", text_color="gray"))
        except: pass

    def _update_results(self, results):
        self.search_results = results
        self.is_searching = False
        self.search_button.configure(state="normal")
        for widget in self.results_frame.winfo_children(): widget.destroy()
        for video in results[:int(self.result_count_var.get())]: self._create_result_item(video)

    def _create_result_item(self, video):
        f = ctk.CTkFrame(self.results_frame, fg_color="transparent")
        f.pack(fill="x", padx=5)
        title = video.get('title', 'Unknown')
        if len(title) > 180: title = title[:177] + "..."
        accent = self._get_system_accent_color() if self.accent_color_var.get() == "System" else THEME_COLORS.get(self.accent_color_var.get(), THEME_COLORS["Blue"])[0]
        cb = ctk.CTkCheckBox(f, text=f"{title} | {video.get('uploader')}", font=self.main_font, width=0, checkbox_width=18, checkbox_height=18, border_color=accent, checkmark_color=accent, command=lambda v=video: self._toggle_queue(v))
        cb.pack(side="left", fill="x", expand=True, pady=1)
        if any(q['video']['id'] == video['id'] for q in self.queue_items): cb.select()
        video['checkbox'] = cb

    def _toggle_queue(self, video):
        if video['checkbox'].get():
            if not any(q['video']['id'] == video['id'] for q in self.queue_items): self.queue_items.append({'video': video, 'status': 'Pending'})
        else: self.queue_items = [q for q in self.queue_items if q['video']['id'] != video['id']]
        self._refresh_queue_display()

    def _refresh_queue_display(self):
        for w in self.queue_frame.winfo_children(): w.destroy()
        self.queue_label.configure(text=f"Download Queue ({len(self.queue_items)})")
        for i, q in enumerate(self.queue_items): self._create_queue_widget(q, i)

    def _create_queue_widget(self, q, idx):
        f = ctk.CTkFrame(self.queue_frame, fg_color=("#e0e0e0", "#2a2a2a" if q['status'] != "Finished" else "#1a1a1a"), corner_radius=5, height=40)
        f.pack(fill="x", padx=5, pady=2)
        status_text = "\uE73E " if q['status'] == "Finished" else ("\uE896 " if q['status'] == "Downloading" else "")
        title = q['video'].get('title', 'Unknown')
        if len(title) > 150: title = title[:147] + "..."
        ctk.CTkButton(f, text="\uE711", font=(self.icon_font, 12), width=30, height=30, fg_color="transparent", hover_color=("#aaaaaa", "#444444"), command=lambda i=idx: self._remove_from_queue(i)).pack(side="right", padx=5)
        lbl = ctk.CTkLabel(f, text=f"{status_text}{title}", font=self.main_font, text_color=("#2a2a2a", "white"), anchor="w", cursor="fleur")
        lbl.pack(side="left", fill="x", expand=True, padx=10)
        for w in [f, lbl]:
            w.bind("<Button-1>", lambda e, i=idx, it=q: self._on_drag_start(e, i, it), add="+")
            w.bind("<B1-Motion>", self._on_drag_motion, add="+")
            w.bind("<ButtonRelease-1>", self._on_drag_stop, add="+")

    def _remove_from_queue(self, idx):
        vid = self.queue_items.pop(idx)['video']
        for res in self.search_results:
            if res['id'] == vid['id'] and 'checkbox' in res: res['checkbox'].deselect()
        self._refresh_queue_display()

    def _clear_completed(self):
        self.queue_items = [q for q in self.queue_items if q['status'] != "Finished"]
        self._refresh_queue_display()

    def _on_drag_start(self, event, idx, q):
        self.drag_data = {"original_index": idx, "item": q, "proxy": ctk.CTkFrame(self, fg_color=("#ffffff", "#3a3a3a"), border_width=2, border_color="#0067c0", corner_radius=5, width=400, height=40)}
        ctk.CTkLabel(self.drag_data["proxy"], text=f"\uE76F {q['video']['title'][:50]}...", font=self.main_font).pack(padx=20, pady=8)
        self.drag_data["proxy"].place(x=event.x_root - self.winfo_rootx() - 200, y=event.y_root - self.winfo_rooty() - 20)

    def _on_drag_motion(self, event):
        if self.drag_data["proxy"]: self.drag_data["proxy"].place(x=event.x_root - self.winfo_rootx() - 200, y=event.y_root - self.winfo_rooty() - 20)

    def _on_drag_stop(self, event):
        if self.drag_data["proxy"]: self.drag_data["proxy"].destroy()
        if self.drag_data["item"]:
            y = event.y_root - self.queue_frame.winfo_rooty()
            ni = max(0, min(len(self.queue_items) - 1, int(y / 44)))
            if ni != self.drag_data["original_index"]:
                it = self.queue_items.pop(self.drag_data["original_index"]); self.queue_items.insert(ni, it); self._refresh_queue_display()
        self.drag_data = {"item": None, "original_index": -1, "proxy": None}

    def _start_batch_download(self):
        if self.is_downloading: return
        self._save_config()
        pending = [q for q in self.queue_items if q['status'] == "Pending"]
        if not pending: return messagebox.showinfo("Queue Empty", "No pending downloads.")
        self.is_downloading = True
        self.download_button.configure(state="disabled", text="Downloading...")
        threading.Thread(target=self._process_queue, daemon=True).start()

    def _process_queue(self):
        folder = self.download_path_var.get()
        for q in self.queue_items:
            if q['status'] == "Pending":
                q['status'] = "Downloading"; self.after(0, self._refresh_queue_display)
                self._perform_single_download(f"https://www.youtube.com/watch?v={q['video']['id']}", q, folder)
                q['status'] = "Finished"; self.after(0, self._refresh_queue_display)
        self.is_downloading = False
        self.after(0, lambda: self.download_button.configure(state="normal", text="Download All"))
        self.after(0, lambda: self.status_label.configure(text=f"Batch Complete! Saved to: {folder}", text_color="#28a745"))

    def _perform_single_download(self, url, q, folder):
        try:
            ydl_opts = {'format': 'bestaudio/best', 'outtmpl': f"{folder}/%(title)s.%(ext)s", 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': self.format_var.get(), 'preferredquality': self.bitrate_var.get()}], 'progress_hooks': [self._progress_hook], 'quiet': True}
            if getattr(sys, 'frozen', False): ydl_opts['ffmpeg_location'] = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
            with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
        except: self.after(0, lambda: messagebox.showerror("Error", f"Failed: {q['video']['title']}"))

    def _progress_hook(self, d):
        if d['status'] == 'downloading': self.after(0, lambda: self.status_label.configure(text=f"Progress... {d.get('_percent_str', '0%')}"))

    def _handle_error(self, m):
        self.is_searching = False; self.search_button.configure(state="normal")
        self.status_label.configure(text="Error", text_color="red"); messagebox.showerror("Error", m)

if __name__ == "__main__":
    app = YtMsdGui()
    app.mainloop()
