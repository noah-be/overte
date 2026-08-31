#!/usr/bin/env python3
"""Fail closed when required static iOS QML plugins are not scanned or linked."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
from pathlib import Path


MAX_INPUT_BYTES = 512 * 1024 * 1024

IMPORT_MARKERS = (
    "CLASSNAME;QtGraphicalEffectsPlugin;",
    "LINKTARGET;Qt6::qtgraphicaleffectsplugin;",
    "CLASSNAME;QtGraphicalEffectsPrivatePlugin;",
    "LINKTARGET;Qt6::qtgraphicaleffectsprivate;",
)

LINK_MARKERS = (
    "/qml/Qt5Compat/GraphicalEffects/libqtgraphicaleffectsplugin.a",
    "/qml/Qt5Compat/GraphicalEffects/private/libqtgraphicaleffectsprivateplugin.a",
    "qtgraphicaleffectsplugin_init.cpp.o",
    "qtgraphicaleffectsprivate_init.cpp.o",
)


def read_bounded(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"input is not a regular file: {path}")
    size = path.stat().st_size
    if size < 1 or size > MAX_INPUT_BYTES:
        raise ValueError(f"input size is outside the accepted range: {path} ({size} bytes)")
    return path.read_text(encoding="utf-8", errors="replace")


def require_markers(path: Path, markers: tuple[str, ...], stage: str) -> None:
    source = read_bounded(path)
    missing = [marker for marker in markers if marker not in source]
    if missing:
        raise ValueError(f"{stage} is missing static QML plugin evidence: {', '.join(missing)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--imports", type=Path)
    parser.add_argument("--link-log", type=Path)
    args = parser.parse_args()
    if (args.imports is None) == (args.link_log is None):
        parser.error("provide exactly one of --imports or --link-log")

    try:
        if args.imports is not None:
            require_markers(args.imports, IMPORT_MARKERS, "QML import scan")
            print("PASS Qt5Compat GraphicalEffects public/private QML import scan")
        else:
            require_markers(args.link_log, LINK_MARKERS, "full-client link")
            print("PASS Qt5Compat GraphicalEffects public/private static link")
    except ValueError as error:
        parser.exit(1, f"error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
