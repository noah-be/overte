#!/usr/bin/env python3
"""Retire obsolete branch-local macOS bootstrap caches fail-closed.

The GitHub Actions cache is a bounded, repository-wide speed layer. Once a
successful bootstrap has published the exact current Ninja, Conan, and local
sccache generations, older macOS generations only increase cross-workflow
eviction pressure. This helper never touches remote per-object ``sccache/*``
entries, iOS keys, another architecture, or another Git ref.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ARCHITECTURE = re.compile(r"^(?:x86_64|arm64)$")
KEY = re.compile(r"^[A-Za-z0-9_.:/-]+$")
MAX_PAGES = 100
MAX_JSON_BYTES = 16 * 1024 * 1024


class PruneError(RuntimeError):
    """Cache inventory or deletion could not be proven safe."""


def api_url(api_base: str, repository: str, suffix: str) -> str:
    if not REPOSITORY.fullmatch(repository):
        raise PruneError("invalid GitHub repository identifier")
    owner, name = repository.split("/", 1)
    return (
        f"{api_base.rstrip('/')}/repos/{quote(owner, safe='')}/"
        f"{quote(name, safe='')}/{suffix.lstrip('/')}"
    )


def request_json(url: str, token: str) -> dict[str, object]:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "overte-macos-bootstrap-cache-prune",
        },
    )
    try:
        with urlopen(request, timeout=60) as response:
            body = response.read(MAX_JSON_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise PruneError("GitHub cache inventory request failed") from error
    if len(body) > MAX_JSON_BYTES:
        raise PruneError("GitHub cache inventory response is too large")
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PruneError("GitHub cache inventory response is invalid") from error
    if not isinstance(value, dict):
        raise PruneError("GitHub cache inventory is not an object")
    return value


def list_caches(repository: str, ref: str, token: str, api_base: str) -> list[dict[str, object]]:
    caches: list[dict[str, object]] = []
    encoded_ref = quote(ref, safe="")
    for page in range(1, MAX_PAGES + 1):
        suffix = f"actions/caches?ref={encoded_ref}&per_page=100&page={page}"
        payload = request_json(api_url(api_base, repository, suffix), token)
        items = payload.get("actions_caches")
        if not isinstance(items, list):
            raise PruneError("GitHub cache inventory has no actions_caches list")
        for item in items:
            if not isinstance(item, dict):
                raise PruneError("GitHub cache inventory contains an invalid entry")
            caches.append(item)
        if len(items) < 100:
            return caches
    raise PruneError("GitHub cache inventory exceeded the page limit")


def cache_identity(item: dict[str, object]) -> tuple[int, str, str, int]:
    cache_id = item.get("id")
    key = item.get("key")
    ref = item.get("ref")
    size = item.get("size_in_bytes")
    if (
        isinstance(cache_id, bool) or not isinstance(cache_id, int) or cache_id <= 0
        or not isinstance(key, str) or not KEY.fullmatch(key)
        or not isinstance(ref, str) or not ref.startswith("refs/")
        or isinstance(size, bool) or not isinstance(size, int) or size < 0
    ):
        raise PruneError("GitHub cache inventory entry has invalid identity fields")
    return cache_id, key, ref, size


def prune_plan(
    caches: list[dict[str, object]],
    ref: str,
    architecture: str,
    active_build: str,
    active_conan: str,
    active_sccache: str,
) -> tuple[list[int], int]:
    if not ref.startswith("refs/heads/") and not ref.startswith("refs/tags/"):
        raise PruneError("ref must be a canonical Git ref")
    if not ARCHITECTURE.fullmatch(architecture):
        raise PruneError("unsupported target architecture")
    active = {active_build, active_conan, active_sccache}
    if len(active) != 3 or any(not KEY.fullmatch(value) for value in active):
        raise PruneError("active cache keys are invalid or not distinct")

    required_active_prefixes = (
        (active_build, f"macos-build-tree-v3-{architecture}-", "-complete-"),
        (active_conan, f"macos-conan-v3-{architecture}-", None),
        (active_sccache, f"macos-sccache-v4-{architecture}-", "-complete-"),
    )
    for value, prefix, marker in required_active_prefixes:
        if not value.startswith(prefix) or (marker is not None and marker not in value):
            raise PruneError("active cache key does not match its required complete family")
    if "-stage-" in active_conan or "-partial-" in active_conan:
        raise PruneError("active Conan key is not a complete generation")

    prefixes = (
        f"macos-build-tree-v1-{architecture}-",
        f"macos-build-tree-v2-{architecture}-",
        f"macos-build-tree-v3-{architecture}-",
        f"macos-conan-v1-{architecture}-",
        f"macos-conan-v2-{architecture}-",
        f"macos-conan-v3-{architecture}-",
        f"macos-sccache-v1-{architecture}-",
        f"macos-sccache-v2-{architecture}-",
        f"macos-sccache-v3-{architecture}-",
        f"macos-sccache-v4-{architecture}-",
    )
    present: set[str] = set()
    delete: list[int] = []
    reclaimed = 0
    seen_ids: set[int] = set()
    for item in caches:
        cache_id, key, item_ref, size = cache_identity(item)
        if cache_id in seen_ids:
            raise PruneError("GitHub cache inventory contains a duplicate cache id")
        seen_ids.add(cache_id)
        if item_ref != ref:
            continue
        if key in active and size > 0:
            present.add(key)
        if key.startswith(prefixes) and key not in active:
            delete.append(cache_id)
            reclaimed += size

    if active - present:
        raise PruneError("current complete bootstrap cache set is not durably visible")
    return sorted(delete), reclaimed


def delete_cache(repository: str, cache_id: int, token: str, api_base: str) -> None:
    request = Request(
        api_url(api_base, repository, f"actions/caches/{cache_id}"),
        method="DELETE",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "overte-macos-bootstrap-cache-prune",
        },
    )
    try:
        with urlopen(request, timeout=60) as response:
            status = response.status
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise PruneError("GitHub cache deletion failed") from error
    if status != 204:
        raise PruneError("GitHub cache deletion returned an unexpected status")


def token_from_environment(name: str) -> str:
    token = os.environ.get(name, "")
    if not token or any(character.isspace() for character in token):
        raise PruneError("GitHub cache token is unavailable")
    return token


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--architecture", required=True)
    parser.add_argument("--active-build", required=True)
    parser.add_argument("--active-conan", required=True)
    parser.add_argument("--active-sccache", required=True)
    parser.add_argument("--token-env", required=True)
    parser.add_argument("--api-base", default="https://api.github.com")
    parser.add_argument("--settle-attempts", type=int, default=12)
    parser.add_argument("--settle-seconds", type=float, default=5.0)
    parser.add_argument("--execute", action="store_true")
    arguments = parser.parse_args()
    try:
        if not 1 <= arguments.settle_attempts <= 60:
            raise PruneError("settle-attempts is outside the safe range")
        if not 0 <= arguments.settle_seconds <= 30:
            raise PruneError("settle-seconds is outside the safe range")
        token = token_from_environment(arguments.token_env)
        last_error: PruneError | None = None
        for attempt in range(arguments.settle_attempts):
            caches = list_caches(arguments.repository, arguments.ref, token, arguments.api_base)
            try:
                delete, reclaimed = prune_plan(
                    caches,
                    arguments.ref,
                    arguments.architecture,
                    arguments.active_build,
                    arguments.active_conan,
                    arguments.active_sccache,
                )
                break
            except PruneError as error:
                last_error = error
                if attempt + 1 == arguments.settle_attempts:
                    raise
                time.sleep(arguments.settle_seconds)
        else:  # pragma: no cover
            raise last_error or PruneError("cache inventory did not settle")

        if arguments.execute:
            for cache_id in delete:
                delete_cache(arguments.repository, cache_id, token, arguments.api_base)
        print(
            "bootstrap-cache-prune "
            f"status={'executed' if arguments.execute else 'planned'} "
            f"entries={len(delete)} bytes={reclaimed}",
            flush=True,
        )
        return 0
    except PruneError as error:
        print(f"bootstrap-cache-prune: {error}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
