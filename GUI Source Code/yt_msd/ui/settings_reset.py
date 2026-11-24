# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.ui.settings_reset).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
#
# A mixin, not a standalone module: MainApp inherits from this class, so what is written here
# are ordinary methods and `self` is the MainApp instance. They were lifted out of the class
# body in wave 6 with their text unchanged - only the imports needed to reach the rest of the
# program were added, and the inside of a multi-line string kept the indentation it was written
# with, because changing it would change what the program shows rather than where it is kept.

import os
from yt_msd.audio.tuning import TUNING
from yt_msd.constants import STOP_AFTER_OFF
from yt_msd.sync.config import DEFAULT_SYNC_SETTINGS

class SettingsResetMixin:
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
        self.minimize_to_tray = False
        self.run_renamer = False
        self.renamer_path = ""
        self.run_custom_script = False
        self.custom_script_path = ""
        self._last_downloaded_files = []
        self.normalization_mode = "ask"
        self.auto_rename = False
        # Back to the default the constructor and load_config() both start from, not to off.
        self.channel_prefix_rename = True
        self.silence_pad_dur = 2.0
        self.silence_trim = True
        self.use_custom_norm_cmd = False
        self.custom_norm_cmd = ""
        self.disable_update_checks = False
        self.disable_ytdlp_updates = False
        # These two opt-outs live on MainApp only, never in the settings list save_config() writes
        # from scratch, so without this they survived a "factory reset": save_config() writes
        # whatever the attributes hold and load_config() reads it back on the next launch, so the
        # user stayed opted out of app-update and yt-dlp-update prompts through a reset that claimed
        # to put everything back to default.
        TUNING.reset()
        # The renamer half is a second copy of this program launched in a console, and it reads
        # the tuning settings above rather than the MainApp attributes. Resetting only the
        # attributes left every renamer this window launched running with the pre-reset trim /
        # pad / override until the app was restarted. load_config() and _apply_imported_config()
        # push the settings for the same reason; a reset has to do it too.
        self.download_threads = 3
        self.normalization_threads = max(1, os.cpu_count() // 2)
        self.local_rescan_interval = 60
        # Everything else gui_config.json stores. The file is deleted at the top of this method, but
        # save_config() at the bottom writes a fresh one out of whatever these attributes and widgets
        # hold, so anything not cleared here was straight back in the file the reset had just removed.
        # These are the parts a user would call "my recent data": the download folders and the
        # destination the top bar shows, the local folders and the folder open in the tree pane, the
        # playlist history, the format and bitrate the two top-bar combos are set to, the metadata tick
        # on the local pane, and the window geometry kept for MusicBee launches. session_data needs
        # nothing: save_config() rebuilds it from the live window on every save, and load_config() only
        # reads it back when "save place" is on, which this reset turns off. ytdlp_last_update_check is
        # cleared as well so the next launch behaves like a first run and looks for a newer yt-dlp
        # instead of trusting a timestamp left over from before the reset.
        default_dl = os.path.join(os.path.expanduser("~"), "Downloads")
        self.format_var = "mp3"
        self.bitrate_var = "192"
        self.recent_folders = [default_dl]
        self.download_path = default_dl
        self.local_folders = []
        self.local_current_path = ""
        self.recent_playlists = []
        self.show_local_metadata = False
        self.host_window_geometry = ""
        self.ytdlp_last_update_check = 0.0
        # "Stop after current" is now in the list save_config() writes, so leaving the attribute as
        # it was would have put an "always" straight back into the file this reset had just removed -
        # the same way the two update opt-outs survived the reset before they were cleared here. The
        # search arming goes with it, and apply_theme() below repaints the button through
        # _update_stop_after_ui().
        self.stop_after_current = STOP_AFTER_OFF
        self._search_stop_after_track = None
        # ...and the widgets that display those values, because save_config() reads the format, the
        # bitrate and the download folder straight off them. Left where they were, they would put the
        # old values back into the new file on the next save. Signals are blocked so no handler runs
        # against a value that has already been changed underneath it.
        if hasattr(self, 'format_combo'):
            self.format_combo.blockSignals(True)
            self.format_combo.setCurrentText(self.format_var)
            self.format_combo.blockSignals(False)
        if hasattr(self, 'bitrate_combo'):
            self.bitrate_combo.blockSignals(True)
            self.bitrate_combo.setCurrentText(self.bitrate_var)
            self.bitrate_combo.blockSignals(False)
        if hasattr(self, 'path_combo'):
            self.path_combo.blockSignals(True)
            self.path_combo.clear()
            self.path_combo.addItems([str(folder) for folder in self.recent_folders])
            self.path_combo.setCurrentText(self.download_path)
            self.path_combo.blockSignals(False)
        if hasattr(self, 'local_meta_cb'):
            self.local_meta_cb.blockSignals(True)
            self.local_meta_cb.setChecked(False)
            self.local_meta_cb.blockSignals(False)
        if hasattr(self, 'local_path_combo'):
            # Rebuilds the address bar from the now-empty recent list without firing
            # load_local_folder, which would try to scan a folder this reset has just forgotten.
            self.set_local_explorer_address("")
        # local_current_path is empty, so the scan returns None and the pane is cleared instead of
        # continuing to list the files of a folder that is no longer set anywhere.
        self.refresh_local_list()
        if hasattr(self, 'local_rescan_timer'):
            self._update_local_rescan_timer()
        if hasattr(self, 'run_renamer_cb'):
            self.run_renamer_cb.blockSignals(True)
            self.run_renamer_cb.setChecked(False)
            self.run_renamer_cb.blockSignals(False)
        if hasattr(self, 'channel_prefix_cb'):
            # The reset value for this one is on, so the box is put back to the state the
            # attributes were just set to rather than cleared with the rest.
            self.channel_prefix_cb.blockSignals(True)
            self.channel_prefix_cb.setChecked(self.channel_prefix_rename)
            self.channel_prefix_cb.blockSignals(False)
        self.splitter_sizes = [300, 800, 300]
        
        # Apply changes
        self.apply_theme()
        # The old form of this read self.splitter, which MainApp never creates: the two real
        # splitters are main_splitter (local pane | everything else) and content_splitter
        # (results | queue), and save_config() stores three sizes by reading both of them. The
        # hasattr() was therefore always false, so the panel widths survived the reset and were
        # written straight back into the new file. Same split the startup code applies.
        if hasattr(self, 'main_splitter') and hasattr(self, 'content_splitter'):
            self.main_splitter.setSizes([self.splitter_sizes[0], self.splitter_sizes[1] + self.splitter_sizes[2]])
            self.content_splitter.setSizes([self.splitter_sizes[1], self.splitter_sizes[2]])
            # Clear what each splitter kept as the user's own arrangement, or the next double-click
            # on a handle restores the pre-reset widths instead of the default pair.
            for splitter in (self.main_splitter, self.content_splitter):
                splitter._last_custom_sizes = []
        if hasattr(self, 'vol_slider'):
            self.vol_slider.setValue(100)
        # The Settings dialog is cached on MainApp and reused, and it reads the MainApp attributes
        # only when it is first built. Resetting without dropping it left the very dialog the user
        # just clicked "reset" in showing the old tick marks and the old pad value - and the next
        # toggle would have written those stale values straight back. _apply_imported_config()
        # throws the cached dialog away for the same reason; do the same here. The caller closes
        # this dialog right after the reset, so closing it from here is safe.
        settings_dialog = getattr(self, 'settings_dialog', None)
        if settings_dialog is not None:
            try:
                settings_dialog.close()
            except Exception:
                pass
            self.settings_dialog = None
        # Sync chains and sync settings live in the same file this method deletes, but
        # SyncConfigManager holds live copies of all three - hosted_chains, client_chains and
        # settings - and the Sync dialog, the export dialog and the removable-drive path all read
        # that manager rather than the file. Clearing only the file therefore left every chain in
        # memory, and the next save() - on close, or from any chain operation - wrote them back into
        # a brand-new file, so no chain was ever actually removed. That write-back is worth keeping
        # for the case where the file is deleted by hand while the app is running: the manager still
        # re-creates it on exit. It must not survive an explicit reset, so the manager is emptied
        # here too.
        # A mirror sync works on the drive it is copying to for its whole run. Stopping the chains
        # first while one is mid-flight would leave it adding and deleting files against a chain
        # definition that no longer exists, so the threads are asked to stop before the chains go.
        for thread in list(getattr(self, 'sync_threads', {}).values()):
            try:
                thread.requestInterruption()
                thread.quit()
                thread.wait(1000)
            except Exception:
                pass
        sync_threads = getattr(self, 'sync_threads', None)
        if sync_threads is not None:
            sync_threads.clear()  # in place again: SyncManagerDialog aliases this same dict
        # The per-chain "Syncing... / [3/40] (7%)" lines the cards show are keyed by chain id.
        # Left behind they describe chains this reset has just removed, and a card for a new chain
        # with the same sync code would inherit the old progress text.
        progress_state = getattr(self, 'sync_progress_state', None)
        if progress_state is not None:
            progress_state.clear()
        sync_manager = getattr(self, 'sync_config_manager', None)
        if sync_manager is not None:
            # Emptied in place. The open Sync dialog keeps references to these very objects, so
            # rebinding them to new lists would leave that window showing chains that are gone.
            sync_manager.hosted_chains.clear()
            sync_manager.client_chains.clear()
            sync_manager.settings.clear()
            sync_manager.settings.update(DEFAULT_SYNC_SETTINGS)
        watcher = getattr(self, 'host_watcher', None)
        if watcher is not None:
            try:
                watcher.stop_all()
            except Exception:
                pass
        if hasattr(self, 'sync_timer'):
            # Re-arms the client auto-sync timer on the default interval. With no client chains the
            # callback returns immediately, but it should not keep running on an interval the user
            # picked before the reset.
            self._update_sync_timer()
        sync_dialog = getattr(self, 'sync_manager_dialog', None)
        if sync_dialog is not None:
            try:
                sync_dialog.refresh_cards(force=True)
            except Exception:
                pass
        self.save_config()
        self._on_status_update("Settings, recent data and sync chains reset to defaults.", False, "#3B8ED0")
