// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <v8.h>

namespace overte { namespace scripting {

// Preserve the existing enumerable-property copy semantics, including inherited
// properties and getters. A getter/proxy/setter may throw or be terminated: in
// that case stop immediately, never unwrap an empty MaybeLocal. The caller owns
// TryCatch and must discard partial destination state on failure.
inline bool copyEnumerableProperties(v8::Local<v8::Context> sourceContext,
        v8::Local<v8::Context> destinationContext, v8::Local<v8::Object> source,
        v8::Local<v8::Object> destination) {
    if (sourceContext.IsEmpty() || destinationContext.IsEmpty() || source.IsEmpty() || destination.IsEmpty()) {
        return false;
    }
    v8::Local<v8::Array> names;
    if (!source->GetPropertyNames(sourceContext).ToLocal(&names)) {
        return false;
    }
    for (uint32_t i = 0; i < names->Length(); ++i) {
        v8::Local<v8::Value> name;
        v8::Local<v8::Value> value;
        if (!names->Get(sourceContext, i).ToLocal(&name) ||
                !source->Get(sourceContext, name).ToLocal(&value) ||
                !destination->Set(destinationContext, name, value).FromMaybe(false)) {
            return false;
        }
    }
    return true;
}

// Original closure Script.require cache transfer, including callable objects.
// Keep malformed/missing properties and JS accessor failures on the same
// checked path; a debug assertion is not a validation boundary.
inline bool copyRequireProperties(v8::Local<v8::Context> context,
        v8::Local<v8::Object> sourceGlobal, v8::Local<v8::Object> destinationGlobal) {
    if (context.IsEmpty() || sourceGlobal.IsEmpty() || destinationGlobal.IsEmpty()) {
        return false;
    }
    auto objectProperty = [&](v8::Local<v8::Object> object, const char* name,
            v8::Local<v8::Object>& result) {
        v8::Local<v8::String> key;
        v8::Local<v8::Value> value;
        if (!v8::String::NewFromUtf8(context->GetIsolate(), name).ToLocal(&key) ||
                !object->Get(context, key).ToLocal(&value) || !value->IsObject()) {
            return false;
        }
        result = value.As<v8::Object>();
        return true;
    };
    v8::Local<v8::Object> sourceScript, sourceRequire, destinationScript, destinationRequire;
    v8::Local<v8::Context> sourceContext;
    return objectProperty(sourceGlobal, "Script", sourceScript) &&
        objectProperty(sourceScript, "require", sourceRequire) &&
        objectProperty(destinationGlobal, "Script", destinationScript) &&
        objectProperty(destinationScript, "require", destinationRequire) &&
        sourceRequire->GetCreationContext().ToLocal(&sourceContext) &&
        copyEnumerableProperties(sourceContext, context, sourceRequire, destinationRequire);
}

}} // namespace overte::scripting
