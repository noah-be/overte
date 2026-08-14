#!/usr/bin/env python3
"""Host tests for the iOS Conan graph policy."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import subprocess
import tempfile
from pathlib import Path


IOS_ROOT = Path(__file__).resolve().parents[1]


def load_auditor():
    path = IOS_ROOT / "tools/audit-conan-graph.py"
    specification = importlib.util.spec_from_file_location("audit_conan_graph", path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def graph(*nodes: dict) -> dict:
    return {"graph": {"nodes": {str(index): node for index, node in enumerate(nodes)}}}


def expect_rejected(auditor, payload: dict, expected: str) -> None:
    try:
        auditor.audit_graph(payload)
    except ValueError as error:
        assert expected in str(error), error
    else:
        raise AssertionError(f"graph was accepted; expected {expected}")


def configure_webrtc_boundary(root: Path, abseil: Path, *, expect_success: bool) -> None:
    package_config = root / "cmake-package"
    package_config.mkdir(exist_ok=True)
    (package_config / "webrtc-audio-processing-config.cmake").write_text(
        "add_library(webrtc-audio-processing::webrtc-audio-processing INTERFACE IMPORTED)\n"
        f'set(abseil_PACKAGE_FOLDER_RELEASE "{abseil.as_posix()}")\n',
        encoding="utf-8",
    )
    source = root / ("cmake-source-pass" if expect_success else "cmake-source-fail")
    source.mkdir()
    (source / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.20)\n"
        "project(overte_webrtc_abseil_boundary LANGUAGES CXX)\n"
        "set(IOS TRUE)\n"
        "set(TARGET_NAME consumer)\n"
        "file(WRITE \"${CMAKE_BINARY_DIR}/consumer.cpp\" \"int overte_consumer;\\n\")\n"
        "add_library(consumer STATIC \"${CMAKE_BINARY_DIR}/consumer.cpp\")\n"
        f'list(PREPEND CMAKE_PREFIX_PATH "{package_config.as_posix()}")\n'
        f'include("{(IOS_ROOT.parent / "cmake/macros/TargetWebRTC.cmake").as_posix()}")\n'
        "target_webrtc()\n"
        "get_target_property(includes consumer INTERFACE_INCLUDE_DIRECTORIES)\n"
        'file(WRITE "${CMAKE_BINARY_DIR}/includes.txt" "${includes}")\n',
        encoding="utf-8",
    )
    build = root / ("cmake-build-pass" if expect_success else "cmake-build-fail")
    completed = subprocess.run(
        ["cmake", "-S", str(source), "-B", str(build)],
        check=False,
        capture_output=True,
        text=True,
    )
    if expect_success:
        assert completed.returncode == 0, completed.stderr
        includes = (build / "includes.txt").read_text(encoding="utf-8")
        assert str(abseil / "include") in includes, includes
    else:
        assert completed.returncode != 0
        assert "lacks absl/base/nullability.h" in completed.stderr


def main() -> None:
    auditor = load_auditor()
    with tempfile.TemporaryDirectory(prefix="overte-conan-audit-") as temporary:
        root = Path(temporary)
        onetbb = root / "onetbb"
        webrtc = root / "webrtc"
        abseil = root / "abseil"
        (onetbb / "lib").mkdir(parents=True)
        (webrtc / "lib").mkdir(parents=True)
        (onetbb / "lib/libtbb.a").touch()
        (webrtc / "lib/libwebrtc-audio-processing-2.a").touch()
        (abseil / "include/absl/base").mkdir(parents=True)
        (abseil / "include/absl/base/nullability.h").touch()
        valid = graph(
            {
                "ref": "overte-ios-dependencies/0.1",
                "context": "host",
                "settings": {"os": "iOS"},
                "options": {},
            },
            {
                "ref": "openssl/3.5.7",
                "context": "host",
                "settings": {"os": "iOS"},
                "options": {"shared": False},
            },
            {
                "ref": "glad/0.1.36@overte/experimental",
                "context": "host",
                "settings": {"os": "iOS"},
                "options": {"shared": False, "spec": "gl", "gles2_version": "3.2"},
            },
            {
                "ref": "onetbb/2021.10.0@overte/ios-static",
                "context": "host",
                "settings": {"os": "iOS"},
                "options": {"shared": False},
                "package_folder": str(onetbb),
            },
            {
                "ref": "webrtc-audio-processing/2.1@overte/ios-static",
                "context": "host",
                "settings": {"os": "iOS"},
                "options": {"shared": False},
                "package_folder": str(webrtc),
            },
            {
                "ref": "abseil/20250127.0",
                "context": "host",
                "settings": {"os": "iOS"},
                "options": {"shared": False},
                "package_folder": str(abseil),
            },
            {
                "ref": "spirv-cross/1.4.350.0",
                "context": "build",
                "settings": {"os": "Macos"},
                "options": {},
            },
        )
        assert auditor.audit_graph(valid) == 7

        (abseil / "include/absl/base/nullability.h").unlink()
        expect_rejected(auditor, valid, "required public header")
        (abseil / "include/absl/base/nullability.h").touch()
        configure_webrtc_boundary(root, abseil, expect_success=True)
        (abseil / "include/absl/base/nullability.h").unlink()
        configure_webrtc_boundary(root, abseil, expect_success=False)
        (abseil / "include/absl/base/nullability.h").touch()

        expect_rejected(
            auditor,
            graph(
                {
                    "ref": "webrtc-audio-processing/2.1@overte/ios-static",
                    "context": "host",
                    "settings": {"os": "iOS"},
                    "options": {"shared": False},
                    "package_folder": str(webrtc),
                }
            ),
            "lacks its Abseil package",
        )

        shared_recipe = root / "shared-recipe"
        (shared_recipe / "lib").mkdir(parents=True)
        (shared_recipe / "lib/libtbb.12.dylib").touch()
        expect_rejected(
            auditor,
            graph(
                {
                    "ref": "onetbb/2021.10.0@overte/ios-static",
                    "context": "host",
                    "settings": {"os": "iOS"},
                    "options": {"shared": False},
                    "package_folder": str(shared_recipe),
                }
            ),
            "lacks libtbb.a",
        )

        expect_rejected(
            auditor,
            graph(
                {
                    "ref": "webrtc-audio-processing/2.1@overte/stable",
                    "context": "host",
                    "settings": {"os": "iOS"},
                    "options": {},
                    "package_folder": str(webrtc),
                }
            ),
            "audited recipe",
        )

    expect_rejected(
        auditor,
        graph({"ref": "qt/5.15.19", "context": "host", "settings": {"os": "iOS"}}),
        "non-Qt-6",
    )
    expect_rejected(
        auditor,
        graph({"ref": "steamworks/1.0", "context": "host", "settings": {"os": "iOS"}}),
        "desktop-only",
    )
    expect_rejected(
        auditor,
        graph({"ref": "scribe/2019.02", "context": "host", "settings": {"os": "iOS"}}),
        "target context",
    )
    expect_rejected(
        auditor,
        graph(
            {
                "ref": "openssl/3.5.7",
                "context": "host",
                "settings": {"os": "iOS"},
                "options": {"shared": True},
            }
        ),
        "shared target",
    )
    expect_rejected(
        auditor,
        graph(
            {
                "ref": "glad/0.1.36@overte/experimental",
                "context": "host",
                "settings": {"os": "iOS"},
                "options": {"shared": False, "spec": "gl", "gles2_version": "None"},
            }
        ),
        "GLES 3.2",
    )

    conanfile = (IOS_ROOT / "conanfile.py").read_text(encoding="utf-8")
    build_script = (IOS_ROOT / "build-ios.sh").read_text(encoding="utf-8")
    assert "onetbb/2021.10.0@overte/ios-static" in conanfile
    assert "webrtc-audio-processing/2.1@overte/ios-static" in conanfile
    assert 'conan export "$script_dir/conan/recipes/onetbb"' in build_script
    assert 'conan export "$script_dir/conan/recipes/webrtc-audio-processing"' in build_script
    for relative in (
        "conan/recipes/onetbb/conanfile.py",
        "conan/recipes/webrtc-audio-processing/conanfile.py",
    ):
        recipe = (IOS_ROOT / relative).read_text(encoding="utf-8")
        assert '"shared": False' in recipe
        assert "ios-static" not in recipe
    webrtc_recipe = (
        IOS_ROOT / "conan/recipes/webrtc-audio-processing/conanfile.py"
    ).read_text(encoding="utf-8")
    for abseil_component in (
        "abseil::absl_base",
        "abseil::absl_flags",
        "abseil::absl_strings",
        "abseil::absl_numeric",
        "abseil::absl_synchronization",
        "abseil::absl_bad_optional_access",
    ):
        assert abseil_component in webrtc_recipe
    target_webrtc = (IOS_ROOT.parent / "cmake/macros/TargetWebRTC.cmake").read_text(
        encoding="utf-8"
    )
    assert "if (IOS)" in target_webrtc
    assert "abseil_PACKAGE_FOLDER_RELEASE" in target_webrtc
    assert "absl/base/nullability.h" in target_webrtc
    assert "target_include_directories" in target_webrtc
    for workflow_name in ("ios-integrated.yml", "ios-world-runtime.yml"):
        workflow = (IOS_ROOT.parent / ".github/workflows" / workflow_name).read_text(
            encoding="utf-8"
        )
        for recipe_input in (
            "ios/conan/recipes/onetbb/conanfile.py",
            "ios/conan/recipes/onetbb/conandata.yml",
            "ios/conan/recipes/webrtc-audio-processing/conanfile.py",
            "ios/conan/recipes/webrtc-audio-processing/conandata.yml",
        ):
            assert recipe_input in workflow, (workflow_name, recipe_input)
    print("PASS iOS Conan graph audit tests")


if __name__ == "__main__":
    main()
