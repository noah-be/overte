#!/usr/bin/env python3
"""Validate an immutable Android Phone alpha tag and its Android version."""

import argparse
from contextlib import contextmanager
import fcntl
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


TAG_RE = re.compile(
    r"android-phone-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)-alpha\.([1-9][0-9]*)"
)
MAX_VERSION_CODE = 2_147_483_647
DEFAULT_VERSION_LOCK_TIMEOUT_SECONDS = 600.0


def fail(message):
    raise RuntimeError(message)


def git(repository, *args):
    result = subprocess.run(
        ["git", "-C", str(repository), *args], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        fail(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def parse_tag(tag):
    match = TAG_RE.fullmatch(tag)
    if not match:
        fail("tag must match canonical android-phone-vM.m.p-alpha.N syntax")
    parts = tuple(int(value) for value in match.groups())
    major, minor, patch, alpha = parts
    if minor > 999 or patch > 999 or alpha > 99:
        fail("tag minor/patch/alpha fields exceed 999/999/99")
    code = major * 100_000_000 + minor * 100_000 + patch * 100 + alpha
    if not 1 <= code <= MAX_VERSION_CODE:
        fail("tag-derived version code is outside Android's signed 32-bit range")
    return parts, code, tag.removeprefix("android-phone-v")


def version_lock_timeout():
    value = os.environ.get(
        "OVERTE_RELEASE_VERSION_LOCK_TIMEOUT_SECONDS",
        str(DEFAULT_VERSION_LOCK_TIMEOUT_SECONDS),
    )
    try:
        timeout = float(value)
    except ValueError:
        fail("release version lock timeout must be a non-negative number")
    if timeout < 0 or not math.isfinite(timeout):
        fail("release version lock timeout must be a non-negative number")
    return timeout


@contextmanager
def version_lifecycle(output, timeout):
    output.parent.mkdir(parents=True, exist_ok=True)
    lock_path = output.parent / f".{output.name}.lock"
    with lock_path.open("a+b") as lock:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    fail(f"timed out waiting for release version lock after {timeout:g} seconds")
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def atomic_write(path, rendered):
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
            destination.write(rendered)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def verified_version(args):
    """Validate the candidate and return its complete version manifest."""
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_revision):
        fail("source revision must be a lowercase 40-character Git commit")
    if not re.fullmatch(r"[1-9][0-9]*", args.version_code):
        fail("version code must be a positive canonical decimal integer")
    if not re.fullmatch(r"0|[1-9][0-9]*", args.published_code_floor):
        fail("published code floor must be a canonical non-negative integer")

    candidate_parts, expected_code, version_name = parse_tag(args.tag)
    supplied_code = int(args.version_code)
    floor = int(args.published_code_floor)
    if supplied_code != expected_code:
        fail(f"version code must be {expected_code} for {args.tag}")
    if supplied_code <= floor:
        fail("version code does not exceed the published version-code floor")

    repository = args.repository.resolve()
    tag_ref = f"refs/tags/{args.tag}"
    tag_commit = git(repository, "rev-list", "-n", "1", tag_ref)
    if tag_commit != args.source_revision:
        fail("release tag does not resolve to the checked-out source revision")
    head = git(repository, "rev-parse", "HEAD")
    if head != args.source_revision:
        fail("checked-out HEAD does not match the supplied source revision")

    for existing in git(repository, "tag", "--list", "android-phone-v*").splitlines():
        if not existing:
            continue
        existing_parts, existing_code, _ = parse_tag(existing)
        if existing != args.tag and existing_parts >= candidate_parts:
            fail(f"release tag is not newer than existing tag {existing}")
        if existing_parts < candidate_parts and existing_code >= supplied_code:
            fail(f"version code is not monotonic after existing tag {existing}")

    result = {
        "schema_version": 1,
        "tag": args.tag,
        "version_name": version_name,
        "version_code": supplied_code,
        "published_version_code_floor": floor,
        "source_revision": args.source_revision,
        "tag_commit": tag_commit,
        "tag_order": list(candidate_parts),
    }
    return json.dumps(result, indent=2, sort_keys=True) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--tag", required=True)
    parser.add_argument("--version-code", required=True)
    parser.add_argument("--published-code-floor", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.output:
        timeout = version_lock_timeout()
        with version_lifecycle(args.output, timeout):
            if args.output.is_symlink() or (
                    args.output.exists() and not args.output.is_file()):
                fail("release version output must be a regular non-symlink file")
            args.output.unlink(missing_ok=True)
            rendered = verified_version(args)
            atomic_write(args.output, rendered)
    else:
        rendered = verified_version(args)
    print(rendered, end="")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
