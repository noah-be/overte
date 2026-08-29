#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

import importlib.util
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
