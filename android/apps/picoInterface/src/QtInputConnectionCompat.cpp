#include <jni.h>

// The QtAndroid.jar bundled by androiddeployqt contains finishComposingText(),
// while the prebuilt Qt 5 native input context used by this target predates
// that JNI entry point. Android calls it when an input connection is closed
// (for example while opening or dismissing the tablet UI). Returning success
// is equivalent to having no pending composition and avoids a Java-side
// UnsatisfiedLinkError.
extern "C" JNIEXPORT jboolean JNICALL
Java_org_qtproject_qt5_android_QtNativeInputConnection_finishComposingText(
    JNIEnv*, jclass) {
    return JNI_TRUE;
}
