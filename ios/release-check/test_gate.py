"""Release-gate regression tests; see QUALIFICATION.md for executed evidence."""
# SPDX-License-Identifier: Apache-2.0
import contextlib
import datetime
import io
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from artifacts import extract_zip, tree_digest
from common import Context, GROUPS
from device import analyze_metrics
from scope import swift_scope
from source_checks import gitleaks_evidence, valid_grype_database, PRIVACY_RULES
from linting import deferred_annotation
import re
import subprocess
import types


class ScannerBoundaryTests(unittest.TestCase):
    def test_grype_requires_valid_recent_database(self):
        now = datetime.datetime(2026, 9, 19, tzinfo=datetime.timezone.utc)
        status = {"valid": True, "built": "2026-09-18T00:00:00Z", "schemaVersion": "v6.1.9"}
        self.assertTrue(valid_grype_database({"status": status}, now))
        self.assertFalse(valid_grype_database({"status": dict(status, valid=False)}, now))
        self.assertFalse(valid_grype_database({"status": dict(status, built="2026-01-01T00:00:00Z")}, now))
        self.assertFalse(valid_grype_database({"status": dict(status, built="2027-01-01T00:00:00Z")}, now))
    def test_directory_fingerprint_survives_private_staging_path_changes(self):
        left = {"Fingerprint": "/temporary/one/file:test-rule:1"}
        right = {"Fingerprint": "/temporary/two/file:test-rule:1"}
        self.assertEqual(gitleaks_evidence(left, "dir", "file-digest"),
                         gitleaks_evidence(right, "dir", "file-digest"))
        self.assertNotEqual(gitleaks_evidence(left, "git", "file-digest"),
                            gitleaks_evidence(right, "git", "file-digest"))

    def test_password_event_constant_is_not_a_credential_assignment(self):
        pattern = next(p for rule, _, p in PRIVACY_RULES if rule == "credential-literal")
        self.assertIsNone(re.search(pattern, 'const RAISE_KEYBOARD_PASSWORD = "RAISE_PASSWORD";'))
        self.assertIsNotNone(re.search(pattern, 'password = "synthetic-fixture-value"'))

    def test_quoted_annotations_do_not_hide_actual_runtime_undefined_names(self):
        self.assertTrue(deferred_annotation('def die() -> "NoReturn":\n    pass\n', 1))
        self.assertFalse(deferred_annotation('def die() -> NoReturn:\n    pass\n', 1))
        self.assertFalse(deferred_annotation('def die() -> "NoReturn":\n    missing_name()\n', 2))
        self.assertTrue(deferred_annotation('from __future__ import annotations\ndef die() -> NoReturn:\n    pass\n', 2))

    def test_invalid_cppcheck_output_does_not_skip_other_linters(self):
        from source_checks import static
        with tempfile.TemporaryDirectory() as tmp, patch("common.git", return_value="a" * 40):
            ctx = Context({}, Path(tmp), ("static",))
            ctx.group = "static"
            fake = types.SimpleNamespace(texts={}, paths=[], hashes={}, production_texts=lambda: {})
            with patch.object(ctx, "command", return_value=subprocess.CompletedProcess([], 1, b"", b"broken installation")), \
                    patch("linting.run_linters") as remaining:
                static(ctx, fake)
            remaining.assert_called_once()
            self.assertTrue(any(x["rule"] == "cppcheck-report-invalid" and x["status"] == "FAIL" for x in ctx.findings))


class SwiftScopeTests(unittest.TestCase):
    def test_linux_defers_only_apple_host_helpers(self):
        with patch("scope.platform.system", return_value="Linux"):
            selected, deferred = swift_scope(["ios/ci/check.swift", "ios/src/App.swift"])
        self.assertEqual(selected, ["ios/src/App.swift"])
        self.assertEqual(deferred, ["ios/ci/check.swift"])

    def test_macos_parses_both(self):
        with patch("scope.platform.system", return_value="Darwin"):
            self.assertEqual(swift_scope(["ios/ci/check.swift", "ios/src/App.swift"]),
                             (["ios/ci/check.swift", "ios/src/App.swift"], []))


class ArchiveBoundaryTests(unittest.TestCase):
    def make_archive(self, directory, names):
        archive = Path(directory) / "input.zip"
        with zipfile.ZipFile(archive, "w") as z:
            for name in names:
                z.writestr(name, "not a secret")
        return archive

    def test_traversal_is_rejected_before_any_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = self.make_archive(tmp, ["good.txt", "../outside.txt"])
            target = Path(tmp) / "unpacked"
            with self.assertRaises(ValueError):
                extract_zip(archive, target)
            self.assertFalse(target.exists())

    def test_case_collisions_are_rejected_on_linux_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = self.make_archive(tmp, ["Payload/App.app/Info.plist", "Payload/App.app/info.plist"])
            with self.assertRaises(ValueError):
                extract_zip(archive, Path(tmp) / "unpacked")

    def test_symlink_and_archive_size_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "links.zip"
            with zipfile.ZipFile(archive, "w") as z:
                member = zipfile.ZipInfo("link")
                member.create_system = 3
                member.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(member, "/outside")
            with self.assertRaises(ValueError):
                extract_zip(archive, Path(tmp) / "unpacked")
            regular = self.make_archive(tmp, ["regular"])
            with self.assertRaises(ValueError):
                extract_zip(regular, Path(tmp) / "unpacked", max_bytes=1)

    def test_tree_identity_changes_for_bytes_and_executable_bit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item = root / "Overte"
            item.write_bytes(b"first")
            first = tree_digest(root)
            item.write_bytes(b"second")
            second = tree_digest(root)
            item.chmod(0o700)
            self.assertNotEqual(first, second)
            self.assertNotEqual(second, tree_digest(root))


class ReportBoundaryTests(unittest.TestCase):
    def context(self, directory, selected):
        with patch("common.git", return_value="a" * 40 + "\n"):
            return Context({}, Path(directory), selected)

    def test_partial_success_never_prints_release_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self.context(tmp, ("hygiene",))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(ctx.finish(), 0)
            self.assertIn("IOS RELEASE CHECK: FAIL", out.getvalue())
            self.assertNotIn("IOS RELEASE CHECK: PASS", out.getvalue())

    def test_full_gate_failure_is_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self.context(tmp, tuple(GROUPS))
            ctx.add("missing-device-evidence", "FAIL", critical=True)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ctx.finish(), 1)

    def test_review_cannot_cross_artifact_or_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self.context(tmp, ("artifact",))
            ctx.artifact_sha = "b" * 64
            review = {"sourceRevision": ctx.revision, "artifactSha256": "c" * 64,
                      "accepted": True, "reviewer": "release-reviewer",
                      "rationale": "Reviewed the complete test fixture evidence.",
                      "expires": (datetime.date.today() + datetime.timedelta(days=1)).isoformat()}
            ctx.config["reviews"] = {"candidate": review}
            self.assertFalse(ctx.review("candidate", "test", artifact=True))
            review["artifactSha256"] = ctx.artifact_sha
            review["sourceRevision"] = "d" * 40
            self.assertFalse(ctx.review("candidate", "test", artifact=True))

    def test_expired_allowlist_cannot_be_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = {"fingerprint": "a" * 64, "reason": "fixture", "owner": "reviewer", "expires": "2000-01-01"}
            with patch("common.json_read", return_value={"entries": [entry]}), patch("common.git", return_value="a" * 40):
                with self.assertRaises(ValueError):
                    Context({}, Path(tmp), ("secrets",))


if __name__ == "__main__":
    unittest.main()
