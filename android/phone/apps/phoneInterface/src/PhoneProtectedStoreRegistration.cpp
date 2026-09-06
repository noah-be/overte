// SPDX-License-Identifier: Apache-2.0
#include "PhoneProtectedAccountStore.h"
#include <AccountManager.h>

// Qt's Java loader calls JNI_OnLoad when loading libphoneInterface, before
// invoking the native application entry point. PhoneInterfaceActivity prepares
// the application-scoped Java store before entering QtActivity.onCreate.
extern "C" JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM* vm, void*) {
    JNIEnv* env = nullptr;
    if (vm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6) != JNI_OK) {
        return JNI_ERR;
    }
    jclass type = env->FindClass("org/overte/phone/SecureAccountStore");
    jobject store = nullptr;
    if (!env->ExceptionCheck() && type) {
        jmethodID prepared = env->GetStaticMethodID(type, "preparedStore",
                "()Lorg/overte/phone/SecureAccountStore;");
        if (!env->ExceptionCheck() && prepared) {
            store = env->CallStaticObjectMethod(type, prepared);
        }
    }
    if (env->ExceptionCheck()) { env->ExceptionClear(); }
    try {
        // An unavailable binding still installs a fail-closed adapter. Shared
        // never falls back to AccountInfo.bin, even when Java setup failed.
        AccountManager::installProtectedAccountStore(
                std::make_shared<phone::ProtectedAccountStore>(vm, env, store));
    } catch (...) {
        // Missing registration is fail-closed under the pinned PX-15 contract.
    }
    if (store) { env->DeleteLocalRef(store); }
    if (type) { env->DeleteLocalRef(type); }
    return JNI_VERSION_1_6;
}
