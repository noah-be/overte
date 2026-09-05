#!/usr/bin/env python3
"""Offline iOS consumer of the original SH-008 scene-bound performance analyzer.

No native trace, approved budget or device identity is invented here. The Shared
validator retains its pending/not-node-accepted result distinction.
"""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import argparse
import hashlib
import json
from pathlib import Path
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/candidate"))
from shared_release import verify_release

MANIFEST_SHA256 = "ca53fddbdf16ffdb48ecb2298f3e6ebd260d9be413d09904bee9c9cc579cad96"
MODULE_SHA256 = "a48201c899e0bf3608d9ec8554c1e234759e54560815914799040449f1eff15f"
MODULE = "tests/performance/schema/metrics.py"
REFERENCE = "tests/performance/schema/reference-fixture.json"


def load_analyzer(release: Path, repository: Path):
    published = verify_release(release, MANIFEST_SHA256, MODULE, executable=False)
    # This release refers to existing repository fixture files rather than
    # duplicating them. Verify its exact installed module/reference, then let
    # the ORIGINAL validator recheck all referenced fixture bytes itself.
    source = None
    for relative in (MODULE, REFERENCE):
        installed = repository / relative
        if any(path.is_symlink() for path in (installed, *installed.parents)) or not installed.is_file():
            raise ValueError("IOS_METRICS_SOURCE")
        with installed.open("rb") as stream:
            content = stream.read(1048577)
        if len(content) > 1048576 or content != (release / relative).read_bytes():
            raise ValueError("IOS_METRICS_SOURCE")
        if relative == MODULE:
            source = content
    if hashlib.sha256(source).hexdigest() != MODULE_SHA256 or not published.is_file():
        raise ValueError("IOS_METRICS_SOURCE")
    module = types.ModuleType("overte_sh008_performance_v001")
    module.__file__ = str((repository / MODULE).resolve())
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shared-contract-root", type=Path, required=True)
    parser.add_argument("--consumer-repository", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-artifact-sha256", required=True)
    parser.add_argument("--form-factor", choices=("ipad", "iphone"), required=True)
    parser.add_argument("--expected-fixture-sha256", required=True)
    parser.add_argument("--budget", type=Path)
    parser.add_argument("--expected-budget-sha256")
    parser.add_argument("--require-budget", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.require_budget and (args.budget is None or args.expected_budget_sha256 is None):
            raise ValueError("IOS_APPROVED_BUDGET_REQUIRED")
        analyzer = load_analyzer(args.shared_contract_root, args.consumer_repository)
        result = analyzer.validate(args.trace, args.expected_source_sha, args.expected_artifact_sha256,
            "ios-" + args.form_factor, args.expected_fixture_sha256, args.budget, args.expected_budget_sha256)
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        print("IOS_PERFORMANCE_TRACE_REJECTED", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
