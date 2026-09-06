// SPDX-License-Identifier: Apache-2.0
#include <QString>
#include <v8.h>
#include <libplatform/libplatform.h>
#include <atomic>
#include <cassert>
#include <limits>
#include <memory>
#include <thread>
struct ScriptEngineV8 {
    v8::Isolate* isolate;
    v8::Local<v8::Context> context;
    v8::Isolate* _v8Isolate = isolate;
    void abortEvaluation();
#include "abort-state.inc"
    v8::Isolate* getIsolate() { return isolate; }
    v8::Local<v8::Context> getContext() { return context; }
};
#include "abort-method.inc"
struct V8ScriptValue {
    ScriptEngineV8* engine;
    std::shared_ptr<v8::Global<v8::Value>> value;
    V8ScriptValue(ScriptEngineV8* owner, v8::Local<v8::Value> local) : engine(owner),
        value(std::make_shared<v8::Global<v8::Value>>(owner->isolate,local)) {}
    v8::Local<v8::Value> constGet() const { return value->Get(engine->isolate); }
};
// Complete original iterator class and all six methods, not a policy model.
#include "v8-iterator-class.inc"
#include "v8-iterator-methods.inc"
static std::atomic<bool> entered { false };
static void markEntered(const v8::FunctionCallbackInfo<v8::Value>&) {
    entered.store(true,std::memory_order_release);
}
int main(int argc,char** argv) {
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
        v8::Isolate::Scope scope(isolate);
        v8::HandleScope handles(isolate);
        auto context = v8::Context::New(isolate);
        v8::Context::Scope contextScope(context);
        ScriptEngineV8 engine { isolate,context };
        assert(context->Global()->Set(context,v8::String::NewFromUtf8Literal(isolate,"entered"),
            v8::Function::New(context,markEntered).ToLocalChecked()).FromJust());
        const char* source = "({first:42,second:7})";
        if(mode == "empty") { source = "({})"; }
        if(mode == "null") { source = "null"; }
        if(mode == "keys-throw") { source = "new Proxy({}, {ownKeys(){throw 1;}})"; }
        if(mode == "keys-terminate") { source = "new Proxy({}, {ownKeys(){entered();for(;;){}}})"; }
        if(mode == "getter-throw") { source = "({get first(){throw 1;}})"; }
        if(mode == "getter-terminate") { source = "({get first(){entered();for(;;){}}})"; }
        if(mode == "stopped") { source = "new Proxy({}, {ownKeys(){entered();return ['first'];}})"; }
        if(mode == "stopped-existing") { source = "({get first(){entered();return 42;}})"; }
        auto object = v8::Script::Compile(context,v8::String::NewFromUtf8(isolate,source).ToLocalChecked())
            .ToLocalChecked()->Run(context).ToLocalChecked();
        v8::TryCatch caught(isolate);
        std::thread terminator;
        if(mode.find("terminate") != std::string::npos) {
            terminator = std::thread([isolate] {
                while(!entered.load(std::memory_order_acquire)) { std::this_thread::yield(); }
                isolate->TerminateExecution();
            });
        }
        {
            if(mode == "stopped") { engine.abortEvaluation(); isolate->CancelTerminateExecution(); }
            V8ScriptValueIterator iterator(&engine,object);
            assert(iterator.name().isEmpty());
            assert(iterator.value().constGet()->IsUndefined());
            if(mode == "stopped-existing") {
                assert(iterator.hasNext()); iterator.next();
                engine.abortEvaluation(); isolate->CancelTerminateExecution();
                assert(!iterator.hasNext() && iterator.name().isEmpty());
                assert(iterator.value().constGet()->IsUndefined());
                iterator.next();
                assert(!entered.load());
            } else if(mode == "ordinary") {
                assert(iterator.hasNext()); iterator.next();
                assert(iterator.name() == "first" && iterator.value().constGet()->Int32Value(context).FromJust() == 42);
                assert(iterator.hasNext()); iterator.next();
                assert(iterator.name() == "second" && iterator.value().constGet()->Int32Value(context).FromJust() == 7);
                assert(!iterator.hasNext());
            } else if(mode.rfind("getter-",0) == 0) {
                assert(iterator.hasNext()); iterator.next();
                assert(iterator.value().constGet()->IsUndefined());
            } else {
                assert(!iterator.hasNext());
            }
        }
        if(terminator.joinable()) { terminator.join(); }
        if(mode.rfind("stopped",0) == 0) { assert(!entered.load() && engine.isEvaluationAborted()); }
        const bool failure = mode.find("throw") != std::string::npos || mode.find("terminate") != std::string::npos;
        assert(caught.HasCaught() == failure);
        assert(caught.HasTerminated() == (mode.find("terminate") != std::string::npos));
    }
    isolate->Dispose();
    v8::V8::Dispose();
    v8::V8::DisposePlatform();
}
