// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#include <jni.h>
#include <memory>
#include <QtAndroidExtras/QAndroidJniObject>
#include <QCoreApplication>
#include <QPointer>
#include <QTimer>
#include <DependencyManager.h>
#include <OffscreenUi.h>
#include <NativeWebViewItem.h>
#include "PhoneApplicationOwner.h"

extern "C" JNIEXPORT void JNICALL Java_org_overte_phone_PhoneInterfaceActivity_nativePrepareWeb(
        JNIEnv* env, jclass, jstring cacheDirectory) {
    if (!cacheDirectory) return;
    const auto* text = env->GetStringChars(cacheDirectory, nullptr); if (!text) return;
    const auto cache = QString::fromUtf16(reinterpret_cast<const ushort*>(text), env->GetStringLength(cacheDirectory));
    env->ReleaseStringChars(cacheDirectory, text);
    auto* application = phoneApplication(); if (!application) return;
    QMetaObject::invokeMethod(application, [application, cache] {
        NativeWebViewItem::setPackagedResourceRoots({ cache + "/scripts", "qrc:/html", "qrc:/scripts" });
        const auto publishSize = [] {
            const auto size = DependencyManager::get<OffscreenUi>()->size();
            if (size.width() > 1 && size.height() > 1)
                QAndroidJniObject::callStaticMethod<void>("org/overte/phone/PhoneInterfaceActivity", "onWebSceneSize", "(II)V", size.width(), size.height());
        };
        publishSize();
        static QPointer<QTimer> monitor;
        if (monitor) return;
        monitor = new QTimer(application);
        auto dimensions = std::make_shared<QSize>();
        QObject::connect(monitor, &QTimer::timeout, application, [dimensions] {
            const auto ui = DependencyManager::get<OffscreenUi>();
            const auto size = ui->size(); if (size.width() <= 1 || size.height() <= 1 || size == *dimensions) return;
            *dimensions = size;
            QAndroidJniObject::callStaticMethod<void>("org/overte/phone/PhoneInterfaceActivity", "onWebSceneSize", "(II)V", size.width(), size.height());
        });
        monitor->start(100);
    }, Qt::QueuedConnection);
}
