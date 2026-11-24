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


# Whether a hosted chain announces itself to the network. A visible chain is named in the host's
# discovery answers, together with its sync code, so a client finds it and never types anything. A
# private chain is named in nothing and answers no untargeted search at all - it only replies to a
# client that already put its code on the request.
DEFAULT_HOST_CHAIN_VISIBLE = True

# Chains saved before this option existed carry no key for it. They read as visible because that
# is what they already were: a hosted chain's code has been broadcast on the LAN by the beacon in
# every build since 3.0, so a chain that could be found before this setting existed must not
# quietly become unfindable after it. MainApp says so once, in a box on the main window
# (_notify_legacy_visible_chains), because a privacy setting that arrives by upgrade has to be
# pointed out rather than assumed. The key below is what remembers that it has.
VISIBILITY_NOTICE_SETTING = 'chains_visibility_notice_shown'


# The sync settings a fresh install gets. Named here rather than written inline so that
# MainApp.reset_to_defaults() can hand back exactly these defaults instead of guessing at
# a copy of the literal.
DEFAULT_SYNC_SETTINGS = {"auto_sync_interval_mins": 30, "firewall_prompted": False,
                         VISIBILITY_NOTICE_SETTING: False}


# How many files a client chain is allowed to delete on its own before it has to ask the user
# first. A chain that was made before this setting existed carries no number at all, and every
# reader of one falls back to this - so a 3.0, 3.1, 3.2, 3.3 or 3.4 chain keeps syncing exactly as
# it always did, just now behind the guard.
DEFAULT_DELETE_CONFIRM_LIMIT = 10

# The top end the option boxes offer. It is a ceiling on what can be typed, not a rule the sync
# enforces: delete_confirm_limit() takes whatever non-negative number a config file hands it.
DELETE_CONFIRM_LIMIT_MAX = 999999

# How long a sync worker may wait for an answer before the question counts as a No. The worker is
# parked and its host connection is being kept warm while it waits (see _HostKeepalive), so this
# only exists so a question nobody answers cannot hold a chain open forever.
SYNC_CONFIRM_WAIT_LIMIT = 30 * 60


def host_chain_is_visible(chain_config: dict) -> bool:
    """Whether this hosted chain may be named to anyone searching the network.

    Read with a fallback rather than required, for the reason `delete_confirm_limit()` reads the
    same way: chains written by 3.0-3.4 have no such key, a hand-edited config can hold anything,
    and a value that reads as neither True nor False must not decide this on its own. Text is what
    a hand-edited file holds, so "false", "0", "no" and "off" are all taken as private.
    """
    raw = chain_config.get('visible')
    if raw is None:
        return DEFAULT_HOST_CHAIN_VISIBLE
    if isinstance(raw, str):
        return raw.strip().lower() not in ('false', '0', 'no', 'off', '')
    return bool(raw)


def delete_confirm_limit(chain_config: dict) -> int:
    """How many files this client chain may delete without asking, or 0 for any number.

    Read with a fallback rather than required. Chains saved by earlier builds have no such key,
    a hand-edited config can hold anything, and neither may turn into a crash or into a sync that
    quietly deletes nothing: a value that is not a number becomes the default, and a negative one
    becomes 0, which is this program's own "no ceiling" value.
    """
    raw = chain_config.get('delete_confirm_limit')
    if raw is None or isinstance(raw, bool):
        return DEFAULT_DELETE_CONFIRM_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_DELETE_CONFIRM_LIMIT
    return value if value > 0 else 0



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

    def add_hosted_chain(self, name: str, folder_path: str, sync_code: Optional[str] = None, notify_delay_mins: int = 5,
                         visible: bool = DEFAULT_HOST_CHAIN_VISIBLE) -> dict:
        code = sync_code or self.generate_unique_sync_code()
        chain = {
            'id': f'hc_{code}',
            'sync_code': code,
            'name': name,
            'folder_path': folder_path,
            'notify_delay_mins': notify_delay_mins,
            # Written every time, even when it is the default, so a chain created by this build is
            # never mistaken for one created before the option existed - which is the difference
            # between telling the user about it and leaving them to find out from a client.
            'visible': bool(visible),
            'created_at': time.time(),
            'last_synced': 0,
            'status': 'Active'
        }
        self.hosted_chains.append(chain)
        self.save()
        return chain

    def set_host_chain_visibility(self, chain_id: str, visible: bool):
        """Make a hosted chain findable by anyone on the LAN, or answer nobody but its code.

        Written as a real True/False rather than as a deletion: the key's absence is what marks a
        chain as predating the option, and a chain the user has just decided about has been decided
        about.
        """
        for c in self.hosted_chains:
            if c.get('id') == chain_id:
                c['visible'] = bool(visible)
                break
        self.save()

    def add_client_chain(self, name: str, folder_path: str, sync_code: str, host_ip: str,
                         host_port: int = 63350, deletion_mode: str = 'mirror', bound_wifi_ssid: str = '',
                         delete_confirm_limit: int = DEFAULT_DELETE_CONFIRM_LIMIT,
                         host_chain_name: str = '') -> dict:
        try:
            limit = max(0, int(delete_confirm_limit))
        except (TypeError, ValueError):
            limit = DEFAULT_DELETE_CONFIRM_LIMIT
        chain = {
            'id': f'cc_{sync_code}',
            'sync_code': sync_code,
            'name': name,
            'folder_path': folder_path,
            'last_known_host_ip': host_ip,
            'host_port': host_port,
            'deletion_mode': deletion_mode,
            # What the host calls this chain, read off the host's own answer - the HELLO a network
            # search gets, or the AUTH a sync makes. The name above is the folder this machine
            # writes into, which the listener may have named differently; this one is what the
            # other machine is serving, and it is what its card shows. Written every time, empty
            # included, so a chain made by this build is never mistaken for one that never learned
            # the name.
            'host_chain_name': str(host_chain_name or '').strip(),
            # How many files this chain may delete before it asks. Kept on the chain rather than
            # in the shared settings because Mirror is a property of one chain: a chain synced in
            # Additive mode never deletes, and so has no use for a number.
            'delete_confirm_limit': limit,
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

    def set_client_delete_limit(self, chain_id: str, value):
        """Store how many files a client chain may delete before it asks (0 for any number).

        Only ever writes a number the worker can use, for the same reason delete_confirm_limit()
        guards what it reads: this value comes out of a box the user types into.
        """
        try:
            limit = max(0, int(value))
        except (TypeError, ValueError):
            limit = DEFAULT_DELETE_CONFIRM_LIMIT
        for c in self.client_chains:
            if c.get('id') == chain_id:
                c['delete_confirm_limit'] = limit
                break
        self.save()

    def remove_chain(self, chain_id: str):
        self.hosted_chains = [c for c in self.hosted_chains if c.get('id') != chain_id]
        self.client_chains = [c for c in self.client_chains if c.get('id') != chain_id]
        self.save()
