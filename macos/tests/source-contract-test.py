#!/usr/bin/env python3
"""Validate the macOS bootstrap's runtime evidence contract."""

from pathlib import Path
import json
import os
import re
import subprocess
import sys

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
    "Node per-object compiler watchdog": (
        libnode_recipe,
        'watchdog = os.environ.get("OVERTE_COMPILER_WATCHDOG", "")',
    ),
    "Node C compiler watchdog": (
        libnode_recipe,
        '"CC", shlex.join([watchdog, "--", c_compiler])',
    ),
    "Node C++ compiler watchdog": (
        libnode_recipe,
        '"CXX", shlex.join([watchdog, "--", cxx_compiler])',
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

for native_test_contract in (
    'build_tests="${OVERTE_MACOS_BUILD_TESTS:-OFF}"',
    "OVERTE_MACOS_BUILD_TESTS must be ON or OFF",
    '-DOVERTE_BUILD_TESTS="$build_tests"',
):
    if native_test_contract not in build_script:
        raise SystemExit(f"macOS native test build contract missing: {native_test_contract}")

native_runner = (ROOT / "tests/project-native-test.sh").read_text(encoding="utf-8")
for native_runtime_contract in (
    '"$(uname -s)" == "Darwin"',
    'conan_dylib_dir="$BUILD_DIR/conanlibs/$BUILD_CONFIG"',
    'export DYLD_LIBRARY_PATH="$conan_dylib_dir${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"',
):
    if native_runtime_contract not in native_runner:
        raise SystemExit(f"macOS native dylib lookup contract missing: {native_runtime_contract}")

application_source = (ROOT / "interface/src/Application.cpp").read_text(encoding="utf-8")
shutdown = application_source.split("void Application::cleanupBeforeQuit()", 1)[1].split(
    "static const float FOCUS_HIGHLIGHT_EXPANSION_FACTOR", 1
)[0]
shutdown_order = (
    "getEntities()->shutdown()",
    "shutdownScripting()",
    "QThreadPool::globalInstance()->clear()",
    "QThreadPool::globalInstance()->waitForDone()",
    "DependencyManager::destroy<EntityTreeRenderer>()",
    "DependencyManager::destroy<ScriptEngines>()",
)
if any(token not in shutdown for token in shutdown_order):
    raise SystemExit("application shutdown dependency contract is incomplete")
if [shutdown.index(token) for token in shutdown_order] != sorted(
    shutdown.index(token) for token in shutdown_order
):
    raise SystemExit("scripts must stop before pooled cleanup and dependency destruction")

entity_renderer = (ROOT / "libraries/entities-renderer/src/EntityTreeRenderer.cpp").read_text(
    encoding="utf-8"
)
entity_scheduling_policy = (
    ROOT / "libraries/entities-renderer/src/EntitySchedulingPolicy.h"
).read_text(encoding="utf-8")
safe_landing_source = (ROOT / "interface/src/octree/SafeLanding.cpp").read_text(
    encoding="utf-8"
)
for scheduling_contract in (
    "safeLandingLoadPriority(bool collisionless)",
    "collisionless ? 0.0f : COLLIDABLE_ENTITY_LOAD_PRIORITY",
    "MAX_UNBUDGETED_RENDERABLE_UPDATES { 16 }",
    "pendingCount <= MAX_UNBUDGETED_RENDERABLE_UPDATES",
    "expectedCostUsec < static_cast<float>(budgetUsec)",
):
    if scheduling_contract not in entity_scheduling_policy:
        raise SystemExit(f"entity scheduling policy missing: {scheduling_contract}")
if "EntitySchedulingPolicy::safeLandingLoadPriority(entityItem.getCollisionless())" not in safe_landing_source:
    raise SystemExit("Safe Landing must use the tested collidable-first loading policy")
if "entityItem.getCollisionless() *" in safe_landing_source:
    raise SystemExit("Safe Landing must not invert collidable loading priority")
if "EntitySchedulingPolicy::shouldUseUnbudgetedRenderableUpdate(" not in entity_renderer:
    raise SystemExit("all platforms must use the tested renderable update budget policy")
if "const bool smallEnoughForUnbudgetedUpdate = true" in entity_renderer:
    raise SystemExit("desktop renderable batches must not bypass the update-count bound")
scheduling_test = (
    ROOT / "tests/entities-renderer/src/EntitySchedulingPolicyTests.cpp"
).read_text(encoding="utf-8")
for boundary_contract in (
    "safeLandingLoadPriority(false)",
    "safeLandingLoadPriority(true)",
    "shouldUseUnbudgetedRenderableUpdate(1999.0f, 16, 2000)",
    "shouldUseUnbudgetedRenderableUpdate(0.0f, 17, 2000)",
    "shouldUseUnbudgetedRenderableUpdate(2000.0f, 1, 2000)",
):
    if boundary_contract not in scheduling_test:
        raise SystemExit(f"entity scheduling boundary test missing: {boundary_contract}")
entity_shutdown = entity_renderer.split("void EntityTreeRenderer::clear()", 1)[1].split(
    "void EntityTreeRenderer::reloadEntityScripts()", 1
)[0]
if entity_shutdown.count("unloadAllEntityScripts(false)") != 2:
    raise SystemExit("application shutdown must queue both entity-script unload operations")
if "unloadAllEntityScripts(true)" in entity_shutdown:
    raise SystemExit("application shutdown must not block the main thread on entity-script unload")

shader_test_header = (ROOT / "tests/gpu/src/ShaderLoadTest.h").read_text(encoding="utf-8")
shader_test_source = (ROOT / "tests/gpu/src/ShaderLoadTest.cpp").read_text(encoding="utf-8")
if "#include <test-utils/Utils.h>" not in shader_test_source:
    raise SystemExit("shader test must include the declaration for installTestMessageHandler")
if "backend->syncProgram(program);" not in shader_test_source or "return false;" in shader_test_source.split(
    "bool ShaderLoadTest::buildProgram", 1
)[1].split("void ShaderLoadTest::initTestCase", 1)[0]:
    raise SystemExit("shader tests must compile programs through the current GL backend")
for shader_cache_contract in (
    "shader::gpu::program::DrawTexture",
    "shader::Source::get(shader::getVertexId(programId))",
    "shader::Source::get(shader::getFragmentId(programId))",
    "expectedBinaryLoads",
    "gpuBinaryShadersLoaded.load()",
    "GL_NUM_PROGRAM_BINARY_FORMATS",
    "Shader cache was not persisted to disk",
):
    if shader_cache_contract not in shader_test_source:
        raise SystemExit(f"current production shader cache test contract missing: {shader_cache_contract}")
for retired_shader_contract in (
    "Source::generate",
    "Test no longer compatible with current code",
    "parseCacheFile",
):
    if retired_shader_contract in shader_test_source:
        raise SystemExit(f"shader tests retain obsolete source handling: {retired_shader_contract}")
shader_source_api = (ROOT / "libraries/shaders/src/shaders/Shaders.h").read_text(
    encoding="utf-8"
)
if 'runtime_error("Implement me")' in shader_source_api:
    raise SystemExit("public shader source API must not expose an unimplemented factory")

texture_test = (ROOT / "tests/gpu/src/TextureTest.cpp").read_text(encoding="utf-8")
for forbidden_texture_dependency in ("ExternalResource", "test_ktx.zip", "downloadFile("):
    if forbidden_texture_dependency in texture_test:
        raise SystemExit("texture tests must not depend on the retired network fixture")
for texture_contract in ("cube_texture.png", "gpu::Texture::serialize", "cube_texture.ktx"):
    if texture_contract not in texture_test and texture_contract not in (
        ROOT / "tests/gpu/CMakeLists.txt"
    ).read_text(encoding="utf-8"):
        raise SystemExit(f"deterministic texture fixture contract missing: {texture_contract}")
if "#include <ktx/KTX.h>" not in texture_test:
    raise SystemExit("texture serialization test must bind the complete KTX type")
if "gpu::Shader::createProgram(shader::gpu::program::drawUnitQuatTextureOpaque)" not in texture_test:
    raise SystemExit("texture test must exercise the generated production texture program")
if "Source::generate" in texture_test:
    raise SystemExit("texture test must not call the retired raw shader factory")
if not re.search(
    r"process2DTextureColorFromImage\(\s*std::move\(image\),\s*"
    r"imagePath\.toStdString\(\),\s*false,\s*gpu::BackendTarget::GL41,\s*"
    r"false,\s*abortSignal\s*\)",
    texture_test,
):
    raise SystemExit(
        "texture test fixture must be an uncompressed managed GL41 resource"
    )
for managed_texture_contract in (
    "getUsageType() == gpu::TextureUsageType::RESOURCE",
    "gpu::Texture::setAllowedGPUMemoryUsage(0);",
):
    if managed_texture_contract not in texture_test:
        raise SystemExit(
            f"managed texture test isolation missing: {managed_texture_contract}"
        )
texture_cleanup = texture_test.split("void TextureTest::cleanupTestCase()", 1)[1].split(
    "std::vector<", 1
)[0]
for cleanup_contract in (
    "_gpuContext->recycle();",
    "_gpuContext->shutdown();",
    "_gpuContext.reset();",
):
    if cleanup_contract not in texture_cleanup:
        raise SystemExit(f"texture test backend cleanup missing: {cleanup_contract}")
if not (
    texture_cleanup.index("_gpuContext->recycle();")
    < texture_cleanup.index("_gpuContext->shutdown();")
    < texture_cleanup.index("_gpuContext.reset();")
):
    raise SystemExit("texture test must stop the transfer engine before backend release")
if texture_test.count("QVERIFY2(!afterSecs(start, FAIL_AFTER_SECONDS)") != 5:
    raise SystemExit("every texture-memory wait must fail from the calling test")
clear_wait = texture_test.split("textures.clear();", 1)[1].split("reportLambda();", 1)[0]
clear_timer_reset = clear_wait.find("start = usecTimestampNow();")
clear_loop = clear_wait.find("while (allocatedMemory != 0)")
if clear_timer_reset < 0 or clear_loop < 0 or clear_timer_reset > clear_loop:
    raise SystemExit("released-texture wait must have an independent timeout")
if "failAfter(" in texture_test or "failAfter(" in (
    ROOT / "libraries/test-utils/src/test-utils/QTestExtensions.h"
).read_text(encoding="utf-8"):
    raise SystemExit("test timeouts must not return only from an inline helper")
gl_shader_source = (ROOT / "libraries/gl/src/gl/GLShaders.cpp").read_text(
    encoding="utf-8"
)
if "GL_PROGRAM_BINARY_RETRIEVABLE_HINT, GL_TRUE" not in gl_shader_source:
    raise SystemExit("shader programs must opt in to retrievable binary checkpoints before linking")

audio_test = (ROOT / "tests/audio/src/AudioTests.cpp").read_text(encoding="utf-8")
typed_audio_spy = "QSignalSpy spy(ac.get(), &AudioClient::devicesChanged);"
if typed_audio_spy not in audio_test or "qvariant_cast<HifiAudioDeviceMode>" not in audio_test:
    raise SystemExit("audio device tests must follow the current typed device signal")
if "SIGNAL(devicesChanged(QAudio::Mode" in audio_test:
    raise SystemExit("audio device tests retain the retired QAudio::Mode signal signature")
if audio_test.index("ac->startThread();") < audio_test.index(typed_audio_spy):
    raise SystemExit("audio tests must validate their signal observer before starting async audio")
if "QSKIP(" not in audio_test:
    raise SystemExit("audio device enumeration must tolerate a runner without audio hardware")
if 'qDebug() << "Mode:" << static_cast<int>(mode);' not in audio_test:
    raise SystemExit("audio device tests must log the scoped device mode portably")

audio_cmake = (ROOT / "tests/audio/CMakeLists.txt").read_text(encoding="utf-8")
codec_test = (ROOT / "tests/audio/src/CodecTests.cpp").read_text(encoding="utf-8")
for codec_deployment_contract in (
    "add_dependencies(${TARGET_NAME} pcmCodec opusCodec)",
    "$<TARGET_FILE_DIR:${TARGET_NAME}>/../PlugIns",
    "$<TARGET_FILE:pcmCodec>",
    "$<TARGET_FILE:opusCodec>",
):
    if codec_deployment_contract not in audio_cmake:
        raise SystemExit(f"codec test deployment contract missing: {codec_deployment_contract}")
for codec_runtime_contract in (
    'testPath.filePath("../PlugIns")',
    "QVERIFY(decoder != nullptr)",
    "plugin->releaseEncoder(encoder)",
    "plugin->releaseDecoder(decoder)",
):
    if codec_runtime_contract not in codec_test:
        raise SystemExit(f"codec test runtime contract missing: {codec_runtime_contract}")
if "QFile::link" in codec_test:
    raise SystemExit("codec tests must not manufacture runtime plugin symlinks")

animation_test = (ROOT / "tests/animation/src/AnimTests.cpp").read_text(encoding="utf-8")
animation_resources = (
    ROOT / "tests/animation/src/animation-test-data.qrc"
).read_text(encoding="utf-8")
if 'QUrl url("qrc:/animation-tests/test.json")' not in animation_test:
    raise SystemExit("animation loader tests must use their deterministic embedded fixture")
if "gist.githubusercontent.com" in animation_test:
    raise SystemExit("animation unit tests must not depend on a mutable remote gist")
for animation_resource_contract in (
    '<qresource prefix="/animation-tests">',
    '<file alias="test.json">data/test.json</file>',
):
    if animation_resource_contract not in animation_resources:
        raise SystemExit(
            f"animation loader fixture resource missing: {animation_resource_contract}"
        )

ktx_benchmark = (ROOT / "tests/ktx/src/KtxBenchmarkTests.cpp").read_text(encoding="utf-8")
ktx_cmake = (ROOT / "tests/ktx/CMakeLists.txt").read_text(encoding="utf-8")
if "OVERTE_TEST_SOURCE_ROOT" not in ktx_benchmark or "OVERTE_TEST_SOURCE_ROOT" not in ktx_cmake:
    raise SystemExit("KTX benchmarks must resolve fixtures from the configured source root")
if "parent.currentPath()" in ktx_benchmark:
    raise SystemExit("KTX benchmarks must not derive source fixtures from the process cwd")
for forbidden_ktx_fixture in ("/interface/scripts/", "scripts/system/appreciate/appreciate.jpg"):
    if forbidden_ktx_fixture in ktx_benchmark:
        raise SystemExit(f"KTX benchmark retains a retired fixture path: {forbidden_ktx_fixture}")
ktx_fixtures = (
    "scripts/developer/tests/cube_texture.png",
    "scripts/system/assets/images/materials/GridPattern.png",
    "scripts/simplifiedUI/simplifiedEmote/emojiApp/resources/images/emojis/512px/1f92c.png",
    "scripts/system/assets/images/Particle-Sprite-Smoke-1.png",
    "scripts/system/assets/images/grabsprite-3.png",
    "scripts/system/html/img/snapshotIcon.png",
    "interface/resources/snapshot/img/no-image.jpg",
    "scripts/system/assets/images/textures/dirt.jpeg",
)
for fixture in ktx_fixtures:
    if f'"{fixture}"' not in ktx_benchmark or not (ROOT / fixture).is_file():
        raise SystemExit(f"KTX benchmark fixture is missing or not tracked by its source: {fixture}")
for ktx_fixture_contract in (
    "QDir(getRootPath()).filePath(relativePath)",
    "QVERIFY2(!image.isNull()",
):
    if ktx_fixture_contract not in ktx_benchmark:
        raise SystemExit(f"KTX benchmark fixture validation missing: {ktx_fixture_contract}")

offscreen_canvas = (ROOT / "libraries/gl/src/gl/OffscreenGLCanvas.cpp").read_text(
    encoding="utf-8"
)
offscreen_make_current = offscreen_canvas.split(
    "bool OffscreenGLCanvas::makeCurrent()", 1
)[1].split("void OffscreenGLCanvas::doneCurrent()", 1)[0]
if not (
    offscreen_make_current.count("gl::initModuleGl();") == 1
    and offscreen_make_current.index("gl::initModuleGl();")
    < offscreen_make_current.index("gl::ContextInfo().init()")
):
    raise SystemExit("offscreen contexts must initialize GLAD before querying context information")

standalone_graphics_defaults = (
    ROOT / "libraries/shared/src/shared/GlobalAppProperties.cpp"
).read_text(encoding="utf-8")
if not re.search(
    r"#if defined\(Q_OS_MAC\) && !defined\(Q_OS_IOS\).*?"
    r"GRAPHICS_API \{ GraphicsAPI::GL41 \};.*?#else.*?"
    r"GRAPHICS_API \{ GraphicsAPI::GL45 \};",
    standalone_graphics_defaults,
    re.DOTALL,
):
    raise SystemExit("standalone desktop-macOS programs must default to OpenGL 4.1")

gltf_serializer = (ROOT / "libraries/model-serializers/src/GLTFSerializer.cpp").read_text(
    encoding="utf-8"
)
for gltf_contract in (
    "primitive.type != cgltf_primitive_type_triangles",
    "if (primitive.indices == nullptr)",
    "std::iota(indices.begin(), indices.end(), 0)",
):
    if gltf_contract not in gltf_serializer:
        raise SystemExit(f"non-indexed glTF triangle contract missing: {gltf_contract}")

if 'copy(self, "*.dylib*", src, bindir, False)' not in root_recipe:
    raise SystemExit("Conan deployment must collect versioned macOS dylibs")

fixup_interface = (ROOT / "cmake/macros/FixupInterface.cmake").read_text(encoding="utf-8")
if "if (NOT MACDEPLOYQT_COMMAND)" not in fixup_interface:
    raise SystemExit("all macOS bundles must fail closed when macdeployqt is unavailable")
for qt_core_dir in ("Qt5Core_DIR", "Qt6Core_DIR"):
    if qt_core_dir not in fixup_interface:
        raise SystemExit(f"macdeployqt discovery must support {qt_core_dir}")
subprocess.run(
    ["cmake", "-P", str(ROOT / "macos/tests/macdeployqt-discovery-test.cmake")],
    cwd=ROOT,
    check=True,
)

graphics_engine = (ROOT / "interface/src/graphics/GraphicsEngine.cpp").read_text(
    encoding="utf-8"
)
warmup = graphics_engine.split("void GraphicsEngine::initializeGPU", 1)[1].split(
    "DependencyManager::get<TextureCache>", 1
)[0]
for warmup_contract in (
    "GL_RENDERER",
    "Apple Software Renderer",
    "shader_warmup_skipped",
    "_programsCompiled.store(true)",
    "pushProgramsToSync(startupPrograms",
):
    if warmup_contract not in warmup:
        raise SystemExit(f"macOS software renderer warmup contract missing: {warmup_contract}")
if warmup.index("shader_warmup_skipped") > warmup.index("pushProgramsToSync"):
    raise SystemExit("software-renderer warmup bypass must precede eager compilation")

deploy_tool = (ROOT / "macos/tools/deploy-conan-dylibs.py").read_text(encoding="utf-8")
bundle_verify = (ROOT / "macos/ci/verify-glad-linkage.sh").read_text(encoding="utf-8")
for webengine_contract in (
    "QtWebEngineProcess.app/Contents/MacOS/QtWebEngineProcess",
    "@executable_path/../../../../..",
    "QtGui.framework/Versions/5/QtGui",
):
    if webengine_contract not in deploy_tool or webengine_contract not in bundle_verify:
        raise SystemExit(f"QtWebEngine bundle contract missing: {webengine_contract}")
if not re.search(
    r'OVERTE_RELEASE_TYPE STREQUAL "DEV".*?add_custom_command\(TARGET \$\{TARGET_NAME\} POST_BUILD.*?MACDEPLOYQT_COMMAND',
    fixup_interface,
    re.DOTALL,
):
    raise SystemExit("macOS DEV bundles must run macdeployqt before direct launch")
if '"-libpath=${CMAKE_BINARY_DIR}/conanlibs/$<CONFIG>"' not in fixup_interface:
    raise SystemExit("macdeployqt must search the collected versioned Conan dylibs")
if fixup_interface.count('macos/tools/deploy-conan-dylibs.py') != 2:
    raise SystemExit("every macOS post-build deployment must rewrite collected Conan dylibs")
subprocess.run(
    [sys.executable, str(ROOT / "macos/tests/deploy-conan-dylibs-test.py")],
    cwd=ROOT,
    check=True,
)

package_libraries = (
    ROOT / "cmake/macros/PackageLibrariesForDeployment.cmake"
).read_text(encoding="utf-8")
if "if (APPLE)" in package_libraries:
    raise SystemExit("macOS bundles must not run BundleUtilities after macdeployqt")

compiler_cmake = (ROOT / "cmake/compiler.cmake").read_text(encoding="utf-8")
if (
    "exec_program(" in compiler_cmake
    or "COMMAND sw_vers -productVersion" not in compiler_cmake
    or "OUTPUT_STRIP_TRAILING_WHITESPACE" not in compiler_cmake
    or "RESULT_VARIABLE _SW_VERS_RESULT" not in compiler_cmake
):
    raise SystemExit("macOS version detection must use execute_process, not removed exec_program")

gl_config = (ROOT / "libraries/gl/src/gl/Config.cpp").read_text(encoding="utf-8")
public_framework = '"/System/Library/Frameworks/OpenGL.framework/OpenGL"'
legacy_framework = '"/System/Library/Frameworks/OpenGL.framework/Versions/Current/OpenGL"'
if public_framework not in gl_config or legacy_framework not in gl_config:
    raise SystemExit("macOS GLAD loader must support current and legacy OpenGL framework paths")
if gl_config.index(public_framework) > gl_config.index(legacy_framework):
    raise SystemExit("macOS GLAD loader must prefer the public framework path")
if "return GL_LIB ? dlsym(GL_LIB, namez) : nullptr;" not in gl_config:
    raise SystemExit("macOS GLAD loader must not call dlsym with a failed framework handle")
if not re.search(r"loadedVersion.*?gladLoadGLLoader.*?if \(loadedVersion == 0\).*?qFatal", gl_config, re.DOTALL):
    raise SystemExit("GLAD initialization must fail closed when entry-point loading fails")

gl_helpers = (ROOT / "libraries/gl/src/gl/GLHelpers.cpp").read_text(encoding="utf-8")
khr_debug_helper = gl_helpers.split("bool khrDebugEnabled()", 1)[1].split(
    "bool extDebugMarkerEnabled()", 1
)[0]
for token in (
    "GLAD_GL_KHR_debug",
    "glad_glPushDebugGroupKHR",
    "glad_glPopDebugGroupKHR",
):
    if token not in khr_debug_helper:
        raise SystemExit(f"KHR debug availability must check raw GLAD state: {token}")
if "nullptr != glPushDebugGroupKHR" in khr_debug_helper:
    raise SystemExit("KHR debug availability must not test GLAD's always-present debug wrapper")

ext_debug_helper = gl_helpers.split("bool extDebugMarkerEnabled()", 1)[1].split(
    "bool debugContextEnabled()", 1
)[0]
for token in (
    "GLAD_GL_EXT_debug_marker",
    "glad_glPushGroupMarkerEXT",
    "glad_glPopGroupMarkerEXT",
):
    if token not in ext_debug_helper:
        raise SystemExit(f"EXT debug marker availability must check raw GLAD state: {token}")
if "nullptr != glPushGroupMarkerEXT" in ext_debug_helper:
    raise SystemExit("EXT debug availability must not test GLAD's always-present debug wrapper")

conanfile = (ROOT / "conanfile.py").read_text(encoding="utf-8")
if not re.search(
    r'glad_options\s*=\s*\{"shared": True\}\s+if\s+self\.settings\.os\s*==\s*"Macos"\s+else\s*\{\}.*?'
    r'self\.requires\(\s*"glad/0\.1\.36@overte/experimental#[^"]+",\s*options=glad_options',
    conanfile,
    re.DOTALL,
):
    raise SystemExit(
        "macOS must use one shared GLAD function-pointer table across all Mach-O images"
    )

gl_context = (ROOT / "libraries/gl/src/gl/ContextQt.cpp").read_text(encoding="utf-8")
if not re.search(
    r"if \(!_qglContext \|\| !_window \|\| !_qglContext->isValid\(\)\).*?"
    r"bool result = _qglContext->makeCurrent\(_window\);.*?if \(result\).*?gl::initModuleGl\(\)",
    gl_context,
    re.DOTALL,
):
    raise SystemExit("GL entry points must only load after a valid context is current")

gl_widget = (ROOT / "libraries/gl/src/gl/GLWidget.cpp").read_text(encoding="utf-8")
if not re.search(r"if \(!_context->makeCurrent\(\)\).*?qFatal.*?_context->clear\(\)", gl_widget, re.DOTALL):
    raise SystemExit("primary GL widget must not issue GL calls after makeCurrent fails")

setting_manager = (ROOT / "libraries/shared/src/SettingManager.cpp").read_text(
    encoding="utf-8"
)
setting_interface = (ROOT / "libraries/shared/src/SettingInterface.cpp").read_text(
    encoding="utf-8"
)
manager_constructor = setting_manager.split("Manager::Manager", 1)[1].split(
    "Manager::~Manager", 1
)[0]
if "_workerThread.start()" in manager_constructor:
    raise SystemExit("settings writer must not start before QApplication exists")
if not re.search(
    r"void Manager::startThread\(\).*?if \(!_workerThread\.isRunning\(\)\).*?"
    r"_workerThread\.start\(\)",
    setting_manager,
    re.DOTALL,
):
    raise SystemExit("settings writer start must be explicit and idempotent")
setup_writer = setting_interface.split("void startThread()", 1)[1].split(
    "void init(bool deferThreadStart)", 1
)[0]
if "globalManager->startThread();" not in setup_writer:
    raise SystemExit("explicit settings lifecycle must start the writer")
if not re.search(
    r"if \(!deferThreadStart\).*?if \(qApp\).*?startThread\(\).*?else.*?"
    r"qAddPreRoutine\(startThread\)",
    setting_interface,
    re.DOTALL,
):
    raise SystemExit("settings init must support explicit deferral and legacy application startup")

main_source = (ROOT / "interface/src/main.cpp").read_text(encoding="utf-8")
trace_block = main_source.split("// Early check for --traceFile argument", 1)[1].split(
    "PROFILE_SYNC_BEGIN", 1
)[0]
trace_shutdown = main_source.split("exitCode = app.exec();", 1)[1].split(
    "Application::shutdownPlugins();", 1
)[0]
if "const char* traceFile" in trace_block or ".toStdString().c_str()" in trace_block:
    raise SystemExit("trace output path must own its storage across the application lifetime")
for trace_contract in (
    "const bool traceRequested = parser.isSet(traceFileOption)",
    "QString traceFile",
    "traceFile = parser.value(traceFileOption)",
):
    if trace_contract not in trace_block:
        raise SystemExit(f"trace output lifetime contract missing: {trace_contract}")
if "if (traceRequested)" not in trace_shutdown or "tracer->serialize(traceFile)" not in trace_shutdown:
    raise SystemExit("trace output must serialize the owning QString after app execution")
application_setup_source = (ROOT / "interface/src/Application_Setup.cpp").read_text(
    encoding="utf-8"
)
entity_renderer_source = (
    ROOT / "libraries/entities-renderer/src/EntityTreeRenderer.cpp"
).read_text(encoding="utf-8")
if "QCoreApplication tempApp" in main_source:
    raise SystemExit("Interface must not create a temporary QCoreApplication before QApplication")
graphics_api_offset = main_source.index("hifi::properties::setGraphicsAPI(")
surface_format_offset = main_source.index("getDefaultOpenGLSurfaceFormat()")
if graphics_api_offset > surface_format_offset:
    raise SystemExit("graphics API must be selected before the OpenGL surface format is cached")
if not re.search(
    r"#elif defined\(Q_OS_MAC\).*?setGraphicsAPI\(hifi::properties::GraphicsAPI::GL41\)",
    main_source,
    re.DOTALL,
):
    raise SystemExit("desktop macOS must default to its supported OpenGL 4.1 backend")
application_offset = main_source.index("Application app(")
settings_load_offset = main_source.index("Setting::init(true)")
settings_start_offset = main_source.index("Setting::startThread()")
parser_offset = main_source.index("parser.process(app)")
if not settings_load_offset < application_offset < settings_start_offset < parser_offset:
    raise SystemExit("Interface settings and command-line startup phases are ordered incorrectly")

startup_preflight = (ROOT / "macos/ci/startup-preflight.sh").read_text(encoding="utf-8")
assert "--display Desktop" in startup_preflight, "startup preflight must never block on display selection"
for startup_contract in (
    "--abortAfterStartup",
    "OVERTE_MACOS_STARTUP_TIMEOUT_SECONDS:-30",
    "[[ $status -eq 99 ]]",
    '--sample "$process_sample"',
):
    if startup_contract not in startup_preflight:
        raise SystemExit(f"startup preflight missing contract: {startup_contract}")

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
    "lightweight_primitive_handoff": "libraries/entities-renderer/src/EntityTreeRenderer.cpp",
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
assert "--display Desktop" in smoke, "serverless smoke must never block on display selection"
for marker in CONTRACT:
    if marker not in smoke:
        raise SystemExit(f"smoke runner does not require {marker}")

online_smoke = (ROOT / "macos/ci/online-smoke.sh").read_text(encoding="utf-8")
assert "--display Desktop" in online_smoke, "online smoke must never block on display selection"
assert 'macos/tests/online-smoke.js' in online_smoke, "online smoke needs its own online fixture gate"
assert "hifi://overte_hub" in online_smoke, "online smoke must target the active public hub"
assert "URL_SCHEME_OVERTE" in online_smoke, "online smoke must document its compatibility scheme"
assert "overte://overte_hub" not in online_smoke, "unsupported product-name scheme must not silently no-op"
assert "overte://welcome" not in online_smoke, "the retired welcome place must not be used"
for inventory_contract in (
    "macos-online-entities.json",
    "validate-online-entities.py",
    "render_handoff_id",
    "--render-handoff-id",
    "--macosTestLightweightEntities",
    "lightweight_entity_filter_active",
    "lightweight_primitive_handoff",
):
    if inventory_contract not in online_smoke:
        raise SystemExit(f"online smoke must correlate its rendered entity: {inventory_contract}")
if "web_entity_qml_paused" in online_smoke:
    raise SystemExit(
        "online lightweight mode must not require a Web renderer that it intentionally filters"
    )
for marker in ONLINE_CONTRACT | {"render_handoff": ""}:
    if marker not in online_smoke:
        raise SystemExit(f"online smoke runner does not require {marker}")
transition_smoke = (ROOT / "macos/ci/transition-smoke.sh").read_text(
    encoding="utf-8"
)
transition_script = (ROOT / "macos/tests/transition-smoke.js").read_text(
    encoding="utf-8"
)
for smoke_name, smoke_source in (
    ("online", online_smoke),
    ("serverless/online transition", transition_smoke),
):
    if "disableEntityScripts" in smoke_source or "entity_scripts_disabled" in smoke_source:
        raise SystemExit(
            f"{smoke_name} smoke must retain the production entity-script lifecycle"
        )
    for lightweight_runner_contract in (
        "--macosTestLightweightEntities",
        "lightweight_entity_filter_active",
    ):
        if lightweight_runner_contract not in smoke_source:
            raise SystemExit(
                f"{smoke_name} smoke must activate the explicit lightweight "
                f"render mode: {lightweight_runner_contract}"
            )

global_properties_header = (
    ROOT / "libraries/shared/src/shared/GlobalAppProperties.h"
).read_text(encoding="utf-8")
global_properties_source = (
    ROOT / "libraries/shared/src/shared/GlobalAppProperties.cpp"
).read_text(encoding="utf-8")
main_source = (ROOT / "interface/src/main.cpp").read_text(encoding="utf-8")
for lightweight_property_contract in (
    "MACOS_TEST_LIGHTWEIGHT_ENTITIES",
    '"overte.macosTestLightweightEntities"',
):
    if lightweight_property_contract not in (
        global_properties_header + global_properties_source
    ):
        raise SystemExit(
            "missing macOS lightweight entity property: "
            f"{lightweight_property_contract}"
        )
if main_source.count('"macosTestLightweightEntities"') != 1:
    raise SystemExit("macOS lightweight entity test flag must be declared exactly once")

lightweight_helper = entity_renderer_source.split(
    "bool macOSLightweightEntityTestEnabled()", 1
)[1].split("bool isLightweightMacOSEntityType", 1)[0]
for lightweight_helper_contract in (
    "property(hifi::properties::TEST).isValid()",
    "hifi::properties::MACOS_TEST_LIGHTWEIGHT_ENTITIES",
):
    if lightweight_helper_contract not in lightweight_helper:
        raise SystemExit(
            "macOS lightweight entity helper missing: "
            f"{lightweight_helper_contract}"
        )

lightweight_types = entity_renderer_source.split(
    "bool isLightweightMacOSEntityType", 1
)[1].split("bool isPrimitiveEntityType", 1)[0]
for lightweight_type_contract in (
    "EntityTypes::Box",
    "EntityTypes::Sphere",
    "EntityTypes::Shape",
    "EntityTypes::Zone",
):
    if lightweight_type_contract not in lightweight_types:
        raise SystemExit(
            "macOS lightweight entity type missing: "
            f"{lightweight_type_contract}"
        )

lightweight_filter = entity_renderer_source.split(
    "const bool lightweightEntityTest = macOSLightweightEntityTestEnabled();", 1
)[1].split("// Path to the parent transforms", 1)[0]
for lightweight_filter_contract in (
    "processedIds.insert(entityID)",
    "lightweight_entity_filter_active",
):
    if lightweight_filter_contract not in lightweight_filter:
        raise SystemExit(
            "macOS lightweight entity filter missing: "
            f"{lightweight_filter_contract}"
        )
if entity_renderer_source.index("processedIds.insert(entityID)") > entity_renderer_source.index(
    "EntityRenderer::addToScene"
):
    raise SystemExit("macOS test filter must skip complex entities before scene submission")
if 'parser.isSet("macosTestLightweightEntities")' not in application_setup_source:
    raise SystemExit("Interface must transfer the macOS lightweight test flag to the app")
lightweight_handoff = entity_renderer_source.split(
    '"OVERTE_MACOS_ENTITY_GATE lightweight_primitive_handoff"', 1
)[0].rsplit("static bool loggedFirstLightweightPrimitiveHandoff", 1)[1]
for handoff_contract in (
    "entity->getEntityHostType() == entity::HostType::DOMAIN",
    "isPrimitiveEntityType(entity->getType())",
):
    if handoff_contract not in lightweight_handoff:
        raise SystemExit(
            "macOS lightweight handoff must identify a streamed domain primitive: "
            f"{handoff_contract}"
        )

for smoke_name, smoke_source in (("serverless", smoke), ("online", online_smoke)):
    if "--disableWatchdog" not in smoke_source:
        raise SystemExit(
            f"{smoke_name} smoke must leave stall sampling to the external supervisor"
        )
    if "--disableLocalAvatar" not in smoke_source:
        raise SystemExit(
            f"{smoke_name} smoke must isolate scene rendering from the local avatar"
        )
    if '--defaultScriptsOverride "file://$default_scripts_override"' not in smoke_source:
        raise SystemExit(
            f"{smoke_name} smoke must isolate the scene from persisted system scripts"
        )
    for timeout_contract in (
        "run-process-with-timeout.py",
        "OVERTE_MACOS_SMOKE_TIMEOUT_SECONDS",
        "OVERTE_MACOS_SMOKE_SHUTDOWN_GRACE_SECONDS",
        "OVERTE_MACOS_LLDB_TIMEOUT_SECONDS",
        "process.json",
        "crash.ips",
        "--crash-report",
        "lldb --batch -o run -k \"thread backtrace all\"",
        "status > 128 && status < 192",
    ):
        if timeout_contract not in smoke_source:
            raise SystemExit(
                f"{smoke_name} smoke is missing timeout contract: {timeout_contract}"
            )

runtime_supervisor = (
    ROOT / "macos/tools/run-process-with-timeout.py"
).read_text(encoding="utf-8")
runtime_result = runtime_supervisor.split('result = {', 1)[1].split('}', 1)[0]
if '"command"' in runtime_result or '"crash_report_source"' in runtime_result:
    raise SystemExit("runtime evidence must not persist argv or private diagnostic paths")
for sanitized_contract in (
    '"executable": Path(command[0]).name',
    '"argument_count": len(command) - 1',
    '"sample_name": args.sample.name',
    '"crash_report_source_name"',
):
    if sanitized_contract not in runtime_supervisor:
        raise SystemExit(f"runtime evidence redaction missing: {sanitized_contract}")
for smoke_name, smoke_source, maximum, cleanup_contract in (
    ("serverless", smoke, 720, 'rm -f "$snapshot" "$warmup_snapshot" "$screenshot_result"'),
    ("online", online_smoke, 720, 'rm -f "$snapshot" "$screenshot_result"'),
):
    default_timeout = re.search(
        r'OVERTE_MACOS_SMOKE_TIMEOUT_SECONDS:-([0-9]+)', smoke_source
    )
    if not default_timeout or int(default_timeout.group(1)) > maximum:
        raise SystemExit(f"{smoke_name} smoke timeout must be at most {maximum}s")
    if "rg -q" in smoke_source:
        raise SystemExit(f"{smoke_name} smoke must not require ripgrep on the runner")
    for screenshot_contract in (
        "validate-screenshot.py",
        "screenshot_result",
        cleanup_contract,
    ):
        if screenshot_contract not in smoke_source:
            raise SystemExit(
                f"{smoke_name} smoke lacks screenshot validation: {screenshot_contract}"
            )

serverless_script = (ROOT / "macos/tests/serverless-smoke.js").read_text(encoding="utf-8")
online_script = (ROOT / "macos/tests/online-smoke.js").read_text(encoding="utf-8")
for inventory_contract in (
    "inspectEntityInventory(entities, 64)",
    "inspectEntityInventory(entities, entities.length)",
    "saveEntityInventory(latestInventory)",
    "Test.saveObject(inventory",
    '"macos-online-entities.json"',
    "visible_renderable_count",
    "visible_primitive_count",
    "type_counts",
):
    if inventory_contract not in online_script:
        raise SystemExit(f"online smoke script lacks entity inventory: {inventory_contract}")
for script_name, script_source, snapshot_name, stage_contracts in (
    (
        "serverless",
        serverless_script,
        "macos-serverless-smoke.png",
        ("warmup_snapshot=", 'snapshotStage = "final"', "5000"),
    ),
    (
        "online",
        online_script,
        "macos-online-smoke.png",
        ('snapshotStage = "capturing"', "One completed frame is the online rendering proof"),
    ),
):
    for render_contract in (
        "Render.renderMethod = 1",
        "Render.shadowsEnabled = false",
        "Render.ambientOcclusionEnabled = false",
        "Render.antialiasingMode = 0",
        "Render.viewportResolutionScale = 1.0",
        'Render.getConfig("RenderMainView.PreparePrimaryBufferForward").numSamples = 1',
        "Scene.shouldRenderAvatars = false",
        "Script.stop()",
        snapshot_name,
    ) + stage_contracts:
        if render_contract not in script_source:
            raise SystemExit(
                f"{script_name} smoke lacks deterministic rendering contract: {render_contract}"
            )
    if script_source.index("Render.renderMethod = 1") > script_source.index(
        "Window.takeSnapshot"
    ):
        raise SystemExit(
            f"{script_name} smoke must apply its render profile before taking a snapshot"
        )
for environmental_type in ("Zone", "Light", "Material"):
    if f"{environmental_type}: true" not in online_script:
        raise SystemExit(
            f"online smoke must not mistake {environmental_type} for visible geometry"
        )
online_validator = (
    ROOT / "macos/tools/validate-online-entities.py"
).read_text(encoding="utf-8")
for online_entity_classification_contract in (
    'NON_RENDERING_TYPES = {"Unknown", "Empty", "Sound", "Script"}',
    'NON_VISIBLE_GEOMETRY_TYPES = NON_RENDERING_TYPES | {"Zone", "Light", "Material"}',
    'PRIMITIVE_TYPES = {"Box", "Sphere", "Shape"}',
    "entity_type not in NON_VISIBLE_GEOMETRY_TYPES",
    "handoff_type not in PRIMITIVE_TYPES",
):
    if online_entity_classification_contract not in online_validator:
        raise SystemExit(
            "online validator must distinguish environmental render effects "
            f"from visible geometry: {online_entity_classification_contract}"
        )
for online_timing_contract in (
    "snapshot_complete=",
    "visibleGeometryReadyAt = Date.now() + 1000",
    "latestInventory.visible_primitive_count > 0",
    "saveEntityInventory(latestInventory)",
    "snapshotSettleDeadline = Date.now() + 300000",
    "snapshot_callback_deferred",
    "Date.now() + 420000",
):
    if online_timing_contract not in online_script:
        raise SystemExit(
            f"online smoke must inventory the completed frame: {online_timing_contract}"
        )
if online_script.index("saveEntityInventory(latestInventory)") > online_script.index(
    "Window.takeSnapshot"
):
    raise SystemExit("online smoke must freeze its correlated inventory before capture")
if 'OVERTE_MACOS_SMOKE_TIMEOUT_SECONDS:-600' not in online_smoke:
    raise SystemExit("online smoke must cover the measured software-renderer frame budget")

for transition_geometry_contract in (
    "visibleGeometryCount",
    "state.visibleGeometryCount > 0",
    '" visible_geometry="',
    "Date.now() + 420000",
    "onlineSnapshotSettleDeadline = Date.now() + 150000",
    "online_snapshot_callback_deferred",
    "returnToServerless",
    "resetFixtureView",
    "MyAvatar.position = { x: 0, y: 1.6, z: 0 }",
    'Camera.mode = "first person"',
    "initial_warmup_snapshot",
    "final_warmup_snapshot",
    "Date.now() + 5000",
):
    if transition_geometry_contract not in transition_script:
        raise SystemExit(
            "transition smoke must wait for visible online geometry: "
            f"{transition_geometry_contract}"
        )
if "fixture_entities=3" not in serverless_script:
    raise SystemExit("serverless smoke must identify the exact three fixture entities")
for fixture_name in (
    "macOS smoke red cube",
    "macOS smoke cyan sphere",
    "macOS smoke label",
):
    if fixture_name not in serverless_script:
        raise SystemExit(f"serverless smoke does not require fixture: {fixture_name}")
if "--require-red-pixels 128 --require-cyan-pixels 128" not in smoke:
    raise SystemExit("serverless smoke must verify both colored fixture entities")
if "--require-red-left --require-cyan-right" not in smoke:
    raise SystemExit("serverless smoke must verify deterministic fixture placement")

performance_smoke = (ROOT / "macos/ci/performance-smoke.sh").read_text(encoding="utf-8")
performance_script = (ROOT / "macos/tests/performance-smoke.js").read_text(encoding="utf-8")
for performance_contract in (
    "run-process-with-timeout.py",
    "validate-performance.py",
    "validate-screenshot.py",
    "TEST-overte-macos-performance.xml",
    "OVERTE_MACOS_PERFORMANCE_MAXIMUM_P95_MS",
    "OVERTE_MACOS_PERFORMANCE passed",
):
    if performance_contract not in performance_smoke:
        raise SystemExit(f"macOS performance runner missing: {performance_contract}")
for performance_contract in (
    "FrameTimings.start()",
    "FrameTimings.finish()",
    "FrameTimings.getValues()",
    "MINIMUM_MEASUREMENT_MS = 20000",
    "MAXIMUM_MEASUREMENT_MS = 90000",
    "MINIMUM_SAMPLE_COUNT = 30",
    "WARMUP_SETTLE_MS = 5000",
    'stage = "settling"',
    "fixture_settled_ms=",
    "sampleCount >= MINIMUM_SAMPLE_COUNT",
    "samples.length >= MINIMUM_SAMPLE_COUNT",
    "samples_us",
    "p50_frame_ms",
    "p95_frame_ms",
    "p99_frame_ms",
    "over_16_67_ms",
    "over_33_33_ms",
    "Test.saveObject(metrics, \"macos-performance.json\")",
):
    if performance_contract not in performance_script:
        raise SystemExit(f"macOS performance script missing: {performance_contract}")
warmup_handler = performance_script.split("Window.stillSnapshotTaken.connect", 1)[1].split(
    "Script.setInterval", 1
)[0]
if "if (!path)" not in warmup_handler or "startMeasurement();" not in warmup_handler:
    raise SystemExit("performance measurement must start after a completed warmup frame")
if performance_script.index('stage = "settling"') > performance_script.index(
    'Window.takeSnapshot(false, false, 16 / 9, "macos-performance-warmup.png")'
):
    raise SystemExit("performance warmup must settle after discovery before snapshot capture")

profile_matrix = (ROOT / "macos/ci/performance-matrix.sh").read_text(encoding="utf-8")
profile_script = (ROOT / "macos/tests/profile-performance-smoke.js").read_text(encoding="utf-8")
profile_definitions = json.loads(
    (ROOT / "macos/tests/performance-profiles.json").read_text(encoding="utf-8")
)
profile_ids = [profile["id"] for profile in profile_definitions["profiles"]]
for required_profile in (
    "forward-compat",
    "forward-balanced",
    "forward-quality",
    "deferred-balanced",
    "deferred-quality",
):
    if profile_ids.count(required_profile) != 1:
        raise SystemExit(f"performance profile set must contain exactly one {required_profile}")
for profile_contract in (
    "OVERTE_MACOS_PROFILE_REPEATS",
    "OVERTE_MACOS_PROFILE_MATRIX_MODE",
    "render-performance-profile.py",
    "analyze-performance-matrix.py",
    "validate-screenshot.py",
    "warmup",
    "run-$repeat",
    "runner_class",
    "diagnostic-lite",
    "profile-accepted",
    "matrix-manifest.json",
    "attempts.jsonl",
    "refusing to upgrade diagnostic graphics evidence to hardware",
    "refusing to mix a performance matrix with existing evidence",
    '--profiles "$profiles_file"',
):
    if profile_contract not in profile_matrix:
        raise SystemExit(f"performance matrix runner missing: {profile_contract}")
for profile_contract in (
    "stress_entities=",
    "Performance.setRefreshRateProfile(2)",
    "LODManager.automaticLODAdjust = false",
    "Stats.forceUpdateStats()",
    "Stats.expanded = true",
    "gpuFrameTime",
    "batchFrameTime",
    "engineFrameTime",
    "drawcalls",
    "triangles",
    "gpuTextureMemory",
    "rates_hz",
    "Test.startTracing()",
    "measurement_complete",
    "warmup_to_snapshot_ms",
    "LODManager.presentTime",
    "LODManager.engineRunTime",
    "LODManager.batchTime",
    "LODManager.gpuTime",
    "lod_timings_ms",
    "polled_latest_and_moving_averages",
    "invalid_count",
):
    if profile_contract not in profile_script:
        raise SystemExit(f"performance profile script missing: {profile_contract}")

online_loading_runner = (ROOT / "macos/ci/online-loading-benchmark.sh").read_text(encoding="utf-8")
online_loading_script = (ROOT / "macos/tests/online-loading-benchmark.js").read_text(encoding="utf-8")
for loading_contract in (
    "OVERTE_MACOS_ONLINE_CONCURRENCIES",
    "OVERTE_MACOS_ONLINE_REPEATS",
    'run_case "$concurrency" "$pair" cold',
    'run_case "$concurrency" "$pair" warm',
    "--cache",
    "--concurrent-downloads",
    "analyze-online-loading.py",
    "online-loading-accepted",
    "online-loading-manifest.json",
    "attempts.jsonl",
    "metrics_present",
    "result_directory",
    "refusing to mix an online-loading benchmark with existing evidence",
    'concurrencies=("${concurrencies[0]}")',
    "OVERTE_MACOS_ONLINE_DIAGNOSTIC_TIMEOUT_SECONDS",
    '--runner-class "$runner_class"',
    'case_timeout_seconds="$diagnostic_timeout_seconds"',
):
    if loading_contract not in online_loading_runner:
        raise SystemExit(f"online loading runner missing: {loading_contract}")
if "--macosTestLightweightEntities" in online_loading_runner:
    raise SystemExit("online loading benchmark must exercise full online entity content")
for loading_contract in (
    "Stats.downloads",
    "Stats.downloadsPending",
    "Stats.processing",
    "Stats.processingPending",
    "Stats.texturePendingTransfers",
    "Test.isTextureLoadingComplete()",
    "Stats.expanded = true",
    "sustained_idle_ms",
    "first_visible_ms",
    "queue_samples",
    'testCase.runner_class === "diagnostic"',
    "diagnostic_observation_complete",
):
    if loading_contract not in online_loading_script:
        raise SystemExit(f"online loading script missing: {loading_contract}")

frame_timings_header = (
    ROOT / "interface/src/FrameTimingsScriptingInterface.h"
).read_text(encoding="utf-8")
frame_timings_source = (
    ROOT / "interface/src/FrameTimingsScriptingInterface.cpp"
).read_text(encoding="utf-8")
if "#include <QtCore/QVariant>" not in frame_timings_header:
    raise SystemExit("frame timing public QVariantList API must include QVariant directly")
application_source = (ROOT / "interface/src/Application.cpp").read_text(encoding="utf-8")
test_registration = application_source.split(
    "if (property(hifi::properties::TEST).isValid())", 1
)[1].split("}", 1)[0]
if '"FrameTimings"' not in test_registration:
    raise SystemExit("frame timings must be exposed to explicit application test scripts")
if "mutable QMutex _mutex" not in frame_timings_header:
    raise SystemExit("frame timing samples must synchronize render and script threads")
if frame_timings_source.count("QMutexLocker locker(&_mutex)") < 7:
    raise SystemExit("all frame timing sample and result access must be synchronized")
if "if (_values.empty())" not in frame_timings_source:
    raise SystemExit("empty frame timing measurements must produce finite zero results")
if "TextureCache" in frame_timings_source or "setUnusedResourceCacheSize" in frame_timings_source:
    raise SystemExit("frame timing collection must not mutate global resource-cache policy")

stability_smoke = (ROOT / "macos/ci/stability-smoke.sh").read_text(encoding="utf-8")
for stability_contract in (
    "serverless-smoke.sh",
    "validate-stability.py",
    "serverless-process.json",
    "serverless-screenshot.json",
    "TEST-overte-macos-stability.xml",
    "iteration <= iterations",
    "refusing to reuse existing stability evidence",
):
    if stability_contract not in stability_smoke and stability_contract not in (
        ROOT / "macos/tools/validate-stability.py"
    ).read_text(encoding="utf-8"):
        raise SystemExit(f"macOS stability suite missing: {stability_contract}")

transition_smoke = (ROOT / "macos/ci/transition-smoke.sh").read_text(encoding="utf-8")
node_list_source = (ROOT / "libraries/networking/src/NodeList.cpp").read_text(
    encoding="utf-8"
)
for transition_contract in (
    "domain_list_connected",
    "entity_server_active",
    "entity_query_sent",
    "entity_data_received",
    "serverless_import_committed",
    "online_seen && /OVERTE_MACOS_ENTITY_GATE serverless_import_committed/",
    "serverless-online-serverless transition smoke passed",
    "--require-red-left --require-cyan-right",
):
    if transition_contract not in transition_smoke:
        raise SystemExit(f"macOS transition runner missing: {transition_contract}")
for transition_contract in (
    'Script.resolvePath("fixtures/serverless-render.json")',
    'AddressManager.handleLookupString("hifi://overte_hub")',
    "AddressManager.handleLookupString(localScene)",
    "state.fixtureCount === 0",
    'AddressManager.protocol === "file"',
    "online_rendering_paused",
    "initial_fixture_entities=3",
    "online_entities=",
    "returned_fixture_entities=3",
    'finish(true, "serverless_online_serverless")',
):
    if transition_contract not in transition_script:
        raise SystemExit(f"macOS transition script missing: {transition_contract}")
if "!AddressManager.isConnected" in transition_script:
    raise SystemExit(
        "serverless transition must remain connected and use its file protocol as the mode gate"
    )
returning_serverless_gate = transition_script.split(
    'stage === "returning_serverless"', 1
)[1].split(") {", 1)[0]
for transition_contract in (
    "AddressManager.isConnected",
    'AddressManager.protocol === "file"',
    "state.fixtureComplete",
):
    if transition_contract not in returning_serverless_gate:
        raise SystemExit(
            f"returning serverless gate missing: {transition_contract}"
        )
if transition_script.index("Scene.shouldRenderEntities = false") > transition_script.index(
    "AddressManager.handleLookupString(localScene)"
):
    raise SystemExit("online entity frames must pause before returning to serverless")
if transition_script.index("Scene.shouldRenderEntities = true") > transition_script.index(
    'Window.takeSnapshot(false, false, 16 / 9, "macos-transition-final.png")'
):
    raise SystemExit("serverless entities must resume before the final render proof")

process_domain_list = node_list_source.split("void NodeList::processDomainList", 1)[1].split(
    "void NodeList::", 1
)[0]
serverless_packet_guard = "if (_domainHandler.isServerless())"
for domain_list_mutation in (
    "QDataStream packetStream",
    "setSessionLocalID(newLocalID)",
    "setSessionUUID(newUUID)",
):
    if process_domain_list.index(serverless_packet_guard) > process_domain_list.index(
        domain_list_mutation
    ):
        raise SystemExit(
            f"serverless DomainList guard must precede {domain_list_mutation}"
        )
if "IGNORING DomainList packet while in a serverless domain" not in process_domain_list:
    raise SystemExit("stale serverless DomainList rejection must remain diagnosable")

render_common = (ROOT / "libraries/render-utils/src/RenderCommonTask.cpp").read_text(
    encoding="utf-8"
)
resolve_framebuffer = render_common.split("void ResolveFramebuffer::run", 1)[1].split(
    "void ExtractFrustums::run", 1
)[0]
for resolve_contract in (
    "srcFbo->getNumSamples() <= 1",
    "outputs = srcFbo",
    "batch.blit(srcFbo, rectSrc, destFbo, rectSrc)",
):
    if resolve_contract not in resolve_framebuffer:
        raise SystemExit(
            f"forward framebuffer resolve contract missing: {resolve_contract}"
        )
if resolve_framebuffer.index("srcFbo->getNumSamples() <= 1") > resolve_framebuffer.index(
    "batch.blit(srcFbo, rectSrc, destFbo, rectSrc)"
):
    raise SystemExit("single-sample forward framebuffers must bypass the resolve blit")

gl_backend_header = (ROOT / "libraries/gpu-gl-common/src/gpu/gl/GLBackend.h").read_text(
    encoding="utf-8"
)
gl_backend_source = (
    ROOT / "libraries/gpu-gl-common/src/gpu/gl/GLBackend.cpp"
).read_text(encoding="utf-8")
gl_backend_output = (
    ROOT / "libraries/gpu-gl-common/src/gpu/gl/GLBackendOutput.cpp"
).read_text(encoding="utf-8")
gl41_backend_output = (
    ROOT / "libraries/gpu-gl/src/gpu/gl41/GL41BackendOutput.cpp"
).read_text(encoding="utf-8")
display_plugin = (
    ROOT / "libraries/display-plugins/src/display-plugins/OpenGLDisplayPlugin.cpp"
).read_text(encoding="utf-8")
tone_map_diagnostics = (
    ROOT / "libraries/render-utils/src/ToneMapDiagnostics.h"
).read_text(encoding="utf-8")
tone_map_header = (
    ROOT / "libraries/render-utils/src/ToneMapAndResampleTask.h"
).read_text(encoding="utf-8")
tone_map_source = (
    ROOT / "libraries/render-utils/src/ToneMapAndResampleTask.cpp"
).read_text(encoding="utf-8")
render_hud_layer = (
    ROOT / "libraries/render-utils/src/RenderHUDLayerTask.cpp"
).read_text(encoding="utf-8")
tone_map_shader = (
    ROOT / "libraries/render-utils/src/toneMapping.slf"
).read_text(encoding="utf-8")
framebuffer_cache = (
    ROOT / "libraries/render-utils/src/FramebufferCache.cpp"
).read_text(encoding="utf-8")
for diagnostic_contract in (
    "diagnoseFramebuffer",
    "GL_FRAMEBUFFER_ATTACHMENT_COLOR_ENCODING",
    "GL_FRAMEBUFFER_ATTACHMENT_COMPONENT_TYPE",
    "GL_FLOAT",
    "GL_UNSIGNED_BYTE",
    "float_nonzero=",
    "byte_nonzero=",
):
    if diagnostic_contract not in gl_backend_header + gl_backend_output:
        raise SystemExit(f"macOS framebuffer diagnostics missing: {diagnostic_contract}")
for stage in ('"tone_input"', '"final"', '"composite"'):
    if f"diagnoseFramebuffer" not in display_plugin or stage not in display_plugin:
        raise SystemExit(f"macOS screenshot diagnostics do not capture {stage}")
if "getToneMapDiagnosticInputFramebuffer" not in display_plugin:
    raise SystemExit("macOS screenshot diagnostics must retain the tone-mapping input")
if "#include <ToneMapDiagnostics.h>" not in display_plugin or "ToneMapAndResampleTask.h" in display_plugin:
    raise SystemExit("macOS display diagnostics must use the narrow tone-map diagnostics header")
if "getToneMapDiagnosticInputFramebuffer" not in tone_map_diagnostics or "task/" in tone_map_diagnostics:
    raise SystemExit("tone-map diagnostics header must expose only the narrow framebuffer boundary")
for std140_contract in (
    "class alignas(16) Parameters",
    "std::array<float, 4> _exposureRegister",
    "std::array<std::int32_t, 4> _curveRegister",
    "static_assert(sizeof(Parameters) == 32",
    "offsetof(Parameters, _exposureRegister) == 0",
    "offsetof(Parameters, _curveRegister) == 16",
):
    if std140_contract not in tone_map_header:
        raise SystemExit(f"tone-map std140 layout contract missing: {std140_contract}")
for shader_register in ("vec4 _exposureRegister", "ivec4 _curveRegister"):
    if shader_register not in tone_map_shader:
        raise SystemExit("tone-map shader must use two explicit std140 registers")
if "struct ToneMappingParams" in tone_map_shader or "params._exposureRegister" in tone_map_shader:
    raise SystemExit("tone-map uniforms must be direct block members for Apple OpenGL")
for vector_parameter_contract in (
    "_exposureRegister.fill(pow(2.0, exposure))",
    "_curveRegister.fill((int)curve)",
    "fragColor * _exposureRegister.xyz",
):
    if vector_parameter_contract not in tone_map_source + tone_map_shader:
        raise SystemExit(f"tone-map vector parameter contract missing: {vector_parameter_contract}")
for neutral_passthrough_contract in (
    "OVERTE_MACOS_TONEMAP_PASSTHROUGH",
    "activeParameters._curveRegister.front() == (int)TonemappingCurve::SRGB",
    "activeParameters._exposureRegister.front() == 1.0f",
    'gpu::doInBatch("ToneMapNeutralBlit::run"',
    "batch.setFramebuffer(destinationFramebuffer)",
    "batch.blit(input.get0(), sourceRect, destinationFramebuffer, destinationRect)",
    "std::swap(sourceRect.x, sourceRect.z)",
):
    if neutral_passthrough_contract not in tone_map_source + tone_map_header:
        raise SystemExit(f"neutral macOS tone-map passthrough missing: {neutral_passthrough_contract}")
neutral_blit = tone_map_source.split("if (neutralPassthrough)", 1)[1].split(
    'gpu::doInBatch("Resample::run"', 1
)[0]
if neutral_blit.index("batch.setFramebuffer(destinationFramebuffer)") > neutral_blit.index(
    "batch.blit(input.get0(), sourceRect, destinationFramebuffer, destinationRect)"
):
    raise SystemExit("neutral macOS tone-map blit must select destination state before copying")
if "return;" not in neutral_blit:
    raise SystemExit("neutral macOS tone-map blit must bypass the broken sampler pipeline")
for neutral_backend_contract in (
    'batch.getName() == "ToneMapNeutralBlit::run"',
    "glIsEnabled(GL_SCISSOR_TEST)",
    "glDisable(GL_SCISSOR_TEST)",
    "glEnable(GL_SCISSOR_TEST)",
    "glReadBuffer(GL_COLOR_ATTACHMENT0)",
    "OVERTE_MACOS_GL_BLIT_ERROR",
    "OVERTE_MACOS_GL_BLIT",
    "source_nonzero=",
    "destination_nonzero=",
    "_macosToneMapDiagnosticFBO = newDrawFBO",
    "_macosToneMapDiagnosticSize",
):
    if neutral_backend_contract not in gl41_backend_output:
        raise SystemExit(
            f"neutral macOS GL blit hardening missing: {neutral_backend_contract}"
        )
neutral_backend_blit = gl41_backend_output.split(
    "const bool neutralToneMapBlit", 1
)[1].split("// Always clean the read fbo", 1)[0]
if neutral_backend_blit.index("glDisable(GL_SCISSOR_TEST)") > neutral_backend_blit.index(
    "glBlitFramebuffer"
):
    raise SystemExit("neutral macOS GL blit must disable inherited scissoring before copying")
if neutral_backend_blit.index("glEnable(GL_SCISSOR_TEST)") < neutral_backend_blit.index(
    "glBlitFramebuffer"
):
    raise SystemExit("neutral macOS GL blit must restore inherited scissoring after copying")
for overwrite_trace_contract in (
    "diagnoseToneMapOverwrite(batch)",
    "OVERTE_MACOS_GL_OVERWRITE",
    "target_became_black=true",
    "_macosToneMapDiagnosticHadRGB && !hasRGB",
):
    if overwrite_trace_contract not in gl_backend_header + gl_backend_source:
        raise SystemExit(
            f"macOS post-tone-map overwrite tracing missing: {overwrite_trace_contract}"
        )
for paused_hud_contract in (
    "#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)",
    "QCoreApplication::instance()",
    "application->property(hifi::properties::TEST).isValid()",
):
    if paused_hud_contract not in render_hud_layer:
        raise SystemExit(f"macOS paused desktop HUD guard missing: {paused_hud_contract}")
paused_hud_guard = render_hud_layer.split(
    "application->property(hifi::properties::TEST).isValid()", 1
)[1].split("#endif", 1)[0]
if "return;" not in paused_hud_guard:
    raise SystemExit("macOS scene tests must skip the deliberately paused desktop HUD")
if render_hud_layer.index("application->property(hifi::properties::TEST).isValid()") > render_hud_layer.index(
    'gpu::doInBatch("CompositeHUD"'
):
    raise SystemExit("macOS paused desktop HUD must be rejected before its composite batch")
for diagnostic_token in ("OVERTE_MACOS_TONEMAP_PARAMS", "sizeof(Parameters)", "exposure_scale="):
    if diagnostic_token not in tone_map_source:
        raise SystemExit(f"tone-map runtime diagnostics missing: {diagnostic_token}")
for linear_output_source, stage in (
    (framebuffer_cache, "tone_map"),
    (display_plugin, "composite"),
):
    linear_guard = linear_output_source.split("#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)", 1)[1]
    if "COLOR_RGBA_32" not in linear_guard or f"stage={stage}" not in linear_guard:
        raise SystemExit(f"macOS {stage} output must bypass broken offscreen sRGB writes")
if display_plugin.index('diagnoseFramebuffer(toneInput') > display_plugin.index(
    'diagnoseFramebuffer(_currentFrame->framebuffer'
):
    raise SystemExit("macOS screenshot diagnostics must capture tone input before final")
if display_plugin.index('diagnoseFramebuffer(_currentFrame->framebuffer') > display_plugin.index(
    'diagnoseFramebuffer(_compositeFramebuffer'
):
    raise SystemExit("macOS screenshot diagnostics must capture final before composite")

main_source = (ROOT / "interface/src/main.cpp").read_text(encoding="utf-8")
if main_source.count('"disableLocalAvatar"') != 1:
    raise SystemExit("the local-avatar suppression option must be declared exactly once")
if "parser.addOption(disableLocalAvatarOption);" not in main_source:
    raise SystemExit("the local-avatar suppression option is not registered")
if "disableEntityScripts" in main_source:
    raise SystemExit(
        "Interface must not expose the incomplete no-entity-script lifecycle"
    )

if "DependencyManager::set<EntityTreeRenderer>(true, qApp, qApp)" not in application_setup_source:
    raise SystemExit("Interface must initialize the complete entity-script lifecycle")
if "disableEntityScripts" in application_setup_source:
    raise SystemExit("Interface must not construct a partially initialized entity renderer")
reload_entity_scripts = entity_renderer_source.split(
    "void EntityTreeRenderer::reloadEntityScripts()", 1
)[1].split("void EntityTreeRenderer::init()", 1)[0]
if "if (!_wantScripts)" not in reload_entity_scripts or "return;" not in reload_entity_scripts:
    raise SystemExit("disabled entity scripts must make reload requests a safe no-op")
local_avatar_property = 'parser.isSet("disableLocalAvatar")'
local_avatar_disable = 'setProperty("shouldRenderLocally", false)'
avatar_init = "avatarManager->init();"
for contract in (
    local_avatar_property,
    local_avatar_disable,
    "OVERTE_MACOS_RENDER_PHASE local_avatar_skipped",
    avatar_init,
):
    if contract not in application_setup_source:
        raise SystemExit(f"missing local-avatar suppression contract: {contract}")
if application_setup_source.index(local_avatar_disable) > application_setup_source.index(
    avatar_init
):
    raise SystemExit("the local avatar must be hidden before AvatarManager::init")

avatar_manager_source = (ROOT / "interface/src/avatar/AvatarManager.cpp").read_text(
    encoding="utf-8"
)
for contract in (
    "hifi::properties::DISABLE_LOCAL_AVATAR",
    "_shouldRender && !disableLocalAvatar",
    "disableLocalAvatar && avatar == _myAvatar",
    "OVERTE_MACOS_RENDER_PHASE local_avatar_scene_submission_skipped",
):
    if contract not in avatar_manager_source:
        raise SystemExit(f"missing AvatarManager local-avatar gate: {contract}")
if "serverless smoke submitted an unexpected skinned model draw" not in smoke:
    raise SystemExit("serverless smoke must reject local-avatar DQ model draws")

application_ui_source = (ROOT / "interface/src/Application_UI.cpp").read_text(
    encoding="utf-8"
)
mesh_reenable_guard = """if (!property(hifi::properties::DISABLE_LOCAL_AVATAR).toBool()) {
        myAvatar->setEnableMeshVisible(true);
    }"""
if mesh_reenable_guard not in application_ui_source:
    raise SystemExit("login completion must not re-enable a suppressed local avatar")

application_setup = (ROOT / "interface/src/Application_Setup.cpp").read_text(
    encoding="utf-8"
)
local_input_gate = application_setup.split(
    "// Preload Tablet sounds", 1
)[1].split("// Needs to happen later", 1)[0]
for local_input_contract in (
    "Q_OS_MAC",
    "property(hifi::properties::TEST).isValid()",
    "local_input_models_skipped",
    "DependencyManager::get<Keyboard>()->createKeyboard()",
):
    if local_input_contract not in local_input_gate:
        raise SystemExit(
            f"macOS runtime isolation contract missing: {local_input_contract}"
        )

gl41_backend = (ROOT / "libraries/gpu-gl/src/gpu/gl41/GL41Backend.cpp").read_text(
    encoding="utf-8"
)
gl_backend_output = (
    ROOT / "libraries/gpu-gl-common/src/gpu/gl/GLBackendOutput.cpp"
).read_text(encoding="utf-8")
mac_framebuffer_srgb = gl_backend_output.split(
    "#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)", 1
)[1].split("#endif", 1)[0]
for framebuffer_srgb_contract in (
    "GL_FRAMEBUFFER_ATTACHMENT_COLOR_ENCODING",
    "colorEncoding == GL_SRGB",
    "glEnable(GL_FRAMEBUFFER_SRGB)",
    "glDisable(GL_FRAMEBUFFER_SRGB)",
    "OVERTE_MACOS_FRAMEBUFFER_SRGB",
):
    if framebuffer_srgb_contract not in mac_framebuffer_srgb:
        raise SystemExit(f"macOS framebuffer-sRGB state contract missing: {framebuffer_srgb_contract}")
if mac_framebuffer_srgb.index("colorEncoding == GL_SRGB") > mac_framebuffer_srgb.index(
    "glDisable(GL_FRAMEBUFFER_SRGB)"
):
    raise SystemExit("macOS must classify a framebuffer before selecting its sRGB write state")
draw_unindexed = gl41_backend.split("void GL41Backend::do_draw", 1)[1].split(
    "void GL41Backend::do_drawIndexed", 1
)[0]
for tone_state_contract in (
    "OVERTE_MACOS_TONEMAP_GL_STATE",
    'fragmentName.contains("toneMapping"',
    "GL_UNIFORM_BUFFER_BINDING",
    "GL_UNIFORM_BUFFER_START",
    "GL_UNIFORM_BUFFER_SIZE",
    "glGetBufferSubData",
    "GL_DRAW_FRAMEBUFFER_BINDING",
    "GL_DRAW_BUFFER0",
    "GL_COLOR_WRITEMASK",
    "GL_FRAMEBUFFER_SRGB",
    "GL_TEXTURE_INTERNAL_FORMAT",
):
    if tone_state_contract not in draw_unindexed:
        raise SystemExit(f"macOS tone-map GL-state diagnostic missing: {tone_state_contract}")
if draw_unindexed.index("OVERTE_MACOS_TONEMAP_GL_STATE") > draw_unindexed.index(
    "draw(mode, numVertices, startVertex)"
):
    raise SystemExit("macOS tone-map state must be captured before its driver draw")
for array_draw_contract in (
    "OVERTE_MACOS_GL_ARRAY_DRAW begin",
    "OVERTE_MACOS_GL_ARRAY_DRAW end",
    "vertex=",
    "fragment=",
    "tracedArrayPrograms.insert(_pipeline._program).second",
):
    if array_draw_contract not in draw_unindexed:
        raise SystemExit(
            f"macOS GL array-draw diagnostic missing: {array_draw_contract}"
        )
if draw_unindexed.index("OVERTE_MACOS_GL_ARRAY_DRAW begin") > draw_unindexed.index(
    "draw(mode, numVertices, startVertex)"
):
    raise SystemExit("macOS GL array draw-begin must precede the driver call")
if draw_unindexed.index("OVERTE_MACOS_GL_ARRAY_DRAW end") < draw_unindexed.index(
    "draw(mode, numVertices, startVertex)"
):
    raise SystemExit("macOS GL array draw-end must follow the driver call")
draw_indexed = gl41_backend.split("void GL41Backend::do_drawIndexed", 1)[1].split(
    "void GL41Backend::do_drawInstanced", 1
)[0]
for draw_contract in (
    "OVERTE_MACOS_GL_DIAGNOSTICS",
    "OVERTE_MACOS_GL_DRAW begin",
    "OVERTE_MACOS_GL_DRAW end",
    "vertex=",
    "fragment=",
    "tracedPrograms.insert(_pipeline._program).second",
):
    if draw_contract not in draw_indexed:
        raise SystemExit(f"macOS GL first-draw diagnostic missing: {draw_contract}")
if draw_indexed.index("OVERTE_MACOS_GL_DRAW begin") > draw_indexed.index(
    "glDrawElements(mode"
):
    raise SystemExit("macOS GL draw-begin diagnostic must precede the driver call")
if draw_indexed.index("OVERTE_MACOS_GL_DRAW end") < draw_indexed.index(
    "glDrawElements(mode"
):
    raise SystemExit("macOS GL draw-end diagnostic must follow the driver call")
if "qCInfo(gpugl41logging)" in draw_indexed:
    raise SystemExit("macOS GL draw diagnostics must bypass startup category resets")
if "application->property(hifi::properties::TEST).isValid()" not in draw_indexed:
    raise SystemExit("macOS test runs must enable GL diagnostics without shell-env dependence")
for smoke_source in (smoke, online_smoke):
    if "OVERTE_MACOS_GL_DIAGNOSTICS=1" not in smoke_source:
        raise SystemExit("macOS entity smokes must enable bounded GL diagnostics")

application_graphics = (
    ROOT / "interface/src/Application_Graphics.cpp"
).read_text(encoding="utf-8")
if "#include <shared/GlobalAppProperties.h>" not in application_graphics:
    raise SystemExit("macOS test UI isolation must declare hifi application properties")
desktop_setup = application_graphics.split(
    "auto offscreenUi = getOffscreenUI();", 1
)[1].split("connect(_window", 1)[0]
for desktop_contract in (
    "Q_OS_MAC",
    "property(hifi::properties::TEST).isValid()",
    "offscreenUi->pause()",
    "desktop_qml_paused",
    "offscreenUi->resume()",
):
    if desktop_contract not in desktop_setup:
        raise SystemExit(f"macOS test UI isolation missing: {desktop_contract}")
if desktop_setup.index("offscreenUi->pause()") > desktop_setup.index(
    "offscreenUi->createDesktop"
):
    raise SystemExit("macOS scene tests must pause QML before its render thread starts")

application_setup = (
    ROOT / "interface/src/Application_Setup.cpp"
).read_text(encoding="utf-8")
web_surface_setup = application_setup.split(
    "WebEntityRenderer::setAcquireWebSurfaceOperator", 1
)[1].split("WebEntityRenderer::setReleaseWebSurfaceOperator", 1)[0]
for web_surface_contract in (
    "Q_OS_MAC",
    "!defined(Q_OS_IOS)",
    "property(hifi::properties::TEST).isValid()",
    "webSurface->pause()",
    "std::once_flag",
    "web_entity_qml_paused",
):
    if web_surface_contract not in web_surface_setup:
        raise SystemExit(
            f"macOS Web entity test isolation missing: {web_surface_contract}"
        )
if web_surface_setup.index("webSurface->pause()") > web_surface_setup.index(
    "webSurface->load(url)"
):
    raise SystemExit("macOS scene tests must pause Web QML before its first load")
if web_surface_setup.count("webSurface->pause()") != 2:
    raise SystemExit("both cached and uncached macOS Web surfaces must be paused")
uncached_web_surface_setup = web_surface_setup.split(
    "new OffscreenQmlSurface()", 1
)[1].split("webSurface->load(url)", 1)[0]
if "webSurface->pause()" not in uncached_web_surface_setup:
    raise SystemExit("uncached macOS Web surfaces must be paused before load")

shared_object_header = (
    ROOT / "libraries/qml/src/qml/impl/SharedObject.h"
).read_text(encoding="utf-8")
shared_object_source = (
    ROOT / "libraries/qml/src/qml/impl/SharedObject.cpp"
).read_text(encoding="utf-8")
if "std::atomic_bool _paused" not in shared_object_header:
    raise SystemExit("offscreen QML pause state must be thread-safe")
for pause_contract in (
    "_paused.store(true, std::memory_order_release)",
    "_paused.store(false, std::memory_order_release)",
    "_paused.load(std::memory_order_acquire)",
):
    if pause_contract not in shared_object_source:
        raise SystemExit(f"offscreen QML pause synchronization missing: {pause_contract}")

fixup_interface = (
    ROOT / "cmake/macros/FixupInterface.cmake"
).read_text(encoding="utf-8")
for post_build in fixup_interface.split(
    "add_custom_command(TARGET ${TARGET_NAME} POST_BUILD"
)[1:]:
    if post_build.index("remove_directory") > post_build.index("${MACDEPLOYQT_COMMAND}"):
        raise SystemExit("macOS bundle Frameworks must be cleared before macdeployqt")
    if '"$<TARGET_FILE_DIR:${TARGET_NAME}>/../Frameworks"' not in post_build:
        raise SystemExit("macOS bundle refresh must target Contents/Frameworks exactly")

bundle_freshness = (
    ROOT / "macos/ci/verify-bundle-freshness.sh"
).read_text(encoding="utf-8")
for freshness_contract in (
    "dwarfdump --uuid",
    "libgpu-gl.dylib",
    "OVERTE_MACOS_GL_DRAW begin",
    "bundle contains a stale",
):
    if freshness_contract not in bundle_freshness:
        raise SystemExit(f"macOS bundle freshness gate missing: {freshness_contract}")

opengl_display = (
    ROOT / "libraries/display-plugins/src/display-plugins/OpenGLDisplayPlugin.cpp"
).read_text(encoding="utf-8")
update_frame_data = opengl_display.split(
    "void OpenGLDisplayPlugin::updateFrameData()", 1
)[1].split("std::function<void(gpu::Batch&", 1)[0]
present_lock_body = update_frame_data.split("withPresentThreadLock([&] {", 1)[1].split(
    "});", 1
)[0]
for forbidden_locked_gl_work in (
    "processProgramsToSync",
    "consumeFrameUpdates",
):
    if forbidden_locked_gl_work in present_lock_body:
        raise SystemExit(
            "OpenGL frame processing must not hold the producer/present mutex: "
            + forbidden_locked_gl_work
        )
if "pendingFrames.swap(_newFrameQueue)" not in present_lock_body:
    raise SystemExit("OpenGL frame queue must be transferred atomically under its mutex")
for snapshot_queue_contract in (
    "pendingSnapshotOperators",
    "std::move(_currentFrame->snapshotOperators.front())",
    "_currentFrame->snapshotOperators.push",
):
    if snapshot_queue_contract not in update_frame_data:
        raise SystemExit(
            "OpenGL frame collapsing must preserve snapshot operators: "
            + snapshot_queue_contract
        )

script_manager = (
    ROOT / "libraries/script-engine/src/ScriptManager.cpp"
).read_text(encoding="utf-8")
shutdown_wait = script_manager.split(
    "void ScriptManager::waitTillDoneRunning(bool shutdown)", 1
)[1].split(
    "void ScriptManager::removeFromScriptEngines()", 1
)[0]
if "_engine->getScopeGuard()" in shutdown_wait:
    raise SystemExit(
        "shutdown wait must not acquire the script isolate from the main thread"
    )
subprocess.run(
    [sys.executable, str(ROOT / "macos/tests/screenshot-validator-test.py")],
    cwd=ROOT,
    check=True,
)
subprocess.run(
    [
        "node",
        str(ROOT / "macos/tests/profile-performance-script-test.js"),
        str(ROOT / "macos/tests/profile-performance-smoke.js"),
    ],
    cwd=ROOT,
    env={**os.environ, "OVERTE_TEST_FIXTURE_MODE": "diagnostic-lite"},
    check=True,
)
subprocess.run(
    [sys.executable, str(ROOT / "macos/tests/performance-validator-test.py")],
    cwd=ROOT,
    check=True,
)
subprocess.run(
    [sys.executable, str(ROOT / "macos/tests/performance-profile-tools-test.py")],
    cwd=ROOT,
    check=True,
)
subprocess.run(
    [sys.executable, str(ROOT / "macos/tests/online-loading-tools-test.py")],
    cwd=ROOT,
    check=True,
)
subprocess.run(
    [sys.executable, str(ROOT / "macos/tests/online-entity-validator-test.py")],
    cwd=ROOT,
    check=True,
)
subprocess.run(
    [
        "node",
        str(ROOT / "macos/tests/performance-script-test.js"),
        str(ROOT / "macos/tests/performance-smoke.js"),
    ],
    cwd=ROOT,
    check=True,
)
subprocess.run(
    [
        "node",
        str(ROOT / "macos/tests/profile-performance-script-test.js"),
        str(ROOT / "macos/tests/profile-performance-smoke.js"),
    ],
    cwd=ROOT,
    check=True,
)
subprocess.run(
    [
        "node",
        str(ROOT / "macos/tests/online-loading-script-test.js"),
        str(ROOT / "macos/tests/online-loading-benchmark.js"),
    ],
    cwd=ROOT,
    check=True,
)
subprocess.run(
    [sys.executable, str(ROOT / "macos/tests/stability-validator-test.py")],
    cwd=ROOT,
    check=True,
)
subprocess.run(
    [sys.executable, str(ROOT / "macos/tests/process-timeout-test.py")],
    cwd=ROOT,
    check=True,
)
subprocess.run(
    [sys.executable, str(ROOT / "macos/tests/compiler-watchdog-test.py")],
    cwd=ROOT,
    check=True,
)
subprocess.run(
    [sys.executable, str(ROOT / "macos/tests/runner-telemetry-test.py")],
    cwd=ROOT,
    check=True,
)
subprocess.run(
    [sys.executable, str(ROOT / "macos/tests/build-progress-test.py")],
    cwd=ROOT,
    check=True,
)
subprocess.run(
    [sys.executable, str(ROOT / "macos/tests/build-tree-checkpoint-test.py")],
    cwd=ROOT,
    check=True,
)
subprocess.run(
    [sys.executable, str(ROOT / "macos/tests/native-test-runner-test.py")],
    cwd=ROOT,
    check=True,
)

print("macOS runtime evidence contract valid")
