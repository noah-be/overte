#!/usr/bin/env python3
"""Validate the macOS bootstrap's runtime evidence contract."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]

libnode_recipe = (ROOT / "macos/conan/libnode/conanfile.py").read_text(encoding="utf-8")
libnode_data = (ROOT / "macos/conan/libnode/conandata.yml").read_text(encoding="utf-8")
build_script = (ROOT / "macos/build-macos.sh").read_text(encoding="utf-8")
root_recipe = (ROOT / "conanfile.py").read_text(encoding="utf-8")
LIBNODE_CONTRACT = {
    "official release archive": (
        libnode_data,
        "https://nodejs.org/dist/v22.22.3/node-v22.22.3.tar.gz",
    ),
    "pinned release checksum": (
        libnode_data,
        "3c354fe130e6a8b71701784f48f010ce9a0af40d9f20292c7a8fb8efed1e694c",
    ),
    "macOS-only recipe": (libnode_recipe, 'str(self.settings.os) != "Macos"'),
    "Node build-type mapping": (
        libnode_recipe,
        'node_build_type = "Debug" if str(self.settings.build_type) == "Debug" else "Release"',
    ),
    "bootstrap export": (
        build_script,
        'conan export "$source_root/macos/conan/libnode" --user overte --channel macos',
    ),
    "macOS graph selection": (
        root_recipe,
        'self.requires("libnode/22.22.3@overte/macos")',
    ),
}
for description, (source, token) in LIBNODE_CONTRACT.items():
    if token not in source:
        raise SystemExit(f"missing libnode contract: {description}")

compiler_cmake = (ROOT / "cmake/compiler.cmake").read_text(encoding="utf-8")
if (
    "exec_program(" in compiler_cmake
    or "COMMAND sw_vers -productVersion" not in compiler_cmake
    or "OUTPUT_STRIP_TRAILING_WHITESPACE" not in compiler_cmake
    or "RESULT_VARIABLE _SW_VERS_RESULT" not in compiler_cmake
):
    raise SystemExit("macOS version detection must use execute_process, not removed exec_program")

jsapi_cmake = (ROOT / "plugins/JSAPIExample/CMakeLists.txt").read_text(encoding="utf-8")
if "overte_find_qt(COMPONENTS Core Core5Compat QUIET REQUIRED)" not in jsapi_cmake:
    raise SystemExit("JSAPIExample must retain a real Qt 5 component after compatibility filtering")

plugins_cmake = (ROOT / "plugins/CMakeLists.txt").read_text(encoding="utf-8")
openxr_entry = 'set(DIR "openxr")'
openxr_position = plugins_cmake.find(openxr_entry)
openxr_guard = plugins_cmake.rfind("if (NOT APPLE)", 0, openxr_position)
openxr_guard_end = plugins_cmake.find("endif()", openxr_position)
if (
    openxr_position < 0
    or openxr_guard < 0
    or openxr_guard_end < 0
    or plugins_cmake.find("endif()", openxr_guard, openxr_position) >= 0
):
    raise SystemExit("OpenXR must stay outside the macOS client build graph")

qt_compat = (ROOT / "cmake/QtCompat.cmake").read_text(encoding="utf-8")
if "macro(overte_find_qt)" not in qt_compat or "function(overte_find_qt)" in qt_compat:
    raise SystemExit("Qt discovery must preserve Qt 5 tool variables in the caller scope")

render_event_handler = (
    ROOT / "interface/src/graphics/RenderEventHandler.h"
).read_text(encoding="utf-8")
for required_include in ("<atomic>", "<QObject>"):
    if f"#include {required_include}" not in render_event_handler:
        raise SystemExit(
            f"RenderEventHandler must include {required_include} instead of relying on transitive includes"
        )

# Application's Pico state is deliberately absent from desktop builds. Check
# every member declared in its Pico-only header blocks instead of maintaining a
# hand-written list, so a newly added member cannot silently break macOS again.
application_header = (ROOT / "interface/src/Application.h").read_text(encoding="utf-8")
application_source = (ROOT / "interface/src/Application.cpp").read_text(encoding="utf-8")
pico_member_names = set()
inside_pico_declaration = False
for line in application_header.splitlines():
    directive = line.strip()
    if directive == "#if defined(ANDROID_APP_PICO_INTERFACE)":
        inside_pico_declaration = True
    elif inside_pico_declaration and directive.startswith("#endif"):
        inside_pico_declaration = False
    elif inside_pico_declaration:
        match = re.search(r"\b(_pico[A-Za-z0-9_]*)\s*(?:\{|;)", line)
        if match:
            pico_member_names.add(match.group(1))

pico_guard_stack = []
for line_number, line in enumerate(application_source.splitlines(), 1):
    directive = line.strip()
    if directive.startswith("#if"):
        parent_is_pico_only = pico_guard_stack[-1] if pico_guard_stack else False
        condition_is_pico_only = bool(re.search(
            r"(?:defined\s*\(\s*ANDROID_APP_PICO_INTERFACE\s*\)|"
            r"defined\s+ANDROID_APP_PICO_INTERFACE|ifdef\s+ANDROID_APP_PICO_INTERFACE)",
            directive,
        )) and "||" not in directive and not directive.startswith("#ifndef")
        pico_guard_stack.append(parent_is_pico_only or condition_is_pico_only)
        continue
    if directive.startswith("#elif"):
        parent_is_pico_only = pico_guard_stack[-2] if len(pico_guard_stack) > 1 else False
        condition_is_pico_only = (
            "ANDROID_APP_PICO_INTERFACE" in directive
            and "!defined" not in directive
            and "||" not in directive
        )
        pico_guard_stack[-1] = parent_is_pico_only or condition_is_pico_only
        continue
    if directive.startswith("#else"):
        parent_is_pico_only = pico_guard_stack[-2] if len(pico_guard_stack) > 1 else False
        pico_guard_stack[-1] = parent_is_pico_only
        continue
    if directive.startswith("#endif"):
        pico_guard_stack.pop()
        continue
    if pico_guard_stack and pico_guard_stack[-1]:
        continue
    for member_name in pico_member_names:
        if re.search(rf"\b{re.escape(member_name)}\b", line):
            raise SystemExit(
                f"Pico-only Application member {member_name} used outside its platform guard "
                f"at interface/src/Application.cpp:{line_number}"
            )

CONTRACT = {
    "serverless_import_committed": "interface/src/Application.cpp",
    "entity_tree_nonempty": "libraries/entities-renderer/src/EntityTreeRenderer.cpp",
    "render_handoff": "libraries/entities-renderer/src/EntityTreeRenderer.cpp",
}
ONLINE_CONTRACT = {
    "domain_list_connected": "libraries/networking/src/NodeList.cpp",
    "entity_server_active": "interface/src/Application.cpp",
    "entity_query_sent": "interface/src/Application_Entities.cpp",
    "entity_data_received": "interface/src/octree/OctreePacketProcessor.cpp",
}

for marker, relative in (CONTRACT | ONLINE_CONTRACT).items():
    source = (ROOT / relative).read_text(encoding="utf-8")
    token = f'"OVERTE_MACOS_ENTITY_GATE {marker}"'
    if source.count(token) != 1:
        raise SystemExit(f"expected exactly one {token} in {relative}")
    position = source.index(token)
    guard = source.rfind("#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)", 0, position)
    end = source.find("#endif", position)
    if guard < 0 or end < 0 or source.find("#endif", guard, position) >= 0:
        raise SystemExit(f"{marker} is not inside the desktop macOS guard")

smoke = (ROOT / "macos/ci/serverless-smoke.sh").read_text(encoding="utf-8")
for marker in CONTRACT:
    if marker not in smoke:
        raise SystemExit(f"smoke runner does not require {marker}")

online_smoke = (ROOT / "macos/ci/online-smoke.sh").read_text(encoding="utf-8")
for marker in ONLINE_CONTRACT | {"render_handoff": ""}:
    if marker not in online_smoke:
        raise SystemExit(f"online smoke runner does not require {marker}")

print("macOS runtime evidence contract valid")
