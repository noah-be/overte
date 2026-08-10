#!/usr/bin/env python3
"""Contract for excluding GL-only diagnostics from iOS Application_Graphics."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
source = (ROOT / "interface/src/Application_Graphics.cpp").read_text(encoding="utf-8")

for token in ("gl::ContextInfo::get(true)", "glGetString(GL_VENDOR)"):
    position = source.index(token)
    guard = source.rfind("#if !defined(Q_OS_IOS)", 0, position)
    close = source.find("#endif", position)
    if guard < 0 or close < 0 or source.find("#endif", guard, position) >= 0:
        raise SystemExit(f"iOS Application_Graphics still compiles GL diagnostic {token!r}")

for core_token in ("_primaryWidget->createContext(globalShareContext)", "_graphicsEngine->initializeGPU(_primaryWidget)"):
    if core_token not in source:
        raise SystemExit(f"core graphics initialization was unexpectedly removed: {core_token}")

print("iOS Application_Graphics diagnostics valid: GL info/vendor excluded; core initialization preserved")
