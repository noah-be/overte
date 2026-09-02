#!/usr/bin/env python3
"""Hardware-free security and protocol tests for wayland_libei_client."""

from __future__ import annotations

import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest

from wayland_libei_client import (
    WaylandInputClient,
    WaylandInputError,
    default_socket_path,
)


class FakeDaemon:
    def __init__(self, directory: Path, response: bytes) -> None:
        self.path = directory / "input.sock"
        self.response = response
        self.request = b""
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(os.fspath(self.path))
        os.chmod(self.path, 0o600)
        self.listener.listen(1)
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self) -> None:
        connection, _ = self.listener.accept()
        with connection:
            while b"\n" not in self.request:
                block = connection.recv(512)
                if not block:
                    break
                self.request += block
            if self.request:
                connection.sendall(self.response)
        self.listener.close()

    def __enter__(self) -> "FakeDaemon":
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        if self.thread.is_alive():
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as wakeup:
                    wakeup.connect(os.fspath(self.path))
            except OSError:
                pass
        self.thread.join(timeout=2)
        self.listener.close()
        self.path.unlink(missing_ok=True)


class WaylandInputClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name) / "target"
        self.directory.mkdir(mode=0o700)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_status_uses_one_bounded_request(self) -> None:
        response = b"OK ready=1 pointer=1 button=1 keyboard=1\n"
        with FakeDaemon(self.directory, response) as daemon:
            status = WaylandInputClient(daemon.path).status()
        self.assertEqual(
            status,
            {"ready": True, "pointer": True, "button": True, "keyboard": True},
        )
        self.assertEqual(daemon.request, b"status\n")

    def test_motion_serializes_only_finite_numbers(self) -> None:
        with FakeDaemon(self.directory, b"OK\n") as daemon:
            WaylandInputClient(daemon.path).motion(12.5, -4.25)
        self.assertEqual(daemon.request, b"motion 12.5 -4.25\n")
        with self.assertRaises(WaylandInputError):
            WaylandInputClient("/absolute/missing.sock").motion(float("nan"), 0)

    def test_server_error_is_not_treated_as_success(self) -> None:
        with FakeDaemon(self.directory, b"ERR not-ready input-devices-unavailable\n") as daemon:
            with self.assertRaisesRegex(WaylandInputError, "not-ready"):
                WaylandInputClient(daemon.path).key(17, "tap")

    def test_group_readable_socket_or_directory_is_rejected(self) -> None:
        with FakeDaemon(self.directory, b"OK\n") as daemon:
            os.chmod(daemon.path, 0o660)
            with self.assertRaisesRegex(WaylandInputError, "private user-owned socket"):
                WaylandInputClient(daemon.path).shutdown()
        os.chmod(self.directory, 0o750)
        with FakeDaemon(self.directory, b"OK\n") as daemon:
            with self.assertRaisesRegex(WaylandInputError, "directory"):
                WaylandInputClient(daemon.path).shutdown()

    def test_non_socket_endpoint_is_rejected(self) -> None:
        endpoint = self.directory / "input.sock"
        endpoint.write_text("not a socket", encoding="utf-8")
        endpoint.chmod(0o600)
        with self.assertRaisesRegex(WaylandInputError, "private user-owned socket"):
            WaylandInputClient(endpoint).status()

    def test_target_cannot_escape_runtime_root(self) -> None:
        with self.assertRaises(WaylandInputError):
            default_socket_path("../other", self.directory)
        expected = self.directory / "fedora-visible" / "input.sock"
        self.assertEqual(default_socket_path("fedora-visible", self.directory), expected)

    def test_codes_and_states_are_validated_before_connect(self) -> None:
        client = WaylandInputClient("/absolute/missing.sock")
        with self.assertRaises(WaylandInputError):
            client.key(0, "down")
        with self.assertRaises(WaylandInputError):
            client.key(17, "hold")
        with self.assertRaises(WaylandInputError):
            client.button(1, "click")


if __name__ == "__main__":
    unittest.main()
