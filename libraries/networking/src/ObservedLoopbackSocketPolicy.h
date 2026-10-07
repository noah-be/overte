// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "Node.h"

// An explicitly bound loopback server can reach a local wildcard client at
// its advertised LAN address, but the client's replies to the server's
// loopback address come from loopback. Native UDT must use that same observed
// endpoint for its outgoing reliable queue and incoming handshake/ACK state.
// The caller supplies a current registered peer after packet verification.
inline bool shouldUseObservedNativeLoopbackSocket(const QHostAddress& nativeBindAddress,
                                                 const SockAddr& sender, const Node* peer,
                                                 const SockAddr& advertisedSocket) {
    if (!peer || !nativeBindAddress.isLoopback() || sender.getType() != SocketType::UDP ||
        !sender.getAddress().isLoopback() || sender.getPort() == 0 ||
        advertisedSocket.getType() != SocketType::UDP || advertisedSocket == sender ||
        advertisedSocket.getPort() != sender.getPort() ||
        peer->getPublicSocket().getType() != SocketType::UDP ||
        peer->getLocalSocket().getType() != SocketType::UDP) {
        return false;
    }
    const auto active = peer->getActiveSocket();
    return !active || active->getType() == SocketType::UDP;
}
