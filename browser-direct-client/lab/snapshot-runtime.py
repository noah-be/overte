#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Capture stable own native runtime bytes before live integration tests."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

from manage import REPO, ROOT, owns_process, read_state

BUILD = REPO / "build/browser-direct/native"
ACTIVE = ROOT / "runtime/native-runtime.json"


def source_fingerprint() -> tuple[dict[str, str], str]:
    names = subprocess.check_output([
        "git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--",
        "*.cpp", "*.h", "CMakeLists.txt", "*.cmake", "conanfile.py"
    ], cwd=REPO).decode().split("\0")
    sources = {name: hashlib.sha256((REPO / name).read_bytes()).hexdigest()
               for name in sorted(set(names)) if name and (REPO / name).is_file()}
    return sources, hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()


def runtime_inputs() -> dict[str, Path]:
    """Match capture's copied files, following the same runtime symlinks."""
    inputs = {}
    for target in ("domain-server", "assignment-client"):
        binary = BUILD / target / target
        if not binary.is_file():
            raise RuntimeError("Build the owned domain and assignments before hashing a runtime")
        inputs[f"native/{target}/{target}"] = binary
    for path in BUILD.rglob("*.so*"):
        if path.is_file():
            inputs[f"native/{path.relative_to(BUILD)}"] = path

    def add_tree(directory: Path, prefix: str, *, optional: bool = False) -> None:
        if not directory.is_dir():
            if optional:
                return
            raise RuntimeError("An owned runtime resource directory is missing")
        # copytree follows directory and file symlinks; hashing must do so too.
        for current, _, files in os.walk(directory, followlinks=True):
            current = Path(current)
            for name in files:
                path = current / name
                if not path.is_file():
                    raise RuntimeError("An owned runtime resource file is unavailable")
                inputs[f"{prefix}/{path.relative_to(directory)}"] = path

    add_tree(BUILD / "domain-server/resources", "native/domain-server/resources", optional=True)
    add_tree(REPO / "domain-server/resources", "domain-resources")
    add_tree(REPO / "build/browser-direct/deps/prefix", "datachannel-prefix")
    return inputs


def candidate() -> dict:
    """Hash built bytes without selecting a snapshot or touching live services."""
    with (REPO / "build/browser-direct/native-build.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        sources, source_hash = source_fingerprint()
        hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest()
                  for name, path in sorted(runtime_inputs().items())}
        after_sources, after_hash = source_fingerprint()
        if sources != after_sources or source_hash != after_hash:
            raise RuntimeError("Native sources changed while the runtime candidate was hashed")
        runtime_hash = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
        active = json.loads(ACTIVE.read_text()) if ACTIVE.is_file() else None
        return {
            "schema": 1, "capturedUTC": datetime.now(timezone.utc).isoformat(),
            "runtimeSHA256": runtime_hash, "runtimeFiles": hashes,
            "sourceFingerprintAtCapture": source_hash, "sourceFilesAtCapture": sources,
            "sourceCaptureIsCompileAttestation": False,
            "matchesSelectedRuntime": bool(active and active["runtimeSHA256"] == runtime_hash),
            "selectedRuntime": active, "snapshotSelectedByThisOperation": False,
            "note": "This read-only candidate hashes built bytes. A separate completed build/test record binds the final source. Existing immutable snapshot manifests are preserved.",
        }


def capture() -> dict:
    if any(owns_process(entry) for entry in read_state().values()):
        raise RuntimeError("Stop the owned domain before selecting a different runtime snapshot")
    with (REPO / "build/browser-direct/native-build.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        slots = ROOT / "runtime-snapshots"
        slots.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = slots / f".preparing-{uuid.uuid4()}"
        native = temporary / "native"
        native.mkdir(parents=True)
        inputs = []
        for target in ("domain-server", "assignment-client"):
            binary = BUILD / target / target
            if not binary.is_file():
                raise RuntimeError("Build the owned domain and assignments before taking a snapshot")
            inputs.append(binary)
        inputs.extend(path for path in BUILD.rglob("*.so*") if path.is_file())
        for source in sorted(set(inputs)):
            destination = native / source.relative_to(BUILD)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        resources = BUILD / "domain-server/resources"
        if resources.is_dir():
            shutil.copytree(resources, native / "domain-server/resources", dirs_exist_ok=True)
        shutil.copytree(REPO / "domain-server/resources", temporary / "domain-resources")
        shutil.copytree(REPO / "build/browser-direct/deps/prefix", temporary / "datachannel-prefix")
        hashes = {}
        for path in sorted(temporary.rglob("*")):
            if path.is_file():
                hashes[str(path.relative_to(temporary))] = hashlib.sha256(path.read_bytes()).hexdigest()
        runtime_hash = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
        sources, source_hash = source_fingerprint()
        manifest = {
            "schema": 1, "capturedUTC": datetime.now(timezone.utc).isoformat(),
            "runtimeSHA256": runtime_hash, "runtimeFiles": hashes,
            "gitHEAD": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
            "sourceFingerprintAtCapture": source_hash,
            "sourceFilesAtCapture": sources,
            "sourceCaptureIsCompileAttestation": False,
            "note": "Runtime byte hashes identify tested binaries; later source edits require a new build/test/snapshot.",
        }
        (temporary / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        slot = slots / runtime_hash
        if slot.exists():
            shutil.rmtree(temporary)
        else:
            temporary.rename(slot)
        pointer = {"snapshot": str(slot), "runtimeSHA256": runtime_hash,
                   "manifestSHA256": hashlib.sha256((slot / "manifest.json").read_bytes()).hexdigest()}
        ACTIVE.write_text(json.dumps(pointer, indent=2) + "\n")
        ACTIVE.chmod(0o600)
        return pointer


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("capture", "candidate"), nargs="?", default="capture")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output and args.operation != "candidate":
        parser.error("Only a read-only candidate may use an evidence output")
    if args.output and (not args.output.resolve().is_relative_to((ROOT / "runtime").resolve()) or
                        args.output.exists()):
        parser.error("Candidate evidence must be a new file in this worktree's runtime directory")
    record = candidate() if args.operation == "candidate" else capture()
    if args.output:
        args.output.write_text(json.dumps(record, indent=2) + "\n")
        args.output.chmod(0o600)
    print(json.dumps({key: record[key] for key in
                      ("runtimeSHA256", "matchesSelectedRuntime", "snapshotSelectedByThisOperation")
                      if key in record} if args.operation == "candidate" else record))
