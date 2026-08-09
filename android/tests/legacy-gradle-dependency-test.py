#!/usr/bin/env python3
"""Guard legacy Android dependencies and retired build-plugin boundaries."""

from __future__ import annotations

from collections import Counter
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
import zipfile


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
INCOMPATIBLE_LEGACY_GRADLE_API = re.compile(
    r"\b(?:archiveFileName|destinationDirectory)\b")
LEGACY_DIRECT_DEPENDENCY_INVENTORY = (
    ANDROID_ROOT / "tests/legacy-gradle-direct-dependencies.json")
GVR_EVIDENCE_SCRIPT = ANDROID_ROOT / "tests/legacy-gvr-evidence.py"
GVR_EVIDENCE_SPEC = importlib.util.spec_from_file_location(
    "legacy_gvr_evidence", GVR_EVIDENCE_SCRIPT)
gvr_evidence = importlib.util.module_from_spec(GVR_EVIDENCE_SPEC)
GVR_EVIDENCE_SPEC.loader.exec_module(gvr_evidence)
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


def parse_legacy_version_code(property_present: bool, raw_value) -> int:
    if not property_present:
        return 1
    value = "" if raw_value is None else str(raw_value)
    if re.fullmatch(r"[0-9]+", value) is None:
        raise ValueError("invalid legacy VERSION_CODE")
    parsed = int(value)
    if not 1 <= parsed <= 2_147_483_647:
        raise ValueError("invalid legacy VERSION_CODE")
    return parsed


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

    return {
        "schemaVersion": 1,
        "scope": "direct declarations only",
        "resolution": "unverified",
        "artifactType": "source declaration inventory",
        "sbom": False,
        "toolchain": {
            "gradle": "6.5",
            "androidGradlePlugin": "4.1.3",
        },
        "modules": modules,
    }


def legacy_toolchain_contract_errors(
        settings: str, root_build: str, documentation: str, wrapper: str,
        phone_settings: str, pico_settings: str) -> list[str]:
    errors = []
    guard = "GradleVersion.version('6.5')"
    if guard not in settings or settings.index(guard) > settings.index("include ':oculus'"):
        errors.append("legacy Gradle 6.5 guard must precede project inclusion")
    if "classpath 'com.android.tools.build:gradle:4.1.3'" not in root_build:
        errors.append("legacy AGP 4.1.3 pin is missing")
    if "Gradle `6.5`" not in documentation or \
            "Plugin `4.1.3`" not in documentation:
        errors.append("legacy toolchain documentation drifted")
    if "gradle-8.13-bin.zip" not in wrapper or "distributionSha256Sum=" not in wrapper:
        errors.append("shared Phone/Pico wrapper pin drifted")
    if "buildFileName = 'build-phone.gradle'" not in phone_settings:
        errors.append("Phone no longer owns a separate root build")
    if "buildFileName = 'build-pico.gradle'" not in pico_settings:
        errors.append("Pico no longer owns a separate root build")
    return errors


class LegacyGradleDependencyTest(unittest.TestCase):
    def test_legacy_native_modules_opt_into_the_isolated_cmake_boundary(self):
        root = (REPOSITORY_ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("if (OVERTE_LEGACY_ANDROID_CMAKE AND CMAKE_VERSION VERSION_LESS 3.24)", root)
        self.assertIn("cmake_minimum_required(VERSION 3.18)", root)
        self.assertIn("cmake_minimum_required(VERSION 3.24)", root)
        for relative_path in (
                "apps/interface/build.gradle",
                "apps/questInterface/build.gradle",
                "apps/framePlayer/build.gradle",
                "apps/questFramePlayer/build.gradle"):
            source = (ANDROID_ROOT / relative_path).read_text(encoding="utf-8")
            self.assertEqual(1, source.count("-DOVERTE_LEGACY_ANDROID_CMAKE=ON"),
                             relative_path)
            self.assertEqual(1, source.count("-DCMAKE_C_FLAGS=-O2 -falign-functions=32 -fPIC"),
                             relative_path)
            self.assertEqual(1, source.count("-DCMAKE_CXX_FLAGS=-O2 -falign-functions=32 -fPIC"),
                             relative_path)

    def test_dedicated_legacy_wrapper_gates_toolchain_and_forwards_arguments(self):
        wrapper = ANDROID_ROOT / "legacy-gradlew"
        self.assertTrue(os.access(wrapper, os.X_OK))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            python_log = root / "python.log"
            gradle_log = root / "gradle.log"
            fake_python = root / "python"
            fake_gradle = root / "gradle"
            fake_python.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$*\" > \"$PYTHON_LOG\"\n",
                encoding="utf-8")
            fake_gradle.write_text(
                "#!/bin/sh\nprintf 'cwd=%s\\nargs=%s\\njava=%s\\n' \"$PWD\" \"$*\" \"$JAVA_HOME\" > \"$GRADLE_LOG\"\nexit 23\n",
                encoding="utf-8")
            fake_python.chmod(0o755)
            fake_gradle.chmod(0o755)
            environment = os.environ.copy()
            environment.update({
                "OVERTE_LEGACY_PYTHON_COMMAND": str(fake_python),
                "OVERTE_LEGACY_GRADLE_COMMAND": str(fake_gradle),
                "OVERTE_LEGACY_JAVA_HOME": str(root / "jdk8"),
                "PYTHON_LOG": str(python_log),
                "GRADLE_LOG": str(gradle_log),
            })
            result = subprocess.run(
                [str(wrapper), "tasks", "--offline"], cwd=root,
                env=environment, text=True, capture_output=True, check=False)
            self.assertEqual(23, result.returncode)
            self.assertIn("run_dependency_report.py toolchain --offline",
                          python_log.read_text(encoding="utf-8"))
            gradle_invocation = gradle_log.read_text(encoding="utf-8")
            self.assertIn(f"cwd={ANDROID_ROOT}", gradle_invocation)
            self.assertIn("args=--no-daemon tasks --offline", gradle_invocation)
            self.assertIn(f"java={root / 'jdk8'}", gradle_invocation)

    def test_dedicated_legacy_wrapper_stops_when_toolchain_gate_fails(self):
        wrapper = ANDROID_ROOT / "legacy-gradlew"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_python = root / "python"
            marker = root / "gradle-started"
            fake_gradle = root / "gradle"
            fake_python.write_text("#!/bin/sh\nexit 17\n", encoding="utf-8")
            fake_gradle.write_text(
                "#!/bin/sh\ntouch \"$GRADLE_MARKER\"\n", encoding="utf-8")
            fake_python.chmod(0o755)
            fake_gradle.chmod(0o755)
            environment = os.environ.copy()
            environment.update({
                "OVERTE_LEGACY_PYTHON_COMMAND": str(fake_python),
                "OVERTE_LEGACY_GRADLE_COMMAND": str(fake_gradle),
                "GRADLE_MARKER": str(marker),
            })
            result = subprocess.run(
                [str(wrapper), "tasks"], env=environment,
                text=True, capture_output=True, check=False)
            self.assertEqual(17, result.returncode)
            self.assertFalse(marker.exists())

    def test_legacy_build_config_strings_use_the_root_escaper(self):
        root_source = (ANDROID_ROOT / "build.gradle").read_text(encoding="utf-8")
        self.assertIn("legacyBuildConfigString", root_source)
        self.assertIn("groovy.json.JsonOutput.toJson", root_source)
        environment_fields = {
            "BACKTRACE_URL": "CMAKE_BACKTRACE_URL",
            "BACKTRACE_TOKEN": "CMAKE_BACKTRACE_TOKEN",
            "OAUTH_CLIENT_ID": "OAUTH_CLIENT_ID",
            "OAUTH_CLIENT_SECRET": "OAUTH_CLIENT_SECRET",
            "OAUTH_REDIRECT_URI": "OAUTH_REDIRECT_URI",
        }
        for relative_path in (
                "apps/interface/build.gradle",
                "apps/questInterface/build.gradle"):
            source = (ANDROID_ROOT / relative_path).read_text(encoding="utf-8")
            self.assertNotIn('"\\\"" + (System.getenv(', source)
            for field, environment_name in environment_fields.items():
                expected = (
                    f'buildConfigField "String", "{field}", '
                    'rootProject.ext.legacyBuildConfigString('
                    f'System.getenv("{environment_name}"))')
                self.assertEqual(2, source.count(expected),
                                 f"{relative_path}: {field}")

    def test_json_string_literals_round_trip_adversarial_values(self):
        for value in (
                "", "ordinary", 'quote"value', "backslash\\value",
                "carriage\rreturn", "line\nfeed", "tab\tvalue",
                "snowman \u2603", "separator \u2028 value", "control \x01"):
            with self.subTest(value=repr(value)):
                literal = json.dumps(value, ensure_ascii=True)
                self.assertEqual(value, json.loads(literal))
                self.assertTrue(literal.startswith('"'))
                self.assertTrue(literal.endswith('"'))

    def test_legacy_version_code_policy_is_positive_and_bounded(self):
        source = (ANDROID_ROOT / "build.gradle").read_text(encoding="utf-8")
        self.assertIn("def parseLegacyVersionCode", source)
        self.assertIn("if (!propertyPresent)", source)
        self.assertIn("return 1", source)
        self.assertIn("value ==~ /[0-9]+/", source)
        self.assertIn("new BigInteger(value)", source)
        self.assertIn("parsed < BigInteger.ONE", source)
        self.assertIn("parsed > BigInteger.valueOf(Integer.MAX_VALUE)", source)
        self.assertIn("throw new GradleException", source)
        self.assertIn(
            "parseLegacyVersionCode(project.hasProperty('VERSION_CODE'), VERSION_CODE)",
            source)
        self.assertNotIn("Integer.valueOf(VERSION_CODE ?: 1)", source)

    def test_legacy_version_code_behavior_matrix(self):
        self.assertEqual(1, parse_legacy_version_code(False, None))
        self.assertEqual(1, parse_legacy_version_code(False, "unread"))
        self.assertEqual(1, parse_legacy_version_code(True, "1"))
        self.assertEqual(2_147_483_647,
                         parse_legacy_version_code(True, "2147483647"))
        for invalid in (
                None, "", "0", "-1", "+1", " 1", "1 ", "1.0", "one",
                "2147483648", "9" * 1000):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    parse_legacy_version_code(True, invalid)

    def test_legacy_root_uses_gradle_4_10_archive_apis(self):
        source = (ANDROID_ROOT / "build.gradle").read_text(encoding="utf-8")
        self.assertEqual([], INCOMPATIBLE_LEGACY_GRADLE_API.findall(source))
        self.assertEqual(2, len(re.findall(r"(?m)^\s*archiveName\s*=", source)))
        self.assertEqual(2, len(re.findall(r"(?m)^\s*destinationDir\s*=", source)))

    def test_validator_recognizes_incompatible_archive_apis(self):
        for source in (
                "archiveFileName.set('symbols.zip')",
                "destinationDirectory.set(layout.buildDirectory.dir('tmp'))"):
            with self.subTest(source=source):
                self.assertTrue(INCOMPATIBLE_LEGACY_GRADLE_API.search(source))

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
            {"gradle": "6.5", "androidGradlePlugin": "4.1.3"},
            inventory["toolchain"])

    def test_legacy_gvr_dependency_chain_is_absent(self):
        inventory = json.loads(LEGACY_DIRECT_DEPENDENCY_INVENTORY.read_text(
            encoding="utf-8"))
        coordinates = {
            dependency["coordinate"]
            for module in inventory["modules"]
            for dependency in module["directDependencies"]
            if dependency["kind"] == "external"
        }
        self.assertFalse(any(value.startswith("com.google.vr:")
                             for value in coordinates))
        self.assertFalse((ANDROID_ROOT / "setupGVR.gradle").exists())
        self.assertFalse(
            (ANDROID_ROOT.parent / "cmake/macros/TargetGoogleVR.cmake").exists())
        for relative_path in ("build.gradle", "apps/interface/build.gradle",
                              "apps/interface/CMakeLists.txt"):
            source = (ANDROID_ROOT / relative_path).read_text(encoding="utf-8")
            self.assertNotRegex(source, r"(?i)(?:google[.]vr|gvr-android-sdk|libgvr)")

    def test_gvr_evidence_reports_packaging_and_elf_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / "legacy.apk"
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr(gvr_evidence.NATIVE_LIBRARY, b"native")
                archive.writestr("lib/arm64-v8a/libgvr.so", b"gvr")
                archive.writestr("lib/arm64-v8a/libgvr_audio.so", b"audio")
            def fake_runner(command, **_kwargs):
                output = " 0x1 (NEEDED) Shared library: [libgvr.so]\n" \
                    if "-dW" in command else " 1: 0 NOTYPE GLOBAL DEFAULT UND gvr_initialize\n"
                return subprocess.CompletedProcess(command, 0, output, "")
            result = gvr_evidence.analyze(apk, "readelf", fake_runner)
            self.assertIn("libgvr.so", result["neededLibraries"])
            self.assertEqual(["gvr_initialize"], result["undefinedGvrSymbols"])
            self.assertEqual(2, len(result["packagedGvrLibraries"]))
            self.assertFalse(result["removalEvidence"]["supportsRemoval"])

    def test_gvr_evidence_supports_removal_only_without_elf_references(self):
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / "legacy.apk"
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr(gvr_evidence.NATIVE_LIBRARY, b"native")
            def fake_runner(command, **_kwargs):
                output = " 0x1 (NEEDED) Shared library: [liblog.so]\n" \
                    if "-dW" in command else " 1: 0 NOTYPE GLOBAL DEFAULT UND malloc\n"
                return subprocess.CompletedProcess(command, 0, output, "")
            result = gvr_evidence.analyze(apk, "readelf", fake_runner)
            self.assertTrue(result["removalEvidence"]["supportsRemoval"])
            self.assertEqual([], result["undefinedGvrSymbols"])

    def test_gvr_evidence_fails_closed_on_missing_native_library_or_readelf_error(self):
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / "legacy.apk"
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr("fixture", b"x")
            with self.assertRaisesRegex(gvr_evidence.EvidenceError, "exactly one"):
                gvr_evidence.analyze(apk, "readelf")
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr(gvr_evidence.NATIVE_LIBRARY, b"native")
            def failed(command, **_kwargs):
                return subprocess.CompletedProcess(command, 2, "", "private detail")
            with self.assertRaisesRegex(gvr_evidence.EvidenceError, "could not inspect"):
                gvr_evidence.analyze(apk, "readelf", failed)

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
            "classpath 'com.android.tools.build:gradle:4.1.3'"))
        self.assertIn("google()", buildscript)
        self.assertIn("mavenCentral()", buildscript)
        self.assertNotIn("jcenter()", buildscript)
        for repository in ("google()", "mavenCentral()"):
            self.assertIn(repository, allprojects)
        self.assertNotIn("jcenter()", allprojects)

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
            "GradleVersion.version('6.5')\ninclude ':oculus'",
            "classpath 'com.android.tools.build:gradle:4.1.3'",
            "Plugin `4.1.3` and Gradle `6.5`",
            "distributionUrl=gradle-8.13-bin.zip\ndistributionSha256Sum=abc",
            "buildFileName = 'build-phone.gradle'",
            "buildFileName = 'build-pico.gradle'",
        ]
        self.assertEqual([], legacy_toolchain_contract_errors(*valid))
        for index, replacement in (
                (0, "include ':oculus'\nGradleVersion.version('6.5')"),
                (1, "classpath 'com.android.tools.build:gradle:3.3.0'"),
                (2, "Plugin `4.1.3` and Gradle `8.13`"),
                (3, "distributionUrl=gradle-8.13-bin.zip"),
                (4, "buildFileName = 'build.gradle'"),
                (5, "buildFileName = 'build.gradle'")):
            broken = list(valid)
            broken[index] = replacement
            with self.subTest(index=index):
                self.assertTrue(legacy_toolchain_contract_errors(*broken))


if __name__ == "__main__":
    unittest.main()
