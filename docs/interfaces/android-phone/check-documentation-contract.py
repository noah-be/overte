#!/usr/bin/env python3
"""Fail closed on stale Android Phone documentation commands and orientation claims."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PHONE_DOC_ROOTS = (
    ROOT / "docs/interfaces/android-phone",
    ROOT / "android/phone/docs",
)

STALE_TEXT = {
    "cd android\n": "Phone-relative commands must start with cd android/phone",
    "./build-phone.sh": "the checked-in Phone entry point is ./build.sh",
    "android/apps/phoneInterface": "the module is below android/phone/apps",
    "settings-phone.gradle": "the checked-in settings file is android/phone/settings.gradle",
    "portrait support, 32-bit": "portrait is tolerated by fullSensor, not disabled",
    "Portrait, 32-bit": "portrait is tolerated by fullSensor, not disabled",
}

# Each public command family is bound to the exact executable in a clean checkout.
REQUIRED_COMMANDS = {
    "./build.sh doctor": "android/phone/build.sh",
    "./build.sh setup --download": "android/phone/build.sh",
    "./build.sh build": "android/phone/build.sh",
    "./phone-emulator-test.sh doctor": "android/phone/phone-emulator-test.sh",
    "./phone-emulator-test.sh all": "android/phone/phone-emulator-test.sh",
    "./tests/phone-static-regression-test.sh": "android/phone/tests/phone-static-regression-test.sh",
    "./tests/phone-host-regression-test.sh": "android/phone/tests/phone-host-regression-test.sh",
    "./tests/phone-device-test.sh": "android/phone/tests/phone-device-test.sh",
    "./build-phone-qt-16k.sh": "android/phone/build-phone-qt-16k.sh",
    "./prepare-phone-16k-conan-deps.sh": "android/phone/prepare-phone-16k-conan-deps.sh",
    "./phone-prebuilt-16k-deps.sh": "android/phone/phone-prebuilt-16k-deps.sh",
    "./finalize-phone-16k-deps.sh": "android/phone/finalize-phone-16k-deps.sh",
    "./tests/check-phone-apk-16k.sh": "android/phone/tests/check-phone-apk-16k.sh",
    "../common/gradlew --settings-file settings.gradle": "android/common/gradlew",
    "../vr/pico/build.sh deps --download": "android/vr/pico/build.sh",
    "python3 tests/device/run.py": "tests/device/run.py",
    "android/phone/ci/verify-phone-release.py": "android/phone/ci/verify-phone-release.py",
}

REQUIRED_PATHS = (
    "android/phone/settings.gradle",
    "android/phone/apps/phoneInterface",
    "tests/device/adapters/appium/android.json",
    "tests/device/catalog.json",
    "tests/device/policies/android-phone-flat-touch.json",
)

ORIENTATION_MARKERS = (
    'android:screenOrientation="fullSensor"',
    "| Supported |",
    "| Tolerated, not yet qualified |",
    "| Unsupported / no claim |",
)

WORKFLOW_MARKERS = (
    "issues/599",
    "GitHub Issues are the only authoritative task source",
    "Inbox → Ready → Active → Closed",
)


def active_markdown() -> list[Path]:
    docs: list[Path] = []
    for base in PHONE_DOC_ROOTS:
        for path in sorted(base.rglob("*.md")):
            if "archive" not in path.relative_to(base).parts:
                docs.append(path)
    return docs


def stale_errors(path: str, text: str) -> list[str]:
    return [f"{path}: {message}" for token, message in STALE_TEXT.items() if token in text]


def validate() -> list[str]:
    errors: list[str] = []
    docs = active_markdown()
    combined = "\n".join(path.read_text(encoding="utf-8") for path in docs)
    for path in docs:
        errors.extend(stale_errors(str(path.relative_to(ROOT)), path.read_text(encoding="utf-8")))

    for snippet, relative in REQUIRED_COMMANDS.items():
        target = ROOT / relative
        if snippet not in combined:
            errors.append(f"documentation: required command is absent: {snippet}")
        if not target.is_file() or not os.access(target, os.X_OK):
            errors.append(f"checkout: command target is not executable: {relative}")

    for relative in REQUIRED_PATHS:
        if not (ROOT / relative).exists():
            errors.append(f"checkout: documented path does not exist: {relative}")

    orientation = (ROOT / "docs/interfaces/android-phone/ORIENTATION.md").read_text(encoding="utf-8")
    for marker in ORIENTATION_MARKERS:
        if marker not in orientation:
            errors.append(f"orientation contract: missing marker: {marker}")

    manifest = (ROOT / "android/phone/apps/phoneInterface/src/main/AndroidManifest.xml").read_text(
        encoding="utf-8"
    )
    if manifest.count('android:screenOrientation="fullSensor"') != 2:
        errors.append("manifest: expected exactly two fullSensor Phone Activity declarations")

    workflow = (ROOT / "docs/interfaces/android-phone/WORKING_SYSTEM.md").read_text(encoding="utf-8")
    for marker in WORKFLOW_MARKERS:
        if marker not in workflow:
            errors.append(f"WORKING_SYSTEM.md: missing Issue #599 workflow marker: {marker}")
    return errors


def self_test() -> list[str]:
    fixtures = {
        "stale-build": "cd android\n./build-phone.sh doctor\n",
        "stale-apk": "android/apps/phoneInterface/build/outputs/apk/debug/app.apk",
        "stale-orientation": "Portrait, 32-bit devices, and release are outside scope.",
    }
    errors: list[str] = []
    for name, text in fixtures.items():
        if not stale_errors(name, text):
            errors.append(f"self-test: stale fixture was accepted: {name}")
    if stale_errors("valid", "cd android/phone\n./build.sh doctor\n"):
        errors.append("self-test: valid Phone command was rejected")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    errors = self_test() if args.self_test else validate()
    if errors:
        print("PHONE_DOCUMENTATION_CONTRACT=FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    result = "SELF_TEST_PASS" if args.self_test else "PASS"
    print(f"PHONE_DOCUMENTATION_CONTRACT={result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
