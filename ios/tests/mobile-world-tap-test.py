#!/usr/bin/env python3
"""Execute the production gesture recognizer against unintended-click cases."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class WorldTapTest(unittest.TestCase):
    def test_real_virtual_pad_contact_routing_compiles_and_preserves_ownership(self):
        source = (ROOT / "libraries/input-plugins/src/input-plugins/TouchscreenVirtualPadDevice.cpp").read_text()
        implementations = []
        for match in re.finditer(r"^bool TouchscreenVirtualPadDevice::isWorldTapPosition\([^)]*\)\s*\{", source, re.MULTILINE):
            depth = 1
            end = match.end()
            while depth and end < len(source):
                depth += (source[end] == "{") - (source[end] == "}")
                end += 1
            implementations.append(source[match.start():end])
        # Only the manager, joystick and button queries are seams. Compile every
        # actual definition so a merge-introduced duplicate fails before Xcode.
        code = r'''
#include <QPointF>
#include <cassert>
namespace glm { struct vec2 { float x, y; vec2(float x = 0, float y = 0) : x(x), y(y) {} }; }
namespace VirtualPad {
struct Manager {
    bool enabled = true, hidden = false;
    static Manager& instance() { static Manager value; return value; }
    bool isEnabled() const { return enabled; }
    bool isHidden() const { return hidden; }
};
}
struct Buttons {
    bool unowned = true;
    bool touchBeginInvalidForAllButtons(const glm::vec2&) const { return unowned; }
};
struct TouchscreenVirtualPadDevice {
    bool ownsMove = false;
    glm::vec2 lastPoint;
    Buttons _buttonsManager;
    bool moveTouchBeginIsValid(const glm::vec2& point) { lastPoint = point; return ownsMove; }
    bool isWorldTapPosition(const QPointF& position);
};
// ACTUAL_DEFINITIONS
int main() {
    TouchscreenVirtualPadDevice pad;
    auto& manager = VirtualPad::Manager::instance();
    const QPointF point(13, 29);
    assert(pad.isWorldTapPosition(point));
    assert(pad.lastPoint.x == 13 && pad.lastPoint.y == 29);
    pad.ownsMove = true;
    assert(!pad.isWorldTapPosition(point));
    pad.ownsMove = false;
    pad._buttonsManager.unowned = false;
    assert(!pad.isWorldTapPosition(point));
    manager.hidden = true;
    assert(pad.isWorldTapPosition(point));
    manager.hidden = false;
    manager.enabled = false;
    assert(pad.isWorldTapPosition(point));
}
'''.replace("// ACTUAL_DEFINITIONS", "\n".join(implementations))
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
        with tempfile.TemporaryDirectory(prefix="world-tap-pad-") as directory:
            source_path = Path(directory) / "test.cpp"
            binary = Path(directory) / "test"
            source_path.write_text(code)
            subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fPIC",
                            str(source_path), "-o", str(binary), *flags], check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=5)

    def test_production_mouse_dispatch_compiles_against_qt6(self):
        flags = subprocess.run(["pkg-config", "--cflags", "Qt6Gui"], capture_output=True, text=True)
        if flags.returncode:
            self.skipTest("Qt 6 Gui development headers unavailable")
        source = (ROOT / "interface/src/Application_Events.cpp").read_text()
        begin = source.index("            QMouseEvent press(QEvent::MouseButtonPress, point.position()")
        end = source.index("            mousePressEvent(&press);", begin)
        code = '#include <QMouseEvent>\n#include <QTouchEvent>\n' + (
            'void dispatch(QTouchEvent* event) {const auto& point=event->points().first();\n'
            + source[begin:end] + '}\n')
        subprocess.run(["c++", "-std=c++17", "-fsyntax-only", "-x", "c++", "-",
                        *flags.stdout.split()], input=code, text=True, check=True)

    def test_real_recognizer_requires_an_exclusive_short_stationary_release(self):
        code = r'''
#include "interface/src/MobileWorldTap.h"
#include <cassert>
#include <limits>
int main() {
    MobileWorldTap tap;
    assert(!tap.release(1, 20, 20, 100, true));
    tap.begin(1, 20, 20, 100, true);
    assert(tap.release(1, 23, 22, 220, true));
    assert(!tap.release(1, 23, 22, 221, true));
    tap.begin(1, 20, 20, 100, false);
    assert(!tap.release(1, 20, 20, 150, true));
    tap.begin(1, 20, 20, 100, true);
    assert(!tap.release(1, 20, 20, 150, false));
    tap.begin(1, 20, 20, 100, true);
    tap.update(1, 100, 20, 130, true);
    assert(!tap.release(1, 20, 20, 150, true));
    tap.begin(1, 20, 20, 100, true);
    assert(!tap.release(1, 20, 20, 451, true));
    tap.begin(1, 20, 20, 100, true);
    assert(!tap.release(2, 20, 20, 150, true));
    tap.begin(1, 20, 20, 100, true);
    tap.cancel();
    assert(!tap.release(1, 20, 20, 150, true));
    tap.begin(1, 20, 20, 100, true);
    assert(!tap.release(1, 20, 20, 99, true));
    tap.begin(1, 20, 20, 100, true);
    assert(!tap.release(1, std::numeric_limits<double>::quiet_NaN(), 20, 150, true));
}
'''
        with tempfile.TemporaryDirectory(prefix="world-tap-") as directory:
            source = Path(directory) / "test.cpp"
            binary = Path(directory) / "test"
            source.write_text(code)
            subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-I", str(ROOT), str(source), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
