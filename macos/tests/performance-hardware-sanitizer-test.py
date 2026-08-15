#!/usr/bin/env python3
"""Hermetic contracts for allowlist-only macOS performance hardware evidence."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
SANITIZER = ROOT / "macos/tools/sanitize-performance-hardware.py"
RUNNER = ROOT / "macos/ci/performance-matrix.sh"


RAW = {
    "SPHardwareDataType": [{
        "_name": "hardware_overview",
        "machine_model": "Mac14,3",
        "machine_name": "Mac mini",
        "chip_type": "Apple M2",
        "processor_name": "Raw CPU Model",
        "number_processors": "proc 8:4:4",
        "physical_memory": "16 GB",
        "serial_number": "SECRET-SERIAL",
        "platform_UUID": "SECRET-UUID",
        "provisioning_UDID": "SECRET-UDID",
        "computer_name": "secret-hostname",
    }],
    "SPDisplaysDataType": [{
        "_name": "Apple M2",
        "sppci_model": "Apple M2",
        "spdisplays_vendor": "sppci_vendor_Apple",
        "spdisplays_vram": "8 GB",
        "_metal_path": "SECRET-IO-PATH",
        "spdisplays_ndrvs": [{
            "_name": "Color LCD",
            "_spdisplays_resolution": "2560 x 1440 @ 60.00Hz",
            "spdisplays_main": "spdisplays_yes",
            "spdisplays_online": "spdisplays_yes",
            "spdisplays_connection_type": "spdisplays_internal",
            "_IODisplayEDID": "SECRET-EDID",
            "_spdisplays_display-serial-number": "SECRET-DISPLAY-SERIAL",
            "_spdisplays_displayPath": "SECRET-DISPLAY-PATH",
        }],
    }],
    "nics": [{"name": "en0", "mac": "AA:BB:CC:DD:EE:FF"}],
    "unexpected": {"token": "SECRET-TOKEN", "hostname": "secret-hostname"},
}


def run(payload: object, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SANITIZER),
            "--output",
            str(output),
            "--os-name",
            "macOS",
            "--os-version",
            "15.7.7",
            "--os-build",
            "24G720",
            "--cpu-model",
            "Apple M2",
        ],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )


with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as directory:
    temporary = Path(directory)
    output = temporary / "hardware.json"
    completed = run(RAW, output)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence == {
        "schema_version": 1,
        "os": {"name": "macOS", "version": "15.7.7", "build": "24G720"},
        "computer": {
            "model": "Mac14,3",
            "name": "Mac mini",
            "chip": "Apple M2",
            "cpu_model": "Apple M2",
            "cpu_cores": 8,
            "memory_bytes": 16 * 1024**3,
        },
        "gpus": [{
            "model": "Apple M2",
            "vendor": "sppci_vendor_Apple",
            "vram_bytes": 8 * 1024**3,
            "displays": [{
                "name": "Color LCD",
                "width": 2560,
                "height": 1440,
                "refresh_hz": 60.0,
                "primary": True,
                "online": True,
                "connection": "spdisplays_internal",
            }],
        }],
    }
    serialized = output.read_text(encoding="utf-8")
    for forbidden in (
        "SECRET", "serial", "uuid", "udid", "hostname", "nics", "edid",
        "AA:BB:CC:DD:EE:FF",
    ):
        assert forbidden.lower() not in serialized.lower(), forbidden
    assert '"mac":' not in serialized.lower()
    assert output.stat().st_mode & 0o777 == 0o600
    classification = subprocess.run(
        [sys.executable, str(SANITIZER), "--classify", str(output)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert classification.returncode == 0
    assert classification.stdout.strip() == "hardware"

    diagnostic_evidence = json.loads(output.read_text(encoding="utf-8"))
    diagnostic_evidence["gpus"][0]["model"] = "Apple Paravirtualized Graphics Device"
    diagnostic = temporary / "diagnostic-hardware.json"
    diagnostic.write_text(json.dumps(diagnostic_evidence), encoding="utf-8")
    diagnostic_classification = subprocess.run(
        [sys.executable, str(SANITIZER), "--classify", str(diagnostic)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert diagnostic_classification.returncode == 0
    assert diagnostic_classification.stdout.strip() == "diagnostic"

    profile_result = temporary / "macos-profile.json"
    profile_result.write_text(json.dumps({
        "schema_version": 3,
        "platform": "macos",
        "fixture_features": ["semantic-markers"],
        "fixture_present_delta": 2,
        "fixture_sha256": "a" * 64,
        "platform_info": {
            "platform": {
                "graphicsAPIs": [{
                    "name": "OpenGL",
                    "renderer": "Apple M2",
                    "vendor": "Apple Inc.",
                    "version": "4.1",
                    "extensions": ["SECRET-EXTENSION"],
                }],
                "nics": [{"name": "en0", "mac": "AA:BB:CC:DD:EE:FF"}],
                "memory": {"secret": "SECRET-MEMORY"},
            },
            "computer": {
                "model": "Mac14,3", "OS": "MACOS", "OSVersion": "24.6.0",
                "serial_number": "SECRET-SERIAL",
            },
            "cpu": {"model": "Apple M2", "numCores": 8, "token": "SECRET-TOKEN"},
            "gpu": {"model": "Apple M2", "serial": "SECRET-GPU-SERIAL"},
            "display": {
                "modeWidth": 2560, "modeHeight": 1440, "modeRefreshrate": 60,
                "macos_serial": 1234,
            },
            "tier": 3,
            "deferred_capable": True,
        },
        "unexpected_secret": "SECRET-TOP-LEVEL",
    }), encoding="utf-8")
    profile_sanitization = subprocess.run(
        [sys.executable, str(SANITIZER), "--profile-result", str(profile_result)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert profile_sanitization.returncode == 0, profile_sanitization.stderr
    profile = json.loads(profile_result.read_text(encoding="utf-8"))
    assert profile["platform_info"] == {
        "platform": {"graphicsAPIs": [{
            "name": "OpenGL", "renderer": "Apple M2", "vendor": "Apple Inc.",
            "version": "4.1",
        }]},
        "computer": {"model": "Mac14,3", "OS": "MACOS", "OSVersion": "24.6.0"},
        "cpu": {"model": "Apple M2", "numCores": 8},
        "gpu": {"model": "Apple M2"},
        "display": {"modeWidth": 2560, "modeHeight": 1440, "modeRefreshrate": 60},
        "tier": 3,
        "deferred_capable": True,
    }
    assert profile["fixture_present_delta"] == 2
    assert profile_result.stat().st_mode & 0o777 == 0o600
    profile_serialized = profile_result.read_text(encoding="utf-8").lower()
    for forbidden in ("secret", "serial", "nics", '"mac":', "aa:bb:cc:dd:ee:ff"):
        assert forbidden not in profile_serialized, forbidden

    invalid_output = temporary / "invalid.json"
    invalid = subprocess.run(
        [
            sys.executable, str(SANITIZER), "--output", str(invalid_output),
            "--os-name", "macOS", "--os-version", "15.7.7", "--os-build", "24G720",
        ],
        input="not json",
        text=True,
        capture_output=True,
        check=False,
    )
    assert invalid.returncode == 1
    assert not invalid_output.exists()
    assert "not json" not in invalid.stderr

    target = temporary / "target.json"
    target.write_text("preserve", encoding="utf-8")
    symlink = temporary / "symlink.json"
    symlink.symlink_to(target)
    refused = run(RAW, symlink)
    assert refused.returncode == 1
    assert target.read_text(encoding="utf-8") == "preserve"

runner = RUNNER.read_text(encoding="utf-8")
assert "uname -a" not in runner
assert 'system_profiler -json SPHardwareDataType SPDisplaysDataType >' not in runner
for contract in (
    "sanitize-performance-hardware.py",
    '--output "$output_dir/hardware.json"',
    '--classify "$output_dir/hardware.json"',
    'private_results="$(mktemp -d',
    '--testResultsLocation "$private_results"',
    '--profile-result "$private_profile_result"',
    'mv "$private_profile_result" "$profile_result"',
):
    assert contract in runner, f"performance matrix runner is missing privacy contract: {contract}"

print("macOS performance hardware sanitizer tests passed")
