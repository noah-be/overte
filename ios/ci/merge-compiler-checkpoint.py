#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Merge a validated object checkpoint without replacing/deleting existing data."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil


def sha(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def merge(source, destination):
    source, destination = source.resolve(), destination.resolve()
    if source == destination or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("checkpoint roots must be separate")
    if not source.is_dir():
        raise ValueError("checkpoint source missing")
    files = []
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError("compiler checkpoint must not contain symlinks")
        if path.is_file():
            target = destination / path.relative_to(source)
            if target.is_symlink() or not target.resolve().is_relative_to(destination):
                raise ValueError("compiler destination containment failure")
            if target.exists() and sha(target) != sha(path):
                raise ValueError("existing compiler entry differs; both copies retained")
            files.append((path, target))
    linked = 0
    for path, target in files:
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(path, target)
        except OSError as error:
            import errno
            if error.errno != errno.EXDEV:
                raise
            with target.open("xb") as output, path.open("rb") as data:
                shutil.copyfileobj(data, output)
        linked += 1
    return {"files": len(files), "added": linked, "retained": len(files) - linked}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(merge(args.source, args.destination))
