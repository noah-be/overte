// SPDX-License-Identifier: Apache-2.0
#include <QString>
#include <QList>
#include <v8.h>
#include <libplatform/libplatform.h>
#include <atomic>
#include <cassert>
#include <cmath>
#include <limits>
#include <memory>
#include <thread>
struct ScriptValueV8Wrapper;
struct ScriptValue {
    std::shared_ptr<ScriptValueV8Wrapper> wrapper;
    ScriptValue() = default;
    explicit ScriptValue(ScriptValueV8Wrapper* p) : wrapper(p) {}
};
struct ScriptEngineV8 {
    v8::Isolate* isolate;
    v8::Local<v8::Context> context;
    v8::Isolate* getIsolate() { return isolate; }
    v8::Local<v8::Context> getContext() { return context; }
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
    ScriptValueV8Wrapper(ScriptEngineV8* engine, V8ScriptValue value) : _engine(engine), _value(std::move(value)) {}
    static ScriptValueV8Wrapper* unwrap(const ScriptValue& v) { return v.wrapper.get(); }
    const V8ScriptValue& toV8Value() const { return _value; }
    bool strictlyEquals(const ScriptValue&) const;
    bool equals(const ScriptValue&) const;
    QList<QString> getPropertyNames() const;
    qint32 toInt32() const;
    double toInteger() const;
    double toNumber() const;
    QString toString() const;
    quint16 toUInt16() const;
    quint32 toUInt32() const;
};
// Only engine/value ownership storage is substituted.
#include "v8-conversion.inc"
static std::atomic<bool> entered { false };
static void markEntered(const v8::FunctionCallbackInfo<v8::Value>&) { entered.store(true, std::memory_order_release); }
int main(int argc, char** argv) {
    assert(argc == 3);
    const std::string kind(argv[1]), mode(argv[2]);
    v8::V8::InitializeICUDefaultLocation(argv[0]);
    auto platform = v8::platform::NewDefaultPlatform();
    v8::V8::InitializePlatform(platform.get());
    assert(v8::V8::Initialize());
    auto allocator = std::unique_ptr<v8::ArrayBuffer::Allocator>(v8::ArrayBuffer::Allocator::NewDefaultAllocator());
    v8::Isolate::CreateParams parameters;
    parameters.array_buffer_allocator = allocator.get();
    auto isolate = v8::Isolate::New(parameters);
    auto otherIsolate = v8::Isolate::New(parameters);
    {
        ScriptEngineV8 foreign { otherIsolate, {} };
        ScriptValue cross;
        {
            v8::Isolate::Scope foreignScope(otherIsolate);
            v8::HandleScope handles(otherIsolate);
            cross = ScriptValue(new ScriptValueV8Wrapper(&foreign, V8ScriptValue(&foreign, v8::Number::New(otherIsolate, 42))));
        }
        v8::Isolate::Scope isolateScope(isolate);
        v8::HandleScope handles(isolate);
        auto context = v8::Context::New(isolate);
        v8::Context::Scope contextScope(context);
        ScriptEngineV8 engine { isolate, context };
        assert(context->Global()->Set(context, v8::String::NewFromUtf8Literal(isolate, "entered"),
            v8::Function::New(context, markEntered).ToLocalChecked()).FromJust());
        const char* source = "42.75";
        if (kind == "strict") { source = "42"; }
        if (kind == "equals") { source = "({valueOf(){globalThis.count=(globalThis.count||0)+1;if(count>1)throw 7;return 42;}})"; }
        if (kind == "names") { source = "({'a\\u0000b':1,42:2})"; }
        if (mode == "throw") { source = kind == "names" ? "new Proxy({}, {ownKeys(){throw 17;}})" : "({[Symbol.toPrimitive](){throw 17;}})"; }
        if (mode == "terminate") { source = kind == "names" ? "new Proxy({}, {ownKeys(){entered();for(;;){}}})" : "({[Symbol.toPrimitive](){entered();for(;;){}}})"; }
        if (mode == "wrap") { source = "4294967297"; }
        if (mode == "nul") { source = "'a\\u0000b'"; }
        if (mode == "nan") { source = "undefined"; }
        auto value = v8::Script::Compile(context, v8::String::NewFromUtf8(isolate, source).ToLocalChecked())
            .ToLocalChecked()->Run(context).ToLocalChecked();
        if (mode == "empty") { value = {}; }
        ScriptValueV8Wrapper wrapper(&engine, V8ScriptValue(&engine, value));
        ScriptValue other(new ScriptValueV8Wrapper(&engine, V8ScriptValue(&engine, v8::Number::New(isolate, 42))));
        if (mode == "missing") { other = {}; }
        if (mode == "cross") { other = cross; }
        v8::TryCatch caught(isolate);
        std::thread terminator;
        if (mode == "terminate") {
            terminator = std::thread([isolate] {
                while (!entered.load(std::memory_order_acquire)) { std::this_thread::yield(); }
                isolate->TerminateExecution();
            });
        }
        const bool failed = mode == "throw" || mode == "terminate" || mode == "empty";
        if (kind == "equals" || kind == "strict") {
            const bool result = kind == "equals" ? wrapper.equals(other) : wrapper.strictlyEquals(other);
            assert(result == (mode == "ordinary"));
            if (kind == "equals" && mode == "ordinary") {
                auto count = context->Global()->Get(context, v8::String::NewFromUtf8Literal(isolate, "count")).ToLocalChecked();
                assert(count->Int32Value(context).FromJust() == 1);
            }
        } else if (kind == "names") {
            const auto names = wrapper.getPropertyNames();
            if (failed) { assert(names.isEmpty()); }
            else { assert(names.size() == 2 && names[0] == "42" && names[1] == QString::fromUtf8("a\0b", 3)); }
        } else if (kind == "string") {
            const auto text = wrapper.toString();
            if (failed) { assert(text.isEmpty()); }
            else { assert(text == (mode == "nul" ? QString::fromUtf8("a\0b", 3) : QStringLiteral("42.75"))); }
        } else {
            const double result = kind == "int32" ? wrapper.toInt32() : kind == "integer" ? wrapper.toInteger() :
                kind == "number" ? wrapper.toNumber() : kind == "uint16" ? wrapper.toUInt16() : wrapper.toUInt32();
            if (kind == "number" && (failed || mode == "nan")) { assert(std::isnan(result)); }
            else { assert(result == (failed ? 0 : mode == "wrap" ? 1 : kind == "number" ? 42.75 : 42)); }
        }
        if (terminator.joinable()) { terminator.join(); }
        assert(caught.HasCaught() == (mode == "throw" || mode == "terminate"));
        if (mode == "terminate") { assert(caught.HasTerminated()); }
    }
    otherIsolate->Dispose();
    isolate->Dispose();
    v8::V8::Dispose();
    v8::V8::DisposePlatform();
}
