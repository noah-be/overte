#!/usr/bin/env python3
"""Prevent arbitrary Qt event re-entry during V8 engine destruction."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "libraries/script-engine/src/v8/ScriptEngineV8.cpp"

source = SOURCE.read_text(encoding="utf-8")
start = source.index("ScriptEngineV8::~ScriptEngineV8()")
end = source.index("\nvoid ScriptEngineV8::perManagerLoopIterationCleanup()", start)
destructor = source[start:end]

if "QEventLoop" in destructor or ".processEvents(" in destructor:
    raise SystemExit(
        "ScriptEngineV8 destruction must not process unrelated thread events"
    )

deferred_flush = (
    "QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete)"
)
if destructor.count(deferred_flush) != 2:
    raise SystemExit(
        "ScriptEngineV8 destruction must flush only deferred deletions before "
        "and after proxy cleanup"
    )

print("script-engine destruction event contract valid")
