// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

// QtAndroid.jar contains input-connection methods that the prebuilt Qt 5
// native input context predates. These no-op successes mirror the working
// Pico runtime and prevent Java-side UnsatisfiedLinkError failures.
#include <jni.h>

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
