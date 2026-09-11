#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import importlib.util
from pathlib import Path
import tempfile

spec = importlib.util.spec_from_file_location("merge", Path(__file__).resolve().parents[1] / "ci/merge-compiler-checkpoint.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    source, target = root / "source", root / "target"
    (source / "a").mkdir(parents=True)
    (source / "a/object").write_bytes(b"compiled-object")
    target.mkdir()
    (target / "existing").write_bytes(b"retain")
    assert module.merge(source, target) == {"files": 1, "added": 1, "retained": 0}
    assert (target / "a/object").read_bytes() == b"compiled-object"
    assert (target / "existing").read_bytes() == b"retain"
    assert module.merge(source, target)["added"] == 0
    # Atomic cached files are never rewritten, even on a content-key conflict.
    (source / "conflict").write_bytes(b"incoming")
    (target / "conflict").write_bytes(b"existing")
    try:
        module.merge(source, target)
        raise AssertionError("conflict overwritten")
    except ValueError:
        pass
    assert (target / "conflict").read_bytes() == b"existing"
    assert (source / "conflict").read_bytes() == b"incoming"
    (source / "conflict").unlink()
    (source / "escape").symlink_to(root.parent)
    try:
        module.merge(source, target)
        raise AssertionError("symlink accepted")
    except ValueError:
        pass
print("PASS compiler checkpoint merge, unchanged entries, conflict preservation, symlink rejection")
