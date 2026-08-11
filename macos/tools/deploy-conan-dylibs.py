#!/usr/bin/env python3
"""Deploy Conan dylibs referenced by a macOS application bundle.

macdeployqt does not reliably copy dependencies whose install name starts at
``/lib``.  Conan already collects those libraries in a flat directory.  This
tool copies that inventory into Contents/Frameworks and changes only install
names whose basename is present in the inventory.  System and Qt install names
are deliberately left to macdeployqt.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def dylib_inventory(lib_dir: Path) -> dict[str, Path]:
    inventory: dict[str, Path] = {}
    for candidate in sorted(lib_dir.glob("*.dylib*")):
        if candidate.is_file():
            inventory[candidate.name] = candidate
    return inventory


def dependencies(path: Path, otool: str) -> list[str] | None:
    result = subprocess.run(
        [otool, "-L", str(path)], capture_output=True, text=True, check=False
    )
    if result.returncode:
        return None
    found: list[str] = []
    for line in result.stdout.splitlines()[1:]:
        install_name = line.strip().split(" (", 1)[0]
        if install_name:
            found.append(install_name)
    return found


def deploy(app: Path, lib_dir: Path, otool: str, install_name_tool: str) -> int:
    contents = app / "Contents"
    if not contents.is_dir():
        raise RuntimeError(f"not a macOS application bundle: {app}")
    if not lib_dir.is_dir():
        raise RuntimeError(f"Conan library directory does not exist: {lib_dir}")

    inventory = dylib_inventory(lib_dir)
    frameworks = contents / "Frameworks"
    frameworks.mkdir(parents=True, exist_ok=True)

    for basename, source in inventory.items():
        destination = frameworks / basename
        # Dereference Conan symlinks.  The resulting bundle must not contain a
        # link back into a CI worker's package cache.
        shutil.copy2(source.resolve(), destination)
        destination.chmod(destination.stat().st_mode | 0o200)

    macho_files: list[Path] = []
    for candidate in sorted(contents.rglob("*")):
        if candidate.is_file() and not candidate.is_symlink():
            deps = dependencies(candidate, otool)
            if deps is None:
                continue
            macho_files.append(candidate)
            if candidate.parent == frameworks and candidate.name in inventory:
                subprocess.run(
                    [install_name_tool, "-id", f"@rpath/{candidate.name}", str(candidate)],
                    check=True,
                )
            for old_name in deps:
                basename = os.path.basename(old_name)
                if basename not in inventory:
                    continue
                new_name = f"@rpath/{basename}"
                if old_name != new_name:
                    subprocess.run(
                        [install_name_tool, "-change", old_name, new_name, str(candidate)],
                        check=True,
                    )

    if not macho_files:
        raise RuntimeError(f"no Mach-O files found in application bundle: {app}")
    print(
        f"Deployed {len(inventory)} Conan dylibs and inspected "
        f"{len(macho_files)} Mach-O files"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--lib-dir", type=Path, required=True)
    parser.add_argument("--otool", default="otool")
    parser.add_argument("--install-name-tool", default="install_name_tool")
    args = parser.parse_args()
    try:
        return deploy(
            args.app.resolve(),
            args.lib_dir.resolve(),
            args.otool,
            args.install_name_tool,
        )
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"deploy-conan-dylibs: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
