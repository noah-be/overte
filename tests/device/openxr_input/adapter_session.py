#!/usr/bin/env python3
"""Durable, privacy-safe host session for Pico OpenXR adapter operations."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import time
from typing import Iterator

from .android_transport import AndroidOpenXrTransport, TransportError

if os.name == "nt":
    import msvcrt
else:
    import fcntl


STATE_SCHEMA_VERSION = 1
PROFILE_PATH = Path(__file__).parent / "profiles/pico4-overte-controller.json"


class AdapterSessionError(RuntimeError):
    """The local Pico input session cannot safely continue."""


def _private_directory(path: Path, *, create: bool) -> Path:
    if not path.is_absolute():
        raise AdapterSessionError("Pico OpenXR state directory must be absolute")
    if create:
        path.mkdir(mode=0o700, parents=False, exist_ok=True)
    try:
        info = path.lstat()
    except FileNotFoundError as error:
        raise AdapterSessionError("Pico OpenXR state directory does not exist") from error
    if (not stat.S_ISDIR(info.st_mode) or path.is_symlink()
            or (hasattr(os, "getuid") and info.st_uid != os.getuid())
            or stat.S_IMODE(info.st_mode) & 0o077):
        raise AdapterSessionError("Pico OpenXR state directory is not private")
    return path


def resolve_state_directory() -> Path:
    """Resolve an explicit or per-user runtime directory without using /tmp."""
    explicit = os.environ.get("OVERTE_PICO_OPENXR_STATE_DIR")
    if explicit:
        return _private_directory(Path(explicit), create=False)
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        raise AdapterSessionError(
            "OVERTE_PICO_OPENXR_STATE_DIR or XDG_RUNTIME_DIR is required")
    base = _private_directory(Path(runtime), create=False)
    return _private_directory(base / "overte-pico-openxr-e2e", create=True)


def isolated_server_port() -> int:
    value = os.environ.get("ANDROID_ADB_SERVER_PORT", "")
    if not value.isdigit():
        raise AdapterSessionError(
            "ANDROID_ADB_SERVER_PORT must select an isolated ADB server")
    port = int(value)
    if not 1024 <= port <= 65535 or port == 5037:
        raise AdapterSessionError(
            "ANDROID_ADB_SERVER_PORT must select a non-default isolated ADB server")
    return port


def pico_openxr_opted_in() -> bool:
    return (os.environ.get("OVERTE_ANDROID_E2E_DEBUG") == "1"
            and os.environ.get("OVERTE_PICO_OPENXR_INPUT") == "1")


def validate_pico_openxr_configuration() -> tuple[int, Path]:
    """Validate all host gates when the explicit runtime opt-in is present."""
    if not pico_openxr_opted_in():
        raise AdapterSessionError("Pico OpenXR input is not explicitly enabled")
    return isolated_server_port(), resolve_state_directory()


class PicoOpenXrAdapterSession:
    """Keep the native nonce/sequence stable across short-lived adapter CLIs."""

    def __init__(self, transport: AndroidOpenXrTransport, selector: str,
                 state_directory: Path) -> None:
        self.transport = transport
        self.profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        key = hashlib.sha256(
            f"org.overte.pico\0{selector}".encode("utf-8")).hexdigest()[:32]
        self.state_path = state_directory / f"session-{key}.json"
        self.lock_path = state_directory / f"session-{key}.lock"

    @contextmanager
    def _lock(self) -> Iterator[None]:
        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            if os.name == "nt":
                msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
            else:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            if os.name == "nt":
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _load(self) -> dict | None:
        if not self.state_path.exists():
            return None
        info = self.state_path.lstat()
        if (not stat.S_ISREG(info.st_mode) or self.state_path.is_symlink()
                or (hasattr(os, "getuid") and info.st_uid != os.getuid())
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise AdapterSessionError("Pico OpenXR session state is not private")
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise AdapterSessionError("Pico OpenXR session state is invalid") from error
        if (not isinstance(value, dict)
                or set(value) != {"schemaVersion", "processIdentity", "sessionNonce",
                                  "nextSequence"}
                or value["schemaVersion"] != STATE_SCHEMA_VERSION
                or not isinstance(value["processIdentity"], str)
                or not value["processIdentity"]
                or not isinstance(value["sessionNonce"], str)
                or len(value["sessionNonce"]) != 64
                or any(character not in "0123456789abcdef"
                       for character in value["sessionNonce"])
                or isinstance(value["nextSequence"], bool)
                or not isinstance(value["nextSequence"], int)
                or not 1 <= value["nextSequence"] <= 0xFFFFFFFF):
            raise AdapterSessionError("Pico OpenXR session state is invalid")
        return value

    def _save_path(self, path: Path, value: dict) -> None:
        payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
        temporary = path.with_name(
            f".{path.name}.{secrets.token_hex(8)}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _save(self, value: dict) -> None:
        self._save_path(self.state_path, value)

    def _new_state(self, process_identity: str) -> dict:
        return {
            "schemaVersion": STATE_SCHEMA_VERSION,
            "processIdentity": process_identity,
            "sessionNonce": secrets.token_hex(32),
            "nextSequence": 1,
        }

    def begin(self, process_identity: str) -> None:
        """Bind the complete E2E run to the one explicitly launched process."""
        if not isinstance(process_identity, str) or not process_identity:
            raise AdapterSessionError("Pico application process identity is unavailable")
        with self._lock():
            if self._load() is not None:
                raise AdapterSessionError("Pico E2E launcher session is already established")
            self._save(self._new_state(process_identity))

    def require_process_identity(self, process_identity: str) -> None:
        if not isinstance(process_identity, str) or not process_identity:
            raise AdapterSessionError("Pico application process identity is unavailable")
        with self._lock():
            state = self._load()
            if state is None:
                raise AdapterSessionError("Pico E2E launcher session is not established")
            if state["processIdentity"] != process_identity:
                raise AdapterSessionError("Pico E2E launcher process identity changed")

    @staticmethod
    def _ack_timeout() -> float:
        raw = os.environ.get("OVERTE_PICO_OPENXR_ACK_SECONDS", "8")
        try:
            value = float(raw)
        except ValueError as error:
            raise AdapterSessionError(
                "OVERTE_PICO_OPENXR_ACK_SECONDS must be numeric") from error
        if not 1.0 <= value <= 15.0:
            raise AdapterSessionError(
                "OVERTE_PICO_OPENXR_ACK_SECONDS must be from 1 through 15")
        return value

    def _wait_for_ack(self, nonce: str, sequence: int) -> dict:
        deadline = time.monotonic() + self._ack_timeout()
        last_error: TransportError | None = None
        while time.monotonic() < deadline:
            try:
                status = self.transport.read_status(
                    expected_nonce=nonce, expected_sequence=sequence)
                if status["state"] == "error" or status["enabled"] is not True:
                    raise AdapterSessionError("native Pico OpenXR input rejected the command")
                return status
            except TransportError as error:
                last_error = error
                time.sleep(0.1)
        raise AdapterSessionError("native Pico OpenXR input acknowledgement timed out") from last_error

    def _wait_for_neutral(self, nonce: str, sequence: int) -> dict:
        deadline = time.monotonic() + self._ack_timeout()
        last_error: TransportError | None = None
        while time.monotonic() < deadline:
            try:
                status = self.transport.read_status(expected_nonce=nonce)
                if (status["acceptedSequence"] == sequence
                        and status["state"] == "neutral"):
                    return status
                if status["state"] == "error":
                    raise AdapterSessionError(
                        "native Pico OpenXR input failed before neutralization")
            except TransportError as error:
                last_error = error
            time.sleep(0.1)
        raise AdapterSessionError(
            "native Pico OpenXR input did not confirm an inter-command neutral window"
        ) from last_error

    def _wait_for_view_application(self, nonce: str, sequence: int) -> dict:
        deadline = time.monotonic() + self._ack_timeout()
        last_error: TransportError | None = None
        while time.monotonic() < deadline:
            try:
                status = self.transport.read_status(
                    expected_nonce=nonce, expected_sequence=sequence)
                if status["state"] == "error" or status["enabled"] is not True:
                    raise AdapterSessionError(
                        "native Pico OpenXR view override failed before consumption")
                if (status["state"] == "active"
                        and status["viewAppliedSequence"] == sequence):
                    return status
            except TransportError as error:
                last_error = error
            time.sleep(0.1)
        raise AdapterSessionError(
            "native Pico OpenXR view override was not consumed by a view query"
        ) from last_error

    def _wait_for_controller_application(self, nonce: str, sequence: int,
                                         operation: str) -> dict:
        deadline = time.monotonic() + self._ack_timeout()
        last_error: TransportError | None = None
        while time.monotonic() < deadline:
            try:
                status = self.transport.read_status(
                    expected_nonce=nonce, expected_sequence=sequence)
                if status["state"] == "error" or status["enabled"] is not True:
                    raise AdapterSessionError(
                        "native Pico OpenXR controller override failed before consumption")
                vector_applied = (operation == "input.move" and
                                  status["vectorAppliedSequence"] == sequence and
                                  abs(float(status["leftThumbstickAppliedY"])) >= 0.01)
                left_secondary_applied = (
                    operation in {"tablet.open", "tablet.close"} and
                    status["booleanAppliedSequence"] == sequence and
                    status["leftSecondaryApplied"] is True)
                right_secondary_applied = (
                    operation in {"input.jump", "input.fly"} and
                    status["booleanAppliedSequence"] == sequence and
                    status["rightSecondaryApplied"] is True)
                boolean_applied = left_secondary_applied or right_secondary_applied
                # Applied-sequence evidence intentionally survives the native
                # neutral window. It proves historical consumption, but must
                # not let a completed pulse masquerade as input that is still
                # active when the behavioral test starts observing it.
                if status["state"] == "active" and (vector_applied or boolean_applied):
                    return status
            except TransportError as error:
                last_error = error
            time.sleep(0.1)
        raise AdapterSessionError(
            "native Pico OpenXR controller override was not consumed by an action query"
        ) from last_error

    def stage(self, process_identity: str, operation: str, arguments: dict) -> dict:
        if not isinstance(process_identity, str) or not process_identity:
            raise AdapterSessionError("Pico application process identity is unavailable")
        with self._lock():
            state = self._load()
            if state is None:
                raise AdapterSessionError("Pico E2E launcher session is not established")
            if state["processIdentity"] != process_identity:
                raise AdapterSessionError("Pico E2E launcher process identity changed")
            sequence = state["nextSequence"]
            if sequence == 0xFFFFFFFF:
                raise AdapterSessionError("Pico OpenXR input sequence is exhausted")
            neutral_before_command = sequence > 1
            if neutral_before_command:
                self._wait_for_neutral(state["sessionNonce"], sequence - 1)
            envelope = {
                "schemaVersion": 1,
                "sessionNonce": state["sessionNonce"],
                "sequence": sequence,
                "commands": [{
                    "id": f"{operation.replace('.', '-')}-{sequence}",
                    "operation": operation,
                    "arguments": arguments,
                }],
            }
            staged = self.transport.stage(envelope, self.profile)
            state["nextSequence"] = sequence + 1
            # Persist immediately after the device-side grant commit. A later
            # acknowledgement timeout must never replay the committed sequence.
            self._save(state)
            status = self._wait_for_ack(state["sessionNonce"], sequence)
            if operation == "input.look":
                status = self._wait_for_view_application(
                    state["sessionNonce"], sequence)
            elif operation in {
                    "input.fly", "input.jump", "input.move",
                    "tablet.open", "tablet.close"}:
                status = self._wait_for_controller_application(
                    state["sessionNonce"], sequence, operation)
        result = {
            "performed": True,
            "inputDomain": ("head-pose" if operation == "input.look"
                            else "controller-action"),
            "sequence": staged["sequence"],
            "nativeState": status["state"],
            "neutralBeforeCommand": neutral_before_command,
        }
        if operation == "input.look":
            result.update({
                "viewApplied": True,
                "viewYawDegrees": status["viewAppliedYawDegrees"],
                "viewPitchDegrees": status["viewAppliedPitchDegrees"],
            })
        elif operation == "input.move":
            result.update({
                "openXrVectorApplied": True,
                "openXrLeftThumbstickY": status["leftThumbstickAppliedY"],
            })
        elif operation in {"tablet.open", "tablet.close"}:
            result.update({
                "openXrBooleanApplied": True,
                "openXrLeftSecondaryApplied": status["leftSecondaryApplied"],
            })
        elif operation in {"input.jump", "input.fly"}:
            result.update({
                "openXrBooleanApplied": True,
                "openXrRightSecondaryApplied": status["rightSecondaryApplied"],
            })
        return result

    def cleanup(self, process_running: bool) -> None:
        with self._lock():
            state = self._load()
            self.transport.cleanup()
            neutral_observed = not process_running or state is None or state["nextSequence"] == 1
            if process_running and state is not None and state["nextSequence"] > 1:
                deadline = time.monotonic() + min(self._ack_timeout(), 5.0)
                while time.monotonic() < deadline:
                    try:
                        status = self.transport.read_status(
                            expected_nonce=state["sessionNonce"])
                        if status["state"] == "neutral":
                            neutral_observed = True
                            break
                    except TransportError:
                        pass
                    time.sleep(0.1)
            try:
                self.state_path.unlink()
            except FileNotFoundError:
                pass
            if not neutral_observed:
                raise AdapterSessionError(
                    "native Pico OpenXR input did not confirm neutral cleanup")

    def discard_local_state(self) -> None:
        with self._lock():
            try:
                self.state_path.unlink()
            except FileNotFoundError:
                pass
