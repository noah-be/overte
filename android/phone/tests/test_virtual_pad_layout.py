"""Exercise the production Phone layout mailbox across competing native threads."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class PhoneLayoutTest(unittest.TestCase):
    def test_actual_button_refresh_preserves_active_contact(self):
        source_text = (ROOT / 'libraries/input-plugins/src/input-plugins/TouchscreenVirtualPadDevice.cpp').read_text()
        start = source_text.index('    for (auto& button : _buttonsManager.buttons)')
        end = source_text.index('    virtualPadManager.setButtonPosition', start)
        refresh = source_text[start:end]
        driver = r'''
#include <cassert>
#include <vector>
struct Point { float x, y; };
struct Button { float buttonRadius; Point buttonPosition; int channel; bool hasValidTouch; int currentTouchId; bool found; };
int main() {
    const int JUMP = 1;
    struct { std::vector<Button> buttons; } _buttonsManager;
    _buttonsManager.buttons = {{20, {10,20}, JUMP, true, 17, true}, {20, {10,10}, 2, false, 23, false}};
    const float _buttonRadius = 46;
    const Point jumpButtonPosition {2120,910}, rbButtonPosition {2120,760};
''' + refresh + r'''
    assert(_buttonsManager.buttons.size() == 2);
    const auto& jump = _buttonsManager.buttons[0];
    const auto& secondary = _buttonsManager.buttons[1];
    assert(jump.buttonRadius == 46 && jump.buttonPosition.x == 2120 && jump.buttonPosition.y == 910);
    assert(secondary.buttonRadius == 46 && secondary.buttonPosition.y == 760);
    assert(jump.hasValidTouch && jump.currentTouchId == 17 && jump.found && jump.channel == JUMP);
    assert(!secondary.hasValidTouch && secondary.currentTouchId == 23 && !secondary.found && secondary.channel == 2);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'contact.cpp'
            binary = Path(directory) / 'contact'
            source.write_text(driver)
            subprocess.run(['c++', '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror',
                            str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True, timeout=30)

    def test_initialization_validation_and_coherent_updates(self):
        driver = r'''
#include "libraries/ui/src/PhoneVirtualPadLayout.h"
#include <atomic>
#include <cassert>
#include <limits>
#include <thread>
#include <vector>
using namespace VirtualPad;
PhoneLayout makeLayout(float value) {
    PhoneLayout layout;
    layout.padDiameter = value;
    layout.buttonDiameter = value * 2;
    layout.buttonRadius = value * 3;
    layout.centerX = value * 4;
    layout.centerY = value * 5;
    layout.buttonX = value * 6;
    layout.jumpY = value * 7;
    layout.secondaryY = value * 8;
    layout.buttonsVisible = true;
    return layout;
}
void verify(const PhoneLayout& layout) {
    if (!layout.revision) { return; }
    assert(layout.buttonDiameter == layout.padDiameter * 2);
    assert(layout.buttonRadius == layout.padDiameter * 3);
    assert(layout.centerX == layout.padDiameter * 4);
    assert(layout.centerY == layout.padDiameter * 5);
    assert(layout.buttonX == layout.padDiameter * 6);
    assert(layout.jumpY == layout.padDiameter * 7);
    assert(layout.secondaryY == layout.padDiameter * 8);
}
int main() {
    PhoneLayoutMailbox mailbox;
    assert(mailbox.read().revision == 0);
    assert(!mailbox.publish(PhoneLayout {}));
    auto first = makeLayout(156);
    first.revision = 999;
    assert(mailbox.publish(first));
    assert(mailbox.read().revision == 1);
    assert(!mailbox.publish(first));
    assert(mailbox.read().revision == 1);
    auto invalid = first;
    invalid.centerX = std::numeric_limits<float>::quiet_NaN();
    assert(!mailbox.publish(invalid));
    invalid = first;
    invalid.buttonDiameter = std::numeric_limits<float>::infinity();
    assert(!mailbox.publish(invalid));
    invalid = first;
    invalid.buttonRadius = -1;
    assert(!mailbox.publish(invalid));
    assert(mailbox.read().revision == 1);
    // A late real-DPI layout replaces all fallback dimensions together.
    assert(mailbox.publish(makeLayout(350)));
    assert(mailbox.read().padDiameter == 350);
    assert(mailbox.read().revision == 2);
    std::atomic<bool> done { false };
    std::vector<std::thread> readers;
    for (int i = 0; i < 3; ++i) {
        readers.emplace_back([&] {
            uint64_t previous = 0;
            do {
                auto layout = mailbox.read();
                verify(layout);
                assert(layout.revision >= previous);
                previous = layout.revision;
            } while (!done.load());
        });
    }
    for (int i = 1; i <= 20000; ++i) { mailbox.publish(makeLayout(float(i))); }
    done.store(true);
    for (auto& reader : readers) { reader.join(); }
    verify(mailbox.read());
    assert(mailbox.read().padDiameter == 20000);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'layout.cpp'
            binary = Path(directory) / 'layout'
            source.write_text(driver)
            subprocess.run(['c++', '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-pthread', '-I', str(ROOT), str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True, timeout=30)


if __name__ == '__main__':
    unittest.main()
