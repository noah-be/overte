#!/usr/bin/env python3
"""Host tests for deterministic external-sideload IPA normalization."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import json
import plistlib
import stat
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path


IOS_ROOT = Path(__file__).resolve().parents[1]
TOOL = IOS_ROOT / "tools/normalize-sideload-ipa.py"
OLD_ID = "org.overte.interface.dev"
NEW_ID = "org.overte.interface.sideload.b206"


def archive_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def entry(name: str, mode: int, *, directory: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name + ("/" if directory else ""))
    info.create_system = 3
    info.external_attr = mode << 16
    return info


def create_fixture(path: Path, *, malicious: str | None = None, signed: bool = False) -> None:
    metadata = {
        "CFBundleDisplayName": "Overte",
        "CFBundleExecutable": "Overte",
        "CFBundleIdentifier": OLD_ID,
        "CFBundleName": "Overte",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "1",
        "CFBundleSupportedPlatforms": ["iPhoneOS"],
        "LSRequiresIPhoneOS": True,
        "UIDeviceFamily": [1, 2],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(entry("Payload", stat.S_IFDIR | 0o755, directory=True), b"")
        archive.writestr(
            entry("Payload/Overte.app", stat.S_IFDIR | 0o755, directory=True), b""
        )
        info = entry("Payload/Overte.app/Info.plist", stat.S_IFREG | 0o644)
        info.extra = b"\x99\x99\x00\x00"
        archive.writestr(info, plistlib.dumps(metadata, fmt=plistlib.FMT_BINARY))
        archive.writestr(
            entry("Payload/Overte.app/Overte", stat.S_IFREG | 0o755),
            b"\xcf\xfa\xed\xfe" + b"fixture executable",
        )
        archive.writestr(
            entry("Payload/Overte.app/PrivacyInfo.xcprivacy", stat.S_IFREG | 0o644),
            b"privacy",
        )
        archive.writestr(
            entry("Payload/Overte.app/data.txt", stat.S_IFREG | 0o644), b"data"
        )
        archive.writestr(
            entry("Payload/Overte.app/data-link", stat.S_IFLNK | 0o777), b"data.txt"
        )
        if signed:
            archive.writestr(
                entry(
                    "Payload/Overte.app/_CodeSignature/CodeResources",
                    stat.S_IFREG | 0o644,
                ),
                b"signature",
            )
        if malicious:
            archive.writestr(malicious, b"unsafe")


class NormalizerTests(unittest.TestCase):
    def run_tool(
        self,
        source: Path,
        output: Path,
        manifest: Path,
        *,
        digest: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(TOOL),
                str(source),
                str(output),
                "--bundle-id",
                NEW_ID,
                "--expected-sha256",
                digest or archive_digest(source),
                "--manifest",
                str(manifest),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_normalizes_identifier_metadata_order_and_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.ipa"
            output = root / "normalized.ipa"
            second = root / "normalized-second.ipa"
            manifest = root / "manifest.json"
            create_fixture(source)
            result = self.run_tool(source, output, manifest)
            self.assertEqual(result.returncode, 0, result.stderr)

            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["originalBundleIdentifier"], OLD_ID)
            self.assertEqual(payload["bundleIdentifier"], NEW_ID)
            self.assertEqual(payload["sourceSha256"], archive_digest(source))
            self.assertEqual(payload["sha256"], archive_digest(output))
            self.assertEqual(payload["infoPlistFormat"], "binary1")
            self.assertFalse(payload["signed"])
            self.assertTrue(payload["requiresSigning"])

            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
                self.assertEqual(
                    names[:3],
                    ["Payload/", "Payload/Overte.app/", "Payload/Overte.app/Info.plist"],
                )
                self.assertEqual(archive.comment, b"")
                self.assertFalse(any(info.extra for info in archive.infolist()))
                info = plistlib.loads(archive.read("Payload/Overte.app/Info.plist"))
                self.assertEqual(info["CFBundleIdentifier"], NEW_ID)
                self.assertTrue(
                    archive.read("Payload/Overte.app/Info.plist").startswith(b"bplist00")
                )
                executable = archive.getinfo("Payload/Overte.app/Overte")
                self.assertEqual(executable.external_attr >> 16 & 0o777, 0o755)
                link = archive.getinfo("Payload/Overte.app/data-link")
                self.assertTrue(stat.S_ISLNK(link.external_attr >> 16))
                self.assertEqual(archive.read(link), b"data.txt")

            second_manifest = root / "second.json"
            second_result = self.run_tool(source, second, second_manifest)
            self.assertEqual(second_result.returncode, 0, second_result.stderr)
            self.assertEqual(output.read_bytes(), second.read_bytes())

    def test_rejects_wrong_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.ipa"
            create_fixture(source)
            result = self.run_tool(
                source, root / "output.ipa", root / "manifest.json", digest="0" * 64
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("SHA-256", result.stderr)

    def test_rejects_content_outside_application(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.ipa"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                create_fixture(source, malicious="../escape")
            result = self.run_tool(source, root / "output.ipa", root / "manifest.json")
            self.assertEqual(result.returncode, 1)
            self.assertIn("unsafe ZIP entry", result.stderr)

    def test_rejects_signed_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.ipa"
            create_fixture(source, signed=True)
            result = self.run_tool(source, root / "output.ipa", root / "manifest.json")
            self.assertEqual(result.returncode, 1)
            self.assertIn("must be unsigned", result.stderr)


if __name__ == "__main__":
    unittest.main()
