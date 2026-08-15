//
//  MacOSOnlineLoadingTelemetryTests.cpp
//  tests/shared/src
//
//  Copyright 2026 Overte e.V.
//  SPDX-License-Identifier: Apache-2.0
//

#include "MacOSOnlineLoadingTelemetryTests.h"

#include <QtCore/QCryptographicHash>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QList>
#include <QtCore/QUrl>

#include <MacOSOnlineLoadingTelemetry.h>
#include <shared/GlobalAppProperties.h>

namespace {

QStringList capturedMessages;

void captureMessage(QtMsgType, const QMessageLogContext&, const QString& message) {
    capturedMessages.append(message);
}

QJsonObject lastRecord() {
    const QString prefix = QStringLiteral("OVERTE_MACOS_ONLINE_NAV ");
    for (auto iterator = capturedMessages.crbegin(); iterator != capturedMessages.crend(); ++iterator) {
        const int prefixAt = iterator->indexOf(prefix);
        if (prefixAt >= 0) {
            return QJsonDocument::fromJson(iterator->mid(prefixAt + prefix.size()).toUtf8()).object();
        }
    }
    return {};
}

void configure(const QByteArray& navigationId = "c10-p1-cold") {
    qApp->setProperty(hifi::properties::TEST, QUrl::fromLocalFile(QStringLiteral("/tmp/test.js")));
    qputenv("OVERTE_MACOS_ONLINE_LOADING_NAVIGATION_ID", navigationId);
    qputenv("OVERTE_MACOS_ONLINE_LOADING_LOCATION_SHA256", QByteArray(64, 'b'));
}

void configureTarget(const QByteArray& target, const QByteArray& navigationId = "c10-p1-target") {
    configure(navigationId);
    qputenv(
        "OVERTE_MACOS_ONLINE_LOADING_LOCATION_SHA256",
        QCryptographicHash::hash(target, QCryptographicHash::Sha256).toHex());
}

} // namespace

QTEST_MAIN(MacOSOnlineLoadingTelemetryTests)

void MacOSOnlineLoadingTelemetryTests::cleanup() {
    qApp->setProperty(hifi::properties::TEST, QVariant());
    qunsetenv("OVERTE_MACOS_ONLINE_LOADING_NAVIGATION_ID");
    qunsetenv("OVERTE_MACOS_ONLINE_LOADING_LOCATION_SHA256");
    capturedMessages.clear();
}

void MacOSOnlineLoadingTelemetryTests::testRequiresExplicitTestGate() {
    qputenv("OVERTE_MACOS_ONLINE_LOADING_NAVIGATION_ID", "c10-p1-no-test");
    qputenv("OVERTE_MACOS_ONLINE_LOADING_LOCATION_SHA256", QByteArray(64, 'b'));
    QVERIFY(!macos::online_loading::enabled());
    QVERIFY(!macos::online_loading::recordOnce("url_accepted"));
}

void MacOSOnlineLoadingTelemetryTests::testRejectsUnsafeIdentity() {
    configure("unsafe host/token");
    QVERIFY(!macos::online_loading::enabled());
    QVERIFY(!macos::online_loading::recordOnce("url_accepted"));

    configure("c10-p1-bad-hash");
    qputenv("OVERTE_MACOS_ONLINE_LOADING_LOCATION_SHA256", "https://secret.invalid/");
    QVERIFY(!macos::online_loading::enabled());
    QVERIFY(!macos::online_loading::recordOnce("url_accepted"));
}

void MacOSOnlineLoadingTelemetryTests::testEmitsSanitizedMonotonicJSON() {
    configure("c10-p1-json");
    const auto previousHandler = qInstallMessageHandler(captureMessage);
    QVERIFY(macos::online_loading::recordOnce("url_accepted"));
    QVERIFY(macos::online_loading::recordOnce("domain_connected"));
    QVERIFY(macos::online_loading::recordOnce("entity_server_active", { { "resource_pending", 3 } }));
    qInstallMessageHandler(previousHandler);

    QCOMPARE(capturedMessages.size(), 3);
    const auto record = lastRecord();
    QCOMPARE(record.value("schema_version").toInt(), 1);
    QCOMPARE(record.value("navigation_id").toString(), QStringLiteral("c10-p1-json"));
    QCOMPARE(record.value("location_sha256").toString(), QString(64, 'b'));
    QCOMPARE(record.value("event").toString(), QStringLiteral("entity_server_active"));
    QCOMPARE(record.value("resource_pending").toInt(), 3);
    QVERIFY(record.value("monotonic_us").toDouble() > 0.0);
    QVERIFY(!capturedMessages.join('\n').contains(QStringLiteral("secret.invalid")));
}

void MacOSOnlineLoadingTelemetryTests::testRequiresStrictOrderAndMonotonicTime() {
    configure("c10-p1-order");
    const auto previousHandler = qInstallMessageHandler(captureMessage);
    QVERIFY(!macos::online_loading::recordOnceAt("domain_connected", 200));
    QVERIFY(macos::online_loading::recordOnceAt("url_accepted", 200));
    QVERIFY(!macos::online_loading::recordOnceAt("domain_connected", 199));
    QVERIFY(macos::online_loading::recordOnceAt("domain_connected", 201));
    QVERIFY(!macos::online_loading::recordOnceAt("entity_server_active", 202, {
        { "resource_pending", -1 },
    }));
    QVERIFY(macos::online_loading::recordOnceAt("entity_server_active", 202, {
        { "resource_loading", 2 },
        { "resource_pending", 1 },
    }));
    QVERIFY(!macos::online_loading::recordOnceAt("entity_server_active", 203));
    qInstallMessageHandler(previousHandler);

    QCOMPARE(capturedMessages.size(), 3);
    const auto record = lastRecord();
    QCOMPARE(record.value("event").toString(), QStringLiteral("entity_server_active"));
    QCOMPARE(record.value("monotonic_us").toDouble(), 202.0);
}

void MacOSOnlineLoadingTelemetryTests::testDeduplicatesPerNavigation() {
    configure("c10-p1-first");
    const auto previousHandler = qInstallMessageHandler(captureMessage);
    QVERIFY(!macos::online_loading::recordOnce("domain_connected"));
    QVERIFY(macos::online_loading::recordOnce("url_accepted"));
    QVERIFY(!macos::online_loading::recordOnce("url_accepted"));
    QVERIFY(macos::online_loading::hasRecorded("url_accepted"));

    qputenv("OVERTE_MACOS_ONLINE_LOADING_NAVIGATION_ID", "c10-p1-second");
    QVERIFY(!macos::online_loading::hasRecorded("url_accepted"));
    QVERIFY(macos::online_loading::recordOnce("url_accepted"));
    QVERIFY(!macos::online_loading::recordOnce("domain_connected", { { "unsafe_key", 1 } }));
    qInstallMessageHandler(previousHandler);

    QCOMPARE(capturedMessages.size(), 2);
    QCOMPARE(lastRecord().value("navigation_id").toString(), QStringLiteral("c10-p1-second"));
}

void MacOSOnlineLoadingTelemetryTests::testBeginsOnlyForExactTargetBytes() {
    const QByteArray target("hifi://overte_hub/benchmark");
    configureTarget(target);

    const auto previousHandler = qInstallMessageHandler(captureMessage);
    QVERIFY(!macos::online_loading::beginNavigation("hifi://another.invalid/benchmark"));
    QVERIFY(macos::online_loading::beginNavigation(target));
    QVERIFY(!macos::online_loading::beginNavigation(target));
    qInstallMessageHandler(previousHandler);

    QCOMPARE(capturedMessages.size(), 1);
    QCOMPARE(lastRecord().value("event").toString(), QStringLiteral("url_accepted"));
    QVERIFY(!capturedMessages.join('\n').contains(QString::fromUtf8(target)));
    QVERIFY(!capturedMessages.join('\n').contains(QStringLiteral("another.invalid")));
}

void MacOSOnlineLoadingTelemetryTests::testRejectsUnsafeTargets() {
    const QList<QByteArray> invalidTargets {
        "http://example.invalid/benchmark",
        "hifi:///missing-host",
        "hifi://user@example.invalid/benchmark",
        "hifi://user:password@example.invalid/benchmark",
        QByteArray("hifi://example.invalid/") + QByteArray(2048, 'x'),
        QByteArray::fromHex("686966693a2f2f6578616d706c652e696e76616c69642fff"),
    };
    const auto previousHandler = qInstallMessageHandler(captureMessage);
    for (int index = 0; index < invalidTargets.size(); ++index) {
        const auto& target = invalidTargets.at(index);
        configureTarget(target, QByteArray("c10-p1-invalid-") + QByteArray::number(index));
        QVERIFY(!macos::online_loading::beginNavigation(target));
    }
    qInstallMessageHandler(previousHandler);
    QVERIFY(capturedMessages.isEmpty());
}
