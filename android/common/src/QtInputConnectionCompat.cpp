// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include <jni.h>

// QtAndroid.jar contains input-connection methods that the prebuilt Qt 5
// native input context used by the modern Android targets predates. Returning
// success mirrors the working runtime behavior: there is no pending composition
// or cursor update, and Java must not fail with UnsatisfiedLinkError.
extern "C" JNIEXPORT jboolean JNICALL
Java_org_qtproject_qt5_android_QtNativeInputConnection_finishComposingText(
        JNIEnv*, jclass) {
    return JNI_TRUE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_org_qtproject_qt5_android_QtNativeInputConnection_updateCursorPosition(
        JNIEnv*, jclass) {
    return JNI_TRUE;
}
