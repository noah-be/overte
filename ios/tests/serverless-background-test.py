#!/usr/bin/env python3
"""Run actual mobile lifecycle methods with scene, transport and audio spies."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import resource
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
baseline = os.environ.get('OVERTE_SERVERLESS_BACKGROUND_BASELINE')
relative = 'interface/src/Application.cpp'
source = (subprocess.check_output(['git', '-C', str(ROOT), 'show', baseline + ':' + relative], text=True)
          if baseline else (ROOT / relative).read_text())
start = source.index('void Application::beforeEnterBackground()')
end = source.index('\n#if defined(Q_OS_ANDROID)\nvoid Application::toggleAwayMode', start)
methods = source[start:end]
fixture = r'''
#include <cassert>
#include <cstring>
#include <iostream>
#define Q_OS_IOS 1
#define qWarning() std::cerr
namespace Qt { enum ConnectionType { BlockingQueuedConnection }; }
struct AudioClient { int stops=0, starts=0; };
struct NodeList {
    bool checkins=true; int resets=0;
    void setSendDomainServerCheckInEnabled(bool enabled) { checkins=enabled; }
    void reset(const char*, bool) { ++resets; }
};
template<class T> struct Pointer {
    T* pointer;
    T* operator->() { return pointer; }
    T* data() { return pointer; }
};
struct DependencyManager {
    template<class T> static Pointer<T> get() { static T object; return { &object }; }
};
struct QMetaObject {
    static void invokeMethod(AudioClient* audio, const char* method, Qt::ConnectionType) {
        if (std::strcmp(method,"stop")==0) ++audio->stops;
        else if (std::strcmp(method,"start")==0) ++audio->starts;
        else assert(false);
    }
};
struct Display {
    bool active=true; int stops=0, starts=0;
    bool isActive() { return active; }
    void deactivate() { active=false; ++stops; }
    bool activate() { active=true; ++starts; return true; }
};
struct Application {
    bool serverless=false, scenePresent=true; int clears=0;
    Display display;
    bool isServerlessMode() { return serverless; }
    Display* getActiveDisplayPlugin() { return &display; }
    void clearDomainOctreeDetails() { ++clears; scenePresent=false; }
    void beforeEnterBackground(); void enterBackground(); void enterForeground();
};
/* ACTUAL METHODS */
int main() {
    auto nodes=DependencyManager::get<NodeList>();
    auto audio=DependencyManager::get<AudioClient>();
    Application local; local.serverless=true; nodes->checkins=false;
    for (int cycle=0; cycle<3; ++cycle) {
        local.beforeEnterBackground(); local.enterBackground();
        assert(local.scenePresent && "Background discarded a serverless scene");
        assert(local.clears==0 && nodes->resets==0 && !nodes->checkins);
        assert(!local.display.active && audio->stops==cycle+1);
        local.enterForeground();
        assert(local.scenePresent && local.display.active);
        assert(!nodes->checkins && "Serverless resume enabled domain check-ins");
        assert(audio->starts==cycle+1);
    }
    Application online; nodes->checkins=true;
    online.beforeEnterBackground(); online.enterBackground();
    assert(online.clears==1 && nodes->resets==1 && !nodes->checkins);
    assert(!online.scenePresent && !online.display.active);
    online.enterForeground();
    assert(nodes->checkins && online.display.active);
    assert(audio->stops==4 && audio->starts==4);
}
'''
with tempfile.TemporaryDirectory(prefix='overte-serverless-background-') as temporary:
    directory=Path(temporary); cpp=directory/'test.cpp'; cpp.write_text(fixture.replace('/* ACTUAL METHODS */',methods))
    binary=directory/'test'
    subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror',str(cpp),'-o',str(binary)],check=True,timeout=30)
    result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=5)
    if baseline:
        assert result.returncode != 0 and 'Background discarded a serverless scene' in result.stderr, result.stderr
    else:
        assert result.returncode == 0, result.stderr
print('EXPECTED BASELINE FAILURE: local scene discarded' if baseline else
      'PASS actual lifecycle methods: local scene/session retained, check-ins disabled, online reset retained, audio/display paired')
