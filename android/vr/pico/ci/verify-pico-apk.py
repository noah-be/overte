#!/usr/bin/env python3
"""Fail-closed structural and signing verification for a Pico 4 APK."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import zipfile


EXPECTED_PACKAGE = "org.overte.pico"
EXPECTED_ABI = "arm64-v8a"
REQUIRED_LIBRARIES = {
    "libc++_shared.so",
    "libopenxr_loader.so",
    "libpicoInterface.so",
    "libpicoOpenXR.so",
    "libplugins_libopenxr.so",
}
E2E_LAYER_LIBRARY = "libXrApiLayer_overte_e2e_input.so"
E2E_LAYER_MANIFEST = (
    "assets/openxr/1/api_layers/explicit.d/overte_e2e_input.json"
)
E2E_LAYER_NAME = "XR_APILAYER_OVERTE_e2e_input"
E2E_BUILD_MARKER = b"OVERTE_E2E_OPENXR_INPUT_V1"
OPENXR_PLUGIN_PATH = f"lib/{EXPECTED_ABI}/libplugins_libopenxr.so"


def fail(message):
    raise RuntimeError(message)


def resolve_tool(explicit, name):
    if explicit:
        path = Path(explicit)
        if not path.is_file() or not path.stat().st_mode & 0o111:
            fail(f"{name} is not executable: {path}")
        return str(path)
    path = shutil.which(name)
    if not path:
        fail(f"{name} was not found; pass --{name} or add it to PATH")
    return path


def run_tool(command):
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        fail(f"command failed ({result.returncode}): {' '.join(command)}: {detail}")
    return result.stdout


def inspect_zip(apk):
    try:
        with zipfile.ZipFile(apk) as archive:
            bad_member = archive.testzip()
            if bad_member:
                fail(f"APK ZIP checksum failed for {bad_member}")
            names = [entry.filename for entry in archive.infolist()]
            layer_manifest_bytes = (
                archive.read(E2E_LAYER_MANIFEST) if E2E_LAYER_MANIFEST in names else None
            )
            openxr_plugin_bytes = (
                archive.read(OPENXR_PLUGIN_PATH) if OPENXR_PLUGIN_PATH in names else b""
            )
    except zipfile.BadZipFile as error:
        fail(f"invalid APK ZIP: {error}")

    if len(names) != len(set(names)):
        fail("APK contains duplicate ZIP entries")
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            fail(f"APK contains unsafe ZIP path: {name}")

    native = re.compile(r"^lib/([^/]+)/([^/]+\.so)$")
    libraries = {(match.group(1), match.group(2)) for name in names if (match := native.match(name))}
    abis = {abi for abi, _ in libraries}
    if abis != {EXPECTED_ABI}:
        fail(f"expected only {EXPECTED_ABI} native libraries, found: {sorted(abis)}")
    present = {library for abi, library in libraries if abi == EXPECTED_ABI}
    missing = REQUIRED_LIBRARIES - present
    if missing:
        fail(f"required Pico native libraries are missing: {sorted(missing)}")
    has_layer_library = E2E_LAYER_LIBRARY in present
    has_layer_manifest = layer_manifest_bytes is not None
    has_activation_marker = E2E_BUILD_MARKER in openxr_plugin_bytes
    if has_layer_library != has_layer_manifest:
        fail("E2E OpenXR input layer library and manifest must be packaged together")
    if has_activation_marker != has_layer_library:
        fail("E2E OpenXR input activation marker and layer package must match")
    if has_layer_manifest:
        try:
            layer_manifest = json.loads(layer_manifest_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            fail(f"invalid E2E OpenXR input layer manifest: {error}")
        if not isinstance(layer_manifest, dict) or set(layer_manifest) != {
                "file_format_version", "api_layer"}:
            fail("unexpected E2E OpenXR input layer manifest structure")
        api_layer = layer_manifest.get("api_layer")
        if (layer_manifest.get("file_format_version") != "1.0.0"
                or not isinstance(api_layer, dict)
                or set(api_layer) != {"name", "library_path", "api_version",
                                      "implementation_version", "description"}
                or api_layer.get("name") != E2E_LAYER_NAME
                or api_layer.get("library_path") != E2E_LAYER_LIBRARY
                or api_layer.get("api_version") != "1.0"
                or api_layer.get("implementation_version") != "1"
                or api_layer.get("description") !=
                    "Overte E2E-only bounded OpenXR input layer"):
            fail("E2E OpenXR input layer manifest does not match the test contract")
    return len(names), len(present), has_layer_manifest


def parse_badging(output):
    package = re.search(r"^package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'", output, re.MULTILINE)
    minimum = re.search(r"^sdkVersion:'(\d+)'$", output, re.MULTILINE)
    target = re.search(r"^targetSdkVersion:'(\d+)'$", output, re.MULTILINE)
    if not package or not minimum or not target:
        fail("aapt badging output is missing package, minSdk, or targetSdk metadata")
    if package.group(1) != EXPECTED_PACKAGE:
        fail(f"expected package {EXPECTED_PACKAGE}, found {package.group(1)}")
    if int(minimum.group(1)) != 26:
        fail(f"expected minSdk 26, found {minimum.group(1)}")
    if int(target.group(1)) != 35:
        fail(f"expected targetSdk 35, found {target.group(1)}")
    return {
        "package": package.group(1),
        "version_code": package.group(2),
        "version_name": package.group(3),
        "min_sdk": int(minimum.group(1)),
        "target_sdk": int(target.group(1)),
    }


def parse_signature(output):
    count = re.search(r"^Number of signers: (\d+)$", output, re.MULTILINE)
    digest = re.search(r"^Signer #1 certificate SHA-256 digest: ([0-9a-f]{64})$", output, re.MULTILINE)
    if not count or not digest:
        fail("apksigner output is missing signer count or certificate SHA-256 digest")
    if int(count.group(1)) != 1:
        fail(f"expected exactly one APK signer, found {count.group(1)}")
    return digest.group(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--aapt", help="path to Android aapt")
    parser.add_argument("--apksigner", help="path to Android apksigner")
    parser.add_argument("--source-revision", help="40-character Git commit used for the APK build")
    parser.add_argument("--expected-version-code")
    parser.add_argument("--expected-version-name")
    parser.add_argument("--expected-signer-sha256")
    layer_expectation = parser.add_mutually_exclusive_group()
    layer_expectation.add_argument(
        "--expect-e2e-input-layer", action="store_true",
        help="require the Debug-only E2E OpenXR input layer and explicit manifest",
    )
    layer_expectation.add_argument(
        "--forbid-e2e-input-layer", action="store_true",
        help="fail if the E2E OpenXR input layer or explicit manifest is packaged",
    )
    parser.add_argument("--output", type=Path, help="write verification manifest as JSON")
    args = parser.parse_args()

    if args.source_revision and not re.fullmatch(r"[0-9a-f]{40}", args.source_revision):
        fail("source revision must be a lowercase 40-character Git commit")

    if not args.apk.is_file() or args.apk.is_symlink():
        fail(f"APK is not a regular non-symlink file: {args.apk}")
    aapt = resolve_tool(args.aapt, "aapt")
    apksigner = resolve_tool(args.apksigner, "apksigner")
    entries, native_libraries, e2e_input_layer = inspect_zip(args.apk)
    if args.expect_e2e_input_layer and not e2e_input_layer:
        fail("Debug APK is missing the required E2E OpenXR input layer")
    if args.forbid_e2e_input_layer and e2e_input_layer:
        fail("release APK must not contain the E2E OpenXR input layer")
    metadata = parse_badging(run_tool([aapt, "dump", "badging", str(args.apk)]))
    if args.expected_version_code and metadata["version_code"] != args.expected_version_code:
        fail("APK version code does not match the release tag")
    if args.expected_version_name and metadata["version_name"] != args.expected_version_name:
        fail("APK version name does not match the release tag")
    signer_digest = parse_signature(
        run_tool([apksigner, "verify", "--verbose", "--print-certs", str(args.apk)])
    )
    if args.expected_signer_sha256:
        expected_signer = args.expected_signer_sha256.lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_signer):
            fail("expected signer digest must be 64 hexadecimal characters")
        if signer_digest != expected_signer:
            fail("APK signer certificate does not match the protected release signer")

    checksum = hashlib.sha256()
    with args.apk.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    digest = checksum.hexdigest()
    manifest = {
        **metadata,
        "abi": EXPECTED_ABI,
        "apk": args.apk.name,
        "sha256": digest,
        "size_bytes": args.apk.stat().st_size,
        "zip_entries": entries,
        "native_libraries": native_libraries,
        "e2e_input_layer": e2e_input_layer,
        "signature_verified": True,
        "signer_certificate_sha256": signer_digest,
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
        sys.exit(main())
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(2)
