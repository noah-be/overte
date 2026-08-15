#!/usr/bin/env python3
"""Host tests for fail-closed iOS Mach-O runtime dependency validation."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import io
import plistlib
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


IOS_ROOT = Path(__file__).resolve().parents[1]
TOOL = IOS_ROOT / "tools/verify-ios-static-runtime.py"


def load_tool():
    specification = importlib.util.spec_from_file_location("ios_static_runtime", TOOL)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def path_command(command: int, value: str, minimum_size: int) -> bytes:
    encoded = value.encode("utf-8") + b"\0"
    size = minimum_size + len(encoded)
    size = (size + 7) & ~7
    if minimum_size == 24:
        prefix = struct.pack("<IIIIII", command, size, minimum_size, 0, 0, 0)
    else:
        prefix = struct.pack("<III", command, size, minimum_size)
    return prefix + encoded + b"\0" * (size - len(prefix) - len(encoded))


def macho(*commands: bytes) -> bytes:
    command_data = b"".join(commands)
    header = struct.pack(
        "<IiiIIIII",
        0xFEEDFACF,
        0x0100000C,
        0,
        2,
        len(commands),
        len(command_data),
        0,
        0,
    )
    return header + command_data + b"fixture"


def expect_failure(callable_object, expected: str) -> None:
    try:
        callable_object()
    except ValueError as error:
        assert expected in str(error), (expected, str(error))
    else:
        raise AssertionError(f"unsafe Mach-O accepted; expected {expected!r}")


def main() -> None:
    verifier = load_tool()
    system = path_command(
        verifier.LC_LOAD_DYLIB,
        "/System/Library/Frameworks/Foundation.framework/Foundation",
        24,
    )
    libsystem = path_command(verifier.LC_LOAD_DYLIB, "/usr/lib/libSystem.B.dylib", 24)
    safe_rpath = path_command(verifier.LC_RPATH, "@executable_path/Frameworks", 12)
    payload = macho(system, libsystem, safe_rpath)
    report = verifier.audit_macho_parts(payload[:32], payload[32 : 32 + len(system + libsystem + safe_rpath)])
    assert report["dependencies"] == [
        "/System/Library/Frameworks/Foundation.framework/Foundation",
        "/usr/lib/libSystem.B.dylib",
    ]
    assert report["rpaths"] == ["@executable_path/Frameworks"]

    verifier.audit_macho_stream(io.BytesIO(payload))
    marker = verifier.FORBIDDEN_IOS_UI_MARKERS[0]
    split = len(marker) // 2
    boundary_payload = payload + b"x" * (verifier.SCAN_CHUNK_BYTES - len(payload) - split)
    boundary_payload += marker + b"fixture tail"
    expect_failure(
        lambda: verifier.audit_macho_stream(io.BytesIO(boundary_payload)),
        "legacy desktop display-mode selector",
    )

    for dependency in (
        "/lib/libwebrtc-audio-processing-2.1.dylib",
        "@rpath/libtbb.12.dylib",
        "@loader_path/libInjected.dylib",
    ):
        broken = path_command(verifier.LC_LOAD_DYLIB, dependency, 24)
        data = macho(broken)
        expect_failure(
            lambda data=data, broken=broken: verifier.audit_macho_parts(
                data[:32], data[32 : 32 + len(broken)]
            ),
            "non-system runtime dependencies",
        )

    build_rpath = path_command(
        verifier.LC_RPATH,
        "/Users/runner/work/overte/build-ios/conan-home/p/lib",
        12,
    )
    data = macho(build_rpath)
    expect_failure(
        lambda: verifier.audit_macho_parts(data[:32], data[32 : 32 + len(build_rpath)]),
        "build-local runtime search paths",
    )

    with tempfile.TemporaryDirectory(prefix="overte-static-runtime-") as temporary:
        app = Path(temporary) / "Overte.app"
        app.mkdir()
        (app / "Info.plist").write_bytes(
            plistlib.dumps({"CFBundleExecutable": "Overte"})
        )
        executable = app / "Overte"
        executable.write_bytes(payload)
        completed = subprocess.run(
            [sys.executable, str(TOOL), str(app)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        assert '"thirdPartyRuntimeDependencies": []' in completed.stdout

    build_script = (IOS_ROOT / "build-ios.sh").read_text(encoding="utf-8")
    interface_cmake = (IOS_ROOT.parent / "interface/CMakeLists.txt").read_text(
        encoding="utf-8"
    )
    assert 'verify-ios-static-runtime.py" "$app_path"' in build_script
    ios_rpath_boundary = """if (IOS)
    set_target_properties(${TARGET_NAME} PROPERTIES
      SKIP_BUILD_RPATH TRUE
      INSTALL_RPATH ""
    )"""
    assert ios_rpath_boundary in interface_cmake
    print("PASS iOS static runtime linkage tests")


if __name__ == "__main__":
    main()
