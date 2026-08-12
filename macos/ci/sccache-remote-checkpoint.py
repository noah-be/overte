#!/usr/bin/env python3
"""Validate and safely retire branch-local GHA sccache generations.

The GHA backend stores one cache entry per compiler object.  Its public cache
key is only ``sccache/<object>``; the deterministic toolchain namespace appears
as the cache API's ``version`` field.  This helper therefore treats the
``sccache/.sccache_check`` record as the authoritative generation marker and
never deletes entries outside the requested Git ref.

No token, compiler command, environment value, or local path is emitted.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


CHECK_KEY = "sccache/.sccache_check"
SCCACHE_PREFIX = "sccache/"
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
VERSION = re.compile(r"^[0-9a-f]{64}$")
MAX_PAGES = 100
MAX_JSON_BYTES = 16 * 1024 * 1024


class CheckpointError(RuntimeError):
    """The remote compiler checkpoint is absent, unhealthy, or unsafe."""


def _counter(stats: dict[str, object], name: str) -> int:
    value = stats.get(name, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _cacheable(stats: dict[str, object]) -> int:
    total = 0
    for name in ("cache_hits", "cache_misses"):
        value = stats.get(name, {})
        if not isinstance(value, dict):
            continue
        counts = value.get("counts", value.get("adv_counts", {}))
        if isinstance(counts, dict):
            total += sum(
                int(item) for item in counts.values()
                if isinstance(item, (int, float)) and not isinstance(item, bool)
            )
    return total


def validate_stats(path: Path, mode: str) -> dict[str, int]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CheckpointError("sccache statistics are unreadable") from error
    if not isinstance(payload, dict):
        raise CheckpointError("sccache statistics are not an object")
    raw = payload.get("stats", payload)
    if not isinstance(raw, dict):
        raise CheckpointError("sccache statistics payload is invalid")

    requests = _counter(raw, "requests_executed") or _counter(raw, "compile_requests")
    writes = _counter(raw, "cache_writes")
    write_errors = _counter(raw, "cache_write_errors")
    cacheable = _cacheable(raw)
    levels = raw.get("multi_level", [])
    local = [
        level for level in levels
        if isinstance(level, dict) and "disk" in str(level.get("name", "")).lower()
    ] if isinstance(levels, list) else []
    remote = [
        level for level in levels
        if isinstance(level, dict) and "gha" in str(level.get("name", "")).lower()
    ] if isinstance(levels, list) else []
    if requests < 1 and mode != "phase":
        raise CheckpointError("compiler checkpoint recorded no requests")
    if requests < 1:
        print(
            "sccache-remote-checkpoint status=healthy requests=0 "
            "reason=no-compiler-work",
            flush=True,
        )
        return {
            "requests": 0, "cacheable": 0, "writes": 0,
            "remote_writes": 0, "remote_hits": 0,
        }
    if len(local) != 1:
        raise CheckpointError("compiler checkpoint did not expose exactly one disk level")
    if len(remote) != 1:
        raise CheckpointError("compiler checkpoint did not expose exactly one GHA level")
    local_writes = _counter(local[0], "writes")
    local_failures = _counter(local[0], "write_failures")
    remote_writes = _counter(remote[0], "writes")
    remote_hits = _counter(remote[0], "hits")
    remote_failures = _counter(remote[0], "write_failures")
    if local_failures:
        raise CheckpointError("disk compiler checkpoint reported write failures")
    if mode == "probe":
        if write_errors or remote_failures:
            raise CheckpointError("remote compiler checkpoint probe reported write failures")
        if writes < 1 or remote_writes < 1:
            raise CheckpointError("remote compiler checkpoint probe produced no GHA write")
    else:
        if cacheable < 1 or remote_writes + remote_hits < 1:
            raise CheckpointError("build produced no reusable remote compiler checkpoint")
        # GHA stores one object per request and can transiently reject a small
        # subset even though the compiler and the local disk tier succeeded.
        # A completed phase remains recoverable when every cacheable miss is
        # represented by a successful L0 write: dependency phases additionally
        # publish a verified Conan checkpoint, and the client phase publishes
        # its Ninja tree and application bundle.  Never relax the initial probe
        # above, and never accept loss in the local recovery tier.
        total_hits = _counter(raw, "cache_hits")
        if not total_hits:
            hits_payload = raw.get("cache_hits", {})
            if isinstance(hits_payload, dict):
                hit_counts = hits_payload.get("counts", {})
                if isinstance(hit_counts, dict):
                    total_hits = sum(
                        int(value) for value in hit_counts.values()
                        if isinstance(value, (int, float)) and not isinstance(value, bool)
                    )
        if local_writes + total_hits < cacheable:
            raise CheckpointError("disk compiler checkpoint did not cover all cacheable requests")

    summary = {
        "requests": requests,
        "cacheable": cacheable,
        "writes": writes,
        "local_writes": local_writes,
        "remote_writes": remote_writes,
        "remote_hits": remote_hits,
        "remote_failures": remote_failures,
    }
    status = "degraded" if write_errors or remote_failures else "healthy"
    print(
        f"sccache-remote-checkpoint status={status} "
        + " ".join(f"{name}={value}" for name, value in summary.items()),
        flush=True,
    )
    return summary


def _api_url(api_base: str, repository: str, suffix: str) -> str:
    if not REPOSITORY.fullmatch(repository):
        raise CheckpointError("invalid GitHub repository identifier")
    owner, name = repository.split("/", 1)
    return (
        f"{api_base.rstrip('/')}/repos/{quote(owner, safe='')}/"
        f"{quote(name, safe='')}/{suffix.lstrip('/')}"
    )


def _request_json(url: str, token: str) -> dict[str, object]:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "overte-macos-sccache-checkpoint",
        },
    )
    try:
        with urlopen(request, timeout=60) as response:
            contents = response.read(MAX_JSON_BYTES + 1)
    except HTTPError as error:
        raise CheckpointError(f"GitHub cache API failed with HTTP {error.code}") from error
    except (OSError, URLError) as error:
        raise CheckpointError("GitHub cache API request failed") from error
    if len(contents) > MAX_JSON_BYTES:
        raise CheckpointError("GitHub cache API response is too large")
    try:
        payload = json.loads(contents)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CheckpointError("GitHub cache API response is invalid") from error
    if not isinstance(payload, dict):
        raise CheckpointError("GitHub cache API response is not an object")
    return payload


def list_caches(repository: str, ref: str, token: str, api_base: str) -> list[dict[str, object]]:
    if not ref.startswith("refs/") or any(character in ref for character in "\r\n"):
        raise CheckpointError("invalid Git ref")
    result: list[dict[str, object]] = []
    for page in range(1, MAX_PAGES + 1):
        suffix = (
            "actions/caches?per_page=100"
            f"&page={page}&ref={quote(ref, safe='')}"
        )
        payload = _request_json(_api_url(api_base, repository, suffix), token)
        batch = payload.get("actions_caches")
        if not isinstance(batch, list):
            raise CheckpointError("GitHub cache inventory is invalid")
        for item in batch:
            if isinstance(item, dict):
                result.append(item)
        if len(batch) < 100:
            return result
    raise CheckpointError("GitHub cache inventory exceeded the bounded page limit")


def _timestamp(item: dict[str, object]) -> tuple[str, int]:
    accessed = item.get("last_accessed_at") or item.get("created_at") or ""
    identifier = item.get("id", 0)
    return str(accessed), int(identifier) if isinstance(identifier, int) else 0


def current_version(caches: Iterable[dict[str, object]], ref: str) -> str:
    checks = [
        item for item in caches
        if item.get("key") == CHECK_KEY and item.get("ref") == ref
        and isinstance(item.get("version"), str)
        and VERSION.fullmatch(str(item["version"]))
    ]
    if not checks:
        raise CheckpointError("remote compiler checkpoint generation marker is missing")
    return str(max(checks, key=_timestamp)["version"])


def discover_version(
    repository: str, ref: str, token: str, api_base: str, *,
    attempts: int = 24, retry_interval: float = 5.0,
) -> str:
    if attempts <= 0 or retry_interval < 0:
        raise CheckpointError("invalid compiler checkpoint discovery policy")
    for attempt in range(1, attempts + 1):
        try:
            return current_version(
                list_caches(repository, ref, token, api_base), ref
            )
        except CheckpointError as error:
            if "generation marker is missing" not in str(error) or attempt == attempts:
                raise
            print(
                "sccache-remote-checkpoint status=waiting-for-marker "
                f"attempt={attempt}",
                flush=True,
            )
            time.sleep(retry_interval)
    raise AssertionError("unreachable")


def prune_ids(
    caches: Iterable[dict[str, object]], ref: str, active_version: str,
    retain_previous: int,
) -> tuple[set[str], list[int]]:
    if not VERSION.fullmatch(active_version) or retain_previous < 0:
        raise CheckpointError("invalid compiler checkpoint retention policy")
    scoped = [
        item for item in caches
        if item.get("ref") == ref
        and isinstance(item.get("key"), str)
        and str(item["key"]).startswith(SCCACHE_PREFIX)
        and isinstance(item.get("version"), str)
        and VERSION.fullmatch(str(item["version"]))
    ]
    markers = [item for item in scoped if item.get("key") == CHECK_KEY]
    if active_version not in {str(item["version"]) for item in markers}:
        raise CheckpointError("active compiler checkpoint marker is not present")
    versions: list[str] = []
    for marker in sorted(markers, key=_timestamp, reverse=True):
        version = str(marker["version"])
        if version != active_version and version not in versions:
            versions.append(version)
    keep = {active_version, *versions[:retain_previous]}
    delete = sorted(
        int(item["id"]) for item in scoped
        if str(item["version"]) not in keep
        and isinstance(item.get("id"), int) and int(item["id"]) > 0
    )
    return keep, delete


def _delete_cache(repository: str, cache_id: int, token: str, api_base: str) -> None:
    request = Request(
        _api_url(api_base, repository, f"actions/caches/{cache_id}"),
        method="DELETE",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "overte-macos-sccache-checkpoint",
        },
    )
    try:
        with urlopen(request, timeout=60) as response:
            if response.status not in (200, 204):
                raise CheckpointError("GitHub cache deletion returned an unexpected status")
    except HTTPError as error:
        raise CheckpointError(f"GitHub cache deletion failed with HTTP {error.code}") from error
    except (OSError, URLError) as error:
        raise CheckpointError("GitHub cache deletion failed") from error


def _token(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise CheckpointError("GitHub cache token is unavailable")
    return value


def _output(path: Path | None, name: str, value: str) -> None:
    if path is None:
        return
    if not re.fullmatch(r"[a-z_]+", name) or "\n" in value or "\r" in value:
        raise CheckpointError("invalid GitHub output")
    with path.open("a", encoding="utf-8") as stream:
        stream.write(f"{name}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    stats = commands.add_parser("verify-stats")
    stats.add_argument("--stats", type=Path, required=True)
    stats.add_argument("--mode", choices=("probe", "build", "phase"), required=True)
    for name in ("discover", "prune"):
        remote = commands.add_parser(name)
        remote.add_argument("--repository", required=True)
        remote.add_argument("--ref", required=True)
        remote.add_argument("--token-env", default="GITHUB_TOKEN")
        remote.add_argument("--api-base", default="https://api.github.com")
        remote.add_argument("--github-output", type=Path)
        if name == "discover":
            remote.add_argument("--attempts", type=int, default=24)
            remote.add_argument("--retry-interval", type=float, default=5.0)
        if name == "prune":
            remote.add_argument("--active-version", required=True)
            remote.add_argument("--retain-previous", type=int, default=1)
            remote.add_argument("--execute", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.command == "verify-stats":
            validate_stats(arguments.stats, arguments.mode)
            return 0
        token = _token(arguments.token_env)
        if arguments.command == "discover":
            version = discover_version(
                arguments.repository, arguments.ref, token, arguments.api_base,
                attempts=arguments.attempts,
                retry_interval=arguments.retry_interval,
            )
            _output(arguments.github_output, "version", version)
            print("sccache-remote-checkpoint status=discovered", flush=True)
            return 0
        caches = list_caches(arguments.repository, arguments.ref, token, arguments.api_base)
        keep, delete = prune_ids(
            caches, arguments.ref, arguments.active_version, arguments.retain_previous
        )
        if arguments.execute:
            for index, cache_id in enumerate(delete, 1):
                _delete_cache(arguments.repository, cache_id, token, arguments.api_base)
                if index % 100 == 0:
                    print(
                        "sccache-remote-checkpoint status=pruning "
                        f"deleted={index} total={len(delete)}",
                        flush=True,
                    )
        print(
            "sccache-remote-checkpoint status=complete "
            f"kept_generations={len(keep)} deleted_entries={len(delete) if arguments.execute else 0} "
            f"eligible_entries={len(delete)}",
            flush=True,
        )
        return 0
    except CheckpointError as error:
        print(f"sccache remote checkpoint error: {error}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
