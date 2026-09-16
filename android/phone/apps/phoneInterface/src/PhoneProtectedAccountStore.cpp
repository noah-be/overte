// SPDX-License-Identifier: Apache-2.0
#include "PhoneProtectedAccountStore.h"
#include <array>

namespace {
using overte::security::StoreResult;

class Environment {
public:
    explicit Environment(JavaVM* vm) : _vm(vm) {
        if (!_vm) { return; }
        const jint status = _vm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6);
        if (status == JNI_EDETACHED) {
            // Android and host JDK headers declare different environment types.
#if defined(__ANDROID__)
            _attached = _vm->AttachCurrentThread(&env, nullptr) == JNI_OK;
#else
            _attached = _vm->AttachCurrentThread(reinterpret_cast<void**>(&env), nullptr) == JNI_OK;
#endif
            if (!_attached) { env = nullptr; }
        } else if (status != JNI_OK) {
            env = nullptr;
        }
    }
    ~Environment() { if (_attached) { _vm->DetachCurrentThread(); } }
    JNIEnv* env { nullptr };
private:
    JavaVM* _vm;
    bool _attached { false };
};

// Never call ExceptionDescribe or stringify a Throwable. Only the Phone
// StoreException method supplies the fixed transport code; other exceptions
// mean the native facility/binding is unavailable.
StoreResult consumeException(JNIEnv* env) {
    jthrowable error = env->ExceptionOccurred();
    if (!error) { return StoreResult::Ok; }
    env->ExceptionClear();
    StoreResult result = StoreResult::Unavailable;
    jclass type = env->GetObjectClass(error);
    if (!env->ExceptionCheck() && type) {
        jmethodID code = env->GetMethodID(type, "nativeFailure", "()I");
        if (!env->ExceptionCheck() && code) {
            jint value = env->CallIntMethod(error, code);
            if (!env->ExceptionCheck()) {
                if (value == 2) { result = StoreResult::Corrupt; }
                else if (value == 3) { result = StoreResult::IoError; }
            }
        }
    }
    if (env->ExceptionCheck()) { env->ExceptionClear(); }
    if (type) { env->DeleteLocalRef(type); }
    env->DeleteLocalRef(error);
    return result;
}

void wipeArray(JNIEnv* env, jbyteArray array, jsize size) {
    std::array<jbyte, 4096> zeros {};
    for (jsize offset = 0; offset < size;) {
        jsize count = std::min<jsize>(size - offset, zeros.size());
        env->SetByteArrayRegion(array, offset, count, zeros.data());
        if (env->ExceptionCheck()) { env->ExceptionClear(); break; }
        offset += count;
    }
}
}

namespace phone {
using namespace overte::security;

ProtectedAccountStore::ProtectedAccountStore(JavaVM* vm, JNIEnv* env, jobject store) : _vm(vm) {
    if (!vm || !env || !store || env->ExceptionCheck()) { return; }
    jclass type = env->GetObjectClass(store);
    if (consumeException(env) != StoreResult::Ok || !type) { return; }
    _read = env->GetMethodID(type, "read", "()[B");
    if (consumeException(env) == StoreResult::Ok && _read) {
        _write = env->GetMethodID(type, "write", "([B)V");
        if (consumeException(env) == StoreResult::Ok && _write) {
            _clear = env->GetMethodID(type, "clear", "()V");
            if (consumeException(env) == StoreResult::Ok && _clear) {
                _store = env->NewGlobalRef(store);
                consumeException(env);
            }
        }
    }
    env->DeleteLocalRef(type);
}

ProtectedAccountStore::~ProtectedAccountStore() {
    Environment attached(_vm);
    if (attached.env && _store) { attached.env->DeleteGlobalRef(_store); }
}

StoreResult ProtectedAccountStore::read(AccountBytes& output) {
    clearAccountBytes(output);
    if (!available()) { return StoreResult::Unavailable; }
    Environment attached(_vm);
    JNIEnv* env = attached.env;
    if (!env) { return StoreResult::Unavailable; }
    auto array = static_cast<jbyteArray>(env->CallObjectMethod(_store, _read));
    StoreResult result = consumeException(env);
    if (result != StoreResult::Ok) {
        if (array) { env->DeleteLocalRef(array); }
        return result;
    }
    if (!array) { return StoreResult::Absent; }
    const jsize size = env->GetArrayLength(array);
    result = consumeException(env);
    if (result == StoreResult::Ok && (size <= 0 || size > static_cast<jsize>(MAX_ACCOUNT_BYTES))) {
        result = StoreResult::Corrupt;
    }
    if (result == StoreResult::Ok) {
        try {
            output.resize(size);
        } catch (...) {
            result = StoreResult::Unavailable;
        }
        if (result == StoreResult::Ok) {
            env->GetByteArrayRegion(array, 0, size, reinterpret_cast<jbyte*>(output.data()));
            result = consumeException(env);
        }
    }
    if (size > 0) { wipeArray(env, array, size); }
    env->DeleteLocalRef(array);
    if (result != StoreResult::Ok) { clearAccountBytes(output); }
    return result;
}

StoreResult ProtectedAccountStore::write(const AccountBytes& input) {
    if (input.empty() || input.size() > MAX_ACCOUNT_BYTES) { return StoreResult::Corrupt; }
    if (!available()) { return StoreResult::Unavailable; }
    Environment attached(_vm);
    JNIEnv* env = attached.env;
    if (!env) { return StoreResult::Unavailable; }
    jbyteArray array = env->NewByteArray(static_cast<jsize>(input.size()));
    StoreResult result = consumeException(env);
    if (!array || result != StoreResult::Ok) { return StoreResult::Unavailable; }
    env->SetByteArrayRegion(array, 0, input.size(), reinterpret_cast<const jbyte*>(input.data()));
    result = consumeException(env);
    if (result == StoreResult::Ok) {
        env->CallVoidMethod(_store, _write, array);
        result = consumeException(env);
    }
    wipeArray(env, array, input.size());
    env->DeleteLocalRef(array);
    return result;
}

StoreResult ProtectedAccountStore::erase() {
    if (!available()) { return StoreResult::Unavailable; }
    Environment attached(_vm);
    if (!attached.env) { return StoreResult::Unavailable; }
    attached.env->CallVoidMethod(_store, _clear);
    return consumeException(attached.env);
}
}
