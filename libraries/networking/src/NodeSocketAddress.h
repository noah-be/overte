// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <QHostAddress>
#include <QString>

// Native node sockets currently use IPv4. An empty setting preserves their
// historical bind; malformed or IPv6 values must never broaden that bind.
inline QHostAddress nodeUdpBindAddress(const QString& setting) {
    if (setting.isEmpty()) {
        return QHostAddress::AnyIPv4;
    }
    const QHostAddress address(setting);
    return address.protocol() == QAbstractSocket::IPv4Protocol ? address : QHostAddress();
}

// The assignment monitor is a local sibling process. When its node socket is
// bound explicitly, child status packets must target that same interface.
inline QHostAddress nodeMonitorAddress(const QString& setting) {
    const auto address = nodeUdpBindAddress(setting);
    return address == QHostAddress::AnyIPv4 ? QHostAddress(QHostAddress::LocalHost) : address;
}
