// Modified in 2026 for the optional direct browser transport.
//
//  WebRTCSocket.cpp
//  libraries/networking/src/webrtc
//
//  Created by David Rowe on 21 Jun 2021.
//  Copyright 2021 Vircadia contributors.
//

#include "WebRTCSocket.h"

#if defined(WEBRTC_DATA_CHANNELS)

#include <QHostAddress>

#include "../NetworkLogging.h"
#include "../udt/Constants.h"


WebRTCSocket::WebRTCSocket(QObject* parent) :
    QObject(parent),
    _dataChannels(this)
{
    // Route signaling messages.
    connect(this, &WebRTCSocket::onSignalingMessage, &_dataChannels, &WebRTCDataChannels::onSignalingMessage);
    connect(&_dataChannels, &WebRTCDataChannels::signalingMessage, this, &WebRTCSocket::sendSignalingMessage);

    // Route received data channel messages.
    connect(&_dataChannels, &WebRTCDataChannels::dataMessage, this, &WebRTCSocket::onDataChannelReceivedMessage);
    connect(&_dataChannels, &WebRTCDataChannels::peerClosed, this, [this](const SockAddr& address) {
        for (auto it = _receivedQueue.begin(); it != _receivedQueue.end();) {
            if (it->first == address) {
                _receivedBytes -= it->second.size();
                it = _receivedQueue.erase(it);
            } else {
                ++it;
            }
        }
        emit peerClosed(address);
    });
}

WebRTCSocket::~WebRTCSocket() {
    // Member destruction would otherwise close peers after the receive queue
    // and error state have already been destroyed, while signals still target us.
    disconnect(&_dataChannels, nullptr, this, nullptr);
    _dataChannels.reset();
}

void WebRTCSocket::setSocketOption(QAbstractSocket::SocketOption option, const QVariant& value) {
    clearError();
    switch (option) {
    case QAbstractSocket::SocketOption::ReceiveBufferSizeSocketOption:
    case QAbstractSocket::SocketOption::SendBufferSizeSocketOption:
        // WebRTC doesn't provide access to setting these buffer sizes.
        break;
    default:
        setError(QAbstractSocket::SocketError::UnsupportedSocketOperationError, "Failed to set socket option");
        qCCritical(networking_webrtc) << "WebRTCSocket::setSocketOption() not implemented for option:" << option;
    }

}

QVariant WebRTCSocket::socketOption(QAbstractSocket::SocketOption option) {
    clearError();
    switch (option) {
    case QAbstractSocket::SocketOption::ReceiveBufferSizeSocketOption:
        // WebRTC doesn't provide access to the receive buffer size. Just use the default buffer size.
        return udt::WEBRTC_RECEIVE_BUFFER_SIZE_BYTES;
    case QAbstractSocket::SocketOption::SendBufferSizeSocketOption:
        // WebRTC doesn't provide access to the send buffer size though it's probably 16MB. Just use the default buffer size.
        return udt::WEBRTC_SEND_BUFFER_SIZE_BYTES;
    default:
        setError(QAbstractSocket::SocketError::UnsupportedSocketOperationError, "Failed to get socket option");
        qCCritical(networking_webrtc) << "WebRTCSocket::getSocketOption() not implemented for option:" << option;
    }

    return QVariant();
}

bool WebRTCSocket::bind(const QHostAddress& address, quint16 port, QAbstractSocket::BindMode mode) {
    // WebRTC data channels aren't bound to ports so just treat this as a successful operation.
    auto wasBound = _isBound.exchange(true);
    if (!wasBound) {
        emit stateChanged(_isBound ? QAbstractSocket::BoundState : QAbstractSocket::UnconnectedState);
    }
    return _isBound;
}

QAbstractSocket::SocketState WebRTCSocket::state() const {
    return _isBound ? QAbstractSocket::BoundState : QAbstractSocket::UnconnectedState;
}

void WebRTCSocket::abort() {
    _dataChannels.reset();
    _receivedQueue.clear();
    _receivedBytes = 0;
    if (_isBound.exchange(false)) {
        emit stateChanged(QAbstractSocket::UnconnectedState);
    }
}


qint64 WebRTCSocket::writeDatagram(const QByteArray& datagram, const SockAddr& destination) {
    clearError();
    if (_dataChannels.sendDataMessage(destination, datagram)) {
        return datagram.length();
    }
    setError(QAbstractSocket::SocketError::UnknownSocketError, "Failed to write datagram");
    return -1;
}

qint64 WebRTCSocket::bytesToWrite(const SockAddr& destination) const {
    return _dataChannels.getBufferedAmount(destination);
}


bool WebRTCSocket::hasPendingDatagrams() const {
    return _receivedQueue.length() > 0;
}

qint64 WebRTCSocket::pendingDatagramSize() const {
    if (_receivedQueue.length() > 0) {
        return _receivedQueue.head().second.length();
    }
    return -1;
}

qint64 WebRTCSocket::readDatagram(char* data, qint64 maxSize, QHostAddress* address, quint16* port) {
    clearError();
    if (maxSize < 0) {
        setError(QAbstractSocket::SocketError::UnsupportedSocketOperationError, "Invalid datagram buffer size");
        return -1;
    }
    if (_receivedQueue.length() > 0) {
        auto datagram = _receivedQueue.dequeue();
        _receivedBytes -= datagram.second.size();
        auto length = std::min((qint64)datagram.second.length(), maxSize);

        if (data) {
            memcpy(data, datagram.second.constData(), length);
        }

        if (address) {
            *address = datagram.first.getAddress();
        }

        if (port) {
            *port = datagram.first.getPort();
        }

        return length;
    }
    setError(QAbstractSocket::SocketError::UnknownSocketError, "Failed to read datagram");
    return -1;
}


QAbstractSocket::SocketError WebRTCSocket::error() const {
    QMutexLocker lock(&_errorMutex);
    return _lastErrorType;
}

QString WebRTCSocket::errorString() const {
    QMutexLocker lock(&_errorMutex);
    return _lastErrorString;
}


void WebRTCSocket::setError(QAbstractSocket::SocketError errorType, QString errorString) {
    QMutexLocker lock(&_errorMutex);
    _lastErrorType = errorType;
    _lastErrorString = errorString;
}

void WebRTCSocket::clearError() {
    QMutexLocker lock(&_errorMutex);
    _lastErrorType = QAbstractSocket::SocketError();
    _lastErrorString = QString();
}


void WebRTCSocket::onDataChannelReceivedMessage(const SockAddr& source, const QByteArray& message) {
    if (!_isBound || message.isEmpty() || message.size() > udt::MAX_PACKET_SIZE ||
        _receivedQueue.size() >= 4096 || _receivedBytes + message.size() > udt::WEBRTC_RECEIVE_BUFFER_SIZE_BYTES) {
        return;
    }
    _receivedQueue.enqueue(QPair<SockAddr, QByteArray>(source, message));
    _receivedBytes += message.size();
    emit readyRead();
}

#endif // WEBRTC_DATA_CHANNELS
