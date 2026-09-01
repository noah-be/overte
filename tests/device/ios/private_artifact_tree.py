#!/usr/bin/env python3
"""Canonical hash for a private, safely extracted iOS application tree.

The stream is ordered by POSIX relative path.  Directories contribute
``D NUL path NUL``.  Files contribute ``F NUL path NUL``, one byte (``X`` for
any executable bit, otherwise ``-``), then the 32 raw SHA-256 bytes of their
contents.  The root directory itself is not part of the stream.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import stat


class ArtifactTreeError(ValueError):
    """The extracted application is not an ordinary, symlink-free tree."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_sha256(root: Path, *, owner_uid: int | None = None,
                require_private: bool = False) -> str:
    """Return the canonical tree digest, optionally enforcing private ownership."""
    if not root.is_absolute():
        raise ArtifactTreeError("prebuilt WDA root is not a safe absolute directory")
    current = Path(root.anchor)
    for component in root.parts[1:]:
        current /= component
        if current.is_symlink():
            raise ArtifactTreeError(
                "prebuilt WDA path contains a symbolic-link component")
    if root.is_symlink() or not root.is_dir():
        raise ArtifactTreeError("prebuilt WDA root is not a safe absolute directory")
    root_value = root.lstat()
    if owner_uid is not None and root_value.st_uid != owner_uid:
        raise ArtifactTreeError("prebuilt WDA tree has the wrong owner")
    if require_private and root_value.st_mode & 0o077:
        raise ArtifactTreeError("prebuilt WDA tree root is not mode 0700")

    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        value = path.lstat()
        if stat.S_ISLNK(value.st_mode):
            raise ArtifactTreeError("prebuilt WDA tree contains a symbolic link")
        if owner_uid is not None and value.st_uid != owner_uid:
            raise ArtifactTreeError("prebuilt WDA tree has the wrong owner")
        if require_private and value.st_mode & 0o077:
            raise ArtifactTreeError("prebuilt WDA tree is accessible to other users")
        if stat.S_ISDIR(value.st_mode):
            digest.update(b"D\0" + relative + b"\0")
        elif stat.S_ISREG(value.st_mode):
            if value.st_nlink != 1:
                raise ArtifactTreeError("prebuilt WDA tree contains a hard-linked file")
            digest.update(b"F\0" + relative + b"\0")
            digest.update(b"X" if value.st_mode & 0o111 else b"-")
            digest.update(bytes.fromhex(file_sha256(path)))
        else:
            raise ArtifactTreeError("prebuilt WDA tree contains a special file")
    return digest.hexdigest()
