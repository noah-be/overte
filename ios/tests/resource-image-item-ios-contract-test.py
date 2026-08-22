#!/usr/bin/env python3
"""Ensure ResourceImageItem has no GL renderer in the iOS compile branch."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
header = (ROOT / "interface/src/ui/ResourceImageItem.h").read_text(encoding="utf-8")
source = (ROOT / "interface/src/ui/ResourceImageItem.cpp").read_text(encoding="utf-8")

ios_start = header.index("#if defined(Q_OS_IOS)")
other = header.index("#else", ios_start)
ios_header = header[ios_start:other]
if "using ResourceImageItemBase = QQuickItem" not in ios_header:
    raise SystemExit("iOS ResourceImageItem is not based on QQuickItem")
for forbidden in ("QQuickFramebufferObject", "QOpenGLFramebufferObject", "GLsync", "gl/Config.h"):
    if forbidden in ios_header:
        raise SystemExit(f"iOS ResourceImageItem header branch exposes {forbidden}")

for token in ("ResourceImageItemRenderer::render", "glWaitSync", "QOpenGLFramebufferObjectFormat"):
    position = source.index(token)
    renderer_guard = source.rfind("#if !defined(Q_OS_IOS)", 0, position)
    renderer_end = source.find("#endif", position)
    if renderer_guard < 0 or renderer_end < 0 or source.find("#endif", renderer_guard, position) >= 0:
        raise SystemExit(f"GL renderer token {token!r} escaped non-iOS guard")
for token in ("ResourceImageItem rendering is disabled on iOS", "qCritical()"):
    if token not in source:
        raise SystemExit(f"iOS ResourceImageItem fail-closed diagnostic missing {token!r}")

print("iOS ResourceImageItem contract valid: plain QQuickItem; GL renderer excluded; fail closed")
