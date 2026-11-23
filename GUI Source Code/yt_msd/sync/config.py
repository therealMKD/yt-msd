# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.sync.config).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
import os
import json
import threading
import time
import random
from typing import List, Optional



def is_client_chain_paused(cc: dict) -> tuple[bool, int]:
    """Returns (is_paused, pause_until) for the client sync chain."""
    paused_until = cc.get('paused_until', 0)

    if paused_until == -1:
        return True, -1

    if paused_until > 0:
        if paused_until > time.time():
            return True, paused_until
        else:
            cc['paused_until'] = 0

    return False, 0



# Shared lock so the two writers of gui_config.json (MainApp.save_config and
# SyncConfigManager.save) never interleave partial reads/writes and clobber each other.
_CONFIG_WRITE_LOCK = threading.Lock()


# The sync settings a fresh install gets. Named here rather than written inline so that
# MainApp.reset_to_defaults() can hand back exactly these defaults instead of guessing at
# a copy of the literal.
DEFAULT_SYNC_SETTINGS = {"auto_sync_interval_mins": 30, "firewall_prompted": False}



class SyncConfigManager:
    """Manages persistence of sync configuration within the unified gui_config.json."""
    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        self.config_file = os.path.join(config_dir, "gui_config.json")
        self.legacy_file = os.path.join(config_dir, "sync_config.json")
        self.settings: dict = dict(DEFAULT_SYNC_SETTINGS)
        self.hosted_chains: List[dict] = []
        self.client_chains: List[dict] = []
        self.load()

    def load(self):
        migrated = False
        # Migrate legacy sync_config.json if present
        if os.path.exists(self.legacy_file):
            try:
                with open(self.legacy_file, 'r', encoding='utf-8') as f:
                    legacy_data = json.load(f)
                    self.settings = legacy_data.get('settings', self.settings)
                    self.hosted_chains = legacy_data.get('hosted_chains', [])
                    self.client_chains = legacy_data.get('client_chains', [])
                migrated = True
            except Exception:
                pass
            try:
                os.remove(self.legacy_file)
            except Exception:
                pass

        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if not migrated or 'hosted_chains' in data:
                        self.settings = data.get('sync_settings', self.settings)
                        self.hosted_chains = data.get('hosted_chains', self.hosted_chains)
                        self.client_chains = data.get('client_chains', self.client_chains)
            except Exception:
                pass

        # bind_client_wifi() used to write the Wi-Fi binding as 'bound_wifi_ssid' while every
        # reader - the chain card label, the auto-sync gate, the LAN-notification path and the
        # removable-drive path - asks for 'wifi_ssid'. A chain that was bound to a network in an
        # earlier build therefore reads back as unbound, and the sync quietly reverts to running on
        # any network. Fold the stray key back onto the name the readers use so an existing binding
        # survives the upgrade instead of silently disappearing.
        for chain in self.client_chains:
            stray_ssid = chain.pop('bound_wifi_ssid', None)
            if stray_ssid is not None and not str(chain.get('wifi_ssid') or '').strip():
                chain['wifi_ssid'] = str(stray_ssid).strip()
                migrated = True

        if migrated:
            self.save()

    def save(self):
        with _CONFIG_WRITE_LOCK:
            data = {}
            if os.path.exists(self.config_file):
                try:
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except Exception:
                    data = {}

            data['sync_settings'] = self.settings
            data['hosted_chains'] = self.hosted_chains
            data['client_chains'] = self.client_chains

            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
            except Exception:
                pass

    def generate_unique_sync_code(self) -> str:
        used = {str(c.get('sync_code')) for c in self.hosted_chains}
        for _ in range(1000):
            code = str(random.randint(1000, 9999))
            if code not in used:
                return code
        return "1000"

    def add_hosted_chain(self, name: str, folder_path: str, sync_code: Optional[str] = None, notify_delay_mins: int = 5) -> dict:
        code = sync_code or self.generate_unique_sync_code()
        chain = {
            'id': f'hc_{code}',
            'sync_code': code,
            'name': name,
            'folder_path': folder_path,
            'notify_delay_mins': notify_delay_mins,
            'created_at': time.time(),
            'last_synced': 0,
            'status': 'Active'
        }
        self.hosted_chains.append(chain)
        self.save()
        return chain

    def add_client_chain(self, name: str, folder_path: str, sync_code: str, host_ip: str,
                         host_port: int = 63350, deletion_mode: str = 'mirror', bound_wifi_ssid: str = '') -> dict:
        chain = {
            'id': f'cc_{sync_code}',
            'sync_code': sync_code,
            'name': name,
            'folder_path': folder_path,
            'last_known_host_ip': host_ip,
            'host_port': host_port,
            'deletion_mode': deletion_mode,
            'paused_until': 0,
            'wifi_ssid': bound_wifi_ssid,
            'created_at': time.time(),
            'last_synced': 0,
            'status': 'Pending Sync'
        }
        self.client_chains.append(chain)
        self.save()
        return chain

    def pause_client_chain(self, chain_id: str, duration_sec: int):
        paused_until = -1 if duration_sec == -1 else int(time.time() + duration_sec)
        for c in self.client_chains:
            if c.get('id') == chain_id:
                c['paused_until'] = paused_until
                break
        self.save()

    def resume_client_chain(self, chain_id: str):
        for c in self.client_chains:
            if c.get('id') == chain_id:
                c['paused_until'] = 0
                break
        self.save()

    def bind_client_wifi(self, chain_id: str, ssid: str):
        for c in self.client_chains:
            if c.get('id') == chain_id:
                # Must be written under exactly 'wifi_ssid'. add_client_chain() stores it under
                # that name and every reader asks for it by that name, so writing it anywhere else
                # made "Bind Wi-Fi" / "Unbind Wi-Fi" on a live chain look like a no-op: the card
                # kept its old label and the auto-sync gate kept the SSID the chain was created with.
                c['wifi_ssid'] = ssid.strip()
                break
        self.save()

    def remove_chain(self, chain_id: str):
        self.hosted_chains = [c for c in self.hosted_chains if c.get('id') != chain_id]
        self.client_chains = [c for c in self.client_chains if c.get('id') != chain_id]
        self.save()
