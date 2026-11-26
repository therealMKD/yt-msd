# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.sync.discovery).
import sys
import json
import re
import subprocess
import threading
import time
import socket
from concurrent.futures import TimeoutError as ScanTimeout, as_completed
from concurrent.futures.thread import ThreadPoolExecutor
from typing import Callable, List, Optional, Tuple
from PySide6.QtCore import QThread, Signal
from yt_msd.subproc import _hidden_window_kwargs
from yt_msd.sync.config import host_chain_is_visible
from yt_msd.sync.lan import (SCAN_BUDGET_SECONDS, SCAN_CONNECT_TIMEOUT,
                             SCAN_MAX_CONCURRENCY, SCAN_MAX_NETWORKS, SCAN_MAX_TARGETS,
                             SCAN_READ_TIMEOUT, SYNC_PORT_END, SYNC_PORT_START, UDP_BEACON_PORT,
                             get_broadcast_addresses, get_local_ip)
from yt_msd.sync.transfer import recv_json_msg, send_json_msg


def advertised_chains(hosted_chains: List[dict]) -> List[dict]:
    """The hosted chains this machine is willing to name to somebody it has never met.

    The beacon is a broadcast: every machine on the network reads it whether it asked or not, so
    it carries the visible chains only. A private chain's code has never been broadcast by anything
    in this program, and this is where that stays true.
    """
    return [{'sync_code': str(chain.get('sync_code')),
             'name': chain.get('name', 'Audio Playlist'),
             'visible': True}
            for chain in hosted_chains
            if chain.get('sync_code') and host_chain_is_visible(chain)]


def probe_replies(hosted_chains: List[dict], tcp_port: int, target_code: str = '') -> List[dict]:
    """What to answer somebody who asked 'who hosts what here?' without introducing themselves.

    The same rule as the beacon, read the other way round: asked in the general, only the visible
    chains answer; asked by code, the chain answers even if it is private, because a client holding
    the code is a client that can sync it anyway, and telling it where the host is is the whole
    point of a search.
    """
    wanted = str(target_code or '').strip()
    replies = []
    for chain in hosted_chains:
        code = str(chain.get('sync_code', '')).strip()
        if not code or (wanted and code != wanted):
            continue
        if not wanted and not host_chain_is_visible(chain):
            continue
        replies.append({'type': 'PROBE_REPLY',
                        'sync_code': code,
                        'chain_name': chain.get('name', 'Audio Playlist'),
                        'tcp_port': tcp_port,
                        'host_ip': get_local_ip(),
                        'visible': host_chain_is_visible(chain)})
    return replies



class UDPBeaconBroadcaster:
    """Broadcaster & Listener for LAN host discovery and dynamic IP updates (runs in dedicated daemon thread)."""
    def __init__(self, get_hosted_chains_cb: Callable[[], List[dict]], get_tcp_port_cb: Callable[[], int],
                 on_chain_updated_cb: Optional[Callable[[str], None]] = None,
                 on_sync_request_cb: Optional[Callable[[str, List[str]], None]] = None):
        self.get_hosted_chains_cb = get_hosted_chains_cb
        self.get_tcp_port_cb = get_tcp_port_cb
        self.on_chain_updated_cb = on_chain_updated_cb
        # A host asking this machine's clients to fetch. Kept apart from the callback above because
        # the two messages mean different things to the machine that reads them: a chain update says
        # "the folder you follow has changed", and a sync request says "every chain you follow has a
        # host that is ready for you now". A broadcaster built without this one simply ignores that
        # message, which is what every broadcaster built before it does.
        self.on_sync_request_cb = on_sync_request_cb
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
                    advertised = advertised_chains(chains)
                    if advertised and tcp_port > 0:
                        beacon_data = {
                            'type': 'BEACON',
                            'sync_codes': [c['sync_code'] for c in advertised],
                            'chains': advertised,
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
                            for reply in probe_replies(chains, tcp_port, target_code):
                                try:
                                    sock.sendto(json.dumps(reply).encode('utf-8'), addr)
                                except Exception:
                                    pass
                    elif msg_type == 'CHAIN_UPDATED':
                        target_code = str(data.get('sync_code', '')).strip()
                        if target_code and self.on_chain_updated_cb:
                            self.on_chain_updated_cb(target_code)
                    elif msg_type == 'CHAIN_SYNC_REQUEST':
                        # "Somebody who hosts chains here is ready, and every client of them should
                        # fetch." The codes are what makes this worth acting on: a broadcast reaches
                        # every machine on the network, and a machine that follows none of the chains
                        # named in it has no reason to start a sync because of it.
                        codes = [str(code).strip() for code in (data.get('sync_codes') or [])
                                 if str(code).strip()]
                        if codes and self.on_sync_request_cb:
                            self.on_sync_request_cb(addr[0], codes)
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



def adapter_addresses() -> List[str]:
    """Every IPv4 address this machine answers on, read from its own adapters.

    `get_local_ip()` answers "which address would a packet leave by", which is one address and not
    always the one on the network being searched: a machine with a VPN adapter, a phone-tethered
    adapter or a virtual adapter answers on several, and a search that only knows the routing-table
    guess spends its whole budget on the wrong network. `netsh` is the same read the Wi-Fi binding
    already makes, and the hostname lookup covers the adapters netsh does not list.
    """
    found = set()
    try:
        own = get_local_ip()
        if own:
            found.add(own)
    except Exception:
        pass
    try:
        for candidate in socket.gethostbyname_ex(socket.gethostname())[2]:
            if candidate:
                found.add(candidate)
    except Exception:
        pass
    if sys.platform == 'win32':
        try:
            res = subprocess.run(["netsh", "interface", "ipv4", "show", "addresses"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 encoding='utf-8', errors='ignore', **_hidden_window_kwargs())
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    if not line.strip().lower().startswith("ip address"):
                        continue
                    _, _, value = line.partition(":")
                    value = value.strip()
                    if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", value):
                        found.add(value)
        except Exception:
            pass
    return sorted(a for a in found if not a.startswith('127.'))


def local_scan_scope() -> Tuple[List[str], List[str]]:
    """What a search should ask about, and which of those addresses belong to this machine.

    The networks are the /24 of each adapter. That is an assumption, and the honest one: nothing in
    the standard library reports a netmask without a call per adapter, and a home or office network
    this program is meant to work on is a /24. Own addresses come back so a search can skip them -
    a client looking for a host is not looking for the machine it is standing on.
    """
    addresses = adapter_addresses()
    bases: List[str] = []
    for address in addresses:
        parts = address.split('.')
        if len(parts) == 4:
            base = '.'.join(parts[:3])
            if base not in bases:
                bases.append(base)
        if len(bases) >= SCAN_MAX_NETWORKS:
            break
    return bases, addresses


def subnet_targets(base_addresses: List[str], exclude: Optional[List[str]] = None) -> List[str]:
    """Every address worth a handshake on these networks: .1 through .254, minus the excluded ones."""
    skip = set(exclude or ())
    targets: List[str] = []
    for base in base_addresses:
        for last in range(1, 255):
            address = f"{base}.{last}"
            if address in skip:
                continue
            targets.append(address)
            if len(targets) >= SCAN_MAX_TARGETS:
                return targets
    return targets

class HostScanner:
    """One pass asking this machine's networks "are you a yt-msd, and what are you hosting?"

    TCP handshakes on the ports the host server listens on, in port order, up to
    `SCAN_MAX_CONCURRENCY` at a time, for `SCAN_BUDGET_SECONDS` in all. Port order is not a detail:
    the host server takes the first free port from 63350 upward, so almost every host is on 63350,
    and asking that one port across the whole network first is what puts an answer on screen in the
    first second rather than the last.

    A broadcast probe is not used, and that is what the earlier version of this did and why it found
    nothing: directed broadcasts are dropped by most access points, and Windows authorises the
    program for the ports it listens on rather than for one it only ever sends from. TCP is the path
    a working sync has already proved on the network it runs on.
    """

    def __init__(self, requested_code: str = '', targets: Optional[List[str]] = None,
                 ports: Optional[List[int]] = None, connect_timeout: float = SCAN_CONNECT_TIMEOUT,
                 budget: float = SCAN_BUDGET_SECONDS):
        self.requested_code = str(requested_code or '').strip()
        self._targets = targets
        self._ports = ports
        self.connect_timeout = connect_timeout
        self.budget = budget
        # Set by run(): how a pass ended, so whoever reports it can say so instead of guessing.
        self.timed_out = False
        self.stopped_early = False
        self.searched = 0

    def scope(self) -> Tuple[List[str], List[int]]:
        """The addresses and ports this pass will ask - handed to it, or read off this machine."""
        if self._targets is not None:
            targets = list(self._targets)
        else:
            bases, own = local_scan_scope()
            targets = subnet_targets(bases, exclude=own)
        ports = (list(self._ports) if self._ports is not None
                 else list(range(SYNC_PORT_START, SYNC_PORT_END + 1)))
        return targets, ports

    def ask(self, host_ip: str, port: int) -> List[dict]:
        """One address on one port: what this program says it hosts there, or nothing at all."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.connect_timeout)
            sock.connect((host_ip, port))
        except Exception:
            return []
        answer = None
        try:
            send_json_msg(sock, {'cmd': 'HELLO', 'sync_code': self.requested_code})
            answer = recv_json_msg(sock, timeout=SCAN_READ_TIMEOUT)
        except Exception:
            answer = None
        finally:
            try:
                sock.close()
            except Exception:
                pass
        return self._read_answer(host_ip, port, answer)

    def _read_answer(self, host_ip: str, port: int, answer) -> List[dict]:
        """One host's answer turned into entries - and nothing at all about anything that is not a host."""
        if not isinstance(answer, dict):
            return []
        if answer.get('status') == 'OK':
            entries = []
            for chain in answer.get('chains') or []:
                code = str(chain.get('sync_code', '')).strip()
                if not code or (self.requested_code and code != self.requested_code):
                    continue
                entries.append({'ip': host_ip, 'port': port, 'sync_code': code,
                                'chain_name': chain.get('name', 'Audio Playlist'),
                                'visible': bool(chain.get('visible', True)),
                                'host_name': str(answer.get('host_name', '')),
                                'advertised': True})
            return entries
        if 'Expected AUTH' in str(answer.get('reason', '')):
            # A yt-msd from before HELLO existed. It will not name its chains, but it answered on a
            # sync port and it will still take a client that authenticates, and the address is the
            # half of the answer that used to have to be typed in.
            return [{'ip': host_ip, 'port': port, 'sync_code': self.requested_code,
                     'chain_name': '', 'visible': True, 'host_name': '', 'advertised': False}]
        return []


    def run(self, on_found: Optional[Callable[[dict], None]] = None,
            should_stop: Optional[Callable[[], bool]] = None) -> List[dict]:
        """Search, reporting every host as it answers. Returns everything found."""
        targets, ports = self.scope()
        found: List[dict] = []
        seen = set()
        deadline = time.time() + self.budget
        ended_early = False
        pool = ThreadPoolExecutor(max_workers=min(SCAN_MAX_CONCURRENCY, max(1, len(targets))))
        try:
            for port in ports:
                if should_stop and should_stop():
                    ended_early = True
                    break
                futures = {pool.submit(self.ask, ip, port): ip for ip in targets}
                self.searched += len(futures)
                try:
                    for future in as_completed(futures, timeout=max(0.05, deadline - time.time())):
                        try:
                            entries = future.result()
                        except Exception:
                            continue
                        for entry in entries:
                            key = (entry['ip'], entry['port'], entry['sync_code'])
                            if key in seen:
                                continue
                            seen.add(key)
                            found.append(entry)
                            if on_found:
                                on_found(entry)
                        if (should_stop and should_stop()) or (self.requested_code and found):
                            ended_early = True
                            break
                except ScanTimeout:
                    # The budget is what bounds a search, not the number of addresses on it: an
                    # empty network answers nothing at all and must still finish.
                    self.timed_out = True
                    break
                if ended_early:
                    break
        finally:
            # Not `with`: a search the user stopped has to let go of the handshakes it had queued
            # rather than stand and wait for every one of them to time out.
            pool.shutdown(wait=False, cancel_futures=True)
        if ended_early:
            self.stopped_early = True
        return found


def discover_hosts_on_lan(sync_code: Optional[str] = None, timeout: float = 2.5) -> List[Tuple[str, int, str, str]]:
    """Search the local network for hosts; returns list of (host_ip, tcp_port, sync_code, chain_name).

    The shape is the one this function has always had, because it is the shape `SyncClientWorker`
    reads when the address a chain remembers has stopped answering. What changed is how the answer
    is got: a TCP search rather than a broadcast probe, for the reasons written on `HostScanner`.
    """
    scanner = HostScanner(requested_code=str(sync_code or ''), budget=timeout)
    return [(entry['ip'], entry['port'], entry['sync_code'], entry['chain_name'])
            for entry in scanner.run()]



def discover_host_on_lan(sync_code: str, timeout: float = 2.5) -> Optional[Tuple[str, int, str]]:
    """Find the host answering a 4-digit sync code; returns (host_ip, tcp_port, chain_name) or None."""
    res = discover_hosts_on_lan(sync_code=str(sync_code), timeout=timeout)
    if res:
        ip, port, _, name = res[0]
        return (ip, port, name)
    return None



class HostScanThread(QThread):
    """The search behind *Find Hosts On My Network*, off the GUI thread.

    A search is a few hundred handshakes and it is meant to be watched while it runs, so it cannot
    happen on the GUI thread - it would hold the window still for its whole budget. Answers are
    emitted as they arrive, which is what lets the window name a host the moment it replies rather
    than after the last address has been asked.
    """
    host_found = Signal(dict)  # one HostScanner entry, exactly as it was found
    scan_finished = Signal(int, str)  # how many there were, and how the search ended

    def __init__(self, requested_code: str = '', parent=None):
        super().__init__(parent)
        self.requested_code = str(requested_code or '').strip()

    def run(self):
        scanner = HostScanner(requested_code=self.requested_code)
        found = scanner.run(on_found=self.host_found.emit,
                            should_stop=self.isInterruptionRequested)
        if scanner.timed_out:
            how = "ran out of time"
        elif scanner.stopped_early:
            how = "stopped"
        else:
            how = "finished"
        self.scan_finished.emit(len(found), how)


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


def send_lan_sync_request(host_port: int, sync_codes: List[str]):
    """Broadcast to the LAN that every client of these hosted chains should run its normal sync now.

    The neighbour of send_lan_update_notification, and not the same message. A chain update names
    one chain and says what happened to it, and a client reads it as "re-check that folder". This
    one names every chain this machine hosts and says nothing about any of their files; it is the
    host saying it is up and ready, and every machine that follows one of these chains should do
    what it would have done had its user pressed Force Sync All. The codes are carried rather than
    left out because a broadcast reaches the whole network, and a machine that follows none of them
    has no business starting a sync because a stranger came online.
    """
    named = [str(code).strip() for code in (sync_codes or []) if str(code).strip()]
    if not named or host_port <= 0:
        return
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    if sys.platform == 'win32':
        try:
            sock.ioctl(0x9800000C, False)
        except Exception:
            pass
    try:
        payload = json.dumps({
            'type': 'CHAIN_SYNC_REQUEST',
            'sync_codes': named,
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

