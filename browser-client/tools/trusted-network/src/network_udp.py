# SPDX-License-Identifier: Apache-2.0
"""Bounded, operator-scoped UDP bridge for an isolated managed test domain.

This forwards protocol datagrams, not authority: the real domain and mixers
still authenticate packets and enforce the guest's native permissions.
"""
import ctypes
import ipaddress
import json
import os
from pathlib import Path
import selectors
import signal
import socket
import struct
import sys
import time

HEADER = struct.Struct('!BHHH')  # pinned local endpoint, server/native ports, size
MAX_PAYLOAD = 65507
MAX_BUFFER = 512 * 1024
MAX_FLOWS = 128


def scope(value):
    address = str(ipaddress.IPv4Address(value['address']))
    # A local managed domain is the sole extra ingress. Internet guests need
    # no UDP exceptions and cannot select destinations through this bridge.
    if not ipaddress.IPv4Address(address).is_loopback:
        raise ValueError('Managed UDP relay requires an operator-pinned loopback domain')
    ports = value['ports']
    if not isinstance(ports, list) or not 1 <= len(ports) <= 32 or any(
            isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535 for port in ports):
        raise ValueError('Managed UDP relay ports must be a bounded explicit list')
    return address, frozenset(ports)


class DatagramRelay:
    def __init__(self, stream, address, ports, native=False):
        self.stream = stream
        stream.setblocking(False)
        self.address = address
        self.local_addresses = tuple(dict.fromkeys(('127.0.0.1', address)))
        self.ports = ports
        self.native = native
        self.selector = selectors.DefaultSelector()
        self.selector.register(stream, selectors.EVENT_READ, 'stream')
        self.sockets = {}
        self.input = bytearray()
        self.output = bytearray()
        self.tokens = 5000.0
        self.updated = time.monotonic()
        if native:
            for endpoint, local_address in enumerate(self.local_addresses):
                for port in ports:
                    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    listener.bind((local_address, port))
                    listener.setblocking(False)
                    self.sockets[(endpoint, port)] = listener
                    self.selector.register(listener, selectors.EVENT_READ, (endpoint, port))

    def admit(self):
        now = time.monotonic()
        self.tokens = min(5000, self.tokens + (now - self.updated) * 5000)
        self.updated = now
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True

    def queue(self, endpoint, port, native_port, payload):
        if not 0 < len(payload) <= MAX_PAYLOAD or len(self.output) + len(payload) + HEADER.size > MAX_BUFFER:
            return
        self.output += HEADER.pack(endpoint, port, native_port, len(payload)) + payload
        self.selector.modify(self.stream, selectors.EVENT_READ | selectors.EVENT_WRITE, 'stream')

    def deliver(self, endpoint, port, native_port, payload):
        if endpoint >= len(self.local_addresses) or port not in self.ports or not native_port or not payload or not self.admit():
            return
        if self.native:
            self.sockets[(endpoint, port)].sendto(payload, ('127.0.0.1', native_port))
        else:
            key = (endpoint, port, native_port)
            peer = self.sockets.get(key)
            if peer is None:
                if len(self.sockets) >= MAX_FLOWS:
                    return
                peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                peer.setblocking(False)
                self.sockets[key] = peer
                self.selector.register(peer, selectors.EVENT_READ, key)
            peer.sendto(payload, (self.address, port))

    def step(self):
        for key, events in self.selector.select(timeout=0.1):
            peer = key.fileobj
            if key.data == 'stream':
                if events & selectors.EVENT_READ:
                    data = peer.recv(65536)
                    if not data:
                        return False
                    self.input += data
                    if len(self.input) > MAX_BUFFER:
                        return False
                    while len(self.input) >= HEADER.size:
                        endpoint, port, native_port, size = HEADER.unpack_from(self.input)
                        if not size or size > MAX_PAYLOAD:
                            return False
                        if len(self.input) < HEADER.size + size:
                            break
                        payload = bytes(self.input[HEADER.size:HEADER.size + size])
                        del self.input[:HEADER.size + size]
                        try:
                            self.deliver(endpoint, port, native_port, payload)
                        except (BlockingIOError, ConnectionRefusedError):
                            pass  # UDP loss does not grant a new route.
                if events & selectors.EVENT_WRITE and self.output:
                    del self.output[:peer.send(self.output)]
                    if not self.output:
                        self.selector.modify(peer, selectors.EVENT_READ, 'stream')
            elif self.native:
                payload, source = peer.recvfrom(MAX_PAYLOAD + 1)
                if ipaddress.IPv4Address(source[0]).is_loopback and self.admit():
                    self.queue(*key.data, source[1], payload)
            else:
                try:
                    payload, source = peer.recvfrom(MAX_PAYLOAD + 1)
                except ConnectionRefusedError:
                    continue
                # Wildcard-bound domain/mixer sockets on the host can reply
                # from 127.0.0.1 to a request sent to its dedicated .2 address.
                # Admit only these two explicitly owned loopback aliases and
                # the exact configured endpoint port. Preserve the original
                # destination alias in the native namespace's reply socket.
                if source[0] in self.local_addresses and source[1] == key.data[1]:
                    self.queue(*key.data, payload)
        return True

    def close(self):
        for peer in self.sockets.values():
            peer.close()
        self.stream.close()
        self.selector.close()


def host_main(config):
    address, ports = scope(config['managedUDP'])
    stopping = False

    def stop(_number, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'Cannot bind managed relay lifetime')
    if os.getppid() != config['supervisorParentPID']:
        return
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(config['managedUDPSocket'])
    os.chmod(config['managedUDPSocket'], 0o600)
    listener.listen(1)
    listener.settimeout(0.2)
    relay = None
    print('OVERTE_UDP_RELAY_READY', flush=True)
    try:
        while not stopping:
            try:
                stream, _ = listener.accept()
                relay = DatagramRelay(stream, address, ports)
                break
            except socket.timeout:
                pass
        while not stopping and relay is not None and relay.step():
            pass
    finally:
        if relay is not None:
            relay.close()
        listener.close()
        Path(config['managedUDPSocket']).unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        host_main(json.loads(Path(sys.argv[1]).read_text()))
    except Exception as error:
        print('Managed UDP relay failed: ' + str(error), file=sys.stderr, flush=True)
        raise SystemExit(1)
