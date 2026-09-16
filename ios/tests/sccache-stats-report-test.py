#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import json
import subprocess
import sys
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
PATH = ROOT / "ios/ci/report-sccache-stats.py"
SPEC = importlib.util.spec_from_file_location("report_sccache_stats", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class SccacheStatsReportTest(unittest.TestCase):
    @staticmethod
    def stats(hits=0, misses=2485, remote_writes=2201, remote_failures=6):
        return {
            "version": "0.17.0",
            "requests_executed": hits + misses,
            "cache_hits": {"counts": {"C/C++": hits}, "adv_counts": {}},
            "cache_misses": {"counts": {"C/C++": misses}, "adv_counts": {}},
            "cache_writes": max(0, misses - remote_failures),
            "cache_write_errors": remote_failures,
            "cache_size": 40_064_722,
            "multi_level": [
                {"name": "L0 (disk)", "hits": hits, "misses": misses, "writes": misses, "write_failures": 0},
                {"name": "L1 (ghac)", "hits": hits, "misses": misses, "writes": remote_writes, "write_failures": remote_failures},
            ],
        }

    def test_realistic_first_build_is_accepted_and_summarized(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = pathlib.Path(temporary)
            (cache / "entry").write_bytes(b"x" * 4096)
            summary = MODULE.summarize(self.stats(), cache, "after")
            MODULE.validate_activity(summary)
        self.assertEqual(summary["requests"], 2485)
        self.assertEqual(summary["misses"], 2485)
        self.assertEqual(summary["hits"], 0)
        self.assertEqual(summary["hitRatePercent"], 0.0)

    def test_identical_rebuild_hits_are_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = pathlib.Path(temporary)
            (cache / "entry").write_bytes(b"x" * 4096)
            summary = MODULE.summarize(
                self.stats(hits=2400, misses=85, remote_writes=85, remote_failures=0),
                cache,
                "after",
            )
            MODULE.validate_activity(summary)
        self.assertGreater(summary["hitRatePercent"], 96.0)

    @classmethod
    def disk_stats(cls, hits=0, misses=2485):
        stats = cls.stats(hits=hits, misses=misses, remote_failures=0)
        stats["multi_level"] = stats["multi_level"][:1]
        return stats

    def test_disk_cold_and_fully_warm_builds(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = pathlib.Path(temporary)
            (cache / "entry").write_bytes(b"x" * 4096)
            for hits, misses in ((0, 2485), (2485, 0)):
                for multilevel in (True, False):
                    with self.subTest(hits=hits, multilevel=multilevel):
                        stats = self.disk_stats(hits, misses)
                        if not multilevel:
                            del stats["multi_level"]
                        summary = MODULE.summarize(stats, cache, "after")
                        MODULE.validate_activity(summary, cache_mode="disk")
                        # Default callers still require their remote checkpoint.
                        with self.assertRaisesRegex(ValueError, "remote GitHub cache level"):
                            MODULE.validate_activity(summary)

    def test_disk_activity_rejects_inactive_or_broken_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = pathlib.Path(temporary)
            entry = cache / "entry"
            cases = (
                ({"requests_executed": 0}, "no sccache compiler requests"),
                ({"cache_hits": {}, "cache_misses": {}}, "no cacheable compiler requests"),
                ({"cache_writes": 0}, "no local compiler checkpoint writes"),
                ({"cache_write_errors": 1}, "local compiler checkpoint writes failed"),
                ({"multi_level": [{"name": "L0 (disk)", "write_failures": 1}]},
                 "local compiler checkpoint writes failed"),
                ({"multi_level": [{"name": "L0 (ghac)"}]}, "non-disk cache level"),
            )
            entry.write_bytes(b"x" * 4096)
            for updates, message in cases:
                with self.subTest(updates=updates):
                    stats = self.disk_stats()
                    stats.update(updates)
                    with self.assertRaisesRegex(ValueError, message):
                        MODULE.validate_activity(MODULE.summarize(stats, cache, "after"), cache_mode="disk")
            for size in (0, 4095):
                entry.write_bytes(b"x" * size)
                with self.assertRaisesRegex(ValueError, "no reusable local compiler checkpoint"):
                    MODULE.validate_activity(MODULE.summarize(self.disk_stats(), cache, "after"), cache_mode="disk")

    def test_observed_qt_run_34704083491_schema(self):
        # Counter/metadata layout and values from the failed runner's JSON.
        # Cache files below test the reporter only, not native cache acceptance.
        payload = {
            "stats": {
                "compile_requests": 0, "requests_executed": 4550,
                "cache_hits": {"counts": {"C/C++": 402},
                               "adv_counts": {"c++ [clang]": 382, "objc++ [clang]": 18, "c [clang]": 2}},
                "cache_misses": {"counts": {"C/C++": 4148},
                                 "adv_counts": {"objc++ [clang]": 80, "c++ [clang]": 3710,
                                                "c [clang]": 354, "c++Header [clang]": 4}},
                "cache_write_errors": 0, "cache_writes": 4148,
                "multi_level": [{"name": "L0 (disk)", "hits": 0, "misses": 0,
                                 "writes": 4148, "write_failures": 0}],
            },
            "cache_size": 268112673, "max_cache_size": 268435456, "version": "0.17.0",
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            path = root / "stats.json"
            path.write_text(json.dumps(payload))
            cache = root / "cache"
            cache.mkdir()
            (cache / "entry").write_bytes(b"x" * 4096)
            summary = MODULE.summarize(MODULE.load_stats(path), cache, "after")
            MODULE.validate_activity(summary, cache_mode="disk")
        self.assertEqual(summary["requests"], 4550)
        self.assertEqual(summary["hits"], 402)
        self.assertEqual(summary["misses"], 4148)
        self.assertEqual(summary["version"], "0.17.0")
        self.assertEqual(summary["reportedCacheBytes"], 268112673)
        self.assertEqual(summary["maxCacheBytes"], 268435456)
        self.assertEqual(summary["cacheCapacityPercent"], 99.88)

    def test_disk_cli_accepts_nested_sccache_json_and_rejects_write_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            cache = root / "cache"
            cache.mkdir()
            (cache / "entry").write_bytes(b"x" * 4096)
            path = root / "stats.json"
            stats = self.disk_stats()
            command = [sys.executable, str(PATH), str(path), "--cache-dir", str(cache),
                       "--phase", "after", "--require-activity", "--cache-mode", "disk"]
            path.write_text(json.dumps({"stats": stats}))
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('"requests":2485', result.stdout)
            stats["cache_write_errors"] = 1
            path.write_text(json.dumps({"stats": stats}))
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("local compiler checkpoint writes failed", result.stderr)
            self.assertNotIn("sccache summary:", result.stdout)

    def test_capacity_annotation_is_informational_and_uses_exact_threshold(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            cache = root / "cache"
            cache.mkdir()
            (cache / "entry").write_bytes(b"x" * 4096)
            path = root / "stats.json"
            for used, maximum, warning in ((89999, 100000, False), (90000, 100000, True),
                                           (100000, 100000, True), (100000, 0, False)):
                with self.subTest(used=used, maximum=maximum):
                    path.write_text(json.dumps({"stats": self.disk_stats(),
                                                "cache_size": used, "max_cache_size": maximum}))
                    result = subprocess.run(
                        [sys.executable, str(PATH), str(path), "--cache-dir", str(cache),
                         "--phase", "after", "--require-activity", "--cache-mode", "disk"],
                        capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual("::warning::Local compiler cache" in result.stdout, warning)

    def test_empty_or_broken_remote_checkpoint_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = pathlib.Path(temporary)
            with self.assertRaisesRegex(ValueError, "no sccache compiler requests"):
                MODULE.validate_activity(MODULE.summarize(self.stats(misses=0), cache, "after"))
            (cache / "entry").write_bytes(b"x" * 4096)
            with self.assertRaisesRegex(ValueError, "failure rate"):
                MODULE.validate_activity(
                    MODULE.summarize(
                        self.stats(misses=100, remote_writes=80, remote_failures=20),
                        cache,
                        "after",
                    )
                )
            with self.assertRaisesRegex(ValueError, "absolute limit"):
                MODULE.validate_activity(
                    MODULE.summarize(
                        self.stats(misses=10_000, remote_writes=9_960, remote_failures=40),
                        cache,
                        "after",
                    )
                )


if __name__ == "__main__":
    unittest.main()
