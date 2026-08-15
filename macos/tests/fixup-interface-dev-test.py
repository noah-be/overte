#!/usr/bin/env python3
"""Hermetically configure the macOS DEV Interface post-build command."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]


with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary_name:
    temporary = Path(temporary_name)
    source = temporary / "source"
    build = temporary / "build"
    source.mkdir()
    qt_root = temporary / "qt"
    qt_core_dir = qt_root / "lib/cmake/Qt5Core"
    qt_core_dir.mkdir(parents=True)
    macdeployqt = qt_root / "bin/macdeployqt"
    macdeployqt.parent.mkdir(parents=True)
    macdeployqt.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    macdeployqt.chmod(0o755)
    (source / "main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    cmake_source = f"""
cmake_minimum_required(VERSION 3.16)
project(FixupInterfaceDevContract C)
set(APPLE TRUE)
set(CMAKE_BUILD_TYPE RelWithDebInfo)
set(Qt5Core_DIR "{qt_core_dir.as_posix()}")
set(Python3_EXECUTABLE "{Path(sys.executable).as_posix()}")
set(OVERTE_RELEASE_TYPE DEV)
set(TARGET_NAME interface)
set(INTERFACE_BUNDLE_NAME interface)
set(INTERFACE_INSTALL_DIR .)
set(CLIENT_COMPONENT client)
add_executable(interface MACOSX_BUNDLE main.c)
include("{(ROOT / 'cmake/macros/FixupInterface.cmake').as_posix()}")
fixup_interface()
"""
    (source / "CMakeLists.txt").write_text(cmake_source, encoding="utf-8")
    configured = subprocess.run(
        ["cmake", "-S", str(source), "-B", str(build), "-G", "Ninja"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert configured.returncode == 0, configured.stdout + configured.stderr
    ninja = (build / "build.ninja").read_text(encoding="utf-8")
    for contract in (
        "deploy-macos-dev-bundle.py",
        "--executable",
        "--qml-dir",
        "--lib-dir",
        "--macdeployqt",
        "--deploy-conan-tool",
        "macos-deploy/RelWithDebInfo/interface-bundle.json",
    ):
        assert contract in ninja, f"generated DEV post-build command missing: {contract}"
    assert "cmake -E remove_directory" not in ninja

print("macOS DEV Interface post-build CMake contract valid")
