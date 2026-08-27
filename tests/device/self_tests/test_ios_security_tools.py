#!/usr/bin/env python3
"""Device-free tests for pinned Fedora iOS security-tool installation."""

from __future__ import annotations

import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock


DEVICE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = DEVICE_ROOT / "ios" / "security_tools.py"
SPEC = importlib.util.spec_from_file_location("ios_security_tools", SCRIPT)
TOOLS = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(TOOLS)


class IosSecurityToolsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-ios-tools-")
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def archive(self, name: str, payload: bytes, *, symbolic: bool = False) -> Path:
        destination = self.root / "tool.tar.gz"
        with tarfile.open(destination, "w:gz") as archive:
            member = tarfile.TarInfo(name)
            if symbolic:
                member.type = tarfile.SYMTYPE
                member.linkname = "/tmp/escape"
                archive.addfile(member)
            else:
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))
        return destination

    def test_exact_regular_member_is_extracted_and_hashed(self):
        payload = b"open-source executable fixture"
        archive = self.archive("age/age", payload)
        destination = self.root / "private/age"
        destination.parent.mkdir(mode=0o700)
        TOOLS.extract_executable(
            archive, "age/age", destination, hashlib.sha256(payload).hexdigest()
        )
        self.assertEqual(payload, destination.read_bytes())
        self.assertEqual(0o700, destination.stat().st_mode & 0o777)

    def test_symlink_or_wrong_digest_is_rejected(self):
        destination = self.root / "private/age"
        destination.parent.mkdir(mode=0o700)
        with self.assertRaises(TOOLS.ToolError):
            TOOLS.extract_executable(
                self.archive("age/age", b"", symbolic=True),
                "age/age", destination, "0" * 64,
            )
        with self.assertRaises(TOOLS.ToolError):
            TOOLS.extract_executable(
                self.archive("age/age", b"tampered"),
                "age/age", destination, "0" * 64,
            )
        self.assertFalse(destination.exists())

    def test_oversize_or_excessive_tar_metadata_is_rejected(self):
        destination = self.root / "private/age"
        destination.parent.mkdir(mode=0o700)
        archive = self.archive("age/age", b"123456789")
        with mock.patch.object(TOOLS, "MAX_EXECUTABLE_BYTES", 8):
            with self.assertRaises(TOOLS.ToolError):
                TOOLS.extract_executable(archive, "age/age", destination, "0" * 64)

        many = self.root / "many.tar.gz"
        with tarfile.open(many, "w:gz") as output:
            for index in range(TOOLS.MAX_TAR_ENTRIES + 1):
                member = tarfile.TarInfo(f"metadata/{index}")
                member.type = tarfile.DIRTYPE
                output.addfile(member)
        with self.assertRaisesRegex(TOOLS.ToolError, "metadata"):
            TOOLS.extract_executable(many, "age/age", destination, "0" * 64)

    @unittest.skipIf(__import__("os").name == "nt", "symlink semantics differ on Windows")
    def test_private_tool_root_rejects_symlink(self):
        real = self.root / "real"
        real.mkdir()
        link = self.root / "link"
        link.symlink_to(real, target_is_directory=True)
        with self.assertRaises(TOOLS.ToolError):
            TOOLS.private_directory(link)

    def test_selected_install_downloads_only_requested_pin(self):
        lock = {
            "appium": {"iosSecurity": {
                "age": {"version": "1.2.1", "executableSha256": "1" * 64,
                        "artifact": {"url": "https://github.com/age", "sha256": "2" * 64}},
                "rcodesign": {"version": "0.29.0", "executableSha256": "3" * 64,
                              "artifact": {"url": "https://github.com/rcodesign",
                                           "sha256": "4" * 64}},
            }}
        }
        executable = self.root / "tools/rcodesign-0.29.0/rcodesign"

        def fake_extract(_archive, member, destination, _digest):
            self.assertIn("rcodesign", member)
            destination.write_bytes(b"rcodesign")

        with (mock.patch.object(TOOLS.platform, "system", return_value="Linux"),
              mock.patch.object(TOOLS.platform, "machine", return_value="x86_64"),
              mock.patch.object(TOOLS.json, "loads", return_value=lock),
              mock.patch.object(TOOLS, "download") as download,
              mock.patch.object(TOOLS, "extract_executable", side_effect=fake_extract)):
            installed = TOOLS.install(self.root / "tools", ("rcodesign",))
        self.assertEqual({"rcodesign": executable}, installed)
        self.assertEqual(1, download.call_count)

    def test_selected_install_rejects_duplicates_or_unknown_tools(self):
        with self.assertRaisesRegex(TOOLS.ToolError, "selection"):
            TOOLS.install(self.root / "duplicate", ("rcodesign", "rcodesign"))
        with self.assertRaisesRegex(TOOLS.ToolError, "selection"):
            TOOLS.install(self.root / "unknown", ("unknown",))


if __name__ == "__main__":
    unittest.main()
