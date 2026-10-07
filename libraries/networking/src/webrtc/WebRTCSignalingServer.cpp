// Modified in 2026 for the optional direct browser transport.
//
//  WebRTCSignalingServer.cpp
//  libraries/networking/src/webrtc
//
//  Created by David Rowe on 16 May 2021.
//  Copyright 2021 Vircadia contributors.
//

#include "WebRTCSignalingServer.h"

#if defined(WEBRTC_DATA_CHANNELS)

#include <QSslKey>
#include <QtCore>
#include <QWebSocket>

#include <BuildInfo.h>
#include <PathUtils.h>

#include "../NetworkLogging.h"
#include "../NodeType.h"


const int WEBRTC_SOCKET_CHECK_INTERVAL_IN_MS = 30000;
namespace {
constexpr int MAX_SIGNALING_CLIENTS = 256;
constexpr int MAX_SIGNALING_BYTES = 65536;
constexpr int MAX_SIGNALS_PER_SECOND = 128;
constexpr qint64 MAX_SIGNALING_OUTBOUND_BYTES = 1048576;

QString socketID(const QWebSocket* socket) {
    return socket->peerAddress().toString() + ":" + QString::number(socket->peerPort());
}

bool validTarget(const QString& target) {
    if (target.size() != 1) {
        return false;
    }
    const auto type = NodeType::fromChar(target.front());
    return type == NodeType::DomainServer || type == NodeType::EntityServer || type == NodeType::AvatarMixer ||
        type == NodeType::AudioMixer || type == NodeType::AssetServer || type == NodeType::MessagesMixer ||
        type == NodeType::EntityScriptServer;
}
} // namespace

WebRTCSignalingServer::WebRTCSignalingServer(QObject* parent, bool isWSSEnabled) :
    QObject(parent)
{
    if (isWSSEnabled) {
        _webSocketServer = (new QWebSocketServer(QStringLiteral("WebRTC Signaling Server"), QWebSocketServer::SecureMode,
            this));

        auto dsDirPath = PathUtils::getAppLocalDataPath();
        const QString KEY_FILENAME = "overte-cert.key";
        const QString CRT_FILENAME = "overte-cert.crt";
        const QString CA_CRT_FILENAME = "overte-cert-ca.crt";
        qCDebug(networking_webrtc) << "WebSocket WSS key file:" << dsDirPath + KEY_FILENAME;
        qCDebug(networking_webrtc) << "WebSocket WSS cert file:" << dsDirPath + CRT_FILENAME;
        qCDebug(networking_webrtc) << "WebSocket WSS CA cert file:" << dsDirPath + CA_CRT_FILENAME;

        QFile sslCaFile(dsDirPath + CA_CRT_FILENAME);
        sslCaFile.open(QIODevice::ReadOnly);
        QSslCertificate sslCaCertificate(&sslCaFile, QSsl::Pem);
        sslCaFile.close();

        QSslConfiguration sslConfiguration;
        QFile sslCrtFile(dsDirPath + CRT_FILENAME);
        sslCrtFile.open(QIODevice::ReadOnly);
        QSslCertificate sslCertificate(&sslCrtFile, QSsl::Pem);
        sslCrtFile.close();

        QFile sslKeyFile(dsDirPath + KEY_FILENAME);
        sslKeyFile.open(QIODevice::ReadOnly);
        QSslKey sslKey(&sslKeyFile, QSsl::Rsa, QSsl::Pem);
        sslKeyFile.close();

        if (!sslCaCertificate.isNull() && !sslKey.isNull() && !sslCertificate.isNull()) {
            sslConfiguration.setPeerVerifyMode(QSslSocket::VerifyNone);
            sslConfiguration.addCaCertificate(sslCaCertificate);
            sslConfiguration.setLocalCertificate(sslCertificate);
            sslConfiguration.setPrivateKey(sslKey);
            _webSocketServer->setSslConfiguration(sslConfiguration);
            qCDebug(networking_webrtc) << "WebSocket SSL mode enabled:"
                << (_webSocketServer->secureMode() == QWebSocketServer::SecureMode);
        } else {
            qCWarning(networking_webrtc) << "Error creating WebSocket SSL key.";
        }

    } else {
        _webSocketServer = (new QWebSocketServer(QStringLiteral("WebRTC Signaling Server"), QWebSocketServer::NonSecureMode,
            this));
    }
    _webSocketServer->setMaxPendingConnections(MAX_SIGNALING_CLIENTS);
    _webSocketServer->setHandshakeTimeout(10000);
    connect(_webSocketServer, &QWebSocketServer::newConnection, this, &WebRTCSignalingServer::newWebSocketConnection);

    // Automatically recover from network interruptions.
    _isWebSocketServerListeningTimer = new QTimer(this);
    connect(_isWebSocketServerListeningTimer, &QTimer::timeout, this, &WebRTCSignalingServer::checkWebSocketServerIsListening);
    _isWebSocketServerListeningTimer->start(WEBRTC_SOCKET_CHECK_INTERVAL_IN_MS);
}

bool WebRTCSignalingServer::bind(const QHostAddress& address, quint16 port) {
    _address = address;
    _port = port;
    auto success = _webSocketServer->listen(_address, _port);
    if (!success) {
        qCWarning(networking_webrtc) << "Failed to open WebSocket for WebRTC signaling.";
    }
    return success;
}

void WebRTCSignalingServer::checkWebSocketServerIsListening() {
    if (!_webSocketServer->isListening()) {
        qCWarning(networking_webrtc) << "WebSocket on port " << QString::number(_port) << " is no longer listening";
        const auto sockets = _webSockets.values();
        for (auto socket : sockets) {
            socket->close(QWebSocketProtocol::CloseCodeGoingAway, "Signaling server restarted");
        }
        _webSocketServer->listen(_address, _port);
    }
}

void WebRTCSignalingServer::webSocketTextMessageReceived(const QString& message) {
    auto source = qobject_cast<QWebSocket*>(sender());
    if (source && _webSockets.value(socketID(source)) == source) {
        const auto now = QDateTime::currentMSecsSinceEpoch();
        auto window = source->property("overteSignalWindow").toLongLong();
        auto count = source->property("overteSignalCount").toInt();
        if (now - window >= 1000) {
            source->setProperty("overteSignalWindow", now);
            count = 0;
        }
        source->setProperty("overteSignalCount", count + 1);
        if (count >= MAX_SIGNALS_PER_SECOND || message.toUtf8().size() > MAX_SIGNALING_BYTES) {
            source->close(QWebSocketProtocol::CloseCodePolicyViolated, "Signaling limit exceeded");
            return;
        }
        QJsonParseError error;
        const auto document = QJsonDocument::fromJson(message.toUtf8(), &error);
        QJsonObject json = document.object();
        const auto target = json.value("to").toString();
        if (error.error != QJsonParseError::NoError || !document.isObject() || !validTarget(target) ||
            (!json.value("data").isObject() && !json.contains("echo"))) {
            source->close(QWebSocketProtocol::CloseCodePolicyViolated, "Invalid signaling message");
            return;
        }
        // All sender identity is assigned by this connection, never the browser.
        json.insert("from", socketID(source));
        json.insert("session", source->property("overteSignalSession").toString());
        _targets[socketID(source)].insert(target);
        // WEBRTC TODO: Move domain server echoing into domain server.
        if (json.keys().contains("echo") && json.value("to").toString() == QString(QChar(NodeType::DomainServer))) {
            // Domain server echo request - echo message back to sender.
            json.insert("to", socketID(source));
            json.insert("from", QString(QChar(NodeType::DomainServer)));
            sendMessage(json);
        } else {
            // WebRTC message or assignment client echo request. (Send both to target.)
            emit messageReceived(json);
        }
    } else {
        qCWarning(networking_webrtc) << "Failed to find WebSocket for incoming WebRTC signaling message.";
    }
}

void WebRTCSignalingServer::sendMessage(const QJsonObject& message) {
    auto destinationAddress = message.value("to").toString();
    auto socket = _webSockets.value(destinationAddress);
    if (socket && message.value("session").toString() == socket->property("overteSignalSession").toString()) {
        const auto payload = QJsonDocument(message).toJson(QJsonDocument::Compact);
        if (payload.size() > MAX_SIGNALING_BYTES || socket->bytesToWrite() + payload.size() > MAX_SIGNALING_OUTBOUND_BYTES) {
            socket->close(QWebSocketProtocol::CloseCodePolicyViolated, "Signaling buffer limit exceeded");
            return;
        }
        socket->sendTextMessage(QString::fromUtf8(payload));
    }
}

void WebRTCSignalingServer::webSocketDisconnected() {
    auto source = qobject_cast<QWebSocket*>(sender());
    if (source) {
        auto address = socketID(source);
        if (_webSockets.value(address) == source) {
            _webSockets.remove(address);
            // Close DS and AC peers through the same trusted server routing.
            const auto session = source->property("overteSignalSession").toString();
            for (const auto& target : _targets.take(address)) {
                emit messageReceived({ { "from", address }, { "to", target }, { "session", session },
                                       { "data", QJsonObject { { "close", true } } } });
            }
            emit sessionClosed(SockAddr(SocketType::WebRTC, source->peerAddress(), source->peerPort()));
        }
        source->deleteLater();
    }
}

void WebRTCSignalingServer::newWebSocketConnection() {
    auto webSocket = _webSocketServer->nextPendingConnection();
    if (!webSocket) {
        return;
    }
    auto webSocketAddress = socketID(webSocket);
    if (_webSockets.size() >= MAX_SIGNALING_CLIENTS || _webSockets.contains(webSocketAddress)) {
        webSocket->close(QWebSocketProtocol::CloseCodePolicyViolated, "Signaling capacity exceeded");
        webSocket->deleteLater();
        return;
    }
    webSocket->setMaxAllowedIncomingFrameSize(MAX_SIGNALING_BYTES);
    webSocket->setMaxAllowedIncomingMessageSize(MAX_SIGNALING_BYTES);
    webSocket->setProperty("overteSignalSession", QUuid::createUuid().toString(QUuid::WithoutBraces));
    webSocket->setProperty("overteSignalWindow", QDateTime::currentMSecsSinceEpoch());
    webSocket->setProperty("overteSignalCount", 0);
    connect(webSocket, &QWebSocket::textMessageReceived, this, &WebRTCSignalingServer::webSocketTextMessageReceived);
    connect(webSocket, &QWebSocket::binaryMessageReceived, this, [webSocket] {
        webSocket->close(QWebSocketProtocol::CloseCodeDatatypeNotSupported, "Signaling requires JSON text");
    });
    connect(webSocket, &QWebSocket::disconnected, this, &WebRTCSignalingServer::webSocketDisconnected);
    _webSockets.insert(webSocketAddress, webSocket);
}

#endif // WEBRTC_DATA_CHANNELS
