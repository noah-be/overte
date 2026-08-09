#!/usr/bin/env python3
"""Guard legacy Android dependencies and retired build-plugin boundaries."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import unittest


ANDROID_ROOT = Path(__file__).resolve().parents[1]
DEPENDENCY = re.compile(
    r"^\s*(api|implementation|compileOnly|runtimeOnly|testImplementation)\s+"
    r"['\"]([^'\"]+)['\"]\s*$", re.MULTILINE)
LEGACY_DOWNLOAD_PLUGIN = re.compile(
    r"de\.undercouch\.download|de\.undercouch\.gradle\.tasks\.download\.Download|"
    r"\btype\s*:\s*Download\b")


def duplicates(source: str) -> list[tuple[str, str]]:
    counts = Counter(DEPENDENCY.findall(source))
    return sorted(declaration for declaration, count in counts.items() if count > 1)


def legacy_download_plugin_references(source: str) -> list[str]:
    return LEGACY_DOWNLOAD_PLUGIN.findall(source)


class LegacyGradleDependencyTest(unittest.TestCase):
    def test_legacy_root_does_not_resolve_the_retired_download_plugin(self):
        source = (ANDROID_ROOT / "build.gradle").read_text(encoding="utf-8")
        self.assertEqual([], legacy_download_plugin_references(source))

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

    def test_validator_recognizes_legacy_download_plugin_apis(self):
        for source in (
                "id 'de.undercouch.download' version '3.3.0'",
                "import de.undercouch.gradle.tasks.download.Download",
                "task fetch(type: Download) {}"):
            with self.subTest(source=source):
                self.assertTrue(legacy_download_plugin_references(source))


if __name__ == "__main__":
    unittest.main()
