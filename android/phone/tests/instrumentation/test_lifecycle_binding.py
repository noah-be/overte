"""Compile Phone's real pending-navigation consumer and check its runtime entry wiring."""
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]

class PhoneLifecycleBindingTests(unittest.TestCase):
    def test_real_consumer_uses_shared_generations(self):
        with tempfile.TemporaryDirectory(prefix="phone-lifecycle-host-") as temporary:
            binary = Path(temporary) / "navigation"
            subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror", "-pthread",
                            str(Path(__file__).with_name("PhonePendingNavigationTest.cpp")),
                            "-o", str(binary)], check=True, timeout=60)
            subprocess.run([str(binary)], check=True, timeout=10)

    def test_actual_phone_callers_bind_cancel_and_bounded_delivery(self):
        source = ROOT / "android/phone/apps/phoneInterface/src"
        native = (source / "PhoneUrlHandler.cpp").read_text()
        self.assertIn("_pending(overte::lifecycle::applicationGate())", native)
        self.assertIn("phone::PendingNavigation<QString> _pending", native)
        self.assertIn("overte::lifecycle::observeNativeVisibility(foreground)", native)
        self.assertNotIn("applicationGate().visible(", native)
        self.assertIn("urlDelivery(QCoreApplication::instance())->cancel()", native)
        java = (source / "main/java/org/overte/phone/PhoneInterfaceActivity.java").read_text()
        pause = java.split("protected void onPause() {", 1)[1].split("super.onPause();", 1)[0]
        self.assertIn("replacePendingUrl(null)", pause)
        self.assertIn("publishNativeForegroundState(false)", pause)
        self.assertIn("mainHandler.postDelayed(drainForegroundTask, 250)", java)
        self.assertIn("if (foregroundDelivery.foregroundDelivered())", java)
        self.assertIn("PhonePendingUrlPolicy.initialDestination(", java)
        self.assertNotIn("STATE_PENDING_URL", java)

    def test_original_phone_submit_with_shared_qt_publication(self):
        native = (ROOT / "android/phone/apps/phoneInterface/src/PhoneUrlHandler.cpp").read_text()
        lifecycle = native.split("class PendingLifecycleDelivery final", 1)[1]
        submit = "void submit(bool foreground) {" + lifecycle.split(
            "void submit(bool foreground) {", 1)[1].split("\nprivate:", 1)[0]
        shared = (ROOT / "interface/src/Application_Events.cpp").read_text()
        publication = "namespace {\nvoid publishClientVisibility(" + shared.split(
            "namespace {\nvoid publishClientVisibility(", 1)[1].split(
            "\nvoid Application::activeChanged(", 1)[0]
        url_entry = 'extern "C" JNIEXPORT jboolean JNICALL\n' + native.split(
            'extern "C" JNIEXPORT jboolean JNICALL\n', 1)[1].split(
            '\nextern "C" JNIEXPORT jboolean JNICALL', 1)[0]
        node_header = (ROOT / "libraries/networking/src/NodeList.h").read_text()
        node_setter = re.search(r"    void setClientTransportVisibility\(bool foreground\) \{[^}]+\}", node_header).group()
        node_field = re.search(r"    std::atomic<bool> _clientTransportSuspended[^;]+;", node_header).group()
        # Compile original Phone submit/URL-entry bodies, Shared publication and
        # the actual NodeList forwarding setter. Only dependency lookup, HTTP/
        # DomainHandler/domain-auth forwarding, JNI string conversion and
        # AndroidHelper actions are boundaries; no full Android runtime is claimed.
        driver = r'''
#include <cassert>
#include <atomic>
#include <string>
#include <type_traits>
#include <QtCore/QCoreApplication>
#include "libraries/shared/src/PhoneLoadingDiagnostics.h"
#include <QtCore/QThread>
#include <QtCore/QString>
#include "android/phone/apps/phoneInterface/src/PhonePendingNavigation.h"
#include "android/phone/apps/phoneInterface/src/PhoneLifecycleHandoff.h"
#include "libraries/networking/src/RequestCancellation.h"
struct AddressManager {
    overte::network::RequestScope requests;
    bool foreground = false;
    void setClientLookupVisibility(bool active) {
        foreground = active; requests.setActive(active);
    }
} addresses;
struct DomainAccountManager {
    bool foreground = false;
    void setClientAuthVisibility(bool active) { foreground = active; }
} domainAuth;
struct NodeList {
    struct DiscoveryBoundary {
        bool foreground = false;
        void setClientDiscoveryVisibility(bool active) { foreground = active; }
    } _domainHandler;
#include "node-visibility-state.inc"
    bool foreground() const {
        const bool active = !_clientTransportSuspended.load(std::memory_order_acquire);
        assert(active == _domainHandler.foreground);
        assert(active == domainAuth.foreground);
        return active;
    }
} nodes;
struct DependencyManager {
    template<class T> static bool isSet() { return true; }
    template<class T> static T* get() {
        if constexpr (std::is_same<T, NodeList>::value) { return &nodes; }
        else if constexpr (std::is_same<T, DomainAccountManager>::value) { return &domainAuth; }
        else { return &addresses; }
    }
};
overte::lifecycle::Gate gate;
overte::lifecycle::Gate& overte::lifecycle::applicationGate() { return gate; }
#include "publication.inc"
struct UrlDelivery {
    phone::PendingNavigation<std::string> pending { gate };
    unsigned cancels = 0;
    unsigned submissions = 0;
    void cancel() { ++cancels; pending.clear(); }
    void submit(const QString& value, const overte::network::RequestTicket&) {
        ++submissions; pending.replace(value.toStdString(), !value.isEmpty());
    }
} urls;
UrlDelivery* urlDelivery(QCoreApplication* app) { assert(app); return &urls; }
// JNI conversion is an unchanged boundary, not a simulated Android runtime.
using jboolean = bool;
using jclass = void*;
using jstring = const char*;
struct JNIEnv {};
#define JNIEXPORT
#define JNICALL
#define JNI_FALSE false
#define JNI_TRUE true
QString fromJavaString(JNIEnv*, jstring value) { return QString::fromUtf8(value); }
#include "phone-url-requests.inc"
#include "phone-url-entry.inc"
struct PhoneDelivery {
    phone::LifecycleHandoff _handoff;
    phone::LifecycleHandoff::Action last = phone::LifecycleHandoff::Action::None;
    void apply(phone::LifecycleHandoff::Action action) { last = action; }
#include "phone-submit.inc"
};
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    PhoneDelivery delivery;
    delivery._handoff.markReady();
    delivery.submit(true);
    assert(!gate.snapshot().foreground && !addresses.foreground);
    assert(!nodes.foreground());
    auto send = [](const char* value) {
        return Java_org_overte_phone_PhoneInterfaceActivity_nativeProcessUrl(nullptr, nullptr, value);
    };
    assert(!send("early explicit URL")); // Java must retain/retry, not lose it.
    assert(!send("   "));
    overte::lifecycle::observeQtVisibility(true);
    assert(gate.snapshot().foreground && addresses.foreground);
    assert(nodes.foreground());
    QCoreApplication::processEvents();
    assert(urls.submissions == 0);
    assert(urls.cancels == 1); // The empty newer ingress revoked native ownership.
    urls.cancels = 0;
    assert(send("early explicit URL")); // Retry after effective Qt visibility.
    assert(urls.submissions == 0); // Queue ownership only, not applied receipt.
    QCoreApplication::processEvents();
    std::string output;
    assert(urls.pending.takeIfReady(true, output) && output == "early explicit URL");
    assert(send("queued before suspend"));
    overte::lifecycle::observeQtVisibility(false);
    overte::lifecycle::observeQtVisibility(true);
    QCoreApplication::processEvents();
    assert(urls.submissions == 1); // Resume cannot revive the queued old ticket.
    assert(!urls.pending.takeIfReady(true, output));
    auto ticket = addresses.requests.next();
    const auto generation = gate.snapshot().generation;
    urls.pending.replace("synthetic pending URL", true);
    delivery.submit(true);
    assert(ticket.current() && gate.snapshot().generation == generation);
    delivery.submit(false);
    assert(urls.cancels == 1 && !ticket.current());
    assert(!nodes.foreground());
    assert(delivery.last == phone::LifecycleHandoff::Action::EnterBackground);
    overte::lifecycle::observeQtVisibility(true);
    assert(!gate.snapshot().foreground && !addresses.foreground);
    assert(!nodes.foreground());
    delivery.submit(true);
    assert(delivery.last == phone::LifecycleHandoff::Action::EnterForeground);
    assert(nodes.foreground());
    assert(!urls.pending.takeIfReady(true, output));
    urls.pending.replace("fresh explicit URL", true);
    ticket = addresses.requests.next();
    overte::lifecycle::observeQtVisibility(false);
    delivery.submit(true);
    assert(!gate.snapshot().foreground && !addresses.foreground && !ticket.current());
    assert(!nodes.foreground());
    assert(!urls.pending.takeIfReady(true, output));
    gate.stop();
    overte::lifecycle::observeQtVisibility(true);
    delivery.submit(true);
    assert(!addresses.foreground);
    assert(!nodes.foreground());
}
'''
        flags = shlex.split(subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "Qt6Core", "Qt6Network"], text=True))
        with tempfile.TemporaryDirectory(prefix="phone-visibility-host-") as temporary:
            directory = Path(temporary)
            (directory / "publication.inc").write_text(publication)
            (directory / "phone-submit.inc").write_text(submit)
            (directory / "phone-url-entry.inc").write_text(url_entry)
            (directory / "phone-url-requests.inc").write_text(
                'overte::network::RequestScope& urlRequests()' + native.split(
                    'overte::network::RequestScope& urlRequests()', 1)[1].split(
                    'class PendingUrlDelivery', 1)[0])
            (directory / "node-visibility-state.inc").write_text(node_setter + "\n" + node_field)
            binary = directory / "test"
            subprocess.run(["c++", "-std=c++17", "-fPIC", "-pthread", "-I", str(ROOT),
                            "-I", temporary, "-x", "c++", "-", "-o", str(binary), *flags],
                           input=driver, text=True, check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=5)

if __name__ == "__main__": unittest.main()
