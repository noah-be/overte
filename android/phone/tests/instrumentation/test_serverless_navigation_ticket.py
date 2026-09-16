#!/usr/bin/env python3
"""Real RequestScope/Ticket semantics in a deterministic two-queue race fixture.

The queues and scene side effects are host adapters. Source contracts additionally
check the application's ticket plumbing and parse/commit guard locations. This
cannot prove atomicity across the application's and DomainHandler's threads or
replace full Qt/device navigation tests.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
TEST = r'''
#include <cassert>
#include <functional>
#include <iostream>
#include <vector>
using overte::network::RequestScope;
using overte::network::RequestTicket;
struct Scene {
    RequestScope navigation;
    RequestScope discovery;
    bool connected = false;
    int parsed = 0, sessions = 0, permissions = 0, entities = 0, handoffs = 0, acknowledgments = 0;
    RequestTicket localSignal() { return navigation.next(); }
    void onlineTransition() { navigation.next(); connected=false; }
    bool request(const RequestTicket& t) { return t.scoped() && t.current(); }
    bool finish(const RequestTicket& t, const std::function<void()>& duringParse={}) {
        if (!request(t)) return false;
        ++parsed;
        if (duringParse) duringParse();
        if (!request(t)) return false;
        ++sessions; ++permissions; ++entities;
        return true;
    }
    bool handoff(const RequestTicket& t) {
        if (!request(t)) return false;
        connected=true; ++handoffs; return true;
    }
    void ack(const RequestTicket& t) { if (request(t)) ++acknowledgments; }
    void assertUntouched() { assert(!connected && sessions==0 && permissions==0 && entities==0 && handoffs==0 && acknowledgments==0); }
};
struct QueuedScene : Scene {
    RequestScope loads;
    int navigationEffects=0, resourceRequests=0;
    bool queuedNavigation(const RequestTicket& nav) {
        if (!request(nav) || !loads.snapshot().current()) return false;
        ++navigationEffects; return true;
    }
    bool queuedRequest(const RequestTicket& nav) {
        if (!request(nav) || !loads.snapshot().current()) return false;
        loads.next(); ++resourceRequests; return true;
    }
    bool queuedHandoff(const RequestTicket& navigation, const RequestTicket& load) {
        return load.scoped() && load.current() && handoff(navigation);
    }
    void queuedAck(const RequestTicket& navigation, const RequestTicket& load) {
        if (load.scoped() && load.current()) ack(navigation);
    }
    void shutdown() { loads.setActive(false); }
};
int main() {
    // 1. An old signal reaches the app queue after the newer online transition.
    { Scene s; auto old=s.localSignal(); s.onlineTransition(); assert(!s.request(old)); s.assertUntouched(); }
    // 2. A download finishes after its destination was replaced.
    { Scene s; auto old=s.localSignal(); assert(s.request(old)); s.onlineTransition(); assert(!s.finish(old)); assert(s.parsed==0); s.assertUntouched(); }
    // 3. Replacement while parsing must precede session/permission/entity effects.
    { Scene s; auto old=s.localSignal(); assert(!s.finish(old,[&]{s.onlineTransition();})); assert(s.parsed==1); s.assertUntouched(); }
    // 4. Replacement between app validation and the DomainHandler queue, or ack.
    { Scene s; auto old=s.localSignal(); assert(s.finish(old)); s.onlineTransition(); assert(!s.handoff(old)); s.ack(old); assert(!s.connected && s.handoffs==0 && s.acknowledgments==0); }
    { Scene s; auto old=s.localSignal(); assert(s.finish(old)); assert(s.handoff(old)); s.onlineTransition(); s.ack(old); assert(s.acknowledgments==0 && !s.connected); }
    // 5. The 2500ms recovery timer must not determine navigation correctness.
    for(int finishAt : {2240,3390}) {
        Scene s; auto old=s.localSignal(); s.onlineTransition();
        std::vector<std::pair<int,std::function<void()>>> events = {
            {finishAt,[&]{assert(!s.finish(old)); assert(!s.handoff(old)); s.ack(old);}},
            {2500,[]{ /* a retry is deliberately unnecessary */ }} };
        std::sort(events.begin(),events.end(),[](auto& a,auto& b){return a.first<b.first;});
        for(auto& e:events)e.second(); s.assertUntouched();
    }
    // 6. A deliberate local destination after an online one is still valid.
    { Scene s; s.onlineTransition(); auto local=s.localSignal(); assert(s.request(local)); assert(s.finish(local)); assert(s.handoff(local)); s.ack(local); assert(s.connected && s.entities==1 && s.acknowledgments==1); }
    // 7. Two local requests complete out of order; only the latest may commit.
    { Scene s; auto old=s.localSignal(); auto latest=s.localSignal(); assert(s.finish(latest)); assert(s.handoff(latest)); s.ack(latest); assert(!s.finish(old)); assert(!s.handoff(old)); s.ack(old); assert(s.entities==1 && s.handoffs==1 && s.acknowledgments==1); }
    // Visibility cancellation belongs to DNS discovery, not scene ownership.
    { Scene s; auto local=s.localSignal(); s.discovery.setActive(false); s.discovery.setActive(true);
      assert(s.finish(local)); assert(s.handoff(local)); s.ack(local); assert(s.acknowledgments==1); }
    // A direct reload retires an old queued owner handoff AND its app ack,
    // while retaining the same destination ticket and accepting the latest load.
    { QueuedScene s; auto nav=s.localSignal(); auto first=s.loads.next();
      std::function<void()> oldHandoff=[&]{assert(!s.queuedHandoff(nav,first));};
      std::function<void()> oldAck=[&]{s.queuedAck(nav,first);};
      auto latest=s.loads.next(); assert(nav.current());
      oldHandoff(); oldAck(); assert(s.handoffs==0 && s.acknowledgments==0);
      assert(s.queuedHandoff(nav,latest)); s.queuedAck(nav,latest);
      assert(s.handoffs==1 && s.acknowledgments==1); }
    // The old owner handoff may already have happened when a direct reload
    // supersedes its queued app ack. That ack must still be discarded.
    { QueuedScene s; auto nav=s.localSignal(); auto first=s.loads.next();
      assert(s.queuedHandoff(nav,first)); auto latest=s.loads.next();
      s.queuedAck(nav,first); assert(s.acknowledgments==0);
      assert(s.queuedHandoff(nav,latest)); s.queuedAck(nav,latest);
      assert(s.handoffs==2 && s.acknowledgments==1); }
    // Shutdown invalidates both queues even while the application object and
    // navigation ticket are alive. next() must not reactivate a closed scope.
    { QueuedScene s; auto nav=s.localSignal(); auto load=s.loads.next();
      std::function<void()> owner=[&]{assert(!s.queuedHandoff(nav,load));};
      std::function<void()> app=[&]{s.queuedAck(nav,load);};
      s.shutdown(); assert(nav.current()); owner(); app();
      auto afterShutdown=s.loads.next(); assert(afterShutdown.scoped() && !afterShutdown.current());
      assert(!s.queuedHandoff(nav,afterShutdown)); s.queuedAck(nav,afterShutdown);
      assert(s.handoffs==0 && s.acknowledgments==0); }
    // Navigation and load-start events queued before shutdown must not touch
    // UI/world state or recreate a ResourceManager after subsystem teardown.
    { QueuedScene s; auto nav=s.localSignal();
      assert(s.queuedNavigation(nav)); assert(s.queuedRequest(nav));
      std::function<void()> navigation=[&]{assert(!s.queuedNavigation(nav));};
      std::function<void()> request=[&]{assert(!s.queuedRequest(nav));};
      s.shutdown(); assert(nav.current()); navigation(); request();
      assert(s.navigationEffects==1 && s.resourceRequests==1); }
    // Shutdown after a completed owner handoff blocks its pending app ack.
    { QueuedScene s; auto nav=s.localSignal(); auto load=s.loads.next();
      assert(s.queuedHandoff(nav,load)); s.shutdown(); s.queuedAck(nav,load);
      assert(nav.current() && s.handoffs==1 && s.acknowledgments==0); }
    { Scene s; RequestTicket unscoped; assert(!s.request(unscoped)); }
    std::cout << "PASS seven navigation sequences plus queued reload/shutdown handoff and ack cases using production RequestScope/RequestTicket\n";
}
'''


def source_contracts():
    app = (ROOT / 'interface/src/Application.cpp').read_text()
    setup = (ROOT / 'interface/src/Application_Setup.cpp').read_text()
    handler = (ROOT / 'libraries/networking/src/DomainHandler.h').read_text()
    assert 'snapshotNavigationTicket() const { return _navigationScope.snapshot(); }' in handler
    domain_impl = (ROOT / 'libraries/networking/src/DomainHandler.cpp').read_text()
    reset = domain_impl.index('void DomainHandler::hardReset(')
    assert domain_impl.count('_navigationScope.next();') == 1
    assert domain_impl.index('_navigationScope.next();') > reset
    capture = setup.index('const auto navigationTicket = domainHandler.snapshotNavigationTicket();')
    enqueue = setup.index('QMetaObject::invokeMethod(this, [this, domainURL, navigationTicket]', capture)
    delivery = setup.index('domainURLChangedWithTicket(domainURL, navigationTicket)', enqueue)
    direct = setup.index('Qt::DirectConnection', delivery)
    assert capture < enqueue < delivery < direct
    parse = app.index('bool Application::prepareServerlessDomainContentsWithTicket(')
    read = app.index('tmpTree->readFromByteArray', parse)
    guard = app.index('!navigationTicket.current()', read)
    mutate = app.index('myAvatar->setSessionUUID', read)
    assert read < guard < mutate
    assert 'loadServerlessDomainWithTicket(domainURL, navigationTicket)' in app
    assert 'prepareServerlessDomainContentsWithTicket(domainURL, request->getData(), namedPaths, navigationTicket, loadTicket)' in app
    handoff = app.index('phase=serverless_handoff')
    assert 'Qt::QueuedConnection' in app[handoff:]
    assert '!navigationTicket.current() || !loadTicket.current()' in app[handoff-700:handoff]
    assert 'const auto loadTicket = _phoneServerlessLoadRequests.next();' in app
    cleanup = app.index('void Application::cleanupBeforeQuit() {')
    retire = app.index('_phoneServerlessLoadRequests.setActive(false);', cleanup)
    consent = app.index('invalidateEntityScriptConsent();', cleanup)
    exit_start = app.index('DependencyManager::prepareToExit();', cleanup)
    disconnect = app.index('getDomainHandler().disconnect(', cleanup)
    entity_shutdown = app.index('getEntities()->shutdown();', cleanup)
    assert cleanup < retire < consent < exit_start < disconnect < entity_shutdown
    assert '#if defined(ANDROID_APP_PHONE_INTERFACE)' in app[cleanup:retire]
    assert '#endif' in app[retire:consent]
    entry = app.index('void Application::loadServerlessDomainWithTicket(')
    entry_guard = app.index('!_phoneServerlessLoadRequests.snapshot().current()', entry)
    advance = app.index('_phoneServerlessLoadRequests.next()', entry)
    create_request = app.index('createResourceRequest(', entry)
    assert entry < entry_guard < advance < create_request
    navigation = app.index('void Application::domainURLChangedWithTicket(')
    navigation_guard = app.index('!_phoneServerlessLoadRequests.snapshot().current()', navigation)
    consent_effect = app.index('invalidateEntityScriptConsent();', navigation)
    mode_effect = app.index('setIsServerlessMode(domainURL.scheme()', navigation)
    assert navigation < navigation_guard < consent_effect < mode_effect


def main():
    scope = (ROOT / 'libraries/networking/src/RequestCancellation.h').read_text()
    body = scope[scope.index('namespace overte'):scope.index('Q_DECLARE_METATYPE')]
    includes = '#include <atomic>\n#include <limits>\n#include <memory>\n#include <cstdint>\n#include <algorithm>\nusing quint64=uint64_t;\n'
    with tempfile.TemporaryDirectory(prefix='overte-serverless-ticket-') as directory:
        cpp=Path(directory)/'test.cpp'; exe=Path(directory)/'test'
        cpp.write_text(includes+body+TEST)
        subprocess.run([os.environ.get('CXX','c++'),'-std=c++17','-O2',str(cpp),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True)
    source_contracts()
    print('PASS application source contracts: original signal ticket, queued delivery, parse guard before state changes, shutdown invalidation before subsystem teardown, closed navigation/load entry guards.')
    print('LIMIT: host queue adapters; no atomic cross-thread transaction, Qt integration, or device behavior proven.')


if __name__=='__main__': main()
