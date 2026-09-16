// SPDX-License-Identifier: Apache-2.0
#include <QVariant>
#include <QHash>
#include <QReadWriteLock>
#include <QDateTime>
#include <QLoggingCategory>
#include <QObject>
#include <v8.h>
#include <libplatform/libplatform.h>
#include <atomic>
#include <cassert>
#include <memory>
Q_LOGGING_CATEGORY(scriptengine_v8, "sh005.inverse-test")
struct ScriptEngineV8;
struct V8ScriptValue {
    v8::Isolate* isolate;
    std::shared_ptr<v8::Global<v8::Value>> value;
    V8ScriptValue(ScriptEngineV8*, v8::Local<v8::Value> = {});
    v8::Local<v8::Value> get() const { return value->Get(isolate); }
};
struct ScriptValue { std::shared_ptr<V8ScriptValue> value; };
Q_DECLARE_METATYPE(ScriptValue)
struct CustomValue { int number; };
Q_DECLARE_METATYPE(CustomValue)
struct PrototypeValue { int number; };
Q_DECLARE_METATYPE(PrototypeValue)
struct ScriptEngine { using MarshalFunction = ScriptValue (*)(ScriptEngineV8*, const void*); };
struct ScriptEngineV8 {
    v8::Isolate* _v8Isolate;
    v8::Local<v8::Context> context;
    struct CustomMarshal { ScriptEngine::MarshalFunction marshalFunc; };
    using CustomMarshalMap = QHash<int, CustomMarshal>;
    using CustomPrototypeMap = QHash<int, V8ScriptValue>;
    QReadWriteLock _customTypeProtect { QReadWriteLock::Recursive };
    CustomMarshalMap _customTypes;
    CustomPrototypeMap _customPrototypes;
    int marshals {0}, proxies {0}, unwraps {0};
    bool stopInMarshal {false};
#include "abort-state.inc"
    void abortEvaluation();
    v8::Local<v8::Context> getContext() { return context; }
    V8ScriptValue castVariantToValue(const QVariant&);
    void logBacktrace(const char*) { assert(false && "unexpected fallback"); }
};
V8ScriptValue::V8ScriptValue(ScriptEngineV8* e, v8::Local<v8::Value> v) : isolate(e->_v8Isolate),
    value(std::make_shared<v8::Global<v8::Value>>(isolate, v)) {}
#include "abort-method.inc"
struct ScriptValueV8Wrapper {
    static V8ScriptValue fullUnwrap(ScriptEngineV8* e, const ScriptValue& v) {
        ++e->unwraps;
        assert(v.value);
        return *v.value;
    }
};
struct ScriptObjectV8Proxy {
    static V8ScriptValue newQObject(ScriptEngineV8* e, QObject*) {
        ++e->proxies;
        return V8ScriptValue(e, v8::Object::New(e->_v8Isolate));
    }
};
struct ScriptVariantV8Proxy {
    static V8ScriptValue newVariant(ScriptEngineV8* e, const QVariant& v, V8ScriptValue proto) {
        ++e->proxies;
        // A real non-upgradable Qt read lock must have been released before
        // the external proxy boundary. This would otherwise deadlock updates.
        assert(e->_customTypeProtect.tryLockForWrite(20));
        e->_customPrototypes.remove(v.userType());
        e->_customTypeProtect.unlock();
        assert(proto.get()->IsObject()); // Snapshot remains alive after removal.
        return proto;
    }
};
// Full production method; only wrapper/proxy storage and native proxy creation
// are seams. Registry lookup, lock lifetime, QVariant selection and V8 values
// execute unchanged with real Qt/V8.
#include "inverse.inc"
static ScriptValue marshal(ScriptEngineV8* e, const void* data) {
    ++e->marshals;
    assert(e->_customTypeProtect.tryLockForWrite(20));
    e->_customTypeProtect.unlock();
    auto number = static_cast<const CustomValue*>(data)->number;
    auto result = ScriptValue{std::make_shared<V8ScriptValue>(e, v8::Integer::New(e->_v8Isolate, number))};
    if (e->stopInMarshal) { e->abortEvaluation(); e->_v8Isolate->CancelTerminateExecution(); }
    return result;
}
int main(int argc, char** argv) {
    assert(argc == 2);
    const std::string mode(argv[1]);
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
        ScriptEngineV8 engine { isolate, context };
        engine._customTypes.insert(qMetaTypeId<CustomValue>(), {marshal});
        engine._customPrototypes.insert(qMetaTypeId<PrototypeValue>(), V8ScriptValue(&engine, v8::Object::New(isolate)));
        if (mode == "ordinary") {
            assert(engine.castVariantToValue(42).get()->Int32Value(context).FromJust() == 42);
            assert(engine.castVariantToValue(true).get()->IsTrue());
            assert(engine.castVariantToValue(QVariant()).get()->IsUndefined());
            assert(engine.castVariantToValue(QVariant::fromValue(nullptr)).get()->IsNull());
            auto text = engine.castVariantToValue(QStringLiteral("hello"));
            assert(text.get()->IsString() && text.get().As<v8::String>()->Length() == 5);
        } else {
            const bool prototype = mode == "prototype" || mode == "stopped-prototype";
            const bool stopped = mode == "stopped-custom" || mode == "stopped-prototype";
            engine.stopInMarshal = mode == "reentrant-stop";
            if (stopped) { engine.abortEvaluation(); isolate->CancelTerminateExecution(); }
            const QVariant input = prototype ? QVariant::fromValue(PrototypeValue{42}) : QVariant::fromValue(CustomValue{42});
            auto result = engine.castVariantToValue(input);
            if (stopped || engine.stopInMarshal) { assert(result.get()->IsUndefined()); }
            else if (prototype) { assert(result.get()->IsObject()); }
            else { assert(result.get()->Int32Value(context).FromJust() == 42); }
            assert(engine.marshals == (!prototype && !stopped ? 1 : 0));
            assert(engine.proxies == (prototype && !stopped ? 1 : 0));
            assert(engine.unwraps == (mode == "custom" ? 1 : 0));
        }
        assert(engine._customTypeProtect.tryLockForWrite(20));
        engine._customTypeProtect.unlock();
    }
    isolate->Dispose();
    v8::V8::Dispose();
    v8::V8::DisposePlatform();
}
