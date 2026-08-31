#!/usr/bin/env python3
"""Device-free tests for the E2E toolchain lock and artifact verifier."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import sys


DEVICE_ROOT = Path(__file__).resolve().parents[1]
if str(DEVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(DEVICE_ROOT))

from validate_toolchain_lock import (  # noqa: E402
    DEFAULT_LOCK,
    LockValidationError,
    main,
    validate_lock,
)


class ToolchainLockTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-toolchain-lock-")
        self.root = Path(self.temporary.name)
        (self.root / "jenkins").mkdir()
        self.data = json.loads(DEFAULT_LOCK.read_text(encoding="utf-8"))
        source_plugins = DEVICE_ROOT / "jenkins" / "plugins.lock.txt"
        (self.root / "jenkins" / "plugins.lock.txt").write_text(
            source_plugins.read_text(encoding="utf-8"), encoding="utf-8"
        )
        source_artifacts = DEVICE_ROOT / "jenkins" / "plugins.artifacts.lock.json"
        (self.root / "jenkins" / "plugins.artifacts.lock.json").write_text(
            source_artifacts.read_text(encoding="utf-8"), encoding="utf-8"
        )

    def tearDown(self):
        self.temporary.cleanup()

    def write_lock(self, data: dict | None = None) -> Path:
        lock = self.root / "toolchain.lock.json"
        lock.write_text(json.dumps(data or self.data, indent=2) + "\n", encoding="utf-8")
        return lock

    def validate_copy(self, data: dict | None = None):
        return validate_lock(
            self.write_lock(data),
            direct_plugins_path=DEVICE_ROOT / "jenkins" / "plugins.txt",
        )

    def test_repository_lock_is_valid_and_complete(self):
        artifacts = validate_lock()
        self.assertEqual(81, len(artifacts))
        self.assertIn("jenkins.plugins.configuration-as-code", artifacts)
        self.assertIn("jenkins.plugins.git", artifacts)
        self.assertIn("appium.iosRuntime.remoteXpc", artifacts)
        self.assertIn("appium.iosRuntime.webdriverAgent", artifacts)
        self.assertIn("appium.iosSecurity.age", artifacts)
        self.assertIn("appium.iosSecurity.rcodesign", artifacts)

    def test_rejects_appium_peer_major_drift(self):
        changed = copy.deepcopy(self.data)
        changed["appium"]["drivers"]["uiautomator2"]["appiumPeerRange"] = "^4.0.0"
        with self.assertRaisesRegex(LockValidationError, "rejects the pinned core"):
            self.validate_copy(changed)

    def test_rejects_xcuitest_remote_runtime_drift(self):
        for field, runtime in (
            ("remoteXpcRange", "remoteXpc"),
            ("webdriverAgentRange", "webdriverAgent"),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.data)
                changed["appium"]["drivers"]["xcuitest"][field] = "^999.0.0"
                with self.assertRaisesRegex(
                    LockValidationError, "rejects the pinned iOS runtime"
                ):
                    self.validate_copy(changed)

    def test_rejects_runtime_outside_npm_engine_range(self):
        changed = copy.deepcopy(self.data)
        changed["appium"]["runtime"]["node"] = "18.20.0"
        with self.assertRaisesRegex(LockValidationError, "does not satisfy appium.nodeRange"):
            self.validate_copy(changed)

    def test_rejects_non_https_and_placeholder_hashes(self):
        changed = copy.deepcopy(self.data)
        artifact = changed["appium"]["core"]["artifact"]
        artifact["url"] = "http://example.invalid/appium.tgz"
        artifact["sha256"] = "0" * 64
        with self.assertRaises(LockValidationError) as raised:
            self.validate_copy(changed)
        self.assertIn("must be an HTTPS URL", str(raised.exception))
        self.assertIn("must not be a placeholder digest", str(raised.exception))

    def test_rejects_resolved_plugin_drift(self):
        plugin_lock = self.root / "jenkins" / "plugins.lock.txt"
        contents = plugin_lock.read_text(encoding="utf-8")
        plugin_lock.write_text(
            contents.replace("git:5.10.1", "git:5.10.0"), encoding="utf-8"
        )
        with self.assertRaisesRegex(LockValidationError, "does not pin git:5.10.1"):
            self.validate_copy()

    def test_rejects_plugin_artifact_metadata_drift(self):
        artifact_lock = self.root / "jenkins" / "plugins.artifacts.lock.json"
        document = json.loads(artifact_lock.read_text(encoding="utf-8"))
        git = next(row for row in document["plugins"] if row["id"] == "git")
        git["sha256"] = "1" * 64
        artifact_lock.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(
            LockValidationError, "direct and resolved artifact metadata differs for git"
        ):
            self.validate_copy()

    def test_rejects_plugin_requiring_newer_jenkins_core(self):
        artifact_lock = self.root / "jenkins" / "plugins.artifacts.lock.json"
        document = json.loads(artifact_lock.read_text(encoding="utf-8"))
        document["plugins"][0]["requiredCore"] = "999.0.0"
        artifact_lock.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(LockValidationError, "requires Jenkins 999.0.0 newer"):
            self.validate_copy()

    def test_local_artifact_verification_passes_and_detects_tampering(self):
        payload = self.root / "artifact.tgz"
        payload.write_bytes(b"immutable test artifact")
        changed = copy.deepcopy(self.data)
        changed["appium"]["core"]["artifact"]["sha256"] = hashlib.sha256(
            payload.read_bytes()
        ).hexdigest()
        lock = self.write_lock(changed)
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            status = main(["--lock", str(lock), "--artifact", f"appium.core={payload}"])
        self.assertEqual(0, status, output.getvalue())

        payload.write_bytes(b"tampered")
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            status = main(["--lock", str(lock), "--artifact", f"appium.core={payload}"])
        self.assertEqual(1, status)
        self.assertIn("SHA-256 mismatch", output.getvalue())

    def test_schema_document_is_well_formed_json_schema(self):
        schema = json.loads(
            (DEVICE_ROOT / "schemas" / "toolchain-lock.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        self.assertEqual(1, schema["properties"]["schemaVersion"]["const"])
        plugin_schema = json.loads(
            (DEVICE_ROOT / "schemas" / "jenkins-plugin-artifacts-lock.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(1, plugin_schema["properties"]["schemaVersion"]["const"])


if __name__ == "__main__":
    unittest.main()
