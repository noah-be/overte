#!/usr/bin/env python3
"""Run the privacy-minimal Overte entity smoke on one fixed trusted iPad."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import math
import os
import plistlib
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REVISION = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
DEVICE_IDENTIFIER = re.compile(r"^[A-Za-z0-9.-]{8,128}$")
OS_VERSION = re.compile(r"^[0-9]+(?:[.][0-9]+)+$")
REFERENCE_DESTINATION = "hifi://overte_hub"
NEGATIVE_DEVICE_STATES = {"disconnected", "unavailable", "offline", "unpaired"}
POSITIVE_DEVICE_STATES = {"available", "connected", "paired", "ready"}
MAX_CONSOLE_LINE_BYTES = 64 * 1024
MAX_GATE_LOG_BYTES = 256 * 1024


class AcceptanceFailure(RuntimeError):
    """A deliberately safe diagnostic with an optional child exit status."""

    def __init__(self, message: str, returncode: int = 1):
        super().__init__(message)
        self.returncode = returncode


def load_tool(filename: str, name: str) -> ModuleType:
    path = ROOT / "ios" / "tools" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AcceptanceFailure(f"cannot load required repository tool {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def positive_timeout(environment_name: str, default: float) -> float:
    raw = os.environ.get(environment_name, str(default))
    try:
        value = float(raw)
    except ValueError as error:
        raise AcceptanceFailure(f"{environment_name} must be a positive number", 2) from error
    if not math.isfinite(value) or value <= 0:
        raise AcceptanceFailure(f"{environment_name} must be a positive number", 2)
    return value


def validate_app(app: Path, expected_bundle_id: str) -> Path:
    if app.is_symlink() or not app.is_dir() or app.suffix != ".app":
        raise AcceptanceFailure("--app must name a non-symlink .app directory", 2)
    try:
        resolved = app.resolve(strict=True)
        with (resolved / "Info.plist").open("rb") as stream:
            info = plistlib.load(stream)
    except (OSError, plistlib.InvalidFileException) as error:
        raise AcceptanceFailure("the application has no valid Info.plist", 2) from error
    if not isinstance(info, dict) or info.get("CFBundleIdentifier") != expected_bundle_id:
        raise AcceptanceFailure("the application bundle identifier does not match --bundle-id", 2)
    executable_name = info.get("CFBundleExecutable")
    if not isinstance(executable_name, str) or not executable_name:
        raise AcceptanceFailure("the application has no bundle executable", 2)
    if not (resolved / executable_name).is_file():
        raise AcceptanceFailure("the application bundle executable is missing", 2)
    if not (resolved / "_CodeSignature" / "CodeResources").is_file():
        raise AcceptanceFailure("the application is not structurally code-signed", 2)
    if not (resolved / "embedded.mobileprovision").is_file():
        raise AcceptanceFailure("the application has no embedded provisioning profile", 2)
    return resolved


def read_fixed_device_identifier() -> str:
    raw_path = os.environ.get("OVERTE_IOS_IPAD_DEVICE_ID_FILE", "")
    if not raw_path:
        raise AcceptanceFailure("OVERTE_IOS_IPAD_DEVICE_ID_FILE is required", 2)
    path = Path(raw_path)
    try:
        metadata = path.lstat()
    except OSError as error:
        raise AcceptanceFailure("the configured iPad identity file is unavailable", 2) from error
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        raise AcceptanceFailure("the configured iPad identity file must be a regular file", 2)
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise AcceptanceFailure("the configured iPad identity file must have mode 0600", 2)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise AcceptanceFailure("the configured iPad identity file cannot be read", 2) from error
    if len(lines) != 1 or not DEVICE_IDENTIFIER.fullmatch(lines[0]):
        raise AcceptanceFailure("the configured iPad identity file is invalid", 2)
    identifier = lines[0]
    if os.environ.get("GITHUB_ACTIONS") == "true":
        # GitHub consumes this command before rendering the following logs.
        print(f"::add-mask::{identifier}", flush=True)
    return identifier


def acquire_device_lock() -> int:
    lock_path = Path(
        os.environ.get("OVERTE_IOS_IPAD_LOCK_FILE", "/tmp/overte-ios-ipad-device.lock")
    )
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid():
            raise AcceptanceFailure("the iPad device lock is not a private regular file", 2)
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        raise AcceptanceFailure("the fixed iPad is already in use", 2) from error
    except OSError as error:
        raise AcceptanceFailure("the iPad device lock is unavailable", 2) from error
    return descriptor


def terminate_process_group(process: subprocess.Popen[Any], preferred: int = signal.SIGTERM) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, preferred)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def run_bounded(phase: str, command: list[str], timeout: float) -> bytes:
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as error:
        raise AcceptanceFailure(f"{phase} could not start", 127) from error
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        terminate_process_group(process)
        raise AcceptanceFailure(f"{phase} timed out", 124) from error
    if process.returncode != 0:
        status = process.returncode if 0 < process.returncode < 126 else 1
        raise AcceptanceFailure(f"{phase} failed", status)
    return output


def load_private_json(path: Path, phase: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AcceptanceFailure(f"{phase} did not produce valid JSON") from error
    if not isinstance(payload, dict):
        raise AcceptanceFailure(f"{phase} JSON root is not an object")
    return payload


def recursive_values(value: Any, keys: set[str]) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in keys:
                found.append(child)
            found.extend(recursive_values(child, keys))
    elif isinstance(value, list):
        for child in value:
            found.extend(recursive_values(child, keys))
    return found


def device_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result")
    records = result.get("devices") if isinstance(result, dict) else None
    if not isinstance(records, list) or not all(isinstance(record, dict) for record in records):
        raise AcceptanceFailure("device listing has an unsupported JSON shape")
    return records


def device_identifier(record: dict[str, Any]) -> str | None:
    for key in ("identifier", "deviceIdentifier", "udid"):
        value = record.get(key)
        if isinstance(value, str):
            return value
    return None


def is_ipad(value: Any) -> bool:
    return any(
        isinstance(item, str) and "ipad" in item.lower()
        for item in recursive_values(value, {"deviceType", "productType", "marketingName", "platform"})
    )


def require_reachable_ipad(payload: dict[str, Any], expected_identifier: str) -> dict[str, Any]:
    matches = [record for record in device_records(payload) if device_identifier(record) == expected_identifier]
    if len(matches) != 1:
        raise AcceptanceFailure("the fixed configured iPad is not uniquely reachable")
    record = matches[0]
    if not is_ipad(record):
        raise AcceptanceFailure("the fixed configured device is not an iPad")

    states = {
        str(item).lower()
        for item in recursive_values(
            record, {"state", "connectionState", "tunnelState", "pairingState"}
        )
        if isinstance(item, str)
    }
    ddi_values = recursive_values(record, {"ddiServicesAvailable"})
    if states.intersection(NEGATIVE_DEVICE_STATES):
        raise AcceptanceFailure("the fixed configured iPad is not reachable")
    if not states.intersection(POSITIVE_DEVICE_STATES) and True not in ddi_values:
        raise AcceptanceFailure("the fixed configured iPad has no affirmative reachable state")
    developer_modes = [
        str(item).lower()
        for item in recursive_values(record, {"developerModeStatus"})
        if isinstance(item, str)
    ]
    if developer_modes and any(mode != "enabled" for mode in developer_modes):
        raise AcceptanceFailure("Developer Mode is not enabled on the fixed configured iPad")
    return record


def require_ipad_details(payload: dict[str, Any], expected_identifier: str) -> None:
    result = payload.get("result")
    if not isinstance(result, (dict, list)) or not is_ipad(result):
        raise AcceptanceFailure("device details do not describe an iPad")
    identifiers = [
        item
        for item in recursive_values(result, {"identifier", "deviceIdentifier", "udid"})
        if isinstance(item, str)
    ]
    if identifiers and expected_identifier not in identifiers:
        raise AcceptanceFailure("device details do not match the fixed configured iPad")


def public_device_metadata(record: dict[str, Any]) -> tuple[str, str]:
    model_values = recursive_values(record, {"marketingName", "productType", "deviceType"})
    model = next(
        (item for item in model_values if isinstance(item, str) and "ipad" in item.lower()),
        None,
    )
    os_values = recursive_values(record, {"osVersionNumber", "osVersion"})
    os_version = next((item for item in os_values if isinstance(item, str) and OS_VERSION.fullmatch(item)), None)
    if model is None or os_version is None:
        raise AcceptanceFailure("device listing lacks safe model or OS metadata")
    return model, os_version


def launch_until_gates(
    command: list[str], gate_log: Path, timeout: float, validator: ModuleType
) -> None:
    descriptor = os.open(gate_log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb", buffering=0) as stream:
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as error:
            raise AcceptanceFailure("application launch could not start", 127) from error

        capture: dict[str, Any] = {"lines": [], "bytes": 0, "error": None}
        capture_lock = threading.Lock()

        def collect_gate_lines() -> None:
            assert process.stdout is not None
            while True:
                raw = process.stdout.readline(MAX_CONSOLE_LINE_BYTES + 1)
                if not raw:
                    return
                if len(raw) > MAX_CONSOLE_LINE_BYTES and not raw.endswith(b"\n"):
                    with capture_lock:
                        capture["error"] = "application console emitted an oversized line"
                    return
                if validator.PREFIX.encode("ascii") not in raw:
                    continue
                with capture_lock:
                    next_size = int(capture["bytes"]) + len(raw)
                    if next_size > MAX_GATE_LOG_BYTES:
                        capture["error"] = "application emitted excessive entity gate telemetry"
                        return
                    capture["bytes"] = next_size
                    capture["lines"].append(raw.decode("utf-8", errors="replace"))
                    stream.write(raw)

        reader = threading.Thread(target=collect_gate_lines, name="ipad-gate-reader", daemon=True)
        reader.start()
        deadline = time.monotonic() + timeout
        while True:
            status = process.poll()
            with capture_lock:
                capture_error = capture["error"]
                lines = list(capture["lines"])
            if capture_error:
                terminate_process_group(process)
                reader.join(timeout=1)
                raise AcceptanceFailure(str(capture_error))
            report = validator.validate(lines)

            if status is not None:
                reader.join(timeout=1)
                with capture_lock:
                    capture_error = capture["error"]
                    lines = list(capture["lines"])
                if capture_error:
                    raise AcceptanceFailure(str(capture_error))
                report = validator.validate(lines)
                if status != 0:
                    safe_status = status if 0 < status < 126 else 1
                    raise AcceptanceFailure("application launch failed", safe_status)
                if not report.get("accepted"):
                    raise AcceptanceFailure("application exited without complete entity gates")
                return

            if report.get("accepted"):
                # The acceptance objective is complete. Stop only the host-side
                # console attachment; the installed application is not uninstalled.
                terminate_process_group(process, signal.SIGINT)
                reader.join(timeout=1)
                return

            if time.monotonic() >= deadline:
                terminate_process_group(process)
                reader.join(timeout=1)
                raise AcceptanceFailure("application launch timed out", 124)
            time.sleep(0.05)


def write_private_json(path: Path, payload: dict[str, Any]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument(
        "--candidate-sha256", "--source-artifact-sha256", dest="candidate_sha256", required=True
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--confirmation", required=True)
    return parser.parse_args()


def execute(args: argparse.Namespace) -> None:
    if REVISION.fullmatch(args.source_revision) is None:
        raise AcceptanceFailure("--source-revision must be a lowercase 40-character Git SHA", 2)
    if DIGEST.fullmatch(args.candidate_sha256) is None:
        raise AcceptanceFailure("--candidate-sha256 must be a lowercase SHA-256", 2)
    if args.confirmation != f"INSTALL {args.candidate_sha256}":
        raise AcceptanceFailure("installation confirmation does not match the candidate SHA-256", 2)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*(?:[.][A-Za-z0-9][A-Za-z0-9-]*)+", args.bundle_id):
        raise AcceptanceFailure("--bundle-id is invalid", 2)
    app = validate_app(args.app, args.bundle_id)
    device_id = read_fixed_device_identifier()
    device_lock = acquire_device_lock()

    if args.output_dir.exists():
        raise AcceptanceFailure("--output-dir must not already exist", 2)
    try:
        args.output_dir.mkdir(mode=0o700, parents=False)
    except OSError as error:
        raise AcceptanceFailure("could not create the output directory", 2) from error

    command_timeout = positive_timeout("OVERTE_IOS_IPAD_COMMAND_TIMEOUT_SECONDS", 330)
    install_timeout = positive_timeout("OVERTE_IOS_IPAD_INSTALL_TIMEOUT_SECONDS", 600)
    launch_timeout = positive_timeout("OVERTE_IOS_IPAD_LAUNCH_TIMEOUT_SECONDS", 480)
    validator = load_tool("validate-entity-gate-log.py", "ipad_entity_gate_validator")
    evidence_tool = load_tool("prepare-entity-evidence.py", "ipad_entity_evidence")

    private_root = Path(tempfile.mkdtemp(prefix="overte-ipad-acceptance-"))
    os.chmod(private_root, 0o700)
    list_json = private_root / "devices.json"
    detail_json = private_root / "details.json"
    install_json = private_root / "install.json"
    gate_log = private_root / "entity-gates.log"
    try:
        run_bounded("devicectl help", ["xcrun", "devicectl", "help"], command_timeout)
        launch_help = run_bounded(
            "devicectl launch help",
            ["xcrun", "devicectl", "device", "process", "launch", "--help"],
            command_timeout,
        )
        if not all(token in launch_help for token in (b"--console", b"--terminate-existing")):
            raise AcceptanceFailure("devicectl launch does not expose required options")
        devicectl_timeout = str(max(1, math.ceil(command_timeout)))
        run_bounded(
            "device listing",
            [
                "xcrun", "devicectl", "list", "devices", "--quiet", "--timeout",
                devicectl_timeout, "--json-output", str(list_json),
            ],
            command_timeout,
        )
        record = require_reachable_ipad(load_private_json(list_json, "device listing"), device_id)
        model, os_version = public_device_metadata(record)

        run_bounded(
            "device details",
            [
                "xcrun", "devicectl", "device", "info", "details", "--device", device_id,
                "--quiet", "--timeout", devicectl_timeout, "--json-output", str(detail_json),
            ],
            command_timeout,
        )
        require_ipad_details(load_private_json(detail_json, "device details"), device_id)

        install_tool_timeout = str(max(1, math.ceil(install_timeout)))
        run_bounded(
            "application installation",
            [
                "xcrun", "devicectl", "device", "install", "app", "--device", device_id,
                "--quiet", "--timeout", install_tool_timeout, "--json-output", str(install_json),
                str(app),
            ],
            install_timeout,
        )
        load_private_json(install_json, "application installation")

        launch_tool_timeout = str(max(1, math.ceil(launch_timeout)))
        launch_until_gates(
            [
                "xcrun", "devicectl", "device", "process", "launch", "--device", device_id,
                "--terminate-existing", "--console", "--timeout", launch_tool_timeout,
                args.bundle_id, "--", "--url", REFERENCE_DESTINATION,
            ],
            gate_log,
            launch_timeout,
            validator,
        )

        evidence_directory = args.output_dir / "entity-evidence"
        evidence_archive = evidence_tool.prepare(
            gate_log,
            evidence_directory,
            {
                "sourceRevision": args.source_revision,
                "bundleSha256": args.candidate_sha256,
                "formFactor": "ipad",
                "osVersion": os_version,
                "deviceModel": model,
            },
        )
        result = {
            "schemaVersion": 1,
            "status": "entity-runtime-smoke-passed",
            "formFactor": "ipad",
            "sourceRevision": args.source_revision,
            "candidateSha256": args.candidate_sha256,
            "bundleIdentifier": args.bundle_id,
            "requestedDestination": REFERENCE_DESTINATION,
            "destinationBoundToGates": False,
            "device": {"model": model, "osVersion": os_version},
            "entityEvidence": evidence_archive.name,
            "entityGateCount": 6,
            "containsRawDeviceLog": False,
            "installedApplicationRemoved": False,
        }
        write_private_json(args.output_dir / "result.json", result)
    finally:
        # Device identifiers and unfiltered application output never survive the
        # process. Cleanup failures must not replace the causal test failure.
        for private_file in (gate_log, list_json, detail_json, install_json):
            try:
                private_file.unlink(missing_ok=True)
            except OSError:
                pass
        shutil.rmtree(private_root, ignore_errors=True)
        os.close(device_lock)


def main() -> int:
    args = parse_arguments()
    try:
        execute(args)
    except AcceptanceFailure as error:
        print(f"error: {error}", file=sys.stderr)
        return error.returncode
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        # Repository tools already use privacy-safe errors. Do not render child
        # output, command lines, device identifiers, or private temporary paths.
        print(f"error: iPad runtime evidence failed: {type(error).__name__}", file=sys.stderr)
        return 1
    print("Overte iPad runtime acceptance passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
