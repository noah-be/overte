#!/usr/bin/env python3
"""Configure and source contracts for statically registered iOS codecs."""

from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "cmake/macros/SetupHifiClientServerPlugin.cmake"
MACRO = MODULE.read_text()
IMPORTS = (ROOT / "interface/src/IOSStaticCodecPlugins.cpp").read_text()
MANAGER = (ROOT / "libraries/plugins/src/plugins/PluginManager.cpp").read_text()
PCM = (ROOT / "plugins/pcmCodec/CMakeLists.txt").read_text()
OPUS = (ROOT / "plugins/opusCodec/CMakeLists.txt").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


for anchor in (
    "set(${TARGET_NAME}_SHARED 0)",
    "target_compile_definitions(${TARGET_NAME} PRIVATE QT_STATICPLUGIN)",
    '"$<LINK_LIBRARY:WHOLE_ARCHIVE,${TARGET_NAME}>"',
    "OVERTE_IOS_STATIC_PLUGIN_AUDITED TRUE",
    "if (NOT IOS)",
):
    require(anchor in MACRO, f"static codec macro contract missing {anchor}")
require("Contents/PlugIns" in MACRO and "if (APPLE AND NOT IOS)" in MACRO,
        "macOS plugin path is not excluded on iOS")
require("Q_IMPORT_PLUGIN(PCMCodecProvider)" in IMPORTS and
        "Q_IMPORT_PLUGIN(AthenaOpusCodecProvider)" in IMPORTS,
        "static codec imports are incomplete")
require("QPluginLoader::staticInstances()" in MANAGER and "#if defined(Q_OS_IOS)" in MANAGER,
        "PluginManager does not enumerate static iOS providers")
require("qobject_cast<CodecProvider*>(instance)" in MANAGER,
        "static providers are not filtered through the codec interface")
require("#else\n        // Now grab the dynamic plugins" in MANAGER,
        "dynamic plugin loading is not retained exclusively in the non-iOS branch")
require("never scan the application bundle" in MANAGER,
        "iOS filesystem plugin scanning is not fail-closed")
require("OVERTE_IOS_STATIC_PLUGIN_CLASS PCMCodecProvider" in PCM,
        "PCM provider class declaration missing")
require("OVERTE_IOS_STATIC_PLUGIN_CLASS AthenaOpusCodecProvider" in OPUS,
        "Opus provider class declaration missing")


def configure(source: Path, build: Path):
    return subprocess.run(["cmake", "-S", str(source), "-B", str(build)],
                          text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, check=False)


def fixture(directory: Path, *, ios=True, apple=False, android=False,
            create_overte=True, plugin_class="FixtureProvider"):
    (directory / "dummy.cpp").write_text("int fixture_symbol = 0;\n")
    app_target = "Overte" if apple or ios else "interface"
    overte = f"add_executable({app_target} dummy.cpp)" if create_overte else ""
    class_decl = f'set(OVERTE_IOS_STATIC_PLUGIN_CLASS "{plugin_class}")' if plugin_class else ""
    expected_kind = "STATIC_LIBRARY" if ios else "SHARED_LIBRARY"
    (directory / "CMakeLists.txt").write_text(f'''cmake_minimum_required(VERSION 3.24)
project(StaticCodecFixture LANGUAGES CXX)
set(IOS {str(ios).upper()})
set(APPLE {str(apple).upper()})
set(ANDROID {str(android).upper()})
set(OVERTE_BUILD_CLIENT TRUE)
{overte}
function(setup_hifi_library)
  if(${{${{TARGET_NAME}}_SHARED}})
    add_library(${{TARGET_NAME}} SHARED dummy.cpp)
  else()
    add_library(${{TARGET_NAME}} STATIC dummy.cpp)
  endif()
endfunction()
set(TARGET_NAME fixtureCodec)
{class_decl}
include("{MODULE.as_posix()}")
setup_hifi_client_server_plugin()
get_target_property(kind fixtureCodec TYPE)
if(NOT kind STREQUAL "{expected_kind}")
  message(FATAL_ERROR "unexpected codec target type: ${{kind}}")
endif()
if(IOS)
get_target_property(defs fixtureCodec COMPILE_DEFINITIONS)
if(NOT "QT_STATICPLUGIN" IN_LIST defs)
  message(FATAL_ERROR "QT_STATICPLUGIN missing")
endif()
get_target_property(audited fixtureCodec OVERTE_IOS_STATIC_PLUGIN_AUDITED)
if(NOT audited)
  message(FATAL_ERROR "static codec target not audited")
endif()
get_target_property(links Overte LINK_LIBRARIES)
if(NOT "$<LINK_LIBRARY:WHOLE_ARCHIVE,fixtureCodec>" IN_LIST links)
  message(FATAL_ERROR "whole-archive link missing: ${{links}}")
endif()
endif()
''')


with tempfile.TemporaryDirectory(prefix="overte-ios-static-codec-") as temporary:
    base = Path(temporary)
    passing = base / "passing"
    passing.mkdir()
    fixture(passing)
    result = configure(passing, base / "passing-build")
    require(result.returncode == 0, "passing codec fixture failed:\n" + result.stdout)

    for name, kwargs in (
        ("macos-shared", {"ios": False, "apple": True}),
        ("android-shared", {"ios": False, "android": True}),
    ):
        source = base / name
        source.mkdir()
        fixture(source, **kwargs)
        result = configure(source, base / f"{name}-build")
        require(result.returncode == 0, f"{name} regression fixture failed:\n{result.stdout}")

    for name, kwargs, error in (
        ("missing-overte", {"create_overte": False}, "requires the Overte application target"),
        ("missing-class", {"plugin_class": ""}, "must declare OVERTE_IOS_STATIC_PLUGIN_CLASS"),
    ):
        source = base / name
        source.mkdir()
        fixture(source, **kwargs)
        result = configure(source, base / f"{name}-build")
        require(result.returncode != 0 and error in " ".join(result.stdout.split()),
                f"{name} did not fail closed:\n{result.stdout}")

print("iOS static codec contract valid: static+whole-archive+imports; macOS/Android shared; two failures")
