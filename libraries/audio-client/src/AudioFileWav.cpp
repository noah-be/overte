//
//  AudioWavFile.h
//  libraries/audio-client/src
//
//  Created by Luis Cuenca on 12/1/2017.
//  Copyright 2017 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "AudioFileWav.h"
#include "AudioDeviceCompat.h"

bool AudioFileWav::create(const QAudioFormat& audioFormat, const QString& filepath) {
    if (_file.isOpen()) {
        _file.close();
    }
    const int sampleSize = hifiAudioSampleSize(audioFormat);
    if (sampleSize <= 0) {
        return false;
    }
    _file.setFileName(filepath);
    if (!_file.open(QIODevice::WriteOnly)) {
        return false;
    }
    addHeader(audioFormat, sampleSize);
    return true;
}

bool AudioFileWav::addRawAudioChunk(char* chunk, int size) {
    if (_file.isOpen()) {
        QDataStream stream(&_file);
        stream.writeRawData(chunk, size);
        return true;
    }
    return false;
}

void AudioFileWav::close() {
    QDataStream stream(&_file);
    stream.setByteOrder(QDataStream::LittleEndian);

    // fill RIFF and size data on header
    _file.seek(4);
    stream << quint32(_file.size() - 8);
    _file.seek(40);
    stream << quint32(_file.size() - 44);
    _file.close();
}

void AudioFileWav::addHeader(const QAudioFormat& audioFormat, int sampleSize) {
    QDataStream stream(&_file);

    stream.setByteOrder(QDataStream::LittleEndian);

    // RIFF
    stream.writeRawData("RIFF", 4);
    stream << quint32(0);
    stream.writeRawData("WAVE", 4);

    // Format description PCM = 16
    stream.writeRawData("fmt ", 4);
    stream << quint32(16);
    stream << quint16(1);
    stream << quint16(audioFormat.channelCount());
    stream << quint32(audioFormat.sampleRate());
    stream << quint32(audioFormat.sampleRate() * audioFormat.channelCount() * sampleSize / 8); // bytes per second
    stream << quint16(audioFormat.channelCount() * sampleSize / 8); // block align
    stream << quint16(sampleSize); // bits Per Sample
    // Init data chunck
    stream.writeRawData("data", 4);
    stream << quint32(0);
}
