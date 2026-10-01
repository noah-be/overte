# SPDX-License-Identifier: Apache-2.0
"""Trusted namespace supervisor. No browser-provided commands or destinations."""
import json
import ctypes
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
from network_udp import DatagramRelay, scope as udp_scope
from network_route_diagnostics import route_failure_diagnostic

DENIED_ROUTES = (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16",
    "100.64.0.0/10", "192.0.0.0/24", "192.0.2.0/24", "198.18.0.0/15",
    "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4",
)


def pump(source, destination):
    try:
        while True:
            data = source.recv(65536)
            if not data:
                break
            destination.sendall(data)
    except OSError:
        pass
    finally:
        try:
            destination.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def bridge(client, unix_path, slots):
    peer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        peer.connect(unix_path)
        upstream = threading.Thread(target=pump, args=(client, peer), daemon=True)
        upstream.start()
        pump(peer, client)
        upstream.join(timeout=1)
    except OSError:
        pass
    finally:
        peer.close()
        client.close()
        slots.release()


def reap_owned_descendants():
    # Bubblewrap's launcher can exit while its PID-namespace init is still
    # waiting for a TERM-resistant child. As the nearest subreaper, retain that
    # orphan and explicitly end/reap it before the network owner can exit.
    children_path = Path(f"/proc/{os.getpid()}/task/{os.getpid()}/children")
    for _ in range(300):
        children = [int(value) for value in children_path.read_text().split()]
        if not children:
            return
        for pid in children:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        while True:
            try:
                pid, _ = os.waitpid(-1, os.WNOHANG)
                if not pid:
                    break
            except ChildProcessError:
                break
        time.sleep(0.01)
    raise RuntimeError("Owned native namespace descendants did not exit")


def install_denied_routes():
    for route in DENIED_ROUTES:
        try:
            subprocess.run(["ip", "route", "add", "prohibit", route], check=True, capture_output=True)
        except subprocess.CalledProcessError as error:
            print("OVERTE_NET_ROUTE_FAILURE=" + json.dumps(route_failure_diagnostic(error), separators=(',', ':')),
                  file=sys.stderr, flush=True)
            raise


def main():
    config = json.loads(Path(sys.argv[1]).read_text())
    child = None
    stopping = threading.Event()
    signal_stopping = False

    def stop(_number, _frame):
        nonlocal signal_stopping
        # Python signal callbacks run between arbitrary main-thread bytecodes,
        # including while Popen holds its non-reentrant waitpid lock. Calling
        # poll/terminate (or acquiring an Event lock) here can deadlock teardown.
        signal_stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    # Set this after unshare's credential transition, which can clear a prior
    # parent-death signal. Check the race where the gateway died before setup.
    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "Cannot bind network supervisor lifetime")
    if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "Cannot own native namespace descendants")
    if os.getppid() != config["supervisorParentPID"]:
        return 0
    print("OVERTE_NET_OWNER_READY", flush=True)
    # The host-owned slirp process configures the namespace. Nothing untrusted
    # executes before the interface, deny routes and scoped bridge are ready.
    for _ in range(200):
        if stopping.is_set() or signal_stopping:
            return 0
        result = subprocess.run(["ip", "-j", "address", "show", "dev", "tap0"], capture_output=True)
        if result.returncode == 0 and b'10.0.2.100' in result.stdout:
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("Private native network initialization timed out")
    install_denied_routes()

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", config["bridgePort"]))
    listener.listen(8)
    listener.settimeout(0.2)
    slots = threading.BoundedSemaphore(8)

    def accept():
        while not stopping.is_set():
            try:
                client, _ = listener.accept()
                if not slots.acquire(blocking=False):
                    client.close()
                    continue
                threading.Thread(target=bridge, args=(client, config["bridgeSocket"], slots), daemon=True).start()
            except socket.timeout:
                pass
            except OSError:
                break

    threading.Thread(target=accept, daemon=True).start()
    udp = None
    if config.get('managedUDP'):
        address, ports = udp_scope(config['managedUDP'])
        stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stream.connect(config['managedUDPSocket'])
        udp = DatagramRelay(stream, address, ports, native=True)

        def forward_datagrams():
            try:
                while not stopping.is_set() and udp.step():
                    pass
            finally:
                # Losing the scoped domain route invalidates this session.
                stopping.set()
                if child is not None and child.poll() is None:
                    child.terminate()

        threading.Thread(target=forward_datagrams, daemon=True).start()
    try:
        if stopping.is_set() or signal_stopping:
            return 0
        # The inner bwrap must create a NEW user namespace. It therefore cannot
        # regain CAP_NET_ADMIN in this outer-owned network namespace.
        child = subprocess.Popen([config["command"], *config["args"]], env=config["environment"])
        print("OVERTE_NET_NATIVE_STARTED", flush=True)
        while child.poll() is None:
            if stopping.wait(0.1) or signal_stopping:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                break
        return child.wait()
    finally:
        stopping.set()
        listener.close()
        if udp is not None:
            udp.close()
        if child is not None and child.poll() is None:
            child.kill()
            child.wait()
        reap_owned_descendants()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print("Private native network failed: " + str(error), file=sys.stderr, flush=True)
        raise SystemExit(1)
