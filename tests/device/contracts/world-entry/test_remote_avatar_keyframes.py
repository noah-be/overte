# SPDX-License-Identifier: Apache-2.0
"""Compile the production keyframe search with checked vector indexing."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class RemoteAvatarKeyframeTests(unittest.TestCase):
    def test_timestamp_boundaries_and_lookback_window(self):
        text = (ROOT / 'interface/src/avatar/OtherAvatar.cpp').read_text()
        body = text.split('size_t oldKeyframeIndex =', 1)[1].split(
            'const std::pair<quint64, JointData> &oldKeyframe', 1)[0]
        source = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <utility>
#include <vector>
using quint64 = std::uint64_t;
std::pair<size_t, size_t> selectFrames(
    const std::vector<std::pair<quint64, int>>& history,
    size_t historyStart, quint64 timePoint) {
    size_t oldKeyframeIndex = ''' + body + r'''
    return {oldKeyframeIndex, newKeyframeIndex};
}
int main() {
    using Pair = std::pair<size_t, size_t>;
    const std::vector<std::pair<quint64,int>> one{{100,0}};
    assert(selectFrames(one,0,100) == Pair(0,0));
    assert(selectFrames(one,0,50) == Pair(0,0));
    assert(selectFrames(one,0,150) == Pair(0,0));
    const std::vector<std::pair<quint64,int>> several{{100,0},{200,0},{300,0}};
    assert(selectFrames(several,0,50) == Pair(0,0));
    assert(selectFrames(several,0,100) == Pair(0,1));
    assert(selectFrames(several,0,150) == Pair(0,1));
    assert(selectFrames(several,0,200) == Pair(1,2));
    assert(selectFrames(several,0,300) == Pair(2,2));
    assert(selectFrames(several,0,350) == Pair(2,2));
    assert(selectFrames(several,1,50) == Pair(1,1));
    assert(selectFrames(several,1,250) == Pair(1,2));
    const std::vector<std::pair<quint64,int>> equal{{100,0},{100,0}};
    assert(selectFrames(equal,0,100) == Pair(1,1));
}
'''
        with tempfile.TemporaryDirectory() as directory:
            cpp = pathlib.Path(directory) / 'keyframes.cpp'
            binary = pathlib.Path(directory) / 'keyframes'
            cpp.write_text(source)
            subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-D_GLIBCXX_ASSERTIONS',
                            str(cpp), '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
