#pragma once

#include <algorithm>
#include <cstddef>
#include <vector>

// A bounded, memory-only recording followed by playback. Never feed live
// microphone samples to the speaker while capturing on a handset.
class PhoneVoiceTestBuffer {
public:
    std::size_t capturedBytes() const { return _recording.size(); }
    std::size_t playedBytes() const { return _position; }
    void reset() { _recording.clear(); _limit = 0; _position = 0; _playing = false; }

    std::vector<char> process(const char* input, std::size_t size, std::size_t limit) {
        std::vector<char> output(size, 0);
        if (!limit || limit > 16 * 1024 * 1024) { reset(); return output; }
        if (_limit != limit) { reset(); _limit = limit; }
        if (!_playing) {
            const auto count = std::min(size, _limit - _recording.size());
            _recording.insert(_recording.end(), input, input + count);
            _playing = _recording.size() == _limit;
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
