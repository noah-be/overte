#!/usr/bin/env python3
"""Fail-closed structural, manifest, alignment, and signing checks for a Quest APK."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import zipfile

EXPECTED_PACKAGE = "org.overte.quest.preview"
EXPECTED_ABI = "arm64-v8a"
REQUIRED_LIBRARIES = {
    "libc++_shared.so", "libinterface.so", "libopenxr_loader.so",
    "libpicoInterface.so", "libpicoOpenXR.so", "libplugins_libopenxr.so",
}
REQUIRED_MANIFEST_MARKERS = {
    "android.hardware.vr.headtracking",
    "com.oculus.intent.category.VR",
    "com.oculus.supportedDevices",
    "quest2|questpro|quest3|quest3s",
}


def fail(message):
    raise RuntimeError(message)


def tool(explicit, name):
    candidate = Path(explicit) if explicit else Path(shutil.which(name) or "")
    if not candidate.is_file() or not candidate.stat().st_mode & 0o111:
        fail(f"{name} is not executable; pass --{name} or add it to PATH")
    return str(candidate)


def run(command):
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode:
        fail(f"command failed ({result.returncode}): {' '.join(command)}: "
             f"{(result.stderr or result.stdout).strip()}")
    return result.stdout


def inspect_zip(apk):
    try:
        with zipfile.ZipFile(apk) as archive:
            bad_member = archive.testzip()
            if bad_member:
                fail(f"APK ZIP checksum failed for {bad_member}")
            names = [entry.filename for entry in archive.infolist()]
    except zipfile.BadZipFile as error:
        fail(f"invalid APK ZIP: {error}")
    if len(names) != len(set(names)):
        fail("APK contains duplicate ZIP entries")
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            fail(f"APK contains unsafe ZIP path: {name}")
    pattern = re.compile(r"^lib/([^/]+)/([^/]+\.so)$")
    libraries = {(match.group(1), match.group(2)) for name in names
                 if (match := pattern.match(name))}
    abis = {abi for abi, _ in libraries}
    if abis != {EXPECTED_ABI}:
        fail(f"expected only {EXPECTED_ABI} native libraries, found: {sorted(abis)}")
    present = {library for abi, library in libraries if abi == EXPECTED_ABI}
    missing = REQUIRED_LIBRARIES - present
    if missing:
        fail(f"required Quest native libraries are missing: {sorted(missing)}")
    return len(names), len(present)


def parse_badging(output):
    package = re.search(r"^package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'",
                        output, re.MULTILINE)
    minimum = re.search(r"^sdkVersion:'(\d+)'$", output, re.MULTILINE)
    target = re.search(r"^targetSdkVersion:'(\d+)'$", output, re.MULTILINE)
    if not package or not minimum or not target:
        fail("aapt output is missing package, minSdk, or targetSdk metadata")
    if package.group(1) != EXPECTED_PACKAGE:
        fail(f"expected package {EXPECTED_PACKAGE}, found {package.group(1)}")
    if (minimum.group(1), target.group(1)) != ("26", "35"):
        fail(f"expected minSdk/targetSdk 26/35, found {minimum.group(1)}/{target.group(1)}")
    return {"package": package.group(1), "version_code": package.group(2),
            "version_name": package.group(3), "min_sdk": 26, "target_sdk": 35}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--aapt")
    parser.add_argument("--apksigner")
    parser.add_argument("--zipalign")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.apk.is_file() or args.apk.is_symlink():
        fail(f"APK is not a regular non-symlink file: {args.apk}")
    aapt, signer, aligner = (tool(args.aapt, "aapt"), tool(args.apksigner, "apksigner"),
                             tool(args.zipalign, "zipalign"))
    entries, library_count = inspect_zip(args.apk)
    metadata = parse_badging(run([aapt, "dump", "badging", str(args.apk)]))
    manifest = run([aapt, "dump", "xmltree", str(args.apk), "AndroidManifest.xml"])
    missing = sorted(marker for marker in REQUIRED_MANIFEST_MARKERS if marker not in manifest)
    if missing:
        fail(f"Quest manifest markers are missing: {missing}")
    run([aligner, "-c", "-v", "4", str(args.apk)])
    signature = run([signer, "verify", "--verbose", "--print-certs", str(args.apk)])
    count = re.search(r"^Number of signers: (\d+)$", signature, re.MULTILINE)
    digest = re.search(r"^Signer #1 certificate SHA-256 digest: ([0-9a-f]{64})$",
                       signature, re.MULTILINE)
    if not count or count.group(1) != "1" or not digest:
        fail("APK must have exactly one signer with a SHA-256 certificate digest")
    checksum_builder = hashlib.sha256()
    with args.apk.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum_builder.update(chunk)
    checksum = checksum_builder.hexdigest()
    report = {**metadata, "abi": EXPECTED_ABI, "apk": args.apk.name,
              "sha256": checksum, "size_bytes": args.apk.stat().st_size,
              "zip_entries": entries, "native_libraries": library_count,
              "signature_verified": True, "zip_aligned": True,
              "signer_certificate_sha256": digest.group(1)}
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(2)
