#!/usr/bin/env python3
"""Exercise runtime bundle staging through real CMake/Ninja incrementality."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile


with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary_name:
    temporary = Path(temporary_name)
    source = temporary / "source"
    build = temporary / "build"
    scripts = source / "scripts/system"
    fonts = source / "interface/resources/fonts"
    serverless = source / "interface/resources/serverless"
    jsdoc = source / "jsdoc"
    for directory in (scripts, fonts, serverless, jsdoc):
        directory.mkdir(parents=True)
    (scripts / "runtime.js").write_text("runtime-v1", encoding="utf-8")
    old_font = fonts / "old.ttf"
    old_font.write_text("font-v1", encoding="utf-8")
    old_scene = serverless / "old.json"
    old_scene.write_text("scene-v1", encoding="utf-8")
    (jsdoc / "index.json").write_text("docs-v1", encoding="utf-8")
    (source / "main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    (source / "CMakeLists.txt").write_text(
        """cmake_minimum_required(VERSION 3.16)
project(RuntimeStagingContract C)
option(JSDOC_ENABLED "stage generated docs" OFF)
add_executable(interface main.c)
set(RESOURCES_DEV_DIR "${CMAKE_BINARY_DIR}/Overte.app/Contents/Resources")
file(GLOB_RECURSE MACOS_RUNTIME_BUNDLE_FILES CONFIGURE_DEPENDS
  "${CMAKE_SOURCE_DIR}/scripts/*"
  "${CMAKE_SOURCE_DIR}/interface/resources/fonts/*"
  "${CMAKE_SOURCE_DIR}/interface/resources/serverless/*")
set_property(TARGET interface APPEND PROPERTY
  LINK_DEPENDS ${MACOS_RUNTIME_BUNDLE_FILES})
add_custom_command(TARGET interface POST_BUILD
  COMMAND "${CMAKE_COMMAND}" -E remove_directory "${RESOURCES_DEV_DIR}/scripts"
  COMMAND "${CMAKE_COMMAND}" -E copy_directory
    "${CMAKE_SOURCE_DIR}/scripts" "${RESOURCES_DEV_DIR}/scripts"
  COMMAND "${CMAKE_COMMAND}" -E remove_directory "${RESOURCES_DEV_DIR}/fonts"
  COMMAND "${CMAKE_COMMAND}" -E copy_directory
    "${CMAKE_SOURCE_DIR}/interface/resources/fonts" "${RESOURCES_DEV_DIR}/fonts"
  COMMAND "${CMAKE_COMMAND}" -E remove_directory "${RESOURCES_DEV_DIR}/serverless"
  COMMAND "${CMAKE_COMMAND}" -E copy_directory
    "${CMAKE_SOURCE_DIR}/interface/resources/serverless" "${RESOURCES_DEV_DIR}/serverless"
  COMMAND "${CMAKE_COMMAND}" -E remove_directory "${RESOURCES_DEV_DIR}/jsdoc")
if (JSDOC_ENABLED)
  add_custom_command(TARGET interface POST_BUILD
    COMMAND "${CMAKE_COMMAND}" -E copy_directory
      "${CMAKE_SOURCE_DIR}/jsdoc" "${RESOURCES_DEV_DIR}/jsdoc")
endif()
""",
        encoding="utf-8",
    )

    def run(*command: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command, text=True, capture_output=True, check=False
        )

    configured = run(
        "cmake", "-S", str(source), "-B", str(build), "-G", "Ninja",
        "-DJSDOC_ENABLED=ON",
    )
    assert configured.returncode == 0, configured.stdout + configured.stderr
    first = run("cmake", "--build", str(build), "--target", "interface")
    assert first.returncode == 0, first.stdout + first.stderr
    staged = build / "Overte.app/Contents/Resources"
    assert (staged / "scripts/system/runtime.js").read_text(encoding="utf-8") == "runtime-v1"
    assert (staged / "fonts/old.ttf").is_file()
    assert (staged / "serverless/old.json").is_file()
    assert (staged / "jsdoc/index.json").is_file()

    # Existing-file edits are direct LINK_DEPENDS changes.
    runtime_script = scripts / "runtime.js"
    runtime_script.write_text("runtime-v2", encoding="utf-8")
    future = runtime_script.stat().st_mtime + 2
    os.utime(runtime_script, (future, future))
    edited = run("cmake", "--build", str(build), "--target", "interface")
    assert edited.returncode == 0, edited.stdout + edited.stderr
    assert (staged / "scripts/system/runtime.js").read_text(encoding="utf-8") == "runtime-v2"

    # CONFIGURE_DEPENDS must detect additions/removals; mirror staging must not
    # retain either deleted runtime payload after the regenerated build.
    old_font.unlink()
    old_scene.unlink()
    new_font = fonts / "new.ttf"
    new_font.write_text("font-v2", encoding="utf-8")
    changed_inventory = run("cmake", "--build", str(build), "--target", "interface")
    assert changed_inventory.returncode == 0, changed_inventory.stdout + changed_inventory.stderr
    assert not (staged / "fonts/old.ttf").exists()
    assert not (staged / "serverless/old.json").exists()
    assert (staged / "fonts/new.ttf").read_text(encoding="utf-8") == "font-v2"

    disabled_docs = run(
        "cmake", "-S", str(source), "-B", str(build), "-G", "Ninja",
        "-DJSDOC_ENABLED=OFF",
    )
    assert disabled_docs.returncode == 0, disabled_docs.stdout + disabled_docs.stderr
    rebuilt_without_docs = run("cmake", "--build", str(build), "--target", "interface")
    assert rebuilt_without_docs.returncode == 0, rebuilt_without_docs.stdout + rebuilt_without_docs.stderr
    assert not (staged / "jsdoc").exists(), "JSDoc ON-to-OFF transition retained stale files"

print("macOS runtime bundle staging incrementality contract valid")
