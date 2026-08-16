#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

"""Exercise the bounded, no-rebuild Full Client LLDB crash capture."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "ios/ci/interface-world-simulator-lldb.sh"
SOURCE_REVISION = "4" * 40
CANDIDATE_SHA256 = "a" * 64
UUID = "12345678-1234-1234-1234-1234567890AB"


def invoke(app: Path, symbols: Path, output: Path, environment: dict[str, str]):
    return subprocess.run(
        [
            str(RUNNER),
            str(app),
            str(symbols),
            "org.overte.interface.dev",
            "iphone",
            SOURCE_REVISION,
            CANDIDATE_SHA256,
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


with tempfile.TemporaryDirectory(prefix="overte-ios-lldb-test-") as directory:
    root = Path(directory)
    app = root / "Overte.app"
    app.mkdir()
    executable = app / "Overte"
    executable.write_bytes(b"fixture app")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

    symbols = root / "Overte.app.dSYM"
    symbol_binary = symbols / "Contents/Resources/DWARF/Overte"
    symbol_binary.parent.mkdir(parents=True)
    symbol_binary.write_bytes(b"fixture symbols")

    bin_dir = root / "bin"
    bin_dir.mkdir()
    scratch = root / "tmp"
    scratch.mkdir()
    command_log = root / "commands.log"
    data_container = root / "data-container"

    fake_xcodebuild = bin_dir / "xcodebuild"
    fake_xcodebuild.write_text(
        "#!/bin/sh\nprintf '%s\\n' 'Xcode 26.5' 'Build version 17F42'\n",
        encoding="utf-8",
    )
    fake_xcodebuild.chmod(fake_xcodebuild.stat().st_mode | stat.S_IXUSR)

    fake_xcrun = bin_dir / "xcrun"
    fake_xcrun.write_text(
        r'''#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$FAKE_COMMAND_LOG"
if [ "$1" = dwarfdump ] && [ "$2" = --uuid ]; then
    case "$3" in
        *.dSYM/*) uuid=${FAKE_SYMBOL_UUID} ;;
        *) uuid=${FAKE_APP_UUID} ;;
    esac
    printf 'UUID: %s (arm64) %s\n' "$uuid" "$3"
elif [ "$1 $2 $3" = "simctl list devices" ]; then
    printf '%s\n' "$FAKE_DEVICE_JSON"
elif [ "$1 $2" = "simctl get_app_container" ]; then
    mkdir -p "$FAKE_DATA_CONTAINER/tmp"
    printf '%s\n' "$FAKE_DATA_CONTAINER"
elif [ "$1 $2" = "simctl launch" ]; then
    [ "${SIMCTL_CHILD_MVK_CONFIG_LOG_LEVEL:-}" = 4 ]
    [ "${SIMCTL_CHILD_MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS:-}" = 0 ]
    [ "${SIMCTL_CHILD_MVK_CONFIG_TRACE_VULKAN_CALLS:-}" = 6 ]
    [ -n "${SIMCTL_CHILD_MVK_CONFIG_SHADER_DUMP_DIR:-}" ]
    case " $* " in
        *" --wait-for-debugger "*) observed_wait=1 ;;
        *) observed_wait=0 ;;
    esac
    [ "$observed_wait" = "${FAKE_EXPECT_WAIT_FOR_DEBUGGER:-0}" ] || {
        printf '%s\n' 'unexpected wait-for-debugger mode' >&2
        exit 70
    }
    stdout=
    stderr=
    for argument in "$@"; do
        case "$argument" in
            --stdout=*) stdout=${argument#--stdout=} ;;
            --stderr=*) stderr=${argument#--stderr=} ;;
        esac
    done
    : > "$stdout"
    : > "$stderr"
    printf '%s\n' 'fixture: 4242'
elif [ "$1" = lldb ]; then
    if [ "${FAKE_LLDB_SLEEP:-0}" = 1 ]; then
        sleep 10
    fi
    if [ "${FAKE_LLDB_NORMAL_EXIT:-0}" = 1 ]; then
        cat <<'EOF'
OVERTE_LLDB_TRACE resume_entry
* thread #1
  frame #0: Overte`Application::resumeAfterLoginDialogActionTaken
OVERTE_LLDB_TRACE qt_exit
* thread #1
  frame #0: QtCore`QCoreApplication::exit
Process 4242 exited with status = 0 (0x00000000)
OVERTE_LLDB_STARTUP_TRACE_COMPLETE
EOF
        exit 0
    fi
    cat <<'EOF'
Process 4242 stopped
* thread #1, stop reason = signal SIGSEGV
  frame #0: 0x0000000100001234 Overte`vks::pipelines::GraphicsPipelineBuilder::create + 604
  frame #1: 0x0000000100001000 Overte`vks::pipelines::Cache::getPipeline + 100
OVERTE_LLDB_CRASH_CAPTURE_COMPLETE
EOF
elif [ "$1 $2" = "simctl uninstall" ]; then
    rm -rf "$FAKE_DATA_CONTAINER"
fi
''',
        encoding="utf-8",
    )
    fake_xcrun.chmod(fake_xcrun.stat().st_mode | stat.S_IXUSR)

    device_fixture = {
        "devices": {
            "com.apple.CoreSimulator.SimRuntime.iOS-26-5": [
                {"name": "iPhone 17", "udid": "private-udid", "isAvailable": True}
            ]
        }
    }
    base_environment = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "TMPDIR": str(scratch),
        "FAKE_COMMAND_LOG": str(command_log),
        "FAKE_DEVICE_JSON": json.dumps(device_fixture),
        "FAKE_DATA_CONTAINER": str(data_container),
        "FAKE_APP_UUID": UUID,
        "FAKE_SYMBOL_UUID": UUID,
    }

    captured_output = root / "captured"
    captured = invoke(app, symbols, captured_output, base_environment)
    assert captured.returncode == 1, (captured.stdout, captured.stderr)
    result = (captured_output / "iphone-serverless-lldb-result.log").read_text(encoding="utf-8")
    assert "capture_status=captured_sigsegv" in result
    assert "lldb_status=0" in result
    assert f"source_revision={SOURCE_REVISION}" in result
    assert f"candidate_sha256={CANDIDATE_SHA256}" in result
    lldb_log = (captured_output / "iphone-serverless-lldb.log").read_text(encoding="utf-8")
    assert "OVERTE_LLDB_CRASH_CAPTURE_COMPLETE" in lldb_log
    commands = command_log.read_text(encoding="utf-8")
    assert "simctl launch --stdout=" in commands
    assert "--wait-for-debugger" not in commands
    assert "lldb --no-lldbinit --no-use-colors --batch --attach-pid 4242" in commands
    assert "startup-trace.lldb" not in commands
    assert "simctl terminate" in commands and "simctl shutdown" in commands

    command_log.write_text("", encoding="utf-8")
    normal_exit_environment = {
        **base_environment,
        "FAKE_LLDB_NORMAL_EXIT": "1",
        "FAKE_EXPECT_WAIT_FOR_DEBUGGER": "1",
        "OVERTE_IOS_LLDB_STARTUP_TRACE": "1",
        "OVERTE_IOS_LLDB_WAIT_FOR_DEBUGGER": "1",
    }
    normal_exit_output = root / "normal-exit"
    normal_exit = invoke(app, symbols, normal_exit_output, normal_exit_environment)
    assert normal_exit.returncode == 1, (normal_exit.stdout, normal_exit.stderr)
    normal_exit_result = (
        normal_exit_output / "iphone-serverless-lldb-result.log"
    ).read_text(encoding="utf-8")
    assert "capture_status=traced_process_exit" in normal_exit_result
    assert "resume_trace=observed" in normal_exit_result
    assert "sandbox_trace=not_observed" in normal_exit_result
    assert "exit_trace=observed" in normal_exit_result
    normal_exit_log = (
        normal_exit_output / "iphone-serverless-lldb.log"
    ).read_text(encoding="utf-8")
    assert "OVERTE_LLDB_TRACE resume_entry" in normal_exit_log
    assert "OVERTE_LLDB_TRACE qt_exit" in normal_exit_log
    normal_exit_commands = command_log.read_text(encoding="utf-8")
    assert "simctl launch --wait-for-debugger" in normal_exit_commands
    assert "startup-trace.lldb" in normal_exit_commands

    command_log.write_text("", encoding="utf-8")
    mismatch_environment = {**base_environment, "FAKE_SYMBOL_UUID": "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE"}
    mismatch_output = root / "mismatch"
    mismatch = invoke(app, symbols, mismatch_output, mismatch_environment)
    assert mismatch.returncode == 2, (mismatch.stdout, mismatch.stderr)
    assert "app and dSYM UUIDs do not match" in mismatch.stderr
    mismatch_commands = command_log.read_text(encoding="utf-8").splitlines()
    assert all(not line.startswith(("simctl ", "lldb ")) for line in mismatch_commands)

    command_log.write_text("", encoding="utf-8")
    timeout_environment = {
        **base_environment,
        "FAKE_LLDB_SLEEP": "1",
        "OVERTE_IOS_LLDB_TIMEOUT_SECONDS": "1",
    }
    timeout_output = root / "timeout"
    timed_out = invoke(app, symbols, timeout_output, timeout_environment)
    assert timed_out.returncode == 124, (timed_out.stdout, timed_out.stderr)
    timeout_result = (timeout_output / "iphone-serverless-lldb-result.log").read_text(encoding="utf-8")
    assert "lldb_status=124" in timeout_result
    assert "capture_status=incomplete" in timeout_result
    timeout_commands = command_log.read_text(encoding="utf-8")
    assert "simctl terminate" in timeout_commands and "simctl shutdown" in timeout_commands

print("PASS no-rebuild Full Client simulator LLDB crash capture")
