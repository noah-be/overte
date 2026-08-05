//
//  InjectedAudioStream.cpp
//  libraries/audio/src
//
//  Created by Stephen Birarda on 6/5/13.
//  Copyright 2013 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "InjectedAudioStream.h"

#include <cmath>
#include <cstring>

#include <QtCore/QDataStream>
#include <QtCore/qdebug.h>

#include <udt/PacketHeaders.h>
#include <UUID.h>

#include "AudioHelpers.h"

InjectedAudioStream::InjectedAudioStream(const QUuid& streamIdentifier, bool isStereo, int numStaticJitterFrames) :
    PositionalAudioStream(PositionalAudioStream::Injector, isStereo, numStaticJitterFrames),
    _streamIdentifier(streamIdentifier),
    _radius(0.0f),
    _attenuationRatio(0) {} 

int InjectedAudioStream::parseStreamProperties(PacketType type,
                                               const QByteArray& packetAfterSeqNum,
                                               int& numAudioSamples) {

    const int positionalDataSize = sizeof(_position) + sizeof(_orientation) +
        sizeof(_avatarBoundingBoxCorner) + sizeof(_avatarBoundingBoxScale);
    // QDataStream uses double precision for floating point values by default, including values read into float.
    const int serializedRadiusSize = sizeof(double);
    const int minimumPropertySize = NUM_BYTES_RFC4122_UUID + sizeof(quint8) + sizeof(LoopbackFlag) +
        positionalDataSize + serializedRadiusSize + sizeof(quint8) + sizeof(quint8);
    if (packetAfterSeqNum.size() < minimumPropertySize) {
        return -1;
    }

    // setup a data stream to read from this packet
    QDataStream packetStream(packetAfterSeqNum);

    // skip the stream identifier
    packetStream.skipRawData(NUM_BYTES_RFC4122_UUID);
    
    // read the channel flag
    quint8 isStereoFlag { 0 };
    packetStream >> isStereoFlag;
    if (isStereoFlag > 1) {
        return -1;
    }
    const bool isStereo = isStereoFlag == 1;

    // pull the loopback flag and set our boolean
    LoopbackFlag shouldLoopback { 0 };
    packetStream >> shouldLoopback;
    if (shouldLoopback > 1) {
        return -1;
    }

    const int positionalDataOffset = packetStream.device()->pos();
    if (packetStream.skipRawData(positionalDataSize) != positionalDataSize) {
        return -1;
    }

    // pull out the radius for this injected source - if it's zero this is a point source
    float radius { 0.0f };
    packetStream >> radius;
    if (!std::isfinite(radius) || radius < 0.0f) {
        return -1;
    }

    quint8 attenuationByte = 0;
    packetStream >> attenuationByte;

    quint8 ignorePenumbraFlag { 0 };
    packetStream >> ignorePenumbraFlag;
    if (packetStream.status() != QDataStream::Ok || ignorePenumbraFlag > 1) {
        return -1;
    }

    // Apply properties only after the complete fixed header has been validated.
    const int positionalBytes = parsePositionalData(packetAfterSeqNum.mid(positionalDataOffset, positionalDataSize));
    if (positionalBytes != positionalDataSize) {
        return -1;
    }

    if (isStereo != _isStereo) {
        _ringBuffer.resizeForFrameSize(isStereo
                                       ? AudioConstants::NETWORK_FRAME_SAMPLES_STEREO
                                       : AudioConstants::NETWORK_FRAME_SAMPLES_PER_CHANNEL);
        _isStereo = isStereo;
    }
    _shouldLoopbackForNode = shouldLoopback == 1;
    _radius = radius;
    _attenuationRatio = unpackFloatGainFromByte(attenuationByte);
    _ignorePenumbra = ignorePenumbraFlag == 1;
    
    int numAudioBytes = packetAfterSeqNum.size() - packetStream.device()->pos();
    numAudioSamples = numAudioBytes / sizeof(int16_t);

    return packetStream.device()->pos();
}

AudioStreamStats InjectedAudioStream::getAudioStreamStats() const {
    AudioStreamStats streamStats = PositionalAudioStream::getAudioStreamStats();
    streamStats._streamIdentifier = _streamIdentifier;
    return streamStats;
}
