#!/usr/bin/env python3
"""Tests for fail-closed static Qt5Compat QML plugin verification."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ios/ci/verify-static-qml-plugin-link.py"
WORKFLOW = ROOT / ".github/workflows/ios-integrated.yml"

spec = importlib.util.spec_from_file_location("static_qml_plugin_link", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def expect_failure(path: Path, markers: tuple[str, ...], stage: str) -> None:
    try:
        module.require_markers(path, markers, stage)
    except ValueError:
        return
    raise AssertionError("incomplete evidence was accepted")


with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    imports = root / "imports.cmake"
    imports.write_text("\n".join(module.IMPORT_MARKERS), encoding="utf-8")
    module.require_markers(imports, module.IMPORT_MARKERS, "imports")
    imports.write_text("\n".join(module.IMPORT_MARKERS[:-1]), encoding="utf-8")
    expect_failure(imports, module.IMPORT_MARKERS, "imports")

    link_log = root / "xcode-build.log"
    link_log.write_text(" ".join(module.LINK_MARKERS), encoding="utf-8")
    module.require_markers(link_log, module.LINK_MARKERS, "link")
    link_log.write_text(" ".join(module.LINK_MARKERS[1:]), encoding="utf-8")
    expect_failure(link_log, module.LINK_MARKERS, "link")

workflow = WORKFLOW.read_text(encoding="utf-8")
assert "verify-static-qml-plugin-link.py --imports" in workflow
assert "verify-static-qml-plugin-link.py --link-log" in workflow
print("PASS fail-closed static Qt5Compat QML plugin scan/link verification")
