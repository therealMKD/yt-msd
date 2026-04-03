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

        # Window configuration
        self.title("yt-msd | YouTube Media Downloader")
        self.geometry("900x700")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)  # Results area
        self.grid_rowconfigure(1, weight=0)  # Search & Controls

        # Icon font for Windows (Segoe MDL2 Assets)
        self.icon_font = "Segoe MDL2 Assets"
        self.main_font = ("Segoe UI", 12)
        self.header_font = ("Segoe UI Semibold", 15)

        # State variables
        self.search_results = []
        self.selected_video = None
        self.download_path_var = ctk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads"))
        self.format_var = ctk.StringVar(value="mp3")
        self.bitrate_var = ctk.StringVar(value="192")
        self.result_count_var = ctk.StringVar(value="10")
        
        # Add trace to update display immediately when result count changes
        self.result_count_var.trace_add("write", lambda *args: self._on_count_changed())
        
        self.is_searching = False
        self.is_downloading = False

        self._create_widgets()

    def _create_widgets(self):
        # Main Container
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=(15, 10))
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)

        # Results Header with Count Selector
        self.header_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        
        self.results_label = ctk.CTkLabel(self.header_frame, text="Search Results", font=self.header_font)
        self.results_label.pack(side="left")

        self.count_menu = ctk.CTkOptionMenu(
            self.header_frame,
            values=["10", "20", "50", "100"],
            variable=self.result_count_var,
            width=70,
            height=26,
            font=self.main_font
        )
        self.count_menu.pack(side="right")
        ctk.CTkLabel(self.header_frame, text="Show:", font=self.main_font).pack(side="right", padx=5)

        # Results Scrollable Frame
        self.results_frame = ctk.CTkScrollableFrame(self.main_frame, fg_color="#1e1e1e", corner_radius=10)
        self.results_frame.grid(row=1, column=0, sticky="nsew")

        # Search & Control Panel
        self.control_panel = ctk.CTkFrame(self, height=180, corner_radius=0, fg_color="#333333")
        self.control_panel.grid(row=1, column=0, sticky="ew")
        self.control_panel.grid_columnconfigure(0, weight=1)

        # Search
        self.search_bar_frame = ctk.CTkFrame(self.control_panel, fg_color="transparent")
        self.search_bar_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(15, 10))
        self.search_bar_frame.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            self.search_bar_frame, 
            placeholder_text="Search YouTube or paste URL here...",
            height=40,
            font=self.main_font,
            corner_radius=8
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.search_entry.bind("<Return>", lambda e: self._start_search())

        self.search_button = ctk.CTkButton(
            self.search_bar_frame,
            text="\uE721", # Search icon
            font=(self.icon_font, 16),
            width=50,
            height=40,
            command=self._start_search,
            corner_radius=8,
            fg_color="#0067c0",
            hover_color="#005aab"
        )
        self.search_button.grid(row=0, column=1)

        # Controls
        self.settings_frame = ctk.CTkFrame(self.control_panel, fg_color="transparent")
        self.settings_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.settings_frame.grid_columnconfigure(5, weight=1)

        # Format
        ctk.CTkLabel(self.settings_frame, text="Format:", font=self.main_font).grid(row=0, column=0, padx=(0, 5))
        self.format_menu = ctk.CTkOptionMenu(
            self.settings_frame,
            values=["mp3", "m4a", "flac", "wav", "aac", "opus", "ogg", "vorbis", "mka"],
            variable=self.format_var,
            width=80, height=28
        )
        self.format_menu.grid(row=0, column=1, padx=(0, 10))

        # Bitrate
        ctk.CTkLabel(self.settings_frame, text="Bitrate:", font=self.main_font).grid(row=0, column=2, padx=(0, 5))
        self.bitrate_menu = ctk.CTkComboBox(
            self.settings_frame,
            values=["128", "192", "256", "320"],
            variable=self.bitrate_var,
            width=80, height=28,
            font=self.main_font
        )
        self.bitrate_menu.grid(row=0, column=3, padx=(0, 10))

        # Save Folder
        ctk.CTkLabel(self.settings_frame, text="Save to:", font=self.main_font).grid(row=0, column=4, padx=(10, 5))
        self.path_entry = ctk.CTkEntry(self.settings_frame, textvariable=self.download_path_var, font=self.main_font, height=28)
        self.path_entry.grid(row=0, column=5, sticky="ew", padx=(0, 5))
        
        self.browse_button = ctk.CTkButton(
            self.settings_frame,
            text="\uED25", # Folder icon
            font=(self.icon_font, 14),
            width=35, height=28,
            command=self._browse_folder
        )
        self.browse_button.grid(row=0, column=6, padx=(0, 10))

        # Download Button
        self.download_button = ctk.CTkButton(
            self.settings_frame,
            text="Download",
            font=("Segoe UI Semibold", 13),
            height=35,
            fg_color="#0067c0",
            hover_color="#005aab",
            command=self._start_download
        )
        self.download_button.grid(row=0, column=7)

        # 5. Status
        self.status_label = ctk.CTkLabel(self.control_panel, text="Ready", font=("Segoe UI", 11), text_color="gray")
        self.status_label.grid(row=2, column=0, sticky="w", padx=20, pady=(0, 10))

    def _browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.download_path_var.get())
        if folder:
            self.download_path_var.set(folder)

    def _on_count_changed(self):
        # Update results only if we already have some
        if self.search_results and not self.is_searching:
            self._update_results(self.search_results)

    def _start_search(self):
        if self.is_searching: return
        query = self.search_entry.get().strip()
        if not query: return

        self.is_searching = True
        self.status_label.configure(text="Searching YouTube...", text_color="#0067c0")
        self.search_button.configure(state="disabled")

        for widget in self.results_frame.winfo_children():
            widget.destroy()

        threading.Thread(target=self._perform_search, args=(query,), daemon=True).start()

    def _perform_search(self, query):
        try:
            ydl_opts = {'quiet': True, 'extract_flat': True, 'skip_download': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch110:{query}", download=False)
                results = [e for e in info['entries'] if e.get('_type') == 'url' or e.get('ie_key') == 'Youtube' or e.get('id')]
                
            self.after(0, lambda: self._update_results(results))
        except Exception as e:
            self.after(0, lambda: self._handle_error(f"Search error: {e}"))

    def _update_results(self, results):
        self.search_results = results
        self.is_searching = False
        self.search_button.configure(state="normal")
        
        # Clear existing buttons from results frame
        for widget in self.results_frame.winfo_children():
            widget.destroy()
            
        limit = int(self.result_count_var.get())
        display_results = results[:limit]
        
        self.status_label.configure(text=f"Showing {len(display_results)} of {len(results)} results", text_color="gray")

        if not results:
            ctk.CTkLabel(self.results_frame, text="No results found.", font=self.main_font).pack(pady=20)
            return

        for i, video in enumerate(display_results):
            btn = ctk.CTkButton(
                self.results_frame,
                text=f"{video.get('title', 'Unknown Title')} | {video.get('uploader', 'Unknown Channel')}",
                font=self.main_font,
                anchor="w",
                fg_color="transparent",
                text_color="white",
                hover_color="#3a3a3a",
                height=32,
                corner_radius=5,
                command=lambda v=video, idx=i: self._select_video(v, idx)
            )
            btn.pack(fill="x", padx=5, pady=1)
            video['widget'] = btn

    def _select_video(self, video, idx):
        for res in self.search_results:
            if 'widget' in res:
                res['widget'].configure(fg_color="transparent")
        
        video['widget'].configure(fg_color="#0067c0")
        self.selected_video = video
        self.status_label.configure(text=f"Selected: {video.get('title')}", text_color="white")

    def _start_download(self):
        if self.is_downloading: return
        
        query = self.search_entry.get().strip()
        if query.startswith(("http://", "https://", "www.youtube.com", "youtu.be")):
            url = query
            title = "Direct URL"
        elif self.selected_video:
            url = f"https://www.youtube.com/watch?v={self.selected_video['id']}"
            title = self.selected_video.get('title')
        else:
            messagebox.showwarning("No Selection", "Please select a video or paste a URL.")
            return

        self.is_downloading = True
        self.download_button.configure(state="disabled", text="Downloading...")
        self.status_label.configure(text=f"Downloading: {title}", text_color="#0067c0")

        threading.Thread(target=self._perform_download, args=(url,), daemon=True).start()

    def _perform_download(self, url):
        try:
            download_path = self.download_path_var.get().replace("\\", "/")
            format_ext = self.format_var.get()
            bitrate = self.bitrate_var.get()

            ydl_opts = {
                'format': f'bestaudio/best',
                'outtmpl': f"{download_path}/%(title)s.%(ext)s",
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': format_ext,
                    'preferredquality': bitrate,
                }],
                'progress_hooks': [self._progress_hook],
                'quiet': True, 'no_warnings': True
            }

            if getattr(sys, 'frozen', False):
                ffmpeg_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
                ydl_opts['ffmpeg_location'] = ffmpeg_path

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            self.after(0, self._download_finished)
        except Exception as e:
            self.after(0, lambda: self._handle_error(f"Download error: {e}"))

    def _progress_hook(self, d):
        if d['status'] == 'downloading':
            p = d.get('_percent_str', '0.0%')
            self.after(0, lambda: self.status_label.configure(text=f"Downloading... {p}"))

    def _download_finished(self):
        self.is_downloading = False
        self.download_button.configure(state="normal", text="Download")
        self.status_label.configure(text="Download Complete!", text_color="#28a745")

    def _handle_error(self, msg):
        self.is_searching = False
        self.is_downloading = False
        self.search_button.configure(state="normal")
        self.download_button.configure(state="normal", text="Download")
        self.status_label.configure(text="Error occurred", text_color="#dc3545")
        messagebox.showerror("Error", msg)

if __name__ == "__main__":
    app = YtMsdGui()
    app.mainloop()
