#!/usr/bin/env python3
"""Fail-closed app-private ADB transport for the Pico E2E OpenXR layer."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import shlex
import subprocess
import time
from typing import Any, Callable

from .controller_protocol import compile_envelope, validate_profile


PACKAGE = "org.overte.pico"
BUILD_MARKER = "OVERTE_E2E_OPENXR_INPUT_V1"
CONSUMER = "XR_APILAYER_OVERTE_e2e_input"
CHANNEL = "app-private-file"
PROFILE_ID = "overte-pico4-controller-v1"
PROFILE_SHA256 = "922e091c38f5cb1ec6c3e55c80b81de0a876524d951318c61e7feb4821eab481"
REMOTE_DIRECTORY = "files/overte-e2e/openxr-input"
MAX_GRANT_LIFETIME_MS = 5 * 60 * 1000
ADB_TIMEOUT_SECONDS = 20
Runner = Callable[..., subprocess.CompletedProcess]


class TransportError(RuntimeError):
    """The private device transport or native acknowledgement failed."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def profile_fingerprint(profile: dict[str, Any]) -> str:
    validate_profile(profile)
    return hashlib.sha256(_canonical(profile)).hexdigest()


class AndroidOpenXrTransport:
    def __init__(self, adb: str | Path, selector: str, *, server_port: int = 5038,
                 runner: Runner = subprocess.run) -> None:
        self.adb = str(Path(adb))
        self.selector = selector
        self.server_port = server_port
        self.runner = runner
        if (not self.selector or any(character.isspace() for character in self.selector)
                or len(self.selector) > 255):
            raise TransportError("private Pico selector is invalid")
        if isinstance(server_port, bool) or not isinstance(server_port, int) \
                or not 1024 <= server_port <= 65535:
            raise TransportError("isolated ADB server port is invalid")
        if not Path(self.adb).is_file():
            raise TransportError("configured ADB executable does not exist")

    def _base(self, *, selected: bool = True) -> list[str]:
        command = [self.adb, "-P", str(self.server_port)]
        if selected:
            command += ["-s", self.selector]
        return command

    def _run(self, command: list[str], *, purpose: str,
             payload: bytes | None = None) -> bytes:
        if purpose not in {
                "discovery", "target-state", "commands-write", "grant-write",
                "status-read", "cleanup"}:
            raise TransportError("isolated Pico ADB operation purpose is invalid")
        try:
            result = self.runner(
                command, input=payload, capture_output=True, check=False,
                timeout=ADB_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as error:
            raise TransportError(f"isolated Pico ADB {purpose} timed out") from error
        except OSError as error:
            raise TransportError(f"isolated Pico ADB {purpose} failed") from error
        if result.returncode:
            raise TransportError(f"isolated Pico ADB {purpose} failed")
        return result.stdout if isinstance(result.stdout, bytes) else result.stdout.encode("utf-8")

    def require_exclusive_target(self) -> None:
        output = self._run([*self._base(selected=False), "devices"],
                           purpose="discovery").decode(
            "utf-8", errors="strict")
        devices = []
        for line in output.splitlines()[1:]:
            fields = line.split()
            if len(fields) >= 2:
                devices.append((fields[0], fields[1]))
        if devices != [(self.selector, "device")]:
            raise TransportError("isolated ADB server must expose exactly the private Pico target")
        state = self._run([*self._base(), "get-state"],
                          purpose="target-state").decode("utf-8").strip()
        if state != "device":
            raise TransportError("private Pico target is not ready")

    def _atomic_write(self, name: str, payload: bytes) -> None:
        if name not in {"commands.json", "grant.json"}:
            raise TransportError("refusing non-allowlisted remote file")
        if not payload or len(payload) > 64 * 1024:
            raise TransportError("OpenXR input payload size is invalid")
        # name is selected above, not supplied by an envelope. All remote paths
        # and the package are fixed literals; JSON is sent only on stdin.
        byte_count = len(payload)
        script = (
            "umask 077; "
            f"directory='{REMOTE_DIRECTORY}'; "
            f"expected={byte_count}; "
            'mkdir -p "$directory" && chmod 700 "$directory" || exit 20; '
            f"temporary=\"$directory/{name}.tmp\"; "
            f"destination=\"$directory/{name}\"; "
            'rm -f "$temporary"; '
            # Pico WLAN-ADB does not reliably propagate stdin EOF to a remote
            # dd. An exact one-byte block count makes completion depend only
            # on the already validated payload length, never on stream EOF.
            'dd bs=1 count="$expected" of="$temporary" 2>/dev/null '
            '&& actual=$(wc -c < "$temporary") && [ "$actual" -eq "$expected" ] '
            '&& chmod 600 "$temporary" && mv -f "$temporary" "$destination"'
        )
        purpose = "commands-write" if name == "commands.json" else "grant-write"
        remote = f"run-as {PACKAGE} sh -c {shlex.quote(script)}"
        # `shell -T` is ADB's documented non-PTY stdin transport. `exec-out`
        # is retained only for read-only/no-stdin calls below.
        self._run([*self._base(), "shell", "-T", remote],
                  purpose=purpose, payload=payload)

    def stage(self, envelope: dict[str, Any], profile: dict[str, Any], *,
              now_ms: int | None = None, lifetime_ms: int = 60_000) -> dict[str, Any]:
        self.require_exclusive_target()
        compiled = compile_envelope(envelope, profile)
        if isinstance(lifetime_ms, bool) or not isinstance(lifetime_ms, int) \
                or not 1_000 <= lifetime_ms <= MAX_GRANT_LIFETIME_MS:
            raise TransportError("grant lifetime is outside the safety boundary")
        issued = int(time.time() * 1000) if now_ms is None else now_ms
        if isinstance(issued, bool) or not isinstance(issued, int) or issued < 1:
            raise TransportError("grant clock is invalid")
        fingerprint = profile_fingerprint(profile)
        if profile.get("profileId") != PROFILE_ID or fingerprint != PROFILE_SHA256:
            raise TransportError("controller profile does not match the native Pico layer")
        grant = {
            "schemaVersion": 1,
            "buildMarker": BUILD_MARKER,
            "testBuild": True,
            "runtimeOptIn": True,
            "channel": CHANNEL,
            "consumer": CONSUMER,
            "bindingProfileSha256": fingerprint,
            "sessionNonce": envelope["sessionNonce"],
            "sequence": envelope["sequence"],
            "expiresEpochMs": issued + lifetime_ms,
        }
        # grant.json is the native commit marker. Writing it last prevents the
        # layer from accepting a new grant with an older command envelope.
        self._atomic_write("commands.json", _canonical(envelope))
        self._atomic_write("grant.json", _canonical(grant))
        return {
            "sequence": compiled["sequence"],
            "sessionNonce": "[redacted]",
            "bindingProfileSha256": grant["bindingProfileSha256"],
            "watchdogDeadlineMs": compiled["watchdogDeadlineMs"],
        }

    def read_status(self, *, expected_nonce: str | None = None,
                    expected_sequence: int | None = None) -> dict[str, Any]:
        self.require_exclusive_target()
        script = (
            f"file='{REMOTE_DIRECTORY}/status.json'; "
            '[ -f "$file" ] && [ ! -L "$file" ] && cat "$file"'
        )
        remote = f"run-as {PACKAGE} sh -c {shlex.quote(script)}"
        raw = self._run([*self._base(), "exec-out", remote], purpose="status-read")
        try:
            status = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TransportError("native OpenXR input status is invalid") from error
        required = {
            "schemaVersion", "buildMarker", "consumer", "profileId",
            "bindingProfileSha256", "enabled", "acceptedSequence", "acceptedNonce",
            "activeCommandId", "state", "detail", "updatedEpochMs",
        }
        if not isinstance(status, dict) or set(status) != required:
            raise TransportError("native OpenXR input status contract is invalid")
        if (status["schemaVersion"] != 1 or status["buildMarker"] != BUILD_MARKER
                or status["consumer"] != CONSUMER
                or status["profileId"] != PROFILE_ID
                or status["bindingProfileSha256"] != PROFILE_SHA256):
            raise TransportError("native OpenXR input status identity mismatch")
        if (not isinstance(status["enabled"], bool)
                or isinstance(status["acceptedSequence"], bool)
                or not isinstance(status["acceptedSequence"], int)
                or not 0 <= status["acceptedSequence"] <= 0xFFFFFFFF
                or not isinstance(status["acceptedNonce"], str)
                or (status["acceptedNonce"] != ""
                    and re.fullmatch(r"[0-9a-f]{32,128}", status["acceptedNonce"]) is None)
                or not isinstance(status["activeCommandId"], str)
                or (status["activeCommandId"] != ""
                    and re.fullmatch(r"[a-z][a-z0-9-]{0,63}",
                                     status["activeCommandId"]) is None)
                or status["state"] not in {"accepted", "active", "neutral", "error"}
                or not isinstance(status["detail"], str)
                or not 1 <= len(status["detail"]) <= 64
                or isinstance(status["updatedEpochMs"], bool)
                or not isinstance(status["updatedEpochMs"], (int, float))
                or not math.isfinite(status["updatedEpochMs"])
                or status["updatedEpochMs"] < 1):
            raise TransportError("native OpenXR input status values are invalid")
        if expected_nonce is not None and status["acceptedNonce"] != expected_nonce:
            raise TransportError("native OpenXR input status nonce mismatch")
        if expected_sequence is not None and status["acceptedSequence"] != expected_sequence:
            raise TransportError("native OpenXR input status sequence mismatch")
        status["acceptedNonce"] = "[redacted]"
        return status

    def cleanup(self) -> None:
        self.require_exclusive_target()
        script = (
            f"directory='{REMOTE_DIRECTORY}'; "
            'rm -f "$directory/grant.json" "$directory/commands.json" '
            '"$directory/grant.json.tmp" "$directory/commands.json.tmp"'
        )
        remote = f"run-as {PACKAGE} sh -c {shlex.quote(script)}"
        self._run([*self._base(), "exec-out", remote], purpose="cleanup")
