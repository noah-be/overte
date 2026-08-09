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


def top_level_block(source: str, name: str) -> str | None:
    match = re.search(rf"(?m)^{re.escape(name)}\s*\{{", source)
    if match is None:
        return None
    opening = source.find("{", match.start())
    depth = 0
    quote = None
    escaped = False
    for index in range(opening, len(source)):
        character = source[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in ("'", '"'):
            quote = character
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1:index]
    raise ValueError(f"unterminated top-level {name} block")


class LegacyGradleDependencyTest(unittest.TestCase):
    def test_root_owns_legacy_plugin_and_repository_configuration(self):
        root = (ANDROID_ROOT / "build.gradle").read_text(encoding="utf-8")
        buildscript = top_level_block(root, "buildscript")
        allprojects = top_level_block(root, "allprojects")
        self.assertIsNotNone(buildscript)
        self.assertIsNotNone(allprojects)
        self.assertEqual(1, buildscript.count(
            "classpath 'com.android.tools.build:gradle:3.2.1'"))
        for repository in ("google()", "jcenter()", "mavenCentral()"):
            self.assertIn(repository, allprojects)

    def test_interface_uses_root_build_authority_and_project_topology(self):
        interface = (ANDROID_ROOT / "apps/interface/build.gradle").read_text(
            encoding="utf-8")
        settings = (ANDROID_ROOT / "settings.gradle").read_text(encoding="utf-8")
        self.assertIsNone(top_level_block(interface, "buildscript"))
        self.assertIsNone(top_level_block(interface, "allprojects"))
        self.assertIn("include ':interface'", settings)
        self.assertIn("project(':interface').projectDir = new File(settingsDir, 'apps/interface')",
                      settings)
        self.assertIn("versionCode appVersionCode", interface)
        self.assertIn("'-DRELEASE_NUMBER=' + RELEASE_NUMBER", interface)

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

    def test_top_level_block_parser_distinguishes_nested_or_missing_authority(self):
        source = """
buildscript {
    repositories { google() }
    value = "a brace } in a string"
}
android {
    allprojects { repositories { jcenter() } }
}
"""
        self.assertIn("google()", top_level_block(source, "buildscript"))
        self.assertIsNone(top_level_block(source, "allprojects"))
        with self.assertRaises(ValueError):
            top_level_block("buildscript { repositories { google() }", "buildscript")


if __name__ == "__main__":
    unittest.main()
