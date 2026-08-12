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


SCHEMA = 1
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
    if payload.get("schema") != SCHEMA:
        raise CheckpointError("unsupported checkpoint metadata schema")
    commit = payload.get("commit")
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise CheckpointError("checkpoint contains an invalid commit id")
    if payload.get("baseline_ns") != BASELINE_NS:
        raise CheckpointError("checkpoint contains an invalid source baseline")
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
    # Cached metadata is untrusted input.  Resolve it as a commit before using it
    # in a diff and never interpret a cached value as a path or option.
    git(repository, "cat-file", "-e", f"{checkpoint}^{{commit}}")
    head = git(repository, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()

    tracked = nul_paths(git(repository, "ls-files", "-z"))
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
