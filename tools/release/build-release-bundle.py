#!/usr/bin/env python3
"""Build a complete, offline-verifiable Overte Android release bundle."""

import argparse
from pathlib import Path
import sys

from release_bundle import BundleError, create_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--verified-manifest", type=Path, required=True)
    parser.add_argument("--version-manifest", type=Path, required=True)
    parser.add_argument("--dependency-inventory", type=Path, required=True)
    parser.add_argument("--notice-bundle", type=Path, required=True)
    parser.add_argument("--source-archive", type=Path, required=True)
    parser.add_argument("--build-environment", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    create_bundle(
        product=args.product, source_revision=args.source_revision,
        payload=args.payload, verified_manifest=args.verified_manifest,
        version_manifest=args.version_manifest,
        dependency_inventory=args.dependency_inventory,
        notice_bundle=args.notice_bundle, source_archive=args.source_archive,
        build_environment=args.build_environment, output=args.output_dir,
    )
    print(args.output_dir.resolve() / "release-bundle.json")


if __name__ == "__main__":
    try:
        main()
    except (BundleError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
