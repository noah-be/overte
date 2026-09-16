"""Run the production Phone scheduler with a real Qt pool under a raw-image backlog."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class TextureStreamingPriorityTest(unittest.TestCase):
    def test_ready_ktx_precedes_queued_raw_images_and_isolates_exceptions(self):
        source = (ROOT / 'libraries/material-networking/src/material-networking/TextureCache.cpp').read_text()
        begin = source.index('static void queueKtxTask(')
        end = source.index('\n/*@jsdoc', begin)
        driver = r'''
#include <QThreadPool>
#include <QRunnable>
#include <QElapsedTimer>
#include <QCryptographicHash>
#include <QSemaphore>
#include <QDebug>
#include <QUrl>
#include <atomic>
#include <cassert>
#include <functional>
#include <stdexcept>
#define ANDROID_APP_PHONE_INTERFACE
#define PROP_VALUE_MAX 92
#define PHONE_LOADING(...) do {} while (false)
bool diagnostic = false;
char control = '1';
bool phoneLoadingDiagnosticsEnabled() { return diagnostic; }
int __system_property_get(const char*, char* value) { value[0] = control; value[1] = 0; return 1; }
''' + source[begin:end] + r'''
int main() {
    auto* pool = QThreadPool::globalInstance();
    pool->setMaxThreadCount(1); // occupy every available worker deterministically
    QSemaphore occupied, release;
    pool->start(QRunnable::create([&] { occupied.release(); release.acquire(); }));
    assert(occupied.tryAcquire(1, 5000));
    std::atomic<int> order { 0 };
    int rawOrder = 0, ktxOrder = 0;
    pool->start(QRunnable::create([&] { rawOrder = ++order; }));
    queueKtxTask([&] { ktxOrder = ++order; }, QUrl("hifi://fixture"), 2);
    release.release();
    assert(pool->waitForDone(5000));
    assert(ktxOrder == 1 && rawOrder == 2);
    // The diagnostic control must reproduce the old FIFO ordering in the
    // exact same APK, and switching it back must restore production ordering.
    for (char selected : {'0', '1'}) {
        diagnostic = true;
        control = selected;
        order = 0;
        pool->start(QRunnable::create([&] { occupied.release(); release.acquire(); }));
        assert(occupied.tryAcquire(1, 5000));
        pool->start(QRunnable::create([&] { rawOrder = ++order; }));
        queueKtxTask([&] { ktxOrder = ++order; }, QUrl(), 2);
        release.release();
        assert(pool->waitForDone(5000));
        assert(ktxOrder == (selected == '1' ? 1 : 2));
        assert(rawOrder == (selected == '1' ? 2 : 1));
    }
    queueKtxTask([] { throw std::runtime_error("fixture"); }, QUrl(), 1);
    assert(pool->waitForDone(5000));
    assert(pool->maxThreadCount() == 1); // no hidden concurrency increase
}
'''
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='phone-ktx-priority-') as temporary:
            path = Path(temporary)
            (path / 'driver.cpp').write_text(driver)
            subprocess.run(['c++', '-std=c++17', '-fPIC', str(path / 'driver.cpp'), '-o', str(path / 'test'), *flags], check=True, timeout=30)
            subprocess.run([str(path / 'test')], check=True, timeout=15)


if __name__ == '__main__':
    unittest.main()
