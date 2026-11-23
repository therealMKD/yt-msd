# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.sync.discovery).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
import sys
import json
import threading
import time
import socket
from typing import List, Optional, Tuple, Callable
from yt_msd.sync.lan import UDP_BEACON_PORT, get_broadcast_addresses, get_local_ip



class UDPBeaconBroadcaster:
    """Broadcaster & Listener for LAN host discovery and dynamic IP updates (runs in dedicated daemon thread)."""
    def __init__(self, get_hosted_chains_cb: Callable[[], List[dict]], get_tcp_port_cb: Callable[[], int],
                 on_chain_updated_cb: Optional[Callable[[str], None]] = None):
        self.get_hosted_chains_cb = get_hosted_chains_cb
        self.get_tcp_port_cb = get_tcp_port_cb
        self.on_chain_updated_cb = on_chain_updated_cb
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if hasattr(self, '_sock') and self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def _run_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock = sock
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        if sys.platform == 'win32':
            try:
                sock.ioctl(0x9800000C, False)
            except Exception:
                pass

        is_bound = False
        try:
            sock.bind(('', UDP_BEACON_PORT))
            is_bound = True
        except Exception:
            is_bound = False
        sock.settimeout(1.0)

        last_beacon_time = 0
        while self._running:
            now = time.time()
            if now - last_beacon_time >= 4.0:
                last_beacon_time = now
                try:
                    chains = self.get_hosted_chains_cb()
                    tcp_port = self.get_tcp_port_cb()
                    if chains and tcp_port > 0:
                        codes = [c.get('sync_code') for c in chains if c.get('sync_code')]
                        beacon_data = {
                            'type': 'BEACON',
                            'sync_codes': codes,
                            'tcp_port': tcp_port,
                            'host_ip': get_local_ip()
                        }
                        raw = json.dumps(beacon_data).encode('utf-8')
                        for _bcast_addr in get_broadcast_addresses():
                            try:
                                sock.sendto(raw, (_bcast_addr, UDP_BEACON_PORT))
                            except Exception:
                                pass
                except Exception:
                    pass

            if is_bound:
                try:
                    msg, addr = sock.recvfrom(2048)
                    data = json.loads(msg.decode('utf-8'))
                    msg_type = data.get('type')
                    if msg_type in ('PROBE', 'PROBE_ALL'):
                        target_code = str(data.get('sync_code', '')).strip()
                        chains = self.get_hosted_chains_cb()
                        tcp_port = self.get_tcp_port_cb()
                        if chains and tcp_port > 0:
                            for c in chains:
                                c_code = str(c.get('sync_code', ''))
                                if not target_code or target_code == c_code or msg_type == 'PROBE_ALL':
                                    reply = {
                                        'type': 'PROBE_REPLY',
                                        'sync_code': c_code,
                                        'chain_name': c.get('name', 'Audio Playlist'),
                                        'tcp_port': tcp_port,
                                        'host_ip': get_local_ip()
                                    }
                                    try:
                                        sock.sendto(json.dumps(reply).encode('utf-8'), addr)
                                    except Exception:
                                        pass
                    elif msg_type == 'CHAIN_UPDATED':
                        target_code = str(data.get('sync_code', '')).strip()
                        if target_code and self.on_chain_updated_cb:
                            self.on_chain_updated_cb(target_code)
                except socket.timeout:
                    pass
                except Exception:
                    time.sleep(0.5)
            else:
                time.sleep(1.0)

        try:
            sock.close()
        except Exception:
            pass



def discover_hosts_on_lan(sync_code: Optional[str] = None, timeout: float = 2.5) -> List[Tuple[str, int, str, str]]:
    """Broadcasts a UDP discovery probe; returns list of (host_ip, tcp_port, sync_code, chain_name)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    if sys.platform == 'win32':
        try:
            sock.ioctl(0x9800000C, False)
        except Exception:
            pass
    sock.settimeout(0.3)

    probe_type = 'PROBE' if sync_code else 'PROBE_ALL'
    probe = json.dumps({'type': probe_type, 'sync_code': str(sync_code or '')}).encode('utf-8')
    start_time = time.time()
    results = []
    seen = set()

    try:
        for _bcast_addr in get_broadcast_addresses():
            try:
                sock.sendto(probe, (_bcast_addr, UDP_BEACON_PORT))
            except Exception:
                pass
        while time.time() - start_time < timeout:
            try:
                msg, (sender_ip, _) = sock.recvfrom(2048)
                data = json.loads(msg.decode('utf-8'))
                if data.get('type') in ('PROBE_REPLY', 'BEACON'):
                    rep_code = str(data.get('sync_code') or '')
                    codes = data.get('sync_codes', [rep_code] if rep_code else [])
                    port = int(data.get('tcp_port', 63350))
                    name = data.get('chain_name', 'Audio Playlist')
                    ip = data.get('host_ip') or sender_ip
                    for c in codes:
                        c_str = str(c)
                        if sync_code and c_str != str(sync_code):
                            continue
                        key = (ip, port, c_str)
                        if key not in seen:
                            seen.add(key)
                            results.append((ip, port, c_str, name))
                            if sync_code and c_str == str(sync_code):
                                return results
            except socket.timeout:
                try:
                    for _bcast_addr in get_broadcast_addresses():
                        try:
                            sock.sendto(probe, (_bcast_addr, UDP_BEACON_PORT))
                        except Exception:
                            pass
                except Exception:
                    pass
            except Exception:
                pass
    finally:
        try:
            sock.close()
        except Exception:
            pass
    return results



def discover_host_on_lan(sync_code: str, timeout: float = 2.5) -> Optional[Tuple[str, int, str]]:
    """Broadcasts a UDP discovery probe for a 4-digit sync code; returns (host_ip, tcp_port, chain_name) or None."""
    res = discover_hosts_on_lan(sync_code=str(sync_code), timeout=timeout)
    if res:
        ip, port, _, name = res[0]
        return (ip, port, name)
    return None



def send_lan_update_notification(sync_code: str, host_port: int):
    """Sends a UDP broadcast notification to LAN that a hosted chain's files have been modified."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    if sys.platform == 'win32':
        try:
            sock.ioctl(0x9800000C, False)
        except Exception:
            pass
    try:
        payload = json.dumps({
            'type': 'CHAIN_UPDATED',
            'sync_code': str(sync_code),
            'host_ip': get_local_ip(),
            'tcp_port': host_port
        }).encode('utf-8')
        for _bcast_addr in get_broadcast_addresses():
            try:
                sock.sendto(payload, (_bcast_addr, UDP_BEACON_PORT))
            except Exception:
                pass
    except Exception:
        pass
    finally:
        try:
            sock.close()
        except Exception:
            pass
