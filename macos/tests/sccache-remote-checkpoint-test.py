#!/usr/bin/env python3
"""Hermetic tests for the macOS per-object remote checkpoint."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "macos/ci/sccache-remote-checkpoint.py"
SPEC = importlib.util.spec_from_file_location("sccache_remote_checkpoint", TOOL)
assert SPEC is not None and SPEC.loader is not None
checkpoint = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checkpoint)


def stats(*, requests=1, writes=1, hits=0, failures=0, errors=0):
    return {
        "stats": {
            "requests_executed": requests,
            "cache_writes": writes,
            "cache_write_errors": errors,
            "cache_hits": {"counts": {"C/C++": hits}},
            "cache_misses": {"counts": {"C/C++": max(0, writes)}},
            "multi_level": [
                {
                    "name": "L0 (disk)",
                    "writes": writes,
                    "hits": 0,
                    "write_failures": 0,
                },
                {
                    "name": "L1 (gha)",
                    "writes": max(0, writes - failures),
                    "hits": hits,
                    "write_failures": failures,
                },
            ],
        }
    }


class RemoteSccacheCheckpointTests(unittest.TestCase):
    def test_probe_and_build_statistics_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "stats.json"
            path.write_text(json.dumps(stats()), encoding="utf-8")
            result = checkpoint.validate_stats(path, "probe")
            self.assertEqual(result["remote_writes"], 1)
            path.write_text(json.dumps(stats(writes=0, hits=1)), encoding="utf-8")
            self.assertEqual(checkpoint.validate_stats(path, "build")["remote_hits"], 1)
            path.write_text(json.dumps(stats(requests=0, writes=0)), encoding="utf-8")
            self.assertEqual(checkpoint.validate_stats(path, "phase")["requests"], 0)
            for invalid in (
                stats(requests=0), stats(errors=1), stats(failures=1),
                {"stats": {"requests_executed": 1, "multi_level": []}},
            ):
                path.write_text(json.dumps(invalid), encoding="utf-8")
                with self.assertRaises(checkpoint.CheckpointError):
                    checkpoint.validate_stats(path, "probe")

    def test_completed_phase_uses_lossless_disk_fallback_for_transient_gha_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "stats.json"
            payload = stats(requests=2737, writes=2624, hits=54, failures=7, errors=7)
            payload["stats"]["cache_misses"]["counts"]["C/C++"] = 2624
            payload["stats"]["multi_level"][1]["writes"] = 2313
            path.write_text(json.dumps(payload), encoding="utf-8")
            with mock.patch("builtins.print") as output:
                result = checkpoint.validate_stats(path, "phase")
            self.assertEqual(result["local_writes"], 2624)
            self.assertEqual(result["remote_failures"], 7)
            self.assertIn("status=degraded", output.call_args.args[0])

            payload["stats"]["multi_level"][0]["write_failures"] = 1
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(checkpoint.CheckpointError, "disk.*write failures"):
                checkpoint.validate_stats(path, "phase")

            payload["stats"]["multi_level"][0]["write_failures"] = 0
            payload["stats"]["multi_level"][0]["writes"] = 2600
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(checkpoint.CheckpointError, "all cacheable requests"):
                checkpoint.validate_stats(path, "phase")

    def test_completed_phase_survives_one_remote_write_failure_after_local_hits(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "stats.json"
            payload = stats(requests=188, writes=1, hits=187, failures=1, errors=1)
            payload["stats"]["multi_level"][1]["writes"] = 0
            path.write_text(json.dumps(payload), encoding="utf-8")
            with mock.patch("builtins.print") as output:
                result = checkpoint.validate_stats(path, "phase")
            self.assertEqual(result["local_writes"], 1)
            self.assertEqual(result["remote_writes"], 0)
            self.assertEqual(result["remote_failures"], 1)
            self.assertIn("status=degraded", output.call_args.args[0])

    def test_current_generation_uses_latest_branch_local_marker(self):
        ref = "refs/heads/apple-macos"
        old = "1" * 64
        current = "2" * 64
        caches = [
            {"id": 1, "key": checkpoint.CHECK_KEY, "version": old, "ref": ref,
             "last_accessed_at": "2026-01-01T00:00:00Z"},
            {"id": 2, "key": checkpoint.CHECK_KEY, "version": current, "ref": ref,
             "last_accessed_at": "2026-01-02T00:00:00Z"},
            {"id": 3, "key": checkpoint.CHECK_KEY, "version": "3" * 64,
             "ref": "refs/heads/apple-ios", "last_accessed_at": "2027-01-01T00:00:00Z"},
        ]
        self.assertEqual(checkpoint.current_version(caches, ref), current)

    def test_discovery_retries_eventually_consistent_generation_marker(self):
        ref = "refs/heads/apple-macos"
        current = "2" * 64
        batches = [[], [{
            "id": 2, "key": checkpoint.CHECK_KEY, "version": current,
            "ref": ref, "last_accessed_at": "2026-01-02T00:00:00Z",
        }]]
        with mock.patch.object(checkpoint, "list_caches", side_effect=batches), mock.patch.object(
            checkpoint.time, "sleep"
        ) as sleep:
            self.assertEqual(
                checkpoint.discover_version(
                    "owner/repository", ref, "secret", "https://example.invalid",
                    attempts=2, retry_interval=0.01,
                ),
                current,
            )
        sleep.assert_called_once_with(0.01)

    def test_pruning_is_ref_and_version_scoped_and_keeps_fallback(self):
        ref = "refs/heads/apple-macos"
        current, previous, obsolete = "a" * 64, "b" * 64, "c" * 64
        caches = [
            {"id": 1, "key": checkpoint.CHECK_KEY, "version": current, "ref": ref,
             "created_at": "2026-03-03T00:00:00Z"},
            {"id": 2, "key": "sccache/current", "version": current, "ref": ref},
            {"id": 3, "key": checkpoint.CHECK_KEY, "version": previous, "ref": ref,
             "created_at": "2026-03-02T00:00:00Z"},
            {"id": 4, "key": "sccache/previous", "version": previous, "ref": ref},
            {"id": 5, "key": checkpoint.CHECK_KEY, "version": obsolete, "ref": ref,
             "created_at": "2026-03-01T00:00:00Z"},
            {"id": 6, "key": "sccache/obsolete", "version": obsolete, "ref": ref},
            {"id": 7, "key": "sccache/foreign", "version": obsolete,
             "ref": "refs/heads/apple-ios"},
            {"id": 8, "key": "macos-conan-v2-safe", "version": obsolete, "ref": ref},
        ]
        keep, delete = checkpoint.prune_ids(caches, ref, current, 1)
        self.assertEqual(keep, {current, previous})
        self.assertEqual(delete, [5, 6])

    def test_pruning_refuses_an_unproven_active_generation(self):
        ref = "refs/heads/apple-macos"
        caches = [{
            "id": 1, "key": checkpoint.CHECK_KEY, "version": "a" * 64,
            "ref": ref, "created_at": "2026-01-01T00:00:00Z",
        }]
        with self.assertRaisesRegex(checkpoint.CheckpointError, "not present"):
            checkpoint.prune_ids(caches, ref, "b" * 64, 1)


if __name__ == "__main__":
    unittest.main()
