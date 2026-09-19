#!/usr/bin/env python3
"""Actual Pico Java/JNI and complete Shared publication, with real host Qt."""
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[5]
APP = ROOT / 'android/vr/pico/apps/picoInterface'
HERE = Path(__file__).parent


class NativeVisibilityTest(unittest.TestCase):
    def test_real_java_jni_and_shared_qt_publication(self):
        source = (ROOT / 'interface/src/Application_Events.cpp').read_text()
        publication = 'namespace {\nvoid publishClientVisibility(' + source.split(
            'namespace {\nvoid publishClientVisibility(', 1)[1].split(
            '\nvoid Application::activeChanged(', 1)[0]
        header = (ROOT / 'libraries/networking/src/NodeList.h').read_text()
        node_source = (ROOT / 'libraries/networking/src/NodeList.cpp').read_text()
        setter = re.search(r'    void setClientTransportVisibility\(bool foreground\) \{[^}]+\}', header).group()
        state = re.search(r'    std::atomic<bool> _clientTransportSuspended[^;]+;', header).group()
        domain_source = (ROOT / 'libraries/networking/src/DomainHandler.cpp').read_text()
        discovery_visibility = 'void DomainHandler::setClientDiscoveryVisibility(' + domain_source.split(
            'void DomainHandler::setClientDiscoveryVisibility(', 1)[1].split(
            'void DomainHandler::resolveDomainHostname()', 1)[0]
        auth_source = (ROOT / 'libraries/networking/src/DomainAccountManager.cpp').read_text()
        auth_visibility = 'overte::network::RequestTicket DomainAccountManager::invalidatePendingAccessToken(' + auth_source.split(
            'overte::network::RequestTicket DomainAccountManager::invalidatePendingAccessToken(', 1)[1].split(
            'void DomainAccountManager::setClientID(', 1)[0]
        entry = re.search(r'void NodeList::sendDomainServerCheckIn\(\) \{\n'
                          r'    if \(_clientTransportSuspended.load\(std::memory_order_acquire\)\) \{ return; \}',
                          node_source).group()
        driver = '''#include <jni.h>
#include <atomic>
#include <cstdlib>
#include <type_traits>
#include <QtCore/QCoreApplication>
#include <QtCore/QThread>
#include "interface/src/ApplicationLifecycle.h"
#include "interface/src/PicoQtVisibility.h"
#include "security/redaction/SafeDiagnostics.h"
#include "libraries/networking/src/RequestCancellation.h"
#include "libraries/networking/src/ScopedHostnameLookup.h"
// Original visibility method and resolver cancellation owner; only launch/
// completion effects and socket storage are boundaries. The original Shared
// ICE test separately executes complete launch helpers and resolver callbacks.
struct DomainHandler : QObject {
    overte::network::RequestScope _discoveryScope;
    overte::network::ScopedHostnameLookup _hostnameLookup, _iceHostnameLookup;
    QString _iceServerHostname;
    bool _isConnected = false;
    struct SocketBoundary { QHostAddress getAddress() const { return {}; } };
    SocketBoundary _iceServerSockAddr, _sockAddr;
    unsigned launches = 0, completions = 0;
    void resolveIceHostname() { ++launches; }
    void resolveDomainHostname() { ++launches; }
    void completedIceServerHostnameLookup() { ++completions; }
    void setClientDiscoveryVisibility(bool);
};
''' + discovery_visibility + '''
struct AddressManager {
    overte::network::RequestScope requests;
    bool foreground = false;
    void setClientLookupVisibility(bool value) { foreground = value; requests.setActive(value); }
};
AddressManager addresses;
struct NodeList {
    DomainHandler _domainHandler;
''' + setter + '\n' + state + '''
    unsigned pastFence = 0;
    void sendDomainServerCheckIn();
};
''' + entry + '''
    ++pastFence; // Explicit post-entry packet/engine boundary, not actual send.
}
NodeList nodes;
// Original auth visibility/invalidation bodies. Pending transport and outcome
// delivery are covered by the separate complete Shared manager/moc test.
struct DomainAccountManager : QObject {
    enum class LoginOutcome { Cancelled };
    overte::network::RequestScope _accessTokenRequests;
    QPointer<QNetworkReply> _pendingAccessTokenReply;
    void loginRequestFinished(overte::network::RequestTicket, overte::network::RequestTicket, int) {}
    overte::network::RequestTicket invalidatePendingAccessToken(LoginOutcome outcome = LoginOutcome::Cancelled, bool suspend = false);
    void setClientAuthVisibility(bool);
};
''' + auth_visibility + '''
DomainAccountManager domainAuth;
struct DependencyManager {
    template<class T> static bool isSet() { return true; }
    template<class T> static T* get() {
        if constexpr (std::is_same<T, NodeList>::value) return &nodes;
        else if constexpr (std::is_same<T, DomainAccountManager>::value) return &domainAuth;
        else return &addresses;
    }
};
overte::lifecycle::Gate gate;
overte::lifecycle::Gate& overte::lifecycle::applicationGate() { return gate; }
''' + publication + '''
static int testArgc = 1;
static char testName[] = "pico-visibility-test";
static char* testArgv[] = {testName, nullptr};
static overte::network::RequestTicket ticket;
static overte::network::RequestTicket discoveryTicket;
static overte::network::RequestTicket authTicket;
static QCoreApplication* testApp = nullptr;
extern "C" JNIEXPORT void JNICALL Java_org_overte_pico_PicoClientVisibilityTest_initialize(JNIEnv*, jclass) {
    testApp = new QCoreApplication(testArgc, testArgv);
}
extern "C" JNIEXPORT void JNICALL Java_org_overte_pico_PicoClientVisibilityTest_shutdown(JNIEnv*, jclass) {
    delete testApp; testApp = nullptr;
}
extern "C" JNIEXPORT void JNICALL Java_org_overte_pico_PicoClientVisibilityTest_qt(JNIEnv*, jclass, jboolean active) {
    overte::lifecycle::observeQtVisibility(active == JNI_TRUE);
}
extern "C" JNIEXPORT void JNICALL Java_org_overte_pico_PicoClientVisibilityTest_events(JNIEnv*, jclass) {
    QCoreApplication::processEvents();
}
extern "C" JNIEXPORT jboolean JNICALL Java_org_overte_pico_PicoClientVisibilityTest_allowed(JNIEnv*, jclass) {
    const auto before = nodes.pastFence;
    nodes.sendDomainServerCheckIn();
    const bool transport = nodes.pastFence != before;
    // Compare each original receiver, not an AND which hides missed denials.
    const bool expected = gate.snapshot().foreground;
    if (addresses.foreground != expected || transport != expected ||
        domainAuth._accessTokenRequests.snapshot().current() != expected ||
        nodes._domainHandler._discoveryScope.snapshot().current() != expected) std::abort();
    return expected;
}
extern "C" JNIEXPORT void JNICALL Java_org_overte_pico_PicoClientVisibilityTest_takeTicket(JNIEnv*, jclass) {
    ticket = addresses.requests.next();
    discoveryTicket = nodes._domainHandler._discoveryScope.snapshot();
    authTicket = domainAuth._accessTokenRequests.snapshot();
}
extern "C" JNIEXPORT jboolean JNICALL Java_org_overte_pico_PicoClientVisibilityTest_ticketCurrent(JNIEnv*, jclass) {
    if (ticket.current() != discoveryTicket.current()) std::abort();
    if (ticket.current() != authTicket.current()) std::abort();
    return ticket.current();
}
extern "C" JNIEXPORT void JNICALL Java_org_overte_pico_PicoClientVisibilityTest_stop(JNIEnv*, jclass) { gate.stop(); }
'''
        jdk = Path(shutil.which('javac')).resolve().parents[1]
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core', 'Qt6Network'], text=True))
        with tempfile.TemporaryDirectory(prefix='pico-native-visibility-') as scratch:
            scratch = Path(scratch)
            cpp = scratch / 'actual-publication-with-owner-boundary.cpp'
            cpp.write_text(driver)
            java = APP / 'src/main/java/org/overte/pico'
            subprocess.run(['javac', '-d', str(scratch), str(java / 'PicoClientVisibility.java'),
                str(java / 'RedactingDiagnostics.java'),
                str(ROOT / 'security/redaction/java/org/overte/security/SafeDiagnostics.java'),
                *map(str, (HERE / 'visibility-stubs').rglob('*.java')),
                str(HERE / 'java-stubs/android/util/Log.java'),
                str(HERE / 'java/org/overte/pico/PicoClientVisibilityTest.java')], check=True, timeout=25)
            for absent in (False, True):
                with self.subTest(missing_native_symbol=absent):
                    library = scratch / ('libmissing.so' if absent else 'libactual.so')
                    subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-fPIC', '-shared', '-pthread', '-DANDROID_APP_PICO_INTERFACE',
                        '-I' + str(jdk / 'include'), '-I' + str(jdk / 'include/linux'),
                        '-I' + str(ROOT), '-I' + str(ROOT / 'interface/src'),
                        *(['-DJava_org_overte_pico_PicoClientVisibility_publish=TestOnlyMissingVisibility'] if absent else []),
                        str(APP / 'lifecycle/PicoClientVisibility.cpp'), str(cpp), '-o', str(library), *flags],
                        check=True, timeout=30)
                    completed = subprocess.run(['java', '-XX:-CreateCoredumpOnCrash', '-cp', str(scratch),
                        'org.overte.pico.PicoClientVisibilityTest', str(library), *(['missing'] if absent else [])],
                        cwd=scratch, capture_output=True, text=True, timeout=10)
                    self.assertEqual(completed.returncode, 0, (completed.stdout + completed.stderr)[-4000:])

    def test_actual_owner_callbacks_and_full_client_only_target(self):
        source = (APP / 'src/main/java/org/overte/pico/PicoInterfaceActivity.java').read_text()
        self.assertIn('PicoClientVisibility.attach(this);', source)
        self.assertIn('if (INSTANCE.current() == this) PicoClientVisibility.foreground(this, true);', source)
        self.assertIn('if (INSTANCE.current() == this) PicoClientVisibility.foreground(this, false);', source)
        self.assertLess(source.index('PicoClientVisibility.detach(this);'), source.index('INSTANCE.clear(this);'))
        focus = source.split('public void onWindowFocusChanged(', 1)[1].split('\n    }', 1)[0]
        self.assertNotIn('PicoClientVisibility', focus)
        cmake = (APP / 'CMakeLists.txt').read_text()
        self.assertIn('target_sources(interface PRIVATE\n'
            '    "${CMAKE_CURRENT_SOURCE_DIR}/overrides/Application_Setup.cpp"\n'
            '    "${CMAKE_CURRENT_SOURCE_DIR}/lifecycle/PicoClientVisibility.cpp"', cmake)
        self.assertEqual(cmake.count('/lifecycle/PicoClientVisibility.cpp'), 1)
        self.assertFalse((APP / 'src/PicoClientVisibility.cpp').exists())


if __name__ == '__main__': unittest.main(verbosity=2)
