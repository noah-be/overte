#!/usr/bin/env python3
"""Keep QML scene synchronization outside macOS' long-running GL lock."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "libraries/qml/src/qml/impl/RenderEventHandler.cpp"
GL_HEADER = ROOT / "libraries/gl/src/gl/GLHelpers.h"
GL_SOURCE = ROOT / "libraries/gl/src/gl/GLHelpers.cpp"

source = SOURCE.read_text(encoding="utf-8")
gl_header = GL_HEADER.read_text(encoding="utf-8")
gl_source = GL_SOURCE.read_text(encoding="utf-8")
function_start = source.index("void RenderEventHandler::qmlRender(bool sceneGraphSync)")
function_end = source.index("\nvoid RenderEventHandler::onQuit()", function_start)
qml_render = source[function_start:function_end]

pre_render = qml_render.index("_shared->preRender(sceneGraphSync)")
sync_branch = qml_render.index("if (sceneGraphSync)", pre_render)
global_lock = qml_render.index("gl::globalLock()")
global_try_lock = qml_render.index("gl::globalTryLock()")
queued_retry = qml_render.index("QMetaObject::invokeMethod")
retry = qml_render.index("shared->requestRender()")
queued_connection = qml_render.index("Qt::QueuedConnection")
first_gl_work = min(
    qml_render.index("resize()"),
    qml_render.index("glBindFramebuffer"),
)

if not pre_render < sync_branch < global_lock < first_gl_work:
    raise SystemExit(
        "QML scene sync must wake the GUI thread before waiting for the macOS GL "
        "serialization lock, while all QML GL work remains serialized"
    )

if not (
    sync_branch
    < global_try_lock
    < queued_retry
    < retry
    < queued_connection
    < first_gl_work
):
    raise SystemExit(
        "asynchronous QML frames must defer and retry instead of blocking their "
        "render thread behind the macOS GL serialization lock; the retry must "
        "be queued safely onto the SharedObject thread"
    )

if qml_render.count("gl::globalLock()") != 1:
    raise SystemExit("sync QML rendering must acquire the global GL lock exactly once")

if qml_render.count("gl::globalTryLock()") != 1:
    raise SystemExit("async QML rendering must try the global GL lock exactly once")

if qml_render.count("gl::globalRelease()") != 1:
    raise SystemExit("qmlRender must release the global GL lock exactly once")

if "bool globalTryLock();" not in gl_header:
    raise SystemExit("GLHelpers must expose the non-blocking global lock operation")

if "return _globalOpenGLLock.try_lock();" not in gl_source:
    raise SystemExit("macOS globalTryLock must use std::mutex::try_lock")

if "bool gl::globalTryLock() { return true; }" not in gl_source:
    raise SystemExit("platforms without global GL serialization must keep rendering")

print("QML render lock ordering contract valid")
