#!/usr/bin/env python3
"""Configure fixtures for the fail-closed rendering compatibility preflight."""

from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "ios/integration/RenderingCompatibilityPreflight.cmake"
INTEGRATION = (ROOT / "ios/integration/CMakeLists.txt").read_text()
TARGETS = ("qml", "vk", "gl", "display-plugins")
HEADERS = (
    "libraries/qml/src/qml/OffscreenSurface.h",
    "libraries/vk/src/vk/VKWidget.h",
    "libraries/gl/src/gl/OffscreenGLCanvas.h",
)

for anchor in (
    'include("${CMAKE_CURRENT_LIST_DIR}/RenderingCompatibilityPreflight.cmake")',
    "overte_add_ios_rendering_compatibility_preflight(overte-ios-rendering-compatibility)",
    "target_link_libraries(Overte overte-ios-rendering-compatibility)",
):
    if anchor not in INTEGRATION:
        raise SystemExit(f"integrated preflight binding missing: {anchor}")


def configure(source: Path, build: Path):
    return subprocess.run(
        ["cmake", "-S", str(source), "-B", str(build)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )


def fixture(directory: Path, targets=TARGETS, omit_header=None, add_definition=True):
    source_root = directory / "source"
    for header in HEADERS:
        if header != omit_header:
            path = source_root / header
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("// fixture\n")
    declarations = "\n".join(f"add_library({target} INTERFACE)" for target in targets)
    definition = "target_compile_definitions(display-plugins INTERFACE OVERTE_IOS_VULKAN_DISABLE_QUICK_GL_COPY=1)" if add_definition and "display-plugins" in targets else ""
    directory.joinpath("CMakeLists.txt").write_text(f'''cmake_minimum_required(VERSION 3.24)
project(RenderingCompatibilityPreflightTest LANGUAGES NONE)
{declarations}
{definition}
set(OVERTE_IOS_COMPAT_SOURCE_ROOT "{source_root.as_posix()}")
include("{MODULE.as_posix()}")
overte_add_ios_rendering_compatibility_preflight(overte-ios-rendering-compatibility)
get_target_property(audited overte-ios-rendering-compatibility OVERTE_IOS_RENDERING_COMPATIBILITY_AUDITED)
if(NOT audited)
  message(FATAL_ERROR "preflight target is not audited")
endif()
''')


def expect_failure(base: Path, name: str, expected: str, **kwargs):
    source = base / name
    source.mkdir()
    fixture(source, **kwargs)
    result = configure(source, base / f"{name}-build")
    if result.returncode == 0 or expected not in " ".join(result.stdout.split()):
        raise SystemExit(f"{name} did not fail closed as expected:\n{result.stdout}")


with tempfile.TemporaryDirectory(prefix="overte-ios-rendering-preflight-") as temporary:
    base = Path(temporary)
    passing = base / "passing"
    passing.mkdir()
    fixture(passing)
    result = configure(passing, base / "passing-build")
    if result.returncode:
        raise SystemExit("passing preflight fixture failed:\n" + result.stdout)

    expect_failure(base, "missing-target", "missing target(s): gl",
                   targets=("qml", "vk", "display-plugins"))
    expect_failure(base, "missing-header", "missing required public header: libraries/vk/src/vk/VKWidget.h",
                   omit_header="libraries/vk/src/vk/VKWidget.h")
    expect_failure(base, "missing-definition", "display-plugins lacks OVERTE_IOS_VULKAN_DISABLE_QUICK_GL_COPY=1",
                   add_definition=False)

print("iOS rendering compatibility CMake preflight valid: pass plus target/header/definition failures")
