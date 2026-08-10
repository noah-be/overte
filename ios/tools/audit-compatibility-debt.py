#!/usr/bin/env python3
"""Keep the experimental iOS full-client compatibility debt explicit."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def candidate_files(source_root: Path, rule: dict) -> set[Path]:
    extensions = set(rule["extensions"])
    candidates: set[Path] = set()
    for raw_root in rule["roots"]:
        root = source_root / raw_root
        if not root.exists():
            raise ValueError(f"compatibility scan root does not exist: {raw_root}")
        paths = [root] if root.is_file() else root.rglob("*")
        candidates.update(path for path in paths if path.is_file() and path.suffix in extensions)
    return candidates


def text_matches(path: Path, pattern: re.Pattern[str]) -> bool:
    try:
        return pattern.search(path.read_text(encoding="utf-8")) is not None
    except UnicodeDecodeError:
        return False


def audit_inventory(source_root: Path, inventory: dict) -> dict[str, int]:
    if inventory.get("schemaVersion") != 1:
        raise ValueError("unsupported compatibility-debt schema")
    rules = inventory.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("compatibility-debt inventory has no rules")
    observed_ids: set[str] = set()
    counts: dict[str, int] = {}
    for rule in rules:
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or rule_id in observed_ids:
            raise ValueError(f"invalid or duplicate compatibility rule: {rule_id}")
        observed_ids.add(rule_id)
        pattern = re.compile(rule["pattern"])
        actual = {
            path.relative_to(source_root).as_posix()
            for path in candidate_files(source_root, rule)
            if text_matches(path, pattern)
        }
        expected = set(rule.get("files", []))
        if actual != expected:
            added = sorted(actual - expected)
            removed = sorted(expected - actual)
            raise ValueError(
                f"compatibility rule {rule_id} changed; added={added}, removed={removed}"
            )
        if not isinstance(rule.get("exitCriterion"), str) or not rule["exitCriterion"].strip():
            raise ValueError(f"compatibility rule has no exit criterion: {rule_id}")
        counts[rule_id] = len(actual)

    desktop_rule = next(rule for rule in rules if rule["id"] == "apple-desktop-framework")
    for relative in desktop_rule["files"]:
        text = (source_root / relative).read_text(encoding="utf-8")
        if "APPLE AND NOT IOS" not in text:
            raise ValueError(f"desktop Apple framework is not guarded from iOS: {relative}")
    return counts


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} SOURCE_ROOT INVENTORY", file=sys.stderr)
        return 2
    try:
        source_root = Path(sys.argv[1]).resolve()
        with Path(sys.argv[2]).open(encoding="utf-8") as stream:
            counts = audit_inventory(source_root, json.load(stream))
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    summary = ", ".join(f"{rule_id}={count}" for rule_id, count in counts.items())
    print(f"Verified iOS compatibility debt inventory: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
