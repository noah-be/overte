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

}} // namespace overte::scripting
