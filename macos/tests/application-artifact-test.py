#!/usr/bin/env python3
"""Hermetic tests for native macOS application artifact provenance."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "macos/ci/application-artifact.py"
SPEC = importlib.util.spec_from_file_location("application_artifact", TOOL)
assert SPEC is not None and SPEC.loader is not None
artifact = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(artifact)


class ApplicationArtifactTests(unittest.TestCase):
    MACHO64 = b"\xcf\xfa\xed\xfe"

    @classmethod
    def write_macho(cls, path: Path, architectures: str, payload: str) -> None:
        path.write_bytes(cls.MACHO64 + f"MACHO:{architectures}\n{payload}\n".encode("ascii"))

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.root = Path(self.temporary.name)
        self.app = self.root / "Overte.app"
        (self.app / "Contents/MacOS").mkdir(parents=True)
        (self.app / "Contents/Frameworks/QtCore.framework/Versions/5").mkdir(parents=True)
        self.main = self.app / "Contents/MacOS/Overte"
        self.framework = self.app / "Contents/Frameworks/QtCore.framework/Versions/5/QtCore"
        self.write_macho(self.main, "arm64", "main")
        self.main.chmod(0o755)
        self.write_macho(self.framework, "arm64 x86_64", "framework")
        os.symlink("5", self.app / "Contents/Frameworks/QtCore.framework/Versions/Current")
        os.symlink(
            "Versions/Current/QtCore",
            self.app / "Contents/Frameworks/QtCore.framework/QtCore",
        )
        (self.app / "Contents/Info.plist").write_text("not Mach-O\n", encoding="utf-8")
        self.file_tool = self.root / "fake-file.py"
        self.lipo_tool = self.root / "fake-lipo.py"
        self.file_tool.write_text(
            "#!/usr/bin/env python3\n"
            "from pathlib import Path\n"
            "import sys\n"
            "data = Path(sys.argv[-1]).read_bytes()\n"
            "print('Mach-O 64-bit binary' if b'MACHO:' in data[:64] else 'ASCII text')\n",
            encoding="utf-8",
        )
        self.lipo_tool.write_text(
            "#!/usr/bin/env python3\n"
            "from pathlib import Path\n"
            "import sys\n"
            "data = Path(sys.argv[-1]).read_bytes()\n"
            "marker = data.find(b'MACHO:')\n"
            "if marker < 0:\n"
            "    raise SystemExit(1)\n"
            "print(data[marker + 6:].splitlines()[0].decode('ascii'))\n",
            encoding="utf-8",
        )
        self.file_tool.chmod(0o755)
        self.lipo_tool.chmod(0o755)
        self.manifest = self.root / "application-manifest.json"
        self.metadata = artifact.metadata_from_values(
            repository="overte-org/overte",
            repository_id=123456,
            workflow=".github/workflows/macos-bootstrap.yml",
            ref="refs/heads/apple-macos",
            sha="a" * 40,
            run_id=987654,
            run_attempt=2,
            target_arch="arm64",
            xcode_version="16.4",
            xcode_build="16F6",
            sdk_version="15.5",
            build_type="RelWithDebInfo",
            deployment_target="11.0",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def package(self):
        return artifact.package_application(
            self.app, self.manifest, self.metadata,
            file_tool=self.file_tool, lipo_tool=self.lipo_tool,
        )

    def verify(self, metadata=None):
        return artifact.verify_application(
            self.app, self.manifest, metadata or self.metadata,
            file_tool=self.file_tool, lipo_tool=self.lipo_tool,
        )

    def test_round_trip_records_strict_provenance_hashes_and_architectures(self):
        manifest = self.package()
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["kind"], artifact.KIND)
        self.assertEqual(manifest["provenance"], self.metadata["provenance"])
        self.assertEqual(manifest["build"], self.metadata["build"])
        self.assertEqual(manifest["application"]["main_executable"], artifact.MAIN_EXECUTABLE)
        entries = manifest["application"]["mach_o"]
        self.assertEqual([entry["path"] for entry in entries], [
            "Contents/Frameworks/QtCore.framework/Versions/5/QtCore",
            "Contents/MacOS/Overte",
        ])
        self.assertEqual(entries[0]["architectures"], ["arm64", "x86_64"])
        self.assertEqual(entries[1]["architectures"], ["arm64"])
        self.assertEqual(
            manifest["application"]["main_sha256"], entries[1]["sha256"],
        )
        self.assertEqual(self.manifest.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.verify(), manifest)

    def test_mach_o_magic_prefilter_is_complete_and_rejects_resources(self):
        candidate = self.root / "candidate"
        for magic in artifact.MACH_O_MAGICS:
            with self.subTest(magic=magic.hex()):
                candidate.write_bytes(magic + b"payload")
                self.assertTrue(artifact._has_mach_o_magic(candidate))
        for payload in (b"", b"Mach-O text", b"\x89PNG", b"!<arch>\n"):
            with self.subTest(payload=payload):
                candidate.write_bytes(payload)
                self.assertFalse(artifact._has_mach_o_magic(candidate))

    def test_every_mach_o_must_have_the_target_slice_during_package_and_verify(self):
        self.write_macho(self.framework, "x86_64", "framework")
        with self.assertRaisesRegex(artifact.ArtifactError, "lacks arm64"):
            self.package()

        self.write_macho(self.framework, "arm64", "framework")
        self.package()
        self.write_macho(self.framework, "x86_64", "framework")
        with self.assertRaisesRegex(artifact.ArtifactError, "lacks arm64"):
            self.verify()

    def test_bundle_tampering_and_inventory_changes_fail_closed(self):
        self.package()
        self.write_macho(self.main, "arm64", "tampered")
        with self.assertRaisesRegex(artifact.ArtifactError, "does not match"):
            self.verify()

        self.write_macho(self.main, "arm64", "main")
        extra = self.app / "Contents/PlugIns/extra.dylib"
        extra.parent.mkdir()
        self.write_macho(extra, "arm64", "extra")
        with self.assertRaisesRegex(artifact.ArtifactError, "does not match"):
            self.verify()

    def test_expected_provenance_and_build_metadata_are_enforced(self):
        self.package()
        cases = (
            ("provenance", "repository", "fork/overte", "provenance mismatch"),
            ("provenance", "repository_id", 999, "provenance mismatch"),
            ("provenance", "workflow", ".github/workflows/other.yml", "provenance mismatch"),
            ("provenance", "ref", "refs/heads/other", "provenance mismatch"),
            ("provenance", "sha", "b" * 40, "provenance mismatch"),
            ("provenance", "run_id", 7, "provenance mismatch"),
            ("provenance", "run_attempt", 3, "provenance mismatch"),
            ("build", "xcode_version", "16.3", "build metadata mismatch"),
            ("build", "xcode_build", "16E1", "build metadata mismatch"),
            ("build", "sdk_version", "15.4", "build metadata mismatch"),
            ("build", "build_type", "Release", "build metadata mismatch"),
            ("build", "deployment_target", "12.0", "build metadata mismatch"),
            ("build", "target_arch", "x86_64", "build metadata mismatch"),
        )
        for section, field, value, message in cases:
            with self.subTest(section=section, field=field):
                changed = json.loads(json.dumps(self.metadata))
                changed[section][field] = value
                with self.assertRaisesRegex(artifact.ArtifactError, message):
                    self.verify(changed)

    def test_manifest_schema_is_strict_and_duplicate_fields_are_rejected(self):
        self.package()
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        payload["unexpected"] = True
        self.manifest.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(artifact.ArtifactError, "root fields"):
            self.verify()

        payload.pop("unexpected")
        payload["schema_version"] = True
        self.manifest.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(artifact.ArtifactError, "root fields"):
            self.verify()

        payload["schema_version"] = 1
        payload["application"]["mach_o"][0]["architectures"] = [1]
        self.manifest.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(artifact.ArtifactError, "inventory architectures"):
            self.verify()

        self.manifest.write_text(
            '{"schema_version":1,"schema_version":1,"kind":"x"}', encoding="utf-8",
        )
        with self.assertRaisesRegex(artifact.ArtifactError, "duplicate JSON fields"):
            self.verify()

    def test_main_executable_must_be_a_real_mach_o_file(self):
        self.main.write_text("not Mach-O\n", encoding="utf-8")
        with self.assertRaisesRegex(artifact.ArtifactError, "main application executable is not Mach-O"):
            self.package()

        self.main.unlink()
        os.symlink("../../Info.plist", self.main)
        with self.assertRaisesRegex(artifact.ArtifactError, "missing or unsafe"):
            self.package()

    def test_cli_round_trip_uses_injected_tools_and_rejects_wrong_sha(self):
        common = [
            "--app", str(self.app), "--manifest", str(self.manifest),
            "--repository", "overte-org/overte", "--repository-id", "123456",
            "--workflow", ".github/workflows/macos-bootstrap.yml",
            "--ref", "refs/heads/apple-macos", "--sha", "a" * 40,
            "--run-id", "987654", "--run-attempt", "2", "--target-arch", "arm64",
            "--xcode-version", "16.4", "--xcode-build", "16F6",
            "--sdk-version", "15.5", "--build-type", "RelWithDebInfo",
            "--deployment-target", "11.0", "--file-tool", str(self.file_tool),
            "--lipo-tool", str(self.lipo_tool),
        ]
        packaged = subprocess.run(
            [sys.executable, str(TOOL), "package", *common],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(packaged.returncode, 0, packaged.stderr)
        self.assertEqual(json.loads(packaged.stdout)["mach_o_count"], 2)
        verified = subprocess.run(
            [sys.executable, str(TOOL), "verify", *common],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(verified.returncode, 0, verified.stderr)
        wrong = common.copy()
        wrong[wrong.index("--sha") + 1] = "b" * 40
        rejected = subprocess.run(
            [sys.executable, str(TOOL), "verify", *wrong],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(rejected.returncode, 1)
        self.assertIn("provenance mismatch", rejected.stderr)
        self.assertNotIn(str(self.root), rejected.stderr)

    def test_invalid_metadata_and_tool_failures_are_rejected(self):
        with self.assertRaisesRegex(artifact.ArtifactError, "invalid ref"):
            artifact.metadata_from_values(
                repository="overte-org/overte", repository_id=1,
                workflow=".github/workflows/macos-bootstrap.yml",
                ref="refs/heads/../unsafe", sha="a" * 40, run_id=1, run_attempt=1,
                target_arch="arm64", xcode_version="16.4", xcode_build="16F6",
                sdk_version="15.5", build_type="Release", deployment_target="11.0",
            )
        broken = self.root / "broken-file.py"
        broken.write_text("#!/usr/bin/env python3\nraise SystemExit(1)\n", encoding="utf-8")
        broken.chmod(0o755)
        with self.assertRaisesRegex(artifact.ArtifactError, "file tool failed"):
            artifact.package_application(
                self.app, self.manifest, self.metadata,
                file_tool=broken, lipo_tool=self.lipo_tool,
            )

    def test_non_utf8_file_description_is_safe_but_architectures_are_ascii(self):
        non_utf8_file = self.root / "non-utf8-file.py"
        non_utf8_file.write_text(
            "#!/usr/bin/env python3\n"
            "from pathlib import Path\n"
            "import sys\n"
            "data = Path(sys.argv[-1]).read_bytes()\n"
            "output = b'Mach-O 64-bit binary\\n' if b'MACHO:' in data[:64] else b'font metadata \\xa9\\n'\n"
            "sys.stdout.buffer.write(output)\n",
            encoding="utf-8",
        )
        non_utf8_file.chmod(0o755)
        manifest = artifact.package_application(
            self.app, self.manifest, self.metadata,
            file_tool=non_utf8_file, lipo_tool=self.lipo_tool,
        )
        self.assertEqual(len(manifest["application"]["mach_o"]), 2)
        self.assertEqual(
            artifact.verify_application(
                self.app, self.manifest, self.metadata,
                file_tool=non_utf8_file, lipo_tool=self.lipo_tool,
            ),
            manifest,
        )

        non_ascii_lipo = self.root / "non-ascii-lipo.py"
        non_ascii_lipo.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "sys.stdout.buffer.write(b'arm64 \\xa9\\n')\n",
            encoding="utf-8",
        )
        non_ascii_lipo.chmod(0o755)
        with self.assertRaisesRegex(
                artifact.ArtifactError, "invalid Mach-O architecture list"):
            artifact.package_application(
                self.app, self.manifest, self.metadata,
                file_tool=non_utf8_file, lipo_tool=non_ascii_lipo,
            )

    def test_transport_archive_preserves_symlinks_modes_and_manifest(self):
        manifest = self.package()
        archive_path = self.root / "transport/Overte.app.tar"
        artifact.archive_application(self.app, archive_path)
        self.assertEqual(archive_path.stat().st_mode & 0o777, 0o600)

        destination = self.root / "restored/interface"
        restored = artifact.extract_application_archive(archive_path, destination)
        self.assertEqual(restored, destination / "Overte.app")
        current = restored / "Contents/Frameworks/QtCore.framework/Versions/Current"
        public_binary = restored / "Contents/Frameworks/QtCore.framework/QtCore"
        self.assertTrue(current.is_symlink())
        self.assertEqual(os.readlink(current), "5")
        self.assertTrue(public_binary.is_symlink())
        self.assertEqual(os.readlink(public_binary), "Versions/Current/QtCore")
        self.assertEqual((restored / "Contents/MacOS/Overte").stat().st_mode & 0o777, 0o755)
        self.assertEqual(
            artifact.verify_application(
                restored, self.manifest, self.metadata,
                file_tool=self.file_tool, lipo_tool=self.lipo_tool,
            ),
            manifest,
        )

    def test_transport_archive_rejects_traversal_and_escaping_symlinks(self):
        traversal = self.root / "traversal.tar"
        with tarfile.open(traversal, "w") as archive:
            member = tarfile.TarInfo("../escape")
            member.size = 0
            archive.addfile(member)
        with self.assertRaisesRegex(artifact.ArtifactError, "unsafe path"):
            artifact.extract_application_archive(traversal, self.root / "bad-one")
        self.assertFalse((self.root / "escape").exists())

        escaping_link = self.root / "escaping-link.tar"
        with tarfile.open(escaping_link, "w") as archive:
            root = tarfile.TarInfo("Overte.app")
            root.type = tarfile.DIRTYPE
            archive.addfile(root)
            link = tarfile.TarInfo("Overte.app/Contents/escape")
            link.type = tarfile.SYMTYPE
            link.linkname = "../../../outside"
            archive.addfile(link)
        with self.assertRaisesRegex(artifact.ArtifactError, "escaping symlink"):
            artifact.extract_application_archive(escaping_link, self.root / "bad-two")

    def test_transport_cli_round_trip_and_nonempty_destination_fail_closed(self):
        archive_path = self.root / "cli/Overte.app.tar"
        archived = subprocess.run(
            [
                sys.executable, str(TOOL), "archive",
                "--app", str(self.app), "--archive", str(archive_path),
            ],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(archived.returncode, 0, archived.stderr)
        self.assertEqual(json.loads(archived.stdout)["mode"], "archive")

        destination = self.root / "cli-restored"
        extracted = subprocess.run(
            [
                sys.executable, str(TOOL), "extract",
                "--archive", str(archive_path), "--destination", str(destination),
            ],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(extracted.returncode, 0, extracted.stderr)
        self.assertEqual(json.loads(extracted.stdout)["mode"], "extract")
        rejected = subprocess.run(
            [
                sys.executable, str(TOOL), "extract",
                "--archive", str(archive_path), "--destination", str(destination),
            ],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(rejected.returncode, 1)
        self.assertIn("destination is not empty", rejected.stderr)
        self.assertNotIn(str(self.root), rejected.stderr)


if __name__ == "__main__":
    unittest.main()
