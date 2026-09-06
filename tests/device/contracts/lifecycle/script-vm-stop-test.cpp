// SPDX-License-Identifier: Apache-2.0
#include <QCoreApplication>
#include <QThread>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <memory>
#include <mutex>
#include <thread>
#include <v8.h>
#include <libplatform/libplatform.h>
#include "libraries/networking/src/RequestCancellation.h"

// Engine construction/destruction is an explicit ownership seam. The actual
// abort body below operates on a real isolate held alive through the test.
struct ScriptEngineV8 {
    v8::Isolate* _v8Isolate;
    void abortEvaluation();
};
struct ScriptManager : QObject, std::enable_shared_from_this<ScriptManager> {
    std::shared_ptr<ScriptEngineV8> _engine;
    std::atomic<bool> _isStopping { false };
    bool _isFinished { false };
    overte::network::RequestScope _scriptLoadContext;
    int delivered { 0 };
    void runningStateChanged() { ++delivered; }
    void stop(bool marshal);
};
#include "methods.inc"

struct EntrySignal {
    std::mutex mutex;
    std::condition_variable changed;
    bool entered { false };
    bool exited { false };
};

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    const bool stopping = std::string(argv[1]) != "normal";
    const bool duplicate = std::string(argv[1]) == "duplicate";
    auto platform = v8::platform::NewDefaultPlatform();
    v8::V8::InitializePlatform(platform.get());
    v8::V8::Initialize();
    auto allocator = std::unique_ptr<v8::ArrayBuffer::Allocator>(
        v8::ArrayBuffer::Allocator::NewDefaultAllocator());
    v8::Isolate::CreateParams params;
    params.array_buffer_allocator = allocator.get();
    auto isolate = v8::Isolate::New(params);
    auto manager = std::make_shared<ScriptManager>();
    manager->_engine = std::make_shared<ScriptEngineV8>(ScriptEngineV8 { isolate });
    EntrySignal signal;
    QThread heldTarget;
    // No target event loop starts until after JS returns. stop(true) therefore
    // cannot rely on the queued stop(false) call to break the running VM.
    manager->moveToThread(&heldTarget);
    std::thread worker([&] {
        v8::Locker lock(isolate);
        v8::Isolate::Scope scope(isolate);
        v8::HandleScope handles(isolate);
        auto context = v8::Context::New(isolate);
        v8::Context::Scope enteredContext(context);
        auto announce = v8::Function::New(context, [](const v8::FunctionCallbackInfo<v8::Value>& info) {
            auto* signal = static_cast<EntrySignal*>(info.Data().As<v8::External>()->Value());
            { std::lock_guard<std::mutex> guard(signal->mutex); signal->entered = true; }
            signal->changed.notify_all();
        }, v8::External::New(isolate, &signal)).ToLocalChecked();
        assert(context->Global()->Set(context, v8::String::NewFromUtf8Literal(isolate, "announce"), announce).FromJust());
        auto source = v8::String::NewFromUtf8Literal(isolate, "announce(); while (true) {};");
        if (!stopping) source = v8::String::NewFromUtf8Literal(isolate, "announce(); 1 + 2");
        auto script = v8::Script::Compile(context, source).ToLocalChecked();
        v8::TryCatch caught(isolate);
        v8::Local<v8::Value> result;
        bool ok = script->Run(context).ToLocal(&result);
        assert(ok == !stopping);
        if (stopping) assert(caught.HasTerminated());
        else assert(result->Int32Value(context).FromJust() == 3);
        { std::lock_guard<std::mutex> guard(signal.mutex); signal.exited = true; }
        signal.changed.notify_all();
    });
    {
        std::unique_lock<std::mutex> guard(signal.mutex);
        assert(signal.changed.wait_for(guard, std::chrono::seconds(1), [&] { return signal.entered; }));
    }
    if (stopping) {
        manager->stop(true);
        if (duplicate) manager->stop(true);
        assert(manager->_isStopping && !manager->_isFinished && manager->delivered == 0);
    }
    {
        std::unique_lock<std::mutex> guard(signal.mutex);
        // Failure exits by assertion instead of hanging a test worker forever.
        assert(signal.changed.wait_for(guard, std::chrono::seconds(1), [&] { return signal.exited; }));
    }
    worker.join();
    // Deliver original queued manager work and then return ownership to main.
    QMetaObject::invokeMethod(manager.get(), [&] {
        manager->moveToThread(app.thread());
        heldTarget.quit();
    }, Qt::QueuedConnection);
    heldTarget.start();
    assert(heldTarget.wait(1000));
    if (stopping) assert(manager->_isFinished && manager->delivered == 1);
    manager.reset();
    isolate->Dispose();
    v8::V8::Dispose();
    v8::V8::DisposePlatform();
}
