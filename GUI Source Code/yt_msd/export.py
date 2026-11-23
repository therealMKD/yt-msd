# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.export).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
import os
import re
import json
import zipfile
import time
from typing import List, Optional, Tuple, Callable
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QScrollArea, QFileDialog, QDialog, QFrame
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from yt_msd.constants import APP_VERSION
from yt_msd.util.yaml import yaml_dump, yaml_load



# ═════════════════════════════════════════════════════════════════════════════
# EXPORT / IMPORT PACKAGES
#
# An export package is a single .zip containing:
#   export.yaml             manifest describing everything inside the package
#   config/gui-config.json  GUI settings (never contains sync chain keys unless
#                           "Sync Chains" was checked when exporting)
#   sync/sync-chains.json   hosted chains, client chains and sync settings
#   music/<folder>/...      copies of the music folders that were selected
#
# PyYAML is not a dependency of this app (TAG.yaml is hand-formatted too), so
# the manifest is written and read by the small YAML helpers below. They cover
# exactly the shapes export.yaml needs: nested mappings, lists of scalars, and
# lists of flat mappings.
# ═════════════════════════════════════════════════════════════════════════════

EXPORT_MANIFEST_NAME = "export.yaml"

EXPORT_CONFIG_ENTRY = "config/gui-config.json"

EXPORT_SYNC_ENTRY = "sync/sync-chains.json"

EXPORT_FORMAT_VERSION = 1

SYNC_ONLY_CONFIG_KEYS = ("sync_settings", "hosted_chains", "client_chains")

EXPORT_SKIP_DIRS = {"$recycle.bin", "system volume information", "__pycache__", ".git"}



def default_export_config() -> dict:
    """A fresh default GUI config, used when only sync chains are exported."""
    default_dl = os.path.join(os.path.expanduser("~"), "Downloads")
    return {
        'format': 'mp3',
        'bitrate': '192',
        'folders': [default_dl],
        'accent': 'System',
        'mode': 'Dark',
        'volume': 100,
        'local_folders': [],
        'local_current_path': '',
        'show_local_metadata': False,
        'minimize_to_tray': False,
        'recent_playlists': [],
        'splitter_sizes': [300, 800, 300],
        'use_custom_args': False,
        'custom_args': '',
        'last_search': '',
        'save_place': False,
        'session_data': {},
        'run_renamer': False,
        'renamer_path': '',
        'run_custom_script': False,
        'custom_script_path': '',
        'normalization_mode': 'ask',
        'auto_rename': False,
        'silence_pad_dur': 2.0,
        'silence_trim': True,
        'use_custom_norm_cmd': False,
        'custom_norm_cmd': '',
        'download_threads': 3,
        'normalization_threads': max(1, os.cpu_count() // 2),
        'local_rescan_interval': 60,
        'disable_update_checks': False,
        'disable_ytdlp_updates': False,
    }



def build_exported_config(current_config: dict, include_config: bool,
                          include_chains: bool, sync_payload: dict) -> dict:
    """Build the gui-config.json copy that goes inside the package.

    Config only   -> the live settings, with every sync chain key removed.
    Chains only   -> a default config with the current sync chains added to it.
    Both          -> the live settings, including the current sync chains.
    """
    base = dict(current_config) if include_config else default_export_config()
    for key in SYNC_ONLY_CONFIG_KEYS:
        base.pop(key, None)
    if include_chains and sync_payload:
        base.update(sync_payload)
    return base



def build_export_manifest_text(include_config: bool, include_chains: bool, include_music: bool,
                              music_entries: List[dict]) -> str:
    """The export.yaml text: what is in the package, and where it lives."""
    manifest = {
        'format_version': EXPORT_FORMAT_VERSION,
        'created': time.strftime("%m-%d-%Y %H:%M:%S"),
        'app_version': APP_VERSION,
        'includes': {
            'config': bool(include_config),
            'sync_chains': bool(include_chains),
            'music': bool(include_music),
        },
        'files': {
            'manifest': EXPORT_MANIFEST_NAME,
            'config': EXPORT_CONFIG_ENTRY,
            'sync_chains': EXPORT_SYNC_ENTRY if include_chains else "",
        },
        'music_folders': list(music_entries or []),
    }
    header = (
        "# yt-msd export package manifest. DO NOT EDIT.\n"
        "# yt-msd reads this file to know what is inside this .zip and how to restore it.\n\n"
    )
    return header + yaml_dump(manifest) + "\n"



def sanitize_archive_name(raw_name: str, fallback: str = "Music") -> str:
    """Make a folder name safe to use as a folder name inside the zip."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(raw_name or "")).strip().strip(".")
    return name or fallback



def unique_music_archive_name(folder: str, used_names: set) -> Tuple[str, str]:
    """Archive path and folder name for a music folder, kept unique inside the zip."""
    name = sanitize_archive_name(os.path.basename(os.path.abspath(folder).rstrip("\\/")))
    candidate = name
    counter = 2
    while candidate.lower() in used_names:
        candidate = f"{name}-{counter}"
        counter += 1
    used_names.add(candidate.lower())
    return f"music/{candidate}", candidate



def iter_folder_files(folder: str, include_subfolders: bool):
    """Yield (absolute path, path relative to the folder) for the files to package."""
    root = os.path.abspath(folder)
    if include_subfolders:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d.lower() not in EXPORT_SKIP_DIRS]
            for filename in filenames:
                full_path = os.path.join(dirpath, filename)
                yield full_path, os.path.relpath(full_path, root)
        return
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                try:
                    if entry.is_file():
                        yield entry.path, entry.name
                except OSError:
                    continue
    except OSError:
        pass



def zip_folder_into(zf, folder: str, archive_root: str, include_subfolders: bool) -> int:
    """Copy one folder into the zip. Returns how many files were written."""
    written = 0
    for full_path, relative_path in iter_folder_files(folder, include_subfolders):
        arcname = f"{archive_root}/{relative_path.replace(os.sep, '/')}"
        try:
            zf.write(full_path, arcname)
            written += 1
        except Exception:
            continue
    return written



def read_import_package(zip_path: str) -> dict:
    """Read export.yaml plus the config / sync payloads out of an export package."""
    with zipfile.ZipFile(zip_path, 'r') as zf:
        names = set(zf.namelist())
        if EXPORT_MANIFEST_NAME not in names:
            raise ValueError("it has no export.yaml manifest, so it is not a yt-msd package")
        manifest = yaml_load(zf.read(EXPORT_MANIFEST_NAME).decode('utf-8', errors='ignore'))
        files = manifest.get('files') if isinstance(manifest.get('files'), dict) else {}
        config_name = str(files.get('config') or EXPORT_CONFIG_ENTRY)
        sync_name = str(files.get('sync_chains') or EXPORT_SYNC_ENTRY)
        config_payload = None
        sync_payload = None
        if config_name in names:
            try:
                config_payload = json.loads(zf.read(config_name).decode('utf-8', errors='ignore'))
            except Exception:
                config_payload = None
        if sync_name in names:
            try:
                sync_payload = json.loads(zf.read(sync_name).decode('utf-8', errors='ignore'))
            except Exception:
                sync_payload = None
        return {'manifest': manifest, 'config': config_payload, 'sync': sync_payload}



def music_import_destination(source_path: str, folder_name: str) -> str:
    """Where a packaged music folder should be restored to.

    The original location is used when its parent folder still exists (same
    machine, or the same share on a new one). Otherwise the folder lands in
    Downloads/yt-msd Import.
    """
    source_path = str(source_path or "").strip()
    if source_path:
        absolute = os.path.abspath(source_path)
        parent = os.path.dirname(absolute)
        if parent and os.path.isdir(parent):
            return absolute
    return os.path.join(os.path.expanduser("~"), "Downloads", "yt-msd Import",
                        sanitize_archive_name(folder_name))



def extract_package_music(zf, manifest: dict,
                         status_cb: Optional[Callable[[str], None]] = None) -> List[dict]:
    """Unpack every music folder the manifest says is in the package."""
    results: List[dict] = []
    names = zf.namelist()
    for entry in manifest.get('music_folders') or []:
        if not isinstance(entry, dict):
            continue
        archive_path = str(entry.get('archive_path') or "").strip().strip("/")
        folder_name = str(entry.get('name') or "") or (archive_path.rsplit("/", 1)[-1] if archive_path else "")
        prefix = ""
        members: List[str] = []
        for candidate in [p for p in (archive_path, f"music/{folder_name}") if p]:
            candidate = candidate.rstrip("/") + "/"
            found = [n for n in names if n.startswith(candidate) and not n.endswith("/")]
            if found:
                prefix, members = candidate, found
                break
        dest_dir = music_import_destination(str(entry.get('source_path') or ""), folder_name)
        dest_root = os.path.normpath(dest_dir)
        written = 0
        error = ""
        for member in members:
            relative = member[len(prefix):].replace("/", os.sep)
            target = os.path.normpath(os.path.join(dest_root, relative))
            if target != dest_root and not target.startswith(dest_root + os.sep):
                continue
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(member) as packed_file:
                    data = packed_file.read()
                with open(target, 'wb') as out_file:
                    out_file.write(data)
                written += 1
            except Exception as exc:
                error = str(exc)
        results.append({'name': folder_name or os.path.basename(dest_root), 'dest': dest_dir,
                        'files': written, 'error': error})
        if status_cb:
            status_cb(f"Restored {written} files to {dest_dir}")
    return results



class ExportDialog(QDialog):
    """Choose what goes into a yt-msd export package (.zip)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Named main_app and not parent, for the reason spelled out in SettingsDialog:
        # self.parent would replace the Qt method of the same name on this dialog.
        self.main_app = parent
        self.setWindowTitle("Export Package")
        self.setMinimumWidth(620)
        self.music_rows: List[dict] = []      # {'path': str, 'check': QCheckBox, 'row': QWidget}
        # How small the window was before the Music section first grew it, so
        # unchecking Music can put the dialog back to that size.
        self._collapsed_size = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title_lbl = QLabel("EXPORT PACKAGE")
        title_lbl.setFont(QFont("Segoe UI Semibold", 11))
        layout.addWidget(title_lbl)
        desc_lbl = QLabel("Everything checked here is packed into one .zip file, described by an export.yaml manifest.\n"
                          "Import that file on another machine to put it all back.")
        desc_lbl.setFont(QFont("Segoe UI", 9))
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        self.config_cb = QCheckBox("Config")
        self.config_cb.setToolTip("Copy your settings (gui-config.json) without any sync chain information.")
        self.config_cb.setChecked(True)
        self.config_cb.toggled.connect(self._update_state)
        layout.addWidget(self.config_cb)

        self.chains_cb = QCheckBox("Sync Chains")
        self.chains_cb.setToolTip("Copy your hosted chains, client chains, and sync settings.")
        self.chains_cb.setChecked(True)
        self.chains_cb.toggled.connect(self._update_state)
        layout.addWidget(self.chains_cb)

        self.music_cb = QCheckBox("Music")
        self.music_cb.setToolTip("Copy the music folders you choose into the package.")
        self.music_cb.toggled.connect(self._toggle_music_section)
        layout.addWidget(self.music_cb)

        # ── MUSIC SECTION (only shown when Music is checked) ──
        self.music_widget = QWidget()
        music_layout = QVBoxLayout(self.music_widget)
        music_layout.setContentsMargins(26, 0, 0, 0)
        music_layout.setSpacing(8)

        folder_row = QHBoxLayout()
        self.add_folder_btn = QPushButton("Add Folder...")
        self.add_folder_btn.setToolTip("Browse for a folder to copy into the package")
        self.add_folder_btn.clicked.connect(self._add_music_folder)
        folder_row.addWidget(self.add_folder_btn)
        folder_row.addStretch()
        music_layout.addLayout(folder_row)

        self.music_rows_widget = QWidget()
        self.music_rows_layout = QVBoxLayout(self.music_rows_widget)
        self.music_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.music_rows_layout.setSpacing(4)
        self.music_rows_layout.addStretch()
        music_layout.addWidget(self._make_row_scroll(self.music_rows_widget, 140))

        layout.addWidget(self.music_widget)
        self.music_widget.setVisible(False)

        # ── FOOTER ──
        footer = QHBoxLayout()
        self.summary_lbl = QLabel("Nothing selected to export.")
        self.summary_lbl.setFont(QFont("Segoe UI", 9))
        footer.addWidget(self.summary_lbl)
        footer.addStretch()
        self.export_btn = QPushButton("Export Package...")
        self.export_btn.setToolTip("Choose where to save the .zip package")
        self.export_btn.clicked.connect(self._choose_export_file)
        footer.addWidget(self.export_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)
        layout.addLayout(footer)

        self._update_state()


    def _make_row_scroll(self, inner_widget: QWidget, max_height: int) -> QScrollArea:
        """A bounded, frameless scroll area for the folder rows."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner_widget)
        scroll.setMaximumHeight(max_height)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        return scroll

    def _toggle_music_section(self, state: bool):
        state = bool(state)
        if state and self._collapsed_size is None:
            # The checkbox changes before the section is shown, so this is still
            # the size the window had without the Music rows.
            self._collapsed_size = self.size()
        self.music_widget.setVisible(state)
        if not state and self._collapsed_size is not None:
            # Hiding a section never shrinks a Qt window by itself, and the layout
            # keeps reporting the expanded minimum size until it is recomputed, so
            # recompute it first and then go back to the size Music was added at.
            dialog_layout = self.layout()
            if dialog_layout is not None:
                dialog_layout.invalidate()
                dialog_layout.activate()
            if self.size() != self._collapsed_size:
                self.resize(self._collapsed_size)
            if self.size() != self._collapsed_size:
                # A layout pass that was already queued can push the window back
                # open, so try once more after the event loop has settled.
                QTimer.singleShot(0, lambda: self.resize(self._collapsed_size))
        self._update_state()

    def _add_music_folder(self):
        start = ""
        if self.music_rows:
            last = self.music_rows[-1]['path']
            start = os.path.dirname(last) or last
        folder = QFileDialog.getExistingDirectory(self, "Choose a Music Folder", start)
        if not folder:
            return
        self._add_music_row(os.path.abspath(folder))
        self._update_state()

    def _add_music_row(self, folder_path: str):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        path_lbl = QLabel(folder_path)
        path_lbl.setFont(QFont("Segoe UI", 9))
        path_lbl.setToolTip(folder_path)
        row_layout.addWidget(path_lbl, 1)

        sub_cb = QCheckBox("subfolders")
        sub_cb.setToolTip("Include everything inside this folder's subfolders")
        sub_cb.setChecked(True)
        sub_cb.toggled.connect(self._update_state)
        row_layout.addWidget(sub_cb)

        remove_btn = QPushButton("Remove")
        remove_btn.setToolTip("Do not include this folder")
        remove_btn.clicked.connect(lambda checked=False, path=folder_path: self._remove_row(self.music_rows, path, 'path'))
        row_layout.addWidget(remove_btn)

        # Keep the trailing stretch last so rows stay top-aligned.
        self.music_rows_layout.insertWidget(self.music_rows_layout.count() - 1, row_widget)
        self.music_rows.append({'path': folder_path, 'check': sub_cb, 'row': row_widget})

    def _remove_row(self, rows: List[dict], key_value: str, key_name: str):
        for entry in list(rows):
            if entry.get(key_name) == key_value:
                rows.remove(entry)
                self.music_rows_layout.removeWidget(entry['row'])
                entry['row'].deleteLater()
                break
        self._update_state()


    def build_options(self, require_selection: bool = False):
        """What the user picked, in the shape MainApp.start_export expects."""
        include_config = self.config_cb.isChecked()
        include_chains = self.chains_cb.isChecked()
        want_music = self.music_cb.isChecked()
        folders: List[dict] = []
        if want_music:
            folders = [{'path': entry['path'], 'subfolders': bool(entry['check'].isChecked())}
                       for entry in self.music_rows]
        include_music = bool(folders)
        if require_selection and not (include_config or include_chains or include_music):
            return None
        return {
            'include_config': include_config,
            'include_chains': include_chains,
            'include_music': include_music,
            'music_folders': folders,
        }

    def _update_state(self):
        options = self.build_options(require_selection=True)
        parts: List[str] = []
        if options:
            if options['include_config']:
                parts.append("config")
            if options['include_chains']:
                parts.append("sync chains")
            if options['include_music']:
                parts.append(f"{len(options['music_folders'])} music folder(s)")
        if parts:
            self.summary_lbl.setText("Will export: " + ", ".join(parts))
            self.export_btn.setEnabled(True)
        else:
            self.summary_lbl.setText("Nothing selected to export.")
            self.export_btn.setEnabled(False)

    def _choose_export_file(self):
        options = self.build_options(require_selection=True)
        if options is None:
            return
        default_name = f"yt-msd-export-{time.strftime('%Y-%m-%d')}.zip"
        start_dir = getattr(self.main_app, 'download_path', '') or os.path.expanduser("~")
        target, _ = QFileDialog.getSaveFileName(self, "Save Export Package",
                                               os.path.join(start_dir, default_name),
                                               "yt-msd Package (*.zip)")
        if not target:
            return
        if not target.lower().endswith(".zip"):
            target += ".zip"
        options['zip_path'] = target
        self.main_app.start_export(options)
        self.accept()
