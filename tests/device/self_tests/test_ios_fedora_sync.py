#!/usr/bin/env python3
"""Device-free tests for authenticated GitHub-to-Fedora iOS synchronization."""

from __future__ import annotations

import importlib.util
import io
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import urllib.error
import zipfile


DEVICE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = DEVICE_ROOT / "ios" / "sync_fedora_artifacts.py"
SPEC = importlib.util.spec_from_file_location("sync_fedora_artifacts", SCRIPT)
SYNC = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(SYNC)


class Response(io.BytesIO):
    def __init__(self, value: object):
        super().__init__(json.dumps(value).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class Opener:
    def __init__(self, values: list[object]):
        self.values = list(values)
        self.requests = []

    def open(self, request, timeout=0):
        self.requests.append((request, timeout))
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return Response(value)


class IosFedoraSyncTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-ios-fedora-sync-")
        self.root = Path(self.temporary.name)
        self.revision = "a" * 40
        self.run = {
            "id": 123,
            "event": "workflow_dispatch",
            "path": ".github/workflows/ios-fedora-e2e-producer.yml@apple-ios",
            "head_branch": "apple-ios",
            "head_sha": self.revision,
            "repository": {"full_name": "noah-be/overte"},
            "head_repository": {"full_name": "noah-be/overte"},
            "run_attempt": 2,
            "status": "completed",
            "conclusion": "success",
        }

    def tearDown(self):
        self.temporary.cleanup()

    def artifact(self, role: str) -> dict:
        return {
            "id": 50 if role == "overte" else 51,
            "name": f"ios-fedora-e2e-{role}-123-2",
            "expired": False,
            "digest": "sha256:" + "b" * 64,
            "archive_download_url": f"https://api.github.com/artifacts/{role}",
            "workflow_run": {
                "id": 123,
                "head_branch": "apple-ios",
                "head_sha": self.revision,
            },
        }

    def workflow_zip(self, role: str, *, unsafe: bool = False) -> Path:
        archive = self.root / f"{role}.zip"
        if role == "overte":
            ipa = "0042-OverteIOSClient-Release-device-signed.ipa"
        else:
            ipa = "WebDriverAgentRunner-Runner-16.8.0-signed.ipa"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("../escape.ipa" if unsafe else ipa, b"ipa")
            output.writestr(ipa.removesuffix(".ipa") + ".manifest.json", b"{}")
        return archive

    def encrypted_artifact_zip(self, role: str, inner: bytes) -> bytes:
        output = io.BytesIO()
        metadata = self.artifact(role)
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr(metadata["name"] + ".zip.age", inner)
        return output.getvalue()

    def test_dispatch_uses_versioned_api_and_returns_exact_run(self):
        opener = Opener([{"workflow_run_id": 8675309}])
        api = SYNC.GitHubApi("noah-be/overte", "private-token", opener=opener)
        self.assertEqual(8675309, api.dispatch({"qt_host_cache_key": "host"}))
        request = opener.requests[0][0]
        self.assertEqual("POST", request.method)
        self.assertEqual(SYNC.API_VERSION, request.get_header("X-github-api-version"))
        self.assertEqual("Bearer private-token", request.get_header("Authorization"))
        body = json.loads(request.data)
        self.assertEqual("apple-ios", body["ref"])

    def test_dispatch_input_contract_rejects_shell_or_namespace_drift(self):
        arguments = mock.Mock(
            qt_host_cache_key="overte-qt-host-v2-macos26-contract-" + "a" * 64,
            qt_ios_cache_key="overte-qt-ios-v2-ios26-contract-" + "b" * 64,
            qt_host_artifact_prefix="overte-qt-host-checkpoint-v1-" + "c" * 32,
            qt_ios_artifact_prefix="overte-qt-ios-checkpoint-v1-" + "d" * 32,
            overte_bundle_id="org.overte.interface.e2e",
            wda_bundle_id="org.overte.WebDriverAgentRunner",
        )
        self.assertEqual(6, len(SYNC.dispatch_inputs(arguments)))
        arguments.qt_host_cache_key = "safe; touch /tmp/injected"
        with self.assertRaises(SYNC.HandoffError):
            SYNC.dispatch_inputs(arguments)

    def test_api_error_does_not_disclose_token_or_body(self):
        error = urllib.error.HTTPError(
            "https://api.github.com/private-token", 403, "private-token", {}, io.BytesIO(b"private-token")
        )
        api = SYNC.GitHubApi("noah-be/overte", "private-token", opener=Opener([error]))
        with self.assertRaises(SYNC.HandoffError) as raised:
            api.run(1)
        self.assertNotIn("private-token", str(raised.exception))

    def test_run_and_artifacts_are_bound_to_protected_producer(self):
        verified = SYNC.verify_run(self.run, 123, require_complete=True)
        selected = SYNC.select_artifacts(
            [self.artifact("overte"), self.artifact("wda")], verified
        )
        self.assertEqual(50, selected["overte"]["id"])
        changed = dict(self.run, head_branch="feature")
        with self.assertRaises(SYNC.HandoffError):
            SYNC.verify_run(changed, 123, require_complete=True)
        duplicate = [self.artifact("overte"), self.artifact("overte"), self.artifact("wda")]
        with self.assertRaises(SYNC.HandoffError):
            SYNC.select_artifacts(duplicate, verified)

    def test_safe_extract_accepts_only_expected_root_pair(self):
        destination = self.root / "private" / "overte"
        ipa, manifest = SYNC.safe_extract(self.workflow_zip("overte"), destination, "overte")
        self.assertEqual("0042-OverteIOSClient-Release-device-signed.ipa", ipa.name)
        self.assertEqual(0o600, manifest.stat().st_mode & 0o777)
        with self.assertRaises(SYNC.HandoffError):
            SYNC.safe_extract(self.workflow_zip("wda", unsafe=True), self.root / "unsafe", "wda")
        self.assertFalse((self.root / "escape.ipa").exists())

    def test_outer_artifact_exposes_only_exact_encrypted_payload(self):
        role = "overte"
        archive = self.root / "outer.zip"
        archive.write_bytes(self.encrypted_artifact_zip(role, b"encrypted"))
        expected = self.artifact(role)["name"] + ".zip.age"
        extracted = SYNC.extract_encrypted_payload(archive, self.root, expected, role)
        self.assertEqual(b"encrypted", extracted.read_bytes())
        wrong = self.root / "wrong.zip"
        with zipfile.ZipFile(wrong, "w") as output:
            output.writestr("signed-cleartext.ipa", b"private")
        with self.assertRaises(SYNC.HandoffError):
            SYNC.extract_encrypted_payload(wrong, self.root, expected, role)

    def test_activate_updates_only_artifact_identity_fields(self):
        config_path = self.root / "targets.json"
        config = {
            "schemaVersion": 1,
            "targets": [{
                "selector": "private-selector",
                "platform": "ios",
                "enabled": True,
                "appId": "old.app",
                "artifactReceipt": "/old/receipt",
                "capabilities": {
                    "appium:udid": "private-device-id",
                    "appium:platformVersion": "26.2.1",
                },
            }],
        }
        SYNC.secure_json(config_path, config)
        receipt_path = self.root / "receipt.json"
        SYNC.secure_json(receipt_path, {
            "overte": {
                "bundleId": "org.overte.interface.e2e",
                "path": "/private/Overte.ipa",
            },
            "wda": {
                "bundleId": "org.overte.WebDriverAgentRunner.xctrunner",
                "path": "/private/WDA.ipa",
            },
        })
        SYNC.activate_target(config_path.resolve(), "private-selector", receipt_path)
        target = json.loads(config_path.read_text(encoding="utf-8"))["targets"][0]
        self.assertEqual("private-device-id", target["capabilities"]["appium:udid"])
        self.assertTrue(target["enabled"])
        self.assertEqual("org.overte.interface.e2e", target["appId"])
        self.assertEqual(
            "org.overte.WebDriverAgentRunner",
            target["capabilities"]["appium:updatedWDABundleId"],
        )
        self.assertEqual(0o600, config_path.stat().st_mode & 0o777)

    def test_receipt_revision_must_equal_protected_run_revision(self):
        receipt = self.root / "receipt.json"
        SYNC.secure_json(receipt, {"sourceRevision": "b" * 40})
        with self.assertRaisesRegex(SYNC.HandoffError, "protected workflow run"):
            SYNC.require_receipt_revision(receipt, self.revision)

    @unittest.skipIf(__import__("os").name == "nt", "symlink semantics differ on Windows")
    def test_symlinked_private_target_file_is_rejected(self):
        target = self.root / "real-targets.json"
        target.write_text("{}", encoding="utf-8")
        link = self.root / "linked-targets.json"
        link.symlink_to(target)
        receipt = self.root / "receipt.json"
        receipt.write_text("{}", encoding="utf-8")
        with self.assertRaises(SYNC.HandoffError):
            SYNC.activate_target(link, "private-selector", receipt)

    def test_failed_final_binding_removes_owned_run_directory(self):
        arguments = mock.Mock(
            repository="noah-be/overte",
            destination=self.root / "handoff",
            run_id=123,
            timeout_seconds=1,
            poll_seconds=1,
            target_config=None,
            target_selector="",
        )
        fake_api = mock.Mock()
        fake_api.run.return_value = self.run
        inners = {role: self.workflow_zip(role).read_bytes() for role in ("overte", "wda")}
        archives = {
            role: self.encrypted_artifact_zip(role, inners[role])
            for role in ("overte", "wda")
        }
        metadata = [self.artifact("overte"), self.artifact("wda")]
        for item, role in zip(metadata, ("overte", "wda")):
            item["digest"] = "sha256:" + hashlib.sha256(archives[role]).hexdigest()
        fake_api.artifacts.return_value = metadata

        def download(url: str, destination: Path):
            role = "overte" if url.endswith("overte") else "wda"
            destination.write_bytes(archives[role])

        fake_api.download.side_effect = download
        identity = self.root / "identity.txt"
        identity.write_text("AGE-SECRET-KEY-test", encoding="utf-8")
        identity.chmod(0o600)

        def decrypt(_age, _identity, encrypted: Path, destination: Path):
            destination.write_bytes(encrypted.read_bytes())

        # Avoid exercising the IPA verifier here; force the first binding to fail.
        with mock.patch.object(SYNC, "GitHubApi", return_value=fake_api), \
                mock.patch.object(SYNC, "install_security_tools", return_value={
                    "age": self.root / "age", "rcodesign": self.root / "rcodesign"
                }), \
                mock.patch.object(SYNC, "decrypt_payload", side_effect=decrypt), \
                mock.patch.object(SYNC.subprocess, "run", return_value=mock.Mock(returncode=2)):
            with mock.patch.dict(SYNC.os.environ, {
                "OVERTE_GITHUB_TOKEN": "token",
                "OVERTE_IOS_AGE_IDENTITY_FILE": str(identity),
            }):
                with self.assertRaises(SYNC.HandoffError):
                    SYNC.run(arguments)
        self.assertEqual([], list((self.root / "handoff").glob("run-*")))


if __name__ == "__main__":
    unittest.main()
