// SPDX-License-Identifier: Apache-2.0
#include "libraries/script-engine/src/v8/V8ExceptionDiagnostics.h"
#include <libplatform/libplatform.h>
#include <atomic>
#include <cassert>
#include <memory>
#include <thread>
#include <QLoggingCategory>
#include "libraries/script-engine/src/ScriptProgram.h"
Q_LOGGING_CATEGORY(scriptengine_v8, "sh005.v8-test")

class ScriptEngineV8 {
public:
    v8::Isolate* _v8Isolate;
    v8::Local<v8::Context> context;
    v8::Isolate* getIsolate() { return _v8Isolate; }
    v8::Local<v8::Context> getContext() { return context; }
    QString formatErrorMessageFromTryCatch(v8::TryCatch& caught);
};
// These two complete functions are extracted unchanged from production.
#include "v8-diagnostic-callers.inc"
#include "v8-syntax-result.inc"
// Only the engine's retained program storage is substituted; compilation,
// syntax-result class and all V8 operations below remain original source.
struct V8ScriptProgram {
    V8ScriptProgram() = default;
    V8ScriptProgram(ScriptEngineV8*, v8::Local<v8::Script>) {}
};
struct ScriptProgramV8Wrapper {
    ScriptEngineV8* _engine;
    QString _source;
    QString _url { QStringLiteral("focused-script.js") };
    V8ScriptProgram _value;
    bool _isCompiled { false };
    ScriptSyntaxCheckResultV8Wrapper _compileResult;
    bool compile();
};
#include "v8-program-compile.inc"

static std::atomic<bool> entered { false };
static void markEntered(const v8::FunctionCallbackInfo<v8::Value>&) {
    entered.store(true, std::memory_order_release);
}

int main(int argc, char** argv) {
    assert(argc == 2);
    const std::string mode(argv[1]);
    v8::V8::InitializeICUDefaultLocation(argv[0]);
    auto platform = v8::platform::NewDefaultPlatform();
    v8::V8::InitializePlatform(platform.get());
    assert(v8::V8::Initialize());
    auto allocator = std::unique_ptr<v8::ArrayBuffer::Allocator>(
        v8::ArrayBuffer::Allocator::NewDefaultAllocator());
    v8::Isolate::CreateParams parameters;
    parameters.array_buffer_allocator = allocator.get();
    auto isolate = v8::Isolate::New(parameters);
    {
        v8::Isolate::Scope isolateScope(isolate);
        v8::HandleScope handles(isolate);
        auto context = v8::Context::New(isolate);
        v8::Context::Scope contextScope(context);
        ScriptEngineV8 engine { isolate, context };
        if (mode == "none") {
            ScriptProgramV8Wrapper valid { &engine, QStringLiteral("1 + 2") };
            assert(valid.compile() && valid._isCompiled);
            assert(valid._compileResult.state() == ScriptSyntaxCheckResult::Valid);
            assert(valid.compile()); // cached result
            auto setup = v8::Script::Compile(context, v8::String::NewFromUtf8Literal(isolate,
                "globalThis.compileReads=0; Error.prepareStackTrace=()=>{compileReads++; return 'unsafe';}"))
                .ToLocalChecked();
            assert(!setup->Run(context).IsEmpty());
            ScriptProgramV8Wrapper invalid { &engine, QStringLiteral("function (") };
            assert(!invalid.compile() && !invalid._isCompiled);
            assert(invalid._compileResult.state() == ScriptSyntaxCheckResult::Error);
            assert(invalid._compileResult.errorLineNumber() == 1);
            assert(!invalid._compileResult.errorMessage().isEmpty());
            auto reads = context->Global()->Get(context,
                v8::String::NewFromUtf8Literal(isolate, "compileReads")).ToLocalChecked();
            assert(reads->Int32Value(context).FromJust() == 0);
            ScriptSyntaxCheckResultV8Wrapper retained(ScriptSyntaxCheckResult::Error,
                4, 5, QStringLiteral("failure"), QStringLiteral("captured frame"));
            assert(retained.errorBacktrace() == QStringLiteral("captured frame"));
        }
        isolate->SetCaptureStackTraceForUncaughtExceptions(true, 64);
        auto key = v8::String::NewFromUtf8Literal(isolate, "entered");
        assert(context->Global()->Set(context, key,
            v8::Function::New(context, markEntered).ToLocalChecked()).FromJust());
        const char* source = "throw new Error('ordinary failure')";
        if (mode == "getter") {
            source = "globalThis.reads=0; const e = {}; Object.defineProperty(e, 'stack', "
                     "{get(){ reads++; throw new Error('must not execute'); }}); throw e";
        } else if (mode == "prepare") {
            source = "globalThis.reads=0; Error.prepareStackTrace=()=>{reads++; "
                     "throw new Error('must not execute');}; throw new Error('captured')";
        } else if (mode == "empty") {
            source = "throw null";
        } else if (mode == "terminate") {
            source = "entered(); try { for(;;) {} } catch(e) { for(;;) {} }";
        }
        v8::TryCatch caught(isolate);
        if (mode == "empty") {
            caught.SetCaptureMessage(false);
        }
        if (mode != "none") {
            auto script = v8::Script::Compile(context,
                v8::String::NewFromUtf8(isolate, source).ToLocalChecked()).ToLocalChecked();
            std::thread terminator;
            if (mode == "terminate") {
                terminator = std::thread([isolate] {
                    while (!entered.load(std::memory_order_acquire)) {
                        std::this_thread::yield();
                    }
                    isolate->TerminateExecution();
                });
            }
            v8::Local<v8::Value> value;
            assert(!script->Run(context).ToLocal(&value));
            if (terminator.joinable()) { terminator.join(); }
            assert(caught.HasCaught());
        }
        auto diagnostic = overte::scripting::exceptionDiagnostics(isolate, context, caught);
        assert(!diagnostic.message.isEmpty());
        assert(getFileNameFromTryCatch(caught, isolate, context) == diagnostic.file);
        assert(engine.formatErrorMessageFromTryCatch(caught).contains(diagnostic.message));
        if (mode == "terminate") {
            assert(caught.HasTerminated());
            assert(caught.Message().IsEmpty());
            assert(diagnostic.terminated && diagnostic.file.isEmpty());
            assert(diagnostic.line == -1 && diagnostic.backtrace.isEmpty());
            assert(diagnostic.message == QStringLiteral("Script execution terminated"));
        } else if (mode == "empty" || mode == "none") {
            assert(caught.Message().IsEmpty());
            assert(!diagnostic.terminated && diagnostic.line == -1);
        } else {
            assert(!diagnostic.terminated && diagnostic.line == 1);
            if (mode == "getter" || mode == "prepare") {
                auto reads = context->Global()->Get(context,
                    v8::String::NewFromUtf8Literal(isolate, "reads")).ToLocalChecked();
                assert(reads->Int32Value(context).FromJust() == 0);
            }
        }
        // No CancelTerminateExecution: each test disposes its isolate after
        // unwinding. This does not claim the application can safely do so yet.
    }
    isolate->Dispose();
    v8::V8::Dispose();
    v8::V8::DisposePlatform();
}
