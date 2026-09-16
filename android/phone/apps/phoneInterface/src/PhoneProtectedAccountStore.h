// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <jni.h>
#include "../../../../../security/storage/ProtectedAccountStore.h"

namespace phone {

/** JNI transport for the Phone AndroidKeyStore primitive; PX-15 v001. */
class ProtectedAccountStore final : public overte::security::ProtectedAccountStore {
public:
    ProtectedAccountStore(JavaVM* vm, JNIEnv* env, jobject store);
    ~ProtectedAccountStore() override;
    overte::security::StoreResult read(overte::security::AccountBytes& output) override;
    overte::security::StoreResult write(const overte::security::AccountBytes& input) override;
    overte::security::StoreResult erase() override;
    bool available() const { return _store && _read && _write && _clear; }

private:
    JavaVM* _vm;
    jobject _store { nullptr };
    jmethodID _read { nullptr };
    jmethodID _write { nullptr };
    jmethodID _clear { nullptr };
};
}
