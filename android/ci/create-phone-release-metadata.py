#!/usr/bin/env python3
"""Create a local release manifest, CycloneDX SBOM and provenance statement."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile


def fail(message):
    raise RuntimeError(message)


def sha256_stream(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path):
    with path.open("rb") as stream:
        return sha256_stream(stream)


def source_archive_digest(repository, revision):
    process = subprocess.Popen(
        ["git", "-C", str(repository), "archive", "--format=tar", revision],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    digest = sha256_stream(process.stdout)
    stderr = process.stderr.read().decode("utf-8", errors="replace")
    if process.wait():
        fail(f"git archive failed: {stderr.strip()}")
    return digest


def load_json(path, label):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"invalid {label}: {error}")
    if not isinstance(value, dict):
        fail(f"{label} must contain a JSON object")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--apk-manifest", type=Path, required=True)
    parser.add_argument("--version-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    repository = args.repository.resolve()
    apk = args.apk.resolve()
    if not apk.is_file() or apk.is_symlink():
        fail("APK must be a regular non-symlink file")
    apk_manifest = load_json(args.apk_manifest, "APK manifest")
    version = load_json(args.version_manifest, "version manifest")
    required = {
        "sha256", "signer_certificate_sha256", "signing_state", "source_revision",
        "version_code", "version_name", "signature_verified", "package_gate",
    }
    if required - apk_manifest.keys():
        fail("APK manifest is missing required verified fields")
    if apk_manifest["sha256"] != sha256_file(apk):
        fail("APK digest does not match its verification manifest")
    for field in ("source_revision", "version_code", "version_name"):
        if apk_manifest[field] != version[field]:
            fail(f"APK and version manifests disagree on {field}")
    if apk_manifest["package_gate"] != "phone-16k":
        fail("APK manifest does not prove the required 16 KiB gate")
    signing_state = apk_manifest["signing_state"]
    if signing_state != "unsigned":
        fail("store-neutral candidate must be explicitly unsigned")
    if apk_manifest["signature_verified"] is not False or apk_manifest["signer_certificate_sha256"] is not None:
        fail("unsigned APK manifest contains contradictory signature evidence")

    components = []
    with zipfile.ZipFile(apk) as archive:
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            if not (info.filename.startswith("lib/arm64-v8a/") and info.filename.endswith(".so")):
                continue
            with archive.open(info) as stream:
                digest = sha256_stream(stream)
            components.append({
                "type": "file",
                "name": info.filename,
                "hashes": [{"alg": "SHA-256", "content": digest}],
                "properties": [{"name": "overte:apk-entry-size", "value": str(info.file_size)}],
            })
    if not components:
        fail("APK contains no ARM64 native libraries for the SBOM")

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_digest = source_archive_digest(repository, version["source_revision"])
    sbom = {
        "bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
        "metadata": {"component": {
            "type": "application", "name": "Overte Android Phone",
            "version": version["version_name"],
            "hashes": [{"alg": "SHA-256", "content": apk_manifest["sha256"]}],
        }},
        "components": components,
    }
    sbom_path = output / "android-phone-sbom.cdx.json"
    sbom_path.write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    provenance = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": apk.name, "digest": {"sha256": apk_manifest["sha256"]}}],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://overte.org/buildtypes/android-phone-release-candidate/v1",
                "externalParameters": {
                    "tag": version["tag"], "versionCode": version["version_code"],
                },
                "resolvedDependencies": [{
                    "uri": f"git+https://github.com/overte-org/overte@{version['tag']}",
                    "digest": {"gitCommit": version["source_revision"], "sha256": source_digest},
                }],
            },
            "runDetails": {"builder": {"id": "overte/android-phone-release-candidate"}},
        },
    }
    provenance_path = output / "android-phone-provenance.intoto.json"
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    release = {
        "schema_version": 2, "status": "draft-candidate", "published": False,
        "distribution": {"kind": "store-neutral", "signing_state": signing_state},
        "tag": version["tag"], "source_revision": version["source_revision"],
        "source_archive_sha256": source_digest,
        "version_code": version["version_code"], "version_name": version["version_name"],
        "apk": apk_manifest,
        "sbom": {"path": sbom_path.name, "sha256": sha256_file(sbom_path)},
        "provenance": {"path": provenance_path.name, "sha256": sha256_file(provenance_path)},
    }
    release_path = output / "android-phone-release-manifest.json"
    release_path.write_text(json.dumps(release, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checksums = [apk, args.apk_manifest.resolve(), args.version_manifest.resolve(), sbom_path, provenance_path, release_path]
    (output / "SHA256SUMS").write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in checksums), encoding="utf-8"
    )
    print(release_path)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
