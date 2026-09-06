//
//  ScriptValueIteratorV8Wrapper.cpp
//  libraries/script-engine/src/v8
//
//  Created by Heather Anderson on 8/29/21.
//  Modified for V8 by dr Karol Suprynowicz on 2022/10/08
//  Copyright 2021 Vircadia contributors.
//  Copyright 2022-2023 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//  SPDX-License-Identifier: Apache-2.0
//

#include "ScriptValueIteratorV8Wrapper.h"
#include "ScriptEngineLoggingV8.h"
#include <limits>

V8ScriptValueIterator::V8ScriptValueIterator(ScriptEngineV8* engine, v8::Local<v8::Value> object) : _engine(engine)  {
    if (_engine->isEvaluationAborted()) { return; }
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    _context.Reset(isolate, _engine->getContext());
    auto context = _context.Get(isolate);
    v8::Context::Scope contextScope(context);
    if (object.IsEmpty() || !object->IsObject()) {
        return;
    }
    v8::Local<v8::Object> v8Object = v8::Local<v8::Object>::Cast(object);
    v8::Local<v8::Array> names;
    if (!v8Object->GetOwnPropertyNames(context).ToLocal(&names) ||
            names->Length() > static_cast<uint32_t>(std::numeric_limits<int>::max())) {
        return;
    }
    _object.Reset(isolate, v8Object);
    _propertyNames.Reset(isolate, names);
    _length = static_cast<int>(names->Length());
}

V8ScriptValueIterator::~V8ScriptValueIterator() {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    _propertyNames.Reset();
    _object.Reset();
    _context.Reset();
}

bool V8ScriptValueIterator::hasNext() const {
    if (_engine->isEvaluationAborted()) { return false; }
    return _currentIndex < _length - 1;
}

QString V8ScriptValueIterator::name() const {
    if (_engine->isEvaluationAborted()) { return {}; }
    if (_currentIndex < 0 || _currentIndex >= _length || _propertyNames.IsEmpty()) {
        return {};
    }
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    auto context = _context.Get(isolate);
    v8::Context::Scope contextScope(context);
    v8::Local<v8::Value> propertyName;
    if (!_propertyNames.Get(isolate)->Get(context, _currentIndex).ToLocal(&propertyName)) {
        return {};
    }
    v8::String::Utf8Value bytes(isolate, propertyName);
    return *bytes ? QString::fromUtf8(*bytes, bytes.length()) : QString();
}

void V8ScriptValueIterator::next() {
    if (_engine->isEvaluationAborted()) { return; }
    if (_currentIndex < _length - 1) {
        _currentIndex++;
    }
}

V8ScriptValue V8ScriptValueIterator::value() {
    auto isolate = _engine->getIsolate();
    Q_ASSERT(isolate->IsCurrent());
    v8::HandleScope handleScope(isolate);
    if (_engine->isEvaluationAborted()) { return V8ScriptValue(_engine, v8::Undefined(isolate)); }
    if (_currentIndex < 0 || _currentIndex >= _length || _propertyNames.IsEmpty() || _object.IsEmpty()) {
        return V8ScriptValue(_engine, v8::Undefined(isolate));
    }
    auto context = _context.Get(isolate);
    v8::Context::Scope contextScope(context);
    v8::Local<v8::Value> v8Value;
    v8::Local<v8::Value> propertyName;
    if (!_propertyNames.Get(isolate)->Get(context, _currentIndex).ToLocal(&propertyName) ||
            !_object.Get(isolate)->Get(context, propertyName).ToLocal(&v8Value)) {
        v8Value = v8::Undefined(isolate);
    }
    return V8ScriptValue(_engine, v8Value);
}

ScriptValue::PropertyFlags ScriptValueIteratorV8Wrapper::flags() const {
    //V8TODO
    return ScriptValue::PropertyFlags();
}

bool ScriptValueIteratorV8Wrapper::hasNext() const {
    return _value->hasNext();
}

QString ScriptValueIteratorV8Wrapper::name() const {
    return _value->name();
}

void ScriptValueIteratorV8Wrapper::next() {
    _value->next();
}

ScriptValue ScriptValueIteratorV8Wrapper::value() const {
    V8ScriptValue result = _value->value();
    return ScriptValue(new ScriptValueV8Wrapper(_engine, std::move(result)));
}
