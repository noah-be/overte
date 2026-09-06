#!/usr/bin/env python3
"""Original native URL/create/retry/result methods; real Qt timers, JNI boundaries."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[5]
CPP = ROOT / 'android/vr/pico/apps/picoInterface/src/PicoWebViewItem.cpp'


class NativeWebCreationTest(unittest.TestCase):
    def test_actual_qml_property_reaches_native_url_setter(self):
        qml = (ROOT / 'interface/resources/qml/+android_picoInterface/Web3DSurface.qml').read_text()
        self.assertIn('import Overte.Pico 1.0', qml)
        item = qml.split('PicoWebView {', 1)[1].split('}', 1)[0]
        self.assertIn('url: root.url', item)
        self.assertIn('Q_PROPERTY(QString url READ url WRITE setUrl NOTIFY urlChanged)',
                      CPP.with_suffix('.h').read_text())
        self.assertIn('qmlRegisterType<PicoWebViewItem>("Overte.Pico", 1, 0, "PicoWebView")',
                      CPP.read_text())

    def test_new_url_recovers_exhausted_creation_without_duplicate_pending_work(self):
        source = CPP.read_text()
        def between(start, end):
            return source[source.index(start):source.index(end, source.index(start))]
        methods = between('void PicoWebViewItem::setUrl(', 'void PicoWebViewItem::setUserAgent(')
        methods += between('void PicoWebViewItem::createWebView()', 'QImage PicoWebViewItem::frameImage()')
        fields = CPP.with_suffix('.h').read_text().split('    QString _url;', 1)[1].split('    bool _pointerPressed', 1)[0]
        driver = r'''
#include <QCoreApplication>
#include <QEventLoop>
#include <QTimer>
#include <QString>
#include <QList>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
// JNI string allocation and Java command/creation effects are substitutes.
// Production Java URL policy is exercised by its separate original test.
using jchar = char16_t;
using jstring = QString*;
union jvalue { int64_t j; int i; bool z; jstring l; };
struct JNIEnv {
    jstring NewString(const jchar* chars, int size) {
        return new QString(QString::fromUtf16(chars, size));
    }
    void DeleteLocalRef(jstring value) { delete value; }
    bool ExceptionCheck() const { return false; }
    void ExceptionClear() {}
};
struct JniScope { JNIEnv storage; JNIEnv* env = &storage; };
struct Command { QString name, url; };
static QList<Command> commands;
static bool callStatic(const char* name, const char*, jvalue* args) {
    const QString command = QString::fromLatin1(name);
    commands.push_back({command, command == "create" ? *args[3].l :
        command == "load" ? *args[1].l : QString()});
    return true;
}
// QuickItem completion/geometry/signals are explicit test boundaries.
class PicoWebViewItem : public QObject {
public:
    QString _url;
''' + fields + r'''
    bool complete = true;
    int changed = 0;
    PicoWebViewItem() { _nativeHandle = 7; }
    bool isComponentComplete() const { return complete; }
    int pixelWidth() const { return 640; }
    int pixelHeight() const { return 480; }
    void urlChanged() { ++changed; }
    void setUseBackground(bool value) { _useBackground = value; }
    void setUrl(const QString&);
    void createWebView();
    void scheduleCreationRetry();
    void acceptCreationResult(bool);
};
''' + methods + r'''
static void need(bool value, const char* message) {
    if (!value) { std::fprintf(stderr, "%s\n", message); std::exit(1); }
}
static int count(const char* name) {
    int result = 0;
    for (const auto& command : commands) if (command.name == name) ++result;
    return result;
}
static void waitForRetry() {
    QEventLoop loop;
    QTimer::singleShot(1200, &loop, &QEventLoop::quit);
    loop.exec();
}
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    const QString mode = QString::fromLocal8Bit(argv[1]);
    PicoWebViewItem item;
    if (mode == "exhausted") {
        // The production failure result at the exhausted retry count schedules
        // no more timers. A later real property change must still recover.
        item._url = "about:blank";
        item._webViewCreationRetries = 3;
        item.acceptCreationResult(false);
        need(!item._webViewCreationRetryScheduled, "exhausted failure scheduled more work");
        item.setUrl("https://example.invalid/recovered");
        need(count("create") == 1 && item._webViewCreationPending,
             "new URL never re-entered creation after exhausted failures");
        need(commands.front().url == item._url && item._webViewCreationRetries == 0,
             "new URL did not receive a fresh bounded attempt budget");
        item.acceptCreationResult(false);
        need(item._webViewCreationRetryScheduled && item._webViewCreationRetries == 1,
             "fresh target did not retain original bounded retry path");
        waitForRetry();
        need(count("create") == 2 && item._webViewCreationPending,
             "original Qt retry timer did not reach new target");
    } else if (mode == "pending") {
        item._url = "about:blank";
        item.createWebView();
        item.setUrl("https://example.invalid/current");
        need(count("create") == 1 && item._webViewCreationPending, "URL change duplicated pending creation");
        item.acceptCreationResult(true);
        need(count("load") == 1 && commands[1].url == item._url,
             "successful pending creation did not apply current URL");
        item.setUrl("https://example.invalid/next");
        need(count("create") == 1 && count("load") == 2, "created URL change recreated WebView");
        need(commands.back().url == item._url, "created view received stale URL");
    } else if (mode == "same") {
        item._url = "about:blank";
        item._webViewCreationRetries = 3;
        item.setUrl(item._url);
        need(commands.isEmpty() && item.changed == 0 && item._webViewCreationRetries == 3,
             "unchanged URL reset retry budget");
    } else if (mode == "incomplete") {
        item.complete = false;
        item.setUrl("about:blank");
        need(commands.isEmpty(), "incomplete QML item created Java view");
        item.complete = true;
        item.createWebView();
        need(count("create") == 1, "completed item lost stored URL");
    } else if (mode == "scheduled") {
        item._url = "about:blank";
        item.acceptCreationResult(false);
        item.setUrl("https://example.invalid/recovered");
        need(count("create") == 1 && item._webViewCreationPending,
             "changed URL did not start while old retry was scheduled");
        item.acceptCreationResult(true);
        waitForRetry();
        need(count("create") == 1 && item._webViewCreated,
             "old scheduled retry duplicated successful new creation");
    }
}
'''
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='pico-web-creation-') as scratch:
            scratch = Path(scratch)
            cpp = scratch / 'original.cpp'
            cpp.write_text(driver)
            binary = scratch / 'test'
            subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-fPIC',
                            str(cpp), '-o', str(binary), *flags], check=True, timeout=30)
            for case in ('exhausted', 'pending', 'same', 'incomplete', 'scheduled'):
                with self.subTest(case=case):
                    result = subprocess.run([str(binary), case], capture_output=True,
                                            text=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__': unittest.main(verbosity=2)
