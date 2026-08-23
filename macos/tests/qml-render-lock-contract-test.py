#!/usr/bin/env python3
"""Keep QML scene synchronization outside macOS' long-running GL lock."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "libraries/qml/src/qml/impl/RenderEventHandler.cpp"

source = SOURCE.read_text(encoding="utf-8")
function_start = source.index("void RenderEventHandler::qmlRender(bool sceneGraphSync)")
function_end = source.index("\nvoid RenderEventHandler::onQuit()", function_start)
qml_render = source[function_start:function_end]

pre_render = qml_render.index("_shared->preRender(sceneGraphSync)")
global_lock = qml_render.index("gl::globalLock()")
first_gl_work = min(
    qml_render.index("resize()"),
    qml_render.index("glBindFramebuffer"),
)

if not pre_render < global_lock < first_gl_work:
    raise SystemExit(
        "QML scene sync must wake the GUI thread before waiting for the macOS GL "
        "serialization lock, while all QML GL work remains serialized"
    )

if qml_render.count("gl::globalLock()") != 1:
    raise SystemExit("qmlRender must acquire the global GL lock exactly once")

if qml_render.count("gl::globalRelease()") != 1:
    raise SystemExit("qmlRender must release the global GL lock exactly once")

print("QML render lock ordering contract valid")
