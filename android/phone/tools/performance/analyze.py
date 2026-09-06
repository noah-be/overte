#!/usr/bin/env python3
"""Phone PH-005 offline SH-008 consumer; never executes or accepts a device run."""
# SPDX-License-Identifier: Apache-2.0
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tests/performance/schema"))
sys.path.insert(0, str(ROOT / "provenance"))
from metrics import validate as validate_metrics
from artifact_identity import digest_file, require


def analyze_phone(trace, artifact, expected_source, expected_artifact,
                  expected_fixture, budget=None, expected_budget=None):
    # Bind the supplied candidate bytes, not just two producer-authored JSON
    # values. Signature, installed-candidate and producer trust remain external.
    paths = [Path(trace), Path(artifact)]
    if budget is not None:
        paths.append(Path(budget))
    identities = set()
    for path in paths:
        require(path.is_file() and not path.is_symlink(), "PHONE_METRICS_REGULAR_INPUT")
        info = path.stat()
        identity = (info.st_dev, info.st_ino)
        require(identity not in identities, "PHONE_METRICS_REUSED_INPUT")
        identities.add(identity)
    require(digest_file(artifact) == expected_artifact, "PHONE_METRICS_CANDIDATE_BYTES")
    # Use Shared units, cadence, checkpoint, duration, STOP and budget rules
    # unchanged. There is no Phone copy of a common schema or numeric budget.
    return validate_metrics(trace, expected_source, expected_artifact,
                            "android-phone", expected_fixture, budget, expected_budget)


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "PHONE_METRICS_ARGUMENTS_REJECTED\n")

    def parse_args(self, args=None, namespace=None):
        values = list(sys.argv[1:] if args is None else args)
        seen = set()
        for value in values:
            if value.startswith("--"):
                option = value.split("=", 1)[0]
                if option in seen:
                    self.error("duplicate option")
                seen.add(option)
        return super().parse_args(values, namespace)


def main(argv=None):
    parser = PrivateParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-artifact-sha256", required=True)
    parser.add_argument("--expected-fixture-sha256", required=True)
    parser.add_argument("--budget", type=Path)
    parser.add_argument("--expected-budget-sha256")
    args = parser.parse_args(argv)
    try:
        result = analyze_phone(args.trace, args.artifact, args.expected_source_sha,
                               args.expected_artifact_sha256, args.expected_fixture_sha256,
                               args.budget, args.expected_budget_sha256)
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        # Shared error objects and malformed trace content are never log context.
        print("PHONE_METRICS_REJECTED", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
