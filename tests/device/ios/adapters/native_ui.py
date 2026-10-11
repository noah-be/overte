"""Serialize actual observed UIKit accessibility widgets into the audit tree."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import math
import time
import xml.etree.ElementTree as ET
from contracts import load_tablet_ui_contract


def validate(document, process_id, now_ms=None):
    if (not isinstance(document, dict) or set(document) != {
            "schemaVersion", "valid", "sampleEpochMs", "processId", "elements"}
            or type(document["schemaVersion"]) is not int or document["schemaVersion"] != 1
            or document["valid"] is not True
            or type(document["processId"]) is not int or document["processId"] != process_id):
        raise ValueError("native UIKit observation has invalid process or schema")
    now_ms = time.time() * 1000 if now_ms is None else now_ms
    epoch = document["sampleEpochMs"]
    if (type(epoch) not in (int, float) or not math.isfinite(epoch)
            or not -1000 <= now_ms - epoch <= 3000):
        raise ValueError("native UIKit observation is stale")
    elements = document["elements"]
    if not isinstance(elements, list) or len(elements) > 128:
        raise ValueError("native UIKit observation exceeds widget bounds")
    identifiers = set()
    vocabulary = load_tablet_ui_contract()
    allowed = {"OverteTabletOpen", "OverteTabletClose"}
    allowed |= {"OverteTabletScreen." + s for s in vocabulary["screenIds"]}
    allowed |= {"OverteTabletReady." + s for s in vocabulary["screenIds"]}
    allowed |= {"OverteTabletControl." + c for c in vocabulary["controlIds"]}
    for element in elements:
        if (not isinstance(element, dict) or set(element) != {"identifier", "visible", "enabled", "frame"}
                or type(element["visible"]) is not bool or type(element["enabled"]) is not bool):
            raise ValueError("native UIKit widget has invalid fields")
        identifier = element["identifier"]
        if (not isinstance(identifier, str) or identifier not in allowed
                or len(identifier) > 128 or identifier in identifiers
                or any(c.isspace() or ord(c) < 32 for c in identifier)):
            raise ValueError("native UIKit widget identifier is invalid or duplicated")
        identifiers.add(identifier)
        frame = element["frame"]
        if (not isinstance(frame, dict) or set(frame) != {"x", "y", "width", "height"}
                or any(type(v) not in (int, float) or not math.isfinite(v)
                       or not 0 <= v <= 10000 for v in frame.values())
                or frame["width"] <= 0 or frame["height"] <= 0):
            raise ValueError("native UIKit widget frame is invalid")
    return document


def source(document):
    # This is a representation of observed native widgets, not a fabricated
    # XCTest tree. Names, presence and enabled state all come from UIKit.
    root = ET.Element("UIKitAccessibility")
    for element in document["elements"]:
        ET.SubElement(root, "UIKitElement", name=element["identifier"],
                      visible=str(element["visible"]).lower(),
                      enabled=str(element["enabled"]).lower())
    return ET.tostring(root, encoding="unicode")
