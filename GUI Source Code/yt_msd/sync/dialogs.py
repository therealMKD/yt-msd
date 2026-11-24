# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.sync.dialogs).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
import os
import sys
import threading
from pathlib import Path
import time
import socket
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QComboBox, QScrollArea, QFileDialog, QMessageBox, QDialog, QMenu, QFrame, QSpinBox, QInputDialog, QCheckBox, QListWidget, QListWidgetItem
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from yt_msd.sync.client import ClientSyncThread, deletions_were_declined, make_delete_confirm_cb
from yt_msd.sync.config import (DEFAULT_DELETE_CONFIRM_LIMIT, DEFAULT_HOST_CHAIN_VISIBLE,
                                DELETE_CONFIRM_LIMIT_MAX, SyncConfigManager, delete_confirm_limit,
                                host_chain_is_visible, is_client_chain_paused)
from yt_msd.sync.discovery import HostScanThread, send_lan_update_notification
from yt_msd.sync.lan import SYNC_PORT_START, get_current_wifi_ssid, get_local_ip
from yt_msd.sync.removable import RemovableInitThread
from yt_msd.sync.tags import SYNC_TAG_FILENAME, make_removable_chain_id
from yt_msd.sync.transfer import filter_audio_files



class CreateHostChainDialog(QDialog):
    """Dialog to create a new hosted Sync Chain."""
    def __init__(self, parent_window, config_manager: SyncConfigManager):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.config_manager = config_manager
        self.setWindowTitle("Create Sync Chain (Host)")
        self.setFixedSize(520, 410)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title_lbl = QLabel("CREATE A NEW SYNC CHAIN (HOST)")
        title_lbl.setFont(QFont("Segoe UI Semibold", 11))
        layout.addWidget(title_lbl)

        desc = QLabel("You will host this folder on your local network. Other yt-msd clients with your sync code can connect and sync audio files.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(desc)

        layout.addWidget(QLabel("Playlist / Sync Chain Name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Rock Classics")
        layout.addWidget(self.name_edit)

        layout.addWidget(QLabel("Master Audio Folder to Sync:"))
        folder_h = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Select folder...")
        self.folder_edit.textChanged.connect(self._update_file_count)
        folder_h.addWidget(self.folder_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.setToolTip("Browse for the master audio folder to sync")
        browse_btn.clicked.connect(self._browse_folder)
        folder_h.addWidget(browse_btn)
        layout.addLayout(folder_h)

        self.count_lbl = QLabel("0 audio files detected (subfolders/zips ignored)")
        self.count_lbl.setStyleSheet("color: #3B8ED0; font-size: 11px;")
        layout.addWidget(self.count_lbl)

        options_h = QHBoxLayout()
        options_h.addWidget(QLabel("Sync Code (4-digit):"))
        self.code_edit = QLineEdit(self.config_manager.generate_unique_sync_code())
        self.code_edit.setFixedWidth(70)
        options_h.addWidget(self.code_edit)

        options_h.addSpacing(20)
        options_h.addWidget(QLabel("Change Notify Delay:"))
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(1, 60)
        self.delay_spin.setValue(5)
        self.delay_spin.setSuffix(" min")
        options_h.addWidget(self.delay_spin)
        options_h.addStretch()
        layout.addLayout(options_h)

        # Whether this chain tells the network it exists. Visible is the default, for the same reason
        # it is the default for a chain saved by an older build: a hosted chain's code has been
        # broadcast on the LAN by the beacon since 3.0, so a chain nobody can find is a change in
        # behaviour the user did not ask for - and a chain nobody can find is a chain nobody joins.
        self.visible_check = QCheckBox("Visible chain - clients on my network can find it without the code")
        self.visible_check.setChecked(DEFAULT_HOST_CHAIN_VISIBLE)
        self.visible_check.setToolTip("Unset means this chain names itself in nothing and answers no search. A client can still sync it, but only one that was already given the 4-digit sync code.")
        layout.addWidget(self.visible_check)

        layout.addStretch()

        btn_h = QHBoxLayout()
        btn_h.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_h.addWidget(cancel_btn)

        create_btn = QPushButton("Create Chain")
        create_btn.setToolTip("Create the sync chain and start hosting")
        create_btn.clicked.connect(self._create_chain)
        btn_h.addWidget(create_btn)
        layout.addLayout(btn_h)

    def _browse_folder(self):
        f = QFileDialog.getExistingDirectory(self, "Select Master Audio Folder", self.folder_edit.text() or "")
        if f:
            self.folder_edit.setText(f)
            if not self.name_edit.text().strip():
                self.name_edit.setText(Path(f).name)

    def _update_file_count(self, path_str: str):
        p = Path(path_str)
        if p.is_dir():
            files = filter_audio_files(p)
            self.count_lbl.setText(f"✔ {len(files)} audio files detected (non-audio & subfolders ignored)")
            self.count_lbl.setStyleSheet("color: #1abd33; font-size: 11px;")
        else:
            self.count_lbl.setText("Folder does not exist or is invalid")
            self.count_lbl.setStyleSheet("color: #E31E24; font-size: 11px;")

    def _create_chain(self):
        name = self.name_edit.text().strip()
        folder = self.folder_edit.text().strip()
        code = self.code_edit.text().strip()
        delay = self.delay_spin.value()

        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a name for this sync chain.")
            return
        if not folder or not Path(folder).is_dir():
            QMessageBox.warning(self, "Invalid Folder", "Please select a valid folder containing your audio files.")
            return
        if not code.isdigit() or len(code) != 4:
            QMessageBox.warning(self, "Invalid Code", "Sync code must be a 4-digit number (e.g. 1002).")
            return

        self.config_manager.add_hosted_chain(name, folder, code, notify_delay_mins=delay,
                                             visible=self.visible_check.isChecked())
        self.accept()



class ConnectClientChainDialog(QDialog):
    """Dialog to connect to a remote Host's Sync Chain."""
    def __init__(self, parent_window, config_manager: SyncConfigManager):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.config_manager = config_manager
        self.setWindowTitle("Connect to Sync Chain (Client)")
        self.setFixedSize(520, 640)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title_lbl = QLabel("CONNECT TO A REMOTE SYNC CHAIN")
        title_lbl.setFont(QFont("Segoe UI Semibold", 11))
        layout.addWidget(title_lbl)

        desc = QLabel("Enter the Host PC's IP address and 4-digit Sync Code to subscribe to their sync chain.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(desc)

        layout.addWidget(QLabel("Host Computer IP Address:"))
        self.ip_edit = QLineEdit()
        self.ip_edit.setPlaceholderText("e.g. 192.168.1.50")
        layout.addWidget(self.ip_edit)

        # ... or none of the above. A search asks this machine's own networks whether anything on
        # them is hosting a chain, which is the whole point of it: the address is the part nobody
        # knows off by heart, and a visible chain hands over its code with its name.
        scan_row = QHBoxLayout()
        self.scan_btn = QPushButton("Find Hosts On My Network")
        self.scan_btn.setFixedWidth(185)
        self.scan_btn.setToolTip("Search this network for yt-msd hosts. A visible chain is named with its code, so nothing has to be typed. A private chain answers only if its code is typed here first.")
        scan_row.addWidget(self.scan_btn)
        self.scan_status = QLabel("Nothing searched yet.")
        self.scan_status.setStyleSheet("color: #888; font-size: 11px;")
        scan_row.addWidget(self.scan_status, 1)
        layout.addLayout(scan_row)

        layout.addWidget(QLabel("4-Digit Sync Code:"))
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("e.g. 1002")
        self.code_edit.setFixedWidth(100)
        layout.addWidget(self.code_edit)

        self.host_list_label = QLabel("Hosts found:")
        self.host_list_label.setStyleSheet("color: #3B8ED0; font-size: 11px;")
        self.host_list_label.setVisible(False)
        layout.addWidget(self.host_list_label)
        self.host_list = QListWidget()
        self.host_list.setMaximumHeight(112)
        self.host_list.setVisible(False)
        self.host_list.setToolTip("Pick one and its address, its code and its chain name go in. A private chain only answers a search that already named its code.")
        self.host_list.currentItemChanged.connect(self._apply_scan_choice)
        layout.addWidget(self.host_list)

        layout.addWidget(QLabel("Local Base Folder where files should be synced:"))
        folder_h = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Base folder (e.g. C:\\Music)...")
        folder_h.addWidget(self.folder_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.setToolTip("Browse for the local folder to sync into")
        browse_btn.clicked.connect(self._browse_base_folder)
        folder_h.addWidget(browse_btn)
        layout.addLayout(folder_h)

        layout.addWidget(QLabel("Playlist / Subfolder Name:"))
        self.playlist_name_edit = QLineEdit()
        self.playlist_name_edit.setPlaceholderText("e.g. Rock Classics")
        layout.addWidget(self.playlist_name_edit)

        layout.addWidget(QLabel("Sync / Deletion Mode:"))
        self.del_mode_combo = QComboBox()
        self.del_mode_combo.addItem("Mirror Mode (Default: Sync all files, update edits & delete removed files)", "mirror")
        self.del_mode_combo.addItem("Additive Mode (Only download new/updated files, keep local files)", "additive")
        layout.addWidget(self.del_mode_combo)

        # How many files this chain may delete before it asks. It lives beside the mode choice
        # because it is a rule about deleting, and the row is hidden for Additive - a chain that
        # keeps every file it has never has anything to be asked about.
        self.delete_limit_row = QWidget()
        limit_row = QHBoxLayout(self.delete_limit_row)
        limit_row.setContentsMargins(0, 0, 0, 0)
        limit_row.setSpacing(8)
        limit_row.addWidget(QLabel("Ask before deleting more than:"))
        self.delete_limit_spin = QSpinBox()
        self.delete_limit_spin.setRange(0, DELETE_CONFIRM_LIMIT_MAX)
        self.delete_limit_spin.setValue(DEFAULT_DELETE_CONFIRM_LIMIT)
        self.delete_limit_spin.setSuffix(" files")
        self.delete_limit_spin.setFixedWidth(110)
        self.delete_limit_spin.setToolTip("Number of files this chain may delete on its own before it asks you first. 0 means any number - it will never ask.")
        limit_row.addWidget(self.delete_limit_spin)
        limit_hint = QLabel("(0 = never ask)")
        limit_hint.setStyleSheet("color: #888; font-size: 11px;")
        limit_row.addWidget(limit_hint)
        limit_row.addStretch()
        layout.addWidget(self.delete_limit_row)
        self.del_mode_combo.currentIndexChanged.connect(self._sync_delete_limit_row)
        self._sync_delete_limit_row()

        layout.addStretch()

        btn_h = QHBoxLayout()
        btn_h.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_h.addWidget(cancel_btn)

        connect_btn = QPushButton("Connect & Join")
        connect_btn.setToolTip("Connect to the remote sync chain")
        connect_btn.clicked.connect(self._connect_chain)
        btn_h.addWidget(connect_btn)
        layout.addLayout(btn_h)

        # The search this window can start, and what it found. A host takes the first free port from
        # 63350 upwards, so the port a chain was found answering on has to be kept: a chain joined
        # to a host sitting on 63351 that was saved with 63350 would be looking for it on a port
        # nothing is listening on. `_scanned_ip` is what ties that port to the address it came from,
        # so an address typed in afterwards is not quietly given someone else's port.
        self._scan_thread = None
        self._scan_results = []
        self._scanned_port = SYNC_PORT_START
        self._scanned_ip = ''
        self.scan_btn.clicked.connect(self._start_scan)

    def _start_scan(self):
        """Search this machine's networks for hosts, on its own thread, off the GUI thread."""
        self._stop_scan()
        self._scan_results = []
        self.host_list.clear()
        self.host_list.setVisible(False)
        self.host_list_label.setVisible(False)
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Searching...")
        self.scan_status.setStyleSheet("color: #888; font-size: 11px;")
        self.scan_status.setText("Asking this network where a chain is being hosted...")
        # The code typed here travels with the search, because that is how a private chain is found:
        # it answers a search that already named it, and nothing else.
        thread = HostScanThread(requested_code=self.code_edit.text().strip(), parent=self)
        thread.host_found.connect(self._on_scan_host)
        thread.scan_finished.connect(self._on_scan_done)
        self._scan_thread = thread
        thread.start()

    def _stop_scan(self):
        """Let go of a search still running, and wait for it to notice.

        The thread is parented to this window and a QThread destroyed while running takes the
        program with it, so a window that is closing - by Connect, by Cancel, or by its close box -
        asks the search to stop first. The scan checks for that between addresses, so this is a
        short wait and not a wait for the whole budget.
        """
        thread = self._scan_thread
        if thread is None:
            return
        self._scan_thread = None
        try:
            thread.requestInterruption()
            thread.wait(3000)
        except RuntimeError:
            pass

    def accept(self):
        self._stop_scan()
        super().accept()

    def reject(self):
        self._stop_scan()
        super().reject()

    def _scan_line(self, entry: dict) -> str:
        """How one found host is written on the list."""
        if not entry.get('sync_code'):
            # The machine answered but would not name a chain: a yt-msd from before a search could
            # be answered. It will still take a client that authenticates, so what it gives is the
            # address, and the code is the part the user has to bring.
            return f"{entry['ip']}:{entry['port']}  -  yt-msd host (older version) - type its sync code"
        found_as = "visible" if entry.get('visible') else "private"
        return f"{entry['ip']}:{entry['port']}  -  {entry['chain_name']}  (code {entry['sync_code']}, {found_as})"

    def _on_scan_host(self, entry: dict):
        item = QListWidgetItem(self._scan_line(entry))
        item.setData(Qt.UserRole, entry)
        self.host_list.addItem(item)
        self._scan_results.append(entry)
        self.host_list.setVisible(True)
        self.host_list_label.setVisible(True)
        # The first host found is picked on its own. The point of a search is that nothing has to be
        # chosen, and a second host on the list is the rare case rather than the one to design for.
        if len(self._scan_results) == 1:
            self.host_list.setCurrentItem(item)

    def _on_scan_done(self, count: int, how: str):
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("Find Hosts On My Network")
        if count:
            self.scan_status.setStyleSheet("color: #1abd33; font-size: 11px;")
            self.scan_status.setText(f"{count} host(s) found ({how}).")
        else:
            self.scan_status.setStyleSheet("color: #FF8C00; font-size: 11px;")
            self.scan_status.setText("No host found. Is yt-msd running on the other PC, and is its chain Visible?")

    def _apply_scan_choice(self, current, previous=None):
        """Put a picked host into the boxes a chain is made from."""
        entry = current.data(Qt.UserRole) if current is not None else None
        if not isinstance(entry, dict):
            return
        self.ip_edit.setText(entry['ip'])
        self._scanned_ip = entry['ip']
        self._scanned_port = int(entry['port'])
        if entry.get('sync_code'):
            self.code_edit.setText(entry['sync_code'])
        if entry.get('chain_name') and not self.playlist_name_edit.text().strip():
            self.playlist_name_edit.setText(entry['chain_name'])
        self.scan_status.setStyleSheet("color: #1abd33; font-size: 11px;")
        self.scan_status.setText(f"Picked {entry['ip']}:{entry['port']}" +
                                 (f", code {entry['sync_code']}" if entry.get('sync_code')
                                  else " - type this host's sync code"))

    def _browse_base_folder(self):
        f = QFileDialog.getExistingDirectory(self, "Select Base Music Directory", self.folder_edit.text() or "")
        if f:
            self.folder_edit.setText(f)

    def _sync_delete_limit_row(self):
        """Show the deletion limit only for a Mirror chain.

        The limit is a rule about deleting files this PC no longer has on its host's list. An
        Additive chain keeps every file it holds whatever the host does, so there is nothing for it
        to be asked about and no number for it to be given.
        """
        is_mirror = self.del_mode_combo.currentData() == 'mirror'
        self.delete_limit_row.setVisible(is_mirror)
        self.delete_limit_spin.setEnabled(is_mirror)

    def _connect_chain(self):
        ip = self.ip_edit.text().strip()
        code = self.code_edit.text().strip()
        base_folder = self.folder_edit.text().strip()
        subfolder = self.playlist_name_edit.text().strip()
        del_mode = self.del_mode_combo.currentData()

        if not ip:
            QMessageBox.warning(self, "Missing IP", "Please enter the Host computer IP address.")
            return
        if not code.isdigit() or len(code) != 4:
            QMessageBox.warning(self, "Invalid Code", "Sync code must be a 4-digit number (e.g. 1002).")
            return
        if not base_folder or not Path(base_folder).exists():
            QMessageBox.warning(self, "Invalid Folder", "Please select a valid base folder on your computer.")
            return
        if not subfolder:
            QMessageBox.warning(self, "Missing Name", "Please enter a name for the playlist folder.")
            return

        full_dest_path = str(Path(base_folder) / subfolder)
        # The port travels with the chain because a host takes the first free port from 63350 upward:
        # a chain found answering on 63351 has to be looked for there and not on the port its name
        # suggests. Only the port belonging to the address being saved is used, so an address typed
        # in after a search is not given the port of the address the search picked.
        host_port = (self._scanned_port if self._scanned_ip == ip else SYNC_PORT_START)
        self.config_manager.add_client_chain(
            name=subfolder,
            folder_path=full_dest_path,
            sync_code=code,
            host_ip=ip,
            host_port=host_port,
            deletion_mode=del_mode,
            delete_confirm_limit=self.delete_limit_spin.value()
        )
        self.accept()



class ConnectRemovableMediaDialog(QDialog):
    """Dialog to configure and sync a chain onto a Removable Storage Drive (USB/SD Card/MP3 Player)."""
    def __init__(self, parent_window, config_manager: SyncConfigManager):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.config_manager = config_manager
        self.setWindowTitle("Connect Removable Media (USB / SD Card / MP3 Player)")
        self.setFixedSize(540, 440)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title_lbl = QLabel("CONNECT REMOVABLE MEDIA SYNC")
        title_lbl.setFont(QFont("Segoe UI Semibold", 11))
        layout.addWidget(title_lbl)

        desc = QLabel("Tag and synchronize a playlist to a removable USB flash drive, SD card, or portable MP3 player. A TAG.yaml file will be placed in the folder to identify it.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(desc)

        # 1. Select Sync Chain
        layout.addWidget(QLabel("Select Sync Chain to Mirror:"))
        self.chain_combo = QComboBox()
        
        all_chains = []
        for hc in self.config_manager.hosted_chains:
            all_chains.append(("Host", hc))
        for cc in self.config_manager.client_chains:
            all_chains.append(("Client", cc))

        if not all_chains:
            self.chain_combo.addItem("No active chains (Create or join a chain first)", None)
            self.chain_combo.setEnabled(False)
        else:
            for c_type, c in all_chains:
                label = f"[{c_type}] {c.get('name', 'Chain')} (Sync Code: {c.get('sync_code')})"
                self.chain_combo.addItem(label, (c_type, c))

        layout.addWidget(self.chain_combo)

        # 2. Target Removable Drive / Folder
        layout.addWidget(QLabel("Target Removable Drive or Folder:"))
        folder_h = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Select drive or folder on USB/SD card (e.g. E:\\Music)...")
        folder_h.addWidget(self.folder_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.setToolTip("Browse for the removable drive or folder")
        browse_btn.clicked.connect(self._browse_folder)
        folder_h.addWidget(browse_btn)
        layout.addLayout(folder_h)

        # Detected removable drives quick buttons. The list comes from the
        # background drive probe's cache: probing all 26 letters here would stat
        # every root on the GUI thread, and a busy MP3 player can sit on one of
        # those calls for seconds.
        detected_drives = []
        app = getattr(self.parent_window, 'parent_app', None)
        cached_drives = getattr(app, 'known_connected_drives', None) if app is not None else None
        if cached_drives:
            detected_drives = sorted(d for d in cached_drives if d.upper() != "C:\\")
        elif sys.platform == 'win32':
            import string
            for letter in string.ascii_uppercase:
                d = f"{letter}:\\"
                if d.upper() != "C:\\" and os.path.exists(d):
                    detected_drives.append(d)

        if detected_drives:
            quick_h = QHBoxLayout()
            quick_lbl = QLabel("Detected Drives:")
            quick_lbl.setStyleSheet("color: #888; font-size: 11px;")
            quick_h.addWidget(quick_lbl)
            for d in detected_drives:
                d_btn = QPushButton(d)
                d_btn.setFixedHeight(22)
                d_btn.setToolTip(f"Use drive {d}")
                d_btn.setStyleSheet("font-size: 11px; padding: 2px 6px;")
                d_btn.clicked.connect(lambda chk=False, drv=d: self._set_drive(drv))
                quick_h.addWidget(d_btn)
            quick_h.addStretch()
            layout.addLayout(quick_h)

        # Subfolder name
        layout.addWidget(QLabel("Playlist / Subfolder Name on Drive:"))
        self.subfolder_edit = QLineEdit()
        self._update_subfolder_placeholder()
        self.chain_combo.currentIndexChanged.connect(self._update_subfolder_placeholder)
        layout.addWidget(self.subfolder_edit)

        # Deletion mode
        layout.addWidget(QLabel("Sync Style:"))
        self.del_mode_combo = QComboBox()
        self.del_mode_combo.addItem("Mirror (Sync all files, delete removed files)", "mirror")
        self.del_mode_combo.addItem("Additive (Only download new/updated, keep existing files)", "additive")
        layout.addWidget(self.del_mode_combo)

        layout.addStretch()

        btn_h = QHBoxLayout()
        btn_h.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_h.addWidget(cancel_btn)

        self.connect_btn = QPushButton("Connect & Initialize Drive")
        self.connect_btn.setToolTip("Connect and initialize the removable drive")
        self.connect_btn.clicked.connect(self._connect_removable)
        btn_h.addWidget(self.connect_btn)
        layout.addLayout(btn_h)

    def _set_drive(self, drive_str: str):
        self.folder_edit.setText(drive_str)

    def _update_subfolder_placeholder(self):
        data = self.chain_combo.currentData()
        if data:
            _, chain = data
            self.subfolder_edit.setText(chain.get('name', ''))

    def _browse_folder(self):
        f = QFileDialog.getExistingDirectory(self, "Select Removable Folder / Drive", self.folder_edit.text() or "")
        if f:
            self.folder_edit.setText(f)

    def _connect_removable(self):
        data = self.chain_combo.currentData()
        if not data:
            QMessageBox.warning(self, "No Chain Selected", "Please create or connect to a sync chain before adding removable media.")
            return

        c_type, chain = data
        base_dir = self.folder_edit.text().strip()
        subfolder = self.subfolder_edit.text().strip()
        del_mode = self.del_mode_combo.currentData()
        sync_code = str(chain.get('sync_code', ''))

        if not base_dir:
            QMessageBox.warning(self, "Missing Folder", "Please select a target folder or drive on the removable device.")
            return

        dest_path = Path(base_dir)
        if subfolder:
            dest_path = dest_path / subfolder

        name = subfolder or chain.get('name', 'Removable Drive')
        parent_folder = chain.get('folder_path', '')
        sync_code = str(chain.get('sync_code', ''))
        chain_name = chain.get('name', name)

        app = getattr(self.parent_window, 'parent_app', None)
        if app is None:
            app = self.parent_window  # SyncManagerDialog -> parent_app

        rc = {
            'id': make_removable_chain_id(sync_code, str(dest_path)),
            'sync_code': sync_code,
            'name': chain_name,
            'folder_path': str(dest_path),
            'deletion_mode': del_mode,
            'last_synced': '',
            'status': 'Ready',
            'drive_root': str(Path(base_dir).anchor),
        }

        # Creating the folder and writing TAG.yaml means talking to the drive.
        # That happens on a worker thread so a slow player cannot freeze this
        # dialog - or the rest of the app - while it thinks about it.
        self._pending_rc = rc
        self._pending_app = app
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("Initializing drive...")

        thread = RemovableInitThread(dest_path, sync_code, chain_name, del_mode, c_type, parent_folder)
        self._init_thread = thread
        thread.done_signal.connect(self._on_drive_initialized)
        thread.start()

    def _on_drive_initialized(self, ok: bool, msg: str, dest_path: str):
        if not ok:
            self.connect_btn.setEnabled(True)
            self.connect_btn.setText("Connect & Initialize Drive")
            QMessageBox.warning(self, "Invalid Path", msg)
            return

        rc = self._pending_rc
        app = self._pending_app
        # Register in the runtime active drives dict and immediately sync
        with app._runtime_state_lock:
            app.active_removable_drives[str(rc['folder_path'])] = rc
            if hasattr(app, 'mount_state'):
                app.mount_state[str(rc['folder_path'])] = True
        self.accept()
        if hasattr(app, '_auto_sync_removable_chain'):
            QTimer.singleShot(50, lambda r=rc: app._auto_sync_removable_chain(r))



class SyncManagerDialog(QDialog):
    """Main Sync Chains Management Dialog with Host, Client, and Removable Drive cards and live transfer tracking."""
    def __init__(self, parent_app):
        super().__init__(parent_app)
        self.parent_app = parent_app
        self.config_manager: SyncConfigManager = parent_app.sync_config_manager
        self.setWindowTitle("Sync Chains Manager - Local Network Playlist Sync")
        self.resize(920, 620)

        # Check Windows Firewall rule every time the sync window opens
        self._check_firewall_rule()

        # Reference the app-level sync_threads dict (persists across dialog open/close)
        self.sync_threads = parent_app.sync_threads

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(12)

        top_bar = QHBoxLayout()
        local_ip = get_local_ip()
        self.ip_badge = QLabel(f"Your Local IP: <b>{local_ip}</b>")
        self.ip_badge.setStyleSheet("background: rgba(59, 142, 208, 0.15); border: 1px solid #3B8ED0; padding: 6px 12px; border-radius: 4px; font-size: 12px;")
        top_bar.addWidget(self.ip_badge)

        copy_ip_btn = QPushButton("Copy IP")
        copy_ip_btn.setFixedWidth(75)
        copy_ip_btn.setToolTip("Copy your local IP address")
        copy_ip_btn.clicked.connect(lambda: QApplication.clipboard().setText(local_ip))
        top_bar.addWidget(copy_ip_btn)

        top_bar.addStretch()

        create_btn = QPushButton("Create Chain (Host)")
        create_btn.setToolTip("Host a folder as a sync chain")
        create_btn.clicked.connect(self._open_create_dialog)
        top_bar.addWidget(create_btn)

        connect_btn = QPushButton("Connect Chain (Client)")
        connect_btn.setToolTip("Connect to an existing sync chain")
        connect_btn.clicked.connect(self._open_connect_dialog)
        top_bar.addWidget(connect_btn)

        removable_btn = QPushButton("Connect Removable Drive (USB)")
        removable_btn.setToolTip("Sync a playlist to a USB / SD drive")
        removable_btn.clicked.connect(self._open_removable_dialog)
        top_bar.addWidget(removable_btn)

        sync_all_btn = QPushButton("Force Sync All")
        sync_all_btn.setToolTip("Force a sync of all chains now")
        sync_all_btn.clicked.connect(self._force_sync_all)
        top_bar.addWidget(sync_all_btn)

        main_layout.addLayout(top_bar)

        settings_bar = QHBoxLayout()
        settings_bar.addWidget(QLabel("Client Auto-Sync Frequency (minutes):"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 1440)
        self.interval_spin.setValue(self.config_manager.settings.get('auto_sync_interval_mins', 30))
        self.interval_spin.setSuffix(" min")
        self.interval_spin.valueChanged.connect(self._update_interval)
        settings_bar.addWidget(self.interval_spin)

        settings_bar.addSpacing(20)
        self.host_port_lbl = QLabel(f"Host Server: Port {getattr(parent_app.sync_host_server, 'active_port', 'Offline')}")
        self.host_port_lbl.setStyleSheet("color: #888; font-size: 11px;")
        settings_bar.addWidget(self.host_port_lbl)

        settings_bar.addStretch()
        main_layout.addLayout(settings_bar)

        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setObjectName("scrollContent")
        self.cards_scroll.setAttribute(Qt.WA_StyledBackground, True)

        self.cards_container = QWidget()
        self.cards_container.setObjectName("scrollContent")
        self.cards_container.setAttribute(Qt.WA_StyledBackground, True)
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(6, 6, 6, 6)
        self.cards_layout.setSpacing(10)
        self.cards_scroll.setWidget(self.cards_container)
        main_layout.addWidget(self.cards_scroll, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(100)
        close_btn.setToolTip("Close this window")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        main_layout.addLayout(footer)

        self.refresh_cards()

    def _check_firewall_rule(self):
        """Binds to sync ports and triggers the Windows Firewall permission alert if no rule exists yet."""
        if sys.platform != 'win32':
            return
        def _bg_firewall():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('0.0.0.0', 0))
                s.listen(1)
                port = s.getsockname()[1]
                try:
                    c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    c.settimeout(0.2)
                    c.connect(('127.0.0.1', port))
                    c.close()
                except Exception:
                    pass
                s.close()

                s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s2.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s2.bind(('0.0.0.0', 0))
                port2 = s2.getsockname()[1]
                try:
                    s2.sendto(b'probe', ('127.0.0.1', port2))
                except Exception:
                    pass
                s2.close()
            except Exception:
                pass
        threading.Thread(target=_bg_firewall, daemon=True).start()

    def showEvent(self, event):
        super().showEvent(event)
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        # Hide instead of closing so thread references and state survive across open/close cycles
        event.ignore()
        self.hide()
        if self.parent_app:
            self.parent_app.raise_()
            self.parent_app.activateWindow()

    def accept(self):
        # Hide instead of accepting (would destroy the dialog with exec())
        self.hide()
        if self.parent_app:
            self.parent_app.raise_()
            self.parent_app.activateWindow()

    def reject(self):
        # Hide instead of rejecting
        self.hide()
        if self.parent_app:
            self.parent_app.raise_()
            self.parent_app.activateWindow()

    def _update_interval(self, val: int):
        self.config_manager.settings['auto_sync_interval_mins'] = val
        self.config_manager.save()
        if hasattr(self.parent_app, '_update_sync_timer'):
            self.parent_app._update_sync_timer()

    def _open_create_dialog(self):
        dlg = CreateHostChainDialog(self, self.config_manager)
        if dlg.exec():
            self.config_manager.save()
            self.parent_app.refresh_sync_watchers()
            self.refresh_cards()

    def _open_connect_dialog(self):
        dlg = ConnectClientChainDialog(self, self.config_manager)
        if dlg.exec():
            self.config_manager.save()
            self.refresh_cards()
            if self.config_manager.client_chains:
                self._sync_single_client_chain(self.config_manager.client_chains[-1])

    def showEvent(self, event):
        super().showEvent(event)
        # Immediately scan drives so cards appear as soon as the dialog opens
        if hasattr(self.parent_app, '_check_removable_drives_change'):
            self.parent_app._check_removable_drives_change()
        QTimer.singleShot(300, self.refresh_cards)

    def _open_removable_dialog(self):
        dlg = ConnectRemovableMediaDialog(self, self.config_manager)
        if dlg.exec():
            # Defer refresh to ensure dialog destruction is completed
            QTimer.singleShot(50, self.refresh_cards)

    def _cards_signature(self) -> tuple:
        """Cheap, I/O-free description of everything the cards currently show."""
        mount_state = getattr(self.parent_app, 'mount_state', {})
        counts = getattr(self.parent_app, 'chain_track_counts', {}) or {}
        hosted = tuple(
            (hc.get('id'), hc.get('name'), str(hc.get('sync_code', '')), hc.get('folder_path'),
             counts.get(hc.get('id')), host_chain_is_visible(hc))
            for hc in self.config_manager.hosted_chains
        )
        clients = tuple(
            (cc.get('id'), cc.get('name'), str(cc.get('sync_code', '')), cc.get('last_known_host_ip', ''),
             bool(is_client_chain_paused(cc)[0]), cc.get('wifi_ssid', ''), cc.get('status', ''))
            # delete_confirm_limit is left out on purpose. A card carries a live spin box for it
            # now, and a signature that changed every time a keystroke landed in that box would
            # rebuild the card - and the box - out from under the user mid-edit.
            for cc in self.config_manager.client_chains
        )
        removables = tuple(
            (rc.get('id'), rc.get('name'), rc.get('folder_path'), rc.get('status', ''),
             str(rc.get('last_synced', '')), bool(mount_state.get(rc.get('folder_path'), True)))
            for rc in getattr(self.parent_app, 'active_removable_drives', {}).values()
        )
        return (hosted, clients, removables)

    def _open_folder(self, folder_str: str):
        """Hand the path straight to the shell instead of stat()ing a drive that
        may be busy with a sync right now."""
        if not folder_str:
            return
        try:
            os.startfile(folder_str)
        except Exception:
            pass

    def refresh_cards(self, force: bool = False):
        # The background drive probe runs every few seconds. Tearing down and
        # rebuilding every card on each pass is pure churn, so skip the rebuild
        # whenever nothing about the chains has actually changed.
        signature = self._cards_signature()
        if (not force and self.cards_layout.count()
                and signature == getattr(self, '_cards_signature_state', None)):
            self._restore_in_progress_labels()
            return
        self._cards_signature_state = signature

        # Preserve scroll position so rescans don't jump back to the top
        scroll_bar = self.cards_scroll.verticalScrollBar()
        saved_scroll = scroll_bar.value() if scroll_bar else 0

        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                w = item.widget()
                w.setParent(None)
                w.deleteLater()

        hosted = self.config_manager.hosted_chains
        clients = self.config_manager.client_chains
        removables = list(getattr(self.parent_app, 'active_removable_drives', {}).values())

        if not hosted and not clients and not removables:
            empty_lbl = QLabel("No active Sync Chains. Click 'Create Chain' to host a folder, 'Connect Chain' to join an existing one, or plug in a USB drive tagged with TAG.yaml.")
            empty_lbl.setAlignment(Qt.AlignCenter)
            empty_lbl.setStyleSheet("color: #888; padding: 40px; font-size: 13px;")
            self.cards_layout.addWidget(empty_lbl)
            self.cards_layout.addStretch()
            self.cards_container.adjustSize()
            self.cards_container.update()
            return

        if hosted:
            sec_lbl = QLabel("HOSTED SYNC CHAINS (This computer is sharing)")
            sec_lbl.setFont(QFont("Segoe UI Semibold", 10))
            sec_lbl.setStyleSheet("color: #3B8ED0; margin-top: 6px;")
            self.cards_layout.addWidget(sec_lbl)

            for hc in hosted:
                card = self._build_host_card(hc)
                self.cards_layout.addWidget(card)

        if clients:
            sec_lbl2 = QLabel("CLIENT SYNC CHAINS (Subscribed to remote hosts)")
            sec_lbl2.setFont(QFont("Segoe UI Semibold", 10))
            sec_lbl2.setStyleSheet("color: #1abd33; margin-top: 14px;")
            self.cards_layout.addWidget(sec_lbl2)

            for cc in clients:
                card = self._build_client_card(cc)
                self.cards_layout.addWidget(card)

        if removables:
            sec_lbl3 = QLabel("REMOVABLE MEDIA SYNC (USB Flash Drives / SD Cards / MP3 Players)")
            sec_lbl3.setFont(QFont("Segoe UI Semibold", 10))
            sec_lbl3.setStyleSheet("color: #9B59B6; margin-top: 14px;")
            self.cards_layout.addWidget(sec_lbl3)

            for rc in removables:
                card = self._build_removable_card(rc)
                self.cards_layout.addWidget(card)

        self.cards_layout.addStretch()
        # Immediately restore live status/progress for any in-progress syncs
        self._restore_in_progress_labels()
        self.cards_container.adjustSize()
        self.cards_container.update()
        # Restore scroll position after layout rebuild
        QTimer.singleShot(0, lambda: self.cards_scroll.verticalScrollBar().setValue(saved_scroll))

    def _build_host_card(self, hc: dict) -> QWidget:
        card = QFrame()
        card.setProperty("chain_id", hc.get('id'))
        card.setProperty("sync_code", str(hc.get('sync_code', '')))
        card.setStyleSheet("background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; padding: 8px;")
        l = QVBoxLayout(card)
        l.setContentsMargins(10, 8, 10, 8)
        l.setSpacing(6)

        header = QHBoxLayout()
        badge = QLabel("HOST")
        badge.setStyleSheet("background: #3B8ED0; color: white; padding: 2px 6px; border-radius: 3px; font-weight: bold; font-size: 10px;")
        header.addWidget(badge)

        name_lbl = QLabel(f"<b>{hc.get('name', 'Audio Playlist')}</b>")
        name_lbl.setFont(QFont("Segoe UI", 12))
        header.addWidget(name_lbl)

        header.addSpacing(10)
        code_lbl = QLabel(f"Sync Code: <b style='color: #FF8C00;'>{hc.get('sync_code')}</b>")
        header.addWidget(code_lbl)

        # Whether this chain tells the network it exists. It is asked once when the chain is made and
        # changed here afterwards, because a chain saved before the choice existed has to be made
        # private without deleting and re-making it.
        is_visible = host_chain_is_visible(hc)
        vis_badge = QLabel("Visible" if is_visible else "Private")
        vis_badge.setStyleSheet("background: " + ("#1abd33" if is_visible else "#FF8C00") +
                                "; color: white; padding: 2px 6px; border-radius: 3px; font-weight: bold; font-size: 10px;")
        header.addWidget(vis_badge)

        header.addStretch()

        vis_btn = QPushButton("Make Private" if is_visible else "Make Visible")
        vis_btn.setFixedWidth(110)
        vis_btn.setToolTip("A visible chain names itself to any client searching this network, code included. A private one answers no search at all, and only a client that was already given the code can find it.")
        vis_btn.clicked.connect(lambda chk=False, cid=hc.get('id'), want=not is_visible: self._set_chain_visibility(cid, want))
        header.addWidget(vis_btn)

        copy_code_btn = QPushButton("Copy Code")
        copy_code_btn.setFixedWidth(105)
        copy_code_btn.setToolTip("Copy the sync code")
        code_val = str(hc.get('sync_code', ''))
        copy_code_btn.clicked.connect(lambda chk=False, c=code_val: QApplication.clipboard().setText(c))
        header.addWidget(copy_code_btn)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(26, 26)
        del_btn.setToolTip("Delete this hosted sync chain")
        del_btn.setStyleSheet("background: #E31E24; color: white; border: none; border-radius: 3px; font-weight: bold;")
        cid_val = hc.get('id')
        del_btn.clicked.connect(lambda chk=False, cid=cid_val: self._delete_chain(cid))
        header.addWidget(del_btn)

        l.addLayout(header)

        vis_hint = QLabel("Any yt-msd on this network can find this chain by name and connect with its code."
                          if is_visible else
                          "This chain names itself in nothing and answers no search: only a client already holding the code can reach it.")
        vis_hint.setWordWrap(True)
        vis_hint.setStyleSheet("color: #888; font-size: 11px;")
        l.addWidget(vis_hint)

        folder_str = hc.get('folder_path', '')
        # Track counts come from the background probe's cache: counting files
        # here would scan the folder on the GUI thread.
        counts = getattr(self.parent_app, 'chain_track_counts', {}) or {}
        audio_cnt = counts.get(hc.get('id'))
        cnt_str = f" ({audio_cnt} tracks)" if audio_cnt is not None else ""

        host_activity_lbl = QLabel("Status: Ready (Serving clients)")
        host_activity_lbl.setStyleSheet("color: #888; font-size: 11px;")
        card.setProperty("host_activity_lbl", host_activity_lbl)
        l.addWidget(host_activity_lbl)

        info_h = QHBoxLayout()
        path_lbl = QLabel(f"Path: {folder_str}{cnt_str}")
        path_lbl.setStyleSheet("color: #888; font-size: 11px;")
        info_h.addWidget(path_lbl, 1)

        open_btn = QPushButton("Open Folder")
        open_btn.setToolTip("Open this folder in File Explorer")
        open_btn.setFixedWidth(115)
        open_btn.clicked.connect(lambda chk=False, f=folder_str: self._open_folder(f))
        info_h.addWidget(open_btn)

        l.addLayout(info_h)
        return card

    def _on_host_activity_received(self, sync_code: str, client_ip: str, activity: str):
        """Updates host card in UI when a client connects or downloads files."""
        for i in range(self.cards_layout.count()):
            item = self.cards_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if w.property("sync_code") == str(sync_code):
                    lbl = w.property("host_activity_lbl")
                    if lbl:
                        lbl.setText(f"Active Sync Event: {activity} ({client_ip})")
                        lbl.setStyleSheet("color: #1abd33; font-size: 11px; font-weight: bold;")
                        def _reset(_l=lbl):
                            try:
                                _l.setText("Status: Ready (Serving clients)")
                                _l.setStyleSheet("color: #888; font-size: 11px;")
                            except Exception:
                                pass
                        QTimer.singleShot(4000, _reset)

    def _build_client_card(self, cc: dict) -> QWidget:
        card = QFrame()
        cid_val = cc.get('id')
        card.setProperty("chain_id", cid_val)
        card.setStyleSheet("background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; padding: 8px;")
        l = QVBoxLayout(card)
        l.setContentsMargins(10, 8, 10, 8)
        l.setSpacing(6)

        header = QHBoxLayout()
        badge = QLabel("CLIENT")
        badge.setStyleSheet("background: #1abd33; color: white; padding: 2px 6px; border-radius: 3px; font-weight: bold; font-size: 10px;")
        header.addWidget(badge)

        name_lbl = QLabel(f"<b>{cc.get('name', 'Audio Playlist')}</b>")
        name_lbl.setFont(QFont("Segoe UI", 12))
        header.addWidget(name_lbl)

        header.addSpacing(10)
        code_lbl = QLabel(f"Code: <b style='color: #FF8C00;'>{cc.get('sync_code')}</b> | Host: {cc.get('last_known_host_ip', 'Unknown')}")
        code_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
        header.addWidget(code_lbl)

        header.addStretch()

        # Pause / Resume Sync Controls
        is_paused, pause_until = is_client_chain_paused(cc)
        if is_paused:
            resume_btn = QPushButton("Resume Sync")
            resume_btn.setToolTip("Resume syncing for this chain")
            resume_btn.setStyleSheet("background: #3B8ED0; color: white; font-size: 11px; padding: 3px 8px; border-radius: 4px;")
            resume_btn.clicked.connect(lambda chk=False, cid=cid_val: self._resume_chain_sync(cid))
            header.addWidget(resume_btn)
        else:
            pause_btn = QPushButton("Pause Sync ▾")
            pause_btn.setToolTip("Pause syncing for this chain")
            pause_btn.setStyleSheet("font-size: 11px; padding: 3px 8px;")
            pause_menu = QMenu(self)
            durations = [
                ("30 Minutes", 30 * 60),
                ("1 Hour", 1 * 3600),
                ("2 Hours", 2 * 3600),
                ("5 Hours", 5 * 3600),
                ("12 Hours", 12 * 3600),
                ("24 Hours", 24 * 3600),
                ("1 Week", 7 * 86400),
                # -1 and not 0. pause_client_chain() turns any other duration into
                # "now + duration_seconds", so 0 asked for a pause that had already expired by the
                # time the card was rebuilt: the chain carried on syncing and the card flipped
                # straight back to "Pause Sync". -1 is the sentinel both pause_client_chain() and
                # is_client_chain_paused() already treat as "paused until the user resumes it",
                # which is what this menu entry promises.
                ("Forever (Until Re-enabled)", -1)
            ]
            for label, secs in durations:
                act = pause_menu.addAction(label)
                act.triggered.connect(lambda chk=False, cid=cid_val, s=secs: self._pause_chain_sync(cid, s))
            pause_btn.setMenu(pause_menu)
            header.addWidget(pause_btn)

        # Wi-Fi SSID Auto-Sync Binding Control
        wifi_ssid = cc.get('wifi_ssid', '')
        wifi_btn = QPushButton(f"Wi-Fi: {wifi_ssid}" if wifi_ssid else "Bind Wi-Fi ▾")
        wifi_btn.setToolTip("Bind this chain to a Wi-Fi network")
        wifi_btn.setStyleSheet("font-size: 11px; padding: 3px 8px;" + (" background: rgba(59, 142, 208, 0.25);" if wifi_ssid else ""))
        wifi_menu = QMenu(self)
        # Reuse the Wi-Fi monitor's cached SSID: shelling out to netsh for every
        # card built would make the sync window crawl.
        curr_ssid = getattr(self.parent_app, 'last_wifi_ssid', None)
        if curr_ssid is None:
            curr_ssid = get_current_wifi_ssid()
        if curr_ssid:
            act_cur = wifi_menu.addAction(f"Bind to current network: '{curr_ssid}'")
            act_cur.triggered.connect(lambda chk=False, cid=cid_val, s=curr_ssid: self._bind_chain_wifi(cid, s))
        act_custom = wifi_menu.addAction("Enter Wi-Fi SSID manually...")
        act_custom.triggered.connect(lambda chk=False, cid=cid_val: self._prompt_custom_wifi(cid))
        if wifi_ssid:
            wifi_menu.addSeparator()
            act_clear = wifi_menu.addAction("Unbind Wi-Fi (Sync on any network)")
            act_clear.triggered.connect(lambda chk=False, cid=cid_val: self._bind_chain_wifi(cid, ""))
        wifi_btn.setMenu(wifi_menu)
        header.addWidget(wifi_btn)

        sync_btn = QPushButton("Sync Now")
        sync_btn.setToolTip("Sync this chain now")
        sync_btn.clicked.connect(lambda chk=False, c=cc: self._sync_single_client_chain(c))
        header.addWidget(sync_btn)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(26, 26)
        del_btn.setToolTip("Remove this client sync chain")
        del_btn.setStyleSheet("background: #E31E24; color: white; border: none; border-radius: 3px; font-weight: bold;")
        del_btn.clicked.connect(lambda chk=False, cid=cid_val: self._delete_chain(cid))
        header.addWidget(del_btn)

        l.addLayout(header)

        folder_str = cc.get('folder_path', '')
        last_sync = cc.get('last_synced', 0)
        if isinstance(last_sync, (int, float)) and last_sync > 0:
            last_sync_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_sync))
        elif isinstance(last_sync, str) and last_sync.strip():
            last_sync_str = last_sync.strip()
        else:
            last_sync_str = "Never"
        del_mode = cc.get('deletion_mode', 'mirror').capitalize()

        pause_info = ""
        if is_paused:
            if pause_until > 0:
                p_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(pause_until))
                pause_info = f"  |  <span style='color: #FF8C00; font-weight: bold;'>Paused until {p_time_str}</span>"
            else:
                pause_info = "  |  <span style='color: #FF8C00; font-weight: bold;'>Paused Forever</span>"

        wifi_info = f"  |  <span style='color: #3B8ED0;'>Wi-Fi: {wifi_ssid}</span>" if wifi_ssid else ""

        status_lbl = QLabel(f"Status: {cc.get('status', 'Idle')}  |  Last Synced: {last_sync_str}  |  Mode: {del_mode}{pause_info}{wifi_info}")
        status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        card.setProperty("status_lbl", status_lbl)
        l.addWidget(status_lbl)

        progress_lbl = QLabel("")
        progress_lbl.setStyleSheet("color: #3B8ED0; font-size: 11px;")
        card.setProperty("progress_lbl", progress_lbl)
        l.addWidget(progress_lbl)

        # The deletion guard, on the chain it applies to. An Additive chain keeps local files
        # whatever its host does, so it has nothing to be asked about and gets no box.
        if cc.get('deletion_mode', 'mirror') != 'additive':
            limit_row = QHBoxLayout()
            limit_row.setSpacing(8)
            limit_lbl = QLabel("Ask before deleting more than:")
            limit_lbl.setStyleSheet("color: #888; font-size: 11px;")
            limit_row.addWidget(limit_lbl)
            limit_spin = QSpinBox()
            limit_spin.setRange(0, DELETE_CONFIRM_LIMIT_MAX)
            limit_spin.setValue(delete_confirm_limit(cc))
            limit_spin.setSuffix(" files")
            limit_spin.setFixedWidth(110)
            limit_spin.setToolTip("Number of files this chain may delete on its own before it asks you first. 0 means any number - it will never ask.")
            limit_spin.valueChanged.connect(lambda val, cid=cid_val: self._update_delete_limit(cid, val))
            limit_row.addWidget(limit_spin)
            limit_hint = QLabel("(0 = never ask)")
            limit_hint.setStyleSheet("color: #666; font-size: 10px;")
            limit_row.addWidget(limit_hint)
            limit_row.addStretch()
            card.setProperty("delete_limit_spin", limit_spin)
            l.addLayout(limit_row)

        info_h = QHBoxLayout()
        path_lbl = QLabel(f"Path: {folder_str}")
        path_lbl.setStyleSheet("color: #888; font-size: 11px;")
        info_h.addWidget(path_lbl, 1)

        open_btn = QPushButton("Open Folder")
        open_btn.setToolTip("Open this folder in File Explorer")
        open_btn.setFixedWidth(115)
        open_btn.clicked.connect(lambda chk=False, f=folder_str: self._open_folder(f))
        info_h.addWidget(open_btn)

        l.addLayout(info_h)
        return card

    def _build_removable_card(self, rc: dict) -> QWidget:
        card = QFrame()
        cid_val = rc.get('id')
        card.setProperty("chain_id", cid_val)
        card.setStyleSheet("background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; padding: 8px;")
        l = QVBoxLayout(card)
        l.setContentsMargins(10, 8, 10, 8)
        l.setSpacing(6)

        header = QHBoxLayout()
        badge = QLabel("REMOVABLE")
        badge.setStyleSheet("background: #9B59B6; color: white; padding: 2px 6px; border-radius: 3px; font-weight: bold; font-size: 10px;")
        header.addWidget(badge)

        name_lbl = QLabel(f"<b>{rc.get('name', 'Removable Drive')}</b>")
        name_lbl.setFont(QFont("Segoe UI", 12))
        header.addWidget(name_lbl)

        header.addSpacing(10)
        code_lbl = QLabel(f"Code: <b style='color: #FF8C00;'>{rc.get('sync_code')}</b> | Style: {rc.get('deletion_mode', 'mirror').capitalize()}")
        code_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
        header.addWidget(code_lbl)

        header.addStretch()

        sync_btn = QPushButton("Sync Now")
        sync_btn.setToolTip("Sync this chain now")
        sync_btn.clicked.connect(lambda chk=False, r=rc: self._sync_single_removable_chain(r))
        header.addWidget(sync_btn)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(26, 26)
        del_btn.setToolTip("Remove this removable sync chain")
        del_btn.setStyleSheet("background: #E31E24; color: white; border: none; border-radius: 3px; font-weight: bold;")
        del_btn.clicked.connect(lambda chk=False, cid=cid_val: self._delete_chain(cid))
        header.addWidget(del_btn)

        l.addLayout(header)

        folder_str = rc.get('folder_path', '')
        last_sync = rc.get('last_synced', 0)
        if isinstance(last_sync, (int, float)) and last_sync > 0:
            last_sync_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_sync))
        elif isinstance(last_sync, str) and last_sync.strip():
            last_sync_str = last_sync.strip()
        else:
            last_sync_str = "Never"
        # Mount state comes from the background probe's cache. Calling
        # exists() here would block this thread on a drive that is busy
        # syncing somewhere else.
        is_mounted = getattr(self.parent_app, 'mount_state', {}).get(folder_str, True)
        mount_str = "Mounted" if is_mounted else "Drive Not Connected"

        status_lbl = QLabel(f"Status: {rc.get('status', 'Ready')} ({mount_str})  |  Last Synced: {last_sync_str}")
        status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        card.setProperty("status_lbl", status_lbl)
        l.addWidget(status_lbl)

        progress_lbl = QLabel("")
        progress_lbl.setStyleSheet("color: #9B59B6; font-size: 11px;")
        card.setProperty("progress_lbl", progress_lbl)
        l.addWidget(progress_lbl)

        info_h = QHBoxLayout()
        path_lbl = QLabel(f"Path: {folder_str}")
        path_lbl.setStyleSheet("color: #888; font-size: 11px;")
        info_h.addWidget(path_lbl, 1)

        open_btn = QPushButton("Open Folder")
        open_btn.setToolTip("Open this folder in File Explorer")
        open_btn.setFixedWidth(115)
        open_btn.clicked.connect(lambda chk=False, f=folder_str: self._open_folder(f))
        info_h.addWidget(open_btn)

        l.addLayout(info_h)
        return card

    def _pause_chain_sync(self, chain_id: str, duration_seconds: int):
        self.config_manager.pause_client_chain(chain_id, duration_seconds)
        self.refresh_cards()

    def _resume_chain_sync(self, chain_id: str):
        self.config_manager.resume_client_chain(chain_id)
        self.refresh_cards()

    def _bind_chain_wifi(self, chain_id: str, ssid: str):
        self.config_manager.bind_client_wifi(chain_id, ssid)
        self.refresh_cards()

    def _prompt_custom_wifi(self, chain_id: str):
        ssid, ok = QInputDialog.getText(self, "Wi-Fi SSID Binding", "Enter Wi-Fi Network SSID:")
        if ok and ssid.strip():
            self._bind_chain_wifi(chain_id, ssid.strip())

    def _delete_chain(self, chain_id: str):
        if QMessageBox.question(self, "Confirm Removal", "Are you sure you want to remove this sync chain? (Audio files on disk will remain untouched)") == QMessageBox.Yes:
            # Check if removable chain
            removables_dict = getattr(self.parent_app, 'active_removable_drives', {})
            with self.parent_app._runtime_state_lock:
                for f_str, rc in list(removables_dict.items()):
                    if rc.get('id') == chain_id:
                        removables_dict.pop(f_str, None)
                        if hasattr(self.parent_app, 'mount_state'):
                            self.parent_app.mount_state.pop(f_str, None)
                        tag_path = str(Path(rc.get('folder_path', '')) / SYNC_TAG_FILENAME)
                        # Deleting TAG.yaml means talking to the drive, so it is
                        # done in a worker thread rather than in this click handler.
                        def _remove_tag(path=tag_path):
                            try:
                                p = Path(path)
                                if p.exists():
                                    p.unlink()
                            except Exception:
                                pass
                        threading.Thread(target=_remove_tag, daemon=True).start()
            self.config_manager.remove_chain(chain_id)
            if hasattr(self.parent_app, 'refresh_sync_watchers'):
                self.parent_app.refresh_sync_watchers()
            self.refresh_cards(force=True)

    def _set_chain_visibility(self, chain_id: str, visible: bool):
        """Flip a hosted chain between findable and unfindable, on its card and in the config.

        Nothing else has to be re-armed to make it take effect: the beacon and a host's answer to a
        search both re-read the chains every time they run, so the next advertisement and the next
        search already see the change. The card is rebuilt straight away because the badge and the
        button on it are the answer, and a card that still said the old thing after a click would
        read as a click that did nothing.
        """
        self.config_manager.set_host_chain_visibility(chain_id, visible)
        self.refresh_cards(force=True)

    def _update_delete_limit(self, chain_id: str, value):
        """Store the number of files a chain may delete before it asks, and stop there.

        Deliberately no refresh_cards() here, and the limit is deliberately not part of
        _cards_signature() either: the box is being edited at this moment, and rebuilding the card
        out from under it would drop the keystroke, the focus and whatever the user was mid-way
        through typing. The next sync reads the number straight out of the chain dict instead.
        """
        self.config_manager.set_client_delete_limit(chain_id, value)

    def _sync_single_client_chain(self, cc: dict):
        cid = cc.get('id')
        if cid in self.sync_threads and self.sync_threads[cid].isRunning():
            return

        cc['status'] = "Syncing..."
        self.parent_app.sync_progress_state[cid] = {'status': 'Syncing...', 'progress': ''}
        self.refresh_cards()

        chain_name = cc.get('name', 'Sync')

        thread = ClientSyncThread(
            cc,
            # None when the app this dialog belongs to cannot put a question on screen, which is
            # how the harness drives these windows; the worker then syncs the way it always did.
            confirm_cb=make_delete_confirm_cb(self.parent_app, chain_name)
        )
        self.sync_threads[cid] = thread

        def _on_status(txt):
            self.parent_app.sync_progress_state.setdefault(cid, {})['status'] = txt
            self._update_client_card_label(cid, "status_lbl", txt)
            if hasattr(self.parent_app, 'dl_progress_signal'):
                self.parent_app.dl_progress_signal.emit(f"[Sync: {chain_name}] {txt}")

        def _on_progress(done, total, filename, idx, total_items):
            pct = int(done / total * 100) if total > 0 else 0
            prog_txt = f"[{idx}/{total_items}] ({pct}%) {filename}"
            self.parent_app.sync_progress_state.setdefault(cid, {})['progress'] = prog_txt
            self._update_client_card_label(cid, "progress_lbl", prog_txt)
            if hasattr(self.parent_app, 'dl_progress_signal'):
                self.parent_app.dl_progress_signal.emit(f"[Sync: {chain_name}] {prog_txt}")

        def _on_finish(ok, msg, transferred, deleted):
            cc['status'] = "Up to date" if ok else f"Failed: {msg}"
            if ok:
                cc['last_synced'] = time.time()
                if deletions_were_declined(msg):
                    # Say so on the status bar too: the card will read "Up to date" while the
                    # files the host stopped offering are still sitting in the folder.
                    if hasattr(self.parent_app, 'status_signal'):
                        self.parent_app.status_signal.emit(f"Sync Chain '{chain_name}': {msg}", False, "#FF8C00")
            self.config_manager.save()
            self.parent_app.sync_progress_state.pop(cid, None)
            self._update_client_card_label(cid, "progress_lbl", "")
            self.refresh_cards()
            if self.parent_app.local_current_path == cc.get('folder_path'):
                # The synced folder may be a slow device: scan it on a worker
                # thread instead of in front of the UI.
                self.parent_app._refresh_local_list_async()
            if hasattr(self.parent_app, 'dl_progress_signal'):
                self.parent_app.dl_progress_signal.emit("")

        thread.status_signal.connect(_on_status)
        thread.progress_signal.connect(_on_progress)
        thread.finished_signal.connect(_on_finish)
        thread.start()

    def _sync_single_removable_chain(self, rc: dict):
        if hasattr(self.parent_app, '_auto_sync_removable_chain'):
            self.parent_app._auto_sync_removable_chain(rc)
            self.refresh_cards()

    def _update_client_card_label(self, chain_id: str, prop_name: str, text: str):
        """Update a visible card's label (status_lbl or progress_lbl) by chain_id."""
        for i in range(self.cards_layout.count()):
            item = self.cards_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if w.property("chain_id") == chain_id:
                    lbl = w.property(prop_name)
                    if lbl:
                        try:
                            lbl.setText(text)
                        except RuntimeError:
                            pass  # widget deleted (dialog closed mid-sync)
                    break

    def _restore_in_progress_labels(self):
        """After refresh_cards(), re-populate status/progress labels for any currently running syncs."""
        state = getattr(self.parent_app, 'sync_progress_state', {})
        threads = getattr(self.parent_app, 'sync_threads', {})
        for cid, ps in state.items():
            thread = threads.get(cid)
            if thread and thread.isRunning():
                if ps.get('status'):
                    self._update_client_card_label(cid, "status_lbl", ps['status'])
                if ps.get('progress'):
                    self._update_client_card_label(cid, "progress_lbl", ps['progress'])

    def _force_sync_all(self):
        # 1. Sync all subscribed client chains
        for cc in self.config_manager.client_chains:
            self._sync_single_client_chain(cc)
        # 2. Sync all removable media chains whose drives are currently
        #    connected. Mount state is read from the background probe's cache so
        #    this click never waits on a busy drive.
        mount_state = getattr(self.parent_app, 'mount_state', {})
        for rc in list(getattr(self.parent_app, 'active_removable_drives', {}).values()):
            if mount_state.get(rc.get('folder_path', ''), True):
                self._sync_single_removable_chain(rc)
        # 3. Push update notification to clients of our hosted chains (force clients to sync)
        port = getattr(self.parent_app.sync_host_server, 'active_port', 0)
        if port > 0:
            codes = [str(hc.get('sync_code')) for hc in self.config_manager.hosted_chains if hc.get('sync_code')]

            def _notify(codes=codes, port=port):
                for code in codes:
                    send_lan_update_notification(code, port)
            threading.Thread(target=_notify, daemon=True).start()
        if hasattr(self.parent_app, 'status_signal'):
            self.parent_app.status_signal.emit("Force Sync initiated: syncing clients & removable drives, notified LAN peers.", False, "#1abd33")
