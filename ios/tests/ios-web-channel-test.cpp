// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "../web/IOSWebChannel.h"
#include <QCoreApplication>
#include <QFile>
#include <QJsonDocument>
#include <QProcess>
#include <QTemporaryDir>
#include <cassert>
#include <iostream>

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    assert(argc == 3);
    using overte::ios::IOSWebChannel;
    IOSWebChannel channel;
    const QUrl origin(QStringLiteral("https://example.invalid/app"));
    bool live = true;
    channel.reset([&](const QUrl& frame, bool mainFrame, std::size_t bytes) {
        return live && mainFrame && frame == origin && bytes <= 64 * 1024;
    });
    QTemporaryDir directory;
    assert(directory.isValid());
    QFile native(directory.filePath("native.js")); assert(native.open(QFile::WriteOnly));
    native.write(IOSWebChannel::transportJavaScript(QStringLiteral("test-document")).toUtf8()); native.close();
    QFile qt(QStringLiteral(":/qtwebchannel/qwebchannel.js")); assert(qt.open(QFile::ReadOnly));
    QFile resource(directory.filePath("qwebchannel.js")); assert(resource.open(QFile::WriteOnly));
    resource.write(qt.readAll()); resource.close();
    QProcess javascript;
    QByteArray incoming;
    unsigned events = 0;
    bool complete = false;
    unsigned handshakes = 0;
    QObject::connect(&channel, &IOSWebChannel::bridgeInitialized, [&] { ++handshakes; });
    QObject::connect(&channel, &IOSWebChannel::sendToPage, [&](const QString& envelope) {
        javascript.write(envelope.toUtf8() + '\n');
    });
    QObject::connect(&channel, &IOSWebChannel::webEventReceived, [&](const QVariant& event) {
        ++events;
        if (events == 1) {
            assert(event.toString() == QStringLiteral("queued before init"));
            channel.publishScriptEvent(QVariantMap {{ QStringLiteral("text"), QString::fromUtf8("quote\" newline\n ü") }});
        } else {
            assert(event.toMap().value(QStringLiteral("text")).toString() == QString::fromUtf8("quote\" newline\n ü"));
            complete = true;
        }
    });
    javascript.start(QStringLiteral("node"), { QString::fromLocal8Bit(argv[1]), directory.filePath("native.js"),
        directory.filePath("qwebchannel.js"), QString::fromLocal8Bit(argv[2]) });
    assert(javascript.waitForStarted(5000));
    for (unsigned iteration = 0; iteration < 100 && !complete; ++iteration) {
        javascript.waitForReadyRead(50);
        incoming += javascript.readAllStandardOutput();
        while (incoming.contains('\n')) {
            const auto end = incoming.indexOf('\n');
            const auto line = incoming.left(end); incoming.remove(0, end + 1);
            assert(channel.receiveEnvelope(QString::fromUtf8(line), origin, true));
        }
        app.processEvents();
    }
    if (!complete) { std::cerr << javascript.readAllStandardError().constData(); }
    assert(complete && events == 2 && handshakes == 1);
    // Native origin, main-frame, lifecycle and size checks precede Qt dispatch.
    const QString init = QStringLiteral("{\"type\":3,\"id\":100}");
    assert(!channel.receiveEnvelope(init, QUrl("https://other.invalid/"), true));
    assert(!channel.receiveEnvelope(init, origin, false));
    assert(!channel.receiveEnvelope(QString(65537, QLatin1Char('x')), origin, true));
    assert(!channel.receiveEnvelope(QStringLiteral("not JSON"), origin, true));
    assert(!channel.receiveEnvelope(QStringLiteral("{\"type\":9,\"object\":\"eventBridge\",\"property\":0,\"value\":\"changed\"}"), origin, true));
    assert(!channel.receiveEnvelope(QStringLiteral("{\"type\":7,\"object\":\"eventBridge\",\"signal\":0}"), origin, true));
    assert(!channel.receiveEnvelope(QStringLiteral("{\"type\":6,\"object\":\"ApplicationInterface\",\"method\":0}"), origin, true));
    assert(!channel.receiveEnvelope(QStringLiteral("{\"type\":6,\"object\":\"eventBridge\",\"method\":\"deleteLater\"}"), origin, true));
    live = false;
    assert(!channel.receiveEnvelope(init, origin, true));
    channel.reset();
    assert(!channel.receiveEnvelope(init, origin, true));
    // A real dispatched page event can synchronously close the bridge. Its
    // dispatch objects survive the invocation, but no later event is admitted.
    channel.reset([&](const QUrl&, bool, std::size_t) { return true; });
    QObject::disconnect(&channel, &IOSWebChannel::webEventReceived, nullptr, nullptr);
    bool resetDuringInvocation = false;
    QObject::connect(&channel, &IOSWebChannel::webEventReceived, [&] { resetDuringInvocation = true; channel.reset(); });
    assert(channel.receiveEnvelope(init, origin, true));
    overte::ios::IOSPageEventBridge bridge;
    const auto invocation = QStringLiteral("{\"type\":6,\"id\":101,\"object\":\"eventBridge\",\"method\":%1,\"args\":[\"close\"]}")
        .arg(bridge.metaObject()->indexOfMethod("emitWebEvent(QVariant)"));
    assert(channel.receiveEnvelope(invocation, origin, true));
    assert(resetDuringInvocation);
    assert(!channel.receiveEnvelope(init, origin, true));
    javascript.terminate(); javascript.waitForFinished(5000);
    std::cout << "PASS actual Qt WebChannel + shipped Overte bootstrap, bidirectional QVariant events and native envelope gates\n";
}
