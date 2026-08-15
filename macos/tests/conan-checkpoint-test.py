#!/usr/bin/env python3
"""Hermetic tests for durable macOS Conan checkpoints."""

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock
import zipfile


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "macos/ci/conan-checkpoint.py"
SPEC = importlib.util.spec_from_file_location("conan_checkpoint", TOOL)
assert SPEC is not None and SPEC.loader is not None
checkpoint = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checkpoint)


class ConanCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        (self.source / "p/pkg/package/id/lib").mkdir(parents=True)
        (self.source / "p/pkg/package/id/lib/library.dylib").write_bytes(b"binary")
        (self.source / "p/pkg/package/id/bin").mkdir()
        executable = self.source / "p/pkg/package/id/bin/tool"
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        executable.chmod(0o755)
        os.symlink("../lib/library.dylib", self.source / "p/pkg/package/id/bin/library")
        (self.source / "sources/archive").mkdir(parents=True)
        (self.source / "sources/archive/source.txt").write_text(
            "source\n", encoding="utf-8"
        )
        self.output = self.root / "checkpoint"
        self.key = "macos-conan-checkpoint-v1-test"
        self.repository_id = 12345
        self.branch = "apple-macos"

    def tearDown(self):
        self.temporary.cleanup()

    def create(self):
        return checkpoint.create_checkpoint(
            self.source,
            self.output,
            self.key,
            self.repository_id,
            self.branch,
            heartbeat_interval=60,
            archive_chunk_bytes=4096,
        )

    def test_discard_partial_cache_removes_only_managed_roots(self):
        conan_home = self.root / "partial-home"
        (conan_home / "p/incomplete").mkdir(parents=True)
        (conan_home / "sources/incomplete").mkdir(parents=True)
        (conan_home / "profiles").mkdir()
        keep = conan_home / "profiles/default"
        keep.write_text("keep\n", encoding="utf-8")
        outside = self.root / "outside"
        outside.mkdir()
        sentinel = outside / "sentinel"
        sentinel.write_text("keep\n", encoding="utf-8")
        os.symlink(outside, conan_home / "p/external")

        checkpoint.discard_partial_cache(conan_home)

        self.assertFalse((conan_home / "p").exists())
        self.assertFalse((conan_home / "sources").exists())
        self.assertEqual(keep.read_text(encoding="utf-8"), "keep\n")
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")

    def test_discard_partial_cache_refuses_a_filesystem_root(self):
        with self.assertRaisesRegex(checkpoint.CheckpointError, "filesystem root"):
            checkpoint.discard_partial_cache(Path(Path.cwd().anchor))

    def test_round_trip_preserves_files_modes_and_safe_links(self):
        manifest = self.create()
        self.assertEqual(manifest["schema"], checkpoint.SCHEMA)
        self.assertEqual(manifest["key"], self.key)
        chunks = manifest["archive"]["chunks"]
        self.assertGreater(len(chunks), 1)
        self.assertEqual(
            manifest["archive"]["bytes"],
            sum((self.output / item["name"]).stat().st_size for item in chunks),
        )
        aggregate = hashlib.sha256()
        for item in chunks:
            data = (self.output / item["name"]).read_bytes()
            self.assertLessEqual(len(data), 4096)
            self.assertEqual(item["sha256"], hashlib.sha256(data).hexdigest())
            aggregate.update(data)
        self.assertEqual(manifest["archive"]["sha256"], aggregate.hexdigest())

        restored = self.root / "restored"
        (restored / "p/old").mkdir(parents=True)
        (restored / "p/old/stale").write_text("stale", encoding="utf-8")
        checkpoint.restore_checkpoint(
            self.output,
            restored,
            self.key,
            self.repository_id,
            self.branch,
            heartbeat_interval=0.01,
        )

        self.assertFalse((restored / "p/old").exists())
        self.assertEqual(
            (restored / "p/pkg/package/id/lib/library.dylib").read_bytes(), b"binary"
        )
        self.assertTrue(os.access(restored / "p/pkg/package/id/bin/tool", os.X_OK))
        link = restored / "p/pkg/package/id/bin/library"
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), "../lib/library.dylib")
        self.assertEqual(
            (restored / "sources/archive/source.txt").read_text(encoding="utf-8"),
            "source\n",
        )

    def test_wrong_key_and_corrupt_archive_fail_before_mutating_destination(self):
        self.create()
        destination = self.root / "destination"
        (destination / "p").mkdir(parents=True)
        sentinel = destination / "p/sentinel"
        sentinel.write_text("keep", encoding="utf-8")

        with self.assertRaisesRegex(checkpoint.CheckpointError, "key mismatch"):
            checkpoint.restore_checkpoint(
                self.output,
                destination,
                "different-key",
                self.repository_id,
                self.branch,
                heartbeat_interval=0.01,
            )
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

        manifest = json.loads(
            (self.output / checkpoint.MANIFEST_NAME).read_text(encoding="utf-8")
        )
        first_chunk = self.output / manifest["archive"]["chunks"][0]["name"]
        data = bytearray(first_chunk.read_bytes())
        data[0] ^= 0xFF
        first_chunk.write_bytes(data)
        with self.assertRaisesRegex(checkpoint.CheckpointError, "chunk digest mismatch"):
            checkpoint.restore_checkpoint(
                self.output,
                destination,
                self.key,
                self.repository_id,
                self.branch,
                heartbeat_interval=0.01,
            )
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_missing_chunk_fails_before_mutating_destination(self):
        manifest = self.create()
        missing = self.output / manifest["archive"]["chunks"][-1]["name"]
        missing.unlink()
        destination = self.root / "destination-missing"
        (destination / "p").mkdir(parents=True)
        sentinel = destination / "p/sentinel"
        sentinel.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(checkpoint.CheckpointError, "chunk is missing"):
            checkpoint.restore_checkpoint(
                self.output,
                destination,
                self.key,
                self.repository_id,
                self.branch,
                heartbeat_interval=0.01,
            )
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def unsafe_checkpoint(self, member: tarfile.TarInfo, data: bytes = b"") -> Path:
        output = self.root / f"unsafe-{len(list(self.root.glob('unsafe-*')))}"
        output.mkdir()
        archive_path = output / ".unsafe.tar"
        with tarfile.open(archive_path, "w") as archive:
            for root_name in checkpoint.ROOTS:
                root = tarfile.TarInfo(root_name)
                root.type = tarfile.DIRTYPE
                root.mode = 0o755
                archive.addfile(root)
            archive.addfile(member, io.BytesIO(data) if member.isfile() else None)
        with tarfile.open(archive_path, "r:") as archive:
            members = archive.getmembers()
        data = archive_path.read_bytes()
        chunk_name = checkpoint._chunk_name(0)
        (output / chunk_name).write_bytes(data)
        archive_path.unlink()
        payload = {
            "schema": checkpoint.SCHEMA,
            "kind": checkpoint.KIND,
            "key": self.key,
            "provenance": {
                "repository_id": self.repository_id,
                "head_repository_id": self.repository_id,
                "head_branch": self.branch,
            },
            "created_utc": "2026-01-01T00:00:00+00:00",
            "roots": list(checkpoint.ROOTS),
            "archive": {
                "format": checkpoint.ARCHIVE_FORMAT,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "chunk_bytes": checkpoint.DEFAULT_ARCHIVE_CHUNK_BYTES,
                "chunks": [
                    {
                        "name": chunk_name,
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                ],
                "entries": len(members),
                "logical_bytes": sum(item.size for item in members if item.isfile()),
            },
        }
        (output / checkpoint.MANIFEST_NAME).write_text(
            json.dumps(payload), encoding="utf-8"
        )
        return output

    def test_traversal_and_escaping_symlinks_are_rejected(self):
        traversal = tarfile.TarInfo("p/../../escape")
        traversal.size = 1
        with self.assertRaisesRegex(checkpoint.CheckpointError, "unsafe member"):
            checkpoint.validate_checkpoint(
                self.unsafe_checkpoint(traversal, b"x"),
                self.key,
                self.repository_id,
                self.branch,
            )

        symlink = tarfile.TarInfo("p/pkg/escape")
        symlink.type = tarfile.SYMTYPE
        symlink.linkname = "../../../outside"
        with self.assertRaisesRegex(checkpoint.CheckpointError, "escapes"):
            checkpoint.validate_checkpoint(
                self.unsafe_checkpoint(symlink),
                self.key,
                self.repository_id,
                self.branch,
            )

    def test_latest_nonexpired_compatible_artifact_is_selected(self):
        provenance = {
            "repository_id": self.repository_id,
            "head_repository_id": self.repository_id,
            "head_branch": self.branch,
        }
        payload = {
            "artifacts": [
                {"id": 4, "name": self.key, "expired": False, "size_in_bytes": 100, "workflow_run": provenance},
                {"id": 7, "name": self.key, "expired": False, "size_in_bytes": 200, "workflow_run": provenance},
                {"id": 9, "name": self.key, "expired": True, "size_in_bytes": 200, "workflow_run": provenance},
                {"id": 8, "name": "different", "expired": False, "size_in_bytes": 200, "workflow_run": provenance},
                {"id": 10, "name": self.key, "expired": False, "size_in_bytes": 200, "workflow_run": {**provenance, "head_branch": "untrusted"}},
            ]
        }
        selected = checkpoint.select_candidates(
            payload, self.key, self.repository_id, self.branch
        )
        self.assertEqual([item["id"] for item in selected], [7, 4])

    def artifact_zip(self, checkpoint_dir: Path, destination: Path) -> None:
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.write(checkpoint_dir / checkpoint.MANIFEST_NAME, checkpoint.MANIFEST_NAME)
            manifest = json.loads(
                (checkpoint_dir / checkpoint.MANIFEST_NAME).read_text(encoding="utf-8")
            )
            for chunk in manifest["archive"]["chunks"]:
                archive.write(checkpoint_dir / chunk["name"], chunk["name"])

    def test_remote_restore_rejects_newest_corrupt_candidate_then_uses_older(self):
        self.create()
        good_zip = self.root / "good.zip"
        self.artifact_zip(self.output, good_zip)
        bad_zip = self.root / "bad.zip"
        bad_zip.write_bytes(b"not a zip")
        destination = self.root / "remote-restored"
        github_output = self.root / "github-output"

        candidates = [
            {"id": 20, "name": self.key, "expired": False, "size_in_bytes": 9},
            {"id": 10, "name": self.key, "expired": False, "size_in_bytes": 10},
        ]

        def download(_repository, artifact_id, _token, _api_base, target, _maximum):
            target.write_bytes((bad_zip if artifact_id == 20 else good_zip).read_bytes())

        with mock.patch.object(checkpoint, "list_candidates", return_value=candidates), mock.patch.object(
            checkpoint, "_download_artifact", side_effect=download
        ):
            restored = checkpoint.restore_latest_remote(
                "owner/repository",
                self.key,
                "secret-token",
                "https://example.invalid",
                self.key,
                self.repository_id,
                self.branch,
                destination,
                github_output,
                heartbeat_interval=0.01,
            )
        self.assertTrue(restored)
        self.assertIn("restored=true", github_output.read_text(encoding="utf-8"))
        self.assertIn("artifact_id=10", github_output.read_text(encoding="utf-8"))
        self.assertTrue((destination / "p/pkg/package/id/lib/library.dylib").is_file())

    def test_failed_remote_restore_does_not_expose_token_or_modify_cache(self):
        destination = self.root / "remote-failed"
        (destination / "p").mkdir(parents=True)
        sentinel = destination / "p/sentinel"
        sentinel.write_text("keep", encoding="utf-8")
        github_output = self.root / "github-output-failed"
        candidate = {
            "id": 3,
            "name": self.key,
            "expired": False,
            "size_in_bytes": 8,
        }

        def corrupt(_repository, _id, token, _api_base, target, _maximum):
            self.assertEqual(token, "very-secret-token")
            target.write_bytes(b"invalid")

        with mock.patch.object(checkpoint, "list_candidates", return_value=[candidate]), mock.patch.object(
            checkpoint, "_download_artifact", side_effect=corrupt
        ), mock.patch("sys.stdout", new_callable=io.StringIO) as stdout, mock.patch(
            "sys.stderr", new_callable=io.StringIO
        ) as stderr:
            restored = checkpoint.restore_latest_remote(
                "owner/repository",
                self.key,
                "very-secret-token",
                "https://example.invalid",
                self.key,
                self.repository_id,
                self.branch,
                destination,
                github_output,
                heartbeat_interval=0.01,
            )
        self.assertFalse(restored)
        combined = stdout.getvalue() + stderr.getvalue()
        self.assertNotIn("very-secret-token", combined)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
        self.assertIn("restored=false", github_output.read_text(encoding="utf-8"))

    def test_uploaded_artifact_metadata_and_digest_are_verified(self):
        digest = "a" * 64
        payload = {
            "id": 42,
            "name": self.key,
            "expired": False,
            "size_in_bytes": 123,
            "digest": f"sha256:{digest}",
            "workflow_run": {
                "repository_id": self.repository_id,
                "head_repository_id": self.repository_id,
                "head_branch": self.branch,
            },
        }
        with mock.patch.object(
            checkpoint, "_api_json", return_value=payload
        ), mock.patch.object(checkpoint, "verify_remote_contents") as contents:
            checkpoint.verify_remote(
                "owner/repository",
                42,
                self.key,
                digest,
                self.key,
                self.repository_id,
                self.branch,
                "secret",
                "https://example.invalid",
                attempts=1,
            )
        contents.assert_called_once()
        payload["digest"] = "sha256:" + "b" * 64
        with mock.patch.object(checkpoint, "_api_json", return_value=payload), self.assertRaisesRegex(
            checkpoint.RemoteError, "digest validation"
        ):
            checkpoint.verify_remote(
                "owner/repository",
                42,
                self.key,
                digest,
                self.key,
                self.repository_id,
                self.branch,
                "secret",
                "https://example.invalid",
                attempts=1,
            )

    def test_uploaded_artifact_verification_retries_eventual_api_visibility(self):
        digest = "c" * 64
        payload = {
            "id": 51,
            "name": self.key,
            "expired": False,
            "size_in_bytes": 456,
            "digest": f"sha256:{digest}",
            "workflow_run": {
                "repository_id": self.repository_id,
                "head_repository_id": self.repository_id,
                "head_branch": self.branch,
            },
        }
        with mock.patch.object(
            checkpoint,
            "_api_json",
            side_effect=[checkpoint.RemoteError("not visible yet"), payload],
        ) as request, mock.patch.object(checkpoint, "verify_remote_contents"):
            checkpoint.verify_remote(
                "owner/repository",
                51,
                self.key,
                digest,
                self.key,
                self.repository_id,
                self.branch,
                "secret",
                "https://example.invalid",
                attempts=2,
                retry_interval=0,
            )
        self.assertEqual(request.call_count, 2)

    def test_post_upload_verification_downloads_and_parses_exact_artifact(self):
        self.create()
        artifact_zip = self.root / "uploaded.zip"
        self.artifact_zip(self.output, artifact_zip)

        def download(_repository, artifact_id, token, _api_base, target, _maximum):
            self.assertEqual(artifact_id, 61)
            self.assertEqual(token, "secret")
            target.write_bytes(artifact_zip.read_bytes())

        with mock.patch.object(checkpoint, "_download_artifact", side_effect=download):
            checkpoint.verify_remote_contents(
                "owner/repository",
                61,
                "secret",
                "https://example.invalid",
                self.key,
                self.repository_id,
                self.branch,
            )


if __name__ == "__main__":
    unittest.main()
