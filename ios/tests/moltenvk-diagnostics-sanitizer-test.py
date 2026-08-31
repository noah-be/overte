#!/usr/bin/env python3
"""Exercise bounded, secret-safe MoltenVK shader diagnostics."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import json
from pathlib import Path
import struct
import tempfile


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "ios/tools/prepare-moltenvk-diagnostics.py"
spec = importlib.util.spec_from_file_location("moltenvk_diagnostics", HELPER)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    source = root / "raw"
    destination = root / "safe"
    source.mkdir()
    spirv = struct.pack("<5I", module.SPIRV_MAGIC, 0x00010000, 0, 1, 0)
    (source / "shader-vs-0000000000001234.spv").write_bytes(spirv)
    (source / "shader-vs-0000000000001234.metal").write_text(
        "token=do-not-upload\n#line 1 /Users/runner/work/source.metal\nvertex main0() {}\n",
        encoding="utf-8",
    )
    (source / "pipeline-0000000000005678.txt").write_text(
        "VS: 0000000000001234\n", encoding="utf-8"
    )
    (source / "unrelated.secret").write_text("private", encoding="utf-8")

    assert module.prepare(source, destination) == 3
    assert sorted(path.name for path in destination.iterdir()) == [
        "manifest.json",
        "pipeline-0000000000005678.txt",
        "shader-vs-0000000000001234.metal",
        "shader-vs-0000000000001234.spv",
    ]
    assert (destination / "shader-vs-0000000000001234.spv").read_bytes() == spirv
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    spirv_metadata = next(item for item in manifest["files"] if item["kind"] == "spv")
    assert spirv_metadata["overteDiagnosticFingerprint"] == module.diagnostic_fingerprint(spirv)
    assert len(spirv_metadata["sha256"]) == 64
    metal = (destination / "shader-vs-0000000000001234.metal").read_text(encoding="utf-8")
    assert "do-not-upload" not in metal and "[REDACTED]" in metal
    assert "/Users/runner" not in metal and "/Users/[REDACTED]" in metal
    assert manifest["rejected"] == [{"count": 1, "reason": "unexpected-name"}]
    assert all((path.stat().st_mode & 0o777) == 0o600 for path in destination.iterdir())

    invalid_source = root / "invalid"
    invalid_source.mkdir()
    (invalid_source / "shader-fs-0000000000009999.spv").write_bytes(b"not spirv")
    try:
        module.prepare(invalid_source, root / "invalid-safe")
    except ValueError as error:
        assert "SPIR-V" in str(error)
    else:
        raise AssertionError("invalid SPIR-V was accepted")

    private_spirv_source = root / "private-spirv"
    private_spirv_source.mkdir()
    private_spirv = spirv + b"token=must-not-upload"
    private_spirv += b"\0" * (-len(private_spirv) % 4)
    (private_spirv_source / "shader-fs-0000000000006666.spv").write_bytes(
        private_spirv
    )
    try:
        module.prepare(private_spirv_source, root / "private-spirv-safe")
    except ValueError as error:
        assert "private text" in str(error)
    else:
        raise AssertionError("SPIR-V containing private text was accepted")

    linked_source = root / "linked"
    linked_source.mkdir()
    linked_target = root / "linked-target.spv"
    linked_target.write_bytes(spirv)
    (linked_source / "shader-fs-0000000000008888.spv").symlink_to(linked_target)
    try:
        module.prepare(linked_source, root / "linked-safe")
    except ValueError as error:
        assert "non-regular" in str(error)
    else:
        raise AssertionError("linked SPIR-V was accepted")

    oversized_source = root / "oversized"
    oversized_source.mkdir()
    oversized = oversized_source / "shader-fs-0000000000007777.spv"
    with oversized.open("wb") as output:
        output.truncate(module.MAX_FILE_BYTES + 1)
    try:
        module.prepare(oversized_source, root / "oversized-safe")
    except ValueError as error:
        assert "per-file" in str(error)
    else:
        raise AssertionError("oversized SPIR-V was accepted")

    empty_source = root / "empty"
    empty_source.mkdir()
    (empty_source / "credential.txt").write_text("token=private", encoding="utf-8")
    empty_destination = root / "empty-safe"
    assert module.prepare(empty_source, empty_destination) == 0
    assert not empty_destination.exists()

print("PASS bounded and secret-safe MoltenVK shader diagnostics")
