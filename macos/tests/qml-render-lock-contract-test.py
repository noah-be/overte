#!/usr/bin/env python3
"""Keep QML and the GUI thread out of macOS' long-running GL-lock waits."""

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

global_try_lock = qml_render.index("gl::globalTryLock()")
sync_branch = qml_render.index("if (sceneGraphSync)", global_try_lock)
sync_wake = qml_render.index("_shared->wakeRenderSyncWaiter()")
queued_retry = qml_render.index("QMetaObject::invokeMethod")
sync_retry = qml_render.index("shared->requestRenderSync()")
async_retry = qml_render.index("shared->requestRender()")
queued_connection = qml_render.index("Qt::QueuedConnection")
pre_render = qml_render.index("_shared->preRender(sceneGraphSync)")
first_gl_work = min(
    qml_render.index("resize()"),
    qml_render.index("glBindFramebuffer"),
)

if not (
    global_try_lock
    < sync_branch
    < sync_wake
    < queued_retry
    < sync_retry
    < async_retry
    < queued_connection
    < pre_render
    < first_gl_work
):
    raise SystemExit(
        "QML frames must acquire the macOS GL lock without waiting; a deferred "
        "sync must wake the GUI thread and queue the same sync request before "
        "any scene sync or GL work begins"
    )

if "QPointer<SharedObject> shared(_shared);" not in qml_render:
    raise SystemExit(
        "deferred QML retries must not dereference a destroyed SharedObject"
    )

if "gl::globalLock()" in qml_render:
    raise SystemExit("QML rendering must never block on the global GL lock")

if qml_render.count("gl::globalTryLock()") != 1:
    raise SystemExit("QML rendering must try the global GL lock exactly once")

if qml_render.count("gl::globalRelease()") != 2:
    raise SystemExit("qmlRender must release the acquired GL lock on every exit")

shared_source = (ROOT / "libraries/qml/src/qml/impl/SharedObject.cpp").read_text(
    encoding="utf-8"
)
wake_start = shared_source.index("void SharedObject::wakeRenderSyncWaiter()")
wake_end = shared_source.index("\nvoid SharedObject::onInitialize()", wake_start)
wake_function = shared_source[wake_start:wake_end]
if not (
    wake_function.index("QMutexLocker locker(&_mutex)")
    < wake_function.index("wake()")
):
    raise SystemExit(
        "the deferred sync wake must hold SharedObject's wait mutex to prevent "
        "a lost wake-up"
    )

if "bool globalTryLock();" not in gl_header:
    raise SystemExit("GLHelpers must expose the non-blocking global lock operation")

if "return _globalOpenGLLock.try_lock();" not in gl_source:
    raise SystemExit("macOS globalTryLock must use std::mutex::try_lock")

if "bool gl::globalTryLock() { return true; }" not in gl_source:
    raise SystemExit("platforms without global GL serialization must keep rendering")

print("QML render lock ordering contract valid")
