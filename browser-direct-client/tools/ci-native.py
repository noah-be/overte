#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Dedicated direct-browser native CI in the reviewed dependency image.

Existing native CI remains unchanged: this lane explicitly enables the optional
transport, builds its open dependency, builds the real server processes, and
executes the new production transport/permissions tests.
"""
from __future__ import annotations

import os
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import re

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "build/browser-direct-ci"
SOURCE = STATE / "libdatachannel"
PREFIX = STATE / "prefix"
PIN = "6b1e2e620f1e37f0eafeee702eaea0043cb305fd"


def run(arguments: list[str]) -> None:
    subprocess.run(arguments, cwd=ROOT, check=True)


def main() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    os.environ["CONAN_HOME"] = str(STATE / "conan")
    os.environ["CCACHE_DIR"] = str(ROOT / ".native-direct-ccache")
    os.environ["CCACHE_MAXSIZE"] = "2G"
    os.environ["QT_RCC_SOURCE_DATE_OVERRIDE"] = "1"
    # Existing networking tests use QApplication even without a visible window.
    # The dedicated container has no display; use the same platform as the lab.
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    run(["python3", "tools/native-tests/packages.py", "--source", "."])
    spec = importlib.util.spec_from_file_location("native_select", ROOT / "tools/native-tests/select.py")
    selection = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(selection)
    policy = json.loads((ROOT / ".github/native-tests.json").read_text())
    selection.separately_qualified_names(policy, ROOT)
    required = sorted(policy["separate_lanes"]["browser-direct"]["tests"])
    required += sorted(name for name in policy["tests"] if name.startswith("networking-"))
    if not Path(os.environ["CONAN_HOME"]).exists():
        shutil.copytree("/root/.conan2", os.environ["CONAN_HOME"])
    if not SOURCE.exists():
        run(["git", "clone", "--branch", "v0.24.6", "--depth", "1", "--recurse-submodules",
             "--shallow-submodules", "https://github.com/paullouisageneau/libdatachannel.git", str(SOURCE)])
    actual = subprocess.check_output(["git", "-C", str(SOURCE), "rev-parse", "HEAD"], text=True).strip()
    if actual != PIN or subprocess.check_output(["git", "-C", str(SOURCE), "status", "--porcelain"], text=True).strip():
        raise RuntimeError("libdatachannel source identity does not match the reviewed release")
    submodules = subprocess.check_output(["git", "-C", str(SOURCE), "submodule", "status", "--recursive"], text=True)
    if any(line[0] != " " for line in submodules.splitlines()):
        raise RuntimeError("libdatachannel submodules differ from their reviewed parent")
    jobs = str(min(4, os.cpu_count() or 2))
    dependency_build = STATE / "dependency-build"
    run(["cmake", "-S", str(SOURCE), "-B", str(dependency_build), "-G", "Ninja",
         "-DCMAKE_BUILD_TYPE=Release", f"-DCMAKE_INSTALL_PREFIX={PREFIX}",
         "-DNO_MEDIA=ON", "-DNO_WEBSOCKET=ON", "-DNO_TESTS=ON", "-DNO_EXAMPLES=ON",
         "-DBUILD_SHARED_LIBS=ON", "-DBUILD_SHARED_DEPS_LIBS=OFF"])
    run(["cmake", "--build", str(dependency_build), "--target", "install", "--parallel", jobs])
    native = STATE / "native"
    run(["conan", "install", ".", "-pr", "tools/conan-profiles/linux", "-s", "compiler.cppstd=gnu20",
         "-s", "build_type=Release", "-o", "Overte/*:qt_source=system",
         "--lockfile=tools/native-tests/conan-linux.lock", "--build=never", "--no-remote", "-of", str(native)])
    run(["cmake", "-S", ".", "-B", str(native), "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
         "-DCMAKE_TOOLCHAIN_FILE=generators/conan_toolchain.cmake", f"-DCMAKE_PREFIX_PATH={PREFIX}",
         "-DCMAKE_C_COMPILER_LAUNCHER=ccache", "-DCMAKE_CXX_COMPILER_LAUNCHER=ccache",
         "-DOVERTE_BUILD_CLIENT=OFF", "-DOVERTE_BUILD_SERVER=ON", "-DOVERTE_BUILD_TOOLS=OFF",
         "-DOVERTE_BUILD_INSTALLER=OFF", "-DOVERTE_BUILD_TESTS=ON", "-DOVERTE_BUILD_MANUAL_TESTS=OFF",
         "-DOVERTE_TEST_GROUPS=networking;browser-direct-transport", "-DOVERTE_BROWSER_TRANSPORT=ON"])
    run(["cmake", "--build", str(native), "--parallel", jobs, "--target", "domain-server", "assignment-client",
         *required])
    discovered = json.loads(subprocess.check_output(["ctest", "--test-dir", str(native), "--show-only=json-v1"], text=True))
    test_names = {entry["name"] for entry in discovered["tests"]}
    expected = {name + "-test" for name in required}
    if expected - test_names:
        raise RuntimeError(f"Missing required direct-browser CTest executables: {sorted(expected - test_names)}")
    run(["ctest", "--test-dir", str(native), "--output-on-failure", "--no-tests=error",
         "--timeout", "45", "-R", "^(" + "|".join(re.escape(name) for name in sorted(expected)) + ")$",
         "--output-junit", str(STATE / "native-results.xml")])


if __name__ == "__main__":
    main()
