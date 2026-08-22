#!/usr/bin/env python3
"""Fail closed when an emulator Conan readiness marker outlives its packages."""

from __future__ import annotations

import hashlib
import re
import shlex
import sys
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"error: {message}")


def parse_cmake_list(source: str, variable: str) -> list[str]:
    match = re.search(rf"set\({re.escape(variable)}\s+([^)]*)\)", source, re.DOTALL)
    if match is None:
        return []
    return [token.strip('"') for token in shlex.split(match.group(1), posix=True)]


def library_exists(name: str, directories: list[Path]) -> bool:
    candidates = (f"lib{name}.so*", f"lib{name}.a", f"{name}.so*", f"{name}.a")
    return any(any(directory.glob(pattern)) for directory in directories for pattern in candidates)


def main() -> None:
    if len(sys.argv) != 5:
        fail("usage: verify-phone-emulator-dependencies.py OUTPUT PROFILE SENTINEL HOST_TOOLS")

    output_dir, profile, sentinel, host_tools = map(Path, sys.argv[1:])
    if not profile.is_file() or not sentinel.is_file():
        fail("the emulator profile or readiness marker is missing")
    if sentinel.stat().st_size > 4096:
        fail("the emulator readiness marker is oversized")

    marker: dict[str, str] = {}
    for line in sentinel.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if not separator or not key or key in marker:
            fail("the emulator readiness marker is malformed")
        marker[key] = value
    expected_profile = hashlib.sha256(profile.read_bytes()).hexdigest()
    if marker != {"abi": "x86_64", "profile": expected_profile}:
        fail("the emulator readiness marker does not match its profile")

    for tool in ("glslangValidator", "scribe", "spirv-cross", "spirv-opt"):
        candidate = host_tools / tool
        if not candidate.exists() or not candidate.is_file() or not candidate.stat().st_mode & 0o111:
            fail(f"the prepared emulator host tool is unavailable: {tool}")

    generators = output_dir / "generators"
    data_files = sorted(generators.glob("*-debug-x86_64-data.cmake"))
    qt_files = sorted(generators.glob("Qt5-debug-*-data.cmake"))
    if not data_files or len(qt_files) != 1:
        fail("the emulator Conan generator set is incomplete")

    package_count = 0
    for data_file in data_files:
        source = data_file.read_text(encoding="utf-8")
        package_match = re.search(
            r'set\(([^\s)]+)_PACKAGE_FOLDER_DEBUG "([^"]+)"\)', source
        )
        if package_match is None:
            continue
        variable, package_text = package_match.groups()
        package = Path(package_text)
        package_count += 1
        if not package.is_dir():
            fail(f"an emulator Conan package is missing: {data_file.name}")

        library_dirs = []
        for directory in parse_cmake_list(source, f"{variable}_LIB_DIRS_DEBUG"):
            expanded = directory.replace(f"${{{variable}_PACKAGE_FOLDER_DEBUG}}", str(package))
            library_dirs.append(Path(expanded))
        for library in parse_cmake_list(source, f"{variable}_LIBS_DEBUG"):
            if library.startswith("$"):
                continue
            if not library_exists(library, library_dirs):
                fail(f"an emulator Conan library is missing: {data_file.name}:{library}")

    if package_count == 0:
        fail("the emulator Conan generator set contains no package roots")

    qt_source = qt_files[0].read_text(encoding="utf-8")
    qt_match = re.search(r'set\(qt_PACKAGE_FOLDER_DEBUG "([^"]+)"\)', qt_source)
    if qt_match is None:
        fail("the emulator Qt package root is missing")
    qt_package = Path(qt_match.group(1))
    if not any(qt_package.rglob("*x86_64.so")):
        fail("the emulator Qt package contains no x86_64 runtime")

    print(f"Phone emulator dependency cache verified ({package_count} packages).")


if __name__ == "__main__":
    main()
