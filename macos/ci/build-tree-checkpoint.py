#!/usr/bin/env python3
"""Make a restored Ninja build tree safe to reuse after a fresh checkout.

GitHub's checkout gives source files new mtimes while actions/cache preserves the
mtimes of Ninja outputs.  Ninja then considers every source newer than its
object, even when the content is unchanged.  A checkpoint records the source
commit inside the cached build tree.  On restore, tracked files from that commit
are assigned a stable old mtime and only paths changed since that commit (plus
local working-tree changes) are made newer than the cached outputs.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


SCHEMA = 2
SUPPORTED_SCHEMAS = {1, SCHEMA}
METADATA_NAME = ".overte-ninja-checkpoint.json"
# Old enough to precede every supported macOS/Xcode build artifact, while still
# being representable by filesystems used by GitHub-hosted runners.
BASELINE_NS = 946_684_800 * 1_000_000_000  # 2000-01-01T00:00:00Z
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class CheckpointError(RuntimeError):
    pass


def git(repository: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise CheckpointError(f"git {' '.join(arguments[:2])} failed: {detail}")
    return result.stdout


def nul_paths(data: bytes) -> set[str]:
    return {
        item.decode("utf-8", "surrogateescape")
        for item in data.split(b"\0")
        if item
    }


def tracked_blobs(repository: Path) -> dict[str, str]:
    """Return the index blob id for every stage-zero tracked path."""
    result: dict[str, str] = {}
    for entry in git(repository, "ls-files", "--stage", "-z").split(b"\0"):
        if not entry:
            continue
        try:
            metadata, raw_path = entry.split(b"\t", 1)
            _mode, object_id, stage = metadata.split(b" ", 2)
        except ValueError as error:
            raise CheckpointError("git returned malformed tracked-file metadata") from error
        if stage != b"0":
            continue
        path = raw_path.decode("utf-8", "surrogateescape")
        blob = object_id.decode("ascii", "strict")
        if not COMMIT_RE.fullmatch(blob):
            raise CheckpointError("git returned an invalid tracked-file object id")
        result[path] = blob
    return result


def commit_available(repository: Path, commit: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(repository), "cat-file", "-e", f"{commit}^{{commit}}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def fetch_checkpoint_commit(repository: Path, commit: str) -> None:
    """Fetch one legacy checkpoint commit omitted by a shallow checkout."""
    if commit_available(repository, commit):
        return
    result = subprocess.run(
        [
            "git", "-C", str(repository), "fetch", "--no-tags", "--depth=1",
            "origin", commit,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode or not commit_available(repository, commit):
        # Do not echo a remote URL or arbitrary Git configuration into CI logs.
        raise CheckpointError(
            "checkpoint commit is absent from the shallow checkout and could not be fetched"
        )
    print(f"macOS Ninja checkpoint fetched legacy commit {commit}", flush=True)


def metadata_path(build_dir: Path) -> Path:
    return build_dir / METADATA_NAME


def record(repository: Path, build_dir: Path) -> None:
    repository = repository.resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    commit = git(repository, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    if not COMMIT_RE.fullmatch(commit):
        raise CheckpointError("HEAD did not resolve to a full commit id")
    payload = {
        "schema": SCHEMA,
        "commit": commit,
        "baseline_ns": BASELINE_NS,
        "tracked_blobs": tracked_blobs(repository),
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    destination = metadata_path(build_dir)
    fd, temporary = tempfile.mkstemp(prefix=f".{METADATA_NAME}.", dir=build_dir)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(payload, output, sort_keys=True, separators=(",", ":"))
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f"macOS Ninja checkpoint recorded at commit {commit}", flush=True)


def load_metadata(build_dir: Path) -> dict[str, object] | None:
    source = metadata_path(build_dir)
    if not source.exists():
        return None
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CheckpointError(f"invalid checkpoint metadata: {error}") from error
    if not isinstance(payload, dict):
        raise CheckpointError("checkpoint metadata is not an object")
    schema = payload.get("schema")
    if schema not in SUPPORTED_SCHEMAS:
        raise CheckpointError("unsupported checkpoint metadata schema")
    commit = payload.get("commit")
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise CheckpointError("checkpoint contains an invalid commit id")
    if payload.get("baseline_ns") != BASELINE_NS:
        raise CheckpointError("checkpoint contains an invalid source baseline")
    if schema == SCHEMA:
        blobs = payload.get("tracked_blobs")
        if not isinstance(blobs, dict):
            raise CheckpointError("checkpoint contains no tracked-file manifest")
        for path, object_id in blobs.items():
            if (
                not isinstance(path, str)
                or not path
                or "\0" in path
                or not isinstance(object_id, str)
                or not COMMIT_RE.fullmatch(object_id)
            ):
                raise CheckpointError("checkpoint contains invalid tracked-file metadata")
    return payload


def restore(repository: Path, build_dir: Path) -> None:
    repository = repository.resolve()
    payload = load_metadata(build_dir)
    if payload is None:
        print(
            "macOS Ninja checkpoint has no metadata (legacy cache); "
            "leaving source timestamps unchanged",
            flush=True,
        )
        return

    checkpoint = str(payload["commit"])
    head = git(repository, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()

    current_blobs = tracked_blobs(repository)
    tracked = set(current_blobs)
    if payload["schema"] == SCHEMA:
        checkpoint_blobs = payload["tracked_blobs"]
        assert isinstance(checkpoint_blobs, dict)
        changed = {
            relative
            for relative, object_id in current_blobs.items()
            if checkpoint_blobs.get(relative) != object_id
        }
    else:
        # Schema 1 predates the manifest.  Its commit may be absent from the
        # default depth-one Actions checkout, so fetch only that exact validated
        # object instead of downloading the full repository history.
        fetch_checkpoint_commit(repository, checkpoint)
        changed = nul_paths(
            git(
                repository,
                "diff",
                "--name-only",
                "-z",
                "--diff-filter=ACMRTUXB",
                checkpoint,
                head,
                "--",
            )
        )
    # Do not make a developer's staged or unstaged edit look older than an
    # object restored from CI.  These sets are empty on a clean Actions checkout.
    changed |= nul_paths(git(repository, "diff", "--name-only", "-z", "HEAD", "--"))
    changed |= nul_paths(
        git(repository, "diff", "--cached", "--name-only", "-z", "HEAD", "--")
    )

    normalized = 0
    marked_changed = 0
    now_ns = time.time_ns()
    for relative in sorted(tracked):
        path = repository / relative
        # Gitlinks and missing/deleted files do not have a file timestamp Ninja
        # can consume.  Do not follow symlinks outside the checkout.
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_dir():
            continue
        timestamp = now_ns if relative in changed else BASELINE_NS
        os.utime(path, ns=(timestamp, timestamp), follow_symlinks=False)
        if relative in changed:
            marked_changed += 1
        else:
            normalized += 1

    relation = "same" if checkpoint == head else "different"
    print(
        "macOS Ninja checkpoint restored "
        f"checkpoint={checkpoint} head={head} relation={relation} "
        f"normalized={normalized} changed={marked_changed}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("record", "restore"))
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--build-dir", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        if arguments.operation == "record":
            record(arguments.repository, arguments.build_dir)
        else:
            restore(arguments.repository, arguments.build_dir)
    except CheckpointError as error:
        print(f"macOS Ninja checkpoint error: {error}", file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
