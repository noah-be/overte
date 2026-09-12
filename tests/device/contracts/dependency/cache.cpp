// Exercise the production DependencyManager with real Qt weak/shared pointers.
#include "DependencyManager.h"
#include <atomic>
#include <cassert>
#include <condition_variable>
#include <mutex>
#include <thread>
#include <vector>

struct Probe : Dependency {
    explicit Probe(int value) : generation(value) {}
    int generation;
};
struct Base : Dependency { virtual int value() const { return 1; } };
struct Derived : Base { int value() const override { return 2; } };
struct Nested : Dependency {
    Nested() { assert(DependencyManager::get<Probe>()); }
    ~Nested() { assert(DependencyManager::isSet<Probe>()); }
};
class Barrier {
public:
    void wait() {
        std::unique_lock<std::mutex> lock(mutex);
        auto previous = phase;
        if (++arrived == 9) { arrived = 0; ++phase; cv.notify_all(); }
        else { cv.wait(lock, [&] { return phase != previous; }); }
    }
private:
    std::mutex mutex;
    std::condition_variable cv;
    int arrived = 0, phase = 0;
};
int main() {
    DependencyManager::registerInheritance<Base, Derived>();
    auto derived = DependencyManager::set<Derived>();
    assert(DependencyManager::get<Base>().data() == derived.data());
    assert(DependencyManager::get<Base>()->value() == 2);
    Barrier barrier;
    std::vector<std::thread> readers;
    // Keep the same threads alive across expiration/replacement, so a stale
    // thread-local cache would fail on the second generation.
    for (int i = 0; i < 8; ++i) {
        readers.emplace_back([&] {
            for (int generation = 0; generation < 40; ++generation) {
                barrier.wait();
                for (int n = 0; n < 1000; ++n) {
                    auto value = DependencyManager::get<Probe>();
                    assert(value && value->generation == generation);
                }
                barrier.wait();
            }
        });
    }
    for (int generation = 0; generation < 40; ++generation) {
        auto owner = DependencyManager::set<Probe>(generation);
        QWeakPointer<Probe> weak = owner;
        barrier.wait(); barrier.wait();
        assert(DependencyManager::get<Probe>() == owner);
        // Constructors and destructors can perform recursive registry reads.
        auto nested = DependencyManager::set<Nested>();
        nested.clear(); DependencyManager::destroy<Nested>();
        owner.clear(); DependencyManager::destroy<Probe>();
        assert(weak.isNull()); // caches must not keep the object alive
        assert(!DependencyManager::isSet<Probe>());
    }
    for (auto& thread : readers) { thread.join(); }
    derived.clear(); DependencyManager::destroy<Derived>();
}
