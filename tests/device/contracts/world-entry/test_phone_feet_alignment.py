# SPDX-License-Identifier: Apache-2.0
"""Exercise the production placement block against delayed capsule initialization.

This isolates numeric placement and pending state; hardware tests cover Qt/model
initialization and real Bullet support. The previous block is a negative control.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


def harness(block):
    return r'''
#include <cassert>
struct Skeleton {
    bool loaded = true;
    double radius = 0;
    bool isLoaded() const { return loaded; }
    double getBoundingCapsuleRadius() const { return radius; }
};
struct Avatar {
    Skeleton skeleton;
    Skeleton* _skeletonModel = &skeleton;
    bool _goToFeetAjustment = true;
    double _goToPosition = 0;
    double position = 0;
    double getWorldPosition() const { return position; }
    double getWorldFeetPosition() const {
        return position - (skeleton.radius > 0 ? 1.0 : .0094);
    }
    void setWorldPosition(double value) { position = value; }
    void update() {
''' + block + r'''
    }
};
int main() {
    Avatar avatar;
    avatar.update(); // resource loaded, collision capsule not initialized
    assert(avatar._goToFeetAjustment);
    assert(avatar.position == 0);
    avatar.skeleton.radius = .1355;
    avatar.update(); // the actual standing extent now exists
    assert(!avatar._goToFeetAjustment);
    assert(avatar.position == 1);
    assert(avatar.getWorldFeetPosition() == 0);
    avatar.position = 3;
    avatar.update(); // completed navigation must not replay each frame
    assert(avatar.position == 3);
}
'''


class PhoneFeetAlignmentTests(unittest.TestCase):
    def test_pending_alignment_waits_for_the_production_collision_extent(self):
        source = (ROOT / 'interface/src/avatar/MyAvatar.cpp').read_text()
        start = source.index('    const bool feetGeometryReady =')
        end = source.index('    if (_physicsSafetyPending', start)
        block = source[start:end]
        old = '''
        if (_goToFeetAjustment && _skeletonModel->isLoaded()) {
            auto feetAjustment = getWorldPosition() - getWorldFeetPosition();
            _goToPosition = getWorldPosition() + feetAjustment;
            setWorldPosition(_goToPosition);
            _goToFeetAjustment = false;
        }
        '''
        with tempfile.TemporaryDirectory() as temporary:
            for name, candidate, expected in [('repaired', block, True), ('previous', old, False)]:
                cpp = Path(temporary) / (name + '.cpp')
                binary = Path(temporary) / name
                cpp.write_text(harness(candidate))
                subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                                '-DANDROID_APP_PHONE_INTERFACE', str(cpp), '-o', str(binary)],
                               check=True, timeout=30)
                result = subprocess.run([str(binary)], stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, timeout=10)
                self.assertEqual(expected, result.returncode == 0, name)


if __name__ == '__main__':
    unittest.main()
