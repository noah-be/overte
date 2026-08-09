#!/usr/bin/env python3
"""Run the complete Phone APK gate and emit signed build provenance."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GATE = ROOT / "android/tests/check-phone-apk-16k.sh"
EXPECTED_PACKAGE = "org.overte.phone"


def fail(message):
    raise RuntimeError(message)


def executable(explicit, name):
    if explicit:
        path = Path(explicit)
        if not path.is_file() or not path.stat().st_mode & 0o111:
            fail(f"{name} is not executable: {path}")
        return str(path)
    found = shutil.which(name)
    if not found:
        fail(f"{name} was not found; pass --{name} or add it to PATH")
    return found


def run(command, *, env=None):
    result = subprocess.run(command, text=True, capture_output=True, env=env, check=False)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        fail(f"command failed ({result.returncode}): {' '.join(command)}: {detail}")
    return result.stdout.strip()


def analyzer_value(analyzer, apk, field):
    value = run([analyzer, "manifest", field, str(apk)])
    if not value or "\n" in value or "\r" in value:
        fail(f"apkanalyzer returned invalid {field} metadata")
    return value


def signature_digest(output):
    signers = re.search(r"^Number of signers: (\d+)$", output, re.MULTILINE)
    digest = re.search(r"^Signer #1 certificate SHA-256 digest: ([0-9a-f]{64})$", output, re.MULTILINE)
    if not signers or not digest:
        fail("apksigner output is missing signer count or certificate SHA-256 digest")
    if int(signers.group(1)) != 1:
        fail(f"expected exactly one APK signer, found {signers.group(1)}")
    return digest.group(1)


def sha256(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--package-gate", type=Path, default=DEFAULT_GATE)
    parser.add_argument("--apkanalyzer")
    parser.add_argument("--apksigner")
    parser.add_argument("--expect-debuggable", choices=("0", "1"))
    parser.add_argument("--source-revision")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if not args.apk.is_file() or args.apk.is_symlink():
        fail(f"APK is not a regular non-symlink file: {args.apk}")
    if not args.package_gate.is_file() or not args.package_gate.stat().st_mode & 0o111:
        fail(f"Phone package gate is not executable: {args.package_gate}")
    if args.source_revision and not re.fullmatch(r"[0-9a-f]{40}", args.source_revision):
        fail("source revision must be a lowercase 40-character Git commit")

    analyzer = executable(args.apkanalyzer, "apkanalyzer")
    signer = executable(args.apksigner, "apksigner")
    gate_env = os.environ.copy()
    gate_env["PHONE_APK_ANALYZER"] = analyzer
    if args.expect_debuggable is not None:
        gate_env["PHONE_EXPECT_DEBUGGABLE"] = args.expect_debuggable
    run([str(args.package_gate), str(args.apk)], env=gate_env)

    package = analyzer_value(analyzer, args.apk, "application-id")
    if package != EXPECTED_PACKAGE:
        fail(f"expected package {EXPECTED_PACKAGE}, found {package}")
    signed = run([signer, "verify", "--verbose", "--print-certs", str(args.apk)])
    manifest = {
        "apk": args.apk.name,
        "package": package,
        "version_code": analyzer_value(analyzer, args.apk, "version-code"),
        "version_name": analyzer_value(analyzer, args.apk, "version-name"),
        "min_sdk": int(analyzer_value(analyzer, args.apk, "min-sdk")),
        "target_sdk": int(analyzer_value(analyzer, args.apk, "target-sdk")),
        "debuggable": analyzer_value(analyzer, args.apk, "debuggable") == "true",
        "abi": "arm64-v8a",
        "page_size_bytes": 16384,
        "size_bytes": args.apk.stat().st_size,
        "sha256": sha256(args.apk),
        "signature_verified": True,
        "signer_certificate_sha256": signature_digest(signed),
        "package_gate": "phone-16k",
    }
    if args.source_revision:
        manifest["source_revision"] = args.source_revision
    rendered = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
