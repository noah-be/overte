#!/usr/bin/env python3
"""Host tests for privacy-minimal iPad entity evidence preparation."""

import importlib.util
import json
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "ios/tools/prepare-entity-evidence.py"
FIXTURES = ROOT / "ios/tests/fixtures/entity-gates"
spec = importlib.util.spec_from_file_location("entity_evidence", TOOL)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
metadata = {"sourceRevision": "a" * 40, "bundleSha256": "b" * 64, "formFactor": "ipad",
            "osVersion": "18.0", "deviceModel": "iPad fixture"}
with tempfile.TemporaryDirectory(prefix="overte-entity-evidence-") as temporary:
    root = Path(temporary)
    raw = root / "exported.log"
    raw.write_text("private token=do-not-copy\n" + (FIXTURES / "success.log").read_text(), encoding="utf-8")
    output = root / "handoff"
    archive = module.prepare(raw, output, metadata)
    handoff = json.loads((output / "handoff.json").read_text())
    assert handoff["accepted"] is True and handoff["gateCount"] == 6
    assert handoff["containsRawDeviceLog"] is False
    assert "do-not-copy" not in (output / "entity-gates.log").read_text()
    with zipfile.ZipFile(archive) as bundle:
        assert set(bundle.namelist()) == {"entity-gates.log", "entity-gates.json", "handoff.json"}
    try:
        module.prepare(raw, output, metadata)
    except ValueError as error:
        assert "already exists" in str(error)
    else:
        raise AssertionError("existing evidence was overwritten")
print("PASS offline iPad entity evidence handoff tests")
