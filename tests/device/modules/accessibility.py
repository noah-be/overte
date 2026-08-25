#!/usr/bin/env python3
"""Record the native accessibility tree and require configured stable labels."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET

from module_support import fail, module_main, operation, write_json


def main() -> None:
    result = operation("accessibility.snapshot")
    source = result.get("source")
    if not isinstance(source, str) or not source.strip():
        fail("accessibility snapshot is empty")
    try:
        root = ET.fromstring(source)
    except ET.ParseError as error:
        fail(f"accessibility snapshot is invalid XML: {error}")
    values = set()
    for element in root.iter():
        for key in ("content-desc", "label", "name", "resource-id", "text", "value"):
            if value := element.attrib.get(key):
                values.add(value)
    required = [item.strip() for item in os.environ.get(
        "OVERTE_E2E_REQUIRED_ACCESSIBILITY", ""
    ).split(",") if item.strip()]
    if not required:
        fail("OVERTE_E2E_REQUIRED_ACCESSIBILITY must list audited stable labels")
    missing = sorted(set(required) - values)
    write_json("accessibility-audit.json", {
        "elementCount": sum(1 for _ in root.iter()), "required": required,
        "missing": missing, "observedValues": len(values),
    })
    if missing:
        fail("missing accessibility labels: " + ", ".join(missing))
    print(f"Accessibility tree exposes all {len(required)} required stable labels.")


module_main(main)
