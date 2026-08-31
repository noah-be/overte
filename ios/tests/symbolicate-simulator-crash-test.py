#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

"""Exercise fail-closed Simulator crash symbolication with a fake atos."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "ios/tools/symbolicate-simulator-crash.py"
IMAGE_UUID = "87810988-b99f-37df-b30d-599a85a641b6"


def invoke(crash: Path, binary: Path, output: Path, environment: dict[str, str]):
    return subprocess.run(
        [str(TOOL), str(crash), str(binary), str(output)],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


with tempfile.TemporaryDirectory(prefix="overte-simulator-symbolicate-") as directory:
    root = Path(directory)
    bin_dir = root / "bin"
    bin_dir.mkdir()
    binary = root / "Overte"
    binary.write_bytes(b"fixture Mach-O")
    crash = root / "Overte-crash.log"
    report = {
        "faultingThread": 0,
        "exception": {
            "type": "EXC_BAD_ACCESS",
            "signal": "SIGSEGV",
            "subtype": "KERN_INVALID_ADDRESS at 0x2030",
        },
        "threads": [
            {
                "frames": [
                    {"imageOffset": 0x120, "imageIndex": 0},
                    {"imageOffset": 0x220, "imageIndex": 0},
                    {"imageOffset": 10, "imageIndex": 1},
                ]
            }
        ],
        "usedImages": [
            {
                "arch": "arm64",
                "base": 0x100000000,
                "uuid": IMAGE_UUID,
                "name": "Overte",
                "CFBundleIdentifier": "org.overte.interface.dev",
            },
            {"arch": "arm64", "base": 0x200000000, "uuid": "0" * 36, "name": "UIKit"},
        ],
    }
    crash.write_text(
        '=== Overte.ips ===\n{"app_name":"Overte"}\n'
        + json.dumps(report, indent=2)
        + "\n",
        encoding="utf-8",
    )
    fake_xcrun = bin_dir / "xcrun"
    fake_xcrun.write_text(
        """#!/bin/sh
set -eu
if [ "$1 $2" = "dwarfdump --uuid" ]; then
    printf 'UUID: %s (arm64) %s\n' "$FAKE_UUID" "$3"
elif [ "$1" = atos ]; then
    printf '%s\n' 'Overte::startup() (Application.cpp:101)' 'Overte::initialize() (main.cpp:55)'
else
    exit 64
fi
""",
        encoding="utf-8",
    )
    fake_xcrun.chmod(fake_xcrun.stat().st_mode | stat.S_IXUSR)
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FAKE_UUID": IMAGE_UUID,
    }

    output = root / "symbolicated.json"
    result = invoke(crash, binary, output, environment)
    assert result.returncode == 0, (result.stdout, result.stderr)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["signal"] == "SIGSEGV"
    assert payload["appImage"]["uuid"] == IMAGE_UUID
    assert [frame["address"] for frame in payload["frames"]] == ["0x100000120", "0x100000220"]
    assert payload["frames"][0]["symbol"] == "Overte::startup() (Application.cpp:101)"

    mismatch = root / "mismatch.json"
    mismatch_result = invoke(
        crash,
        binary,
        mismatch,
        {**environment, "FAKE_UUID": "123e4567-e89b-12d3-a456-426614174000"},
    )
    assert mismatch_result.returncode == 1
    assert "binary UUID does not match" in mismatch_result.stderr
    assert not mismatch.exists()

print("PASS fail-closed Simulator crash symbolication")
