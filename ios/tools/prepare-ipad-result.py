#!/usr/bin/env python3
"""Create a privacy-minimal, initially blocked iPad acceptance result."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=Path("ios/tests/device-acceptance.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--ipa-sha256", required=True)
    parser.add_argument("--xcode", required=True)
    parser.add_argument("--sdk", required=True)
    parser.add_argument("--os-version", required=True)
    args = parser.parse_args()
    try:
        matrix = json.loads(args.matrix.read_text(encoding="utf-8"))
        if args.output.exists():
            raise ValueError("output already exists")
        if not re.fullmatch(r"[0-9a-f]{40}", args.source_revision):
            raise ValueError("invalid source revision")
        if not re.fullmatch(r"[0-9a-f]{64}", args.ipa_sha256):
            raise ValueError("invalid IPA digest")
        if not re.fullmatch(r"[0-9]+(?:[.][0-9]+)+", args.os_version):
            raise ValueError("invalid iPadOS version")
        case_ids = [case["id"] for case in matrix["cases"]]
        if not case_ids or len(case_ids) != len(set(case_ids)):
            raise ValueError("acceptance matrix has invalid case IDs")
        payload = {
            "schemaVersion": 1,
            "formFactor": "ipad",
            "device": {"osVersion": args.os_version},
            "build": {
                "sourceRevision": args.source_revision,
                "bundleSha256": args.ipa_sha256,
                "xcode": args.xcode,
                "sdk": args.sdk,
            },
            "results": [
                {
                    "id": case_id,
                    "outcome": "blocked",
                    "evidence": [],
                    "notes": "Not executed yet; replace this note after physical-iPad testing.",
                }
                for case_id in case_ids
            ],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Created privacy-minimal iPad result template with {len(case_ids)} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
