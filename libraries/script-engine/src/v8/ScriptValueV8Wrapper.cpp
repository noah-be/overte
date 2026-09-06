//
//  ScriptValueV8Wrapper.cpp
//  libraries/script-engine/src/v8
//
//  Created by Heather Anderson on 5/16/21.
//  Modified for V8 by dr Karol Suprynowicz on 2022/10/08
//  Copyright 2021 Vircadia contributors.
//  Copyright 2022-2023 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//  SPDX-License-Identifier: Apache-2.0
//

#include "ScriptValueV8Wrapper.h"
#include <QReadLocker>
#include <limits>

#include "ScriptValueIteratorV8Wrapper.h"

#include "../ScriptEngineLogging.h"
#include "ScriptEngineLoggingV8.h"


void ScriptValueV8Wrapper::enqueueRelease() {
    _engine->scheduleValueWrapperForDeletion(this);
}

void ScriptValueV8Wrapper::release() {
    // Check if ScriptValueV8Wrapper::release was called from inside ScriptValueV8Wrapper functions, and if so, delete it later
    // This prevents access-after-delete crashes when ScriptValueV8Wrapper::release is called from inside JS executed in
    // ScriptValueV8Wrapper::call, ScriptValueV8Wrapper::construct and others
    if (lock.tryLockForWrite()) {
        lock.unlock();
        delete this;
    } else {
        _engine->scheduleValueWrapperForDeletion(this);
    }
}

ScriptValueProxy* ScriptValueV8Wrapper::copy() const {
    //V8TODO: check if the value needs to be copied or just wrapper
    v8::Isolate *isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    v8::Context::Scope contextScope(_engine->getContext());
    // V8TODO: I'm not sure if this part is right:
    ScriptValueV8Wrapper *copiedWrapper = new ScriptValueV8Wrapper(_engine, _value);
    return copiedWrapper;
}

ScriptValueV8Wrapper* ScriptValueV8Wrapper::unwrap(const ScriptValue& val) {
    return dynamic_cast<ScriptValueV8Wrapper*>(val.ptr());
}

V8ScriptValue ScriptValueV8Wrapper::fullUnwrap(const ScriptValue& value) const {
    ScriptValueV8Wrapper* unwrapped = unwrap(value);
    if (unwrapped) {
        if (unwrapped->engine().get() != _engine) {
            return _engine->castVariantToValue(unwrapped->toVariant());
        } else {
            return unwrapped->toV8Value();
        }
    }
    QVariant varValue = value.toVariant();
    return _engine->castVariantToValue(varValue);
}

V8ScriptValue ScriptValueV8Wrapper::fullUnwrap(ScriptEngineV8* engine, const ScriptValue& value) {
    ScriptValueV8Wrapper* unwrapped = unwrap(value);
    if (unwrapped) {
        if (unwrapped->engine().get() != engine) {
            return engine->castVariantToValue(unwrapped->toVariant());
        } else {
            return unwrapped->toV8Value();
        }
    }
    QVariant varValue = value.toVariant();
    return engine->castVariantToValue(varValue);
}

ScriptValue ScriptValueV8Wrapper::call(const ScriptValue& thisObject, const ScriptValueList& args) {
    Q_ASSERT(_engine == _value.getEngine());
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    auto context = _engine->getContext();
    v8::Context::Scope contextScope(context);
    const auto callable = _value.get();
    if (args.length() > Q_METAMETHOD_INVOKE_MAX_ARGS || callable.IsEmpty() || !callable->IsFunction()) {
        return _engine->undefinedValue();
    }
    V8ScriptValue v8This = fullUnwrap(thisObject);
    if (isolate->IsExecutionTerminating() || v8This.get().IsEmpty()) { return ScriptValue(); }
    v8::Local<v8::Value> v8Args[Q_METAMETHOD_INVOKE_MAX_ARGS];
    int argIndex = 0;
    for (ScriptValueList::const_iterator iter = args.begin(); iter != args.end(); ++iter) {
        const auto argument = fullUnwrap(*iter).get();
        if (isolate->IsExecutionTerminating() || argument.IsEmpty()) { return ScriptValue(); }
        v8Args[argIndex++] = argument;
    }
    v8::Local<v8::Function> v8Function = callable.As<v8::Function>();
    v8::TryCatch tryCatch(isolate);
    v8::Local<v8::Value> recv;
    if (v8This.get()->IsObject()) {
        recv = v8This.get();
    }else{
        recv = context->Global();
    }

    v8::MaybeLocal<v8::Value> maybeResult;
    {
        QReadLocker guard(&lock);
        maybeResult = v8Function->Call(context, recv, args.length(), v8Args);
    }
    if (tryCatch.HasTerminated() || isolate->IsExecutionTerminating()) {
        return ScriptValue();
    }
    if (tryCatch.HasCaught()) {
        QString errorMessage(QString("Function call failed: \"") + _engine->formatErrorMessageFromTryCatch(tryCatch));
        if (_engine->_manager) {
            v8::Local<v8::Message> exceptionMessage = tryCatch.Message();
            int errorLineNumber = -1;
            if (!exceptionMessage.IsEmpty()) {
                errorLineNumber = exceptionMessage->GetLineNumber(context).FromMaybe(-1);
            }
            _engine->_manager->scriptErrorMessage(errorMessage, getFileNameFromTryCatch(tryCatch, isolate, context),
                                                  errorLineNumber);
        } else {
            qDebug(scriptengine_v8) << errorMessage;
        }
    }
    v8::Local<v8::Value> result;
    Q_ASSERT(_engine == _value.getEngine());
    if (maybeResult.ToLocal(&result)) {
        return ScriptValue(new ScriptValueV8Wrapper(_engine, V8ScriptValue(_engine, result)));
    } else {
        auto currentContext = _engine->currentContext();
        QString errorMessage("JS function call failed: " + currentContext->backtrace().join("\n"));
        if (_engine->_manager) {
            _engine->_manager->scriptErrorMessage(errorMessage, currentContext->currentFileName(), currentContext->currentLineNumber());
        } else {
            qDebug(scriptengine_v8) << errorMessage;
        }
        return _engine->undefinedValue();
    }
}

ScriptValue ScriptValueV8Wrapper::call(const ScriptValue& thisObject, const ScriptValue& arguments) {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    v8::Context::Scope contextScope(_engine->getContext());
    V8ScriptValue v8This = fullUnwrap(thisObject);
    V8ScriptValue v8Args = fullUnwrap(arguments);
    // V8TODO should there be a v8 try-catch here?
    // IsFunction check should be here probably
    // V8TODO I'm not sure in what format arguments are yet, backtrace will show how it is used
    // V8TODO: this seems to never be used?
    Q_ASSERT(false);
    return _engine->undefinedValue();
    /*v8::Local<v8::Function> v8Function = v8::Local<v8::Function>::Cast(_value.get());
    auto maybeResult = v8Function->Call(_engine->getContext(), v8This, v8Args);
    v8::Local<v8::Value> result;
    if (maybeResult.ToLocal(&result)) {
        return ScriptValue(new ScriptValueV8Wrapper(_engine, V8ScriptValue(_engine->getContext(), result)));
    } else {
        //V8TODO Add more details
        qCWarning(scriptengine_v8) << "JS function call failed";
        return _engine->undefinedValue();
    }*/
}

ScriptValue ScriptValueV8Wrapper::construct(const ScriptValueList& args) {
    //V8TODO: there is CallAsContructor in V8
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    auto context = _engine->getContext();
    v8::Context::Scope contextScope(context);
    const auto callable = _value.get();
    if (args.length() > Q_METAMETHOD_INVOKE_MAX_ARGS || callable.IsEmpty() ||
            !callable->IsFunction() || !callable.As<v8::Function>()->IsConstructor()) {
        return _engine->undefinedValue();
    }
    v8::Local<v8::Value> v8Args[Q_METAMETHOD_INVOKE_MAX_ARGS];
    int argIndex = 0;
    for (ScriptValueList::const_iterator iter = args.begin(); iter != args.end(); ++iter) {
        const auto argument = fullUnwrap(*iter).get();
        if (isolate->IsExecutionTerminating() || argument.IsEmpty()) { return ScriptValue(); }
        v8Args[argIndex++] = argument;
    }
    v8::Local<v8::Function> v8Function = callable.As<v8::Function>();
    // V8TODO: I'm not sure if this is correct, maybe use CallAsConstructor instead?
    // Maybe it's CallAsConstructor for function and NewInstance for class?
    // Preserve the caller's TryCatch/exception semantics; no script coercion or
    // diagnostic callbacks while termination is unwinding.
    v8::MaybeLocal<v8::Object> maybeResult;
    {
        QReadLocker guard(&lock);
        maybeResult = v8Function->NewInstance(context, args.length(), v8Args);
    }
    if (isolate->IsExecutionTerminating()) { return ScriptValue(); }
    v8::Local<v8::Object> result;
    if (maybeResult.ToLocal(&result)) {
        return ScriptValue(new ScriptValueV8Wrapper(_engine, V8ScriptValue(_engine, result)));
    } else {
        //V8TODO Add more details
        qCWarning(scriptengine_v8) << "JS function call failed";
        return _engine->undefinedValue();
    }
}

// V8TODO: this seems to never be used?
ScriptValue ScriptValueV8Wrapper::construct(const ScriptValue& arguments) {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    v8::Context::Scope contextScope(_engine->getContext());
    // V8TODO I'm not sure in what format arguments are yet, backtrace will show how it is used
    Q_ASSERT(false);
    return _engine->undefinedValue();
    //V8ScriptValue unwrapped = fullUnwrap(arguments);
    //V8ScriptValue result = _value.construct(unwrapped);
    //return ScriptValue(new ScriptValueV8Wrapper(_engine, std::move(result)));
}

// V8TODO: check how data() is used and if it needs fixing
ScriptValue ScriptValueV8Wrapper::data() const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    auto context = _engine->getContext();
    v8::Context::Scope contextScope(context);
    // __data remains the existing ordinary property, not a private storage API.
    // A script may replace it with a throwing getter; never assert on that input.
    if (!_value.constGet()->IsObject()) {
        return _engine->nullValue();
    }
    auto object = _value.constGet().As<v8::Object>();
    v8::Local<v8::Value> data;
    if (!object->Get(context, v8::String::NewFromUtf8Literal(isolate, "__data")).ToLocal(&data)) {
        if (isolate->IsExecutionTerminating()) {
            return ScriptValue();
        }
        return _engine->undefinedValue();
    }
    V8ScriptValue result(_engine, data);
    return ScriptValue(new ScriptValueV8Wrapper(_engine, std::move(result)));
}

ScriptEnginePointer ScriptValueV8Wrapper::engine() const {
    if (!_engine) {
        return ScriptEnginePointer();
    }
#ifdef OVERTE_SCRIPT_USE_AFTER_DELETE_GUARD
    Q_ASSERT(!_engine->_wasDestroyed);
#endif
    return _engine->shared_from_this();
}

ScriptValueIteratorPointer ScriptValueV8Wrapper::newIterator() const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    v8::Context::Scope contextScope(_engine->getContext());
    ScriptValueIteratorPointer iterator = std::make_shared<ScriptValueIteratorV8Wrapper>(_engine, _value);
    return iterator;
}

bool ScriptValueV8Wrapper::hasProperty(const QString& name) const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    auto context = _engine->getContext();
    v8::Context::Scope contextScope(context);
    //V8TODO: does function return true on IsObject too?
    if (_value.constGet()->IsObject()) {
    //V8TODO: what about flags?
        v8::Local<v8::Value> resultLocal;
        v8::Local<v8::String> key = v8::String::NewFromUtf8(isolate, name.toStdString().c_str(),v8::NewStringType::kNormal).ToLocalChecked();
        const v8::Local<v8::Object> object = v8::Local<v8::Object>::Cast(_value.constGet());
        //V8TODO: Which context?
        if (object->Get(context, key).ToLocal(&resultLocal)) {
            return true;
        } else {
            return false;
        }
    }
    return false;
}



ScriptValue ScriptValueV8Wrapper::property(const QString& name, const ScriptValue::ResolveFlags &mode) const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    auto context = _engine->getContext();
    v8::Context::Scope contextScope(context);
    if (_value.constGet()->IsNullOrUndefined()) {
        return _engine->undefinedValue();
    }
    if (_value.constGet()->IsObject()) {
    //V8TODO: what about flags?
        v8::Local<v8::Value> resultLocal;
        v8::Local<v8::String> key = v8::String::NewFromUtf8(_engine->getIsolate(), name.toStdString().c_str(),v8::NewStringType::kNormal).ToLocalChecked();
        const v8::Local<v8::Object> object = v8::Local<v8::Object>::Cast(_value.constGet());
        //V8TODO: Which context?
        v8::MaybeLocal<v8::Value> maybeResult;
        {
            QReadLocker readLock(&lock);
            maybeResult = object->Get(context, key);
        }
        if (maybeResult.ToLocal(&resultLocal)) {
            V8ScriptValue result(_engine, resultLocal);
            return ScriptValue(new ScriptValueV8Wrapper(_engine, std::move(result)));
        } else {
            if (isolate->IsExecutionTerminating()) {
                return ScriptValue();
            }
            qCDebug(scriptengine_v8) << "Failed to get script property";
        }
    }
    return _engine->undefinedValue();
}

ScriptValue ScriptValueV8Wrapper::property(quint32 arrayIndex, const ScriptValue::ResolveFlags& mode) const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    v8::Context::Scope contextScope(_engine->getContext());
    if (_value.constGet()->IsNullOrUndefined()) {
        qCDebug(scriptengine_v8) << "Failed to get property, parent of value: " << arrayIndex << " is not a V8 object, reported type: " << QString(*v8::String::Utf8Value(isolate, _value.constGet()->TypeOf(isolate)));
        return _engine->undefinedValue();
    }
    if (_value.constGet()->IsObject()) {
    //V8TODO: what about flags?
        v8::Local<v8::Value> resultLocal;
        const v8::Local<v8::Object> object = v8::Local<v8::Object>::Cast(_value.constGet());
        lock.lockForRead();
        if (object->Get(_value.constGetContext(), arrayIndex).ToLocal(&resultLocal)) {
            V8ScriptValue result(_engine, resultLocal);
            lock.unlock();
            return ScriptValue(new ScriptValueV8Wrapper(_engine, std::move(result)));
        }
        lock.unlock();
    }
    qCDebug(scriptengine_v8) << "Failed to get property, parent of value: " << arrayIndex << " is not a V8 object, reported type: " << QString(*v8::String::Utf8Value(isolate, _value.constGet()->TypeOf(isolate)));
    return _engine->undefinedValue();
}

ScriptValue ScriptValueV8Wrapper::prototype() const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    v8::Context::Scope contextScope(_engine->getContext());

    auto value = _value.constGet();
    if (!value->IsObject()) {
        return _engine->undefinedValue();
    }
    auto object = v8::Local<v8::Object>::Cast(value);
    auto prototype = object->GetPrototype();

    V8ScriptValue result(_engine, prototype);
    return ScriptValue(new ScriptValueV8Wrapper(_engine, result));
}

void ScriptValueV8Wrapper::setData(const ScriptValue& value) {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    auto context = _engine->getContext();
    v8::Context::Scope contextScope(context);
    V8ScriptValue unwrapped = fullUnwrap(value);
    // Private properties are an experimental feature for now on V8, so we are using regular value for now
    if (_value.constGet()->IsNullOrUndefined()) {
        qCDebug(scriptengine_v8) << "ScriptValueV8Wrapper::setData() was called on a value that is null or undefined";
        return;
    }
    if (_value.constGet()->IsObject()) {
        auto v8Object = v8::Local<v8::Object>::Cast(_value.constGet());
        if( !v8Object->Set(context, v8::String::NewFromUtf8(isolate, "__data").ToLocalChecked(), unwrapped.constGet()).FromMaybe(false)) {
            qCDebug(scriptengine_v8) << "ScriptValueV8Wrapper::data(): Data object couldn't be created";
            Q_ASSERT(false);
        }
    } else {
        qCDebug(scriptengine_v8) << "ScriptValueV8Wrapper::data() was called on a value that is not an object";
        Q_ASSERT(false);
    }
}

void ScriptValueV8Wrapper::setProperty(const QString& name, const ScriptValue& value, const ScriptValue::PropertyFlags& flags) {
    Q_ASSERT(flags != ScriptValue::PropertyGetter || flags != ScriptValue::PropertySetter);
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    auto context = _engine->getContext();
    v8::Context::Scope contextScope(context);
    V8ScriptValue unwrapped = fullUnwrap(value);
    if (_value.constGet()->IsNullOrUndefined()) {
        qCDebug(scriptengine_v8) << "ScriptValueV8Wrapper::setProperty() was called on a value that is null or undefined";
        return;
    }
    if(_value.constGet()->IsObject()) {
        v8::Local<v8::String> key = v8::String::NewFromUtf8(isolate, name.toStdString().c_str(),v8::NewStringType::kNormal).ToLocalChecked();
        Q_ASSERT(_value.get()->IsObject());
        auto object = v8::Local<v8::Object>::Cast(_value.get());
        lock.lockForRead();
        v8::Maybe<bool> retVal = object->Set(isolate->GetCurrentContext(), key, unwrapped.constGet());
        lock.unlock();
        if (retVal.IsJust() ? !retVal.FromJust() : true){
            qCDebug(scriptengine_v8) << "Failed to set property";
        }
    } else {
        v8::Local<v8::String> details;
        QString detailsString("");
        if(_value.get()->ToDetailString(context).ToLocal(&details)) {
            v8::String::Utf8Value utf8Value(isolate,details);
            detailsString = *utf8Value;
        }
        qCDebug(scriptengine_v8) << "Failed to set property:" + name + " - parent is not an object. Parent details: " + " Type: " + QString(*v8::String::Utf8Value(isolate, _value.constGet()->TypeOf(isolate)));
        qCDebug(scriptengine_v8) << _engine->currentContext()->backtrace();
    }
    //V8TODO: what about flags?
    //_value.setProperty(name, unwrapped, (V8ScriptValue::PropertyFlags)(int)flags);
}

void ScriptValueV8Wrapper::setProperty(quint32 arrayIndex, const ScriptValue& value, const ScriptValue::PropertyFlags& flags) {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    auto context = _engine->getContext();
    v8::Context::Scope contextScope(context);
    V8ScriptValue unwrapped = fullUnwrap(value);
    if (_value.constGet()->IsNullOrUndefined()) {
        qCDebug(scriptengine_v8) << "ScriptValueV8Wrapper::setProperty() was called on a value that is null or undefined";
        return;
    }
    if(_value.constGet()->IsObject()) {
        auto object = v8::Local<v8::Object>::Cast(_value.get());
        //V8TODO: I don't know which context to use here
        lock.lockForRead();
        v8::Maybe<bool> retVal(object->Set(context, arrayIndex, unwrapped.constGet()));
        lock.unlock();
        if (retVal.IsJust() ? !retVal.FromJust() : true){
            qCDebug(scriptengine_v8) << "Failed to set property";
        }
    } else {
        qCDebug(scriptengine_v8) << "Failed to set property: " + QString::number(arrayIndex) + " - parent is not an object";
    }
    //V8TODO: what about flags?
    //_value.setProperty(arrayIndex, unwrapped, (V8ScriptValue::PropertyFlags)(int)flags);
}

void ScriptValueV8Wrapper::setPrototype(const ScriptValue& prototype) {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    auto context = _engine->getContext();
    v8::Context::Scope contextScope(context);
    ScriptValueV8Wrapper* unwrappedPrototype = unwrap(prototype);
    if (unwrappedPrototype) {
        if(unwrappedPrototype->toV8Value().constGet()->IsNullOrUndefined() && _value.constGet()->IsNullOrUndefined()) {
            qCDebug(scriptengine_v8) << "Failed to assign prototype - one of values is null or undefined";
        }
        if(unwrappedPrototype->toV8Value().constGet()->IsObject() && _value.constGet()->IsObject()) {
            auto object = v8::Local<v8::Object>::Cast(_value.get());
            //V8TODO: I don't know which context to use here
            lock.lockForRead();
            v8::Maybe<bool> retVal = object->SetPrototype(context, unwrappedPrototype->toV8Value().constGet());
            lock.unlock();
            if (retVal.IsJust() ? !retVal.FromJust() : true){
                qCDebug(scriptengine_v8) << "Failed to assign prototype";
            }
        } else {
            qCDebug(scriptengine_v8) << "Failed to assign prototype - one of values is not an object";
        }
    }
}

bool ScriptValueV8Wrapper::strictlyEquals(const ScriptValue& other) const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    v8::Context::Scope contextScope(_engine->getContext());
    ScriptValueV8Wrapper* unwrappedOther = unwrap(other);
    if (!unwrappedOther || isolate != unwrappedOther->_engine->getIsolate()) { return false; }
    const auto value = _value.constGet();
    const auto otherValue = unwrappedOther->toV8Value().constGet();
    return !value.IsEmpty() && !otherValue.IsEmpty() && value->StrictEquals(otherValue);
}

inline QList<QString> ScriptValueV8Wrapper::getPropertyNames() const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    auto context = _engine->getContext();
    v8::Context::Scope contextScope(context);
    v8::Local<v8::Value> value = _value.constGet();
    if (value.IsEmpty() || value->IsNullOrUndefined()) {
        return QList<QString>();
    }
    if (!value->IsObject()) {
        return QList<QString>();
    }
    v8::Local<v8::Object> object = v8::Local<v8::Object>::Cast(value);
    v8::Local<v8::Array> array;
    if (!object->GetPropertyNames(context).ToLocal(&array)) {
        return QList<QString>();
    }
    QList<QString> names;
    for (uint32_t n = 0; n < array->Length(); n++) {
        v8::Local<v8::Value> key;
        v8::Local<v8::String> name;
        if (!array->Get(context, n).ToLocal(&key) || !key->ToString(context).ToLocal(&name)) { return {}; }
        v8::String::Utf8Value text(isolate, name);
        if (!*text) { return {}; }
        names.append(QString::fromUtf8(*text, text.length()));
    }
    return names;
}

bool ScriptValueV8Wrapper::toBool() const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    v8::Context::Scope contextScope(_engine->getContext());
    return _value.constGet()->ToBoolean(_engine->getIsolate())->Value();
}

qint32 ScriptValueV8Wrapper::toInt32() const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    auto context = _engine->getContext();
    v8::Context::Scope contextScope(context);
    v8::Local<v8::Int32> integer;
    const auto value = _value.constGet();
    if (value.IsEmpty() || !value->ToInt32(context).ToLocal(&integer)) {
        return 0;
    }
    return static_cast<int32_t>((integer)->Value());
}

double ScriptValueV8Wrapper::toInteger() const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    auto context = _engine->getContext();
    v8::Context::Scope contextScope(context);
    v8::Local<v8::Integer> integer;
    const auto value = _value.constGet();
    if (value.IsEmpty() || !value->ToInteger(context).ToLocal(&integer)) {
        return 0;
    }
    return (integer)->Value();
}

double ScriptValueV8Wrapper::toNumber() const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    auto context = _engine->getContext();
    v8::Context::Scope contextScope(context);
    v8::Local<v8::Number> number;
    const auto value = _value.constGet();
    if (value.IsEmpty() || !value->ToNumber(context).ToLocal(&number)) {
        return std::numeric_limits<double>::quiet_NaN();
    }
    return number->Value();
}

QString ScriptValueV8Wrapper::toString() const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    const auto context = _engine->getContext();
    v8::Context::Scope contextScope(context);
    const auto value = _value.constGet();
    v8::Local<v8::String> converted;
    if (value.IsEmpty() || !value->ToString(context).ToLocal(&converted)) { return {}; }
    v8::String::Utf8Value string(isolate, converted);
    return *string ? QString::fromUtf8(*string, string.length()) : QString();
}

quint16 ScriptValueV8Wrapper::toUInt16() const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    auto context = _engine->getContext();
    v8::Context::Scope contextScope(context);
    v8::Local<v8::Uint32> integer;
    const auto value = _value.constGet();
    if (value.IsEmpty() || !value->ToUint32(context).ToLocal(&integer)) {
        return 0;
    }
    return static_cast<uint16_t>(integer->Value());
}

quint32 ScriptValueV8Wrapper::toUInt32() const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    auto context = _engine->getContext();
    v8::Context::Scope contextScope(context);
    v8::Local<v8::Uint32> integer;
    const auto value = _value.constGet();
    if (value.IsEmpty() || !value->ToUint32(context).ToLocal(&integer)) {
        return 0;
    }
    return integer->Value();
}

QVariant ScriptValueV8Wrapper::toVariant() const {
    QVariant dest;
    if (_engine->castValueToVariant(_value, dest, QMetaType::UnknownType)) {
        return dest;
    } else {
        Q_ASSERT(false);
        return QVariant();
    }
}

QObject* ScriptValueV8Wrapper::toQObject() const {
    QVariant dest;
    if (_engine->castValueToVariant(_value, dest, QMetaType::QObjectStar)) {
        if (dest.canConvert<QObject*>()) {
            return dest.value<QObject*>();
        } else {
            //Q_ASSERT(false);
            return nullptr;
        }
    } else {
        //Q_ASSERT(false);
        return nullptr;
    }
}

static QString reprImpl(
    v8::Isolate* isolate,
    v8::Local<v8::Context> context,
    v8::Local<v8::Value> value,
    int indent = 0,
    bool prependIndent = true
) {
    constexpr int INDENT_WIDTH = 4;

    QString str;

    if (prependIndent) { str = QString(INDENT_WIDTH * indent, ' '); }

    if (value->IsUndefined()) {
        str += "undefined";
    } else if (value->IsNull()) {
        str += "null";
    } else if (value->IsArray()) {
        v8::Handle<v8::Array> array = v8::Handle<v8::Array>::Cast(value);
        auto length = array->Length();

        str += "Array(";
        str += QString::number(length);
        str += ") [\n";

        for (uint32_t i = 0; i < length; i++) {
            str += QString(INDENT_WIDTH * (indent + 1), ' ');
            str += QString::number(i);
            str += ": ";

            // arrays in javascript can have unoccupied elements
            if (array->Has(context, i).ToChecked()) {
                str += reprImpl(
                    isolate,
                    context,
                    array->Get(context, i).ToLocalChecked(),
                    indent + 1,
                    false
                );
            } else {
                str += "<empty slot>";
            }

            str += ",\n";
        }

        str += QString(INDENT_WIDTH * indent, ' ');
        str += ']';
    } else if (value->IsObject() && !value->IsFunction()) {
        // don't use this path for functions, they're objects but not
        // relevant for property dumps, so just use the primitive path instead
        v8::Local<v8::Object> object = v8::Local<v8::Object>::Cast(value);
        v8::Local<v8::String> constructorName = object->GetConstructorName();

        str += QString(*v8::String::Utf8Value(isolate, constructorName->ToString(context).ToLocalChecked()));;

        v8::Local<v8::Array> properties = object->GetPropertyNames(context).ToLocalChecked();

        if (properties->Length() != 0) {
            str += " {\n";

            for (uint32_t i = 0; i < properties->Length(); i++) {
                auto name = properties->Get(context, i).ToLocalChecked();
                auto elem = object->Get(context, name).ToLocalChecked();

                str += QString(INDENT_WIDTH * (indent + 1), ' ');
                str += reprImpl(isolate, context, name);
                str += ": ";
                str += reprImpl(
                    isolate,
                    context,
                    elem,
                    indent + 1,
                    false
                );
                str += "\n";
            }

            str += QString(INDENT_WIDTH * indent, ' ');
            str += "}";
        } else {
            str += " {}";
        }
    } else if (value->IsSymbol()) {
        v8::Local<v8::Symbol> symbol = v8::Local<v8::Symbol>::Cast(value);
        str += "Symbol(";
        str += QString(*v8::String::Utf8Value(isolate, symbol->Description(isolate)));
        str += ')';
    } else {
        // Number, String, Boolean, Function
        if (auto valueString = value->ToString(context); !valueString.IsEmpty()) {
            str += QString(*v8::String::Utf8Value(isolate, valueString.ToLocalChecked()));
        } else {
            str += "[...]";
        }
    }

    return str;
}

QString ScriptValueV8Wrapper::repr() const {
    auto* isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());

    v8::HandleScope handleScope(isolate);

    auto context = _engine->getContext();
    v8::Context::Scope contextScope(context);

    auto value = toV8Value().constGet();

    return reprImpl(isolate, context, value);
}

bool ScriptValueV8Wrapper::equals(const ScriptValue& other) const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    auto context = _engine->getContext();
    v8::Context::Scope contextScope(context);
    ScriptValueV8Wrapper* unwrappedOther = unwrap(other);
    if (!unwrappedOther || isolate != unwrappedOther->_engine->getIsolate()) { return false; }
    const auto value = _value.constGet();
    const auto otherValue = unwrappedOther->toV8Value().constGet();
    // Equals may invoke user coercion. Evaluate it exactly once: a second
    // invocation can change state or throw even if the first one succeeded.
    return !value.IsEmpty() && !otherValue.IsEmpty() && value->Equals(context, otherValue).FromMaybe(false);
}

bool ScriptValueV8Wrapper::isArray() const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    v8::Context::Scope contextScope(_engine->getContext());
    return _value.constGet()->IsArray();
}

bool ScriptValueV8Wrapper::isBool() const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    v8::Context::Scope contextScope(_engine->getContext());
    return _value.constGet()->IsBoolean();
}

bool ScriptValueV8Wrapper::isError() const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    auto context = _engine->getContext();
    v8::Context::Scope contextScope(context);
    v8::Local<v8::Value> error;
    if (!context->Global()->Get(context, v8::String::NewFromUtf8(isolate, "Error").ToLocalChecked()).ToLocal(&error)) {
        Q_ASSERT(false);
    }
    if (!error->IsObject()) {
        Q_ASSERT(false);
    }
    auto errorObj = v8::Local<v8::Object>::Cast(error);
    if (_value.constGet()->InstanceOf(context, errorObj).FromMaybe(false)) {
        return true;
    }
    return false;
}

bool ScriptValueV8Wrapper::isFunction() const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    v8::Context::Scope contextScope(_engine->getContext());
    return _value.constGet()->IsFunction();
}

bool ScriptValueV8Wrapper::isNumber() const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    v8::Context::Scope contextScope(_engine->getContext());
    return _value.constGet()->IsNumber();
}

bool ScriptValueV8Wrapper::isNull() const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    v8::Context::Scope contextScope(_engine->getContext());
    return _value.constGet()->IsNull();
}

bool ScriptValueV8Wrapper::isObject() const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    v8::Context::Scope contextScope(_engine->getContext());
    return _value.constGet()->IsObject();
}

bool ScriptValueV8Wrapper::isString() const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    v8::Context::Scope contextScope(_engine->getContext());
    return _value.constGet()->IsString();
}

bool ScriptValueV8Wrapper::isUndefined() const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    v8::Context::Scope contextScope(_engine->getContext());
    return _value.constGet()->IsUndefined();
}

bool ScriptValueV8Wrapper::isValid() const {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    v8::Context::Scope contextScope(_engine->getContext());
    if (_value.constGet()->IsNullOrUndefined()) {
        return false;
    }
    return true;
}

bool ScriptValueV8Wrapper::isVariant() const {
    //V8TODO: check if it's variant proxy? I'm not sure though.
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    v8::Context::Scope contextScope(_engine->getContext());
    Q_ASSERT(false);
    return false;
    //return _value.isVariant();
}
