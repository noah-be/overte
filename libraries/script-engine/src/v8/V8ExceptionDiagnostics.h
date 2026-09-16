// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <QString>
#include <QStringList>
#include <v8.h>

namespace overte { namespace scripting {

// Read V8's captured metadata only. Reading exception.stack or coercing an
// arbitrary resource/exception object can execute hostile JavaScript getters.
// This is diagnostic hardening, not an engine cancellation/consent mechanism.
struct ExceptionDiagnostics {
    bool terminated { false };
    QString message { QStringLiteral("Script exception (no captured message)") };
    QString file;
    int line { -1 };
    int column { -1 };
    QStringList backtrace;
};

inline QString capturedString(v8::Isolate* isolate, v8::Local<v8::Value> value) {
    if (value.IsEmpty() || !value->IsString()) {
        return {};
    }
    v8::String::Utf8Value bytes(isolate, value.As<v8::String>());
    return *bytes ? QString::fromUtf8(*bytes, bytes.length()) : QString();
}

inline ExceptionDiagnostics exceptionDiagnostics(v8::Isolate* isolate,
        v8::Local<v8::Context> context, const v8::TryCatch& caught) {
    ExceptionDiagnostics result;
    result.terminated = caught.HasTerminated() || isolate->IsExecutionTerminating();
    if (result.terminated) {
        result.message = QStringLiteral("Script execution terminated");
        return result;
    }
    const auto message = caught.Message();
    if (message.IsEmpty()) {
        return result;
    }
    const auto text = capturedString(isolate, message->Get());
    if (!text.isEmpty()) {
        result.message = text;
    }
    result.file = capturedString(isolate, message->GetScriptResourceName());
    result.line = message->GetLineNumber(context).FromMaybe(-1);
    result.column = message->GetStartColumn(context).FromMaybe(-1);
    const auto stack = message->GetStackTrace();
    if (!stack.IsEmpty()) {
        // A bounded captured stack does not invoke Error.prepareStackTrace.
        for (int i = 0; i < stack->GetFrameCount() && i < 32; ++i) {
            const auto frame = stack->GetFrame(isolate, i);
            if (!frame.IsEmpty()) {
                result.backtrace.append(QStringLiteral("%1 (%2:%3:%4)")
                    .arg(capturedString(isolate, frame->GetFunctionName()))
                    .arg(capturedString(isolate, frame->GetScriptName()))
                    .arg(frame->GetLineNumber()).arg(frame->GetColumn()));
            }
        }
    }
    return result;
}

}} // namespace overte::scripting
