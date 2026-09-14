#!/usr/bin/env python3
"""Execute the real Qt guard; substitute native sampling and resource boundaries."""
from pathlib import Path
import subprocess,tempfile,shlex,os
root=Path(__file__).resolve().parents[3]
flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Gui'],text=True))
stub=r'''
#pragma once
#include <QObject>
#include <QThread>
#include <cassert>
class ResourceCache: public QObject {
public:
    qint64 budget=-1; int changes=0;
    static inline uint32_t limit=10,loading=0,pending=4;
    void setUnusedResourceCacheSize(qint64 value) {assert(QThread::currentThread()==thread());budget=value;++changes;}
    static uint32_t getRequestLimit(){return limit;}
    static void setRequestLimit(uint32_t v){limit=v;}
    static uint32_t getLoadingRequestCount(){return loading;}
    static uint32_t getPendingRequestCount(){return pending;}
};
'''
code=r'''
#include "ios/performance/FullClientMemoryGuard.h"
#include "ios/performance/NativeMetrics.h"
#include "ios/performance/MemoryWarningHandler.h"
#include <ResourceCache.h>
#include <QGuiApplication>
#include <QTimer>
#include <QPointer>
#include <cassert>
#include <functional>
namespace overte::ios {
NativeMetrics metrics; std::function<void()> warning; int fullSamples=0;
NativeMetrics sampleAvailableMemory() noexcept {return metrics;}
NativeMetrics sampleNativeMetrics() noexcept {++fullSamples;return metrics;}
void installMemoryWarningHandler(QObject* owner,std::function<void()> callback){
    QPointer<QObject> ptr(owner);warning=[ptr,callback]{if(ptr)callback();};
}
}
int main(int argc,char** argv){
    QGuiApplication app(argc,argv);QObject lifetime;
    using namespace overte::ios;constexpr uint64_t M=1024*1024;
    metrics.availableMemoryAvailable=true;metrics.availableMemoryBytes=1024*M;
    ResourceCache cache;auto* deletedCache=new ResourceCache;
    installFullClientMemoryGuard(&lifetime,{{&cache,64*M},{deletedCache,8*M}});
    delete deletedCache; // queued budget operation must be cancelled safely
    QCoreApplication::processEvents();assert(cache.budget==64*M);assert(ResourceCache::limit==2);
    auto* timer=lifetime.findChild<QTimer*>("iosMemoryPressureTimer");assert(timer&&timer->interval()==1000);
    auto tick=[&]{QMetaObject::invokeMethod(timer,"timeout",Qt::DirectConnection);QCoreApplication::processEvents();};
    metrics.availableMemoryBytes=512*M;tick();assert(cache.budget==0&&ResourceCache::limit==1);
    const auto purges=cache.changes;tick();tick();assert(cache.changes==purges);
    metrics.availableMemoryBytes=256*M;tick();assert(ResourceCache::limit==0);
    metrics.availableMemoryAvailable=false;metrics.footprintAvailable=false;tick();assert(ResourceCache::limit==0);
    metrics.availableMemoryAvailable=true;metrics.availableMemoryBytes=800*M;
    tick();tick();assert(ResourceCache::limit==0);tick();assert(ResourceCache::limit==2&&cache.budget==64*M);
    warning();QCoreApplication::processEvents();assert(ResourceCache::limit==0&&cache.budget==0);
    app.applicationStateChanged(Qt::ApplicationSuspended);assert(!timer->isActive());
    app.applicationStateChanged(Qt::ApplicationActive);assert(timer->isActive());
    assert(fullSamples==1); // normal timer never performs expensive task_info
}
'''
with tempfile.TemporaryDirectory(prefix='overte-memory-guard-') as d:
    p=Path(d);(p/'ResourceCache.h').write_text(stub);(p/'test.cpp').write_text(code)
    subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-fPIC','-I',d,'-I',str(root),str(root/'ios/performance/FullClientMemoryGuard.cpp'),str(p/'test.cpp'),'-o',str(p/'test'),*flags],check=True,timeout=60)
    subprocess.run([str(p/'test')],env={**os.environ,'QT_QPA_PLATFORM':'offscreen','XDG_RUNTIME_DIR':d},check=True,timeout=15)
setup=(root/'interface/src/Application_Setup.cpp').read_text()
call=setup.index('overte::ios::installFullClientMemoryGuard(this,')
assert setup.index('void Application::initialize(')<call
assert setup.index('ResourceCache::setRequestLimit(concurrentDownloads);')<call
assert 'concurrentDownloads = std::min(concurrentDownloads, uint32_t(2));' in setup
assert '&ShaderCache::instance()' in setup
cmake=(root/'ios/integration/CMakeLists.txt').read_text()
arc=cmake.split('set_source_files_properties("${CMAKE_CURRENT_LIST_DIR}/../performance/MemoryWarningHandler.mm"',1)[1].split(')',1)[0]
assert 'TARGET_DIRECTORY Overte' in arc and '-fobjc-arc' in arc
for cache in ['ModelCache','SoundCache','AnimationCache','MaterialCache','recording::ClipCache','TextureCache']:
    assert 'DependencyManager::get<'+cache+'>().data()' in setup
native=(root/'ios/performance/MemoryWarningHandler.mm').read_text()
assert 'UIApplicationDidReceiveMemoryWarningNotification' in native and 'removeObserver:observer' in native
assert 'Qt::QueuedConnection' in native
print('PASS real Qt guard: startup budgets, owner-thread dispatch, deleted-cache safety, pressure pause/recovery, warning, foreground timer, cheap samples; native/resource internals substituted')
