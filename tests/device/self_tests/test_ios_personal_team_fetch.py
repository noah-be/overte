#!/usr/bin/env python3
"""Device-free public Personal-Team kit fetch safety tests."""

from __future__ import annotations

import importlib.util
import argparse
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
import urllib.request
from unittest import mock


DEVICE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = DEVICE_ROOT / "ios" / "fetch_personal_team_kit.py"
REUSE_SCRIPT = DEVICE_ROOT / "ios" / "fetch_reusable_overte_artifact.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("fetch_personal_team_kit", SCRIPT)
assert SPEC and SPEC.loader
FETCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FETCH)
REUSE_SPEC = importlib.util.spec_from_file_location(
    "fetch_reusable_overte_artifact", REUSE_SCRIPT
)
assert REUSE_SPEC and REUSE_SPEC.loader
REUSE = importlib.util.module_from_spec(REUSE_SPEC)
REUSE_SPEC.loader.exec_module(REUSE)


class IosPersonalTeamFetchTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-personal-kit-fetch-")
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def make_archive(self, payload: bytes = b"fixture") -> Path:
        archive = self.root / "kit.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for name in FETCH.EXPECTED_NAMES:
                output.writestr(name, payload)
        return archive

    def test_exact_archive_extracts_only_three_bounded_public_files(self):
        destination = self.root / "output"
        FETCH.extract(self.make_archive(), destination)
        self.assertEqual(set(FETCH.EXPECTED_NAMES), {item.name for item in destination.iterdir()})
        for item in destination.iterdir():
            self.assertEqual(0o644, item.stat().st_mode & 0o777)

    def test_high_ratio_and_unexpected_member_fail_closed_and_cleanup(self):
        archive = self.make_archive(b"0" * (1024 * 1024))
        destination = self.root / "bomb-output"
        with self.assertRaisesRegex(FETCH.SYNC.HandoffError, "extraction limits"):
            FETCH.extract(archive, destination)
        self.assertFalse(destination.exists())

        archive.unlink()
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("../personal-team-e2e-kit.json", b"bad")
        with self.assertRaisesRegex(FETCH.SYNC.HandoffError, "exact three"):
            FETCH.extract(archive, destination)

    def test_artifact_selection_binds_exact_run_attempt_and_digest(self):
        run = {
            "id": 123, "run_attempt": 2, "head_sha": "a" * 40,
            "repository": {"id": 42},
        }
        item = {
            "name": "ios-personal-team-e2e-kit-v2-123-2", "expired": False,
            "id": 77, "digest": "sha256:" + "1" * 64,
            "archive_download_url":
                "https://api.github.com/repos/noah-be/overte/actions/artifacts/77/zip",
            "workflow_run": {
                "id": 123, "repository_id": 42, "head_repository_id": 42,
                "head_branch": "apple-ios", "head_sha": "a" * 40,
            },
        }
        self.assertIs(item, FETCH.select_artifact({"total_count": 1, "artifacts": [item]}, run))
        item["name"] = "ios-personal-team-e2e-kit-v2-999-1"
        with self.assertRaisesRegex(FETCH.SYNC.HandoffError, "no unique"):
            FETCH.select_artifact({"total_count": 1, "artifacts": [item]}, run)

    def test_reusable_overte_selection_requires_attempt_one_and_exact_artifact(self):
        run = {
            "id": 33000393530, "run_attempt": 1, "run_number": 521,
            "head_sha": "a" * 40, "repository": {"id": 42},
        }
        item = {
            "id": 9619898701,
            "name": "521-overte-ios-integrated-e2e-unsigned-33000393530",
            "size_in_bytes": 413495489,
            "digest": "sha256:" + "1" * 64,
            "expired": False,
            "created_at": "2026-08-26T19:17:40Z",
            "archive_download_url":
                "https://api.github.com/repos/noah-be/overte/actions/artifacts/"
                "9619898701/zip",
            "workflow_run": {
                "id": 33000393530, "repository_id": 42,
                "head_repository_id": 42, "head_branch": "apple-ios",
                "head_sha": "a" * 40,
            },
        }
        api = mock.Mock()
        api.artifacts.return_value = [item]
        self.assertIs(item, REUSE.select_artifact(api, run))
        run["run_attempt"] = 2
        with self.assertRaisesRegex(REUSE.SYNC.HandoffError, "attempt 1"):
            REUSE.select_artifact(api, run)

    def test_reusable_overte_extract_rejects_extra_or_traversal_members(self):
        archive = self.root / "reusable.zip"
        names = {
            "0521-OverteIOSClient-Release-device-unsigned.ipa": b"ipa",
            "0521-OverteIOSClient-Release-device-unsigned.json": b"{}",
        }
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for name, payload in names.items():
                output.writestr(name, payload)
        destination = self.root / "reusable-output"
        ipa, manifest = REUSE.extract(archive, destination)
        self.assertEqual(set(names), {ipa.name, manifest.name})

        archive.unlink()
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("../0521-OverteIOSClient-Release-device-unsigned.ipa", b"bad")
            output.writestr("0521-OverteIOSClient-Release-device-unsigned.json", b"{}")
        with self.assertRaisesRegex(REUSE.SYNC.HandoffError, "unsafe member"):
            REUSE.extract(archive, self.root / "rejected-reuse")

    def test_private_token_is_api_only_and_removed_on_blob_redirect(self):
        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

        class Opener:
            request = None

            def open(self, request, timeout):
                self.request = request
                return Response(json.dumps({"ok": True}).encode())

        opener = Opener()
        value = FETCH.api_json(
            "https://api.github.com/repos/noah-be/overte/actions/runs/123",
            "private-token", opener=opener,
        )
        self.assertTrue(value["ok"])
        self.assertEqual("Bearer private-token", opener.request.get_header("Authorization"))
        request = urllib.request.Request(
            "https://api.github.com/repos/noah-be/overte/actions/artifacts/77/zip",
            headers={"Authorization": "Bearer private-token"},
        )
        redirected = FETCH.SYNC.SafeRedirectHandler().redirect_request(
            request, None, 302, "Found", {},
            "https://example.blob.core.windows.net/private/artifact.zip",
        )
        self.assertIsNotNone(redirected)
        self.assertIsNone(redirected.get_header("Authorization"))

    def test_dispatch_selects_only_returned_run_attempt_one_with_audited_inputs(self):
        arguments = argparse.Namespace(
            repository="noah-be/overte", run_id=None, run_attempt=None,
            timeout_seconds=3600, poll_seconds=20,
            qt_host_cache_key="overte-qt-host-v2-a-contract-" + "1" * 64,
            qt_ios_cache_key="overte-qt-ios-v2-b-contract-" + "2" * 64,
            qt_host_artifact_prefix="overte-qt-host-checkpoint-v1-" + "3" * 32,
            qt_ios_artifact_prefix="overte-qt-ios-checkpoint-v1-" + "4" * 32,
            overte_reuse_run_id=33000393530,
            overte_reuse_run_attempt=1,
        )
        api = mock.Mock()
        api.dispatch.return_value = 8675309
        selected = {"id": 8675309, "run_attempt": 1}
        with mock.patch.object(FETCH.SYNC, "GitHubApi", return_value=api), mock.patch.object(
                FETCH.SYNC, "wait_for_run", return_value=selected) as wait:
            self.assertIs(selected, FETCH.select_run(arguments, "private-token"))
        api.dispatch.assert_called_once_with({
            "personal_team_e2e_kit": "true",
            "qt_host_cache_key": arguments.qt_host_cache_key,
            "qt_ios_cache_key": arguments.qt_ios_cache_key,
            "qt_host_artifact_prefix": arguments.qt_host_artifact_prefix,
            "qt_ios_artifact_prefix": arguments.qt_ios_artifact_prefix,
            "personal_team_overte_reuse_run_id": "33000393530",
        })
        wait.assert_called_once_with(api, 8675309, 1, 3600, 20)

        arguments.qt_ios_cache_key = "$(unsafe)"
        with self.assertRaisesRegex(FETCH.SYNC.HandoffError, "dispatch input"):
            FETCH.dispatch_inputs(arguments)

    def test_explicit_selection_never_dispatches_or_uses_latest(self):
        arguments = argparse.Namespace(
            repository="noah-be/overte", run_id=123, run_attempt=2,
        )
        run = {
            "id": 123, "event": "workflow_dispatch",
            "path": ".github/workflows/ios-bootstrap.yml",
            "head_branch": "apple-ios", "head_sha": "a" * 40,
            "repository": {"id": 42, "full_name": "noah-be/overte"},
            "head_repository": {"id": 42, "full_name": "noah-be/overte"},
            "run_attempt": 2, "status": "completed", "conclusion": "success",
        }
        with mock.patch.object(FETCH, "api_json", return_value=run) as request, \
                mock.patch.object(FETCH.SYNC, "GitHubApi") as api:
            self.assertIs(run, FETCH.select_run(arguments, "private-token"))
        request.assert_called_once_with(
            "https://api.github.com/repos/noah-be/overte/actions/runs/123",
            "private-token",
        )
        api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
