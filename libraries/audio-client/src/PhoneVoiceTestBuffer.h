#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <vector>

// A bounded, memory-only recording followed by playback. Never feed live
// microphone samples to the speaker while capturing on a handset.
class PhoneVoiceTestBuffer {
public:
    std::size_t capturedBytes() const { return _recording.size(); }
    std::size_t playedBytes() const { return _position; }
    void reset() { _recording.clear(); _limit = 0; _position = 0; _playing = false; }

    std::vector<char> process(const char* input, std::size_t size, std::size_t limit,
                             bool normalizePcm16 = false) {
        std::vector<char> output(size, 0);
        if (!limit || limit > 16 * 1024 * 1024) { reset(); return output; }
        if (_limit != limit) { reset(); _limit = limit; }
        if (!_playing) {
            const auto count = std::min(size, _limit - _recording.size());
            _recording.insert(_recording.end(), input, input + count);
            _playing = _recording.size() == _limit;
            if (_playing && normalizePcm16) {
                int peak = 0;
                for (std::size_t i = 0; i + sizeof(int16_t) <= _recording.size(); i += sizeof(int16_t)) {
                    int16_t value;
                    std::memcpy(&value, _recording.data() + i, sizeof(value));
                    peak = std::max(peak, value < 0 ? -static_cast<int>(value) : static_cast<int>(value));
                }
                // Preview gain only: bounded to +30 dB, never amplify exact
                // silence, and never boost already loud input into clipping.
                const double gain = peak > 0 ? std::min(32.0, std::max(1.0, 16384.0 / peak)) : 1.0;
                for (std::size_t i = 0; i + sizeof(int16_t) <= _recording.size(); i += sizeof(int16_t)) {
                    int16_t value;
                    std::memcpy(&value, _recording.data() + i, sizeof(value));
                    value = static_cast<int16_t>(static_cast<int>(value) * gain);
                    std::memcpy(_recording.data() + i, &value, sizeof(value));
                }
            }
        } else {
            const auto count = std::min(size, _recording.size() - _position);
            std::copy_n(_recording.begin() + _position, count, output.begin());
            _position += count;
            // Keep the completed phase until reset: no repeated capture of
            // the sound just played through the handset speaker.
        }
        return output;
    }

private:
    std::vector<char> _recording;
    std::size_t _limit { 0 };
    std::size_t _position { 0 };
    bool _playing { false };
};
