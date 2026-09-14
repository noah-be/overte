"""Execute the production Qt delivery/JNI entry; Android strings and URL sink are seams."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / 'android/phone/apps/phoneInterface/src'


class NavigationSupersessionTest(unittest.TestCase):
    def test_queued_and_buffered_destinations_follow_latest_intent(self):
        native = (SOURCE / 'PhoneUrlHandler.cpp').read_text()
        delivery = native[native.index('// One application-owned'):native.index('QVariantMap touchUiMetricsMap')]
        entry = native[native.index('extern "C" JNIEXPORT jboolean JNICALL'):native.index(
            'extern "C" JNIEXPORT jboolean JNICALL\nJava_org_overte_phone_PhoneInterfaceActivity_nativeHandleBack')]
        helper_source = (ROOT / 'interface/src/AndroidHelper.cpp').read_text()
        helper_methods = helper_source[helper_source.index('void AndroidHelper::notifyStartupNavigationReady()'):helper_source.index('void AndroidHelper::notifyEnterForeground()')]
        application = (ROOT / 'interface/src/Application.cpp').read_text()
        checkpoint = application[application.index('#if defined(ANDROID_APP_PHONE_INTERFACE)\n    // An accepted early'):application.index('#ifdef Q_OS_ANDROID\n    const auto startupDestination')]
        # Execute the real Application acceptance branch. The large existing
        # default-navigation body is represented by a counted fallback seam.
        checkpoint += '\n++fallback;\n#if defined(ANDROID_APP_PHONE_INTERFACE)\n}\n#endif\n'
        ui = (ROOT / 'interface/src/Application_UI.cpp').read_text()
        resume_guard = ui[ui.index('    if (!_resumeAfterLoginDialogActionTaken_SafeToRun)'):ui.index('    _resumeAfterLoginDialogActionTaken_Completed = true;') + len('    _resumeAfterLoginDialogActionTaken_Completed = true;')]
        early = ui[ui.index('#if defined(ANDROID_APP_PHONE_INTERFACE)\n    // Resume, avatar/settings'):ui.index('\n}\n\nQSharedPointer<OffscreenUi> Application::getOffscreenUI()')]
        driver = r'''
#include <cassert>
#include <functional>
#include "libraries/shared/src/PhoneLoadingDiagnostics.h"
#include <QCoreApplication>
#include <QPointer>
#include <QStringList>
#include <QScopedValueRollback>
#include <QThread>
#include <QVariant>
#define ANDROID_APP_PHONE_INTERFACE
#include "android/phone/apps/phoneInterface/src/PhonePendingNavigation.h"
#include "libraries/networking/src/RequestCancellation.h"
class AndroidHelper : public QObject {
    Q_OBJECT
public:
    bool _loadComplete = false;
    bool _startupNavigationReady = true;
    bool _startupUrlDispatching = false;
    bool reject = false;
    bool reenter = false;
    std::function<void()> onProcess;
    QStringList navigated;
    static AndroidHelper& instance() { static AndroidHelper helper; return helper; }
    bool isLoadComplete() const { return _loadComplete; }
    bool isStartupNavigationReady() const { return _startupNavigationReady; }
    bool processURL(const QString& url) {
        if (onProcess) { const auto callback = onProcess; callback(); }
        if (reenter) { notifyStartupNavigationReady(); assert(!dispatchPendingStartupUrl()); }
        if (reject) { return false; }
        navigated.append(url); return true;
    }
    void notifyStartupNavigationReady();
    bool dispatchPendingStartupUrl();
    void destinationSelected() { notifyStartupNavigationReady(); }
    void loaded() { _loadComplete = true; emit qtAppLoadComplete(); }
signals:
    void qtAppLoadComplete();
    void startupNavigationReady();
    void startupUrlDispatchRequested(bool& accepted);
};
overte::lifecycle::Gate gate;
overte::lifecycle::Gate& overte::lifecycle::applicationGate() { return gate; }
using jboolean = bool;
using jclass = void*;
using jstring = const char*;
struct JNIEnv {};
#define JNIEXPORT
#define JNICALL
#define JNI_TRUE true
#define JNI_FALSE false
QString fromJavaString(JNIEnv*, jstring text) { return QString::fromUtf8(text); }
''' + helper_methods + delivery + entry + r'''
class FakeReply : public QNetworkReply {
public:
    void finish() { emit finished(); }
    void abort() override { }
    qint64 readData(char*, qint64) override { return 0; }
};
namespace SandboxUtils {
    FakeReply* last = nullptr;
    int requests = 0;
    QNetworkReply* getStatus() { ++requests; return last = new FakeReply; }
}
class StartupFixture : public QObject {
public:
    struct Monitor { int calls = 0; void init() { ++calls; } } _connectionMonitor;
    QVariant testProperty;
    QString _urlParam;
    bool _resumeAfterLoginDialogActionTaken_SafeToRun = true;
    bool _resumeAfterLoginDialogActionTaken_WasPostponed = false;
    bool _resumeAfterLoginDialogActionTaken_Completed = false;
    int fallback = 0;
    QString sentTo, SENT_TO_PREVIOUS_LOCATION = "previous_location";
    void resumeTail() {
''' + resume_guard + '\n' + early + r'''
    }
    void handleSandboxStatus(QNetworkReply*, bool acceptedStartupUrl) {
''' + checkpoint + r'''
        AndroidHelper::instance().notifyStartupNavigationReady();
    }
};
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    gate.visible(true);
    auto& helper = AndroidHelper::instance();
    auto send = [](const char* url) {
        return Java_org_overte_phone_PhoneInterfaceActivity_nativeProcessUrl(nullptr, nullptr, url);
    };
    // Reproduce the actual startup ordering: Qt is ready, but the delayed
    // default destination has not been selected. An accepted link must wait.
    helper.loaded();
    helper._startupNavigationReady = false;
    assert(send("hifi://startup"));
    QCoreApplication::processEvents();
    assert(helper.navigated.empty());
    helper.reenter = true;
    assert(helper.dispatchPendingStartupUrl());
    assert(!helper._startupNavigationReady); // reentrant notification cannot drain
    helper.reenter = false;
    helper.destinationSelected();
    assert((helper.navigated == QStringList{"hifi://startup"}));
    helper.destinationSelected();
    assert(helper.navigated.size() == 1); // no duplicate delivery
    assert(!helper.dispatchPendingStartupUrl());
    helper.navigated.clear();
    // Execute the late Application checkpoint as well as the early path below.
    bool acceptedStartupUrl = false;
    int fallback = 0;
    QString sentTo, SENT_TO_PREVIOUS_LOCATION = "previous_location";
    auto checkpoint = [&]() {
''' + checkpoint + r'''
    };
    helper._startupNavigationReady = false;
    assert(send("hifi://checkpoint"));
    QCoreApplication::processEvents();
    checkpoint();
    assert(fallback == 0);
    assert(helper.navigated == QStringList{"hifi://checkpoint"});
    helper.destinationSelected();
    helper.navigated.clear();
    // Empty and rejected checkpoints retain the caller's normal fallback.
    helper._startupNavigationReady = false;
    checkpoint();
    assert(fallback == 1);
    assert(!helper.dispatchPendingStartupUrl());
    assert(send("hifi://rejected"));
    QCoreApplication::processEvents();
    helper.reject = true;
    checkpoint();
    assert(fallback == 2);
    helper.reject = false;
    helper.destinationSelected();
    assert(helper.navigated.empty());
    // Cancellation still applies while waiting at the later startup gate.
    helper._startupNavigationReady = false;
    assert(send("hifi://obsolete"));
    QCoreApplication::processEvents();
    assert(!send(nullptr));
    assert(!helper.dispatchPendingStartupUrl());
    helper.destinationSelected();
    QCoreApplication::processEvents();
    assert(helper.navigated.empty());
    // Both JNI calls return before Qt processes either. Only B may navigate.
    helper._loadComplete = true;
    assert(send("hifi://a") && send("hifi://b"));
    QCoreApplication::processEvents();
    assert(helper.navigated == QStringList{"hifi://b"});
    helper.navigated.clear();
    // A rejected/new non-VIEW intent must invalidate an already queued URL.
    assert(send("hifi://stale"));
    assert(!send(nullptr));
    QCoreApplication::processEvents();
    assert(helper.navigated.empty());
    // Startup-buffered A must also be invalidated before queued cleanup runs.
    helper._loadComplete = false;
    assert(!helper.dispatchPendingStartupUrl());
    assert(send("hifi://buffered"));
    QCoreApplication::processEvents();
    assert(!send(""));
    helper.loaded();
    assert(helper.navigated.empty());
    assert(send("hifi://fresh"));
    QCoreApplication::processEvents();
    assert(helper.navigated == QStringList{"hifi://fresh"});
    helper.navigated.clear();
    // A cancellation queued before a newer intent must not erase that intent.
    helper._loadComplete = false;
    assert(!send(""));
    assert(send("hifi://retained"));
    QCoreApplication::processEvents();
    helper.loaded();
    assert(helper.navigated == QStringList{"hifi://retained"});
    helper.navigated.clear();
    // A runtime reentrant submission remains deliverable after startup.
    // There must be no guard that leaves B buffered without a future wakeup.
    helper.onProcess = [&]() {
        helper.onProcess = {};
        urlDelivery(&app)->submit("hifi://runtime-b", urlRequests().next());
    };
    assert(send("hifi://runtime-a"));
    QCoreApplication::processEvents();
    assert(helper.navigated.contains("hifi://runtime-a"));
    assert(helper.navigated.contains("hifi://runtime-b"));
    assert(helper.navigated.size() == 2);
    helper.navigated.clear();
    // The real resume tail dispatches before requesting sandbox status.
    StartupFixture earlyAccepted;
    helper._startupNavigationReady = false;
    assert(send("hifi://early-a"));
    QCoreApplication::processEvents();
    const int requestsBefore = SandboxUtils::requests;
    helper.onProcess = [&]() {
        assert(earlyAccepted._connectionMonitor.calls == 1);
        assert(SandboxUtils::requests == requestsBefore);
        QCoreApplication::processEvents(); // no older sandbox callback exists
    };
    helper.reenter = true;
    earlyAccepted.resumeTail();
    helper.reenter = false;
    helper.onProcess = {};
    auto firstReply = SandboxUtils::last;
    earlyAccepted.resumeTail(); // duplicate keyboard-focus notification
    assert(earlyAccepted._connectionMonitor.calls == 1);
    assert(SandboxUtils::last == firstReply);
    assert(helper.navigated == QStringList{"hifi://early-a"});
    assert(helper._startupNavigationReady);
    assert(send("hifi://early-b"));
    QCoreApplication::processEvents();
    firstReply->finish();
    assert(earlyAccepted.fallback == 0 && earlyAccepted._connectionMonitor.calls == 1);
    assert((helper.navigated == QStringList{"hifi://early-a", "hifi://early-b"}));
    delete firstReply;
    helper.navigated.clear();
    // Empty early checkpoint still accepts a link arriving before the callback.
    StartupFixture lateAccepted;
    helper._startupNavigationReady = false;
    lateAccepted.resumeTail();
    assert(!helper._startupNavigationReady);
    assert(send("hifi://late"));
    QCoreApplication::processEvents();
    SandboxUtils::last->finish();
    assert(lateAccepted.fallback == 0 && lateAccepted._connectionMonitor.calls == 1);
    assert(helper.navigated == QStringList{"hifi://late"});
    delete SandboxUtils::last;
    helper.navigated.clear();
    // Empty, rejected, explicit cancellation and lifecycle invalidation all
    // retain the one normal callback fallback without a second monitor init.
    for (int mode = 0; mode != 4; ++mode) {
        StartupFixture fallbackRun;
        helper._startupNavigationReady = false;
        if (mode) { assert(send("hifi://discarded")); QCoreApplication::processEvents(); }
        if (mode == 1) { helper.reject = true; }
        if (mode == 2) { assert(!send(nullptr)); }
        if (mode == 3) { gate.visible(false); gate.visible(true); }
        fallbackRun.resumeTail();
        helper.reject = false;
        QCoreApplication::processEvents();
        SandboxUtils::last->finish();
        assert(fallbackRun.fallback == 1 && fallbackRun._connectionMonitor.calls == 1);
        assert(helper.navigated.empty());
        delete SandboxUtils::last;
    }
    // Test mode without an explicit CLI URL keeps its no-navigation policy.
    StartupFixture testNoUrl;
    helper._startupNavigationReady = false;
    testNoUrl.testProperty = true;
    const int testRequestsBefore = SandboxUtils::requests;
    testNoUrl.resumeTail();
    assert(testNoUrl._connectionMonitor.calls == 0);
    assert(SandboxUtils::requests == testRequestsBefore);
    helper.destinationSelected();
    // Shared visibility generation remains an independent cancellation fence.
    assert(send("hifi://suspended"));
    gate.visible(false); gate.visible(true);
    QCoreApplication::processEvents();
    assert(helper.navigated.empty());
}
#include "driver.moc"
'''
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core', 'Qt6Network'], text=True))
        qt_libexec = subprocess.check_output(['pkg-config', '--variable=libexecdir', 'Qt6Core'], text=True).strip()
        with tempfile.TemporaryDirectory(prefix='phone-navigation-') as scratch:
            path = Path(scratch)
            (path / 'driver.cpp').write_text(driver)
            subprocess.run([qt_libexec + '/moc', str(path / 'driver.cpp'), '-o', str(path / 'driver.moc')], check=True, timeout=20)
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(ROOT), str(path / 'driver.cpp'),
                            '-o', str(path / 'test'), *flags], check=True, timeout=30)
            subprocess.run([str(path / 'test')], check=True, timeout=5)

    def test_complete_resume_preprocessor_branches(self):
        ui = (ROOT / 'interface/src/Application_UI.cpp').read_text()
        body = ui[ui.index('void Application::resumeAfterLoginDialogActionTaken()'):ui.index('QSharedPointer<OffscreenUi> Application::getOffscreenUI()')]
        for defines in ([], ['Q_OS_ANDROID'], ['Q_OS_ANDROID', 'ANDROID_APP_PICO_INTERFACE'],
                        ['Q_OS_ANDROID', 'ANDROID_APP_PHONE_INTERFACE']):
            output = subprocess.check_output(
                ['c++', '-E', '-P', '-x', 'c++', *['-D' + item for item in defines], '-'],
                input=body, text=True, stderr=subprocess.PIPE)
            if 'ANDROID_APP_PHONE_INTERFACE' in defines:
                self.assertEqual(output.count('SandboxUtils::getStatus()'), 1)
                self.assertEqual(output.count('_connectionMonitor.init()'), 1)
                self.assertLess(output.index('setRefreshRateRegime'), output.index('dispatchPendingStartupUrl'))
                self.assertLess(output.index('getDomainHandler().resetting()'), output.index('_connectionMonitor.init()'))
                self.assertLess(output.index('dispatchPendingStartupUrl'), output.index('SandboxUtils::getStatus()'))
            else:
                self.assertEqual(output.count('SandboxUtils::getStatus()'), 2)
                self.assertNotIn('dispatchPendingStartupUrl', output)
                self.assertNotIn('_connectionMonitor.init()', output)
                self.assertLess(output.index('SandboxUtils::getStatus()'), output.index('setRefreshRateRegime'))

    def test_actual_java_replacement_revokes_native_ownership(self):
        source = (SOURCE / 'main/java/org/overte/phone/PhoneInterfaceActivity.java').read_text()
        method = 'private void replacePendingUrl(' + source.split('private void replacePendingUrl(', 1)[1].split('\n}\n', 1)[0]
        driver = '''class ReplacementTest {
    String pendingUrl;
    int pendingUrlRetryAttempts, cancellations;
    boolean unavailable;
    boolean nativeProcessUrl(String value) {
        if (unavailable) throw new UnsatisfiedLinkError();
        if (value == null || value.isEmpty()) ++cancellations;
        else throw new AssertionError("replacement must not navigate before resume");
        return false;
    }
''' + method + '''
    public static void main(String[] args) {
        ReplacementTest activity = new ReplacementTest();
        activity.replacePendingUrl("hifi://new");
        if (activity.cancellations != 1 || !"hifi://new".equals(activity.pendingUrl)) throw new AssertionError();
        activity.replacePendingUrl(null);
        if (activity.cancellations != 2 || activity.pendingUrl != null) throw new AssertionError();
        activity.unavailable = true;
        activity.replacePendingUrl("hifi://startup");
        if (!"hifi://startup".equals(activity.pendingUrl)) throw new AssertionError();
    }
}
'''
        with tempfile.TemporaryDirectory(prefix='phone-intent-') as scratch:
            path = Path(scratch)
            (path / 'ReplacementTest.java').write_text(driver)
            subprocess.run(['javac', '-d', scratch, str(path / 'ReplacementTest.java')], check=True, timeout=20)
            subprocess.run(['java', '-cp', scratch, 'ReplacementTest'], check=True, timeout=5)


if __name__ == '__main__':
    unittest.main()
