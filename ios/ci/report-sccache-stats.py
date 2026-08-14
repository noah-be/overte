#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

"""Emit a compact, stable summary for sccache 0.17 JSON statistics."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


def counter_total(value: object) -> int:
    if not isinstance(value, dict):
        return 0
    counts = value.get("counts")
    if isinstance(counts, dict) and counts:
        return sum(int(item) for item in counts.values())
    advanced = value.get("adv_counts")
    if isinstance(advanced, dict):
        return sum(int(item) for item in advanced.values())
    return 0


def load_stats(path: pathlib.Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stats = payload.get("stats", payload)
    if not isinstance(stats, dict):
        raise ValueError("statistics payload is not an object")
    return stats


def local_cache_usage(path: pathlib.Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    files = [candidate for candidate in path.rglob("*") if candidate.is_file()]
    return len(files), sum(candidate.stat().st_size for candidate in files)


def summarize(stats: dict, cache_dir: pathlib.Path, phase: str) -> dict:
    hits = counter_total(stats.get("cache_hits"))
    misses = counter_total(stats.get("cache_misses"))
    requests = int(stats.get("requests_executed", stats.get("compile_requests", 0)))
    writes = int(stats.get("cache_writes", 0))
    write_errors = int(stats.get("cache_write_errors", 0))
    file_count, local_bytes = local_cache_usage(cache_dir)
    levels = []
    for raw in stats.get("multi_level", []):
        if not isinstance(raw, dict):
            continue
        levels.append(
            {
                "name": str(raw.get("name", "unknown")),
                "hits": int(raw.get("hits", 0)),
                "misses": int(raw.get("misses", 0)),
                "writes": int(raw.get("writes", 0)),
                "writeFailures": int(raw.get("write_failures", 0)),
            }
        )
    total_lookups = hits + misses
    return {
        "phase": phase,
        "version": str(stats.get("version", "unknown")),
        "requests": requests,
        "hits": hits,
        "misses": misses,
        "hitRatePercent": round((100.0 * hits / total_lookups), 2) if total_lookups else 0.0,
        "writes": writes,
        "writeErrors": write_errors,
        "reportedCacheBytes": int(stats.get("cache_size", 0)),
        "localCacheFiles": file_count,
        "localCacheBytes": local_bytes,
        "levels": levels,
    }


def validate_activity(summary: dict) -> None:
    if summary["requests"] < 1:
        raise ValueError("V8 rebuild produced no sccache compiler requests")
    if summary["hits"] + summary["misses"] < 1:
        raise ValueError("V8 rebuild produced no cacheable compiler requests")
    if summary["localCacheFiles"] < 1 or summary["localCacheBytes"] < 4096:
        raise ValueError("V8 rebuild left no reusable local compiler checkpoint")
    remote = [level for level in summary["levels"] if "gha" in level["name"].lower()]
    if not remote:
        raise ValueError("V8 rebuild did not configure the remote GitHub cache level")
    if summary["misses"] and not any(level["writes"] for level in remote):
        raise ValueError("V8 cache misses produced no remote compiler checkpoint writes")
    remote_writes = sum(level["writes"] for level in remote)
    remote_failures = sum(level["writeFailures"] for level in remote)
    attempts = remote_writes + remote_failures
    if attempts and remote_failures / attempts > 0.05:
        raise ValueError(
            f"remote V8 compiler checkpoint write failure rate is too high: {remote_failures}/{attempts}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stats", type=pathlib.Path)
    parser.add_argument("--cache-dir", type=pathlib.Path, required=True)
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    parser.add_argument("--require-activity", action="store_true")
    args = parser.parse_args()
    try:
        summary = summarize(load_stats(args.stats), args.cache_dir, args.phase)
        if args.require_activity:
            validate_activity(summary)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"report-sccache-stats: {exc}", file=sys.stderr)
        return 1
    line = json.dumps(summary, sort_keys=True, separators=(",", ":"))
    print(f"V8 sccache summary: {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
