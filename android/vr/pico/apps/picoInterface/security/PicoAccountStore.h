// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "../../../../../../security/storage/ProtectedAccountStore.h"
#include <jni.h>

namespace overte { namespace pico {
// Prepared by Java before Qt startup; registered by the Shared-owned startup hook.
std::shared_ptr<security::ProtectedAccountStore> protectedAccountStore();
bool prepareProtectedAccountStore(JNIEnv* env, jobject peer);
}}
