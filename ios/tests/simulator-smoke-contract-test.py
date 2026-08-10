#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

import json
import os
import pathlib
import stat
import subprocess
import tempfile


REPO = pathlib.Path(__file__).resolve().parents[2]
SMOKE = REPO / "ios/ci/simulator-smoke.sh"


with tempfile.TemporaryDirectory() as directory:
    root = pathlib.Path(directory)
    app = root / "OverteIOSBootstrap.app"
    app.mkdir()
    bin_dir = root / "bin"
    bin_dir.mkdir()
    log = root / "xcrun.log"
    fixture = {
        "devices": {
            "com.apple.CoreSimulator.SimRuntime.iOS-26-0": [
                {"name": "iPhone 17", "udid": "phone-udid", "isAvailable": True},
                {"name": "iPad Pro", "udid": "tablet-udid", "isAvailable": True},
            ]
        }
    }
    fake = bin_dir / "xcrun"
    fake.write_text(
        """#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$FAKE_XCRUN_LOG"
if [ -n "${FAKE_FAIL_MATCH:-}" ] && printf '%s' "$*" | grep -F "$FAKE_FAIL_MATCH" >/dev/null; then
    exit "${FAKE_FAIL_STATUS:-17}"
fi
if [ "$1 $2 $3" = "simctl list devices" ]; then
    printf '%s\n' "$FAKE_DEVICE_JSON"
elif [ "$1 $2" = "simctl launch" ]; then
    printf '%s: 4242\n' "$3"
fi
""",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{bin_dir}:{environment['PATH']}",
            "FAKE_XCRUN_LOG": str(log),
            "FAKE_DEVICE_JSON": json.dumps(fixture),
            "OVERTE_IOS_SIMULATOR_GRACE_SECONDS": "0",
        }
    )
    result = subprocess.run(
        [str(SMOKE), str(app), "org.overte.interface.dev", str(root / "diagnostics")],
        cwd=REPO,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "PASS iphone simulator launch" in result.stdout, result.stdout
    assert "PASS ipad simulator launch" in result.stdout, result.stdout
    commands = log.read_text(encoding="utf-8").splitlines()
    phone_boot = commands.index("simctl boot phone-udid")
    tablet_boot = commands.index("simctl boot tablet-udid")
    first_wait = commands.index("simctl bootstatus phone-udid -b")
    assert phone_boot < first_wait and tablet_boot < first_wait, commands
    assert "simctl openurl phone-udid hifi://overte_hub" in commands, commands
    assert "simctl openurl tablet-udid hifi://overte_hub" in commands, commands
    assert "simctl terminate phone-udid org.overte.interface.dev" in commands, commands
    assert "simctl terminate tablet-udid org.overte.interface.dev" in commands, commands
    assert "simctl shutdown phone-udid" in commands, commands
    assert "simctl shutdown tablet-udid" in commands, commands
    assert "elapsed=" in result.stderr and "timeout=" in result.stderr, result.stderr

    environment["FAKE_FAIL_MATCH"] = "simctl install phone-udid"
    environment["FAKE_FAIL_STATUS"] = "17"
    failed = subprocess.run(
        [str(SMOKE), str(app), "org.overte.interface.dev", str(root / "failure-diagnostics")],
        cwd=REPO, env=environment, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False, timeout=20,
    )
    assert failed.returncode == 17, (failed.stdout, failed.stderr)
    failure_commands = log.read_text(encoding="utf-8").splitlines()
    assert "simctl io phone-udid screenshot " + str(root / "failure-diagnostics/iphone-failure.png") in failure_commands
    assert failure_commands.count("simctl shutdown phone-udid") <= 3, failure_commands

print("PASS bounded dual-simulator smoke contract tests")
