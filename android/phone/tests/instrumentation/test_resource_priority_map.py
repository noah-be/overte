"""Exercise production Resource priority entry points and synchronization on host Qt."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


def driver_source():
    source = (ROOT / 'libraries/networking/src/ResourceCache.cpp').read_text()
    functions = source[source.index('void Resource::setLoadPriorityOperator('):
                       source.index('void Resource::refresh()')]
    finished = source[source.index('void Resource::finishedLoading('):
                      source.index('void Resource::setSize(')]
    copy_initializer = source[source.index('#if defined(ANDROID_APP_PHONE_INTERFACE)\n    _loadPriorityOperators('):
                              source.index('    _bytesReceived(other._bytesReceived),')]
    return r'''
#include <atomic>
#include <cassert>
#include <cfloat>
#include <functional>
#include <memory>
#include <thread>
#include <vector>
#include <QCoreApplication>
#include "libraries/networking/src/PhoneResourcePriorityMap.h"
uint qHash(const QPointer<QObject>& value, uint seed) {
    // Match ResourceCache's pointer hash; seed conversion avoids Qt6's
    // size_t/uint overload ambiguity in this Qt5-source host harness.
    return qHash(value.data(), static_cast<size_t>(seed));
}
PhoneResourcePriorityMap& phoneResourcePriorityMaps() {
    static auto* maps = new PhoneResourcePriorityMap;
    return *maps;
}
class Resource {
public:
    Resource() = default;
    // Execute the production map copy initializer. The unrelated resource
    // fields are deliberately excluded from this map-synchronization test.
    Resource(const Resource& other) :
''' + copy_initializer + r'''
        _failedToLoad(false) {}
    PhoneResourcePriorityMap::Map _loadPriorityOperators;
    bool _failedToLoad = false;
    bool _loaded = false;
    void setLoadPriorityOperator(const QPointer<QObject>&, std::function<float()>);
    float getLoadPriority();
    void finishedLoading(bool);
    void finished(bool) {}
};
''' + functions + finished + r'''
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    QObject first, second, third;
    Resource resource;
    assert(resource.getLoadPriority() == 0.0f);
    resource.setLoadPriorityOperator(&first, [] { return -7.0f; });
    resource.setLoadPriorityOperator(&second, [] { return 9.0f; });
    assert(resource.getLoadPriority() == 9.0f);
    resource.setLoadPriorityOperator(&second, [] { return 10.0f; });
    assert(resource.getLoadPriority() == 10.0f);
    Resource copy(resource);
    resource.finishedLoading(true);
    assert(resource.getLoadPriority() == 0.0f);
    assert(copy.getLoadPriority() == 10.0f);
    copy.finishedLoading(false);
    copy.setLoadPriorityOperator(&first, [] { return 30.0f; });
    assert(copy.getLoadPriority() == 10.0f); // failure gate retained

    Resource emptyCallbacks;
    emptyCallbacks.setLoadPriorityOperator(&first, {});
    assert(emptyCallbacks.getLoadPriority() == -FLT_MAX);
    assert(emptyCallbacks.getLoadPriority() == 0.0f);
    Resource deadOwner;
    auto owner = std::make_unique<QObject>();
    deadOwner.setLoadPriorityOperator(owner.get(), [] { return 20.0f; });
    owner.reset();
    assert(deadOwner.getLoadPriority() == -FLT_MAX);
    assert(deadOwner.getLoadPriority() == 0.0f);

#if defined(ANDROID_APP_PHONE_INTERFACE)
    // Mutating the same map from an evaluated callback must not invalidate
    // the snapshot or deadlock. Its effect is visible on the next selection.
    Resource reentrant;
    bool entered = false;
    reentrant.setLoadPriorityOperator(&first, [&] {
        if (!entered) {
            entered = true;
            reentrant.finishedLoading(true);
            reentrant.setLoadPriorityOperator(&second, [] { return 27.0f; });
        }
        return 3.0f;
    });
    assert(reentrant.getLoadPriority() == 3.0f);
    assert(reentrant.getLoadPriority() == 27.0f);

    struct OnDestroy {
        std::function<void()> callback;
        ~OnDestroy() { callback(); }
    };
    int destroyed = 0;
    for (int action = 0; action != 3; ++action) {
        Resource retiring;
        auto owner = std::make_unique<QObject>();
        auto capture = std::make_shared<OnDestroy>();
        capture->callback = [&] {
            ++destroyed;
            retiring.setLoadPriorityOperator(&third, [] { return 31.0f; });
        };
        retiring.setLoadPriorityOperator(owner.get(), [capture] { return 5.0f; });
        capture.reset();
        if (action == 0) {
            retiring.setLoadPriorityOperator(owner.get(), [] { return 6.0f; });
        } else if (action == 1) {
            retiring.finishedLoading(true);
        } else {
            owner.reset();
            assert(retiring.getLoadPriority() == -FLT_MAX);
        }
        assert(retiring.getLoadPriority() == 31.0f);
    }
    assert(destroyed == 3);

    // QHash detachment copies std::function captures. A capture copy is also
    // allowed to reenter; preparing writes under a map mutex would deadlock.
    struct OnCopy {
        std::shared_ptr<std::atomic<bool>> armed;
        std::function<void()> callback;
        OnCopy(std::shared_ptr<std::atomic<bool>> flag, std::function<void()> fn)
            : armed(std::move(flag)), callback(std::move(fn)) {}
        OnCopy(const OnCopy& other) : armed(other.armed), callback(other.callback) {
            if (armed->exchange(false)) { callback(); }
        }
        float operator()() const { return 2.0f; }
    };
    Resource copying;
    auto armed = std::make_shared<std::atomic<bool>>(false);
    copying.setLoadPriorityOperator(&first, OnCopy(armed, [&] {
        copying.setLoadPriorityOperator(&third, [] { return 42.0f; });
    }));
    armed->store(true);
    copying.setLoadPriorityOperator(&second, [] { return 4.0f; });
    assert(!armed->load());
    assert(copying.getLoadPriority() == 42.0f); // retry preserves nested write

    // Concurrent entry points exercise Qt's real implicitly shared map,
    // including snapshot copy and completion clear. Resource status flags
    // are not part of the concurrency contract: failure stays false and
    // only the completion thread writes _loaded.
    Resource concurrent;
    constexpr int iterations = 1500;
    std::atomic<bool> start { false };
    auto wait = [&] { while (!start.load()) { std::this_thread::yield(); } };
    std::vector<std::thread> threads;
    threads.emplace_back([&] {
        wait();
        for (int i = 0; i < iterations; ++i) {
            concurrent.setLoadPriorityOperator(&first, [i] { return float(i % 13); });
        }
    });
    threads.emplace_back([&] {
        wait();
        for (int i = 0; i < iterations; ++i) {
            concurrent.setLoadPriorityOperator(&second, [i] { return float(i % 17); });
        }
    });
    threads.emplace_back([&] {
        wait();
        for (int i = 0; i < iterations; ++i) {
            const float result = concurrent.getLoadPriority();
            assert(result >= 0.0f && result <= 16.0f);
        }
    });
    threads.emplace_back([&] {
        wait();
        for (int i = 0; i < iterations; ++i) {
            Resource current(concurrent);
            const float result = current.getLoadPriority();
            assert(result >= 0.0f && result <= 16.0f);
            current.finishedLoading(true);
        }
    });
    threads.emplace_back([&] {
        wait();
        for (int i = 0; i < iterations; ++i) { concurrent.finishedLoading(true); }
    });
    start.store(true);
    for (auto& thread : threads) { thread.join(); }
    concurrent.setLoadPriorityOperator(&third, [] { return 99.0f; });
    assert(concurrent.getLoadPriority() == 99.0f);
#endif
}
'''


class ResourcePriorityMapTest(unittest.TestCase):
    def run_driver(self, phone=True, sanitizer=False):
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='phone-priority-map-') as scratch:
            path = Path(scratch)
            (path / 'driver.cpp').write_text(driver_source())
            options = ['-DANDROID_APP_PHONE_INTERFACE'] if phone else []
            if sanitizer:
                options += ['-fsanitize=thread', '-g', '-O1', '-fno-omit-frame-pointer']
            compiled = subprocess.run(['c++', '-std=c++17', '-fPIC', '-pthread', '-I', str(ROOT),
                                       *options, str(path / 'driver.cpp'), '-o', str(path / 'test'),
                                       *flags], text=True, capture_output=True, timeout=45)
            if sanitizer and 'cannot find' in compiled.stderr and 'libtsan.so' in compiled.stderr:
                self.skipTest('ThreadSanitizer runtime is missing; instrumented binary could not link')
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run([str(path / 'test')], text=True,
                                    capture_output=True, timeout=30)
            if sanitizer and 'ThreadSanitizer: unexpected memory mapping' in result.stderr:
                self.skipTest('ThreadSanitizer runtime cannot start: unexpected memory mapping')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_production_phone_map_and_concurrent_reentrancy(self):
        self.run_driver()

    def test_non_phone_priority_semantics_remain_unchanged(self):
        self.run_driver(phone=False)

    @unittest.skipUnless(os.environ.get('OVT_RUN_TSAN') == '1', 'Set OVT_RUN_TSAN=1 to attempt ThreadSanitizer')
    def test_thread_sanitizer(self):
        self.run_driver(sanitizer=True)


if __name__ == '__main__':
    unittest.main()
