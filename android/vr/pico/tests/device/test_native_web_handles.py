#!/usr/bin/env python3
"""Original native registry/lifetime/callbacks; real Qt, Java/QuickItem boundaries."""
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[5]
CPP = ROOT / 'android/vr/pico/apps/picoInterface/src/PicoWebViewItem.cpp'


class NativeWebHandlesTest(unittest.TestCase):
    def test_original_lifetime_rejects_reused_addresses_and_cleans_pending_creation(self):
        source = CPP.read_text()
        def between(start, end):
            return source[source.index(start):source.index(end, source.index(start))]
        registry = between('QMutex itemRegistryMutex;', 'std::atomic<JavaVM*>')
        provider = between('class PicoWebImageProvider', 'struct JniScope')
        lifetime = between('PicoWebViewItem::PicoWebViewItem(', 'void PicoWebViewItem::setUrl(')
        frames = between('QImage PicoWebViewItem::frameImage()', 'int PicoWebViewItem::pixelWidth()')
        callbacks = source[source.index('extern "C" JNIEXPORT void JNICALL\nJava_org_overte_pico_OffscreenWebView_nativeFrame'):]
        driver = r'''
#include <QCoreApplication>
#include <QHash>
#include <QImage>
#include <QMutexLocker>
#include <QPointer>
#include <QQuickImageProvider>
#include <limits>
#include <new>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
using QQuickItem = QObject; // QuickItem input setup is an explicit boundary.
using jlong = int64_t;
using jint = int32_t;
using jboolean = unsigned char;
using jobject = void*;
using jclass = void*;
union jvalue { jlong j; };
#define JNIEXPORT
#define JNICALL
// Only Java direct-buffer access and outbound command effects are substitutes.
struct JNIEnv {
    void* GetDirectBufferAddress(jobject buffer) { return buffer; }
    jlong GetDirectBufferCapacity(jobject) { return 4; }
};
static QList<jlong> destroyed;
static bool callStatic(const char* name, const char*, jvalue* args) {
    if (QString::fromLatin1(name) == "destroy") destroyed.push_back(args[0].j);
    return true;
}
class PicoWebViewItem : public QQuickItem {
public:
    explicit PicoWebViewItem(QQuickItem* parent = nullptr);
    ~PicoWebViewItem();
    enum { ItemAcceptsInputMethod = 1 };
    void setAcceptHoverEvents(bool) {}
    void setAcceptedMouseButtons(Qt::MouseButton) {}
    void setFlag(int, bool) {}
    bool _webViewCreated = false, _webViewCreationPending = false;
    int64_t _nativeHandle = 0;
    mutable QMutex _imageMutex;
    QImage _image;
    quint64 _frameSerial = 0;
    unsigned creations = 0;
    void acceptCreationResult(bool) { ++creations; }
    void acceptFrame(const void*, qsizetype, int, int);
    QImage frameImage() const;
    QString frameSource() const;
};
''' + registry + provider + lifetime + frames + callbacks + r'''
static void need(bool value, const char* reason) {
    if (!value) { std::fprintf(stderr, "%s\n", reason); std::exit(1); }
}
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    const QString mode = QString::fromLocal8Bit(argv[1]);
    JNIEnv env;
    uint32_t pixel = 0xff123456;
    if (mode == "reuse") {
        alignas(PicoWebViewItem) unsigned char storage[sizeof(PicoWebViewItem)];
        auto* first = new (storage) PicoWebViewItem;
        const jlong oldHandle = itemRegistry.key(first);
        need(oldHandle > 0, "initial handle missing");
        // A callback already admitted before destruction retains the original
        // QPointer/context, never a newly constructed object at the same address.
        Java_org_overte_pico_OffscreenWebView_nativeCreationFinished(nullptr, nullptr, oldHandle, true);
        first->~PicoWebViewItem();
        auto* second = new (storage) PicoWebViewItem;
        const jlong currentHandle = itemRegistry.key(second);
        Java_org_overte_pico_OffscreenWebView_nativeCreationFinished(nullptr, nullptr, oldHandle, true);
        Java_org_overte_pico_OffscreenWebView_nativeFrame(&env, nullptr, oldHandle, &pixel, 1, 1);
        QCoreApplication::processEvents();
        need(second->creations == 0 && second->frameImage().isNull(), "stale callback reached replacement");
        need(currentHandle > 0 && currentHandle != oldHandle, "native handle was reused");
        PicoWebImageProvider provider;
        QSize size;
        need(provider.requestImage(QString::number(oldHandle, 16) + "/1", &size, {}).isNull(), "old image URL reached replacement");
        Java_org_overte_pico_OffscreenWebView_nativeCreationFinished(nullptr, nullptr, currentHandle, true);
        Java_org_overte_pico_OffscreenWebView_nativeFrame(&env, nullptr, currentHandle, &pixel, 1, 1);
        QCoreApplication::processEvents();
        need(second->creations == 1 && !second->frameImage().isNull(), "current callback was lost");
        need(second->frameSource().startsWith("image://pico-web/" + QString::number(currentHandle, 16) + "/"), "image source uses a different identity");
        need(!provider.requestImage(QString::number(currentHandle, 16) + "/1", &size, {}).isNull(), "current image is unavailable");
        second->~PicoWebViewItem();
        need(itemRegistry.isEmpty(), "destroy retained a registry entry");
    } else if (mode == "pending") {
        auto* item = new PicoWebViewItem;
        const auto handle = itemRegistry.key(item);
        item->_webViewCreationPending = true;
        delete item;
        need(destroyed.size() == 1 && destroyed.front() == handle, "pending Java creation was not cleaned up");
    }
    else if (mode == "exhaustion") {
        nextItemHandle = std::numeric_limits<jlong>::max();
        PicoWebViewItem last, denied, stillDenied;
        need(itemRegistry.key(&last) == std::numeric_limits<jlong>::max(), "last valid handle lost");
        need(!itemRegistry.values().contains(&denied) && !itemRegistry.values().contains(&stillDenied), "exhausted handle wrapped");
        need(denied._nativeHandle == 0 && stillDenied._nativeHandle == 0, "exhaustion did not deny permanently");
        need(nextItemHandle == 0, "exhaustion state was revived");
    }
''' + '\n}\n'
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core', 'Qt6Gui', 'Qt6Quick'], text=True))
        with tempfile.TemporaryDirectory(prefix='pico-web-handles-') as scratch:
            scratch = Path(scratch)
            cpp = scratch / 'original.cpp'
            cpp.write_text(driver)
            binary = scratch / 'test'
            subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-fPIC',
                            str(cpp), '-o', str(binary), *flags], check=True, timeout=30)
            for case in ('reuse', 'pending', 'exhaustion'):
                with self.subTest(case=case):
                    result = subprocess.run([str(binary), case], capture_output=True, text=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_all_native_commands_and_image_urls_use_the_same_nonpointer_identity(self):
        source = CPP.read_text()
        header = CPP.with_suffix('.h').read_text()
        self.assertIn('int64_t _nativeHandle { 0 };', header)
        commands = re.findall(r'\b\w+\[0\]\.j = ([^;]+);', source)
        self.assertEqual(len(commands), 16)
        self.assertEqual(set(commands), {'_nativeHandle'})
        self.assertNotIn('reinterpret_cast<jlong>(this)', source)
        self.assertNotIn('reinterpret_cast<quintptr>(this)', source)
        self.assertIn('.arg(static_cast<qlonglong>(_nativeHandle), 0, 16)', source)
        self.assertIn('if (!_nativeHandle || !isComponentComplete()', source)


if __name__ == '__main__': unittest.main(verbosity=2)
