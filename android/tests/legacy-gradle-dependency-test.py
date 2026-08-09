#!/usr/bin/env python3
"""Reject exact duplicate dependency declarations in legacy Android modules."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import unittest


ANDROID_ROOT = Path(__file__).resolve().parents[1]
DEPENDENCY = re.compile(
    r"^\s*(api|implementation|compileOnly|runtimeOnly|testImplementation)\s+"
    r"['\"]([^'\"]+)['\"]\s*$", re.MULTILINE)


def duplicates(source: str) -> list[tuple[str, str]]:
    counts = Counter(DEPENDENCY.findall(source))
    return sorted(declaration for declaration, count in counts.items() if count > 1)


class LegacyGradleDependencyTest(unittest.TestCase):
    def test_legacy_interface_has_no_exact_duplicate_dependencies(self):
        source = (ANDROID_ROOT / "apps/interface/build.gradle").read_text(encoding="utf-8")
        self.assertEqual([], duplicates(source))

    def test_validator_distinguishes_duplicates_from_configuration_choices(self):
        source = """
            api 'example:library:1'
            implementation 'example:library:1'
            api 'example:library:1'
        """
        self.assertEqual([("api", "example:library:1")], duplicates(source))


if __name__ == "__main__":
    unittest.main()
