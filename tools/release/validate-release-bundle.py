#!/usr/bin/env python3
"""Validate an Overte release bundle without network or device access."""

import argparse
from pathlib import Path
import sys

from release_bundle import BundleError, validate_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--product")
    parser.add_argument("--source-revision")
    parser.add_argument("--release-tag")
    args = parser.parse_args()
    contract = validate_bundle(args.bundle)
    if args.product and contract["product"] != args.product:
        raise BundleError("bundle product does not match the expected product")
    if args.source_revision and contract["source_revision"] != args.source_revision:
        raise BundleError("bundle source revision does not match the expected commit")
    if args.release_tag and contract["release_tag"] != args.release_tag:
        raise BundleError("bundle release tag does not match the expected tag")
    print(args.bundle.resolve() / "release-bundle.json")


if __name__ == "__main__":
    try:
        main()
    except (BundleError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
