//
// PhoneQmlFatalDiagnostics.h
// Copyright 2026 Overte e.V.
// Distributed under the Apache License, Version 2.0.
// See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//
// Diagnostic snapshot for the matching Qt 5.15.18 private ABI; Phone only.
#pragma once
#if defined(ANDROID_APP_PHONE_INTERFACE)
#include <private/qqmlengine_p.h>
#include <private/qv4engine_p.h>
#include <private/qv4stackframe_p.h>
#include <QThread>
#include <android/log.h>
#include <cstdint>

namespace {
struct PhoneQmlSlot { QQmlEngine* object {}; QV4::ExecutionEngine* engine {}; unsigned id {}; };
// All engines are created and destroyed on the application thread. Other threads
// intentionally see no entries; never traverse a different thread's engine.
thread_local PhoneQmlSlot phoneQmlSlots[32];
thread_local unsigned phoneQmlNextId = 0;
thread_local unsigned phoneQmlRegistryOverflow = 0;
thread_local bool phoneQmlInFatal = false;
void phoneRegisterQmlEngine(QQmlEngine* object) {
    if (object->thread() != QThread::currentThread()) return;
    for (const auto& slot : phoneQmlSlots) if (slot.object == object) return;
    for (auto& slot : phoneQmlSlots) {
        if (slot.object) continue;
        slot = { object, QQmlEnginePrivate::get(object)->v4engine(), ++phoneQmlNextId };
        QObject::connect(object, &QObject::destroyed, [](QObject* dying) {
            for (auto& entry : phoneQmlSlots)
                if (entry.object == dying) entry = {};
        });
        return;
    }
    ++phoneQmlRegistryOverflow;
}
void phoneUnregisterQmlEngine(QQmlEngine* object) {
    for (auto& slot : phoneQmlSlots) if (slot.object == object) slot = {};
}
// Non-cryptographic identifiers for packaged source correlation, not secrets.
uint64_t phoneQmlSourceId(const QString& source) noexcept {
    uint64_t h = UINT64_C(14695981039346656037);
    for (const auto ch : source) { h ^= ch.unicode(); h *= UINT64_C(1099511628211); }
    return h;
}
}
extern "C" void overtePhoneQmlFatalSnapshot() noexcept {
    if (phoneQmlInFatal) return;
    phoneQmlInFatal = true;
    __android_log_print(ANDROID_LOG_FATAL, "OvertePhoneQml",
        "qml_fatal_registry overflow=%u", phoneQmlRegistryOverflow);
    for (const auto& slot : phoneQmlSlots) {
        auto* engine = slot.engine;
        if (!engine || !engine->currentStackFrame) continue;
        // uintptr_t arithmetic avoids undefined subtraction of corrupted pointers.
        const uintptr_t base = reinterpret_cast<uintptr_t>(engine->jsStackBase);
        const uintptr_t top = reinterpret_cast<uintptr_t>(engine->jsStackTop);
        __android_log_print(ANDROID_LOG_FATAL, "OvertePhoneQml",
            "qml_fatal engine=%u stack_nonnegative=%d stack_bytes=%llu",
            slot.id, top >= base, static_cast<unsigned long long>(top >= base ? top - base : 0));
        auto* frame = engine->currentStackFrame;
        for (unsigned depth = 0; frame && depth < 8; ++depth) {
            if (frame->engine != engine) break;
            auto* function = frame->v4Function;
            auto* compiled = function ? function->compiledFunction : nullptr;
            if (!compiled) break;
            // source() only copies a refcounted QString from the compilation unit.
            // Do NOT call function(), stackTrace(), qmlScopeObject(), property(),
            // evaluate(), or any API constructing QV4::Scope / running JavaScript.
            const auto source = frame->source();
            __android_log_print(ANDROID_LOG_FATAL, "OvertePhoneQml",
                "qml_frame engine=%u depth=%u source_id=%llu name_index=%u ip=%d code_size=%u registers=%u",
                slot.id, depth, static_cast<unsigned long long>(phoneQmlSourceId(source)),
                unsigned(compiled->nameIndex), frame->instructionPointer,
                unsigned(compiled->codeSize), unsigned(compiled->nRegisters));
            // A bounded local bytecode window allows offline instruction/lookup
            // decoding. Bytecode contains numeric operands, never URL/string data.
            const int size = int(compiled->codeSize);
            const int ip = frame->instructionPointer;
            if (function->codeData && size >= 0 && size <= 1024 * 1024 && ip >= 0 && ip <= size) {
                const int begin = ip > 24 ? ip - 24 : 0;
                const int end = ip + 24 < size ? ip + 24 : size;
                for (int pos = begin; pos < end; ++pos)
                    __android_log_print(ANDROID_LOG_FATAL, "OvertePhoneQml",
                        "qml_byte engine=%u depth=%u offset=%d value=%u", slot.id, depth, pos,
                        unsigned(static_cast<unsigned char>(function->codeData[pos])));
            }
            if (frame->parent == frame) break;
            frame = frame->parent;
        }
    }
    // This function is called immediately before the existing fatal abort path.
    // Deliberately retain the reentrancy guard.
}
#endif
