#!/usr/bin/env python3
"""Fail closed when Qt 5 compatibility APIs and target opt-ins diverge."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
LEGACY = re.compile(r"\b(?:QRegExp|QRegExpValidator|QTextCodec|QTextDecoder|QTextEncoder|QStringRef|QLinkedList|QMutableLinkedListIterator|QXmlSimpleReader|QXmlInputSource|QXmlDefaultHandler|QXmlAttributes|QXmlParseException)\b")
SUFFIXES = {".cpp", ".h", ".hpp", ".mm", ".in", ".tmpl", ".template", ".inc", ".ipp"}
SKIP = {".git", "build", "build-ios", "node_modules", "vendor"}
EXPECTED = {
    "android/apps/interface/src/main/cpp/native.cpp",
    "assignment-client/src/assets/AssetServer.cpp",
    "domain-server/src/ContentSettingsBackupHandler.cpp",
    "domain-server/src/DomainContentBackupManager.cpp",
    "domain-server/src/DomainGatekeeper.cpp",
    "domain-server/src/DomainServer.cpp",
    "plugins/JSAPIExample/src/JSAPIExample.cpp",
    "tests-manual/render-perf/src/main.cpp",
    "tools/nitpick/src/AWSInterface.cpp",
    "tools/nitpick/src/TestRunnerMobile.cpp",
}

def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)

def scan() -> set[str]:
    matches = set()
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SUFFIXES or any(part in SKIP for part in path.parts):
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if LEGACY.search(source):
            matches.add(path.relative_to(ROOT).as_posix())
    return matches

actual = scan()
require(actual == EXPECTED,
        f"Core5Compat consumers changed; added={sorted(actual - EXPECTED)}, removed={sorted(EXPECTED - actual)}")
for macro in ("SetupHifiLibrary.cmake", "SetupHifiProject.cmake", "SetupHifiTestCase.cmake"):
    require("Core5Compat" not in (ROOT / "cmake/macros" / macro).read_text(),
            f"{macro} still links Core5Compat by default")
require("set(PLATFORM_QT_COMPONENTS WebView Xml Core5Compat)" not in (ROOT / "CMakeLists.txt").read_text(),
        "iOS platform components still link Core5Compat")
contracts = {
    "assignment-client/CMakeLists.txt": "setup_hifi_project(Core Gui Network Quick WebSockets Core5Compat)",
    "domain-server/CMakeLists.txt": "setup_hifi_project(Network Core5Compat)",
    "android/apps/interface/CMakeLists.txt": "setup_hifi_library(Core5Compat)",
    "tests-manual/render-perf/CMakeLists.txt": "setup_hifi_project(Quick Gui Core5Compat)",
    "plugins/JSAPIExample/CMakeLists.txt": "overte_link_qt_modules(${TARGET_NAME} Core5Compat)",
    "tools/nitpick/CMakeLists.txt": "overte_link_qt_modules(${TARGET_NAME} Widgets Core5Compat)",
}
for relative, marker in contracts.items():
    require(marker in (ROOT / relative).read_text(), f"missing explicit Core5Compat opt-in: {relative}")
qt_compat = (ROOT / "cmake/QtCompat.cmake").read_text()
require(re.search(r"if\(OVERTE_QT_MAJOR EQUAL 5\).*?OVERTE_QT_UNAVAILABLE_COMPONENTS Core5Compat", qt_compat, re.S),
        "Qt 5 does not centrally filter the nonexistent Core5Compat component")
require(re.search(r"macro\(overte_find_qt[^)]*\).*?overte_filter_qt_components", qt_compat, re.S),
        "Qt package discovery bypasses the central component filter")
require(re.search(r"function\(overte_link_qt_modules[^)]*\).*?overte_filter_qt_components", qt_compat, re.S),
        "Qt target linking bypasses the central component filter")
templates = list((ROOT / "libraries/entities/src").glob("*.in"))
require(templates and not any(LEGACY.search(path.read_text()) for path in templates),
        "generated Entity source template uses Core5Compat or escaped scan scope")
print("Core5Compat CMake contract valid: defaults/iOS clean; explicit legacy targets and templates audited")
