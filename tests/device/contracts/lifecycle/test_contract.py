# SPDX-License-Identifier: Apache-2.0
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]

class LifecycleTests(unittest.TestCase):
    def test_compiled_state_event_order_and_bounds(self):
        with tempfile.TemporaryDirectory() as temporary:
            binary = pathlib.Path(temporary) / 'lifecycle'
            subprocess.run(['c++', '-std=c++14', '-Wall', '-Wextra', '-Werror', '-pthread',
                            '-I', str(ROOT), str(pathlib.Path(__file__).with_name('test_lifecycle.cpp')),
                            '-o', str(binary)], check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=10)

    def test_actual_qt_lifecycle_caller_is_bound(self):
        source = (ROOT / 'interface/src/Application_Events.cpp').read_text()
        body = source.split('void Application::activeChanged(Qt::ApplicationState state) {', 1)[1].split('\n}', 1)[0]
        self.assertIn('observeQtVisibility(state == Qt::ApplicationActive)', body)
        definition = (ROOT / 'interface/src/Application.cpp').read_text()
        self.assertIn('Gate& overte::lifecycle::applicationGate()', definition)

    def test_initial_visibility_seed_and_actual_inactive_body(self):
        setup = (ROOT / 'interface/src/Application_Setup.cpp').read_text()
        connect = 'connect(this, &Application::applicationStateChanged, this, &Application::activeChanged);'
        tail = setup.split(connect, 1)[1]
        self.assertIn('activeChanged(applicationState());', tail.split('connect(', 1)[0])
        source = (ROOT / 'interface/src/Application_Events.cpp').read_text()
        body = source.split('void Application::activeChanged(Qt::ApplicationState state) {', 1)[1].split('\n}', 1)[0]
        # Execute the original production body; only Qt/rate/consent boundaries
        # are test substitutes. Never substitute a second lifecycle engine.
        harness = '''
#include "interface/src/ApplicationLifecycle.h"
#include <cassert>
#include <initializer_list>
namespace Qt { enum ApplicationState { ApplicationActive, ApplicationInactive, ApplicationSuspended, ApplicationHidden }; }
struct AddressManager { bool foreground = false; void setClientLookupVisibility(bool value) { foreground = value; } };
AddressManager addresses;
struct DependencyManager { template<class T> static T* get() { return &addresses; } };
struct RefreshRateManager {
    enum class RefreshRateRegime { FOCUS_ACTIVE, UNFOCUS };
    void setRefreshRateRegime(RefreshRateRegime) {}
};
overte::lifecycle::Gate gate;
overte::lifecycle::Gate& overte::lifecycle::applicationGate() { return gate; }
// The real publication bridge is separately compiled/executed with Qt by
// test_visibility_inputs.py; this small event-body test substitutes that edge.
void overte::lifecycle::observeQtVisibility(bool value) {
    gate.visible(value);
    addresses.setClientLookupVisibility(value);
}
struct Application {
    bool _isForeground = false, _aboutToQuit = false, _startUpFinished = true;
    int consentInvalidations = 0;
    void invalidateEntityScriptConsent() { ++consentInvalidations; }
    RefreshRateManager rates;
    RefreshRateManager& getRefreshRateManager() { return rates; }
    void activeChanged(Qt::ApplicationState state) { BODY }
};
int main() {
    Application app;
    for (auto hidden : {Qt::ApplicationInactive, Qt::ApplicationSuspended, Qt::ApplicationHidden}) {
        auto invalidations = app.consentInvalidations;
        app.activeChanged(Qt::ApplicationActive);
        assert(app.consentInvalidations == invalidations);
        assert(app._isForeground && gate.snapshot().foreground);
        assert(addresses.foreground);
        auto generation = gate.snapshot().generation;
        app.activeChanged(Qt::ApplicationActive);
        assert(app.consentInvalidations == invalidations);
        assert(gate.snapshot().generation == generation);
        app.activeChanged(hidden);
        assert(app.consentInvalidations == invalidations + 1);
        assert(!app._isForeground && !gate.snapshot().foreground);
        assert(!addresses.foreground);
        assert(gate.snapshot().state == overte::lifecycle::State::Suspended);
    }
}
'''.replace('BODY', body)
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / 'actual-visibility.cpp'
            path.write_text(harness)
            binary = pathlib.Path(temporary) / 'visibility'
            subprocess.run(['c++', '-std=c++14', '-Wall', '-Wextra', '-Werror', '-pthread',
                            '-I', str(ROOT), str(path), '-o', str(binary)], check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=10)

if __name__ == '__main__':
    unittest.main()
