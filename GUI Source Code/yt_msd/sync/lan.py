# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.sync.lan).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
import sys
import subprocess
import time
import socket
from typing import Optional
from yt_msd.subproc import _hidden_window_kwargs


# ============================================================
# LOCAL NETWORK PLAYLIST & AUDIO FILE SYNC ("SYNC CHAINS")
# ============================================================

SYNC_PORT_START = 63350

SYNC_PORT_END = 63370

UDP_BEACON_PORT = 63350

SYNC_SOCKET_TIMEOUT = 12.0

# How often a client pings its host while it has stopped to ask the user something. The host
# reads the next command with a 30-second timeout (SyncHostServer._handle_client), so this has to
# be comfortably shorter than that - and long enough that a question answered straight away costs
# nothing. See _HostKeepalive in yt_msd.sync.client.
SYNC_CONFIRM_PING_INTERVAL = 10.0

SYNC_CHUNK_SIZE = 1024 * 1024

# How long a restore code stays good on the host that shows it. The code is meant to be read off one
# screen and typed into another machine by two people who are standing in the same room, so it needs
# long enough to be read aloud and typed - and it must not sit on screen indefinitely, because while
# it is open anybody at the client could be handed the one thing that lets them overwrite this
# machine's hosted folder.
SYNC_RESTORE_CODE_TIMEOUT = 180.0

# How long each read of the swapped half of a chain may take. The ordinary socket timeout is a
# handshake timeout: it assumes the next message is already on its way. During a rebuild the host is
# hashing its own library before it answers, and a client is hashing its own before it sends the
# index, and either of those is a slow drive doing a lot of work rather than a dead connection.
SYNC_RESTORE_HANDSHAKE_TIMEOUT = 300.0

# The code a host shows when a client asks it to rebuild itself from that client. Four characters,
# from an alphabet with the look-alikes taken out of it - no I, O, 0 or 1 - because it is read off
# one screen and typed into another, usually out loud. It is deliberately not four digits: the number
# a chain is found by is four digits, and a code that must never be confused with that one should not
# look like it.
RESTORE_CODE_LENGTH = 4

RESTORE_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def restore_code_shape(text) -> Optional[str]:
    """A typed restore code in the shape it can be checked in, or nothing if it is not one.

    Uppercased, with the spaces and dashes somebody adds while copying four characters off a screen
    taken back out. Anything else - the wrong length, a letter this code does not use, nothing at all
    - is not a code, and is answered as that rather than sent along to be compared against one.
    """
    typed = str(text or '').strip().upper().replace(' ', '').replace('-', '')
    if len(typed) != RESTORE_CODE_LENGTH:
        return None
    if any(ch not in RESTORE_CODE_ALPHABET for ch in typed):
        return None
    return typed


# What a host calls itself when a client asks it "are you a yt-msd, and what are you hosting?"
# before authenticating. The answer is what makes a scan able to tell a sync host from whatever
# else happens to have a port open on a machine down the hall. See HELLO in yt_msd.sync.host.
DISCOVERY_APP_NAME = 'yt-msd'

# A LAN search is a TCP handshake to every address on this machine's own networks, on the ports
# the host server listens on. TCP rather than a UDP broadcast because it is the one path a sync
# has already proved works on the network it runs on: broadcast traffic is dropped by most access
# points, and Windows authorises the program for the TCP ports it listens on and not for a
# broadcast port it only ever sends from. The numbers are the whole budget of one search - long
# enough to cross a /24 twice, short enough that a search that finds nothing finishes.
SCAN_CONNECT_TIMEOUT = 0.35
SCAN_READ_TIMEOUT = 1.5
SCAN_MAX_CONCURRENCY = 128
SCAN_BUDGET_SECONDS = 14.0
SCAN_MAX_NETWORKS = 4
SCAN_MAX_TARGETS = 1024



def get_current_wifi_ssid() -> Optional[str]:
    """Returns the current connected Wi-Fi SSID on Windows, or None if not connected to Wi-Fi."""
    if sys.platform != 'win32':
        return None
    try:
        res = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='ignore',
            **_hidden_window_kwargs()
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                line = line.strip()
                if line.startswith("SSID") and not line.startswith("SSID name") and not line.startswith("BSSID"):
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        ssid = parts[1].strip()
                        if ssid:
                            return ssid
    except Exception:
        pass
    return None



_CACHED_LOCAL_IP = None

_CACHED_LOCAL_IP_TIME = 0



def get_local_ip() -> str:
    """Returns the primary local IPv4 address on the LAN interface with fast memory caching."""
    global _CACHED_LOCAL_IP, _CACHED_LOCAL_IP_TIME
    now = time.time()
    if _CACHED_LOCAL_IP and (now - _CACHED_LOCAL_IP_TIME < 60.0):
        return _CACHED_LOCAL_IP

    # 1. First attempt: UDP routing table query (instant 0ms kernel lookup, no packets sent)
    ip = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        cand = s.getsockname()[0]
        s.close()
        if cand and not cand.startswith('127.'):
            ip = cand
    except Exception:
        pass

    # 2. Fallback: Hostname adapter resolution with LAN subnet priority (prefer 192.168.x.x / 10.x.x.x)
    if not ip or ip.startswith('127.'):
        try:
            hostname = socket.gethostname()
            candidates = socket.gethostbyname_ex(hostname)[2]
            for c in candidates:
                if c.startswith('192.168.'):
                    ip = c
                    break
            if not ip:
                for c in candidates:
                    if c.startswith('10.'):
                        ip = c
                        break
            if not ip:
                for c in candidates:
                    if not c.startswith('127.') and not c.startswith('172.17.') and not c.startswith('172.18.') and not c.startswith('172.21.'):
                        ip = c
                        break
        except Exception:
            pass

    if not ip:
        ip = '127.0.0.1'

    _CACHED_LOCAL_IP = ip
    _CACHED_LOCAL_IP_TIME = now
    return ip



def get_broadcast_addresses() -> list:
    """Returns a list of broadcast addresses: subnet-directed (e.g. 192.168.1.255) across all network adapters and global."""
    addrs = set()
    addrs.add('255.255.255.255')
    try:
        local_ip = get_local_ip()
        if local_ip and not local_ip.startswith('127.'):
            parts = local_ip.split('.')
            if len(parts) == 4:
                addrs.add(f"{parts[0]}.{parts[1]}.{parts[2]}.255")
        hostname = socket.gethostname()
        for cand in socket.gethostbyname_ex(hostname)[2]:
            if cand and not cand.startswith('127.'):
                parts = cand.split('.')
                if len(parts) == 4:
                    addrs.add(f"{parts[0]}.{parts[1]}.{parts[2]}.255")
    except Exception:
        pass
    return list(addrs)
