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


LOG_STREAM_FILTER_BANNER = (
    'Filtering the log data using "process == "Overte" OR '
    'eventMessage CONTAINS "OVERTE_IOS_VULKAN_FATAL""\n'
)
SERVERLESS_LOG = LOG_STREAM_FILTER_BANNER + "\n".join(
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
    app_pid_file = root / "fake-app.pid"
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
elif [ "$1 $2" = "simctl get_app_container" ]; then
    mkdir -p "$FAKE_DATA_CONTAINER/tmp"
    printf '%s\n' "$FAKE_DATA_CONTAINER"
elif [ "$1 $2" = "simctl launch" ]; then
    [ "${SIMCTL_CHILD_MVK_CONFIG_LOG_LEVEL:-}" = 4 ] || {
        printf '%s\n' "missing MoltenVK diagnostic log level" >&2
        exit 65
    }
    [ "${SIMCTL_CHILD_MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS:-}" = 0 ] || {
        printf '%s\n' "Metal argument buffers must be disabled for simulator runtime evidence" >&2
        exit 71
    }
    if [ "${FAKE_EXPECT_MVK_TRACE:-0}" = 1 ]; then
        [ "${SIMCTL_CHILD_MVK_CONFIG_TRACE_VULKAN_CALLS:-}" = 6 ] || {
            printf '%s\n' "missing requested MoltenVK Vulkan call trace" >&2
            exit 72
        }
    fi
    [ -n "${SIMCTL_CHILD_MVK_CONFIG_SHADER_DUMP_DIR:-}" ] || exit 66
    case "$SIMCTL_CHILD_MVK_CONFIG_SHADER_DUMP_DIR" in
        "$FAKE_DATA_CONTAINER"/tmp/overte-mvk-shaders-*) ;;
        *) exit 70 ;;
    esac
    app_stdout=""
    app_stderr=""
    for argument in "$@"; do
        case "$argument" in
            --stdout=*) app_stdout=${argument#--stdout=} ;;
            --stderr=*) app_stderr=${argument#--stderr=} ;;
        esac
    done
    [ -n "$app_stdout" ] && [ -n "$app_stderr" ]
    : > "$app_stdout"
    printf '%s' "${FAKE_APP_STDERR:-}" > "$app_stderr"
    if [ "${FAKE_CREATE_SHADER_DUMP:-0}" = 1 ]; then
        mkdir -p "$SIMCTL_CHILD_MVK_CONFIG_SHADER_DUMP_DIR"
        printf '%s\n' 'synthetic metal shader' > \
            "$SIMCTL_CHILD_MVK_CONFIG_SHADER_DUMP_DIR/shader-vs-0000000000001234.metal"
        printf '\003\002#\007\000\000\001\000\000\000\000\000\001\000\000\000\000\000\000\000' > \
            "$SIMCTL_CHILD_MVK_CONFIG_SHADER_DUMP_DIR/shader-vs-0000000000001234.spv"
        printf '%s\n' 'synthetic pipeline' > \
            "$SIMCTL_CHILD_MVK_CONFIG_SHADER_DUMP_DIR/pipeline-0000000000001234.txt"
        printf '%s\n' 'must not escape diagnostics' > \
            "$SIMCTL_CHILD_MVK_CONFIG_SHADER_DUMP_DIR/unrelated.secret"
    fi
    if [ "${FAKE_APP_EXIT_EARLY:-0}" = 1 ]; then
        sleep "${FAKE_APP_EXIT_SECONDS:-0.2}" >/dev/null 2>&1 &
    else
        sleep 60 >/dev/null 2>&1 &
    fi
    app_pid=$!
    printf '%s\n' "$app_pid" > "$FAKE_APP_PID_FILE"
    if [ "${FAKE_CREATE_CRASH_REPORT:-0}" = 1 ]; then
        crash_root="$HOME/Library/Logs/DiagnosticReports"
        mkdir -p "$crash_root"
        (
            sleep "${FAKE_CRASH_REPORT_DELAY:-0}"
            printf '%s\n' "${FAKE_CRASH_REPORT:-synthetic crash report}" > \
                "$crash_root/Overte-fixture.ips"
        ) >/dev/null 2>&1 &
    fi
    if [ "${FAKE_CREATE_DRIVER_CRASH_REPORT:-0}" = 1 ]; then
        crash_root="$HOME/Library/Logs/DiagnosticReports"
        mkdir -p "$crash_root"
        (
            sleep "${FAKE_DRIVER_CRASH_REPORT_DELAY:-1}"
            printf '%s\n' "${FAKE_DRIVER_CRASH_REPORT:-synthetic driver crash report}" > \
                "$crash_root/SimMetalHost-fixture.ips"
        ) >/dev/null 2>&1 &
    fi
    printf 'fixture: %s\n' "$app_pid"
elif [ "$1 $2" = "simctl spawn" ] && [ "$4 $5" = "log stream" ]; then
    printf '%s' "$FAKE_PROCESS_LOG"
    noise_lines=${FAKE_PROCESS_NOISE_LINES:-0}
    noise_index=0
    while [ "$noise_index" -lt "$noise_lines" ]; do
        printf '%s\n' 'Overte synthetic repetitive audio diagnostic payload'
        noise_index=$((noise_index + 1))
    done
    if [ -n "${FAKE_DELAYED_PROCESS_LOG:-}" ]; then
        sleep "${FAKE_DELAYED_PROCESS_LOG_SECONDS:-0.2}"
        printf '%s' "$FAKE_DELAYED_PROCESS_LOG"
    fi
    if [ "${FAKE_LOG_STREAM_EXIT:-0}" = 1 ]; then
        exit 0
    fi
    trap 'exit 0' TERM INT
    while :; do sleep 1; done
elif [ "$1 $2" = "simctl spawn" ] && [ "$4 $5" = "log show" ]; then
    case " $* " in
        *" --last 5m --style compact --info --debug --predicate "*) ;;
        *) printf '%s\n' "invalid log show options" >&2; exit 64 ;;
    esac
    printf '%s\n' "${FAKE_POSTMORTEM_LOG:-synthetic RunningBoard postmortem}"
elif [ "$1 $2" = "simctl terminate" ]; then
    if [ -s "$FAKE_APP_PID_FILE" ]; then
        kill "$(cat "$FAKE_APP_PID_FILE")" 2>/dev/null || true
    fi
elif [ "$1 $2" = "simctl uninstall" ]; then
    rm -rf "$FAKE_DATA_CONTAINER"
elif [ "$1 $2" = "simctl io" ] && [ "$4" = "screenshot" ]; then
    cp "$FAKE_SCREENSHOT" "$5"
fi
""",
        encoding="utf-8",
    )
    fake_xcrun.chmod(fake_xcrun.stat().st_mode | stat.S_IXUSR)
    fake_sample = bin_dir / "sample"
    fake_sample.write_text(
        """#!/bin/sh
set -eu
output=
while [ "$#" -gt 0 ]; do
    if [ "$1" = -file ]; then
        output=$2
        shift 2
    else
        shift
    fi
done
[ -n "$output" ]
printf '%s\n' "${FAKE_SAMPLE_TEXT:-synthetic process stack}" > "$output"
""",
        encoding="utf-8",
    )
    fake_sample.chmod(fake_sample.stat().st_mode | stat.S_IXUSR)
    fake_log = bin_dir / "log"
    fake_log.write_text(
        """#!/bin/sh
set -eu
printf '%s\n' "${FAKE_HOST_METAL_LOG:-synthetic host Metal postmortem}"
""",
        encoding="utf-8",
    )
    fake_log.chmod(fake_log.stat().st_mode | stat.S_IXUSR)
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{bin_dir}:{environment['PATH']}",
            "TMPDIR": str(scratch),
            "FAKE_XCRUN_COMMAND_LOG": str(command_log),
            "FAKE_APP_PID_FILE": str(app_pid_file),
            "FAKE_DATA_CONTAINER": str(root / "fake-data-container"),
            "FAKE_DEVICE_JSON": json.dumps(device_fixture),
            "FAKE_SCREENSHOT": str(screenshot_fixture),
            "OVERTE_IOS_WORLD_TIMEOUT_SECONDS": "1",
            "OVERTE_IOS_WORLD_POLL_SECONDS": "1",
            "OVERTE_IOS_WORLD_SCREENSHOT_SETTLE_SECONDS": "0",
            "OVERTE_IOS_WORLD_CRASH_REPORT_WAIT_SECONDS": "1",
            "OVERTE_IOS_WORLD_MVK_TRACE_VULKAN_CALLS": "6",
            "FAKE_EXPECT_MVK_TRACE": "1",
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
            for suffix in (
                "process-samples",
                "postmortem",
                "overte-crash-report",
                "simmetalhost-crash-report",
            ):
                assert not (root / f"raw-diagnostics/{family}-{scenario}-{suffix}.log").exists()
            assert_no_raw_log(output, scratch)
            assert_private(result, app)
            commands = command_log.read_text(encoding="utf-8").splitlines()
            assert f"simctl boot {udid}" in commands, commands
            permission = f"simctl privacy {udid} grant microphone org.overte.interface.dev"
            assert permission in commands, commands
            launch = [
                line
                for line in commands
                if line.startswith("simctl launch --stdout=")
                and f" {udid} org.overte.interface.dev " in line
            ]
            assert len(launch) == 1, launch
            assert commands.index(permission) < commands.index(launch[0]), commands
            streams = [line for line in commands if line.startswith(f"simctl spawn {udid} log stream ")]
            assert len(streams) == 1, streams
            assert commands.index(streams[0]) < commands.index(launch[0]), commands
            assert "log show" not in "\n".join(commands), commands
            assert 'process == "Overte"' in streams[0], streams
            assert "--level debug" in streams[0], streams
            assert "OVERTE_IOS_VULKAN_FATAL" in streams[0], streams
            assert "OVERTE_IOS_VULKAN_DEBUG" in streams[0], streams
            assert "OVERTE_IOS_VULKAN_PIPELINE_CONTEXT" in streams[0], streams
            assert f"--url {launch_url}" in launch[0], launch
            assert "--ios-world-evidence" in launch[0], launch
            assert "--stdout=" in launch[0], launch
            assert "--stderr=" in launch[0], launch
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

    command_log.write_text("", encoding="utf-8")
    permission_failure_output = root / "permission-failure"
    permission_failure = invoke(
        app,
        permission_failure_output,
        {
            **environment,
            "FAKE_PROCESS_LOG": SERVERLESS_LOG,
            "FAKE_FAIL_MATCH": (
                "simctl privacy phone-udid grant microphone "
                "org.overte.interface.dev"
            ),
            "FAKE_FAIL_STATUS": "19",
            "FAKE_FAILURE_DETAIL": "fixture microphone permission failure",
        },
        "iphone",
        "serverless",
        "-",
    )
    assert permission_failure.returncode == 19, (
        permission_failure.stdout,
        permission_failure.stderr,
    )
    permission_diagnostics = (
        root / "raw-diagnostics/iphone-serverless-command-errors.log"
    )
    permission_text = permission_diagnostics.read_text(encoding="utf-8")
    assert "command_label=simulator microphone permission" in permission_text
    assert "command_status=19" in permission_text
    assert "fixture microphone permission failure" in permission_text
    permission_commands = command_log.read_text(encoding="utf-8")
    assert "simctl launch" not in permission_commands
    assert_no_raw_log(permission_failure_output, scratch)

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

    fatal_after_gates_output = root / "fatal-after-gates"
    fatal_after_gates = invoke(
        app,
        fatal_after_gates_output,
        {
            **environment,
            "FAKE_PROCESS_LOG": SERVERLESS_LOG,
            "FAKE_DELAYED_PROCESS_LOG": (
                "Overte OVERTE_IOS_VULKAN_FATAL "
                "Fatal iOS Vulkan result: VK_ERROR_UNKNOWN (-13)\n"
            ),
            # The stream gets a one-second head start before launch. Delay past
            # that boundary so the fatal marker arrives only after the gates
            # have been accepted, during the screenshot-settle window.
            "FAKE_DELAYED_PROCESS_LOG_SECONDS": "1.5",
            "OVERTE_IOS_WORLD_SCREENSHOT_SETTLE_SECONDS": "2",
        },
        "iphone",
        "serverless",
        "-",
    )
    assert fatal_after_gates.returncode == 1, (
        fatal_after_gates.stdout,
        fatal_after_gates.stderr,
    )
    assert "fatal iOS Vulkan pipeline error observed" in fatal_after_gates.stderr
    assert not (fatal_after_gates_output / "iphone-serverless.png").exists()
    assert (fatal_after_gates_output / "iphone-serverless-failure.png").is_file()
    assert_no_raw_log(fatal_after_gates_output, scratch)

    stopped_stream_output = root / "stopped-stream"
    stopped_stream = invoke(
        app,
        stopped_stream_output,
        {**environment, "FAKE_PROCESS_LOG": "", "FAKE_LOG_STREAM_EXIT": "1"},
        "iphone",
        "serverless",
        "-",
    )
    assert stopped_stream.returncode == 1, (stopped_stream.stdout, stopped_stream.stderr)
    assert "process log stream stopped before the world gates were observed" in stopped_stream.stderr
    stream_diagnostics = root / "raw-diagnostics/iphone-serverless-command-errors.log"
    assert "command_label=process log stream" in stream_diagnostics.read_text(encoding="utf-8")
    assert_no_raw_log(stopped_stream_output, scratch)

    noisy_output = root / "bounded-noisy-diagnostics"
    noisy_marker = (
        "Overte OVERTE_IOS_WORLD_GATE navigation_requested "
        "kind= serverless destination= serverless_tutorial\n"
    )
    noisy = invoke(
        app,
        noisy_output,
        {
            **environment,
            "FAKE_PROCESS_LOG": noisy_marker,
            "FAKE_PROCESS_NOISE_LINES": "60000",
        },
        "iphone",
        "serverless",
        "-",
    )
    assert noisy.returncode == 124, (noisy.stdout, noisy.stderr)
    noisy_diagnostics = (
        root / "raw-diagnostics/iphone-serverless-application.log"
    )
    noisy_text = noisy_diagnostics.read_text(encoding="utf-8")
    assert len(noisy_text.encode("utf-8")) < 2 * 1024 * 1024
    assert "OVERTE_IOS_WORLD_GATE navigation_requested" in noisy_text
    assert "middle omitted" in noisy_text
    assert_no_raw_log(noisy_output, scratch)

    early_exit_output = root / "early-exit"
    early_exit = invoke(
        app,
        early_exit_output,
        {
            **environment,
            "HOME": str(root / "home"),
            "FAKE_PROCESS_LOG": "",
            "FAKE_APP_STDERR": "Overte fatal: synthetic early process exit\n",
            "FAKE_APP_EXIT_EARLY": "1",
            "FAKE_APP_EXIT_SECONDS": "2",
            "FAKE_CREATE_CRASH_REPORT": "1",
            "FAKE_CRASH_REPORT_DELAY": "0.5",
            "FAKE_CRASH_REPORT": "synthetic dyld crash cause",
            "FAKE_CREATE_DRIVER_CRASH_REPORT": "1",
            "FAKE_DRIVER_CRASH_REPORT_DELAY": "3",
            "FAKE_DRIVER_CRASH_REPORT": "synthetic delayed SimMetalHost cause",
            "FAKE_POSTMORTEM_LOG": "synthetic RunningBoard exit cause",
            "FAKE_SAMPLE_TEXT": "synthetic main-thread stack",
            "FAKE_CREATE_SHADER_DUMP": "1",
            "FAKE_HOST_METAL_LOG": "synthetic SimMetalHost pipeline failure",
            "OVERTE_IOS_WORLD_TIMEOUT_SECONDS": "5",
            "OVERTE_IOS_WORLD_STACK_SAMPLE_SECONDS": "1",
            "OVERTE_IOS_WORLD_CRASH_REPORT_WAIT_SECONDS": "5",
        },
        "iphone",
        "serverless",
        "-",
    )
    assert early_exit.returncode == 1, (early_exit.stdout, early_exit.stderr)
    assert "application process exited before the world gates were observed" in early_exit.stderr
    application_diagnostics = root / "raw-diagnostics/iphone-serverless-application.log"
    assert application_diagnostics.is_file()
    assert "synthetic early process exit" in application_diagnostics.read_text(encoding="utf-8")
    process_diagnostics = root / "raw-diagnostics/iphone-serverless-process-samples.log"
    assert process_diagnostics.is_file()
    assert "synthetic main-thread stack" in process_diagnostics.read_text(encoding="utf-8")
    assert "command" not in process_diagnostics.read_text(encoding="utf-8")
    postmortem = root / "raw-diagnostics/iphone-serverless-postmortem.log"
    assert "synthetic RunningBoard exit cause" in postmortem.read_text(encoding="utf-8")
    assert "postmortem_status=0" in postmortem.read_text(encoding="utf-8")
    crash = root / "raw-diagnostics/iphone-serverless-overte-crash-report.log"
    assert "synthetic dyld crash cause" in crash.read_text(encoding="utf-8")
    driver_crash = root / "raw-diagnostics/iphone-serverless-simmetalhost-crash-report.log"
    assert "synthetic delayed SimMetalHost cause" in driver_crash.read_text(encoding="utf-8")
    host_metal = root / "raw-diagnostics/iphone-serverless-host-metal.log"
    assert "synthetic SimMetalHost pipeline failure" in host_metal.read_text(encoding="utf-8")
    shader_dump = root / "raw-diagnostics/iphone-serverless-moltenvk-shaders"
    assert sorted(path.name for path in shader_dump.iterdir()) == [
        "pipeline-0000000000001234.txt",
        "shader-vs-0000000000001234.metal",
        "shader-vs-0000000000001234.spv",
    ]
    assert "synthetic metal shader" in (shader_dump / "shader-vs-0000000000001234.metal").read_text(
        encoding="utf-8"
    )
    assert (early_exit_output / "iphone-serverless-failure.png").is_file()
    assert_no_raw_log(early_exit_output, scratch)

print("PASS fail-closed iPhone/iPad serverless and online simulator screenshot runner mocks")
