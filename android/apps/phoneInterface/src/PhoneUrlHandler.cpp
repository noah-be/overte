//
// Runtime URL hand-off from Android's activity thread to the Qt application.
//

#include <jni.h>

#include <QCoreApplication>
#include <QMetaObject>
#include <QString>
#include <QThread>

#include "AndroidHelper.h"

namespace {

QString fromJavaString(JNIEnv* env, jstring value) {
    if (!env || !value) {
        return {};
    }

    const jchar* characters = env->GetStringChars(value, nullptr);
    if (!characters) {
        // GetStringChars may leave an OutOfMemoryError pending. Do not perform
        // further JNI work in that case; Java will receive the exception.
        return {};
    }

    const jsize length = env->GetStringLength(value);
    const QString result = QString::fromUtf16(
        reinterpret_cast<const ushort*>(characters), length);
    env->ReleaseStringChars(value, characters);
    return result;
}

} // namespace

extern "C" JNIEXPORT void JNICALL
Java_org_overte_phone_PhoneInterfaceActivity_nativeProcessUrl(
        JNIEnv* env, jobject /* activity */, jstring value) {
    const QString url = fromJavaString(env, value).trimmed();
    if (url.isEmpty() || !QCoreApplication::instance()) {
        return;
    }

    auto& androidHelper = AndroidHelper::instance();
    if (QThread::currentThread() == androidHelper.thread()) {
        androidHelper.processURL(url);
        return;
    }

    QMetaObject::invokeMethod(
        &androidHelper,
        [url]() { AndroidHelper::instance().processURL(url); },
        Qt::QueuedConnection);
}
