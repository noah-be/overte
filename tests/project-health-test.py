#!/usr/bin/env python3
"""Repository-wide, dependency-light structural and syntax tests."""

from __future__ import annotations

from pathlib import Path
import json
import os
import py_compile
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


def tracked(*patterns: str) -> list[Path]:
    command = ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *patterns]
    output = subprocess.check_output(command, cwd=ROOT)
    return sorted(path for item in output.rstrip(b"\0").split(b"\0") if item
                  and (path := ROOT / item.decode()).exists())


class ProjectHealthTests(unittest.TestCase):
    maxDiff = None

    def test_tablet_button_import_supports_keyboard_focus(self):
        source = ROOT / "interface/resources/qml/hifi/tablet/TabletButton.qml"
        first_line = source.read_text(encoding="utf-8").splitlines()[0]
        self.assertRegex(first_line, r"^import QtQuick 2\.(?:[1-9]|[1-9][0-9]+)$")
        self.assertIn("activeFocusOnTab:", source.read_text(encoding="utf-8"))

    def test_direct_touch_tablet_actions_take_priority_over_parent_gestures(self):
        button = (ROOT / "interface/resources/qml/hifi/tablet/TabletButton.qml").read_text(
            encoding="utf-8"
        )
        home = (ROOT / "interface/resources/qml/hifi/tablet/TabletHome.qml").read_text(
            encoding="utf-8"
        )
        menu = (ROOT / "interface/resources/qml/hifi/tablet/TabletMenuView.qml").read_text(
            encoding="utf-8"
        )
        self.assertIn("preventStealing: tabletButton.prioritizeTap", button)
        self.assertIn("prioritizeTap: presentation.touchOptimized", home)
        self.assertIn("preventStealing: touchMetrics.directTouch", menu)

    def test_shared_text_field_owns_its_style_constants(self):
        source = (ROOT / "interface/resources/qml/controlsUit/TextField.qml").read_text(
            encoding="utf-8"
        )
        self.assertIn("HifiConstants { id: hifi }", source)

    def test_qt6_tablet_components_do_not_fail_before_use(self):
        setting_number = (
            ROOT / "scripts/system/settings/qml/SettingNumber.qml"
        ).read_text(encoding="utf-8")
        self.assertTrue(setting_number.startswith("import QtQuick\nimport QtQuick.Controls\n"))
        self.assertIn("RegularExpressionValidator", setting_number)

        custom_query = (
            ROOT / "interface/resources/qml/dialogs/TabletCustomQueryDialog.qml"
        ).read_text(encoding="utf-8")
        self.assertIn("import QtQuick.Dialogs as OriginalDialogs", custom_query)
        self.assertNotRegex(custom_query, r"import QtQuick\.Dialogs\s+[0-9]")

        tablet_root = (
            ROOT / "interface/resources/qml/hifi/tablet/TabletRoot.qml"
        ).read_text(encoding="utf-8")
        for component in (
            "TabletCustomQueryDialog",
            "TabletFileDialog",
            "TabletAssetDialog",
        ):
            self.assertNotRegex(
                tablet_root,
                rf"Component\s*\{{[^}}]*\b{component}\s*\{{",
            )
            self.assertIn(f'Qt.createComponent("../../dialogs/{component}.qml")', tablet_root)

    def test_all_python_files_compile(self):
        python2_allowlist = {
            Path("tools/bake-tools/bake.py"),
            Path("tools/bake-tools/convertToRelativePaths.py"),
        }
        failures = []
        seen_allowlist = set()
        with tempfile.TemporaryDirectory(prefix="overte-pycompile-") as cache:
            for source in tracked("*.py"):
                target = Path(cache) / (str(source.relative_to(ROOT)).replace("/", "_") + "c")
                try:
                    py_compile.compile(str(source), cfile=str(target), doraise=True)
                except py_compile.PyCompileError as error:
                    relative = source.relative_to(ROOT)
                    if relative in python2_allowlist:
                        seen_allowlist.add(relative)
                    else:
                        failures.append(f"{relative}: {error.msg}")
        self.assertEqual(failures, [])
        self.assertEqual(seen_allowlist, python2_allowlist, "remove stale Python 2 exceptions")

    def test_all_shell_files_parse(self):
        template_allowlist = {
            Path("tools/ci-scripts/linux-package-release/after-install.sh"),
            Path("tools/ci-scripts/linux-package-release/assignment-client-before-install.sh"),
            Path("tools/ci-scripts/linux-package-release/before-remove.sh"),
            Path("tools/ci-scripts/linux-package-release/domain-server-before-install.sh"),
            Path("tools/ci-scripts/linux-package-release/ice-server-before-install.sh"),
        }
        failures = []
        seen_allowlist = set()
        for source in tracked("*.sh"):
            result = subprocess.run(["bash", "-n", str(source)], text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if result.returncode:
                relative = source.relative_to(ROOT)
                if relative in template_allowlist and "<%=" in source.read_text(encoding="utf-8"):
                    seen_allowlist.add(relative)
                else:
                    failures.append(f"{relative}:\n{result.stdout.strip()}")
        self.assertEqual(failures, [])
        self.assertEqual(seen_allowlist, template_allowlist, "remove stale shell-template exceptions")

    def test_json_documents_parse_or_are_documented_non_json_assets(self):
        # These tracked files use comments/empty placeholders despite their suffix.
        allowlist = {
            Path("script-archive/shaders/exampleUserDataV2.json"),
            Path("unpublishedScripts/DomainContent/Home/teleport/downsparkle.json"),
        }
        failures = []
        seen_allowlist = set()
        for source in tracked("*.json"):
            relative = source.relative_to(ROOT)
            try:
                json.loads(source.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                if relative in allowlist:
                    seen_allowlist.add(relative)
                else:
                    failures.append(f"{relative}: {error}")
        self.assertEqual(failures, [])
        self.assertEqual(seen_allowlist, allowlist, "remove stale JSON exceptions")

    def test_xml_documents_parse(self):
        failures = []
        for source in tracked("*.xml"):
            try:
                ET.parse(source)
            except (OSError, ET.ParseError) as error:
                failures.append(f"{source.relative_to(ROOT)}: {error}")
        self.assertEqual(failures, [])

    def test_qt_resource_collections_reference_existing_files(self):
        failures = []
        checked = 0
        for source in tracked("*.qrc"):
            root = ET.parse(source).getroot()
            for item in root.findall(".//file"):
                if not item.text:
                    failures.append(f"{source.relative_to(ROOT)}: empty file entry")
                    continue
                checked += 1
                target = source.parent / item.text.strip()
                if not target.is_file():
                    failures.append(
                        f"{source.relative_to(ROOT)}: missing {item.text.strip()}"
                    )
        self.assertGreater(checked, 10)
        self.assertEqual(failures, [])

    def test_qml_module_manifests_reference_existing_components(self):
        directives = {"module", "plugin", "classname", "typeinfo", "depends", "prefer",
                      "designersupported"}
        failures = []
        checked = 0
        for source in tracked("*/qmldir"):
            for number, raw_line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
                line = raw_line.split("#", 1)[0].strip()
                if not line:
                    continue
                fields = line.split()
                if fields[0] in directives:
                    continue
                if fields[0] in {"singleton", "internal"}:
                    fields = fields[1:]
                if len(fields) < 2:
                    failures.append(f"{source.relative_to(ROOT)}:{number}: malformed entry")
                    continue
                candidate = source.parent / fields[-1]
                if candidate.suffix in {".qml", ".js"}:
                    checked += 1
                    if not candidate.is_file():
                        failures.append(
                            f"{source.relative_to(ROOT)}:{number}: missing {fields[-1]}"
                        )
        self.assertGreater(checked, 20)
        self.assertEqual(failures, [])

    def test_javascript_syntax(self):
        self.assertIsNotNone(__import__("shutil").which("node"), "node is required")
        # Intentional syntax fixture plus files using Interface's non-Node include dialect.
        allowlist = {
            Path("script-archive/acScripts/botProceduralWayPoints.js"),
            Path("script-archive/drylake/ratCreator.js"),
            Path("script-archive/example/brownianFun.js"),
            Path("script-archive/example/soundToys.js"),
            Path("script-archive/pointer.js"),
            Path("scripts/developer/debugging/queryAACubeInspector.js"),
            Path("scripts/developer/tests/performance/domain-check.js"),
            Path("scripts/developer/tests/unit_tests/scriptTests/nested/syntax-error.js"),
            Path("tests-manual/qml/qml/qml/+android/UI.js"),
            Path("tests-manual/qml/qml/qml/+ios/UI.js"),
            Path("tests-manual/qml/qml/qml/+osx/UI.js"),
            Path("tests-manual/qml/qml/qml/UI.js"),
        }
        failures = []
        seen_allowlist = set()
        for source in tracked("*.js"):
            relative = source.relative_to(ROOT)
            result = subprocess.run(["node", "--check", str(source)], text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if result.returncode:
                if relative in allowlist:
                    seen_allowlist.add(relative)
                else:
                    failures.append(f"{relative}:\n{result.stdout.strip()}")
        self.assertEqual(failures, [])
        self.assertEqual(seen_allowlist, allowlist, "remove stale JavaScript exceptions")

    def test_tracked_symbolic_links_resolve_inside_checkout(self):
        failures = []
        for source in tracked():
            if source.is_symlink() and not source.exists():
                failures.append(str(source.relative_to(ROOT)))
        self.assertEqual(failures, [])

    def test_cmake_test_projects_have_sources_and_registration(self):
        failures = []
        test_root = ROOT / "tests"
        registered = 0
        for cmake in sorted(test_root.glob("*/CMakeLists.txt")):
            text = cmake.read_text(encoding="utf-8")
            if "setup_hifi_testcase(" not in text or text.lstrip().startswith("#") and "#setup_hifi_testcase(" in text:
                continue
            registered += 1
            sources = list((cmake.parent / "src").glob("*.cpp"))
            if not sources:
                failures.append(f"{cmake.parent.relative_to(ROOT)} has no C++ test source")
        self.assertGreaterEqual(registered, 12)
        self.assertEqual(failures, [])

    def test_cmake_discovery_ignores_non_cmake_test_harnesses(self):
        cmake = (ROOT / "tests/CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn(
            'EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/${DIR}/CMakeLists.txt"',
            cmake,
        )

    def test_gradle_wrapper_is_complete(self):
        required = [
            ROOT / "android/common/gradlew",
            ROOT / "android/common/gradle/wrapper/gradle-wrapper.jar",
            ROOT / "android/common/gradle/wrapper/gradle-wrapper.properties",
            ROOT / "android/phone/settings.gradle",
            ROOT / "android/vr/pico/settings.gradle",
        ]
        self.assertTrue(all(path.is_file() for path in required))
        self.assertTrue(os.access(required[0], os.X_OK))
        properties = required[2].read_text(encoding="utf-8")
        self.assertIn("distributionUrl=", properties)
        self.assertIn("distributionSha256Sum=", properties)


if __name__ == "__main__":
    unittest.main(verbosity=2)
