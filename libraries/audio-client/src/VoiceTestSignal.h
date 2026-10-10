// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <stdexcept>

// Synthetic input at the network PCM boundary. The ordinary mute, noise gate,
// encoder and packet path still run. This is deliberately not a hardware test.
class VoiceTestSignal {
public:
    static constexpr int RATE = 24000;
    static constexpr int FRAMES = 116160; // 0.5 + 12 * (0.24 + 0.08) + 0.5
    void enable() { _enabled = true; _frame = FRAMES; }
    void reset() { _enabled = false; _frame = FRAMES; }
    // Preserve incomplete progress when a lifecycle or clock failure cancels a send.
    void cancel() { _enabled = false; }
    void send(const std::array<int, 12>& symbols) {
        for (int symbol : symbols) {
            if (symbol < 0 || symbol > 7) { throw std::invalid_argument("voice symbol"); }
        }
        _symbols = symbols;
        _enabled = true;
        _frame = 0;
    }
    bool active() const { return _enabled && _frame < FRAMES; }
    int frames() const { return _frame; }
    void replace(int16_t* pcm, int frames, int channels) {
        if (!_enabled) { return; }
        for (int i = 0; i < frames; ++i) {
            int16_t sample = 0;
            const int relative = _frame - 12000;
            if (_frame < FRAMES && relative >= 0 && relative < 12 * 7680) {
                const int symbol = relative / 7680;
                const int local = relative % 7680;
                if (local < 5760) {
                    const double envelope = std::min(1.0, std::min(local / 192.0, (5759 - local) / 192.0));
                    sample = static_cast<int16_t>(std::lround(0.15 * 32767 * envelope *
                        std::sin(2.0 * 3.14159265358979323846 * (500 + 150 * _symbols[symbol]) * local / RATE)));
                }
            }
            for (int channel = 0; channel < channels; ++channel) { pcm[i * channels + channel] = sample; }
            if (_frame < FRAMES) { ++_frame; }
        }
    }
private:
    bool _enabled { false };
    int _frame { FRAMES };
    std::array<int, 12> _symbols {};
};
