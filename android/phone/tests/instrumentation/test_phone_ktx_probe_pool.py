"""Exercise the production probe pool: drain, admission races and pool isolation."""
from pathlib import Path
import resource
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
DRIVER = r'''
#include <QCoreApplication>
#include <QSemaphore>
#include <QThread>
#include <QEvent>
#include <atomic>
#include <cassert>
#include <future>
#include <thread>
#include <vector>
#include <chrono>
#include "libraries/material-networking/src/material-networking/PhoneKtxProbePool.h"
using namespace std::chrono_literals;
int main(int argc,char**argv) {
    QCoreApplication app(argc,argv);
    // Accepted tasks drain even if stop happens while the first task is blocked.
    {
        PhoneKtxProbePool pool; QSemaphore entered,release;
        std::atomic<int> active{0},maximum{0},executed{0};
        assert(pool.start([&]{++active;maximum=1;entered.release();release.acquire();--active;++executed;}));
        assert(entered.tryAcquire(1,2000));
        for(int i=0;i<30;++i)assert(pool.start([&]{const int n=++active;maximum=std::max(maximum.load(),n);--active;++executed;}));
        auto stopping=std::async(std::launch::async,[&]{pool.stop();});
        while(!pool.isStopping())std::this_thread::yield();
        assert(!pool.start([]{}));assert(stopping.wait_for(20ms)==std::future_status::timeout);
        release.release();assert(stopping.wait_for(2s)==std::future_status::ready);stopping.get();
        assert(executed==31&&maximum==1);pool.stop();assert(!pool.start([]{}));
    }
    // Concurrent start/stop never loses accepted work or admits after terminal stop.
    for(int round=0;round<20;++round){
        PhoneKtxProbePool pool;std::atomic<int> accepted{0},executed{0};std::atomic<bool> go{false};
        std::vector<std::thread> producers;
        for(int k=0;k<4;++k)producers.emplace_back([&]{while(!go)std::this_thread::yield();for(int i=0;i<100;++i){if(pool.start([&]{++executed;}))++accepted;}});
        std::thread stop([&]{while(!go)std::this_thread::yield();pool.stop();});go=true;
        for(auto&thread:producers)thread.join();stop.join();pool.stop();assert(accepted==executed);assert(!pool.start([]{}));
    }
    // Destruction waits for already accepted work while its captures remain alive.
    {
        std::atomic<int> executed{0};{PhoneKtxProbePool pool;for(int i=0;i<20;++i)assert(pool.start([&]{++executed;}));}assert(executed==20);
    }
    // Saturating global pool must not prevent dedicated probe from running.
    {
        auto global=QThreadPool::globalInstance();const auto old=global->maxThreadCount();global->setMaxThreadCount(1);
        QSemaphore globalEntered,globalRelease,probeDone;
        global->start(QRunnable::create([&]{globalEntered.release();globalRelease.acquire();}));assert(globalEntered.tryAcquire(1,2000));
        PhoneKtxProbePool pool;assert(pool.start([&]{probeDone.release();}));assert(probeDone.tryAcquire(1,2000));
        pool.stop();globalRelease.release();global->waitForDone();global->setMaxThreadCount(old);
    }
    // A queued owner callback survives pool drain; owner guard must reject it.
    {
        PhoneKtxProbePool pool;QObject context;int delivered=0,applied=0;
        assert(pool.start([&]{QMetaObject::invokeMethod(&context,[&]{++delivered;if(pool.isStopping())return;++applied;},Qt::QueuedConnection);}));
        pool.stop();assert(delivered==0);QCoreApplication::sendPostedEvents(nullptr,QEvent::MetaCall);assert(delivered==1&&applied==0);
    }
    // Document stop's boundary: it drains workers, not already-running owner callbacks.
    {
        PhoneKtxProbePool pool;QObject context;int applied=0;
        assert(pool.start([&]{QMetaObject::invokeMethod(&context,[&]{if(pool.isStopping())return;std::thread stopper([&]{pool.stop();});stopper.join();++applied;},Qt::QueuedConnection);}));
        assert(!pool.isStopping());
        // Ensure worker has posted before pumping the owner event.
        QSemaphore barrier;assert(pool.start([&]{barrier.release();}));assert(barrier.tryAcquire(1,2000));
        QCoreApplication::sendPostedEvents(nullptr,QEvent::MetaCall);assert(pool.isStopping()&&applied==1);
    }
    printf("PASS: actual pool, drain, single worker, 20 concurrent-admission rounds, destruction, global saturation, queued callback guard, owner-race boundary\n");
}
'''


class ProbePoolTest(unittest.TestCase):
    def test_actual_pool(self):
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='overte-probe-pool-') as directory:
            cpp = Path(directory) / 'pool.cpp'
            exe = Path(directory) / 'pool'
            cpp.write_text(DRIVER)
            subprocess.run(['c++', '-std=c++17', '-O2', '-pthread', '-DANDROID_APP_PHONE_INTERFACE',
                            '-I', str(ROOT), str(cpp), '-o', str(exe), *flags], check=True)
            subprocess.run([str(exe)], check=True, timeout=30,
                           preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))


if __name__ == '__main__':
    unittest.main()
