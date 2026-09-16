// SPDX-License-Identifier: Apache-2.0
#include "libraries/script-engine/src/v8/V8PropertyCopy.h"
#include "libraries/script-engine/src/v8/V8ExceptionDiagnostics.h"
#include <libplatform/libplatform.h>
#include <atomic>
#include <cassert>
#include <memory>
#include <thread>

struct ScriptEngineV8 {
    v8::Isolate* _v8Isolate;
    v8::Local<v8::Context> context;
    bool areGlobalObjectContentsStored { false };
    v8::Global<v8::Object> _globalObjectContents;
    bool error { false };
    v8::Local<v8::Context> getContext() { return context; }
    void setUncaughtException(const v8::TryCatch&, const QString&) { error = true; }
    void setUncaughtEngineException(const QString&) { error = true; }
    bool storeGlobalObjectContents();
};
// Complete original snapshot caller, with only error notification substituted.
#include "v8-global-snapshot.inc"

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
    auto allocator = std::unique_ptr<v8::ArrayBuffer::Allocator>(v8::ArrayBuffer::Allocator::NewDefaultAllocator());
    v8::Isolate::CreateParams parameters;
    parameters.array_buffer_allocator = allocator.get();
    auto isolate = v8::Isolate::New(parameters);
    {
        v8::Isolate::Scope scope(isolate);
        v8::HandleScope handles(isolate);
        auto context = v8::Context::New(isolate);
        v8::Context::Scope contextScope(context);
        assert(context->Global()->Set(context, v8::String::NewFromUtf8Literal(isolate, "entered"),
            v8::Function::New(context, markEntered).ToLocalChecked()).FromJust());
        auto evaluate = [&](const char* text) {
            return v8::Script::Compile(context, v8::String::NewFromUtf8(isolate, text).ToLocalChecked())
                .ToLocalChecked()->Run(context).ToLocalChecked();
        };
        if (mode.rfind("require-", 0) == 0) {
            const char* sourceText = "({Script:{require:Object.assign(function(){},{cache:41})}})";
            const char* destinationText = "({Script:{require:function(){}}})";
            if (mode == "require-source-script") { sourceText = "({Script:1})"; }
            if (mode == "require-source-require") { sourceText = "({Script:{require:null}})"; }
            if (mode == "require-destination-script") { destinationText = "({})"; }
            if (mode == "require-destination-require") { destinationText = "({Script:{require:4}})"; }
            if (mode == "require-getter") { sourceText = "({get Script(){throw 1;}})"; }
            if (mode == "require-cache-getter") { sourceText = "({Script:{require:{get cache(){throw 1;}}}})"; }
            if (mode == "require-terminate") { sourceText = "({Script:{require:{get cache(){entered();for(;;){}}}}})"; }
            auto source = evaluate(sourceText).As<v8::Object>();
            auto destination = evaluate(destinationText).As<v8::Object>();
            v8::TryCatch caught(isolate);
            std::thread terminator;
            if (mode == "require-terminate") {
                terminator = std::thread([isolate] {
                    while (!entered.load(std::memory_order_acquire)) { std::this_thread::yield(); }
                    isolate->TerminateExecution();
                });
            }
            const bool copied = overte::scripting::copyRequireProperties(context, source, destination);
            if (terminator.joinable()) { terminator.join(); }
            assert(copied == (mode == "require-ordinary"));
            if (copied) {
                auto script = destination->Get(context, v8::String::NewFromUtf8Literal(isolate,"Script"))
                    .ToLocalChecked().As<v8::Object>();
                auto require = script->Get(context, v8::String::NewFromUtf8Literal(isolate,"require"))
                    .ToLocalChecked().As<v8::Object>();
                assert(require->IsFunction());
                auto cache = require->Get(context, v8::String::NewFromUtf8Literal(isolate,"cache")).ToLocalChecked();
                assert(cache->Int32Value(context).FromJust() == 41);
            }
            const bool expectedException = mode == "require-getter" ||
                mode == "require-cache-getter" || mode == "require-terminate";
            assert(caught.HasCaught() == expectedException);
            assert(caught.HasTerminated() == (mode == "require-terminate"));
        } else if (mode == "snapshot" || mode == "snapshot-error") {
            ScriptEngineV8 engine { isolate, context };
            if (mode == "snapshot-error") {
                evaluate("Object.defineProperty(globalThis,'bad',{enumerable:true,configurable:true,get(){throw 1;}})");
                assert(!engine.storeGlobalObjectContents());
                assert(engine.error && !engine.areGlobalObjectContentsStored && engine._globalObjectContents.IsEmpty());
                evaluate("delete globalThis.bad");
            }
            evaluate("globalThis.original=42");
            assert(engine.storeGlobalObjectContents());
            assert(engine.areGlobalObjectContentsStored && !engine._globalObjectContents.IsEmpty());
            evaluate("globalThis.original=99");
            assert(engine.storeGlobalObjectContents());
            auto saved = engine._globalObjectContents.Get(isolate)->Get(context,
                v8::String::NewFromUtf8Literal(isolate, "original")).ToLocalChecked();
            assert(saved->Int32Value(context).FromJust() == 42);
        } else {
            const char* text = "Object.assign(Object.create({inherited:7}),{own:3})";
            if (mode == "getter") { text = "({get own(){throw 1;}})"; }
            if (mode == "keys") { text = "new Proxy({}, {ownKeys(){throw 1;}})"; }
            if (mode == "terminate") { text = "({get own(){entered();for(;;){}}})"; }
            auto source = evaluate(text).As<v8::Object>();
            auto destination = v8::Object::New(isolate);
            if (mode == "setter") {
                destination = evaluate("({set own(v){throw 1;}})").As<v8::Object>();
            }
            v8::TryCatch caught(isolate);
            std::thread terminator;
            if (mode == "terminate") {
                terminator = std::thread([isolate] {
                    while (!entered.load(std::memory_order_acquire)) { std::this_thread::yield(); }
                    isolate->TerminateExecution();
                });
            }
            const bool copied = overte::scripting::copyEnumerableProperties(context, context, source, destination);
            if (terminator.joinable()) { terminator.join(); }
            if (mode == "ordinary") {
                assert(copied && !caught.HasCaught());
                for (const auto& pair : { std::make_pair("own",3), std::make_pair("inherited",7) }) {
                    auto value = destination->Get(context,
                        v8::String::NewFromUtf8(isolate,pair.first).ToLocalChecked()).ToLocalChecked();
                    assert(value->Int32Value(context).FromJust() == pair.second);
                }
                assert(!overte::scripting::copyEnumerableProperties({},context,source,destination));
                assert(!overte::scripting::copyEnumerableProperties(context,context,{},destination));
            } else {
                assert(!copied && caught.HasCaught());
                assert((mode == "terminate") == caught.HasTerminated());
            }
        }
    }
    isolate->Dispose();
    v8::V8::Dispose();
    v8::V8::DisposePlatform();
}
