#!/usr/bin/env python3
"""Reject desktop and incorrectly-contextualized packages in an iOS Conan graph."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


FORBIDDEN_PACKAGES = {
    "discord-rpc",
    "libovr",
    "openvr",
    "openxr",
    "sdl",
    "sixense",
    "steamworks",
}
BUILD_CONTEXT_ONLY = {"glslang", "scribe", "spirv-cross", "spirv-tools"}


def split_reference(reference: str) -> tuple[str, str]:
    match = re.match(r"([^/]+)/([^@#%:]+)", reference)
    if match is None:
        raise ValueError(f"invalid Conan reference: {reference}")
    return match.group(1), match.group(2)


def audit_graph(payload: dict) -> int:
    nodes = payload.get("graph", {}).get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        raise ValueError("Conan graph has no nodes")
    references = 0
    saw_ios_host = False
    for node in nodes.values():
        if not isinstance(node, dict):
            raise ValueError("Conan graph node is not an object")
        context = node.get("context")
        settings = node.get("settings", {})
        if context == "host" and settings.get("os") == "iOS":
            saw_ios_host = True
        reference = node.get("ref")
        if not reference:
            continue
        references += 1
        name, version = split_reference(reference)
        if name in FORBIDDEN_PACKAGES:
            raise ValueError(f"desktop-only package entered iOS graph: {reference}")
        if name == "glad":
            options = node.get("options", {})
            if context != "host" or settings.get("os") != "iOS":
                raise ValueError(f"glad entered the wrong iOS graph context: {reference}")
            if str(options.get("spec")) != "gl" or str(options.get("gles2_version")) != "3.2":
                raise ValueError(f"glad lacks the audited GLES 3.2 dispatch contract: {reference}")
        if name == "qt" and not version.startswith("6."):
            raise ValueError(f"non-Qt-6 package entered iOS graph: {reference}")
        if name == "quazip" and tuple(map(int, version.split("."))) < (1, 7):
            raise ValueError(f"legacy QuaZIP entered iOS graph: {reference}")
        if name in BUILD_CONTEXT_ONLY and context != "build":
            raise ValueError(f"host tool entered target context: {reference}")
        shared = node.get("options", {}).get("shared")
        if context == "host" and shared not in (None, False, "False", "false"):
            raise ValueError(f"shared target package entered iOS graph: {reference}")
    if not saw_ios_host:
        raise ValueError("Conan graph has no iOS host-context node")
    return references


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} CONAN_GRAPH_JSON", file=sys.stderr)
        return 2
    try:
        with Path(sys.argv[1]).open(encoding="utf-8") as stream:
            count = audit_graph(json.load(stream))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Verified iOS Conan graph: {count} package references")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
