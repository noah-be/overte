#!/usr/bin/env python3
"""Mock contracts for Fedora-side privacy-minimal iPad log capture."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "ios/tools/fedora-ipad-log.py"
DEVICE_ID = "00008110-001234567890001E"
REVISION = "a" * 40
DIGEST = "b" * 64
BUNDLE = "org.overte.interface.dev"


def executable(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def environment(root: Path, mode: str = "one") -> dict[str, str]:
    bin_dir = root / "bin"
    bin_dir.mkdir(exist_ok=True)
    executable(
        bin_dir / "idevice_id",
        "#!/usr/bin/env python3\n"
        "import os\n"
        "mode=os.environ.get('FAKE_DEVICE_MODE','one')\n"
        f"print('{DEVICE_ID}') if mode in ('one','multiple') else None\n"
        "print('00008110-SECONDDEVICE00002') if mode == 'multiple' else None\n",
    )
    executable(
        bin_dir / "idevicesyslog",
        "#!/usr/bin/env python3\n"
        "print('unrelated process owner=PrivatePerson')\n"
        f"print('Overte {BUNDLE} udid={DEVICE_ID} user=Alice alice@example.test 192.0.2.5 /home/alice/cache iPad14,5')\n"
        f"print('Overte lifecycle foreground {BUNDLE}')\n",
    )
    result = os.environ.copy()
    result["PATH"] = f"{bin_dir}:{result['PATH']}"
    result["FAKE_DEVICE_MODE"] = mode
    return result


def run_capture(root: Path, mode: str = "one") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable, str(TOOL), "capture",
            "--output-dir", str(root / "evidence"),
            "--bundle-id", BUNDLE,
            "--source-revision", REVISION,
            "--ipa-sha256", DIGEST,
            "--duration-seconds", "1",
        ],
        cwd=ROOT, env=environment(root, mode), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=5,
    )


with tempfile.TemporaryDirectory(prefix="overte-fedora-ipad-log-") as temporary:
    root = Path(temporary)
    success = run_capture(root)
    assert success.returncode == 0, (success.stdout, success.stderr)
    manifest = json.loads((root / "evidence/capture.json").read_text(encoding="utf-8"))
    log = (root / "evidence/overte-ipad-syslog.txt").read_text(encoding="utf-8")
    public = success.stdout + success.stderr + json.dumps(manifest) + log
    for secret in (DEVICE_ID, "Alice", "alice@example.test", "192.0.2.5", "/home/alice", "iPad14,5"):
        assert secret not in public, secret
    assert "unrelated process" not in log
    assert manifest["matchedLineCount"] == 2
    assert manifest["privacy"] == {
        "containsRawDeviceIdentifier": False,
        "containsDeviceModel": False,
        "containsUserInformation": False,
    }
    assert stat.S_IMODE((root / "evidence").stat().st_mode) == 0o700
    assert stat.S_IMODE((root / "evidence/capture.json").stat().st_mode) == 0o600

with tempfile.TemporaryDirectory(prefix="overte-fedora-ipad-log-multiple-") as temporary:
    root = Path(temporary)
    multiple = run_capture(root, "multiple")
    assert multiple.returncode == 1
    assert "exactly one trusted iPad" in multiple.stderr
    assert DEVICE_ID not in multiple.stdout + multiple.stderr
    assert not (root / "evidence").exists()

print("PASS Fedora iPad privacy-minimal log capture contracts")
