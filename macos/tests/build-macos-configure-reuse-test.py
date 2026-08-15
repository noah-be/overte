#!/usr/bin/env python3
"""Hermetically verify exact CMake graph reuse and safe fallback."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / "macos/build-macos.sh"


def executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary_name:
    temporary = Path(temporary_name)
    fake_bin = temporary / "bin"
    fake_bin.mkdir()
    cmake_log = temporary / "cmake.log"
    executable(
        fake_bin / "uname",
        "#!/bin/sh\ncase \"${1:-}\" in -s) echo Darwin;; -m) echo x86_64;; *) echo Darwin;; esac\n",
    )
    executable(
        fake_bin / "xcodebuild",
        "#!/bin/sh\nprintf 'Xcode 16.4\\nBuild version 16F6\\n'\n",
    )
    executable(
        fake_bin / "conan",
        "#!/bin/sh\n[ \"${1:-}\" = --version ] && echo 'Conan version 2.31.2'\n",
    )
    executable(fake_bin / "node", "#!/bin/sh\nexit 0\n")
    executable(fake_bin / "aqt", "#!/bin/sh\nexit 0\n")
    executable(
        fake_bin / "cmake",
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$FAKE_CMAKE_LOG\"\n",
    )

    build = temporary / "build"
    build.mkdir()
    cache = build / "CMakeCache.txt"
    ninja = build / "build.ninja"
    exact_key = build / ".overte-macos-complete-key"
    ninja.write_text("# generated\n", encoding="utf-8")

    def write_cache(architecture: str) -> None:
        cache.write_text(
            "\n".join(
                (
                    "CMAKE_BUILD_TYPE:STRING=RelWithDebInfo",
                    f"CMAKE_HOME_DIRECTORY:INTERNAL={ROOT}",
                    "CMAKE_GENERATOR:INTERNAL=Ninja",
                    f"CMAKE_OSX_ARCHITECTURES:STRING={architecture}",
                    "CMAKE_OSX_DEPLOYMENT_TARGET:STRING=11.0",
                    "OVERTE_BUILD_TESTS:BOOL=ON",
                    "OVERTE_RELEASE_TYPE:STRING=DEV",
                    "OVERTE_RENDERING_BACKEND:STRING=OpenGL",
                    "",
                )
            ),
            encoding="utf-8",
        )

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "FAKE_CMAKE_LOG": str(cmake_log),
            "OVERTE_MACOS_BUILD_DIR": str(build),
            "OVERTE_MACOS_BUILD_TESTS": "ON",
            "OVERTE_MACOS_SKIP_CONFIGURE": "ON",
            "OVERTE_MACOS_EXPECTED_BUILD_TREE_KEY": "exact-complete-key",
        }
    )

    write_cache("x86_64")
    exact_key.write_text("exact-complete-key\n", encoding="utf-8")
    exact = subprocess.run(
        [str(BUILD_SCRIPT), "configure"],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    assert exact.returncode == 0, exact.stdout + exact.stderr
    assert "reusing exact verified CMake/Ninja graph" in exact.stdout
    assert not cmake_log.exists(), "exact verified graph must not invoke CMake"

    write_cache("arm64")
    fallback = subprocess.run(
        [str(BUILD_SCRIPT), "configure"],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    assert fallback.returncode == 0, fallback.stdout + fallback.stderr
    assert "cache invariants failed; configuring safely" in fallback.stdout
    invoked = cmake_log.read_text(encoding="utf-8")
    assert "--preset conan-relwithdebinfo" in invoked
    assert "-DOVERTE_BUILD_TESTS=ON" in invoked
    assert "-DCMAKE_OSX_ARCHITECTURES=x86_64" in invoked

    cmake_log.unlink()
    write_cache("x86_64")
    exact_key.write_text("another-key\n", encoding="utf-8")
    wrong_key = subprocess.run(
        [str(BUILD_SCRIPT), "configure"],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    assert wrong_key.returncode == 0, wrong_key.stdout + wrong_key.stderr
    assert "cache invariants failed; configuring safely" in wrong_key.stdout
    assert cmake_log.exists(), "a mismatched complete-tree proof must invoke CMake"

    invalid_environment = environment.copy()
    invalid_environment["OVERTE_MACOS_SKIP_CONFIGURE"] = "unexpected"
    invalid = subprocess.run(
        [str(BUILD_SCRIPT), "configure"],
        text=True,
        capture_output=True,
        check=False,
        env=invalid_environment,
    )
    assert invalid.returncode != 0
    assert "OVERTE_MACOS_SKIP_CONFIGURE must be ON or OFF" in invalid.stderr

print("macOS exact CMake configure reuse contract valid")
