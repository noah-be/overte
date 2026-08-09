#!/usr/bin/env python3
"""Guard legacy Android dependencies and retired build-plugin boundaries."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import unittest


ANDROID_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ANDROID_ROOT.parent
DEPENDENCY = re.compile(
    r"^\s*(api|implementation|compileOnly|runtimeOnly|testImplementation)\s+"
    r"['\"]([^'\"]+)['\"]\s*$", re.MULTILINE)
LEGACY_DOWNLOAD_PLUGIN = re.compile(
    r"de\.undercouch\.download|de\.undercouch\.gradle\.tasks\.download\.Download|"
    r"\btype\s*:\s*Download\b")
DEAD_LEGACY_BUILD_PROTOTYPE = re.compile(
    r"\b(?:setupDependencies|cleanDependencies|testElf|EXEC_SUFFIX|baseUrl)\b|"
    r"build time binary dependency resolution")
LEGACY_DIRECT_DEPENDENCY_INVENTORY = (
    ANDROID_ROOT / "tests/legacy-gradle-direct-dependencies.json")
LEGACY_MODULES = {
    "framePlayer": "apps/framePlayer/build.gradle",
    "interface": "apps/interface/build.gradle",
    "oculus": "libraries/oculus/build.gradle",
    "picoInterface": "apps/picoInterface/build.gradle",
    "qt": "libraries/qt/build.gradle",
    "questFramePlayer": "apps/questFramePlayer/build.gradle",
    "questInterface": "apps/questInterface/build.gradle",
}
CONFIGURATION = r"api|implementation|compileOnly|runtimeOnly|testImplementation"
EXTERNAL_DECLARATION = re.compile(
    rf"^\s*({CONFIGURATION})\s+['\"]([^'\"]+)['\"]\s*$")
PROJECT_DECLARATION = re.compile(
    rf"^\s*({CONFIGURATION})\s+project\(\s*(?:path\s*:\s*)?"
    r"['\"]([^'\"]+)['\"]\s*\)\s*$")
FILE_TREE_DECLARATION = re.compile(
    rf"^\s*({CONFIGURATION})\s+(fileTree\(.*\))\s*$")


def duplicates(source: str) -> list[tuple[str, str]]:
    counts = Counter(DEPENDENCY.findall(source))
    return sorted(declaration for declaration, count in counts.items() if count > 1)


def coordinates_in_multiple_configurations(source: str) -> list[str]:
    configurations: dict[str, set[str]] = {}
    for configuration, coordinate in DEPENDENCY.findall(source):
        configurations.setdefault(coordinate, set()).add(configuration)
    return sorted(coordinate for coordinate, names in configurations.items()
                  if len(names) > 1)


def application_api_dependencies(source: str) -> list[str]:
    if "apply plugin: 'com.android.application'" not in source:
        return []
    return sorted(coordinate for configuration, coordinate in DEPENDENCY.findall(source)
                  if configuration == "api")


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


def direct_dependencies(source: str) -> list[dict[str, str]]:
    block = top_level_block(source, "dependencies")
    if block is None:
        return []
    dependencies = []
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue
        external = EXTERNAL_DECLARATION.fullmatch(line)
        if external:
            dependencies.append({
                "configuration": external.group(1),
                "kind": "external",
                "coordinate": external.group(2),
            })
            continue
        project = PROJECT_DECLARATION.fullmatch(line)
        if project:
            dependencies.append({
                "configuration": project.group(1),
                "kind": "project",
                "project": project.group(2),
            })
            continue
        file_tree = FILE_TREE_DECLARATION.fullmatch(line)
        if file_tree:
            dependencies.append({
                "configuration": file_tree.group(1),
                "kind": "fileTree",
                "notation": re.sub(r"\s+", " ", file_tree.group(2)),
            })
            continue
        raise ValueError(f"unsupported direct dependency declaration: {line}")
    return dependencies


def legacy_direct_dependency_inventory() -> dict:
    modules = []
    for name, relative_path in LEGACY_MODULES.items():
        source = (ANDROID_ROOT / relative_path).read_text(encoding="utf-8")
        modules.append({
            "name": name,
            "buildFile": relative_path,
            "directDependencies": direct_dependencies(source),
        })

    gvr_maven = sorted(
        dependency["coordinate"]
        for module in modules
        for dependency in module["directDependencies"]
        if dependency["kind"] == "external"
        and dependency["coordinate"].startswith("com.google.vr:")
    )
    prebuilt_references = [
        "build.gradle",
        "setupGVR.gradle",
        "apps/interface/CMakeLists.txt",
        "../cmake/macros/TargetGoogleVR.cmake",
    ]
    prebuilt_versions = set()
    for relative_path in prebuilt_references:
        source = (ANDROID_ROOT / relative_path).read_text(encoding="utf-8")
        prebuilt_versions.update(re.findall(r"gvr-android-sdk-([0-9.]+)", source))
    if len(prebuilt_versions) != 1:
        raise ValueError(f"ambiguous GVR prebuilt versions: {sorted(prebuilt_versions)}")

    return {
        "schemaVersion": 1,
        "scope": "direct declarations only",
        "resolution": "unverified",
        "artifactType": "source declaration inventory",
        "sbom": False,
        "toolchain": {
            "gradle": "4.10.1",
            "androidGradlePlugin": "3.2.1",
        },
        "modules": modules,
        "gvrVersionBoundary": {
            "versionAlignment": "unverified",
            "mavenArtifacts": gvr_maven,
            "prebuilt": {
                "version": next(iter(prebuilt_versions)),
                "references": prebuilt_references,
            },
        },
    }


def legacy_toolchain_contract_errors(
        settings: str, root_build: str, documentation: str, wrapper: str,
        phone_settings: str, pico_settings: str) -> list[str]:
    errors = []
    guard = "GradleVersion.version('4.10.1')"
    if guard not in settings or settings.index(guard) > settings.index("include ':oculus'"):
        errors.append("legacy Gradle 4.10.1 guard must precede project inclusion")
    if "classpath 'com.android.tools.build:gradle:3.2.1'" not in root_build:
        errors.append("legacy AGP 3.2.1 pin is missing")
    if "Gradle Version to `4.10.1`" not in documentation or \
            "Plugin Version to `3.2.1`" not in documentation:
        errors.append("legacy toolchain documentation drifted")
    if "gradle-8.13-bin.zip" not in wrapper or "distributionSha256Sum=" not in wrapper:
        errors.append("shared Phone/Pico wrapper pin drifted")
    if "buildFileName = 'build-phone.gradle'" not in phone_settings:
        errors.append("Phone no longer owns a separate root build")
    if "buildFileName = 'build-pico.gradle'" not in pico_settings:
        errors.append("Pico no longer owns a separate root build")
    return errors


class LegacyGradleDependencyTest(unittest.TestCase):
    def test_direct_dependency_inventory_matches_legacy_gradle_sources(self):
        expected = json.loads(LEGACY_DIRECT_DEPENDENCY_INVENTORY.read_text(
            encoding="utf-8"))
        self.assertEqual(expected, legacy_direct_dependency_inventory())

    def test_direct_dependency_inventory_has_honest_scope_and_module_set(self):
        inventory = json.loads(LEGACY_DIRECT_DEPENDENCY_INVENTORY.read_text(
            encoding="utf-8"))
        settings = (ANDROID_ROOT / "settings.gradle").read_text(encoding="utf-8")
        settings_modules = set(re.findall(r"include ':([^']+)'", settings))
        inventory_modules = {module["name"] for module in inventory["modules"]}
        self.assertEqual(set(LEGACY_MODULES), settings_modules)
        self.assertEqual(settings_modules, inventory_modules)
        self.assertEqual("direct declarations only", inventory["scope"])
        self.assertEqual("unverified", inventory["resolution"])
        self.assertEqual("source declaration inventory", inventory["artifactType"])
        self.assertIs(inventory["sbom"], False)
        self.assertEqual(
            {"gradle": "4.10.1", "androidGradlePlugin": "3.2.1"},
            inventory["toolchain"])

    def test_direct_dependency_inventory_exposes_unverified_gvr_version_split(self):
        inventory = json.loads(LEGACY_DIRECT_DEPENDENCY_INVENTORY.read_text(
            encoding="utf-8"))
        boundary = inventory["gvrVersionBoundary"]
        self.assertEqual("unverified", boundary["versionAlignment"])
        self.assertEqual([
            "com.google.vr:sdk-audio:1.80.0",
            "com.google.vr:sdk-base:1.80.0",
        ], boundary["mavenArtifacts"])
        self.assertEqual("1.101.0", boundary["prebuilt"]["version"])

    def test_direct_dependency_parser_classifies_supported_declarations(self):
        source = """
dependencies {
    implementation 'example:library:1.2.3'
    api project(':plain')
    implementation project(path: ':named')
    implementation fileTree(include: ['*.jar'], dir: 'libs')
    implementation fileTree(dir: new File(toolRoot, 'jar'), include: ['*.jar'])
}
"""
        self.assertEqual([
            {"configuration": "implementation", "kind": "external",
             "coordinate": "example:library:1.2.3"},
            {"configuration": "api", "kind": "project", "project": ":plain"},
            {"configuration": "implementation", "kind": "project",
             "project": ":named"},
            {"configuration": "implementation", "kind": "fileTree",
             "notation": "fileTree(include: ['*.jar'], dir: 'libs')"},
            {"configuration": "implementation", "kind": "fileTree",
             "notation": "fileTree(dir: new File(toolRoot, 'jar'), include: ['*.jar'])"},
        ], direct_dependencies(source))

    def test_direct_dependency_parser_rejects_unclassified_declarations(self):
        with self.assertRaisesRegex(ValueError, "unsupported direct dependency"):
            direct_dependencies("dependencies {\n    custom files('opaque.jar')\n}\n")

    def test_legacy_root_has_no_retired_dependency_setup_prototype(self):
        source = (ANDROID_ROOT / "build.gradle").read_text(encoding="utf-8")
        self.assertEqual([], DEAD_LEGACY_BUILD_PROTOTYPE.findall(source))

    def test_legacy_toolchain_split_is_explicit_and_consistent(self):
        sources = [path.read_text(encoding="utf-8") for path in (
            ANDROID_ROOT / "settings.gradle",
            ANDROID_ROOT / "build.gradle",
            REPOSITORY_ROOT / "BUILD_ANDROID.md",
            ANDROID_ROOT / "gradle/wrapper/gradle-wrapper.properties",
            ANDROID_ROOT / "settings-phone.gradle",
            ANDROID_ROOT / "settings-pico.gradle",
        )]
        self.assertEqual([], legacy_toolchain_contract_errors(*sources))

    def test_root_owns_legacy_plugin_and_repository_configuration(self):
        root = (ANDROID_ROOT / "build.gradle").read_text(encoding="utf-8")
        buildscript = top_level_block(root, "buildscript")
        allprojects = top_level_block(root, "allprojects")
        self.assertIsNotNone(buildscript)
        self.assertIsNotNone(allprojects)
        self.assertEqual(1, buildscript.count(
            "classpath 'com.android.tools.build:gradle:3.2.1'"))
        self.assertIn("google()", buildscript)
        self.assertIn("mavenCentral()", buildscript)
        self.assertNotIn("jcenter()", buildscript)
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
        self.assertEqual([], coordinates_in_multiple_configurations(source))
        self.assertEqual([], application_api_dependencies(source))

    def test_validator_distinguishes_duplicates_from_configuration_choices(self):
        source = """
            api 'example:library:1'
            implementation 'example:library:1'
            api 'example:library:1'
        """
        self.assertEqual([("api", "example:library:1")], duplicates(source))

    def test_validator_recognizes_cross_configuration_duplicates(self):
        source = """
            api 'example:library:1'
            implementation 'example:library:1'
            implementation 'example:other:1'
            api 'example:library:2'
        """
        self.assertEqual(
            ["example:library:1"],
            coordinates_in_multiple_configurations(source))

    def test_validator_restricts_api_only_for_application_modules(self):
        application = """
            apply plugin: 'com.android.application'
            api 'example:library:1'
            implementation 'example:internal:1'
        """
        library = application.replace(
            "com.android.application", "com.android.library")
        self.assertEqual(
            ["example:library:1"], application_api_dependencies(application))
        self.assertEqual([], application_api_dependencies(library))
        self.assertEqual([], application_api_dependencies(
            "apply plugin: 'com.android.application'\n"
            "implementation 'example:library:1'"))

    def test_validator_recognizes_legacy_download_plugin_apis(self):
        for source in (
                "id 'de.undercouch.download' version '3.3.0'",
                "import de.undercouch.gradle.tasks.download.Download",
                "task fetch(type: Download) {}"):
            with self.subTest(source=source):
                self.assertTrue(legacy_download_plugin_references(source))

    def test_validator_recognizes_retired_dependency_setup_artifacts(self):
        for source in (
                "task setupDependencies() {}",
                "task cleanDependencies(type: Delete) {}",
                "def baseUrl = 'https://example.test/'",
                "def readelf = tool + EXEC_SUFFIX",
                "task testElf {}",
                "// build time binary dependency resolution"):
            with self.subTest(source=source):
                self.assertTrue(DEAD_LEGACY_BUILD_PROTOTYPE.search(source))

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

    def test_repository_contract_uses_the_requested_top_level_scope(self):
        source = """
buildscript { repositories { google() } }
allprojects { repositories { google(); jcenter(); mavenCentral() } }
"""
        self.assertNotIn("jcenter()", top_level_block(source, "buildscript"))
        self.assertIn("jcenter()", top_level_block(source, "allprojects"))

    def test_legacy_toolchain_contract_rejects_version_and_topology_drift(self):
        valid = [
            "GradleVersion.version('4.10.1')\ninclude ':oculus'",
            "classpath 'com.android.tools.build:gradle:3.2.1'",
            "Plugin Version to `3.2.1` and Gradle Version to `4.10.1`",
            "distributionUrl=gradle-8.13-bin.zip\ndistributionSha256Sum=abc",
            "buildFileName = 'build-phone.gradle'",
            "buildFileName = 'build-pico.gradle'",
        ]
        self.assertEqual([], legacy_toolchain_contract_errors(*valid))
        for index, replacement in (
                (0, "include ':oculus'\nGradleVersion.version('4.10.1')"),
                (1, "classpath 'com.android.tools.build:gradle:3.3.0'"),
                (2, "Plugin Version to `3.2.1` and Gradle Version to `8.13`"),
                (3, "distributionUrl=gradle-8.13-bin.zip"),
                (4, "buildFileName = 'build.gradle'"),
                (5, "buildFileName = 'build.gradle'")):
            broken = list(valid)
            broken[index] = replacement
            with self.subTest(index=index):
                self.assertTrue(legacy_toolchain_contract_errors(*broken))


if __name__ == "__main__":
    unittest.main()
