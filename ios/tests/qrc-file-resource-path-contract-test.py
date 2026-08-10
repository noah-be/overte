#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "libraries/networking/src/FileResourceRequest.cpp").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


require('filename = ":" + _url.path();' in SOURCE,
        "qrc URLs must map to a single-colon QFile resource path")
require('filename = ":/" + _url.path();' not in SOURCE,
        "qrc URLs must not receive a duplicate slash")
require("QUrl::path() already starts with '/'" in SOURCE and "invalid QFile resource path ://foo" in SOURCE,
        "the path invariant and failure mode must remain documented")

fixtures = {
    "qrc:///serverless/tutorial.json": ":/serverless/tutorial.json",
    "qrc:/qml/Root.qml": ":/qml/Root.qml",
}
for url, expected in fixtures.items():
    actual = ":" + urlparse(url).path
    require(actual == expected, f"unexpected qrc mapping: {url} -> {actual}")
    require(not actual.startswith("://"), f"invalid duplicated-slash resource path: {actual}")

print("qrc FileResourceRequest path contract valid: embedded assets retain :/ paths")
