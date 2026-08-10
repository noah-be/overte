#include <jni.h>

#include "support/test_assertions.h"

extern "C" JNIEXPORT jboolean JNICALL
Java_org_qtproject_qt5_android_QtNativeInputConnection_finishComposingText(
        JNIEnv*, jclass);
extern "C" JNIEXPORT jboolean JNICALL
Java_org_qtproject_qt5_android_QtNativeInputConnection_updateCursorPosition(
        JNIEnv*, jclass);

int main() {
    // These compatibility exports intentionally do not dereference JNI state:
    // Qt 5 only needs a successful no-op when newer QtAndroid.jar calls them.
    OVERTE_EXPECT(Java_org_qtproject_qt5_android_QtNativeInputConnection_finishComposingText(
            nullptr, nullptr) == JNI_TRUE);
    OVERTE_EXPECT(Java_org_qtproject_qt5_android_QtNativeInputConnection_updateCursorPosition(
            nullptr, nullptr) == JNI_TRUE);
    return 0;
}
