// SPDX-License-Identifier: Apache-2.0
#include <QString>
#include <QStringList>
#include <QList>
#include <QMetaEnum>
#include <QReadLocker>
#include <QReadWriteLock>
#include <QLoggingCategory>
#include <v8.h>
#include <libplatform/libplatform.h>
#include <atomic>
#include <cassert>
#include <memory>
#include <thread>
Q_LOGGING_CATEGORY(scriptengine_v8, "sh005.invocation-test")
struct ScriptValueV8Wrapper;
struct ScriptValue {
    std::shared_ptr<ScriptValueV8Wrapper> wrapper;
    bool failUnwrap { false };
    ScriptValue() = default;
    explicit ScriptValue(ScriptValueV8Wrapper* p) : wrapper(p) {}
};
using ScriptValueList = QList<ScriptValue>;
struct ContextBoundary {
    QStringList backtrace() { return {}; }
    QString currentFileName() { return {}; }
    int currentLineNumber() { return -1; }
};
struct ManagerBoundary {
    unsigned notifications { 0 };
    void scriptErrorMessage(const QString&, const QString&, int) { ++notifications; }
};
struct ScriptEngineV8 {
    v8::Isolate* isolate;
    v8::Local<v8::Context> context;
    ManagerBoundary* _manager;
    ContextBoundary contextBoundary;
    unsigned unwraps { 0 };
    v8::Isolate* getIsolate() { return isolate; }
    v8::Local<v8::Context> getContext() { return context; }
    ScriptValue undefinedValue();
    QString formatErrorMessageFromTryCatch(const v8::TryCatch&) { return QStringLiteral("captured diagnostic boundary"); }
    ContextBoundary* currentContext() { return &contextBoundary; }
};
QString getFileNameFromTryCatch(const v8::TryCatch&, v8::Isolate*, v8::Local<v8::Context>) { return {}; }
struct V8ScriptValue {
    ScriptEngineV8* engine;
    std::shared_ptr<v8::Global<v8::Value>> value;
    V8ScriptValue(ScriptEngineV8* owner, v8::Local<v8::Value> local) : engine(owner),
        value(std::make_shared<v8::Global<v8::Value>>(owner->isolate, local)) {}
    v8::Local<v8::Value> get() const { return value->Get(engine->isolate); }
    ScriptEngineV8* getEngine() const { return engine; }
};
struct ScriptValueV8Wrapper {
    ScriptEngineV8* _engine;
    V8ScriptValue _value;
    QReadWriteLock lock;
    ScriptValueV8Wrapper(ScriptEngineV8* engine, V8ScriptValue value) : _engine(engine), _value(std::move(value)) {}
    V8ScriptValue fullUnwrap(const ScriptValue& value) {
        ++_engine->unwraps;
        if (value.failUnwrap) { return V8ScriptValue(_engine, {}); }
        return value.wrapper ? value.wrapper->_value : V8ScriptValue(_engine, v8::Undefined(_engine->isolate));
    }
    ScriptValue call(const ScriptValue&, const ScriptValueList&);
    ScriptValue construct(const ScriptValueList&);
};
ScriptValue ScriptEngineV8::undefinedValue() {
    return ScriptValue(new ScriptValueV8Wrapper(this, V8ScriptValue(this, v8::Undefined(isolate))));
}
// Only manager/context diagnostic receivers and cross-engine conversion/value
// ownership are boundaries; both complete production invocation bodies follow.
#include "v8-invocation.inc"
static std::atomic<bool> entered { false };
static void markEntered(const v8::FunctionCallbackInfo<v8::Value>&) { entered.store(true, std::memory_order_release); }
int main(int argc, char** argv) {
    assert(argc == 3);
    const bool constructing = std::string(argv[1]) == "construct";
    const std::string mode(argv[2]);
    v8::V8::InitializeICUDefaultLocation(argv[0]);
    auto platform = v8::platform::NewDefaultPlatform();
    v8::V8::InitializePlatform(platform.get());
    assert(v8::V8::Initialize());
    auto allocator = std::unique_ptr<v8::ArrayBuffer::Allocator>(v8::ArrayBuffer::Allocator::NewDefaultAllocator());
    v8::Isolate::CreateParams parameters;
    parameters.array_buffer_allocator = allocator.get();
    auto isolate = v8::Isolate::New(parameters);
    {
        v8::Isolate::Scope isolateScope(isolate);
        v8::HandleScope handles(isolate);
        auto context = v8::Context::New(isolate);
        v8::Context::Scope contextScope(context);
        ManagerBoundary manager;
        ScriptEngineV8 engine { isolate, context, &manager };
        assert(context->Global()->Set(context, v8::String::NewFromUtf8Literal(isolate, "entered"),
            v8::Function::New(context, markEntered).ToLocalChecked()).FromJust());
        const char* source = constructing ? "(function(){ this.count=arguments.length; })" : "(function(){ return arguments.length; })";
        if (mode == "nonfunction") { source = "({})"; }
        if (mode == "arrow") { source = "(()=>42)"; }
        if (mode == "throw") { source = "(function(){ throw 17; })"; }
        if (mode == "terminate") { source = "(function(){ entered();for(;;){} })"; }
        const auto value = v8::Script::Compile(context, v8::String::NewFromUtf8(isolate, source).ToLocalChecked())
            .ToLocalChecked()->Run(context).ToLocalChecked();
        ScriptValueV8Wrapper wrapper(&engine, V8ScriptValue(&engine, value));
        ScriptValueList args;
        const int count = mode == "limit" ? Q_METAMETHOD_INVOKE_MAX_ARGS : mode == "over" ? Q_METAMETHOD_INVOKE_MAX_ARGS + 1 : mode == "empty-argument" ? 1 : 0;
        for (int i = 0; i < count; ++i) { args.append(ScriptValue()); }
        if (mode == "empty-argument") { args[0].failUnwrap = true; }
        v8::TryCatch caught(isolate);
        std::thread terminator;
        if (mode == "terminate") {
            terminator = std::thread([isolate] {
                while (!entered.load(std::memory_order_acquire)) { std::this_thread::yield(); }
                isolate->TerminateExecution();
            });
        }
        auto result = constructing ? wrapper.construct(args) : wrapper.call(ScriptValue(), args);
        if (terminator.joinable()) { terminator.join(); }
        assert(wrapper.lock.tryLockForWrite());
        wrapper.lock.unlock();
        if (mode == "terminate" || mode == "empty-argument") {
            assert(!result.wrapper && manager.notifications == 0);
        } else if (mode == "over" || mode == "nonfunction" || (constructing && mode == "arrow")) {
            assert(result.wrapper->_value.get()->IsUndefined() && engine.unwraps == 0);
        } else if (mode == "throw") {
            assert(result.wrapper->_value.get()->IsUndefined());
            if (constructing) { assert(caught.HasCaught()); }
            else { assert(manager.notifications > 0); }
        } else {
            assert(result.wrapper);
            auto returned = result.wrapper->_value.get();
            if (constructing) { returned = returned.As<v8::Object>()->Get(context, v8::String::NewFromUtf8Literal(isolate, "count")).ToLocalChecked(); }
            assert(returned->Int32Value(context).FromJust() == (mode == "arrow" ? 42 : count));
        }
    }
    isolate->Dispose();
    v8::V8::Dispose();
    v8::V8::DisposePlatform();
}
