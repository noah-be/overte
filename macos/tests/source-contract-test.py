#!/usr/bin/env python3
"""Validate the macOS bootstrap's runtime evidence contract."""

from pathlib import Path
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
for marker in ONLINE_CONTRACT | {"render_handoff": ""}:
    if marker not in online_smoke:
        raise SystemExit(f"online smoke runner does not require {marker}")

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
for smoke_name, smoke_source, maximum in (
    ("serverless", smoke, 720),
    ("online", online_smoke, 720),
):
    default_timeout = re.search(
        r'OVERTE_MACOS_SMOKE_TIMEOUT_SECONDS:-([0-9]+)', smoke_source
    )
    if not default_timeout or int(default_timeout.group(1)) > maximum:
        raise SystemExit(f"{smoke_name} smoke timeout must be at most {maximum}s")

serverless_script = (ROOT / "macos/tests/serverless-smoke.js").read_text(encoding="utf-8")
online_script = (ROOT / "macos/tests/online-smoke.js").read_text(encoding="utf-8")
for script_name, script_source, snapshot_name in (
    ("serverless", serverless_script, "macos-serverless-smoke.png"),
    ("online", online_script, "macos-online-smoke.png"),
):
    for render_contract in (
        "Render.renderMethod = 1",
        "Render.shadowsEnabled = false",
        "Render.ambientOcclusionEnabled = false",
        "Render.antialiasingMode = 0",
        "Render.viewportResolutionScale = 0.5",
        "Scene.shouldRenderAvatars = false",
        "Script.stop()",
        snapshot_name,
    ):
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
if "fixture_entities=3" not in serverless_script:
    raise SystemExit("serverless smoke must identify the exact three fixture entities")
for fixture_name in (
    "macOS smoke red cube",
    "macOS smoke cyan sphere",
    "macOS smoke label",
):
    if fixture_name not in serverless_script:
        raise SystemExit(f"serverless smoke does not require fixture: {fixture_name}")

main_source = (ROOT / "interface/src/main.cpp").read_text(encoding="utf-8")
if main_source.count('"disableLocalAvatar"') != 1:
    raise SystemExit("the local-avatar suppression option must be declared exactly once")
if "parser.addOption(disableLocalAvatarOption);" not in main_source:
    raise SystemExit("the local-avatar suppression option is not registered")

application_setup_source = (ROOT / "interface/src/Application_Setup.cpp").read_text(
    encoding="utf-8"
)
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

print("macOS runtime evidence contract valid")
