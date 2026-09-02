#!/usr/bin/env python3
"""Reject credentials and private device identities in persisted E2E artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


PATTERNS = (
    ("credential-key", re.compile(
        r'(?i)["\'](?:password|passwd|access[_-]?token|control[_-]?token|authorization|secret)["\']\s*[:=]')),
    ("credential-url", re.compile(r"[a-z][a-z0-9+.-]*://[^/@\s:]+:[^/@\s]+@", re.I)),
    ("android-serial-label", re.compile(r"(?i)[\"'](?:deviceSerial|udid|androidSerial)[\"']\s*:")),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", action="append", required=True, type=Path)
    parser.add_argument("--forbid-value", action="append", default=[],
                        help="private value to detect; it is never printed")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    forbidden = [value for value in args.forbid_value if value]
    findings = []
    for root in args.result:
        root = root.resolve()
        if not root.is_dir():
            raise ValueError("artifact result must be a directory")
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            if path.stat().st_size > 4 * 1024 * 1024:
                continue
            content = path.read_bytes()
            if b"\0" in content:
                continue
            text = content.decode("utf-8", errors="replace")
            categories = {name for name, pattern in PATTERNS if pattern.search(text)}
            if any(value in text for value in forbidden):
                categories.add("private-selector")
            for category in sorted(categories):
                findings.append({"path": path.relative_to(root).as_posix(),
                                 "category": category})
    payload = {"schemaVersion": 1,
               "status": "failed" if findings else "passed",
               "findings": findings}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"Artifact privacy audit: {payload['status']} ({len(findings)} finding(s))")
    return 1 if findings else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=__import__("sys").stderr)
        raise SystemExit(2)
