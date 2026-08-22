#!/usr/bin/env python3
"""Mock contracts for the protected physical-iPad acceptance executor."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import fcntl
import os
import plistlib
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXECUTOR = ROOT / "ios/ci/ipad-device-acceptance.py"
SOURCE_REVISION = "b" * 40
CANDIDATE_SHA = "a" * 64
DEVICE_ID = "00008110-001234567890001E"
BUNDLE_ID = "org.overte.interface.dev"
GATES = (ROOT / "ios/tests/fixtures/entity-gates/success.log").read_text(encoding="utf-8")


def make_app(root: Path) -> Path:
    app = root / "Overte.app"
    (app / "_CodeSignature").mkdir(parents=True)
    (app / "_CodeSignature/CodeResources").write_text("signed", encoding="utf-8")
    (app / "embedded.mobileprovision").write_text("fixture", encoding="utf-8")
    executable = app / "Overte"
    executable.write_text("fixture", encoding="utf-8")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    with (app / "Info.plist").open("wb") as stream:
        plistlib.dump({"CFBundleIdentifier": BUNDLE_ID, "CFBundleExecutable": "Overte"}, stream)
    return app


def make_fake_xcrun(bin_dir: Path) -> Path:
    fake = bin_dir / "xcrun"
    fake.write_text(
        r'''#!/usr/bin/env python3
import json
import os
import pathlib
import sys
import time

args = sys.argv[1:]
with pathlib.Path(os.environ["FAKE_XCRUN_LOG"]).open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(args) + "\n")

def json_output(payload):
    if "--json-output" not in args:
        return
    path = pathlib.Path(args[args.index("--json-output") + 1])
    path.write_text(json.dumps(payload), encoding="utf-8")

if args == ["devicectl", "help"]:
    print("devicectl fixture help")
elif args == ["devicectl", "device", "process", "launch", "--help"]:
    print("--console --terminate-existing")
elif args[:3] == ["devicectl", "list", "devices"]:
    identifier = os.environ["FAKE_DEVICE_ID"]
    if os.environ.get("FAKE_DEVICE_MODE") == "wrong":
        identifier = "00008110-WRONGDEVICE00001"
    json_output({
        "result": {"devices": [{
            "identifier": identifier,
            "connectionProperties": {"tunnelState": "connected", "pairingState": "paired"},
            "deviceProperties": {
                "developerModeStatus": "enabled", "ddiServicesAvailable": True,
                "osVersionNumber": "18.5", "name": "Private Owner iPad"
            },
            "hardwareProperties": {
                "deviceType": "iPad", "productType": "iPad14,5", "marketingName": "iPad Pro"
            }
        }]}
    })
elif args[:5] == ["devicectl", "device", "info", "details", "--device"]:
    json_output({
        "result": {
            "identifier": os.environ["FAKE_DEVICE_ID"],
            "deviceProperties": {"osVersionNumber": "18.5"},
            "hardwareProperties": {"deviceType": "iPad", "productType": "iPad14,5"}
        }
    })
elif args[:5] == ["devicectl", "device", "install", "app", "--device"]:
    if os.environ.get("FAKE_DEVICE_MODE") == "install-failure":
        raise SystemExit(23)
    json_output({"result": {"installed": True}})
elif args[:5] == ["devicectl", "device", "process", "launch", "--device"]:
    if os.environ.get("FAKE_DEVICE_MODE") == "timeout":
        time.sleep(30)
    elif os.environ.get("FAKE_DEVICE_MODE") == "oversized":
        print("OVERTE_IOS_ENTITY_GATE " + "x" * 70000, flush=True)
    else:
        print("private token=must-not-survive")
        print(os.environ["FAKE_GATE_LOG"], end="", flush=True)
else:
    raise SystemExit(19)
''',
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    return fake


def run_executor(
    root: Path,
    app: Path,
    output: Path,
    confirmation: str,
    mode: str = "success",
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{root / 'bin'}:{environment['PATH']}",
            "TMPDIR": str(root / "private-tmp"),
            "OVERTE_IOS_IPAD_DEVICE_ID_FILE": str(root / "device-id"),
            "OVERTE_IOS_IPAD_LOCK_FILE": str(root / "device.lock"),
            "OVERTE_IOS_IPAD_COMMAND_TIMEOUT_SECONDS": "2",
            "OVERTE_IOS_IPAD_INSTALL_TIMEOUT_SECONDS": "2",
            "OVERTE_IOS_IPAD_LAUNCH_TIMEOUT_SECONDS": "0.2" if mode == "timeout" else "2",
            "FAKE_XCRUN_LOG": str(root / "xcrun-commands.jsonl"),
            "FAKE_DEVICE_ID": DEVICE_ID,
            "FAKE_DEVICE_MODE": mode,
            "FAKE_GATE_LOG": GATES,
        }
    )
    return subprocess.run(
        [
            sys.executable,
            str(EXECUTOR),
            "--app", str(app),
            "--bundle-id", BUNDLE_ID,
            "--source-revision", SOURCE_REVISION,
            "--candidate-sha256", CANDIDATE_SHA,
            "--output-dir", str(output),
            "--confirmation", confirmation,
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=10,
    )


def private_json_paths(command_log: Path) -> list[Path]:
    paths: list[Path] = []
    if not command_log.exists():
        return paths
    for line in command_log.read_text(encoding="utf-8").splitlines():
        arguments = json.loads(line)
        if "--json-output" in arguments:
            paths.append(Path(arguments[arguments.index("--json-output") + 1]))
    return paths


def assert_private_cleanup(root: Path) -> None:
    for path in private_json_paths(root / "xcrun-commands.jsonl"):
        assert not path.exists(), path
    assert list((root / "private-tmp").iterdir()) == [], list((root / "private-tmp").iterdir())


def assert_identifier_private(result: subprocess.CompletedProcess[str]) -> None:
    allowed_mask = f"::add-mask::{DEVICE_ID}"
    leaks = [
        line
        for line in (result.stdout + result.stderr).splitlines()
        if DEVICE_ID in line and line != allowed_mask
    ]
    assert not leaks, leaks


with tempfile.TemporaryDirectory(prefix="overte-ipad-device-contract-") as temporary:
    root = Path(temporary)
    (root / "bin").mkdir()
    (root / "private-tmp").mkdir()
    make_fake_xcrun(root / "bin")
    app = make_app(root)
    identity = root / "device-id"
    identity.write_text(DEVICE_ID + "\n", encoding="utf-8")
    identity.chmod(0o600)

    # Authorization is validated before even a read-only devicectl help/list call.
    denied = run_executor(root, app, root / "denied-output", "INSTALL " + "0" * 64)
    assert denied.returncode == 2, (denied.stdout, denied.stderr)
    assert not (root / "xcrun-commands.jsonl").exists()
    assert_identifier_private(denied)

    wrong = run_executor(root, app, root / "wrong-output", f"INSTALL {CANDIDATE_SHA}", "wrong")
    assert wrong.returncode == 1, (wrong.stdout, wrong.stderr)
    wrong_commands = [json.loads(line) for line in (root / "xcrun-commands.jsonl").read_text().splitlines()]
    assert any(command[:3] == ["devicectl", "list", "devices"] for command in wrong_commands)
    assert not any(command[:4] == ["devicectl", "device", "install", "app"] for command in wrong_commands)
    assert not any(
        command[:4] == ["devicectl", "device", "process", "launch"] and "--help" not in command
        for command in wrong_commands
    )
    assert_identifier_private(wrong)
    assert_private_cleanup(root)

    (root / "xcrun-commands.jsonl").unlink()
    install_failure = run_executor(
        root, app, root / "install-failure-output", f"INSTALL {CANDIDATE_SHA}", "install-failure"
    )
    assert install_failure.returncode == 23, (install_failure.stdout, install_failure.stderr)
    assert "application installation failed" in install_failure.stderr
    assert_identifier_private(install_failure)
    assert_private_cleanup(root)

    (root / "xcrun-commands.jsonl").unlink()
    success_output = root / "success-output"
    success = run_executor(root, app, success_output, f"INSTALL {CANDIDATE_SHA}")
    assert success.returncode == 0, (success.stdout, success.stderr)
    result = json.loads((success_output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "entity-runtime-smoke-passed" and result["entityGateCount"] == 6
    assert result["requestedDestination"] == "hifi://overte_hub"
    assert result["destinationBoundToGates"] is False
    assert result["containsRawDeviceLog"] is False
    assert result["installedApplicationRemoved"] is False
    archive = success_output / result["entityEvidence"]
    with zipfile.ZipFile(archive) as evidence:
        assert set(evidence.namelist()) == {"entity-gates.log", "entity-gates.json", "handoff.json"}
        contents = b"".join(evidence.read(name) for name in evidence.namelist())
        assert b"must-not-survive" not in contents
        assert DEVICE_ID.encode() not in contents
    public_payload = b"".join(path.read_bytes() for path in success_output.rglob("*") if path.is_file())
    assert DEVICE_ID.encode() not in public_payload
    assert_identifier_private(success)
    assert b"must-not-survive" not in public_payload
    commands = [json.loads(line) for line in (root / "xcrun-commands.jsonl").read_text().splitlines()]
    launch = next(
        command
        for command in commands
        if command[:4] == ["devicectl", "device", "process", "launch"]
        and "--help" not in command
    )
    assert "--terminate-existing" in launch and "--console" in launch
    assert launch[-3:] == ["--", "--url", "hifi://overte_hub"], launch
    assert_private_cleanup(root)

    (root / "xcrun-commands.jsonl").unlink()
    timeout_output = root / "timeout-output"
    timed_out = run_executor(
        root, app, timeout_output, f"INSTALL {CANDIDATE_SHA}", "timeout"
    )
    assert timed_out.returncode == 124, (timed_out.stdout, timed_out.stderr)
    assert "timed out" in timed_out.stderr
    assert_identifier_private(timed_out)
    assert not (timeout_output / "entity-evidence.zip").exists()
    assert_private_cleanup(root)

    (root / "xcrun-commands.jsonl").unlink()
    oversized_output = root / "oversized-output"
    oversized = run_executor(
        root, app, oversized_output, f"INSTALL {CANDIDATE_SHA}", "oversized"
    )
    assert oversized.returncode == 1, (oversized.stdout, oversized.stderr)
    assert "oversized line" in oversized.stderr
    assert not (oversized_output / "entity-evidence.zip").exists()
    assert_private_cleanup(root)

    lock_descriptor = os.open(root / "device.lock", os.O_RDWR)
    try:
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        command_count = len((root / "xcrun-commands.jsonl").read_text().splitlines())
        locked = run_executor(
            root, app, root / "locked-output", f"INSTALL {CANDIDATE_SHA}"
        )
        assert locked.returncode == 2, (locked.stdout, locked.stderr)
        assert "already in use" in locked.stderr
        assert len((root / "xcrun-commands.jsonl").read_text().splitlines()) == command_count
    finally:
        fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        os.close(lock_descriptor)

print("PASS protected iPad device acceptance executor contracts")
