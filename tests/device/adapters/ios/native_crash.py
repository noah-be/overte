"""Require an actual process-bound native abort firing receipt."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
from adapters.ios.native_integration import envelope


def enabled(target):
    value = target.get("nativeCrash")
    return (isinstance(value, dict) and value == {"kind": "ios-documents", "version": 1}
            and type(value["version"]) is int)


def observation(document, process_id, command_id, now_ms=None):
    envelope(document, process_id, {"schemaVersion", "processId", "sampleEpochMs",
                                  "commandId", "phase", "cause"}, now_ms)
    if (document["commandId"] != command_id or document["phase"] != "firing"
            or document["cause"] != "SIGABRT"):
        raise ValueError("native crash did not reach the actual owned abort firing boundary")
    return document
