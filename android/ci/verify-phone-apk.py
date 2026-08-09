#!/usr/bin/env python3
"""Run the complete Phone APK gate and emit build provenance."""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GATE = ROOT / "android/tests/check-phone-apk-16k.sh"
EXPECTED_PACKAGE = "org.overte.phone"
DEFAULT_TEMP_ROOT = ROOT / "android/build/apk-verification-tmp"
DEFAULT_MANIFEST_LOCK_TIMEOUT_SECONDS = 600.0


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


def verify_unsigned(signer, apk):
    result = subprocess.run(
        [signer, "verify", "--verbose", "--print-certs", str(apk)],
        text=True, capture_output=True, check=False,
    )
    if result.returncode == 0:
        fail("APK was expected to be unsigned but has a valid signature")
    detail = f"{result.stdout}\n{result.stderr}"
    if not re.search(r"DOES NOT VERIFY|not signed|Missing META-INF", detail, re.IGNORECASE):
        fail("apksigner did not provide recognized evidence that the APK is unsigned")


def sha256(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def manifest_lock_timeout():
    value = os.environ.get(
        "OVERTE_APK_MANIFEST_LOCK_TIMEOUT_SECONDS",
        str(DEFAULT_MANIFEST_LOCK_TIMEOUT_SECONDS),
    )
    try:
        timeout = float(value)
    except ValueError as error:
        fail("APK manifest lock timeout must be a non-negative number")
    if timeout < 0 or not math.isfinite(timeout):
        fail("APK manifest lock timeout must be a non-negative number")
    return timeout


@contextmanager
def manifest_lifecycle(output, timeout):
    output.parent.mkdir(parents=True, exist_ok=True)
    lock_path = output.parent / f".{output.name}.lock"
    with lock_path.open("a+b") as lock:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    fail(f"timed out waiting for APK manifest lock after {timeout:g} seconds")
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def atomic_write(path, rendered):
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
            destination.write(rendered)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def verified_manifest(args):
    """Run all gates and return a manifest only after complete verification."""
    if not args.apk.is_file() or args.apk.is_symlink():
        fail(f"APK is not a regular non-symlink file: {args.apk}")
    if not args.package_gate.is_file() or not args.package_gate.stat().st_mode & 0o111:
        fail(f"Phone package gate is not executable: {args.package_gate}")
    if args.source_revision and not re.fullmatch(r"[0-9a-f]{40}", args.source_revision):
        fail("source revision must be a lowercase 40-character Git commit")
    if args.expect_unsigned and args.expect_signer:
        fail("--expect-unsigned and --expect-signer are mutually exclusive")

    analyzer = executable(args.apkanalyzer, "apkanalyzer")
    signer = executable(args.apksigner, "apksigner")
    temp_root = Path(os.environ.get("PHONE_APK_VERIFY_TMPDIR", DEFAULT_TEMP_ROOT))
    if temp_root.is_symlink():
        fail(f"APK verification temporary directory must not be a symlink: {temp_root}")
    temp_root.mkdir(parents=True, exist_ok=True)
    if not temp_root.is_dir() or not os.access(temp_root, os.W_OK):
        fail(f"APK verification temporary directory is not writable: {temp_root}")
    gate_env = os.environ.copy()
    gate_env["PHONE_APK_ANALYZER"] = analyzer
    gate_env["TMPDIR"] = str(temp_root.resolve())
    if args.expect_debuggable is not None:
        gate_env["PHONE_EXPECT_DEBUGGABLE"] = args.expect_debuggable
    run([str(args.package_gate), str(args.apk)], env=gate_env)

    package = analyzer_value(analyzer, args.apk, "application-id")
    if package != EXPECTED_PACKAGE:
        fail(f"expected package {EXPECTED_PACKAGE}, found {package}")
    signer_digest = None
    if args.expect_unsigned:
        verify_unsigned(signer, args.apk)
    else:
        signed = run([signer, "verify", "--verbose", "--print-certs", str(args.apk)])
        signer_digest = signature_digest(signed)
        if args.expect_signer:
            expected_signer = args.expect_signer.lower().replace(":", "")
            if not re.fullmatch(r"[0-9a-f]{64}", expected_signer):
                fail("expected signer must be a SHA-256 certificate digest")
            if signer_digest != expected_signer:
                fail("APK signer certificate does not match the approved upload key")
    version_code_value = analyzer_value(analyzer, args.apk, "version-code")
    if not re.fullmatch(r"[1-9][0-9]*", version_code_value):
        fail("APK version code is not a positive canonical decimal integer")
    manifest = {
        "apk": args.apk.name,
        "package": package,
        "version_code": int(version_code_value),
        "version_name": analyzer_value(analyzer, args.apk, "version-name"),
        "min_sdk": int(analyzer_value(analyzer, args.apk, "min-sdk")),
        "target_sdk": int(analyzer_value(analyzer, args.apk, "target-sdk")),
        "debuggable": analyzer_value(analyzer, args.apk, "debuggable") == "true",
        "abi": "arm64-v8a",
        "page_size_bytes": 16384,
        "size_bytes": args.apk.stat().st_size,
        "sha256": sha256(args.apk),
        "signing_state": "unsigned" if args.expect_unsigned else "signed",
        "signature_verified": not args.expect_unsigned,
        "signer_certificate_sha256": signer_digest,
        "package_gate": "phone-16k",
    }
    if args.source_revision:
        manifest["source_revision"] = args.source_revision
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--package-gate", type=Path, default=DEFAULT_GATE)
    parser.add_argument("--apkanalyzer")
    parser.add_argument("--apksigner")
    parser.add_argument("--expect-debuggable", choices=("0", "1"))
    parser.add_argument("--source-revision")
    parser.add_argument("--expect-signer", help="required signer certificate SHA-256")
    parser.add_argument("--expect-unsigned", action="store_true",
                        help="require an unsigned APK for store-neutral handoff")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output:
        timeout = manifest_lock_timeout()
        with manifest_lifecycle(args.output, timeout):
            if args.output.is_symlink() or (
                    args.output.exists() and not args.output.is_file()):
                fail("APK manifest output must be a regular non-symlink file")
            args.output.unlink(missing_ok=True)
            rendered = verified_manifest(args)
            atomic_write(args.output, rendered)
    else:
        rendered = verified_manifest(args)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
