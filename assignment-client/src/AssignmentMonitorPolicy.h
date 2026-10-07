// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <SockAddr.h>

// Child status is also unsourced and unverified. A configured native bind can
// select another local interface; RTC loopback peers are never child processes.
inline bool isAssignmentChildStatusSender(const SockAddr& sender, const QHostAddress& nativeBindAddress) {
    if (sender.getType() != SocketType::UDP || sender.getPort() == 0) {
        return false;
    }
    if (sender.getAddress() == QHostAddress::LocalHost
        || sender.getAddress() == QHostAddress::LocalHostIPv6) {
        return true;
    }
    return !nativeBindAddress.isNull() && nativeBindAddress != QHostAddress::AnyIPv4
        && sender.getAddress() == nativeBindAddress;
}

// StopNode is unsourced and unverified. Preserve native localhost control and
// the configured sibling monitor endpoint without granting it to RTC guests.
inline bool isAssignmentMonitorStopSender(const SockAddr& sender, const SockAddr& monitor) {
    if (sender.getType() != SocketType::UDP) {
        return false;
    }
    if (sender.getAddress() == QHostAddress::LocalHost
        || sender.getAddress() == QHostAddress::LocalHostIPv6) {
        return true;
    }
    return monitor.getType() == SocketType::UDP && !monitor.getAddress().isNull()
        && monitor.getPort() != 0 && sender == monitor;
}
