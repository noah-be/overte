#!/usr/bin/env python3
"""Audit the stable tablet controls through one platform-neutral app session."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET

from module_support import (
    InfrastructureError,
    assert_process,
    fail,
    module_main,
    operation,
    process_identity,
    write_json,
)
from overte_session import OverteSession


def configured_identifier(name: str) -> str:
    value = os.environ.get(name, "")
    if not value or value.strip() != value or any(character.isspace() for character in value):
        raise InfrastructureError(f"{name} must contain one non-sensitive stable identifier")
    return value


def snapshot_values() -> tuple[int, set[str]]:
    result = operation("accessibility.snapshot")
    source = result.get("source")
    if not isinstance(source, str) or not source.strip():
        raise InfrastructureError("accessibility snapshot is empty")
    try:
        root = ET.fromstring(source)
    except ET.ParseError as error:
        raise InfrastructureError("accessibility snapshot is invalid XML") from error
    values = set()
    count = 0
    for element in root.iter():
        count += 1
        for key in ("content-desc", "label", "name", "resource-id", "text", "value"):
            if value := element.attrib.get(key):
                values.add(value)
    return count, values


def main() -> None:
    open_identifier = configured_identifier("OVERTE_E2E_TABLET_OPEN_ACCESSIBILITY_ID")
    close_identifier = configured_identifier("OVERTE_E2E_TABLET_CLOSE_ACCESSIBILITY_ID")
    if open_identifier == close_identifier:
        raise InfrastructureError("tablet open and close accessibility identifiers must differ")

    operation("app.launch")
    session = OverteSession()
    session.ensure_controlled_scene()
    identity = process_identity()

    session.set_tablet(False)
    closed_count, closed_values = snapshot_values()
    closed_missing = [] if open_identifier in closed_values else [open_identifier]
    assert_process(identity, "closed-tablet accessibility snapshot")

    session.set_tablet(True)
    opened_count, opened_values = snapshot_values()
    opened_missing = [] if close_identifier in opened_values else [close_identifier]
    assert_process(identity, "open-tablet accessibility snapshot")

    session.set_tablet(False)
    assert_process(identity, "accessibility audit cleanup")
    missing = closed_missing + opened_missing
    write_json("accessibility-audit.json", {
        "closedElementCount": closed_count,
        "closedObservedValues": len(closed_values),
        "missing": missing,
        "openElementCount": opened_count,
        "openObservedValues": len(opened_values),
        "required": [open_identifier, close_identifier],
    })
    if missing:
        fail("missing accessibility identifiers: " + ", ".join(missing))
    print("Accessibility tree exposes the audited tablet controls in one app session.")


module_main(main)
