// SPDX-License-Identifier: Apache-2.0
#include <QString>
#include <v8.h>
#include <libplatform/libplatform.h>
#include <cassert>
#include <cstring>
#include <memory>
#include <vector>
struct ScriptEngineV8;
struct V8ScriptValue {
    std::shared_ptr<v8::Global<v8::Value>> value;
    V8ScriptValue(ScriptEngineV8*,v8::Local<v8::Value>);
};
struct ScriptValueV8Wrapper {
    V8ScriptValue value;
    ScriptValueV8Wrapper(ScriptEngineV8*,V8ScriptValue v):value(std::move(v)) {}
};
struct ScriptValue {
    std::shared_ptr<ScriptValueV8Wrapper> wrapper;
    ScriptValue() = default;
    explicit ScriptValue(ScriptValueV8Wrapper* p):wrapper(p) {}
};
struct ScriptEngineV8 {
    v8::Isolate* _v8Isolate;
    v8::Local<v8::Context> context;
    v8::Local<v8::Context> getContext() { return context; }
    ScriptValue newValue(const QString&);
    ScriptValue newValue(const QLatin1String&);
    ScriptValue newValue(const char*);
};
V8ScriptValue::V8ScriptValue(ScriptEngineV8* engine,v8::Local<v8::Value> local)
    :value(std::make_shared<v8::Global<v8::Value>>(engine->_v8Isolate,local)) {}
// Only engine/context/value ownership storage is a boundary; methods unchanged.
#include "string-factory.inc"
static void equal(v8::Isolate* isolate,const ScriptValue& value,const QString& expected) {
    assert(value.wrapper);
    auto local=value.wrapper->value.value->Get(isolate);
    assert(local->IsString());
    auto string=local.As<v8::String>();
    assert(string->Length()==expected.size());
    std::vector<uint16_t> bytes(expected.size()+1);
    assert(string->Write(isolate,bytes.data(),0,expected.size(),v8::String::NO_NULL_TERMINATION)==expected.size());
    for(int i=0;i<expected.size();++i) assert(bytes[i]==expected[i].unicode());
}
int main(int argc,char** argv) {
    v8::V8::InitializeICUDefaultLocation(argv[0]);
    auto platform=v8::platform::NewDefaultPlatform();
    v8::V8::InitializePlatform(platform.get()); assert(v8::V8::Initialize());
    auto allocator=std::unique_ptr<v8::ArrayBuffer::Allocator>(v8::ArrayBuffer::Allocator::NewDefaultAllocator());
    v8::Isolate::CreateParams parameters; parameters.array_buffer_allocator=allocator.get();
    auto isolate=v8::Isolate::New(parameters);
    {
        v8::Isolate::Scope scope(isolate); v8::HandleScope handles(isolate);
        auto context=v8::Context::New(isolate); v8::Context::Scope contextScope(context);
        ScriptEngineV8 engine {isolate,context};
        const QString nul=QString::fromLatin1("a\0b",3);
        equal(isolate,engine.newValue(nul),nul); // Historical truncation RED first.
        equal(isolate,engine.newValue(QString()),QString());
        equal(isolate,engine.newValue(QStringLiteral("plain")),QStringLiteral("plain"));
        const QString unicode=QString::fromUtf8("\xc3\xa4\xf0\x9f\x98\x80");
        equal(isolate,engine.newValue(unicode),unicode);
        const QString surrogate(QChar(0xd800));
        equal(isolate,engine.newValue(surrogate),surrogate);
        equal(isolate,engine.newValue(QLatin1String("a\0b",3)),nul);
        equal(isolate,engine.newValue(QLatin1String("\xe4",1)),QString(QChar(0xe4)));
        const char bounded[] {'x','y','z'};
        equal(isolate,engine.newValue(QLatin1String(bounded,2)),QStringLiteral("xy"));
        equal(isolate,engine.newValue(QLatin1String()),QString());
        equal(isolate,engine.newValue(""),QString());
        equal(isolate,engine.newValue("a\0b"),QStringLiteral("a")); // C-string contract.
        equal(isolate,engine.newValue("\xc3\xa4"),QString(QChar(0xe4)));
        equal(isolate,engine.newValue("\xff"),QString(QChar(0xfffd))); // V8 UTF8 replacement.
        assert(!engine.newValue(static_cast<const char*>(nullptr)).wrapper);
    }
    isolate->Dispose(); v8::V8::Dispose(); v8::V8::DisposePlatform();
}
