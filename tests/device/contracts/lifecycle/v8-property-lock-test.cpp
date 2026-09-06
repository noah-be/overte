// SPDX-License-Identifier: Apache-2.0
#include <QString>
#include <v8.h>
#include <libplatform/libplatform.h>
#include <QReadLocker>
#include <QReadWriteLock>
#include <QLoggingCategory>
#include <atomic>
#include <cassert>
#include <memory>
#include <thread>
Q_LOGGING_CATEGORY(scriptengine_v8, "sh005.property-test")

struct ScriptValueV8Wrapper;
struct ScriptValue {
    using ResolveFlags = int;
    std::shared_ptr<ScriptValueV8Wrapper> wrapper;
    ScriptValue() = default;
    explicit ScriptValue(ScriptValueV8Wrapper* value) : wrapper(value) {}
};
struct ScriptEngineV8 {
    v8::Isolate* isolate;
    v8::Local<v8::Context> context;
    v8::Isolate* getIsolate() { return isolate; }
    v8::Local<v8::Context> getContext() { return context; }
    ScriptValue undefinedValue();
    ScriptValue nullValue();
};
struct V8ScriptValue {
    ScriptEngineV8* engine;
    std::shared_ptr<v8::Global<v8::Value>> value;
    V8ScriptValue(ScriptEngineV8* owner, v8::Local<v8::Value> local) : engine(owner),
        value(std::make_shared<v8::Global<v8::Value>>(owner->isolate, local)) {}
    v8::Local<v8::Value> constGet() const { return value->Get(engine->isolate); }
};
struct ScriptValueV8Wrapper {
    ScriptEngineV8* _engine;
    V8ScriptValue _value;
    mutable QReadWriteLock lock;
    ScriptValueV8Wrapper(ScriptEngineV8* engine, V8ScriptValue value) : _engine(engine), _value(std::move(value)) {}
    ScriptValue property(const QString&, const ScriptValue::ResolveFlags&) const;
    ScriptValue data() const;
};
ScriptValue ScriptEngineV8::undefinedValue() {
    return ScriptValue(new ScriptValueV8Wrapper(this, V8ScriptValue(this, v8::Undefined(isolate))));
}
ScriptValue ScriptEngineV8::nullValue() {
    return ScriptValue(new ScriptValueV8Wrapper(this, V8ScriptValue(this, v8::Null(isolate))));
}
// Original complete function; only engine/value lifetime storage is substituted.
#include "v8-property-lock.inc"
#include "v8-data-getter.inc"

static std::atomic<bool> entered { false };
static void markEntered(const v8::FunctionCallbackInfo<v8::Value>&) {
    entered.store(true, std::memory_order_release);
}

int main(int argc, char** argv) {
    assert(argc == 2);
    const std::string scenario(argv[1]);
    const bool dataGetter = scenario.rfind("data-",0) == 0;
    const auto mode = dataGetter ? scenario.substr(5) : scenario;
    v8::V8::InitializeICUDefaultLocation(argv[0]);
    auto platform = v8::platform::NewDefaultPlatform();
    v8::V8::InitializePlatform(platform.get());
    assert(v8::V8::Initialize());
    auto allocator = std::unique_ptr<v8::ArrayBuffer::Allocator>(v8::ArrayBuffer::Allocator::NewDefaultAllocator());
    v8::Isolate::CreateParams parameters;
    parameters.array_buffer_allocator = allocator.get();
    auto isolate = v8::Isolate::New(parameters);
    {
        v8::Isolate::Scope scope(isolate);
        v8::HandleScope handles(isolate);
        auto context = v8::Context::New(isolate);
        v8::Context::Scope contextScope(context);
        ScriptEngineV8 engine { isolate, context };
        assert(context->Global()->Set(context, v8::String::NewFromUtf8Literal(isolate,"entered"),
            v8::Function::New(context,markEntered).ToLocalChecked()).FromJust());
        const char* source = "({secretProperty:42})";
        if (mode == "throw") { source = "({get secretProperty(){throw 1;}})"; }
        if (mode == "terminate") { source = "({get secretProperty(){entered();for(;;){}}})"; }
        if (mode == "missing") { source = "({})"; }
        if (mode == "null") { source = "null"; }
        const auto effectiveSource = dataGetter ? QString::fromUtf8(source).replace("secretProperty","__data").toUtf8() : QByteArray(source);
        auto value = v8::Script::Compile(context,v8::String::NewFromUtf8(isolate,effectiveSource.constData()).ToLocalChecked())
            .ToLocalChecked()->Run(context).ToLocalChecked();
        ScriptValueV8Wrapper wrapper(&engine,V8ScriptValue(&engine,value));
        v8::TryCatch caught(isolate);
        std::thread terminator;
        if (mode == "terminate") {
            terminator = std::thread([isolate] {
                while (!entered.load(std::memory_order_acquire)) { std::this_thread::yield(); }
                isolate->TerminateExecution();
            });
        }
        auto result = dataGetter ? wrapper.data() : wrapper.property(QStringLiteral("secretProperty"),0);
        if (terminator.joinable()) { terminator.join(); }
        // A failed named getter previously leaked a read lock here.
        assert(wrapper.lock.tryLockForWrite());
        wrapper.lock.unlock();
        assert(caught.HasCaught() == (mode == "throw" || mode == "terminate"));
        if (mode == "terminate") {
            assert(caught.HasTerminated() && !result.wrapper);
        } else {
            assert(result.wrapper);
            auto returned = result.wrapper->_value.constGet();
            if (mode == "ordinary") { assert(returned->Int32Value(context).FromJust() == 42); }
            else if (dataGetter && mode == "null") { assert(returned->IsNull()); }
            else { assert(returned->IsUndefined()); }
        }
    }
    isolate->Dispose();
    v8::V8::Dispose();
    v8::V8::DisposePlatform();
}
