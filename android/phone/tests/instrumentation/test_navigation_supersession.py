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
        driver = r'''
#include <cassert>
#include <QCoreApplication>
#include <QPointer>
#include <QStringList>
#include "android/phone/apps/phoneInterface/src/PhonePendingNavigation.h"
#include "libraries/networking/src/RequestCancellation.h"
class AndroidHelper : public QObject {
    Q_OBJECT
public:
    bool ready = false;
    QStringList navigated;
    static AndroidHelper& instance() { static AndroidHelper helper; return helper; }
    bool isLoadComplete() const { return ready; }
    void processURL(const QString& url) { navigated.append(url); }
    void loaded() { ready = true; emit qtAppLoadComplete(); }
signals:
    void qtAppLoadComplete();
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
''' + delivery + entry + r'''
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    gate.visible(true);
    auto& helper = AndroidHelper::instance();
    auto send = [](const char* url) {
        return Java_org_overte_phone_PhoneInterfaceActivity_nativeProcessUrl(nullptr, nullptr, url);
    };
    // Both JNI calls return before Qt processes either. Only B may navigate.
    helper.ready = true;
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
    helper.ready = false;
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
    helper.ready = false;
    assert(!send(""));
    assert(send("hifi://retained"));
    QCoreApplication::processEvents();
    helper.loaded();
    assert(helper.navigated == QStringList{"hifi://retained"});
    helper.navigated.clear();
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
