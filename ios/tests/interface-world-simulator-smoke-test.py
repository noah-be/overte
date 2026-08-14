#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

"""Mock the iPhone/iPad serverless and online world screenshot runner."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import tempfile
import zlib


ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "ios/ci/interface-world-simulator-smoke.sh"
DOMAIN = "123e4567-e89b-12d3-a456-426614174000"
SESSION = "123e4567-e89b-12d3-a456-426614174001"
NODE = "123e4567-e89b-12d3-a456-426614174002"
ENTITY = "123e4567-e89b-12d3-a456-426614174003"


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def png_bytes(*, blank: bool = False) -> bytes:
    width = height = 400
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            if blank:
                rows.extend((18, 18, 18))
            else:
                rows.extend(((x * 3 + y) % 256, (y * 7 + x) % 256, (x ^ y) % 256))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", header)
        + png_chunk(b"IDAT", zlib.compress(rows))
        + png_chunk(b"IEND", b"")
    )


SERVERLESS_LOG = "\n".join(
    (
        "Overte OVERTE_IOS_WORLD_GATE navigation_requested kind= serverless destination= serverless_tutorial",
        "Overte OVERTE_IOS_WORLD_GATE serverless_import_committed scene= serverless_tutorial",
        f"Overte OVERTE_IOS_ENTITY_GATE entity_tree_nonempty entity= {{{ENTITY}}}",
        f"Overte OVERTE_IOS_ENTITY_GATE render_handoff entity= {{{ENTITY}}}",
    )
) + "\n"
ONLINE_LOG = "\n".join(
    (
        "Overte OVERTE_IOS_WORLD_GATE navigation_requested kind= online destination= overte_hub",
        f"Overte OVERTE_IOS_ENTITY_GATE domain_list_connected domain= {DOMAIN} session= {SESSION}",
        f"Overte OVERTE_IOS_ENTITY_GATE entity_server_active node= {NODE}",
        f"Overte OVERTE_IOS_ENTITY_GATE entity_query_sent node= {NODE} bytes= 144",
        f"Overte OVERTE_IOS_ENTITY_GATE entity_data_received node= {NODE} bytes= 1200",
        f"Overte OVERTE_IOS_ENTITY_GATE entity_tree_nonempty entity= {{{ENTITY}}}",
        f"Overte OVERTE_IOS_ENTITY_GATE render_handoff entity= {{{ENTITY}}}",
    )
) + "\n"


def invoke(
    app: Path,
    output: Path,
    environment: dict[str, str],
    family: str,
    scenario: str,
    domain: str,
):
    return subprocess.run(
        [
            str(SMOKE),
            str(app),
            "org.overte.interface.dev",
            family,
            scenario,
            domain,
            str(output),
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=20,
    )


def assert_private(result: subprocess.CompletedProcess[str], app: Path) -> None:
    combined = result.stdout + result.stderr
    assert str(app) not in combined, combined
    assert "org.overte.interface.dev" not in combined, combined
    assert "hifi://overte_hub" not in combined, combined


def assert_no_raw_log(output: Path, scratch: Path) -> None:
    assert not list(output.rglob("*.log")), list(output.rglob("*.log"))
    assert not list(scratch.glob("overte-ios-world-smoke.*")), list(scratch.iterdir())


with tempfile.TemporaryDirectory(prefix="overte-ios-world-smoke-test-") as directory:
    root = Path(directory)
    app = root / "private-world-candidate.app"
    app.mkdir()
    bin_dir = root / "bin"
    bin_dir.mkdir()
    scratch = root / "tmp"
    scratch.mkdir()
    command_log = root / "xcrun-commands.txt"
    screenshot_fixture = root / "world.png"
    screenshot_fixture.write_bytes(png_bytes())
    blank_fixture = root / "blank.png"
    blank_fixture.write_bytes(png_bytes(blank=True))
    device_fixture = {
        "devices": {
            "com.apple.CoreSimulator.SimRuntime.iOS-26-0": [
                {"name": "iPhone 17", "udid": "phone-udid", "isAvailable": True},
                {"name": "iPad Pro", "udid": "tablet-udid", "isAvailable": True},
            ]
        }
    }
    fake_xcrun = bin_dir / "xcrun"
    fake_xcrun.write_text(
        """#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$FAKE_XCRUN_COMMAND_LOG"
if [ "$1 $2 $3" = "simctl list devices" ]; then
    printf '%s\n' "$FAKE_DEVICE_JSON"
elif [ -n "${FAKE_FAIL_MATCH:-}" ] && [ "$*" = "$FAKE_FAIL_MATCH" ]; then
    printf '%s\n' "${FAKE_FAILURE_DETAIL:-fixture command failure}" >&2
    exit "${FAKE_FAIL_STATUS:-13}"
elif [ "$1 $2" = "simctl launch" ]; then
    printf '%s: 4242\n' "$4"
elif [ "$1 $2" = "simctl spawn" ] && [ "$4 $5" = "log show" ]; then
    printf '%s' "$FAKE_PROCESS_LOG"
elif [ "$1 $2" = "simctl io" ] && [ "$4" = "screenshot" ]; then
    cp "$FAKE_SCREENSHOT" "$5"
fi
""",
        encoding="utf-8",
    )
    fake_xcrun.chmod(fake_xcrun.stat().st_mode | stat.S_IXUSR)
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{bin_dir}:{environment['PATH']}",
            "TMPDIR": str(scratch),
            "FAKE_XCRUN_COMMAND_LOG": str(command_log),
            "FAKE_DEVICE_JSON": json.dumps(device_fixture),
            "FAKE_SCREENSHOT": str(screenshot_fixture),
            "OVERTE_IOS_WORLD_TIMEOUT_SECONDS": "1",
            "OVERTE_IOS_WORLD_POLL_SECONDS": "1",
            "OVERTE_IOS_WORLD_SCREENSHOT_SETTLE_SECONDS": "0",
            "OVERTE_IOS_WORLD_DIAGNOSTICS_DIR": str(root / "raw-diagnostics"),
        }
    )

    for family, udid in (("iphone", "phone-udid"), ("ipad", "tablet-udid")):
        for scenario, process_log, domain, destination, launch_url in (
            (
                "serverless",
                SERVERLESS_LOG,
                "-",
                "serverless_tutorial",
                "file:///~/serverless/tutorial.json",
            ),
            ("online", ONLINE_LOG, DOMAIN, "overte_hub", "hifi://overte_hub"),
        ):
            command_log.write_text("", encoding="utf-8")
            output = root / f"success-{family}-{scenario}"
            case_environment = {**environment, "FAKE_PROCESS_LOG": process_log}
            result = invoke(app, output, case_environment, family, scenario, domain)
            assert result.returncode == 0, (result.stdout, result.stderr)
            assert f"PASS full-client {family} simulator {scenario} world with screenshot" in result.stdout
            screenshot = output / f"{family}-{scenario}.png"
            screenshot_report = json.loads(
                (output / f"{family}-{scenario}-screenshot.json").read_text(encoding="utf-8")
            )
            runtime = json.loads(
                (output / f"{family}-{scenario}-runtime.json").read_text(encoding="utf-8")
            )
            assert screenshot.is_file()
            assert screenshot_report["accepted"] is True
            assert screenshot_report["scenario"] == scenario
            assert screenshot_report["destination"] == destination
            assert runtime["accepted"] is True
            assert runtime["scenario"] == scenario
            assert runtime["screenshot"]["sha256"] == screenshot_report["sha256"]
            assert not (output / f"{family}-{scenario}-failure.png").exists()
            assert_no_raw_log(output, scratch)
            assert_private(result, app)
            commands = command_log.read_text(encoding="utf-8").splitlines()
            assert f"simctl boot {udid}" in commands, commands
            launch = [line for line in commands if line.startswith(f"simctl launch {udid} ")]
            assert len(launch) == 1, launch
            assert f"--url {launch_url}" in launch[0], launch
            assert "--ios-world-evidence" in launch[0], launch
            assert f"simctl io {udid} screenshot {screenshot}" in commands, commands
            assert f"simctl terminate {udid} org.overte.interface.dev" in commands, commands
            assert f"simctl uninstall {udid} org.overte.interface.dev" in commands, commands
            assert f"simctl shutdown {udid}" in commands, commands

    wrong_domain_output = root / "wrong-domain"
    wrong_domain = invoke(
        app,
        wrong_domain_output,
        {**environment, "FAKE_PROCESS_LOG": ONLINE_LOG},
        "iphone",
        "online",
        "223e4567-e89b-12d3-a456-426614174000",
    )
    assert wrong_domain.returncode == 1, (wrong_domain.stdout, wrong_domain.stderr)
    assert "connected domain does not match" in wrong_domain.stderr
    assert (wrong_domain_output / "iphone-online-failure.png").is_file()
    assert_no_raw_log(wrong_domain_output, scratch)

    install_failure_output = root / "install-failure"
    install_failure = invoke(
        app,
        install_failure_output,
        {
            **environment,
            "FAKE_PROCESS_LOG": SERVERLESS_LOG,
            "FAKE_FAIL_MATCH": f"simctl install phone-udid {app}",
            "FAKE_FAIL_STATUS": "13",
            "FAKE_FAILURE_DETAIL": "IXErrorDomain Code=13 Missing bundle ID",
        },
        "iphone",
        "serverless",
        "-",
    )
    assert install_failure.returncode == 13, (install_failure.stdout, install_failure.stderr)
    command_diagnostics = root / "raw-diagnostics/iphone-serverless-command-errors.log"
    assert command_diagnostics.is_file()
    diagnostic_text = command_diagnostics.read_text(encoding="utf-8")
    assert "command_label=application install" in diagnostic_text
    assert "command_status=13" in diagnostic_text
    assert "IXErrorDomain Code=13 Missing bundle ID" in diagnostic_text
    assert_no_raw_log(install_failure_output, scratch)

    blank_output = root / "blank"
    blank = invoke(
        app,
        blank_output,
        {
            **environment,
            "FAKE_PROCESS_LOG": SERVERLESS_LOG,
            "FAKE_SCREENSHOT": str(blank_fixture),
        },
        "ipad",
        "serverless",
        "-",
    )
    assert blank.returncode == 1, (blank.stdout, blank.stderr)
    assert "blank or lacks visible world detail" in blank.stderr
    assert (blank_output / "ipad-serverless-failure.png").is_file()
    assert_no_raw_log(blank_output, scratch)

print("PASS fail-closed iPhone/iPad serverless and online simulator screenshot runner mocks")
