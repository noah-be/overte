#!/usr/bin/env python3
"""Lock the opt-in iOS E2E application contract and normal-release isolation."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import plistlib
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
IOS = ROOT / "ios"


def load_validator():
    path = IOS / "tools/verify-e2e-test-build.py"
    spec = importlib.util.spec_from_file_location("e2e_test_build_validator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rejected(*arguments: str) -> str:
    completed = subprocess.run(
        [str(IOS / "build-ios.sh"), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 1, (completed.stdout, completed.stderr)
    return completed.stderr


def main() -> None:
    validator = load_validator()
    with (IOS / "resources/InterfaceInfo.plist.in").open("rb") as stream:
        normal = plistlib.load(stream)
    with (IOS / "resources/InterfaceE2EInfo.plist.in").open("rb") as stream:
        e2e = plistlib.load(stream)
    validator.validate(normal, "disabled")
    validator.validate(e2e, "enabled")
    for info, expected in ((normal, "enabled"), (e2e, "disabled")):
        try:
            validator.validate(info, expected)
        except ValueError:
            pass
        else:
            raise AssertionError("E2E marker isolation must fail closed")

    build_script = (IOS / "build-ios.sh").read_text(encoding="utf-8")
    cmake = (ROOT / "interface/CMakeLists.txt").read_text(encoding="utf-8")
    setup = (ROOT / "interface/src/Application_Setup.cpp").read_text(encoding="utf-8")
    assert "-DOVERTE_IOS_E2E_TEST_BUILD=" in build_script
    assert "verify-e2e-test-build.py" in build_script
    assert "InterfaceE2EInfo.plist.in" in cmake
    assert 'MATCHES "[.]e2e$"' in cmake
    assert "#if defined(Q_OS_IOS) && defined(OVERTE_IOS_E2E_TEST_BUILD)" in setup
    assert "FileUtils::computeDocumentPath(path)" in setup
    assert "QDir::cleanPath" in setup
    assert 'path.startsWith(documentsRoot + "/")' in setup
    assert "Rejected iOS E2E results path outside Documents" in setup
    assert "QDir().mkpath(path)" in setup

    assert "explicit --bundle-id" in rejected(
        "configure", "--platform", "device", "--client-graph", "--e2e-test-build"
    )
    assert "requires --platform device" in rejected(
        "configure", "--platform", "simulator", "--client-graph", "--e2e-test-build",
        "--bundle-id", "org.overte.interface.e2e",
    )
    assert "must end in .e2e" in rejected(
        "configure", "--platform", "device", "--client-graph", "--e2e-test-build",
        "--bundle-id", "org.overte.interface.release",
    )
    assert "requires --client-graph" in rejected(
        "configure", "--platform", "device", "--e2e-test-build",
        "--bundle-id", "org.overte.interface.e2e",
    )
    print("iOS E2E test-build contract passed")


if __name__ == "__main__":
    main()
