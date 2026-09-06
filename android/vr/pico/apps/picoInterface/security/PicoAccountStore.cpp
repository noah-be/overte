// SPDX-License-Identifier: Apache-2.0
#include "PicoAccountStore.h"
#include <mutex>

namespace overte { namespace pico {
namespace {
using namespace security;
bool failed(JNIEnv* env) {
    if (!env->ExceptionCheck()) return false;
    env->ExceptionClear(); // Never ExceptionDescribe(): Java messages can contain private data.
    return true;
}
StoreResult status(jint value) {
    switch (value) {
        case 0: return StoreResult::Ok;
        case 1: return StoreResult::Absent;
        case 2: return StoreResult::Locked;
        case 3: return StoreResult::Unavailable;
        case 4: return StoreResult::Corrupt;
        case 5: return StoreResult::IoError;
        default: return StoreResult::Unavailable;
    }
}
class Environment {
public:
    explicit Environment(JavaVM* vm) : _vm(vm) {
        if (!vm) return;
        jint result = vm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6);
        if (result == JNI_EDETACHED) {
#ifdef __ANDROID__
            attached = vm->AttachCurrentThread(&env, nullptr) == JNI_OK;
#else
            attached = vm->AttachCurrentThread(reinterpret_cast<void**>(&env), nullptr) == JNI_OK;
#endif
            if (!attached) env = nullptr;
        } else if (result != JNI_OK) env = nullptr;
        if (env && (env->PushLocalFrame(16) < 0 || failed(env))) {
            failed(env); env = nullptr;
        }
    }
    ~Environment() {
        if (env) env->PopLocalFrame(nullptr);
        if (attached) _vm->DetachCurrentThread();
    }
    JNIEnv* env { nullptr };
private:
    JavaVM* _vm;
    bool attached { false };
};
void wipe(JNIEnv* env, jbyteArray bytes) {
    if (!bytes) return;
    const auto length = env->GetArrayLength(bytes);
    if (failed(env)) return;
    const jbyte zeros[256] {};
    for (jsize at = 0; at < length; at += 256) {
        env->SetByteArrayRegion(bytes, at, std::min<jsize>(256, length - at), zeros);
        if (failed(env)) return;
    }
}
class Store final : public ProtectedAccountStore {
public:
    bool prepare(JNIEnv* env, jobject peer) {
        std::lock_guard<std::mutex> guard(mutex);
        if (object) return true; // Application-context peer survives Activity recreation.
        if (!peer || env->PushLocalFrame(8) < 0) { failed(env); return false; }
        JavaVM* candidateVm = nullptr;
        jclass type = env->GetObjectClass(peer);
        bool valid = !failed(env) && type;
        if (valid) {
            readMethod = env->GetMethodID(type, "read", "()Lorg/overte/pico/PicoAccountStoreBridge$ReadResult;");
            valid = !failed(env) && readMethod;
        }
        if (valid) { writeMethod = env->GetMethodID(type, "write", "([B)I"); valid = !failed(env) && writeMethod; }
        if (valid) { eraseMethod = env->GetMethodID(type, "erase", "()I"); valid = !failed(env) && eraseMethod; }
        if (valid) valid = env->GetJavaVM(&candidateVm) == JNI_OK;
        if (valid) { object = env->NewGlobalRef(peer); valid = !failed(env) && object; }
        if (valid) vm = candidateVm;
        env->PopLocalFrame(nullptr);
        return valid;
    }
    StoreResult read(AccountBytes& output) override {
        std::lock_guard<std::mutex> guard(mutex);
        clearAccountBytes(output);
        Environment scope(vm);
        auto env = scope.env;
        if (!env || !object) return StoreResult::Unavailable;
        jobject result = env->CallObjectMethod(object, readMethod);
        if (failed(env) || !result) return StoreResult::Unavailable;
        jclass type = env->GetObjectClass(result);
        if (failed(env) || !type) return StoreResult::Unavailable;
        auto statusField = env->GetFieldID(type, "status", "I");
        if (failed(env) || !statusField) return StoreResult::Unavailable;
        auto bytesField = env->GetFieldID(type, "bytes", "[B");
        if (failed(env) || !bytesField) return StoreResult::Unavailable;
        jint code = env->GetIntField(result, statusField);
        if (failed(env)) return StoreResult::Unavailable;
        auto bytes = static_cast<jbyteArray>(env->GetObjectField(result, bytesField));
        if (failed(env)) return StoreResult::Unavailable;
        StoreResult outcome = status(code);
        if (outcome == StoreResult::Ok) {
            jsize count = bytes ? env->GetArrayLength(bytes) : 0;
            if (failed(env)) outcome = StoreResult::Unavailable;
            else if (count <= 0 || static_cast<std::size_t>(count) > MAX_ACCOUNT_BYTES) outcome = StoreResult::Corrupt;
            else {
                try { output.resize(count); }
                catch (...) { wipe(env, bytes); return StoreResult::Unavailable; }
                env->GetByteArrayRegion(bytes, 0, count, reinterpret_cast<jbyte*>(output.data()));
                if (failed(env)) { clearAccountBytes(output); outcome = StoreResult::Unavailable; }
            }
        }
        wipe(env, bytes);
        return outcome;
    }
    StoreResult write(const AccountBytes& input) override {
        std::lock_guard<std::mutex> guard(mutex);
        if (input.empty() || input.size() > MAX_ACCOUNT_BYTES) return StoreResult::Corrupt;
        Environment scope(vm);
        auto env = scope.env;
        if (!env || !object) return StoreResult::Unavailable;
        auto bytes = env->NewByteArray(static_cast<jsize>(input.size()));
        if (failed(env) || !bytes) return StoreResult::Unavailable;
        env->SetByteArrayRegion(bytes, 0, static_cast<jsize>(input.size()), reinterpret_cast<const jbyte*>(input.data()));
        if (failed(env)) { wipe(env, bytes); return StoreResult::Unavailable; }
        auto code = env->CallIntMethod(object, writeMethod, bytes);
        const bool error = failed(env);
        wipe(env, bytes);
        auto result = error ? StoreResult::Unavailable : status(code);
        return result == StoreResult::Absent ? StoreResult::IoError : result;
    }
    StoreResult erase() override {
        std::lock_guard<std::mutex> guard(mutex);
        Environment scope(vm);
        if (!scope.env || !object) return StoreResult::Unavailable;
        auto code = scope.env->CallIntMethod(object, eraseMethod);
        return failed(scope.env) ? StoreResult::Unavailable : status(code);
    }
private:
    std::mutex mutex;
    JavaVM* vm { nullptr };
    jobject object { nullptr };
    jmethodID readMethod { nullptr }, writeMethod { nullptr }, eraseMethod { nullptr };
};
std::shared_ptr<Store> store() {
    // Process-lived JNI references must not be destroyed after JVM teardown.
    static auto* instance = new std::shared_ptr<Store>(std::make_shared<Store>());
    return *instance;
}
}
std::shared_ptr<security::ProtectedAccountStore> protectedAccountStore() { return store(); }
bool prepareProtectedAccountStore(JNIEnv* env, jobject peer) { return store()->prepare(env, peer); }
}}

extern "C" JNIEXPORT jboolean JNICALL
Java_org_overte_pico_PicoInterfaceActivity_prepareProtectedAccountStore(JNIEnv* env, jobject, jobject peer) {
    try { return overte::pico::prepareProtectedAccountStore(env, peer) ? JNI_TRUE : JNI_FALSE; }
    catch (...) { if (env->ExceptionCheck()) env->ExceptionClear(); return JNI_FALSE; }
}
