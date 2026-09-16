// SPDX-License-Identifier: Apache-2.0
#include <QString>
#include <QStringList>
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
    using PropertyFlags = int;
    static constexpr int PropertyGetter = 1, PropertySetter = 2;
    using ResolveFlags = int;
    std::shared_ptr<ScriptValueV8Wrapper> wrapper;
    ScriptValue() = default;
    explicit ScriptValue(ScriptValueV8Wrapper* value) : wrapper(value) {}
};
struct ScriptEngineV8 {
    v8::Isolate* isolate;
    v8::Local<v8::Context> context;
    v8::Isolate* _v8Isolate = isolate;
    void abortEvaluation();
#include "abort-state.inc"
    v8::Isolate* getIsolate() { return isolate; }
    v8::Local<v8::Context> getContext() { return context; }
    struct Context { QStringList backtrace() { return {}; } } boundary;
    Context* currentContext() { return &boundary; }
    ScriptValue undefinedValue();
    ScriptValue nullValue();
};
#include "abort-method.inc"
struct V8ScriptValue {
    ScriptEngineV8* engine;
    std::shared_ptr<v8::Global<v8::Value>> value;
    V8ScriptValue(ScriptEngineV8* owner, v8::Local<v8::Value> local) : engine(owner),
        value(std::make_shared<v8::Global<v8::Value>>(owner->isolate, local)) {}
    v8::Local<v8::Value> constGet() const { return value->Get(engine->isolate); }
    v8::Local<v8::Value> get() const { return constGet(); }
    v8::Local<v8::Context> constGetContext() const { return engine->context; }
};
struct ScriptValueV8Wrapper {
    ScriptEngineV8* _engine;
    V8ScriptValue _value;
    mutable QReadWriteLock lock;
    ScriptValueV8Wrapper(ScriptEngineV8* engine, V8ScriptValue value) : _engine(engine), _value(std::move(value)) {}
    ScriptValue property(const QString&, const ScriptValue::ResolveFlags&) const;
    ScriptValue data() const;
    ScriptValue property(quint32, const ScriptValue::ResolveFlags&) const;
    bool hasProperty(const QString&) const;
    ScriptValue prototype() const;
    void setData(const ScriptValue&);
    void setProperty(const QString&, const ScriptValue&, const ScriptValue::PropertyFlags&);
    void setProperty(quint32, const ScriptValue&, const ScriptValue::PropertyFlags&);
    void setPrototype(const ScriptValue&);
    static ScriptValueV8Wrapper* unwrap(const ScriptValue& v) { return v.wrapper.get(); }
    const V8ScriptValue& toV8Value() const { return _value; }
    V8ScriptValue fullUnwrap(const ScriptValue& v) const {
        return v.wrapper ? v.wrapper->_value : V8ScriptValue(_engine, v8::Undefined(_engine->isolate));
    }
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
    const bool boundary = scenario.rfind("boundary-", 0) == 0;
    const auto split = scenario.rfind('-');
    const auto operation = boundary ? scenario.substr(9, split - 9) : std::string();
    const auto mode = boundary ? scenario.substr(split + 1) : dataGetter ? scenario.substr(5) : scenario;
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
        if (mode == "stopped") { source = "({get secretProperty(){entered();return 42;}})"; }
        if (mode == "missing") { source = "({})"; }
        if (mode == "null") { source = "null"; }
        if (boundary) { source = "new Proxy({secretProperty:42,0:42}, {get(t,k,r){entered();return Reflect.get(t,k,r);},set(t,k,v,r){entered();return Reflect.set(t,k,v,r);},setPrototypeOf(t,p){entered();return Reflect.setPrototypeOf(t,p);}})"; }
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
        if (mode == "stopped") { engine.abortEvaluation(); isolate->CancelTerminateExecution(); }
        if (boundary) {
            const bool stopped = mode == "stopped";
            ScriptValue replacement(new ScriptValueV8Wrapper(&engine, V8ScriptValue(&engine, v8::Object::New(isolate))));
            if (operation == "has") { assert(wrapper.hasProperty("secretProperty") == !stopped); }
            else if (operation == "index" || operation == "prototype") {
                const auto result = operation == "index" ? wrapper.property(quint32(0), 0) : wrapper.prototype();
                assert(bool(result.wrapper) == !stopped);
                if (!stopped && operation == "index") { assert(result.wrapper->_value.constGet()->Int32Value(context).FromJust() == 42); }
            } else if (operation == "setname") { wrapper.setProperty(QStringLiteral("secretProperty"), replacement, 0); }
            else if (operation == "setindex") { wrapper.setProperty(quint32(0), replacement, 0); }
            else if (operation == "setdata") { wrapper.setData(replacement); }
            else if (operation == "setproto") { wrapper.setPrototype(replacement); }
            else { assert(false); }
            if (stopped) { assert(!entered.load()); }
            else if (operation != "prototype") { assert(entered.load()); }
            assert(!caught.HasCaught() && wrapper.lock.tryLockForWrite());
            wrapper.lock.unlock();
        } else {
        auto result = dataGetter ? wrapper.data() : wrapper.property(QStringLiteral("secretProperty"),0);
        if (terminator.joinable()) { terminator.join(); }
        // A failed named getter previously leaked a read lock here.
        assert(wrapper.lock.tryLockForWrite());
        wrapper.lock.unlock();
        assert(caught.HasCaught() == (mode == "throw" || mode == "terminate"));
        if (mode == "stopped") {
            assert(!entered.load() && !result.wrapper && engine.isEvaluationAborted());
        } else if (mode == "terminate") {
            assert(caught.HasTerminated() && !result.wrapper);
        } else {
            assert(result.wrapper);
            auto returned = result.wrapper->_value.constGet();
            if (mode == "ordinary") { assert(returned->Int32Value(context).FromJust() == 42); }
            else if (dataGetter && mode == "null") { assert(returned->IsNull()); }
            else { assert(returned->IsUndefined()); }
        }
        }
    }
    isolate->Dispose();
    v8::V8::Dispose();
    v8::V8::DisposePlatform();
}
