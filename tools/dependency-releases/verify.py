#!/usr/bin/env python3
"""Download, hash and restore current dependency archives in isolated Conan caches."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from check import ROOT, POLICY, REPOSITORY, load


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(root, directory, conan):
    data = load((root / POLICY).read_text())
    directory.mkdir(parents=True, exist_ok=True)
    receipt = {"policy": data, "archives": {}}
    for family, bundle in data["bundles"].items():
        destination = directory / bundle["tag"]
        destination.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="conan-", dir=directory) as cache:
            environment = dict(os.environ, CONAN_HOME=cache)
            for name, expected in bundle["assets"].items():
                archive = destination / name
                if archive.exists() and digest(archive) != expected:
                    raise ValueError(f"Existing archive checksum mismatch: {archive}")
                if not archive.exists():
                    partial = archive.with_suffix(archive.suffix + ".partial")
                    url = f"https://github.com/{REPOSITORY}/releases/download/{bundle['tag']}/{name}"
                    subprocess.run(["curl", "--fail", "--location", "--retry", "3",
                                    "--output", str(partial), url], check=True)
                    if digest(partial) != expected:
                        raise ValueError(f"Downloaded archive checksum mismatch: {partial}")
                    partial.replace(archive)
                if digest(archive) != expected:
                    raise ValueError(f"Downloaded archive checksum mismatch: {archive}")
                if name.endswith("-conan.tgz"):
                    subprocess.run([conan, "cache", "restore", str(archive)],
                                   env=environment, check=True)
                receipt["archives"][family + "/" + name] = {
                    "sha256": expected,
                    "isolated_cache_restore": name.endswith("-conan.tgz"),
                }
    (directory / "verification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("All current archives verified; Conan archives restored in isolated caches")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--conan", default="conan")
    args = parser.parse_args()
    verify(args.root, args.directory.resolve(), args.conan)
