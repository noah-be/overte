"""Verify immutable General release bytes before invoking a platform consumer."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import hashlib
import os
from pathlib import Path, PurePosixPath


def verify_release(root: Path, manifest_sha256: str, entrypoint: str, *, executable: bool = True) -> Path:
    root = root.absolute()
    if any(p.is_symlink() for p in (root, *root.parents)) or not root.is_dir():
        raise ValueError("SHARED_CONTRACT_ROOT")
    manifest = root / "SHA256SUMS"
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("SHARED_MANIFEST_MISSING")
    with manifest.open("rb") as stream:
        raw = stream.read(16385)
    if len(raw) > 16384 or hashlib.sha256(raw).hexdigest() != manifest_sha256:
        raise ValueError("SHARED_MANIFEST_PIN")
    seen = set()
    for line in raw.decode("ascii").splitlines():
        expected, name = line.split("  ", 1)
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or name in seen:
            raise ValueError("SHARED_MANIFEST_PATH")
        seen.add(name)
        file = root.joinpath(*relative.parts)
        if any(p.is_symlink() for p in (file, *file.parents)) or not file.is_file():
            raise ValueError("SHARED_SOURCE_MISSING")
        with file.open("rb") as stream:
            contents = stream.read(1048577)
        if len(contents) > 1048576 or hashlib.sha256(contents).hexdigest() != expected:
            raise ValueError("SHARED_SOURCE_DIGEST")
    adapter = root / entrypoint
    if "./" + entrypoint not in seen or (executable and not os.access(adapter, os.X_OK)):
        raise ValueError("SHARED_ADAPTER_NOT_EXECUTABLE")
    return adapter
