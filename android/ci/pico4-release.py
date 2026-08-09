#!/usr/bin/env python3
"""Validate Pico RC coordinates and create deterministic release metadata."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


TAG = re.compile(r"pico4-v(\d{1,2})\.(\d{1,2})\.(\d{1,2})-rc\.(\d{1,2})")


def coordinates(tag: str) -> dict[str, object]:
    match = TAG.fullmatch(tag)
    if not match:
        raise ValueError("tag must match pico4-vMAJOR.MINOR.PATCH-rc.N")
    major, minor, patch, rc = map(int, match.groups())
    if minor > 99 or patch > 99 or not 1 <= rc <= 99:
        raise ValueError("minor/patch must be 0..99 and rc must be 1..99")
    version_code = major * 10_000_000 + minor * 100_000 + patch * 1_000 + rc
    if not 1 <= version_code <= 2_100_000_000:
        raise ValueError("derived Android version code is outside the supported range")
    return {
        "tag": tag,
        "version_name": f"{major}.{minor}.{patch}-rc.{rc}",
        "version_code": version_code,
        "release_type": "RC",
    }


def canonical_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--github-ref")
    parser.add_argument("--apk-manifest", type=Path)
    parser.add_argument("--dependency-checksums", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    release = coordinates(args.tag)
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        raise ValueError("revision must be a lowercase 40-character Git commit")
    if args.github_ref and args.github_ref != f"refs/tags/{args.tag}":
        raise ValueError("workflow ref must be the exact requested tag")

    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            for key in ("tag", "version_name", "version_code", "release_type"):
                output.write(f"{key}={release[key]}\n")

    if not args.output_dir:
        print(canonical_json({**release, "source_revision": args.revision}), end="")
        return 0
    if not args.apk_manifest or not args.dependency_checksums:
        raise ValueError("bundle generation requires APK manifest and dependency checksums")
    manifest = json.loads(args.apk_manifest.read_text(encoding="utf-8"))
    expected = {
        "version_name": release["version_name"],
        "version_code": str(release["version_code"]),
        "source_revision": args.revision,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"APK manifest {key} does not match release coordinates")

    dependencies = []
    for line in args.dependency_checksums.read_text(encoding="utf-8").splitlines():
        digest, name = line.split(None, 1)
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid dependency checksum manifest")
        dependencies.append({"name": name.strip(), "sha256": digest})

    args.output_dir.mkdir(parents=True, exist_ok=True)
    provenance = {
        "schema": "org.overte.pico.release-candidate.v1",
        **release,
        "source_revision": args.revision,
        "artifact": manifest,
        "dependencies": sorted(dependencies, key=lambda item: item["name"]),
    }
    sbom = {
        "bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
        "metadata": {"component": {"type": "application", "name": "Overte Pico 4",
                                   "version": release["version_name"]}},
        "components": [{"type": "file", "name": item["name"],
                        "hashes": [{"alg": "SHA-256", "content": item["sha256"]}]}
                       for item in sorted(dependencies, key=lambda item: item["name"])],
    }
    files = {
        "pico4-release-manifest.json": provenance,
        "pico4-sbom.cdx.json": sbom,
    }
    for name, value in files.items():
        (args.output_dir / name).write_text(canonical_json(value), encoding="utf-8")
    digest_lines = [f"{sha256(args.output_dir / name)}  {name}" for name in sorted(files)]
    digest_lines.append(f"{manifest['sha256']}  {manifest['apk']}")
    (args.output_dir / "SHA256SUMS").write_text("\n".join(digest_lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
