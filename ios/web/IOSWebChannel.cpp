// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "IOSWebChannel.h"
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonParseError>

namespace overte::ios {
IOSWebChannel::IOSWebChannel(QObject* parent) : QObject(parent) {}

void IOSWebChannel::reset(Gate gate) {
    _gate = {};
    if (_receiving) {
        // A script may close or replace its page in an emitWebEvent handler.
        // Revoke immediately, then destroy Qt's dispatch objects after return.
        _resetPending = true; _pendingGate = std::move(gate); return;
    }
    _initializing = false; _initialized = false;
    _channel.reset(); // Tear down old pending updates before bridge/transport.
    _bridge.reset();
    _transport.reset();
    if (!gate) { return; }
    _gate = std::move(gate);
    _bridge = std::make_unique<IOSPageEventBridge>();
    _transport = std::make_unique<IOSWebTransport>();
    _channel = std::make_unique<QWebChannel>();
    _transport->sender = [this](const QJsonObject& message) {
        emit sendToPage(QString::fromUtf8(QJsonDocument(message).toJson(QJsonDocument::Compact)));
    };
    connect(_bridge.get(), &IOSPageEventBridge::webEventReceived, this, &IOSWebChannel::webEventReceived);
    _channel->registerObject(QStringLiteral("eventBridge"), _bridge.get());
    _channel->connectTo(_transport.get());
}

bool IOSWebChannel::receiveEnvelope(const QString& envelope, const QUrl& frame, bool mainFrame) {
    const auto utf8 = envelope.toUtf8();
    if (!_gate || !_transport || !_gate(frame, mainFrame, static_cast<std::size_t>(utf8.size()))) { return false; }
    QJsonParseError error;
    const auto document = QJsonDocument::fromJson(utf8, &error);
    if (error.error != QJsonParseError::NoError || !document.isObject()) { return false; }
    const auto message = document.object();
    const auto typeValue = message.value(QStringLiteral("type"));
    const auto type = typeValue.toInt(-1);
    if (!typeValue.isDouble() || typeValue.toDouble() != type ||
            (type != 3 && type != 4 && type != 6 && type != 7 && type != 8)) { return false; }
    if (type == 6 || type == 7 || type == 8) {
        if (message.value(QStringLiteral("object")).toString() != QStringLiteral("eventBridge")) { return false; }
    }
    if (type == 7 || type == 8) {
        const auto signal = message.value(QStringLiteral("signal"));
        const int allowed = _bridge->metaObject()->indexOfSignal("scriptEventReceived(QVariant)");
        if (!signal.isDouble() || signal.toDouble(-1) != allowed) { return false; }
    }
    // QObject's inherited slots (e.g. deleteLater) must never be callable by a
    // web document. Qt owns protocol processing; bound its method invocation to
    // the one page->script operation that this isolated bridge intentionally exports.
    if (type == 6) {
        const auto method = message.value(QStringLiteral("method"));
        const int allowed = _bridge->metaObject()->indexOfMethod("emitWebEvent(QVariant)");
        if ((method.isDouble() && method.toDouble(-1) != allowed) ||
                (method.isString() && method.toString() != QStringLiteral("emitWebEvent") &&
                 method.toString() != QStringLiteral("emitWebEvent(QVariant)")) ||
                (!method.isDouble() && !method.isString())) { return false; }
    }
    if (type == 3) { _initializing = true; }
    _receiving = true;
    _transport->receive(message);
    _receiving = false;
    if (_resetPending) {
        _resetPending = false;
        reset(std::move(_pendingGate));
        return true;
    }
    if (type == 4 && _initializing && !_initialized) { _initialized = true; emit bridgeInitialized(); }
    return true;
}

void IOSWebChannel::publishScriptEvent(const QVariant& message) {
    if (_bridge) { emit _bridge->scriptEventReceived(message); }
}

QString IOSWebChannel::transportJavaScript(const QString& documentNonce) {
    // qwebchannel.js and Overte's createGlobalEventBridge.js follow this shim.
    // Both remain the actual shared implementation, not a replacement protocol.
    const auto nonce = QString::fromUtf8(QJsonDocument(QJsonArray { documentNonce }).toJson(QJsonDocument::Compact));
    return QStringLiteral(R"JS(
(function (identity) {
    "use strict";
    window.qt = {webChannelTransport: {
        document: identity[0],
        send: function (message) {
            if (typeof message === "string") window.webkit.messageHandlers.overteWebChannel.postMessage({document:identity[0],envelope:message});
        },
        onmessage: null
    }};
})(%1);
)JS").arg(nonce);
}
} // namespace overte::ios
