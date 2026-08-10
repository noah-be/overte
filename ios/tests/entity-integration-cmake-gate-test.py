#!/usr/bin/env python3
"""Configure fixtures proving the iOS entity graph gate passes and fails closed."""

import pathlib
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE = ROOT / "ios/integration/EntityIntegrationGate.cmake"
REQUIRED = ("networking", "octree", "entities", "entities-renderer")


def configure(source: pathlib.Path, build: pathlib.Path):
    return subprocess.run(
        ["cmake", "-S", str(source), "-B", str(build)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def write_fixture(directory: pathlib.Path, targets):
    declarations = "\n".join(f"add_library({name} INTERFACE)" for name in targets)
    required = ";".join(REQUIRED)
    directory.joinpath("CMakeLists.txt").write_text(
        f'''cmake_minimum_required(VERSION 3.24)
project(EntityIntegrationGateTest LANGUAGES NONE)
{declarations}
include("{MODULE.as_posix()}")
overte_add_ios_entity_integration_gate(overte-ios-entity-integration)
get_target_property(actual overte-ios-entity-integration INTERFACE_LINK_LIBRARIES)
set(expected "{required}")
if(NOT actual STREQUAL expected)
  message(FATAL_ERROR "unexpected integration links: '${{actual}}'")
endif()
get_target_property(audited overte-ios-entity-integration OVERTE_IOS_ENTITY_INTEGRATION_AUDITED)
if(NOT audited)
  message(FATAL_ERROR "integration target is not marked audited")
endif()
''',
        encoding="utf-8",
    )


with tempfile.TemporaryDirectory(prefix="overte-ios-entity-gate-") as temporary:
    base = pathlib.Path(temporary)
    passing = base / "passing"
    passing.mkdir()
    write_fixture(passing, REQUIRED)
    passed = configure(passing, base / "passing-build")
    if passed.returncode:
        raise SystemExit("passing fixture failed:\n" + passed.stdout)

    failing = base / "failing"
    failing.mkdir()
    write_fixture(failing, REQUIRED[:-1])
    failed = configure(failing, base / "failing-build")
    normalized_output = " ".join(failed.stdout.split())
    expected_error = "missing native Overte target(s): entities-renderer"
    if failed.returncode == 0 or expected_error not in normalized_output:
        raise SystemExit("gate did not fail closed as expected:\n" + failed.stdout)

print("iOS entity CMake gate valid: binds 4 targets and fails closed when one is missing")
