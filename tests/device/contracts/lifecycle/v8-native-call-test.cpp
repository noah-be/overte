// SPDX-License-Identifier: Apache-2.0
#include <QVariant>
#include <QPointer>
#include <QMetaMethod>
#include <QLoggingCategory>
#include <v8.h>
#include <libplatform/libplatform.h>
#include <atomic>
#include <cassert>
#include <memory>
#include "v8-native-call-meta.h"
#include "meta.inc"
Q_LOGGING_CATEGORY(scriptengine_v8,"sh005.native-call-test")
int nativeCalls=0;
std::function<void()> duringNative;
struct ScriptEngineV8;
struct V8ScriptValue {
 v8::Isolate* isolate;
 v8::Local<v8::Value> value;
 V8ScriptValue(ScriptEngineV8*,v8::Local<v8::Value>);
 v8::Local<v8::Value> get(){return value;}
};
struct ScriptValueV8Wrapper {
 V8ScriptValue value;
 ScriptValueV8Wrapper(ScriptEngineV8*,V8ScriptValue v):value(v){}
 static V8ScriptValue fullUnwrap(ScriptEngineV8*,const ScriptValue& v){assert(v.value);return v.value->value;}
};
ScriptValue::ScriptValue(ScriptValueV8Wrapper* p):value(p){}
struct Context {
 Context* parentContext(){return this;}
 QStringList backtrace(){return {};}
};
struct ScriptEngineV8 {
 v8::Isolate* _v8Isolate;
 v8::Local<v8::Context> context;
 Context current;
 int conversions{0},inverse{0};
 std::function<void()> duringConversion;
#include "abort-state.inc"
 void abortEvaluation();
 v8::Isolate* getIsolate(){return _v8Isolate;}
 v8::Local<v8::Context> getContext(){return context;}
 Context* currentContext(){return &current;}
 void logBacktrace(const char*){}
 bool castValueToVariant(V8ScriptValue v,QVariant& out,int){++conversions;out=v.get()->Int32Value(context).FromJust();if(duringConversion)duringConversion();return true;}
 int computeCastPenalty(V8ScriptValue,int){return 0;}
 QString valueType(V8ScriptValue){return "number";}
 V8ScriptValue castVariantToValue(QVariant v){++inverse;return V8ScriptValue(this,v8::Integer::New(_v8Isolate,v.toInt()));}
};
V8ScriptValue::V8ScriptValue(ScriptEngineV8* e,v8::Local<v8::Value> v):isolate(e->_v8Isolate),value(v){}
#include "abort-method.inc"
struct ContextScopeV8 { explicit ContextScopeV8(ScriptEngineV8*){} };
struct ScriptContextV8Wrapper { ScriptContextV8Wrapper(ScriptEngineV8*,const v8::FunctionCallbackInfo<v8::Value>*,v8::Local<v8::Context>,Context*){} };
struct ScriptContextGuard { explicit ScriptContextGuard(ScriptContextV8Wrapper*){} };
struct ScriptMethodV8Proxy {
 ScriptEngineV8* _engine;
 QPointer<QObject> _object;
 int _numMaxParams{1};
 QList<QMetaMethod> _metas;
 QString fullName(){return "Target.method";}
 void call(const v8::FunctionCallbackInfo<v8::Value>&);
};
// Production selection, lifetime guard, conversion flow and QMetaMethod.invoke
// are unchanged. Context stack and conversion implementations are explicit seams.
#include "call.inc"
int main(int argc,char**argv){
 assert(argc==2);std::string mode(argv[1]);
 v8::V8::InitializeICUDefaultLocation(argv[0]);auto platform=v8::platform::NewDefaultPlatform();v8::V8::InitializePlatform(platform.get());assert(v8::V8::Initialize());
 auto allocator=std::unique_ptr<v8::ArrayBuffer::Allocator>(v8::ArrayBuffer::Allocator::NewDefaultAllocator());v8::Isolate::CreateParams params;params.array_buffer_allocator=allocator.get();auto isolate=v8::Isolate::New(params);
 {
 v8::Isolate::Scope scope(isolate);v8::HandleScope handles(isolate);auto context=v8::Context::New(isolate);v8::Context::Scope cs(context);
 ScriptEngineV8 engine{isolate,context};auto target=std::make_unique<Target>();
 qRegisterMetaType<ScriptValue>();
 const char* sig=mode=="void"?"empty(int)":mode=="scriptvalue"?"wrapped(ScriptValue)":"number(int,int)";
 auto method=target->metaObject()->method(target->metaObject()->indexOfMethod(sig));assert(method.isValid());
 ScriptMethodV8Proxy proxy{&engine,target.get(),method.parameterCount(),{method}};
 if(mode=="conversion-stop")engine.duringConversion=[&]{engine.abortEvaluation();isolate->CancelTerminateExecution();};
 if(mode=="conversion-delete")engine.duringConversion=[&]{target.reset();};
 if(mode=="native-stop")duringNative=[&]{engine.abortEvaluation();isolate->CancelTerminateExecution();};
 if(mode=="stopped"){engine.abortEvaluation();isolate->CancelTerminateExecution();}
 auto callback=v8::Function::New(context,[](const v8::FunctionCallbackInfo<v8::Value>& args){static_cast<ScriptMethodV8Proxy*>(args.Data().As<v8::External>()->Value())->call(args);},v8::External::New(isolate,&proxy)).ToLocalChecked();
 v8::Local<v8::Value> args[]={v8::Integer::New(isolate,42),v8::Integer::New(isolate,1)};v8::TryCatch caught(isolate);auto result=callback->Call(context,context->Global(),method.parameterCount(),args);
 bool rejected=mode=="stopped"||mode=="conversion-stop"||mode=="conversion-delete";
 assert(nativeCalls==(rejected?0:1));assert(engine.conversions==(mode=="stopped"||mode=="scriptvalue"?0:mode=="normal"||mode=="native-stop"?2:1));
 assert(caught.HasCaught()==(mode=="conversion-delete"));
 if(mode=="normal")assert(result.ToLocalChecked()->Int32Value(context).FromJust()==43);
 if(mode=="scriptvalue")assert(result.ToLocalChecked()->Int32Value(context).FromJust()==42);
 assert(engine.inverse==(mode=="normal"?1:0));
 if(mode=="native-stop"||mode=="conversion-stop"||mode=="stopped")assert(result.ToLocalChecked()->IsUndefined());
 }
 duringNative={};isolate->Dispose();v8::V8::Dispose();v8::V8::DisposePlatform();
}
