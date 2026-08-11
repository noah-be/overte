#!/usr/bin/env python3
"""Report whether a legacy APK's native library still depends on Google VR."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile


NATIVE_LIBRARY = "lib/arm64-v8a/libnative-lib.so"
GVR_LIBRARY = re.compile(r"^lib/[^/]+/libgvr(?:_audio)?[.]so$")
NEEDED_LIBRARY = re.compile(r"\(NEEDED\).*Shared library: \[([^]]+)]")
UNDEFINED_GVR_SYMBOL = re.compile(r"\bUND\b[^\n]*\b(gvr_[A-Za-z0-9_]+)\b")
MAX_NATIVE_LIBRARY_BYTES = 512 * 1024 * 1024


class EvidenceError(RuntimeError):
    pass


def sha256_stream(stream) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def run_readelf(readelf: str, arguments: list[str], library: Path, runner=subprocess.run) -> str:
    result = runner(
        [readelf, *arguments, "--", str(library)],
        text=True, capture_output=True, check=False, timeout=60,
    )
    if result.returncode:
        raise EvidenceError("readelf could not inspect the legacy native library")
    return result.stdout


def analyze(apk: Path, readelf: str, runner=subprocess.run) -> dict:
    if not apk.is_file() or apk.is_symlink():
        raise EvidenceError("APK must be a regular non-symlink file")
    with zipfile.ZipFile(apk) as archive:
        native_entries = [entry for entry in archive.infolist() if entry.filename == NATIVE_LIBRARY]
        if len(native_entries) != 1:
            raise EvidenceError("APK must contain exactly one arm64 legacy native library")
        native_entry = native_entries[0]
        if native_entry.file_size <= 0 or native_entry.file_size > MAX_NATIVE_LIBRARY_BYTES:
            raise EvidenceError("legacy native library has an invalid size")
        packaged = []
        seen = set()
        for entry in archive.infolist():
            if not GVR_LIBRARY.fullmatch(entry.filename):
                continue
            if entry.filename in seen:
                raise EvidenceError("APK contains duplicate GVR library entries")
            seen.add(entry.filename)
            with archive.open(entry) as stream:
                packaged.append({
                    "entry": entry.filename,
                    "sizeBytes": entry.file_size,
                    "sha256": sha256_stream(stream),
                })
        with tempfile.TemporaryDirectory(prefix="overte-legacy-gvr-") as directory:
            native_path = Path(directory) / "libnative-lib.so"
            with archive.open(native_entry) as source, native_path.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            dynamic = run_readelf(readelf, ["-dW"], native_path, runner)
            symbols = run_readelf(readelf, ["-Ws"], native_path, runner)
    needed = sorted(set(NEEDED_LIBRARY.findall(dynamic)))
    undefined = sorted(set(UNDEFINED_GVR_SYMBOL.findall(symbols)))
    direct_gvr_absent = "libgvr.so" not in needed and "libgvr_audio.so" not in needed
    with apk.open("rb") as stream:
        apk_sha256 = sha256_stream(stream)
    return {
        "schemaVersion": 1,
        "apkSha256": apk_sha256,
        "nativeLibrary": NATIVE_LIBRARY,
        "neededLibraries": needed,
        "undefinedGvrSymbols": undefined,
        "packagedGvrLibraries": sorted(packaged, key=lambda item: item["entry"]),
        "removalEvidence": {
            "directGvrDependencyAbsent": direct_gvr_absent,
            "undefinedGvrSymbolsAbsent": not undefined,
            "supportsRemoval": direct_gvr_absent and not undefined,
        },
        "scope": "APK packaging and arm64 ELF metadata only",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--readelf", default=shutil.which("llvm-readelf") or shutil.which("readelf"))
    args = parser.parse_args()
    if not args.readelf:
        raise EvidenceError("llvm-readelf or readelf is required")
    print(json.dumps(analyze(args.apk, args.readelf), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EvidenceError, OSError, zipfile.BadZipFile) as error:
        print(f"FAIL: {error}", file=__import__("sys").stderr)
        raise SystemExit(1)
