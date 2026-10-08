// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <QByteArray>
#include <QDataStream>
#include <QIODevice>

// A bounded copy of actual device input, before local echo, AEC or resampling.
// No output/voice-test PCM can enter this buffer. Owned by the audio thread.
class AcousticTestCapture {
public:
    bool start(int rate, int channels, int seconds) {
        if (_active || !_pcm.isEmpty() || rate < 8000 || rate > 48000 ||
                channels < 1 || channels > 2 || seconds < 6 || seconds > 10) { return false; }
        _rate = rate;
        _channels = channels;
        _limit = rate * channels * 2 * seconds;
        _callbacks = 0;
        _invalid = false;
        _active = true;
        return true;
    }
    void append(const QByteArray& input, int rate, int channels) {
        if (!_active) { return; }
        if (rate != _rate || channels != _channels || input.size() % (_channels * 2)) {
            _invalid = true;
            _active = false;
            _pcm.clear();
            return;
        }
        if (!input.isEmpty()) { ++_callbacks; }
        _pcm.append(input.constData(), qMin(input.size(), static_cast<qsizetype>(_limit - _pcm.size())));
        if (_pcm.size() == _limit) { _active = false; }
    }
    void stop() { _active = false; }
    void invalidate() { _invalid = true; _active = false; _pcm.clear(); }
    void reset() { _active = false; _invalid = false; _callbacks = 0; _pcm.clear(); _limit = 0; }
    bool active() const { return _active; }
    bool complete() const { return !_invalid && _limit > 0 && _pcm.size() == _limit; }
    bool invalid() const { return _invalid; }
    int callbacks() const { return _callbacks; }
    int rate() const { return _rate; }
    int channels() const { return _channels; }
    int bytes() const { return static_cast<int>(_pcm.size()); }
    QByteArray wav() const {
        if (_invalid || _pcm.isEmpty()) { return {}; }
        QByteArray result;
        QDataStream stream(&result, QIODevice::WriteOnly);
        stream.setByteOrder(QDataStream::LittleEndian);
        stream.writeRawData("RIFF", 4);
        stream << quint32(36 + _pcm.size());
        stream.writeRawData("WAVEfmt ", 8);
        stream << quint32(16) << quint16(1) << quint16(_channels) << quint32(_rate)
               << quint32(_rate * _channels * 2) << quint16(_channels * 2) << quint16(16);
        stream.writeRawData("data", 4);
        stream << quint32(_pcm.size());
        stream.writeRawData(_pcm.constData(), _pcm.size());
        return result;
    }
private:
    QByteArray _pcm;
    int _rate { 0 }, _channels { 0 }, _limit { 0 }, _callbacks { 0 };
    bool _active { false }, _invalid { false };
};
