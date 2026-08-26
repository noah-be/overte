#!/usr/bin/env python3
"""Device-free tests for authenticated GitHub-to-Fedora iOS synchronization."""

from __future__ import annotations

import importlib.util
import io
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import urllib.error
import warnings
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
            "path": ".github/workflows/ios-bootstrap.yml@apple-ios",
            "head_branch": "apple-ios",
            "head_sha": self.revision,
            "repository": {"full_name": "noah-be/overte", "id": 42},
            "head_repository": {"full_name": "noah-be/overte", "id": 42},
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
            "archive_download_url": (
                "https://api.github.com/repos/noah-be/overte/actions/artifacts/"
                f"{50 if role == 'overte' else 51}/zip"
            ),
            "workflow_run": {
                "id": 123,
                "repository_id": 42,
                "head_repository_id": 42,
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
        self.assertIs(True, body["return_run_details"])
        self.assertNotIn("latest", request.full_url)

    def test_dispatch_input_contract_rejects_shell_or_namespace_drift(self):
        arguments = mock.Mock(
            qt_host_cache_key="overte-qt-host-v2-macos26-contract-" + "a" * 64,
            qt_ios_cache_key="overte-qt-ios-v2-ios26-contract-" + "b" * 64,
            qt_host_artifact_prefix="overte-qt-host-checkpoint-v1-" + "c" * 32,
            qt_ios_artifact_prefix="overte-qt-ios-checkpoint-v1-" + "d" * 32,
            overte_bundle_id="org.overte.interface.e2e",
            wda_bundle_id="org.overte.WebDriverAgentRunner",
        )
        inputs = SYNC.dispatch_inputs(arguments)
        self.assertEqual(7, len(inputs))
        self.assertEqual("true", inputs["fedora_e2e_producer"])
        arguments.qt_host_cache_key = "safe; touch /tmp/injected"
        with self.assertRaises(SYNC.HandoffError):
            SYNC.dispatch_inputs(arguments)

    def test_api_error_does_not_disclose_token_or_body(self):
        error = urllib.error.HTTPError(
            "https://api.github.com/private-token", 403, "private-token", {}, io.BytesIO(b"private-token")
        )
        api = SYNC.GitHubApi("noah-be/overte", "private-token", opener=Opener([error]))
        try:
            with self.assertRaises(SYNC.HandoffError) as raised:
                api.run(1)
        finally:
            error.close()
        self.assertNotIn("private-token", str(raised.exception))

    def test_run_and_artifacts_are_bound_to_protected_producer(self):
        verified = SYNC.verify_run(
            self.run, 123, expected_attempt=2, require_complete=True
        )
        selected = SYNC.select_artifacts(
            [self.artifact("overte"), self.artifact("wda")], verified
        )
        self.assertEqual(50, selected["overte"]["id"])
        changed = dict(self.run, head_branch="feature")
        with self.assertRaises(SYNC.HandoffError):
            SYNC.verify_run(changed, 123, expected_attempt=2, require_complete=True)
        with self.assertRaises(SYNC.HandoffError):
            SYNC.verify_run(self.run, 123, expected_attempt=1, require_complete=True)
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

    def test_zip_duplicates_symlinks_compression_and_actual_overrun_are_rejected(self):
        role = "overte"
        expected = self.artifact(role)["name"] + ".zip.age"
        duplicate = self.root / "duplicate.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(duplicate, "w") as output:
                output.writestr(expected, b"one")
                output.writestr(expected, b"two")
        with self.assertRaises(SYNC.HandoffError):
            SYNC.extract_encrypted_payload(duplicate, self.root, expected, role)

        link = self.root / "link.zip"
        info = zipfile.ZipInfo(expected)
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        with zipfile.ZipFile(link, "w") as output:
            output.writestr(info, b"target")
        with self.assertRaises(SYNC.HandoffError):
            SYNC.extract_encrypted_payload(link, self.root, expected, role)

        compressed = self.root / "compressed.zip"
        with zipfile.ZipFile(compressed, "w", compression=zipfile.ZIP_DEFLATED) as output:
            output.writestr(expected, b"0" * 100_000)
        with self.assertRaisesRegex(SYNC.HandoffError, "unsafe"):
            SYNC.extract_encrypted_payload(compressed, self.root, expected, role)

        entry = mock.Mock(file_size=4, compress_size=4, compress_type=zipfile.ZIP_STORED)
        archive = mock.Mock()
        archive.open.return_value = io.BytesIO(b"12345")
        with self.assertRaisesRegex(SYNC.HandoffError, "exceeded"):
            SYNC.copy_zip_member(archive, entry, self.root / "overrun", 4, "fixture")
        self.assertFalse((self.root / "overrun").exists())

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
                "testBuild": {"scenePath": SYNC.SCENE_PATH},
                "capabilities": {
                    "appium:udid": "private-device-id",
                    "appium:platformVersion": "26.2.1",
                    "appium:autoLaunch": False,
                },
            }],
        }
        SYNC.secure_json(config_path, config)
        receipt_path = self.root / "receipt.json"
        SYNC.secure_json(receipt_path, {
            "schemaVersion": 1,
            "contract": "overte-ios-fedora-e2e-receipt-v1",
            "sourceRevision": self.revision,
            "createdAt": "2026-08-25T12:00:00Z",
            "notAfter": "2026-08-26T12:00:00Z",
            "provenance": {
                "repository": "noah-be/overte", "repositoryId": 42,
                "workflow": ".github/workflows/ios-bootstrap.yml",
                "reusableWorkflow": ".github/workflows/ios-fedora-e2e-producer.yml",
                "ref": "refs/heads/apple-ios", "runId": 123, "runAttempt": 2,
            },
            "overte": {
                "bundleId": "org.overte.interface.e2e",
                "path": "/private/Overte.ipa",
                "sha256": "1" * 64,
            },
            "wda": {
                "bundleId": "org.overte.WebDriverAgentRunner.xctrunner",
                "ipaPath": "/private/WDA.ipa",
                "ipaSha256": "2" * 64,
                "prebuiltPath": "/private/WebDriverAgentRunner-Runner.app",
                "prebuiltTreeSha256": "3" * 64,
            },
            "toolchain": {
                "xcuitestDriver": "12.8.0", "remoteXpc": "5.15.3",
                "webdriverAgent": "16.8.0",
            },
        })
        SYNC.activate_target(config_path.resolve(), "private-selector", receipt_path)
        target = json.loads(config_path.read_text(encoding="utf-8"))["targets"][0]
        self.assertEqual("private-device-id", target["capabilities"]["appium:udid"])
        self.assertTrue(target["enabled"])
        self.assertTrue(target["capabilities"]["appium:usePreinstalledWDA"])
        self.assertFalse(target["capabilities"]["appium:enforceAppInstall"])
        self.assertFalse(target["capabilities"]["appium:autoLaunch"])
        self.assertEqual("signed-ipa", target["artifactMode"])
        self.assertEqual(SYNC.SCENE_PATH, target["testBuild"]["scenePath"])
        self.assertEqual("org.overte.interface.e2e", target["appId"])
        self.assertEqual(
            "org.overte.WebDriverAgentRunner",
            target["capabilities"]["appium:updatedWDABundleId"],
        )
        self.assertEqual(
            "/private/WebDriverAgentRunner-Runner.app",
            target["capabilities"]["appium:prebuiltWDAPath"],
        )
        self.assertEqual(0o600, config_path.stat().st_mode & 0o777)

    def test_receipt_must_equal_protected_run_attempt(self):
        receipt = self.root / "receipt.json"
        SYNC.secure_json(receipt, {
            "sourceRevision": "b" * 40,
            "provenance": {},
        })
        with self.assertRaisesRegex(SYNC.HandoffError, "workflow attempt"):
            SYNC.require_receipt_binding(receipt, self.run)

    def test_preinstalled_mode_observes_device_without_ipa_paths(self):
        config_path = self.root / "preinstalled-targets.json"
        SYNC.secure_json(config_path, {
            "schemaVersion": 1,
            "targets": [{
                "selector": "private-selector", "platform": "ios", "enabled": False,
                "testBuild": {"scenePath": SYNC.SCENE_PATH},
                "capabilities": {
                    "appium:udid": "private-device-id",
                    "appium:platformVersion": "18.7",
                    "appium:app": "/stale/Overte.ipa",
                    "appium:prebuiltWDAPath": "/stale/WDA.ipa",
                    "appium:autoLaunch": False,
                },
            }],
        })
        now = datetime.now(timezone.utc).replace(microsecond=0)
        attestation = self.root / "personal-team-preinstalled-attestation.json"
        SYNC.secure_json(attestation, {
            "schemaVersion": 1,
            "contract": "overte-ios-personal-team-preinstalled-attestation-v1",
            "sourceRevision": self.revision,
            "unsignedKitManifestSha256": "3" * 64,
            "createdAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "notAfter": (now + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "expectedBundleIdentifiers": {
                "overte": "org.overte.interface.e2e",
                "wdaRunner": "org.overte.WebDriverAgentRunner.xctrunner",
                "wdaXCTest": "org.overte.WebDriverAgentRunner",
            },
            "toolchain": {
                "xcuitestDriver": "12.8.0", "remoteXpc": "5.15.3",
                "webdriverAgent": "16.8.0",
            },
            "humanAttestation": {
                "deviceObserved": True, "installedWithSideloadly": True,
                "fixedBundleIdentifiersConfirmed": True,
                "acceptedNoCryptographicByteBinding": True,
                "derivationBinding": "none-device-observed",
            },
            "signingObservation": None,
        })
        arguments = mock.Mock(
            attestation=attestation.resolve(), destination=(self.root / "runs"),
            target_config=config_path.resolve(), target_selector="private-selector",
            service_runtime=Path("/usr/local/lib/overte-ios-remotexpc/5.15.3-r4"),
        )
        with mock.patch.object(
                SYNC.subprocess, "run", return_value=mock.Mock(returncode=0)) as execute:
            self.assertEqual(0, SYNC.run_preinstalled(arguments))
            command = execute.call_args.args[0]
            self.assertNotIn("private-device-id", command)
            self.assertIn("private-device-id", execute.call_args.kwargs["input"].decode())

            arguments.service_runtime = self.root / "mutable-runtime"
            with self.assertRaisesRegex(SYNC.HandoffError, "exact pinned immutable"):
                SYNC.run_preinstalled(arguments)
            self.assertEqual(1, execute.call_count)
            arguments.service_runtime = SYNC.PINNED_SERVICE_RUNTIME

            linked_config = self.root / "linked-preinstalled-targets.json"
            linked_config.symlink_to(config_path)
            arguments.target_config = linked_config
            with self.assertRaisesRegex(SYNC.HandoffError, "target configuration is unsafe"):
                SYNC.run_preinstalled(arguments)
            self.assertEqual(1, execute.call_count)
        target = json.loads(config_path.read_text(encoding="utf-8"))["targets"][0]
        self.assertEqual("personal-team-preinstalled", target["artifactMode"])
        self.assertNotIn("appium:app", target["capabilities"])
        self.assertNotIn("appium:prebuiltWDAPath", target["capabilities"])
        self.assertFalse(target["capabilities"]["appium:enforceAppInstall"])
        receipt = json.loads(Path(target["artifactReceipt"]).read_text(encoding="utf-8"))
        self.assertEqual(SYNC.PREINSTALLED_RECEIPT, receipt["contract"])
        self.assertNotIn("path", receipt["overte"])
        self.assertFalse(receipt["provenance"]["cryptographicByteBinding"])

    def test_sensitive_destinations_and_targets_inside_checkout_are_rejected(self):
        arguments = mock.Mock(
            destination=SYNC.REPOSITORY_ROOT / "private-ios-output",
            target_config=None,
        )
        with self.assertRaisesRegex(SYNC.HandoffError, "safe non-root private"):
            SYNC.run_local_import(arguments)
        repository_config = SYNC.REPOSITORY_ROOT / "tests/device/capabilities.json"
        with self.assertRaisesRegex(SYNC.HandoffError, "absolute private"):
            SYNC.activate_target(repository_config, "private-selector", self.root / "receipt")

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
            run_attempt=2,
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
            role = "overte" if "/50/" in url else "wda"
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
