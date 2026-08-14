#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

"""Mock the bounded full-client simulator entity runner."""

import json
import os
import pathlib
import stat
import subprocess
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[2]
SMOKE = ROOT / "ios/ci/interface-simulator-smoke.sh"
UUIDS = {
    "domain": "123e4567-e89b-12d3-a456-426614174000",
    "session": "123e4567-e89b-12d3-a456-426614174001",
    "node": "123e4567-e89b-12d3-a456-426614174002",
    "entity": "123e4567-e89b-12d3-a456-426614174003",
}
SUCCESS_LOG = "\n".join(
    (
        f"Overte OVERTE_IOS_ENTITY_GATE domain_list_connected domain= {UUIDS['domain']} session= {UUIDS['session']}",
        f"Overte OVERTE_IOS_ENTITY_GATE entity_server_active node= {UUIDS['node']}",
        f"Overte OVERTE_IOS_ENTITY_GATE entity_query_sent node= {UUIDS['node']} bytes= 144",
        f"Overte OVERTE_IOS_ENTITY_GATE entity_data_received node= {UUIDS['node']} bytes= 1200",
        f"Overte OVERTE_IOS_ENTITY_GATE entity_tree_nonempty entity= {{{UUIDS['entity']}}}",
        f"Overte OVERTE_IOS_ENTITY_GATE render_handoff entity= {{{UUIDS['entity']}}}",
    )
) + "\n"
WRONG_ORDER_LOG = "\n".join(SUCCESS_LOG.splitlines()[:1] + SUCCESS_LOG.splitlines()[2:]) + "\n"
MISSING_LOG = "\n".join(SUCCESS_LOG.splitlines()[:-1]) + "\n"


def invoke(app: pathlib.Path, output: pathlib.Path, environment: dict[str, str], family: str):
    return subprocess.run(
        [str(SMOKE), str(app), "org.overte.interface.dev", family, str(output)],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=20,
    )


def assert_private(result: subprocess.CompletedProcess[str], app: pathlib.Path) -> None:
    combined = result.stdout + result.stderr
    assert str(app) not in combined, combined
    assert "org.overte.interface.dev" not in combined, combined
    assert "hifi://overte_hub" not in combined, combined


def assert_no_raw_log(output: pathlib.Path, scratch: pathlib.Path) -> None:
    assert not list(output.rglob("*.log")), list(output.rglob("*.log"))
    assert not list(scratch.glob("overte-ios-interface-smoke.*")), list(scratch.iterdir())


with tempfile.TemporaryDirectory(prefix="overte-ios-interface-smoke-test-") as directory:
    root = pathlib.Path(directory)
    app = root / "private-launch-argument.app"
    app.mkdir()
    bin_dir = root / "bin"
    bin_dir.mkdir()
    scratch = root / "tmp"
    scratch.mkdir()
    command_log = root / "xcrun-commands.txt"
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
if [ -n "${FAKE_FAIL_MATCH:-}" ] && printf '%s' "$*" | grep -F "$FAKE_FAIL_MATCH" >/dev/null; then
    exit "${FAKE_FAIL_STATUS:-17}"
fi
if [ "$1 $2 $3" = "simctl list devices" ]; then
    printf '%s\n' "$FAKE_DEVICE_JSON"
elif [ "$1 $2" = "simctl launch" ]; then
    printf '%s: 4242\n' "$4"
elif [ "$1 $2" = "simctl spawn" ] && [ "$4 $5" = "log show" ]; then
    printf '%s' "$FAKE_PROCESS_LOG"
elif [ "$1 $2" = "simctl io" ] && [ "$4" = "screenshot" ]; then
    : > "$5"
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
            "FAKE_PROCESS_LOG": SUCCESS_LOG,
            "OVERTE_IOS_INTERFACE_SMOKE_TIMEOUT_SECONDS": "1",
            "OVERTE_IOS_INTERFACE_SMOKE_POLL_SECONDS": "1",
        }
    )

    for family, udid in (("iphone", "phone-udid"), ("ipad", "tablet-udid")):
        output = root / f"success-{family}"
        result = invoke(app, output, environment, family)
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert f"PASS full-client {family} simulator entity runtime" in result.stdout
        report = json.loads((output / f"{family}-entity-gates.json").read_text(encoding="utf-8"))
        assert report["accepted"] is True, report
        assert report["completed_gates"] == report["expected_gates"], report
        assert len(report["evidence"]) == 6, report
        assert not (output / f"{family}-failure.png").exists()
        assert_no_raw_log(output, scratch)
        assert_private(result, app)
        commands = command_log.read_text(encoding="utf-8").splitlines()
        assert f"simctl boot {udid}" in commands, commands
        assert f"simctl install {udid} {app}" in commands, commands
        assert f"simctl openurl {udid} hifi://overte_hub" in commands, commands
        scoped = [line for line in commands if line.startswith(f"simctl spawn {udid} log show ")]
        assert scoped and all("--predicate processIdentifier == 4242" in line for line in scoped), scoped
        assert all('eventMessage CONTAINS "OVERTE_IOS_ENTITY_GATE"' in line for line in scoped), scoped
        assert f"simctl terminate {udid} org.overte.interface.dev" in commands, commands
        assert f"simctl shutdown {udid}" in commands, commands

    wrong_output = root / "wrong-order"
    wrong_environment = {**environment, "FAKE_PROCESS_LOG": WRONG_ORDER_LOG}
    wrong = invoke(app, wrong_output, wrong_environment, "iphone")
    assert wrong.returncode == 1, (wrong.stdout, wrong.stderr)
    wrong_report = json.loads((wrong_output / "iphone-entity-gates.json").read_text(encoding="utf-8"))
    assert wrong_report["accepted"] is False, wrong_report
    assert any("expected 'entity_server_active'" in error for error in wrong_report["errors"]), wrong_report
    assert (wrong_output / "iphone-failure.png").is_file()
    assert_no_raw_log(wrong_output, scratch)
    assert_private(wrong, app)

    timeout_output = root / "timeout"
    timeout_environment = {**environment, "FAKE_PROCESS_LOG": MISSING_LOG}
    timed_out = invoke(app, timeout_output, timeout_environment, "ipad")
    assert timed_out.returncode == 124, (timed_out.stdout, timed_out.stderr)
    timeout_report = json.loads((timeout_output / "ipad-entity-gates.json").read_text(encoding="utf-8"))
    assert timeout_report["accepted"] is False, timeout_report
    assert timeout_report["errors"] == ["missing gate 'render_handoff'"], timeout_report
    assert (timeout_output / "ipad-failure.png").is_file()
    assert_no_raw_log(timeout_output, scratch)
    assert_private(timed_out, app)
    timeout_commands = command_log.read_text(encoding="utf-8").splitlines()
    assert "simctl terminate tablet-udid org.overte.interface.dev" in timeout_commands, timeout_commands
    assert "simctl shutdown tablet-udid" in timeout_commands, timeout_commands

    failure_output = root / "install-failure"
    failure_environment = {
        **environment,
        "FAKE_FAIL_MATCH": "simctl install phone-udid",
        "FAKE_FAIL_STATUS": "17",
    }
    failed = invoke(app, failure_output, failure_environment, "iphone")
    assert failed.returncode == 17, (failed.stdout, failed.stderr)
    assert (failure_output / "iphone-failure.png").is_file()
    assert_no_raw_log(failure_output, scratch)
    assert_private(failed, app)
    failure_commands = command_log.read_text(encoding="utf-8").splitlines()
    assert "simctl shutdown phone-udid" in failure_commands, failure_commands

    stale_output = root / "stale-removal-failure"
    stale_environment = {
        **environment,
        "FAKE_FAIL_MATCH": "simctl uninstall phone-udid org.overte.interface.dev",
        "FAKE_FAIL_STATUS": "18",
    }
    stale = invoke(app, stale_output, stale_environment, "iphone")
    assert stale.returncode == 18, (stale.stdout, stale.stderr)
    stale_commands = command_log.read_text(encoding="utf-8").splitlines()
    assert "simctl get_app_container phone-udid org.overte.interface.dev data" in stale_commands
    assert f"simctl install phone-udid {app}" not in stale_commands[-4:], stale_commands[-4:]
    assert_no_raw_log(stale_output, scratch)
    assert_private(stale, app)

print("PASS fail-closed full-client iPhone/iPad simulator entity runner mocks")
