// SPDX-License-Identifier: Apache-2.0
#include "PicoAccessibilityTree.h"
#include <jni.h>
#include <QtAndroidExtras/QAndroidJniObject>
#include <QAccessible>
#include <QCoreApplication>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMetaObject>
#include <QPointer>
#include <QQuickItem>
#include <QTimer>
#include <QFileInfo>
#include <shared/GlobalAppProperties.h>
#include <DependencyManager.h>
#include <OffscreenUi.h>
#include <scripting/HMDScriptingInterface.h>

namespace {
PicoAccessibilityTree& tree() { static PicoAccessibilityTree value; return value; }
QPointer<QQuickItem> launcher;
bool loading { false };
void prepareControls() {
    if (!DependencyManager::isSet<OffscreenUi>() || !DependencyManager::isSet<HMDScriptingInterface>()) { return; }
    const auto ui = DependencyManager::get<OffscreenUi>();
    if (launcher) {
        launcher->setProperty("tabletOpen", DependencyManager::get<HMDScriptingInterface>()->getShouldShowTablet());
    } else if (!loading && ui->getRootItem()) {
        loading = true;
        ui->load(QUrl("qrc:/qml/hifi/PicoTabletAccessibility.qml"), hifi::qml::QmlContextObjectCallback([](QQmlContext*, QQuickItem* created) {
            launcher = created;
            loading = false;
        }));
    }
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
Java_org_overte_pico_PicoAccessibilityBridge_nativeRequestFrame(
        JNIEnv*, jclass, jobject receiver, jint width, jint height, jint generation) {
    auto app = QCoreApplication::instance();
    if (!app || !receiver || width <= 0 || height <= 0 || width > 16384 || height > 16384) { return JNI_FALSE; }
    QAndroidJniObject sink(receiver);
    const bool accepted = QMetaObject::invokeMethod(app, [sink, width, height, generation] {
        QJsonObject frame { {"schemaVersion", 1}, {"ready", false} };
        if (DependencyManager::isSet<OffscreenUi>()) {
            QAccessible::setActive(true);
            prepareControls();
            frame = tree().snapshot(DependencyManager::get<OffscreenUi>()->getRootItem(), QSize(width, height));
        }
        const QUrl probe = QCoreApplication::instance()->property(hifi::properties::TEST).toUrl();
        const QString expected = QFileInfo(QStringLiteral(
            "/data/user/0/org.overte.pico/files/overte-e2e/overte_e2e_probe.js")).canonicalFilePath();
        frame.insert("controlledDebugProbe", probe.isLocalFile() && !expected.isEmpty()
            && QFileInfo(probe.toLocalFile()).canonicalFilePath() == expected);
        const auto encoded = QAndroidJniObject::fromString(QString::fromUtf8(QJsonDocument(frame).toJson(QJsonDocument::Compact)));
        sink.callMethod<void>("acceptFrame", "(Ljava/lang/String;I)V", encoded.object<jstring>(), generation);
    }, Qt::QueuedConnection);
    return accepted ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_org_overte_pico_PicoAccessibilityBridge_nativePerformAction(
        JNIEnv* env, jclass, jint identifier, jstring action, jstring content) {
    auto app = QCoreApplication::instance();
    if (!app) { return JNI_FALSE; }
    const auto operation = javaText(env, action);
    if (env->ExceptionCheck()) { return JNI_FALSE; }
    const auto text = javaText(env, content);
    if (env->ExceptionCheck() || (operation != "press" && operation != "focus" && operation != "set-text")
            || text.size() > 4096) { return JNI_FALSE; }
    const bool accepted = QMetaObject::invokeMethod(app, [identifier, operation, text] {
        tree().action(identifier, operation, text);
    }, Qt::QueuedConnection);
    return accepted ? JNI_TRUE : JNI_FALSE;
}
