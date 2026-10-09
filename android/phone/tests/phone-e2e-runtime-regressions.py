#!/usr/bin/env python3
"""Mandatory Phone-native contracts excluded from the shared source profile."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
CHECKS = (
    "android/phone/tests/phone-test-inventory-test.py",
    "android/phone/tests/test_phone_ime.py",
    "android/phone/tests/phone-apk-provenance-test.py",
    "android/phone/tests/test_phone_voice_signal.py",
    "tests/device/contracts/world-entry/test_phone_feet_alignment.py",
    "tests/device/contracts/world-entry/test_phone_pad_projection.py",
    "tests/device/contracts/tablet/test_phone_settings_click.py",
    "tests/device/contracts/lifecycle/test_phone_native_startup.py",
    "tests/device/contracts/test_phone_accessibility_tree.py",
)
parser = argparse.ArgumentParser()
parser.add_argument("--execute", action="store_true",
                    help="execute the Qt/GLM native contracts on the prepared host")
args = parser.parse_args()
# Every declared input is required even in dependency-light platform checks.
for name in CHECKS:
    if not (ROOT / name).is_file():
        raise SystemExit("Missing mandatory Phone runtime contract: " + name)
for name in (CHECKS[3:] if args.execute else CHECKS[:3]):
    path = ROOT / name
    if not path.is_file():
        raise SystemExit("Missing mandatory Phone runtime contract: " + name)
    print("Phone runtime contract: " + name, flush=True)
    arguments = [sys.executable, str(path)]
    if name.endswith("phone-test-inventory-test.py"):
        arguments.append(str(ROOT))
    subprocess.run(arguments, cwd=ROOT, check=True, timeout=90)
