#include <jni.h>

// The QtAndroid.jar bundled by androiddeployqt contains input-connection
// methods that the prebuilt Qt 5 native input context used by this target
// predates. Returning success is equivalent to having no pending composition
// or cursor update and avoids a Java-side UnsatisfiedLinkError.
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
