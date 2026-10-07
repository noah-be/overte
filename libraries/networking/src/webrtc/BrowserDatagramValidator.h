// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <array>
#include <cstdint>
#include <cstring>

#include "../BrowserPacketPolicy.h"
#include "../NLPacket.h"
#include "../udt/Constants.h"
#include "../udt/ControlPacket.h"

// Check the browser datagram before the native parser reads any header. This
// validates framing only; the native version, source, HMAC and permission
// checks still run afterwards. UDP does not use this transport boundary.
inline bool isBrowserDatagramValid(const char* data, qint64 size) {
    constexpr qint64 WORD_BYTES = sizeof(uint32_t);
    if (!data || size < WORD_BYTES || size > udt::MAX_PACKET_SIZE) {
        return false;
    }
    uint32_t header;
    std::memcpy(&header, data, sizeof(header));

    if (header & udt::CONTROL_BIT_MASK) {
        constexpr int TYPE_OFFSET = 8 * sizeof(udt::ControlPacket::Type);
        const uint32_t type = (header & ~udt::CONTROL_BIT_MASK) >> TYPE_OFFSET;
        // Control headers contain only their control bit and type. Unknown
        // types and the unused low bits must not reach ControlPacket::readType.
        if (type > udt::ControlPacket::HandshakeRequest ||
            header != (udt::CONTROL_BIT_MASK | (type << TYPE_OFFSET))) {
            return false;
        }
        if (type == udt::ControlPacket::HandshakeRequest) {
            return size == WORD_BYTES;
        }
        // ACK, Handshake and HandshakeACK all read one native SequenceNumber.
        if (size != WORD_BYTES + sizeof(udt::SequenceNumber)) {
            return false;
        }
        uint32_t sequenceNumber;
        std::memcpy(&sequenceNumber, data + WORD_BYTES, sizeof(sequenceNumber));
        return sequenceNumber <= static_cast<uint32_t>(udt::SequenceNumber::MAX);
    }

    const bool isPartOfMessage = header & udt::MESSAGE_BIT_MASK;
    // Native ordered PacketLists require reliability. Do not expose unsupported
    // unreliable ordered-message framing to native message reassembly.
    if (isPartOfMessage && !(header & udt::RELIABILITY_BIT_MASK)) {
        return false;
    }
    const auto dataHeaderBytes = udt::Packet::totalHeaderSize(isPartOfMessage);
    if (size < dataHeaderBytes + sizeof(PacketType) + sizeof(PacketVersion)) {
        return false;
    }

    // Native and SDK SendQueue retransmissions use all four obfuscation levels.
    // Only the type byte is needed here; do not modify/copy the packet. Keep the
    // keys identical to udt/Packet.cpp. Tests use actual Packet::obfuscate, so
    // native key/header drift causes the transport regression to fail.
    constexpr std::array<uint64_t, 4> KEYS {{
        0x0, 0x6362726973736574, 0x7362697261726461, 0x72687566666d616e
    }};
    const auto level = (header & udt::OBFUSCATION_LEVEL_MASK) >> udt::OBFUSCATION_LEVEL_OFFSET;
    uint8_t typeByte;
    uint8_t keyByte;
    std::memcpy(&typeByte, data + dataHeaderBytes, sizeof(typeByte));
    std::memcpy(&keyByte, &KEYS[level], sizeof(keyByte));
    const auto type = static_cast<PacketType>(typeByte ^ keyByte);
    if (!isBrowserPacketAllowed(type)) {
        return false;
    }
    return size >= NLPacket::totalHeaderSize(type, isPartOfMessage);
}
