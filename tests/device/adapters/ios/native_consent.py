"""Validate actual source-scoped production consent-dialog execution."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
from urllib.parse import urlsplit
from adapters.ios.native_integration import envelope


def enabled(target):
    value = target.get("nativeEntityConsent")
    return (isinstance(value, dict) and value == {"kind": "ios-documents", "version": 1}
            and type(value["version"]) is int)


def observation(document, process_id, command_id, operation, source, scene, now_ms=None):
    envelope(document, process_id, {"schemaVersion", "processId", "sampleEpochMs", "commandId",
        "operation", "source", "origin", "visible", "ok"}, now_ms)
    expected, actual = urlsplit(scene), urlsplit(document["origin"])
    if (document["commandId"] != command_id or document["operation"] != operation
            or operation not in {"review", "allow"} or document["source"] != source
            or document["visible"] is not True or document["ok"] is not True
            or (actual.scheme, actual.hostname, actual.port, actual.path) !=
               (expected.scheme, expected.hostname, expected.port, expected.path)
            or actual.username is not None or actual.password is not None):
        raise ValueError("native consent did not drive the exact current source-scoped dialog")
    return document
