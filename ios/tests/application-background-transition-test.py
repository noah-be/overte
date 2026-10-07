#!/usr/bin/env python3
"""Execute the actual Application state handler with resource-operation spies."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import os
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
baseline = os.environ.get("OVERTE_LIFECYCLE_BASELINE")
source = (subprocess.check_output(["git", "show", baseline + ":interface/src/Application_Events.cpp"],
                                 cwd=root, text=True) if baseline else
          (root / "interface/src/Application_Events.cpp").read_text())
handler = source[source.index("void Application::activeChanged("):
                 source.index("void Application::windowMinimizedChanged(")]
fixture = r'''
#include <cassert>
#define Q_OS_IOS 1
namespace Qt { enum ApplicationState {ApplicationActive, ApplicationInactive, ApplicationHidden, ApplicationSuspended}; }
namespace overte::lifecycle { void observeQtVisibility(bool) {} }
struct RefreshRateManager {
    enum class RefreshRateRegime {FOCUS_ACTIVE, UNFOCUS};
    void setRefreshRateRegime(RefreshRateRegime) {}
};
struct Application {
    bool _isForeground = true, _iosBackgrounded = false, _aboutToQuit = false, _startUpFinished = true;
    int prepared = 0, stopped = 0, started = 0;
    RefreshRateManager manager;
    void invalidateEntityScriptConsent() {}
    RefreshRateManager& getRefreshRateManager() { return manager; }
    void beforeEnterBackground() { ++prepared; }
    void enterBackground() { assert(prepared == stopped + 1); ++stopped; }
    void enterForeground() { assert(stopped == started + 1); ++started; }
    void activeChanged(Qt::ApplicationState);
};
/* ACTUAL HANDLER */
int main() {
    Application app;
    app.activeChanged(Qt::ApplicationActive);
    assert(app.started == 0);
    app.activeChanged(Qt::ApplicationInactive);
    assert(!app._isForeground && app.stopped == 0);
    app.activeChanged(Qt::ApplicationHidden);
    assert(app.stopped == 1 && app.prepared == 1);
    app.activeChanged(Qt::ApplicationSuspended);
    assert(app.stopped == 1);
    app.activeChanged(Qt::ApplicationActive);
    app.activeChanged(Qt::ApplicationActive);
    assert(app.started == 1 && app._isForeground);

    app.activeChanged(Qt::ApplicationInactive); // Control Center, no full background
    app.activeChanged(Qt::ApplicationActive);
    assert(app.started == 1 && app.stopped == 1);
    app.activeChanged(Qt::ApplicationSuspended); // direct transition also supported
    assert(app.stopped == 2);
    app.activeChanged(Qt::ApplicationActive);
    assert(app.started == 2);

    Application startup;
    startup._startUpFinished = false;
    startup.activeChanged(Qt::ApplicationHidden);
    assert(startup.stopped == 0);
    startup._startUpFinished = true;
    startup.activeChanged(Qt::ApplicationHidden); // replay at startup completion
    assert(startup.stopped == 1);
    startup.activeChanged(Qt::ApplicationActive);
    assert(startup.started == 1);
    startup._aboutToQuit = true;
    startup.activeChanged(Qt::ApplicationHidden);
    assert(startup.stopped == 1);
}
'''
with tempfile.TemporaryDirectory(prefix="overte-ios-background-") as temporary:
    p = Path(temporary)
    (p / "test.cpp").write_text(fixture.replace("/* ACTUAL HANDLER */", handler))
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    str(p / "test.cpp"), "-o", str(p / "test")], check=True, timeout=30)
    result = subprocess.run([str(p / "test")], capture_output=True, text=True, timeout=5)
    if baseline:
        assert result.returncode != 0 and "app.stopped == 1" in result.stderr, result.stderr
    else:
        assert result.returncode == 0, result.stderr
        ui = (root / "interface/src/Application_UI.cpp").read_text()
        assert "activeChanged(applicationState());" in ui.split("_startUpFinished = true;", 1)[1].split("\n}", 1)[0]
print("EXPECTED BASELINE FAILURE: inactive hides the required background transition" if baseline else
      "PASS actual Application state handler: inactive-hidden, direct suspension, duplicate events, startup replay and quitting")
