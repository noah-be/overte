#!/usr/bin/env python3
"""Hermetic tests for branch-local macOS bootstrap cache retention."""

from __future__ import annotations

import importlib.util
import io
import os
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "macos/ci/bootstrap-cache-prune.py"
SPEC = importlib.util.spec_from_file_location("bootstrap_cache_prune", TOOL)
assert SPEC and SPEC.loader
prune = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prune)

REF = "refs/heads/apple-macos"
BUILD = "macos-build-tree-v3-x86_64-tool-complete-source"
CONAN = "macos-conan-v3-x86_64-tool-input"
SCCACHE = "macos-sccache-v4-x86_64-compiler-complete-source"


def item(cache_id: int, key: str, size: int = 100, ref: str = REF) -> dict[str, object]:
    return {"id": cache_id, "key": key, "ref": ref, "size_in_bytes": size}


class BootstrapCachePruneTests(unittest.TestCase):
    def inventory(self) -> list[dict[str, object]]:
        return [
            item(1, BUILD, 1000),
            item(2, CONAN, 2000),
            item(3, SCCACHE, 3000),
            item(4, "macos-build-tree-v2-x86_64-old-complete-old", 4000),
            item(5, "macos-build-tree-v3-x86_64-tool-configured-old", 5000),
            item(6, "macos-conan-v3-x86_64-old-stage-qt", 6000),
            item(7, "macos-sccache-v4-x86_64-old-partial-run", 7000),
            item(8, "sccache/object", 8000),
            item(9, "ios-client-build-tree-v1-arm64-current", 9000),
            item(10, "macos-build-tree-v3-arm64-other", 10_000),
            item(11, "macos-build-tree-v3-x86_64-other-ref", 11_000, "refs/heads/main"),
            item(12, "macos-conan-v2-x86_64-retired", 12_000),
            item(13, "macos-sccache-v3-x86_64-retired", 13_000),
        ]

    def test_plan_keeps_only_current_complete_macos_generations(self) -> None:
        delete, reclaimed = prune.prune_plan(
            self.inventory(), REF, "x86_64", BUILD, CONAN, SCCACHE
        )
        self.assertEqual(delete, [4, 5, 6, 7, 12, 13])
        self.assertEqual(reclaimed, 47_000)

    def test_missing_or_empty_active_cache_aborts_without_deletion(self) -> None:
        for missing_id in (1, 2, 3):
            inventory = [entry for entry in self.inventory() if entry["id"] != missing_id]
            with self.assertRaises(prune.PruneError):
                prune.prune_plan(inventory, REF, "x86_64", BUILD, CONAN, SCCACHE)
        inventory = self.inventory()
        inventory[0]["size_in_bytes"] = 0
        with self.assertRaises(prune.PruneError):
            prune.prune_plan(inventory, REF, "x86_64", BUILD, CONAN, SCCACHE)

    def test_invalid_or_duplicate_inventory_is_rejected(self) -> None:
        duplicate = self.inventory() + [item(1, "macos-build-tree-v2-x86_64-duplicate")]
        with self.assertRaises(prune.PruneError):
            prune.prune_plan(duplicate, REF, "x86_64", BUILD, CONAN, SCCACHE)
        malformed = self.inventory()
        malformed[0]["key"] = "unsafe\nkey"
        with self.assertRaises(prune.PruneError):
            prune.prune_plan(malformed, REF, "x86_64", BUILD, CONAN, SCCACHE)
        with self.assertRaises(prune.PruneError):
            prune.prune_plan(
                self.inventory(), REF, "x86_64",
                "macos-build-tree-v2-x86_64-old-complete-old", CONAN, SCCACHE,
            )
        with self.assertRaises(prune.PruneError):
            prune.prune_plan(
                self.inventory(), REF, "x86_64", BUILD,
                CONAN + "-stage-qt", SCCACHE,
            )
        with self.assertRaises(prune.PruneError):
            prune.prune_plan(
                self.inventory(), REF, "x86_64", BUILD, CONAN,
                "macos-sccache-v4-x86_64-compiler-partial-run",
            )

    def test_main_executes_only_the_validated_plan(self) -> None:
        argv = [
            str(TOOL), "--repository", "owner/repo", "--ref", REF,
            "--architecture", "x86_64", "--active-build", BUILD,
            "--active-conan", CONAN, "--active-sccache", SCCACHE,
            "--token-env", "TEST_TOKEN", "--settle-attempts", "1", "--execute",
        ]
        deleted: list[int] = []
        output = io.StringIO()
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.dict(os.environ, {"TEST_TOKEN": "secret-token"}, clear=False),
            mock.patch.object(prune, "list_caches", return_value=self.inventory()),
            mock.patch.object(
                prune, "delete_cache",
                side_effect=lambda _repo, cache_id, _token, _api: deleted.append(cache_id),
            ),
            mock.patch.object(sys, "stdout", output),
        ):
            self.assertEqual(prune.main(), 0)
        self.assertEqual(deleted, [4, 5, 6, 7, 12, 13])
        self.assertNotIn("secret-token", output.getvalue())
        self.assertNotIn(BUILD, output.getvalue())
        self.assertIn("entries=6 bytes=47000", output.getvalue())

    def test_main_never_deletes_when_inventory_cannot_prove_active_set(self) -> None:
        argv = [
            str(TOOL), "--repository", "owner/repo", "--ref", REF,
            "--architecture", "x86_64", "--active-build", BUILD,
            "--active-conan", CONAN, "--active-sccache", SCCACHE,
            "--token-env", "TEST_TOKEN", "--settle-attempts", "1", "--execute",
        ]
        incomplete = [entry for entry in self.inventory() if entry["id"] != 2]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.dict(os.environ, {"TEST_TOKEN": "secret-token"}, clear=False),
            mock.patch.object(prune, "list_caches", return_value=incomplete),
            mock.patch.object(prune, "delete_cache") as delete,
            mock.patch.object(sys, "stderr"),
        ):
            self.assertEqual(prune.main(), 1)
        delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
