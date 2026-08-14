#!/usr/bin/env python3
"""Host tests for the iOS Conan graph policy."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
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


def main() -> None:
    auditor = load_auditor()
    with tempfile.TemporaryDirectory(prefix="overte-conan-audit-") as temporary:
        root = Path(temporary)
        onetbb = root / "onetbb"
        webrtc = root / "webrtc"
        (onetbb / "lib").mkdir(parents=True)
        (webrtc / "lib").mkdir(parents=True)
        (onetbb / "lib/libtbb.a").touch()
        (webrtc / "lib/libwebrtc-audio-processing-2.a").touch()
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
                "ref": "spirv-cross/1.4.350.0",
                "context": "build",
                "settings": {"os": "Macos"},
                "options": {},
            },
        )
        assert auditor.audit_graph(valid) == 6

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
