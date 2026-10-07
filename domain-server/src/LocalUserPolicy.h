// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <SockAddr.h>
#include <NodeType.h>

// Assignment requests deploy native server processes and use the separate
// native subnet allowlist. A browser endpoint never belongs to that plane.
inline bool isNativeAssignmentTransport(const SockAddr& sender) {
    return sender.getType() == SocketType::UDP;
}

// A browser joins through the normal agent authentication and permission path.
// Reject server roles before inspecting a pending native assignment UUID.
inline bool isNodeConnectTransportAllowed(const SockAddr& sender, NodeType_t nodeType) {
    return sender.getType() == SocketType::UDP
        || (sender.getType() == SocketType::WebRTC && nodeType == NodeType::Agent);
}

// A browser's transport address describes the DataChannel endpoint, not a
// privileged native client on this machine. Keep normal authentication and
// anonymous/group permissions for WebRTC, including loopback-hosted browsers.
inline bool isLocalUserConnection(const SockAddr& sender, const QHostAddress& localAddress) {
    return sender.getType() == SocketType::UDP &&
        (sender.getAddress() == localAddress || sender.getAddress() == QHostAddress::LocalHost);
}
