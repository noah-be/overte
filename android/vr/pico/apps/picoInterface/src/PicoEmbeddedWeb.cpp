// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#include <jni.h>
#include <NativeWebViewItem.h>

extern "C" JNIEXPORT void JNICALL
Java_org_overte_pico_PicoEmbeddedWebHost_nativePrepareWeb(JNIEnv* env, jclass, jstring cacheDirectory) {
    if (!cacheDirectory) { return; }
    const auto* text = env->GetStringChars(cacheDirectory, nullptr);
    if (!text) { return; }
    const auto cache = QString::fromUtf16(reinterpret_cast<const ushort*>(text), env->GetStringLength(cacheDirectory));
    env->ReleaseStringChars(cacheDirectory, text);
    // These roots come from the owning Activity, never HTML or a QML grant.
    // The shared setter is locked and is safe before Qt's application starts.
    NativeWebViewItem::setPackagedResourceRoots({ cache + "/scripts", "qrc:/html", "qrc:/scripts" });
}
