#Open Source Software under the Apache License, Version 2.0
#This is the GUI version of yt-msd. It is the full-featured version of the project.
#Again, only partially vibe coded. I swear I know what I'm doing

import os
import sys
import json
import threading
import yt_dlp
import customtkinter as ctk
from tkinter import filedialog, messagebox

# Set appearance mode and color theme for a modern Windows 11 look
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")  # Standard blue accent

class YtMsdGui(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window configuration - Widened for the queue
        self.title("yt-msd | YouTube Media Downloader")
        self.geometry("1400x850")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)  # Main area
        self.grid_rowconfigure(1, weight=0)  # Controls

        # Icon font for Windows (Segoe MDL2 Assets)
        self.icon_font = "Segoe MDL2 Assets"
        self.main_font = ("Segoe UI", 12)
        self.header_font = ("Segoe UI Semibold", 15)

        # Config file path
        self.config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui_config.json")

        # State variables
        self.search_results = []
        self.queue_items = []
        self.download_path_var = ctk.StringVar()
        self.format_var = ctk.StringVar(value="mp3")
        self.bitrate_var = ctk.StringVar(value="192")
        self.result_count_var = ctk.StringVar(value="10")
        self.recent_folders = []

        # Load settings from config
        self._load_config()
        
        self.result_count_var.trace_add("write", lambda *args: self._on_count_changed())
        
        self.is_searching = False
        self.is_downloading = False
        
        self.drag_data = {"item": None, "original_index": -1, "proxy": None}

        self._create_widgets()

    def _create_widgets(self):
        # --- Main Layout Container ---
        self.layout_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.layout_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=(15, 10))
        self.layout_frame.grid_columnconfigure(0, weight=3) # Search Results
        self.layout_frame.grid_columnconfigure(1, weight=0) # Separator
        self.layout_frame.grid_columnconfigure(2, weight=2) # Download Queue
        self.layout_frame.grid_rowconfigure(0, weight=1)

        # 1. Search Results Column
        self.results_col = ctk.CTkFrame(self.layout_frame, fg_color="transparent")
        self.results_col.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.results_col.grid_columnconfigure(0, weight=1)
        self.results_col.grid_rowconfigure(1, weight=1)

        self.res_header = ctk.CTkFrame(self.results_col, fg_color="transparent")
        self.res_header.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.results_label = ctk.CTkLabel(self.res_header, text="Search Results", font=self.header_font)
        self.results_label.pack(side="left")
        
        self.count_menu = ctk.CTkOptionMenu(self.res_header, values=["10", "20", "50", "100"], variable=self.result_count_var, width=70, height=26, font=self.main_font)
        self.count_menu.pack(side="right")
        ctk.CTkLabel(self.res_header, text="Show:", font=self.main_font).pack(side="right", padx=5)

        self.results_frame = ctk.CTkScrollableFrame(self.results_col, fg_color="#1e1e1e", corner_radius=10)
        self.results_frame.grid(row=1, column=0, sticky="nsew")

        # 2. Results/Queue Separator
        ctk.CTkFrame(self.layout_frame, width=2, fg_color="#444444").grid(row=0, column=1, sticky="ns", padx=5)

        # 3. Download Queue Column
        self.queue_col = ctk.CTkFrame(self.layout_frame, fg_color="transparent")
        self.queue_col.grid(row=0, column=2, sticky="nsew", padx=(10, 0))
        self.queue_col.grid_columnconfigure(0, weight=1)
        self.queue_col.grid_rowconfigure(1, weight=1)

        self.queue_header = ctk.CTkFrame(self.queue_col, fg_color="transparent")
        self.queue_header.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.queue_label = ctk.CTkLabel(self.queue_header, text="Download Queue (0)", font=self.header_font)
        self.queue_label.pack(side="left")
        
        self.clear_comp_btn = ctk.CTkButton(self.queue_header, text="Clear Completed", font=self.main_font, height=26, width=120, fg_color="#444444", hover_color="#555555", command=self._clear_completed)
        self.clear_comp_btn.pack(side="right")

        self.queue_frame = ctk.CTkScrollableFrame(self.queue_col, fg_color="#1e1e1e", corner_radius=10)
        self.queue_frame.grid(row=1, column=0, sticky="nsew")

        # 4. Global Control Panel
        self.control_panel = ctk.CTkFrame(self, height=180, corner_radius=0, fg_color="#333333")
        self.control_panel.grid(row=1, column=0, sticky="ew")
        self.control_panel.grid_columnconfigure(0, weight=1)

        # Search Bar
        self.search_bar_frame = ctk.CTkFrame(self.control_panel, fg_color="transparent")
        self.search_bar_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(15, 10))
        self.search_bar_frame.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(self.search_bar_frame, placeholder_text="Search YouTube or paste URL here...", height=40, font=self.main_font, corner_radius=8)
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.search_entry.bind("<Return>", lambda e: self._start_search())

        self.search_button = ctk.CTkButton(self.search_bar_frame, text="\uE721", font=(self.icon_font, 16), width=50, height=40, command=self._start_search, corner_radius=8, fg_color="#0067c0", hover_color="#005aab")
        self.search_button.grid(row=0, column=1)

        # Settings
        self.settings_frame = ctk.CTkFrame(self.control_panel, fg_color="transparent")
        self.settings_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.settings_frame.grid_columnconfigure(5, weight=1)

        ctk.CTkLabel(self.settings_frame, text="Format:", font=self.main_font).grid(row=0, column=0, padx=(0, 5))
        self.format_menu = ctk.CTkOptionMenu(self.settings_frame, values=["mp3", "m4a", "flac", "wav", "aac", "opus", "ogg", "vorbis", "mka"], variable=self.format_var, width=80, height=28, command=lambda _: self._save_config())
        self.format_menu.grid(row=0, column=1, padx=(0, 10))

        ctk.CTkLabel(self.settings_frame, text="Bitrate:", font=self.main_font).grid(row=0, column=2, padx=(0, 5))
        self.bitrate_menu = ctk.CTkComboBox(self.settings_frame, values=["128", "192", "256", "320"], variable=self.bitrate_var, width=80, height=28, font=self.main_font, command=lambda _: self._save_config())
        self.bitrate_menu.grid(row=0, column=3, padx=(0, 10))

        ctk.CTkLabel(self.settings_frame, text="Save to:", font=self.main_font).grid(row=0, column=4, padx=(10, 5))
        
        # New ComboBox for Folder (Tracks 5 most recent)
        self.path_menu = ctk.CTkComboBox(self.settings_frame, values=self.recent_folders, variable=self.download_path_var, font=self.main_font, height=28, command=lambda _: self._save_config())
        self.path_menu.grid(row=0, column=5, sticky="ew", padx=(0, 5))
        
        self.browse_button = ctk.CTkButton(self.settings_frame, text="\uED25", font=(self.icon_font, 14), width=35, height=28, command=self._browse_folder)
        self.browse_button.grid(row=0, column=6, padx=(0, 10))

        self.download_button = ctk.CTkButton(self.settings_frame, text="Download All", font=("Segoe UI Semibold", 13), height=35, width=140, fg_color="#0067c0", hover_color="#005aab", command=self._start_batch_download)
        self.download_button.grid(row=0, column=7)

        self.status_label = ctk.CTkLabel(self.control_panel, text="Ready", font=("Segoe UI", 11), text_color="gray")
        self.status_label.grid(row=2, column=0, sticky="w", padx=20, pady=(0, 10))

    # --- Config Management ---
    def _load_config(self):
        default_dl = os.path.join(os.path.expanduser("~"), "Downloads")
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    cfg = json.load(f)
                    self.format_var.set(cfg.get('format', 'mp3'))
                    self.bitrate_var.set(cfg.get('bitrate', '192'))
                    self.recent_folders = cfg.get('recent_folders', [default_dl])
                    self.download_path_var.set(self.recent_folders[0])
                    return
            except: pass
        self.recent_folders = [default_dl]
        self.download_path_var.set(default_dl)

    def _save_config(self):
        # Update folder list
        current_path = self.download_path_var.get()
        if current_path and current_path not in self.recent_folders:
            self.recent_folders.insert(0, current_path)
            self.recent_folders = self.recent_folders[:5]
        elif current_path in self.recent_folders:
            self.recent_folders.remove(current_path)
            self.recent_folders.insert(0, current_path)

        cfg = {
            'format': self.format_var.get(),
            'bitrate': self.bitrate_var.get(),
            'recent_folders': self.recent_folders
        }
        try:
            with open(self.config_path, 'w') as f:
                json.dump(cfg, f, indent=4)
            # Update path menu if it exists
            if hasattr(self, 'path_menu'):
                self.path_menu.configure(values=self.recent_folders)
        except: pass

    # --- Search Logic ---
    def _browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.download_path_var.get())
        if folder: 
            self.download_path_var.set(folder)
            self._save_config()

    def _on_count_changed(self):
        if self.search_results and not self.is_searching:
            self._update_results(self.search_results)

    def _start_search(self):
        if self.is_searching: return
        query = self.search_entry.get().strip()
        if not query: return
        
        self.is_searching = True
        # NEW: Show exact search term and clear the bar
        self.results_label.configure(text=f"Search Results - [{query}]")
        self.search_entry.delete(0, 'end')
        
        self.status_label.configure(text="Searching YouTube...", text_color="#0067c0")
        self.search_button.configure(state="disabled")
        for widget in self.results_frame.winfo_children(): widget.destroy()
        threading.Thread(target=self._perform_staged_search, args=(query,), daemon=True).start()

    def _perform_staged_search(self, query):
        try:
            initial_count = int(self.result_count_var.get())
            ydl_opts = {'quiet': True, 'extract_flat': True, 'skip_download': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch{initial_count}:{query}", download=False)
                results = [e for e in info['entries'] if e.get('_type') == 'url' or e.get('ie_key') == 'Youtube' or e.get('id')]
            self.after(0, lambda: self._update_results(results))
            threading.Thread(target=self._background_fetch_full, args=(query, len(results)), daemon=True).start()
        except Exception as e:
            self.after(0, lambda: self._handle_error(f"Search error: {e}"))

    def _background_fetch_full(self, query, already_fetched):
        try:
            ydl_opts = {'quiet': True, 'extract_flat': True, 'skip_download': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch110:{query}", download=False)
                full_results = [e for e in info['entries'] if e.get('_type') == 'url' or e.get('ie_key') == 'Youtube' or e.get('id')]
            self.search_results = full_results
            self.after(0, lambda: self.status_label.configure(text=f"Loaded {len(full_results)} results total", text_color="gray"))
        except: pass

    def _update_results(self, results):
        self.search_results = results
        self.is_searching = False
        self.search_button.configure(state="normal")
        for widget in self.results_frame.winfo_children(): widget.destroy()
        
        limit = int(self.result_count_var.get())
        display_results = results[:limit]
        self.status_label.configure(text=f"Showing top {len(display_results)} results", text_color="gray")
        for video in display_results: self._create_result_item(video)

    def _create_result_item(self, video):
        item_frame = ctk.CTkFrame(self.results_frame, fg_color="transparent")
        item_frame.pack(fill="x", padx=5, pady=0)
        
        is_queued = any(q['video']['id'] == video['id'] for q in self.queue_items)
        
        # Truncate title for search results - higher limit for wide window
        display_title = video.get('title', 'Unknown')
        if len(display_title) > 180: display_title = display_title[:177] + "..."
        
        cb = ctk.CTkCheckBox(item_frame, text=f"{display_title} | {video.get('uploader')}", font=self.main_font, width=0, checkbox_width=18, checkbox_height=18, command=lambda v=video: self._toggle_queue(v))
        cb.pack(side="left", fill="x", expand=True, pady=1)
        if is_queued: cb.select()
        video['checkbox'] = cb

    # --- Queue Logic ---
    def _toggle_queue(self, video):
        if video['checkbox'].get():
            if not any(q['video']['id'] == video['id'] for q in self.queue_items):
                self.queue_items.append({'video': video, 'status': 'Pending'})
        else:
            self.queue_items = [q for q in self.queue_items if q['video']['id'] != video['id']]
        self._refresh_queue_display()

    def _refresh_queue_display(self):
        for widget in self.queue_frame.winfo_children(): widget.destroy()
        self.queue_label.configure(text=f"Download Queue ({len(self.queue_items)})")
        for i, q_item in enumerate(self.queue_items): self._create_queue_widget(q_item, i)

    def _create_queue_widget(self, q_item, index):
        video = q_item['video']
        status = q_item['status']
        text_color = "gray" if status == "Finished" else "white"
        f = ctk.CTkFrame(self.queue_frame, fg_color="#2a2a2a", corner_radius=5, height=40)
        f.pack(fill="x", padx=5, pady=2)
        status_text = ""
        if status == "Finished": status_text = "\uE73E "
        elif status == "Downloading": status_text = "\uE896 "
        
        # Truncate title for queue - much higher limit (150)
        display_title = video.get('title', 'Unknown')
        if len(display_title) > 150: display_title = display_title[:147] + "..."
        
        # PACK BUTTON FIRST to ensure it stays on the right
        rem_btn = ctk.CTkButton(f, text="\uE711", font=(self.icon_font, 12), width=30, height=30, fg_color="transparent", hover_color="#444444", command=lambda idx=index: self._remove_from_queue(idx))
        rem_btn.pack(side="right", padx=5)

        lbl = ctk.CTkLabel(f, text=f"{status_text}{display_title}", font=self.main_font, text_color=text_color, anchor="w", cursor="fleur")
        lbl.pack(side="left", fill="x", expand=True, padx=10)
        for w in [f, lbl]:
            w.bind("<Button-1>", lambda e, idx=index, data=q_item: self._on_drag_start(e, idx, data), add="+")
            w.bind("<B1-Motion>", self._on_drag_motion, add="+")
            w.bind("<ButtonRelease-1>", self._on_drag_stop, add="+")

    def _remove_from_queue(self, index):
        removed_video = self.queue_items.pop(index)['video']
        for res in self.search_results:
            if res['id'] == removed_video['id'] and 'checkbox' in res:
                res['checkbox'].deselect()
        self._refresh_queue_display()

    def _clear_completed(self):
        self.queue_items = [q for q in self.queue_items if q['status'] != "Finished"]
        self._refresh_queue_display()

    # --- ADVANCED Drag & Drop logic ---
    def _on_drag_start(self, event, index, q_item):
        self.drag_data["original_index"] = index
        self.drag_data["item"] = q_item
        self.drag_data["proxy"] = ctk.CTkFrame(self, fg_color="#3a3a3a", border_width=2, border_color="#0067c0", corner_radius=5, width=400, height=40)
        proxy_title = ctk.CTkLabel(self.drag_data["proxy"], text=f"\uE76F {q_item['video']['title'][:50]}...", font=self.main_font)
        proxy_title.pack(padx=20, pady=8)
        self.drag_data["proxy"].place(x=event.x_root - self.winfo_rootx() - 200, y=event.y_root - self.winfo_rooty() - 20)

    def _on_drag_motion(self, event):
        if self.drag_data["proxy"]:
            self.drag_data["proxy"].place(x=event.x_root - self.winfo_rootx() - 200, y=event.y_root - self.winfo_rooty() - 20)

    def _on_drag_stop(self, event):
        if self.drag_data["proxy"]:
            self.drag_data["proxy"].destroy()
            self.drag_data["proxy"] = None
        if self.drag_data["item"] is None: return
        y_rel = event.y_root - self.queue_frame.winfo_rooty()
        new_index = max(0, min(len(self.queue_items) - 1, int(y_rel / 44)))
        if new_index != self.drag_data["original_index"]:
            item = self.queue_items.pop(self.drag_data["original_index"])
            self.queue_items.insert(new_index, item)
            self._refresh_queue_display()
        self.drag_data = {"item": None, "original_index": -1, "proxy": None}
        self.status_label.configure(text="Ready", text_color="gray")

    # --- Batch Download Logic ---
    def _start_batch_download(self):
        if self.is_downloading: return
        # Save current settings and folder list
        self._save_config()
        pending = [q for q in self.queue_items if q['status'] == "Pending"]
        if not pending:
            messagebox.showinfo("Queue Empty", "No pending downloads.")
            return
        self.is_downloading = True
        self.download_button.configure(state="disabled", text="Processing Queue...")
        threading.Thread(target=self._process_queue, daemon=True).start()

    def _process_queue(self):
        save_folder = self.download_path_var.get()
        for q_item in self.queue_items:
            if q_item['status'] == "Pending":
                q_item['status'] = "Downloading"
                self.after(0, self._refresh_queue_display)
                url = f"https://www.youtube.com/watch?v={q_item['video']['id']}"
                self._perform_single_download(url, q_item, save_folder)
                q_item['status'] = "Finished"
                self.after(0, self._refresh_queue_display)

        self.is_downloading = False
        self.after(0, lambda: self.download_button.configure(state="normal", text="Download All"))
        # NEW: Status with save folder
        self.after(0, lambda: self.status_label.configure(text=f"Batch Download Complete! Saved to: {save_folder}", text_color="#28a745"))

    def _perform_single_download(self, url, q_item, save_folder):
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': f"{save_folder}/%(title)s.%(ext)s",
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': self.format_var.get(), 'preferredquality': self.bitrate_var.get()}],
                'progress_hooks': [self._progress_hook],
                'quiet': True, 'no_warnings': True
            }
            if getattr(sys, 'frozen', False):
                ydl_opts['ffmpeg_location'] = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
            with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
        except Exception:
            self.after(0, lambda: messagebox.showerror("Error", f"Failed: {q_item['video']['title']}"))

    def _progress_hook(self, d):
        if d['status'] == 'downloading':
            p = d.get('_percent_str', '0.0%')
            self.after(0, lambda: self.status_label.configure(text=f"Batch Progress... {p}"))

    def _handle_error(self, msg):
        self.is_searching = False
        self.search_button.configure(state="normal")
        self.status_label.configure(text="Error", text_color="red")
        messagebox.showerror("Error", msg)

if __name__ == "__main__":
    app = YtMsdGui()
    app.mainloop()
