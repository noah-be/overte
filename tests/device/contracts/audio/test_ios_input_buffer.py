#!/usr/bin/env python3
"""Exercise the production input allocation with larger iOS callback blocks."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class InputBufferTests(unittest.TestCase):
    def test_ios_preserves_native_blocks_and_other_platform_buffer(self):
        source = (ROOT / "libraries/audio-client/src/AudioClient.cpp").read_text()
        begin = source.index("                _audioInput = new HifiAudioSource(")
        allocation = source[begin:source.index("                // different audio input devices", begin)]
        fixture = r'''
#include <algorithm>
#include <cassert>
struct Device { int getDevice() const { return 0; } };
struct Format {};
struct HifiAudioSource {
    // Qt's default ring capacity is 250 ms; capacity does not delay readyRead.
    int capacity = 44100 * 2 / 4;
    HifiAudioSource(int, Format, void*) {}
    void setBufferSize(int bytes) { capacity = bytes; }
};
struct AudioClient {
    Device _inputDeviceInfo;
    Format _inputFormat;
    int _numInputCallbackBytes = 440;
    HifiAudioSource* _audioInput = nullptr;
    void allocate() { /* ALLOCATION */ }
    ~AudioClient() { delete _audioInput; }
};
int main() {
    AudioClient client;
    client.allocate();
#ifdef Q_OS_IOS
    // A 1024-frame hardware callback exceeds the previous 220-frame ring.
    // Exercise eight seconds of physical-sized blocks without padded samples.
    int captured = 0;
    for (int samples = 0; samples < 44100 * 8;) {
        int blockSamples = std::min(1024, 44100 * 8 - samples);
        captured += std::min(client._audioInput->capacity, blockSamples * 2);
        samples += blockSamples;
    }
    assert(captured == 44100 * 8 * 2);
#else
    assert(client._audioInput->capacity == client._numInputCallbackBytes);
#endif
}
'''.replace("/* ALLOCATION */", allocation)
        with tempfile.TemporaryDirectory(prefix="overte-ios-input-buffer-") as directory:
            path = Path(directory)
            (path / "input.cpp").write_text(fixture)
            for ios in (True, False):
                binary = path / ("ios" if ios else "other")
                flags = ["-DQ_OS_IOS=1"] if ios else []
                subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", *flags,
                                str(path / "input.cpp"), "-o", str(binary)], check=True, timeout=30)
                subprocess.run([str(binary)], check=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
