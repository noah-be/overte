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
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys


CHUNK_SIZE = 1024 * 1024
MACHO_MAGICS = frozenset({
    b"\xfe\xed\xfa\xce",  # MH_MAGIC
    b"\xce\xfa\xed\xfe",  # MH_CIGAM
    b"\xfe\xed\xfa\xcf",  # MH_MAGIC_64
    b"\xcf\xfa\xed\xfe",  # MH_CIGAM_64
    b"\xca\xfe\xba\xbe",  # FAT_MAGIC
    b"\xbe\xba\xfe\xca",  # FAT_CIGAM
    b"\xca\xfe\xba\xbf",  # FAT_MAGIC_64
    b"\xbf\xba\xfe\xca",  # FAT_CIGAM_64
})


def dylib_inventory(lib_dir: Path) -> dict[str, Path]:
    inventory: dict[str, Path] = {}
    for candidate in sorted(lib_dir.glob("*.dylib*")):
        if candidate.is_file():
            inventory[candidate.name] = candidate
    return inventory


def file_digest(path: Path) -> bytes:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            value.update(chunk)
    return value.digest()


def files_identical(source: Path, destination: Path) -> bool:
    try:
        if not destination.is_file() or destination.is_symlink():
            return False
        if source.stat().st_size != destination.stat().st_size:
            return False
        return file_digest(source) == file_digest(destination)
    except OSError:
        return False


def is_macho(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            return stream.read(4) in MACHO_MAGICS
    except OSError:
        return False


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


def runtime_paths(path: Path, otool: str) -> list[str] | None:
    result = subprocess.run(
        [otool, "-l", str(path)], capture_output=True, text=True, check=False
    )
    if result.returncode:
        return None
    found: list[str] = []
    expect_path = False
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped == "cmd LC_RPATH":
            expect_path = True
        elif expect_path and stripped.startswith("path "):
            found.append(stripped[5:].split(" (offset ", 1)[0])
            expect_path = False
    return found


def fix_webengine_helper(
    contents: Path, otool: str, install_name_tool: str
) -> bool:
    frameworks = contents / "Frameworks"
    webengine = frameworks / "QtWebEngineCore.framework"
    if not webengine.exists():
        return False

    helper = (
        webengine
        / "Helpers/QtWebEngineProcess.app/Contents/MacOS/QtWebEngineProcess"
    )
    qt_gui = frameworks / "QtGui.framework/Versions/5/QtGui"
    if not helper.is_file():
        raise RuntimeError("QtWebEngine helper executable is missing from the bundle")
    if not qt_gui.is_file():
        raise RuntimeError("QtGui framework required by QtWebEngine is missing")

    helper_dependencies = dependencies(helper, otool)
    if helper_dependencies is None or not any(
        dependency.startswith("@rpath/QtGui.framework/")
        for dependency in helper_dependencies
    ):
        raise RuntimeError("QtWebEngine helper has no relocatable QtGui dependency")
    helper_rpaths = runtime_paths(helper, otool)
    if helper_rpaths is None:
        raise RuntimeError("unable to inspect QtWebEngine helper runtime paths")

    # From .../QtWebEngineProcess.app/Contents/MacOS, five parent components
    # lead to the main application's Contents/Frameworks directory.
    required_rpath = "@executable_path/../../../../.."
    if required_rpath not in helper_rpaths:
        subprocess.run(
            [install_name_tool, "-add_rpath", required_rpath, str(helper)],
            check=True,
        )
    return True


def deploy(
    app: Path,
    lib_dir: Path,
    otool: str,
    install_name_tool: str,
    preserve_existing: bool = False,
) -> int:
    contents = app / "Contents"
    if not contents.is_dir():
        raise RuntimeError(f"not a macOS application bundle: {app}")
    if not lib_dir.is_dir():
        raise RuntimeError(f"Conan library directory does not exist: {lib_dir}")

    inventory = dylib_inventory(lib_dir)
    frameworks = contents / "Frameworks"
    frameworks.mkdir(parents=True, exist_ok=True)

    copied = 0
    preserved = 0
    for basename, source in inventory.items():
        destination = frameworks / basename
        # Dereference Conan symlinks.  The resulting bundle must not contain a
        # link back into a CI worker's package cache.
        resolved_source = source.resolve()
        # --preserve-existing is only supplied by the outer DEV bundle helper
        # after its source-input and complete bundle-output hashes both match a
        # successful deployment. Standalone/full calls always compare/copy.
        if preserve_existing and destination.is_file() and not destination.is_symlink():
            preserved += 1
        elif not files_identical(resolved_source, destination):
            shutil.copy2(resolved_source, destination)
            copied += 1
        destination.chmod(destination.stat().st_mode | 0o200)

    macho_files: list[Path] = []
    for candidate in sorted(contents.rglob("*")):
        if candidate.is_file() and not candidate.is_symlink():
            if not is_macho(candidate):
                continue
            deps = dependencies(candidate, otool)
            if deps is None:
                raise RuntimeError(
                    f"unable to inspect Mach-O dependencies: {candidate.name}"
                )
            macho_files.append(candidate)
            if candidate.parent == frameworks and candidate.name in inventory:
                expected_id = f"@rpath/{candidate.name}"
                if expected_id not in deps:
                    subprocess.run(
                        [install_name_tool, "-id", expected_id, str(candidate)],
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

    fixed_webengine = fix_webengine_helper(contents, otool, install_name_tool)

    if not macho_files:
        raise RuntimeError(f"no Mach-O files found in application bundle: {app}")
    print(
        f"Deployed {len(inventory)} Conan dylibs "
        f"({copied} copied, {preserved} verified-preserved) and inspected "
        f"{len(macho_files)} Mach-O files; "
        f"QtWebEngine helper fixed={str(fixed_webengine).lower()}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--lib-dir", type=Path, required=True)
    parser.add_argument("--otool", default="otool")
    parser.add_argument("--install-name-tool", default="install_name_tool")
    parser.add_argument("--preserve-existing", action="store_true")
    args = parser.parse_args()
    try:
        return deploy(
            args.app.resolve(),
            args.lib_dir.resolve(),
            args.otool,
            args.install_name_tool,
            args.preserve_existing,
        )
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"deploy-conan-dylibs: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
