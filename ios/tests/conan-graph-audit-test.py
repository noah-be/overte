#!/usr/bin/env python3
"""Host tests for the iOS Conan graph policy."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
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
            "ref": "spirv-cross/1.4.350.0",
            "context": "build",
            "settings": {"os": "Macos"},
            "options": {},
        },
    )
    assert auditor.audit_graph(valid) == 4

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
    print("PASS iOS Conan graph audit tests")


if __name__ == "__main__":
    main()
