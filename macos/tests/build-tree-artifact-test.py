#!/usr/bin/env python3
"""Hermetic tests for durable resumable macOS build-tree artifacts."""

from __future__ import annotations

import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "macos/ci/build-tree-artifact.py"
SPEC = importlib.util.spec_from_file_location("build_tree_artifact", TOOL)
assert SPEC and SPEC.loader
artifact = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(artifact)
KEY = "macos-build-tree-v3-x86_64-tool"
COMPLETE = f"{KEY}-complete-source"
REPOSITORY_ID = "123456"
BRANCH = "apple-macos"


class BuildTreeArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repository"
        self.build = self.root / "build"
        objects = self.build / "objects"
        objects.mkdir(parents=True)
        (self.build / "CMakeCache.txt").write_text("cache\n", encoding="utf-8")
        (self.build / "build.ninja").write_text("ninja\n", encoding="utf-8")
        (self.build / ".overte-ninja-checkpoint.json").write_text(
            json.dumps({"schema": 2}), encoding="utf-8"
        )
        (self.build / ".overte-macos-complete-key").write_text(
            f"{COMPLETE}\n", encoding="utf-8"
        )
        executable = objects / "client.o"
        executable.write_bytes(b"resumable-object")
        executable.chmod(0o750)
        os.symlink("client.o", objects / "latest.o")
        app = self.build / "interface" / "Overte.app" / "Contents" / "MacOS"
        app.mkdir(parents=True)
        (app / "Overte").write_bytes(b"reproducible-app")
        application_archive = self.build / "application-archive"
        application_archive.mkdir()
        (application_archive / "Overte.app.tar").write_bytes(b"duplicate-app")
        self.checkpoint = Path(self.temporary.name) / "checkpoint"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def tool(self, operation: str, *extra: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(TOOL), operation, *extra],
            check=check,
            capture_output=True,
            text=True,
        )

    def common(self) -> tuple[str, ...]:
        return (
            "--key", KEY,
            "--repository-id", REPOSITORY_ID,
            "--branch", BRANCH,
        )

    def create(self, *, complete_key: str = COMPLETE, check: bool = True):
        return self.tool(
            "create",
            "--root", str(self.root),
            "--output-dir", str(self.checkpoint),
            "--complete-key", complete_key,
            *self.common(),
            check=check,
        )

    def test_round_trip_preserves_resume_state_and_omits_reproducible_products(self) -> None:
        created = self.create()
        self.assertIn("build-tree-artifact phase=create status=complete", created.stdout)
        manifest = json.loads((self.checkpoint / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["kind"], "overte-macos-build-tree-checkpoint")
        self.assertEqual(manifest["roots"], ["build"])

        self.tool(
            "verify",
            "--checkpoint-dir", str(self.checkpoint),
            "--complete-key", COMPLETE,
            *self.common(),
        )
        (self.build / "objects" / "client.o").write_bytes(b"damaged")
        restored = self.tool(
            "restore",
            "--checkpoint-dir", str(self.checkpoint),
            "--root", str(self.root),
            *self.common(),
        )
        self.assertIn("build-tree-artifact phase=restore status=complete", restored.stdout)
        object_file = self.build / "objects" / "client.o"
        self.assertEqual(object_file.read_bytes(), b"resumable-object")
        self.assertEqual(object_file.stat().st_mode & 0o777, 0o750)
        self.assertTrue((self.build / "objects" / "latest.o").is_symlink())
        self.assertFalse((self.build / "interface" / "Overte.app").exists())
        self.assertFalse((self.build / "application-archive").exists())

    def test_create_rejects_a_tree_not_marked_as_the_requested_generation(self) -> None:
        result = self.create(complete_key=f"{COMPLETE}-other", check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("not the requested complete generation", result.stderr)
        self.assertFalse(self.checkpoint.exists())

    def test_artifact_pruning_retains_active_and_one_previous_generation(self) -> None:
        candidates = [{"id": 90}, {"id": 100}, {"id": 80}]
        self.assertEqual(artifact.artifact_prune_plan(candidates, 100, 1), [80])
        with self.assertRaises(artifact.core.CheckpointError):
            artifact.artifact_prune_plan(candidates, 70, 1)

    def test_artifact_deletion_uses_the_authenticated_safe_opener(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value.status = 204
        opener = mock.MagicMock()
        opener.open.return_value = response
        with mock.patch.object(artifact.core, "build_opener", return_value=opener):
            artifact.delete_artifact(
                "owner/repository", 42, "secret-token", "https://api.github.test"
            )
        request = opener.open.call_args.args[0]
        self.assertEqual(request.method, "DELETE")
        self.assertTrue(request.full_url.endswith("/actions/artifacts/42"))


if __name__ == "__main__":
    unittest.main()
