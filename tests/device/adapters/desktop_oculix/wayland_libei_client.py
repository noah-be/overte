#!/usr/bin/env python3
"""Same-user client for the persistent Wayland/libei input daemon.

This module deliberately contains no portal code.  Starting authorization and
owning the long-lived portal/libei session belongs to ``wayland_libei_daemon``;
adapter operations only connect to its private target socket.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import socket
import stat
from typing import Final


TARGET_PATTERN: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")
MAX_RESPONSE: Final = 4096
BTN_MISC: Final = 0x100
KEY_MAX: Final = 0x2FF


class WaylandInputError(RuntimeError):
    """The daemon endpoint or an input command was rejected."""


def _validated_target(value: str) -> str:
    if not isinstance(value, str) or not TARGET_PATTERN.fullmatch(value):
        raise WaylandInputError("target must be a safe 1-80 character identifier")
    return value


def default_socket_path(target: str, runtime_root: str | os.PathLike[str] | None = None) -> Path:
    """Return the target socket without creating or changing filesystem state."""
    target = _validated_target(target)
    if runtime_root is None:
        xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
        if not xdg_runtime or not os.path.isabs(xdg_runtime):
            raise WaylandInputError("XDG_RUNTIME_DIR must be an absolute path")
        root = Path(xdg_runtime) / "overte-device-lab" / "wayland-input"
    else:
        root = Path(runtime_root)
        if not root.is_absolute():
            raise WaylandInputError("runtime root must be absolute")
    return root / target / "input.sock"


def _require_private_endpoint(path: Path) -> None:
    try:
        parent = path.parent.stat(follow_symlinks=False)
        endpoint = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise WaylandInputError(f"input endpoint is unavailable: {exc.strerror}") from exc
    if (not stat.S_ISDIR(parent.st_mode) or stat.S_ISLNK(parent.st_mode)
            or parent.st_uid != os.getuid() or parent.st_mode & 0o077):
        raise WaylandInputError("input endpoint directory must be user-owned mode 0700")
    if (not stat.S_ISSOCK(endpoint.st_mode) or stat.S_ISLNK(endpoint.st_mode)
            or endpoint.st_uid != os.getuid() or endpoint.st_mode & 0o077):
        raise WaylandInputError("input endpoint must be a private user-owned socket")


class WaylandInputClient:
    """One target-scoped command client; the server session remains alive."""

    def __init__(self, socket_path: str | os.PathLike[str], *, timeout: float = 5.0) -> None:
        self.socket_path = Path(socket_path)
        if not self.socket_path.is_absolute():
            raise WaylandInputError("input socket path must be absolute")
        if (not isinstance(timeout, (int, float)) or isinstance(timeout, bool)
                or not math.isfinite(float(timeout)) or not 0.1 <= float(timeout) <= 30.0):
            raise WaylandInputError("timeout must be between 0.1 and 30 seconds")
        self.timeout = float(timeout)

    def _request(self, *fields: str) -> str:
        if (not fields or any(not isinstance(item, str) or not item
                              or re.search(r"\s", item) for item in fields)):
            raise WaylandInputError("protocol fields must be non-empty and whitespace-free")
        request = (" ".join(fields) + "\n").encode("ascii", errors="strict")
        if len(request) > MAX_RESPONSE:
            raise WaylandInputError("input request is too large")
        _require_private_endpoint(self.socket_path)
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self.timeout)
                client.connect(os.fspath(self.socket_path))
                client.sendall(request)
                client.shutdown(socket.SHUT_WR)
                response = bytearray()
                while b"\n" not in response and len(response) <= MAX_RESPONSE:
                    block = client.recv(512)
                    if not block:
                        break
                    response.extend(block)
        except OSError as exc:
            raise WaylandInputError(f"input daemon communication failed: {exc}") from exc
        if len(response) > MAX_RESPONSE or not response.endswith(b"\n") or response.count(b"\n") != 1:
            raise WaylandInputError("input daemon returned a malformed response")
        try:
            text = response[:-1].decode("ascii")
        except UnicodeDecodeError as exc:
            raise WaylandInputError("input daemon returned a non-ASCII response") from exc
        if text == "OK":
            return ""
        if text.startswith("OK "):
            return text[3:]
        if text.startswith("ERR "):
            raise WaylandInputError(f"input daemon rejected the command: {text[4:]}")
        raise WaylandInputError("input daemon returned an unknown response")

    def status(self) -> dict[str, bool]:
        values: dict[str, bool] = {}
        for item in self._request("status").split():
            name, separator, raw = item.partition("=")
            if not separator or raw not in {"0", "1"} or name in values:
                raise WaylandInputError("input daemon returned malformed status")
            values[name] = raw == "1"
        expected = {"ready", "pointer", "button", "keyboard"}
        if set(values) != expected:
            raise WaylandInputError("input daemon returned incomplete status")
        return values

    def motion(self, dx: float, dy: float) -> None:
        values = (dx, dy)
        if any(not isinstance(value, (int, float)) or isinstance(value, bool)
               or not math.isfinite(float(value)) or abs(float(value)) > 100000.0
               for value in values):
            raise WaylandInputError("motion values must be finite and bounded")
        self._request("motion", format(float(dx), ".17g"), format(float(dy), ".17g"))

    def button(self, code: int, state: str) -> None:
        if (not isinstance(code, int) or isinstance(code, bool)
                or not BTN_MISC <= code <= KEY_MAX or state not in {"down", "up", "click"}):
            raise WaylandInputError("button requires an evdev button code and down/up/click")
        self._request("button", str(code), state)

    def key(self, code: int, state: str) -> None:
        if (not isinstance(code, int) or isinstance(code, bool)
                or not 1 <= code <= KEY_MAX or state not in {"down", "up", "tap"}):
            raise WaylandInputError("key requires an evdev keycode and down/up/tap")
        self._request("key", str(code), state)

    def shutdown(self) -> None:
        self._request("shutdown")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    endpoint = parser.add_mutually_exclusive_group(required=True)
    endpoint.add_argument("--socket", type=Path)
    endpoint.add_argument("--target")
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--timeout", type=float, default=5.0)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    motion = commands.add_parser("motion")
    motion.add_argument("dx", type=float)
    motion.add_argument("dy", type=float)
    button = commands.add_parser("button")
    button.add_argument("code", type=int)
    button.add_argument("state", choices=("down", "up", "click"))
    key = commands.add_parser("key")
    key.add_argument("code", type=int)
    key.add_argument("state", choices=("down", "up", "tap"))
    commands.add_parser("shutdown")
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        path = (arguments.socket if arguments.socket is not None else
                default_socket_path(arguments.target, arguments.runtime_root))
        client = WaylandInputClient(path, timeout=arguments.timeout)
        if arguments.command == "status":
            print(json.dumps(client.status(), sort_keys=True, separators=(",", ":")))
        elif arguments.command == "motion":
            client.motion(arguments.dx, arguments.dy)
        elif arguments.command == "button":
            client.button(arguments.code, arguments.state)
        elif arguments.command == "key":
            client.key(arguments.code, arguments.state)
        elif arguments.command == "shutdown":
            client.shutdown()
    except WaylandInputError as exc:
        _parser().error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
