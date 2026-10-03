// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "Node.h"
#include "SockAddr.h"
#include "udt/PacketHeaders.h"

// Browser peers expose only the audited agent protocol. Native process control,
// raw persistence, assignment deployment, server replies and future packet
// types remain unavailable even when they are unsourced or nonverified.
inline bool isBrowserPacketAllowed(PacketType type) {
    switch (type) {
        case PacketType::DomainConnectRequest:
        case PacketType::DomainConnectRequestPending:
        case PacketType::DomainListRequest:
        case PacketType::DomainDisconnectRequest:
        case PacketType::DomainServerPathQuery:
        case PacketType::Ping:
        case PacketType::PingReply:
        case PacketType::AvatarData:
        case PacketType::AvatarIdentity:
        case PacketType::AvatarQuery:
        case PacketType::SetAvatarTraits:
        case PacketType::BulkAvatarTraitsAck:
        case PacketType::RequestsDomainListData:
        case PacketType::NodeIgnoreRequest:
        case PacketType::NodeKickRequest:
        case PacketType::NodeMuteRequest:
        case PacketType::PerAvatarGainSet:
        case PacketType::NegotiateAudioFormat:
        case PacketType::MicrophoneAudioNoEcho:
        case PacketType::SilentAudioFrame:
        case PacketType::MessagesData:
        case PacketType::MessagesSubscribe:
        case PacketType::MessagesUnsubscribe:
        case PacketType::EntityQuery:
        case PacketType::BrowserEntityQuery:
        case PacketType::EntityScriptCallMethod:
        case PacketType::AssetMappingOperation:
        case PacketType::AssetGet:
            return true;
        default:
            return false;
    }
}

inline bool isPacketTransportAllowed(const SockAddr& sender, PacketType type) {
    return sender.getType() == SocketType::UDP
        || (sender.getType() == SocketType::WebRTC && isBrowserPacketAllowed(type));
}

// Keep the historical private-network fallback exclusively between native UDP
// endpoints. Any RTC involvement binds the packet to its exact current socket.
inline bool isPacketSourceAddressAllowed(const SockAddr& expected, const SockAddr& sender) {
    return ((sender.getType() == SocketType::UDP || sender.getType() == SocketType::WebRTC) && expected == sender)
        || (expected.getType() == SocketType::UDP && sender.getType() == SocketType::UDP
            && expected.hasPrivateAddress() && sender.hasPrivateAddress());
}

inline bool isBrowserPacketSourceNode(const Node* source) {
    if (!source) {
        return false;
    }
    const auto active = source->getActiveSocket();
    return (active && active->getType() == SocketType::WebRTC)
        || source->getPublicSocket().getType() == SocketType::WebRTC
        || source->getLocalSocket().getType() == SocketType::WebRTC;
}

inline bool isBrowserAgentPacketSource(const SockAddr& sender, const Node* source) {
    if (sender.getType() != SocketType::WebRTC || !source || source->getType() != NodeType::Agent) {
        return false;
    }
    if (const auto active = source->getActiveSocket()) {
        return *active == sender;
    }
    // An admitted browser may send its first authenticated PingReply before
    // the node socket is active. Only its advertised RTC endpoints are valid.
    return source->getPublicSocket() == sender || source->getLocalSocket() == sender;
}
