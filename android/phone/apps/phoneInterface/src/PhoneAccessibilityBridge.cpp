// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#include <jni.h>
#include <QtAndroidExtras/QAndroidJniObject>
#include <QCoreApplication>
#include <QGuiApplication>
#include <QAccessible>
#include <QJsonDocument>
#include <QMetaObject>
#include <QPointer>
#include <DependencyManager.h>
#include <OffscreenUi.h>
#include <ui/PhoneAccessibilityTree.h>
#include "AndroidHelper.h"
#include "PhoneApplicationOwner.h"

namespace {
PhoneAccessibilityTree& tree() {
    // Used exclusively on Qt's GUI thread after native startup.
    static PhoneAccessibilityTree value;
    return value;
}
QString javaText(JNIEnv* env, jstring value) {
    if (!value) { return {}; }
    const auto characters = env->GetStringChars(value, nullptr);
    if (!characters) { return {}; }
    const auto text = QString::fromUtf16(reinterpret_cast<const ushort*>(characters), env->GetStringLength(value));
    env->ReleaseStringChars(value, characters);
    return text;
}
}

extern "C" JNIEXPORT jboolean JNICALL
Java_org_overte_phone_PhoneAccessibilityBridge_nativeRequestFrame(
        JNIEnv*, jclass, jobject receiver, jint width, jint height, jint generation) {
    auto app = phoneApplication();
    if (!app || !receiver || width <= 0 || height <= 0 || width > 16384 || height > 16384) { return JNI_FALSE; }
    QAndroidJniObject sink(receiver);
    const auto accepted = QMetaObject::invokeMethod(app, [sink, width, height, generation] {
        QJsonObject frame { {"schemaVersion", 1}, {"ready", false} };
        if (AndroidHelper::instance().isLoadComplete() && DependencyManager::isSet<OffscreenUi>()) {
            // This provider owns Android's accessibility delegate. Activate
            // Qt when Android requests its real tree, on Qt's GUI thread.
            QAccessible::setActive(true);
            const auto ui = DependencyManager::get<OffscreenUi>();
            frame = tree().snapshot(ui->getRootItem(), QSize(width, height));
        }
        const auto encoded = QAndroidJniObject::fromString(QString::fromUtf8(QJsonDocument(frame).toJson(QJsonDocument::Compact)));
        sink.callMethod<void>("acceptFrame", "(Ljava/lang/String;I)V", encoded.object<jstring>(), generation);
    }, Qt::QueuedConnection);
    return accepted ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_org_overte_phone_PhoneAccessibilityBridge_nativePerformAction(
        JNIEnv* env, jclass, jint identifier, jstring action, jstring content) {
    auto app = phoneApplication();
    if (!app) { return JNI_FALSE; }
    const auto operation = javaText(env, action);
    if (env->ExceptionCheck()) { return JNI_FALSE; }
    const auto text = javaText(env, content);
    if (env->ExceptionCheck() || (operation != "press" && operation != "focus" && operation != "set-text")
            || text.size() > 4096) { return JNI_FALSE; }
    const auto accepted = QMetaObject::invokeMethod(app, [identifier, operation, text] {
        if (AndroidHelper::instance().isLoadComplete()) { tree().action(identifier, operation, text); }
    }, Qt::QueuedConnection);
    return accepted ? JNI_TRUE : JNI_FALSE;
}
