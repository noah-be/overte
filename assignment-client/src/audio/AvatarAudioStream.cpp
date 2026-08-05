//
//  AvatarAudioStream.cpp
//  assignment-client/src/audio
//
//  Created by Stephen Birarda on 6/5/13.
//  Copyright 2013 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "AvatarAudioStream.h"

#include <cstring>

#include <udt/PacketHeaders.h>

#include "AudioLogging.h"

AvatarAudioStream::AvatarAudioStream(bool isStereo, int numStaticJitterFrames) :
    PositionalAudioStream(PositionalAudioStream::Microphone, isStereo, numStaticJitterFrames) {}

int AvatarAudioStream::parseStreamProperties(PacketType type, const QByteArray& packetAfterSeqNum, int& numAudioSamples) {
    int readBytes = 0;

    if (type == PacketType::SilentAudioFrame || type == PacketType::ReplicatedSilentAudioFrame) {
        if (packetAfterSeqNum.size() < static_cast<int>(sizeof(SilentSamplesBytes))) {
            return -1;
        }

        SilentSamplesBytes numSilentSamples { 0 };
        memcpy(&numSilentSamples, packetAfterSeqNum.constData(), sizeof(numSilentSamples));
        readBytes += sizeof(SilentSamplesBytes);
        numAudioSamples = (int) numSilentSamples;

        // read the positional data
        const int positionalBytes = parsePositionalData(packetAfterSeqNum.mid(readBytes));
        if (positionalBytes < 0) {
            return -1;
        }
        readBytes += positionalBytes;

    } else {
        const bool shouldLoopbackForNode = type == PacketType::MicrophoneAudioWithEcho;

        // read the channel flag
        if (packetAfterSeqNum.size() < static_cast<int>(sizeof(ChannelFlag))) {
            return -1;
        }
        ChannelFlag channelFlag = static_cast<ChannelFlag>(packetAfterSeqNum.at(readBytes));
        if (channelFlag > 1) {
            return -1;
        }
        bool isStereo = channelFlag == 1;
        readBytes += sizeof(ChannelFlag);

        // Validate positional data before changing the frame size or codec.
        const int positionalBytes = parsePositionalData(packetAfterSeqNum.mid(readBytes));
        if (positionalBytes < 0) {
            return -1;
        }
        readBytes += positionalBytes;

        _shouldLoopbackForNode = shouldLoopbackForNode;

        // if isStereo value has changed, restart the ring buffer with new frame size
        if (isStereo != _isStereo) {
            _ringBuffer.resizeForFrameSize(isStereo
                                           ? AudioConstants::NETWORK_FRAME_SAMPLES_STEREO
                                           : AudioConstants::NETWORK_FRAME_SAMPLES_PER_CHANNEL);
            // restart the codec
            if (_codec) {
                QMutexLocker lock(&_decoderMutex);
                if (_decoder) {
                    _codec->releaseDecoder(_decoder);
                }
                _decoder = _codec->createDecoder(AudioConstants::SAMPLE_RATE, isStereo ? AudioConstants::STEREO : AudioConstants::MONO);
            }
            qCDebug(audio) << "resetting AvatarAudioStream... codec:" << _selectedCodecName << "isStereo:" << isStereo;

            _isStereo = isStereo;
        }

        // calculate how many samples are in this packet
        int numAudioBytes = packetAfterSeqNum.size() - readBytes;
        numAudioSamples = numAudioBytes / sizeof(int16_t);
    }

    return readBytes;
}
