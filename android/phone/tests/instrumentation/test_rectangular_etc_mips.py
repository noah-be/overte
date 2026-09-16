#!/usr/bin/env python3
"""Exercise the production tail repair against the pinned Etc2Comp sources.
Pass the Etc2Comp source directory (containing EtcLib) as the first argument.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

repo = Path(__file__).resolve().parents[4]
source = (repo / 'libraries/image/src/image/TextureProcessing.cpp').read_text()
start = source.index('        // Etc2Comp stops when either dimension reaches zero.')
end = source.index('#endif', start)
repair = source[start:end]
etc = Path(sys.argv[1]).resolve() / 'EtcLib'
fixture = r'''
#include <Etc.h>
#include <EtcFilter.h>
#include <algorithm>
#include <cassert>
#include <cmath>
#include <vector>
struct Pixels { std::vector<float> p; float* editBits() { return p.data(); } };
void check(int width, int height) {
    Pixels localCopy { std::vector<float>(width * height * 4, 0.5f) };
    const int numMips = 1 + (int)std::log2(std::max(width, height));
    auto mipMaps = std::vector<Etc::RawImage>(numMips);
    const auto etcFormat = Etc::Image::Format::RGB8;
    const auto errorMetric = Etc::ErrorMetric::RGBA;
    const float effort = 1.0f;
    const int numEncodeThreads = 1;
    int elapsed;
    Etc::EncodeMipmaps(localCopy.editBits(), width, height, etcFormat, errorMetric,
        effort, 1, 1, numMips, Etc::FILTER_WRAP_NONE, mipMaps.data(), &elapsed);
    std::vector<std::shared_ptr<unsigned char>> before;
    int missing = 0;
    for (const auto& mip : mipMaps) {
        before.push_back(mip.paucEncodingBits);
        missing += !mip.paucEncodingBits;
    }
    assert((width == height) == (missing == 0));
''' + repair + r'''
    for (int i = 0; i < numMips; ++i) {
        assert(mipMaps[i].paucEncodingBits);
        if (before[i]) assert(before[i] == mipMaps[i].paucEncodingBits);
        const int w = std::max(1, width >> i), h = std::max(1, height >> i);
        assert(mipMaps[i].uiEncodingBitsBytes == ((w + 3) / 4) * ((h + 3) / 4) * 8);
    }
}
int main() { check(32, 8); check(8, 32); check(16, 16); check(1, 16); check(16, 1); check(24, 8); }
'''
with tempfile.TemporaryDirectory() as tmp:
    cpp = Path(tmp) / 'test.cpp'; cpp.write_text(fixture)
    exe = Path(tmp) / 'test'
    includes = [etc / 'Etc', etc / 'EtcCodec']
    sources = sorted(etc.rglob('*.cpp'))
    subprocess.run(['c++', '-std=c++14', '-O1', '-pthread', *['-I'+str(p) for p in includes], str(cpp), *map(str, sources), '-o', str(exe)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run([str(exe)], check=True)
print('PASS: real ETC encoder reproduces missing tails; production repair completes six mip chains and preserves existing levels')
