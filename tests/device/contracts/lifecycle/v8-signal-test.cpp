// SPDX-License-Identifier: Apache-2.0
#include <QMetaEnum>
#include <QVariant>
#include <QList>
#include <QLoggingCategory>
#include <v8.h>
#include <libplatform/libplatform.h>
#include <atomic>
#include <cassert>
#include <functional>
#include <memory>
#include <thread>
#include "ReadWriteLockable.h"
#include "signal-meta.h"
#include "signal-moc.inc"
Q_LOGGING_CATEGORY(scriptengine_v8, "sh005.signal-test")
struct V8ScriptValue {
    v8::Isolate* isolate;
    std::shared_ptr<v8::Global<v8::Value>> value;
    V8ScriptValue(v8::Isolate* i, v8::Local<v8::Value> v) : isolate(i), value(std::make_shared<v8::Global<v8::Value>>(i, v)) {}
    v8::Local<v8::Value> get() const { return value->Get(isolate); }
};
struct ManagerBoundary {
    int notifications { 0 };
    void scriptErrorMessage(const QString&, const QString&, int) { ++notifications; }
};
struct ScriptEngineV8 {
    v8::Isolate* isolate;
    v8::Local<v8::Context> context;
    ManagerBoundary* _manager;
    bool emptyConversion { false }, stopConversion { false };
    int conversions { 0 }, uncaught { 0 }, pops { 0 };
    v8::Isolate* _v8Isolate = isolate;
    void abortEvaluation();
#include "abort-state.inc"
    v8::Isolate* getIsolate() { return isolate; }
    v8::Local<v8::Context> getContext() { return context; }
    V8ScriptValue castVariantToValue(const QVariant& value) {
        ++conversions;
        if (stopConversion) { abortEvaluation(); isolate->CancelTerminateExecution(); }
        return V8ScriptValue(isolate, emptyConversion ? v8::Local<v8::Value>() : v8::Local<v8::Value>(v8::Integer::New(isolate, value.toInt())));
    }
    QString formatErrorMessageFromTryCatch(const v8::TryCatch&) { return QStringLiteral("captured diagnostic boundary"); }
    void setUncaughtException(const v8::TryCatch&, const char*) { ++uncaught; }
    void popContext() { ++pops; }
};
#include "abort-method.inc"
QString getFileNameFromTryCatch(const v8::TryCatch&, v8::Isolate*, v8::Local<v8::Context>) { return {}; }
class ScriptSignalV8Proxy final : public ScriptSignalV8ProxyBase, public ReadWriteLockable {
public:
    struct Connection { V8ScriptValue thisValue, callback; std::function<void(std::function<void()>)> invokeInEnvironment; };
    using ConnectionList = QList<Connection>;
    ScriptEngineV8* _engine;
    QMetaMethod _meta;
    ConnectionList _connections;
    ScriptSignalV8Proxy(ScriptEngineV8* e, QMetaMethod m) : _engine(e), _meta(m) {}
    void connect(ScriptValue, ScriptValue) override {}
    void disconnect(ScriptValue, ScriptValue) override {}
    QString fullName() const { return QStringLiteral("fixture signal"); }
    int qt_metacall(QMetaObject::Call, int, void**) override;
};
// Real base meta-object dispatch and locking; engine conversion, ownership and
// diagnostics are explicit boundaries. Entire production callback body follows.
#include "signal-body.inc"
static std::atomic<bool> entered { false };
static int first = 0, second = 0, observedArguments = -1;
static void record(const v8::FunctionCallbackInfo<v8::Value>& info) {
    ++first;
    observedArguments = info.Length();
    for (int i = 0; i < info.Length(); ++i) { assert(info[i]->Int32Value(info.GetIsolate()->GetCurrentContext()).FromJust() == i + 1); }
}
static void next(const v8::FunctionCallbackInfo<v8::Value>&) { ++second; }
static void markEntered(const v8::FunctionCallbackInfo<v8::Value>&) { entered.store(true, std::memory_order_release); }
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
        ManagerBoundary manager;
        ScriptEngineV8 engine { isolate, context, &manager };
        Emitter emitter;
        const char* signature = mode == "zero" ? "zero()" : (mode == "ten" || mode == "conversion-stop") ? "ten(int,int,int,int,int,int,int,int,int,int)" :
            mode == "over" ? "huge(int,int,int,int,int,int,int,int,int,int,int)" : "ping(int)";
        auto meta = emitter.metaObject()->method(emitter.metaObject()->indexOfSignal(signature));
        assert(meta.isValid());
        ScriptSignalV8Proxy proxy(&engine, meta);
        auto callback = v8::Local<v8::Value>(v8::Function::New(context, record).ToLocalChecked());
        if (mode == "empty-callback") { callback = {}; }
        if (mode == "null-callback") { callback = v8::Null(isolate); }
        if (mode == "undefined-callback") { callback = v8::Undefined(isolate); }
        if (mode == "object-callback") { callback = v8::Object::New(isolate); }
        if (mode == "throw" || mode == "terminate") {
            assert(context->Global()->Set(context, v8::String::NewFromUtf8Literal(isolate, "entered"),
                v8::Function::New(context, markEntered).ToLocalChecked()).FromJust());
            callback = v8::Script::Compile(context, v8::String::NewFromUtf8(isolate,
                mode == "throw" ? "(function(){throw 17;})" : "(function(){entered();for(;;){}})").ToLocalChecked()).ToLocalChecked()->Run(context).ToLocalChecked();
        }
        proxy._connections.append({ V8ScriptValue(isolate, {}), V8ScriptValue(isolate, callback) });
        proxy._connections.append({ V8ScriptValue(isolate, {}), V8ScriptValue(isolate, v8::Function::New(context, next).ToLocalChecked()) });
        if (mode == "consent-denied") {
            proxy._connections[0].invokeInEnvironment = [](std::function<void()>) {};
        } else if (mode == "consent-allowed") {
            proxy._connections[0].invokeInEnvironment = [](std::function<void()> invoke) { invoke(); };
        }
        assert(QMetaObject::connect(&emitter, meta.methodIndex(), &proxy, proxy.metaObject()->methodCount()));
        engine.emptyConversion = mode == "empty-conversion";
        engine.stopConversion = mode == "conversion-stop";
        std::thread terminator;
        if (mode == "terminate") {
            terminator = std::thread([isolate] {
                while (!entered.load(std::memory_order_acquire)) { std::this_thread::yield(); }
                isolate->TerminateExecution();
            });
        }
        if (mode == "stopped") {
            engine.abortEvaluation();
            isolate->CancelTerminateExecution();
            assert(engine.isEvaluationAborted() && !isolate->IsExecutionTerminating());
        }
        if (mode == "zero") { emitter.zero(); }
        else if (mode == "ten" || mode == "conversion-stop") { emitter.ten(1,2,3,4,5,6,7,8,9,10); }
        else if (mode == "over") { emitter.huge(1,2,3,4,5,6,7,8,9,10,11); }
        else if (mode == "null-arguments" || mode == "null-argument") {
            void* arguments[] { nullptr, nullptr };
            assert(proxy.qt_metacall(QMetaObject::InvokeMetaMethod, proxy.metaObject()->methodCount(),
                mode == "null-arguments" ? nullptr : arguments) == -1);
        } else { emitter.ping(1); }
        if (terminator.joinable()) { terminator.join(); }
        assert(proxy.getLock().tryLockForWrite());
        proxy.getLock().unlock();
        assert(engine.pops == 0);
        const bool rejected = mode == "conversion-stop" || mode == "over" || mode == "empty-conversion" || mode == "null-arguments" || mode == "null-argument" || mode == "terminate" || mode == "stopped";
        assert(second == (rejected ? 0 : 1));
        assert(manager.notifications == (mode == "throw" ? 1 : 0));
        assert(engine.uncaught == (mode == "throw" ? 1 : 0));
        const bool normal = mode == "zero" || mode == "one" || mode == "ten" || mode == "consent-allowed";
        assert(first == (normal ? 1 : 0));
        if (normal) { assert(observedArguments == (mode == "zero" ? 0 : mode == "ten" ? 10 : 1)); }
        if (mode == "conversion-stop") { assert(engine.conversions == 1 && engine.isEvaluationAborted()); }
        if (mode == "over" || mode == "stopped") { assert(engine.conversions == 0); }
    }
    isolate->Dispose();
    v8::V8::Dispose();
    v8::V8::DisposePlatform();
}
