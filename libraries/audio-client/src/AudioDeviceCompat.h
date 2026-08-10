// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <QtGlobal>
#include <QMetaType>
#include <QAudioFormat>
#include <QList>
#include <QString>

enum class HifiAudioDeviceMode {
    Input,
    Output
};

Q_DECLARE_METATYPE(HifiAudioDeviceMode)

#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
#include <QAudioDevice>
#include <QAudioSink>
#include <QAudioSource>
#include <QMediaDevices>

using HifiQtAudioDevice = QAudioDevice;
using HifiAudioSource = QAudioSource;
using HifiAudioSink = QAudioSink;

inline QString hifiAudioDeviceName(const HifiQtAudioDevice& device) {
    return device.description();
}

inline QList<HifiQtAudioDevice> hifiAvailableAudioDevices(HifiAudioDeviceMode mode) {
    return mode == HifiAudioDeviceMode::Input ? QMediaDevices::audioInputs() : QMediaDevices::audioOutputs();
}

inline HifiQtAudioDevice hifiDefaultAudioDevice(HifiAudioDeviceMode mode) {
    return mode == HifiAudioDeviceMode::Input ? QMediaDevices::defaultAudioInput() : QMediaDevices::defaultAudioOutput();
}
#else
#include <QAudio>
#include <QAudioDeviceInfo>
#include <QAudioInput>
#include <QAudioOutput>

using HifiQtAudioDevice = QAudioDeviceInfo;
using HifiAudioSource = QAudioInput;
using HifiAudioSink = QAudioOutput;

inline QAudio::Mode hifiQtAudioMode(HifiAudioDeviceMode mode) {
    return mode == HifiAudioDeviceMode::Input ? QAudio::AudioInput : QAudio::AudioOutput;
}

inline QString hifiAudioDeviceName(const HifiQtAudioDevice& device) {
    return device.deviceName();
}

inline QList<HifiQtAudioDevice> hifiAvailableAudioDevices(HifiAudioDeviceMode mode) {
    return QAudioDeviceInfo::availableDevices(hifiQtAudioMode(mode));
}

inline HifiQtAudioDevice hifiDefaultAudioDevice(HifiAudioDeviceMode mode) {
    return mode == HifiAudioDeviceMode::Input ?
        QAudioDeviceInfo::defaultInputDevice() : QAudioDeviceInfo::defaultOutputDevice();
}
#endif

inline void hifiConfigurePcm16(QAudioFormat& format) {
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
    format.setSampleFormat(QAudioFormat::Int16);
#else
    format.setSampleSize(16);
    format.setCodec("audio/pcm");
    format.setSampleType(QAudioFormat::SignedInt);
    format.setByteOrder(QAudioFormat::LittleEndian);
#endif
}

inline int hifiAudioSampleSize(const QAudioFormat& format) {
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
    return format.sampleFormat() == QAudioFormat::Int16 ? 16 : 0;
#else
    return format.sampleSize();
#endif
}

inline int hifiAudioSinkPullCapacity(const HifiAudioSink& sink) {
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
    // QAudioSink does not publish its backend period. After start(), bufferSize()
    // is the only documented upper bound available for pull-buffer allocation.
    // This is a capacity bound, not a latency or callback-cadence estimate.
    return sink.bufferSize();
#else
    return sink.periodSize();
#endif
}
